"""
KAIROS v2 — LangGraph agent.
State machine: identify → guardrails → generate → send_email → log
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import text as sql_text

from src.agents.kairos.channels import send_email
from src.agents.kairos.guardrails import (
    check_profile_eligible,
    get_eligible_targets,
    is_within_sending_window,
)
from src.agents.kairos.message_gen import generate_message
from src.database import AsyncSessionFactory

logger = logging.getLogger(__name__)


class KairosState(TypedDict):
    run_id: str
    trigger_type: str
    segment: str
    max_per_segment: int
    brand_context: str
    existing_targets: list[dict]
    cold_targets: list[dict]
    sequences_created: list[str]
    emails_sent: int
    wa_sent: int
    errors: list[str]
    skipped: int


async def _create_and_send_email(
    profile: dict,
    segment: str,
    state: KairosState,
) -> tuple[str | None, str | None]:
    """Cria sequência, envia email e retorna (seq_id, error)."""
    profile_id = str(profile["profile_id"])
    email = profile.get("email")
    phone = profile.get("phone")

    eligible, _reason = await check_profile_eligible(profile_id, segment)
    if not eligible:
        return None, "skipped"
    if not email:
        return None, "skipped"

    msg = await generate_message(
        profile,
        segment,
        "email",
        state.get("brand_context", "VERTEX"),
    )

    seq_id = str(uuid.uuid4())
    async with AsyncSessionFactory() as session:
        await session.execute(
            sql_text("""
                INSERT INTO kairos_sequences
                    (id, profile_id, run_id, segment, trigger_type, status,
                     email, phone, email_subject)
                VALUES (:id, :pid, :run, :seg, :trig, 'email_pending',
                        :email, :phone, :subj)
            """),
            {
                "id": seq_id,
                "pid": profile_id,
                "run": state["run_id"],
                "seg": segment,
                "trig": state["trigger_type"],
                "email": email,
                "phone": phone,
                "subj": msg.get("subject", ""),
            },
        )
        await session.commit()

    result = await send_email(
        to_email=email,
        subject=msg.get("subject", ""),
        body_html=msg.get("body_html", ""),
        body_text=msg.get("body_text", ""),
        tags=["kairos", segment, state["run_id"]],
    )

    async with AsyncSessionFactory() as session:
        if result["success"]:
            await session.execute(
                sql_text("""
                    UPDATE kairos_sequences
                    SET status = 'email_sent',
                        email_sent_at = NOW(),
                        email_message_id = :mid
                    WHERE id = :sid
                """),
                {"mid": result.get("id"), "sid": seq_id},
            )
            await session.execute(
                sql_text("""
                    INSERT INTO kairos_outreach_log
                        (id, sequence_id, profile_id, channel, action,
                         message_preview, provider_id)
                    VALUES (:id, :sid, :pid, 'email', 'sent', :preview, :prov)
                """),
                {
                    "id": str(uuid.uuid4()),
                    "sid": seq_id,
                    "pid": profile_id,
                    "preview": msg.get("subject", "")[:100],
                    "prov": result.get("id"),
                },
            )
            await session.commit()
            return seq_id, None

        await session.execute(
            sql_text("UPDATE kairos_sequences SET status = 'failed' WHERE id = :sid"),
            {"sid": seq_id},
        )
        await session.commit()
        return None, f"email falhou para {profile_id}: {result.get('error')}"


async def node_validate_window(state: KairosState) -> KairosState:
    ok, reason = is_within_sending_window()
    if not ok:
        logger.warning("KAIROS abortado: %s", reason)
        return {**state, "errors": state["errors"] + [f"fora da janela: {reason}"]}
    return state


async def node_identify_targets(state: KairosState) -> KairosState:
    if state.get("errors"):
        return state

    existing: list[dict] = []
    cold: list[dict] = []
    max_each = state.get("max_per_segment", 25)
    segment = state.get("segment", "both")

    if segment in ("existing_customer", "both"):
        existing = await get_eligible_targets("existing_customer", max_each)
        logger.info("KAIROS: %s existing customers identificados", len(existing))

    if segment in ("cold_lead", "both"):
        cold = await get_eligible_targets("cold_lead", max_each)
        logger.info("KAIROS: %s cold leads identificados", len(cold))

    return {**state, "existing_targets": existing, "cold_targets": cold}


async def node_process_existing(state: KairosState) -> KairosState:
    if state.get("errors") and not state.get("existing_targets"):
        return state

    created = list(state.get("sequences_created", []))
    emails_sent = state.get("emails_sent", 0)
    errors = list(state.get("errors", []))
    skipped = state.get("skipped", 0)

    for profile in state.get("existing_targets", []):
        try:
            seq_id, err = await _create_and_send_email(profile, "existing_customer", state)
            if err == "skipped":
                skipped += 1
            elif err:
                errors.append(err)
            elif seq_id:
                created.append(seq_id)
                emails_sent += 1
        except Exception as exc:
            logger.error("Erro ao processar existing %s: %s", profile.get("profile_id"), exc)
            errors.append(str(exc))
        await asyncio.sleep(0.5)

    return {
        **state,
        "sequences_created": created,
        "emails_sent": emails_sent,
        "errors": errors,
        "skipped": skipped,
    }


async def node_process_cold_leads(state: KairosState) -> KairosState:
    created = list(state.get("sequences_created", []))
    emails_sent = state.get("emails_sent", 0)
    errors = list(state.get("errors", []))
    skipped = state.get("skipped", 0)

    for profile in state.get("cold_targets", []):
        try:
            seq_id, err = await _create_and_send_email(profile, "cold_lead", state)
            if err == "skipped":
                skipped += 1
            elif err:
                errors.append(err)
            elif seq_id:
                created.append(seq_id)
                emails_sent += 1
        except Exception as exc:
            logger.error("Erro ao processar cold lead %s: %s", profile.get("profile_id"), exc)
            errors.append(str(exc))
        await asyncio.sleep(0.5)

    return {
        **state,
        "sequences_created": created,
        "emails_sent": emails_sent,
        "errors": errors,
        "skipped": skipped,
    }


async def node_log_run(state: KairosState) -> KairosState:
    logger.info(
        "KAIROS run %s concluído: emails=%s wa=%s skipped=%s errors=%s",
        state["run_id"],
        state.get("emails_sent", 0),
        state.get("wa_sent", 0),
        state.get("skipped", 0),
        len(state.get("errors", [])),
    )
    return state


def build_kairos_graph():
    graph = StateGraph(KairosState)
    graph.add_node("validate_window", node_validate_window)
    graph.add_node("identify_targets", node_identify_targets)
    graph.add_node("process_existing", node_process_existing)
    graph.add_node("process_cold_leads", node_process_cold_leads)
    graph.add_node("log_run", node_log_run)

    graph.set_entry_point("validate_window")
    graph.add_edge("validate_window", "identify_targets")
    graph.add_edge("identify_targets", "process_existing")
    graph.add_edge("process_existing", "process_cold_leads")
    graph.add_edge("process_cold_leads", "log_run")
    graph.add_edge("log_run", END)
    return graph.compile()


kairos_agent = build_kairos_graph()


async def run_kairos(
    trigger_type: str = "scheduled",
    segment: str = "both",
    max_per_segment: int = 25,
    brand_context: str = "VERTEX by Veltrus",
) -> dict:
    """Entry point principal do KAIROS."""
    run_id = str(uuid.uuid4())[:8]
    initial_state: KairosState = {
        "run_id": run_id,
        "trigger_type": trigger_type,
        "segment": segment,
        "max_per_segment": max_per_segment,
        "brand_context": brand_context,
        "existing_targets": [],
        "cold_targets": [],
        "sequences_created": [],
        "emails_sent": 0,
        "wa_sent": 0,
        "errors": [],
        "skipped": 0,
    }
    final_state = await kairos_agent.ainvoke(initial_state)
    return {
        "run_id": run_id,
        "trigger_type": trigger_type,
        "sequences_created": len(final_state.get("sequences_created", [])),
        "emails_sent": final_state.get("emails_sent", 0),
        "wa_sent": final_state.get("wa_sent", 0),
        "skipped": final_state.get("skipped", 0),
        "errors": final_state.get("errors", []),
    }
