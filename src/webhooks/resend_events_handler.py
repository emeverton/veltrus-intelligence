"""
Recebe eventos de email do Resend (open, click, bounce, unsubscribe).
Atualiza status das sequências KAIROS.
"""
from __future__ import annotations

import logging
import os
import uuid as uuid_lib

from sqlalchemy import text as sql_text
from svix.webhooks import Webhook, WebhookVerificationError

from src.database import AsyncSessionFactory

logger = logging.getLogger(__name__)

RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET", "")


def verify_resend_signature(raw_body: bytes, headers: dict) -> bool:
    if not RESEND_WEBHOOK_SECRET:
        return True  # dev mode
    try:
        wh = Webhook(RESEND_WEBHOOK_SECRET)
        wh.verify(raw_body, headers)
        return True
    except WebhookVerificationError:
        return False


async def handle_resend_event(event: dict) -> None:
    event_type = event.get("type", "")
    data = event.get("data", {})
    message_id = data.get("email_id") or data.get("message_id", "")

    if not message_id:
        return

    async with AsyncSessionFactory() as session:
        if event_type == "email.opened":
            await session.execute(
                sql_text("""
                    UPDATE kairos_sequences
                    SET status = 'email_opened', email_opened_at = NOW()
                    WHERE email_message_id = :mid
                      AND status = 'email_sent'
                """),
                {"mid": message_id},
            )
            logger.info("KAIROS: email aberto — message_id=%s", message_id)

        elif event_type in ("email.bounced", "email.complained"):
            await session.execute(
                sql_text("""
                    UPDATE kairos_sequences
                    SET status = 'failed', completed_at = NOW(), outcome = :outcome
                    WHERE email_message_id = :mid
                """),
                {"mid": message_id, "outcome": event_type},
            )
            logger.warning("KAIROS: %s — message_id=%s", event_type, message_id)

        elif event_type == "email.unsubscribed":
            seq = await session.execute(
                sql_text("""
                    SELECT profile_id FROM kairos_sequences
                    WHERE email_message_id = :mid LIMIT 1
                """),
                {"mid": message_id},
            )
            row = seq.fetchone()
            if row:
                await session.execute(
                    sql_text("""
                        INSERT INTO kairos_opt_outs (id, profile_id)
                        VALUES (:id, :pid)
                        ON CONFLICT (profile_id) DO NOTHING
                    """),
                    {"id": str(uuid_lib.uuid4()), "pid": str(row.profile_id)},
                )
                await session.execute(
                    sql_text("""
                        UPDATE kairos_sequences
                        SET status = 'opted_out', completed_at = NOW()
                        WHERE profile_id = :pid
                          AND status NOT IN ('completed', 'failed', 'opted_out')
                    """),
                    {"pid": str(row.profile_id)},
                )
                logger.info("KAIROS: unsubscribe processado para profile %s", row.profile_id)

        await session.commit()
