"""
Worker de escalação WhatsApp.
Busca sequências com email_sent há > 48h e email não aberto.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text as sql_text

from src.agents.kairos.channels import send_whatsapp
from src.agents.kairos.message_gen import generate_message
from src.database import AsyncSessionFactory

logger = logging.getLogger(__name__)


async def process_wa_escalations() -> dict:
    """Envia WhatsApp para sequências sem abertura de email após 48h."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    sent = 0
    errors: list[str] = []

    async with AsyncSessionFactory() as session:
        pending = await session.execute(
            sql_text("""
                SELECT id, profile_id, email, phone, segment, run_id
                FROM kairos_sequences
                WHERE status = 'email_sent'
                  AND email_sent_at <= :cutoff
                  AND email_opened_at IS NULL
                  AND phone IS NOT NULL
                LIMIT 50
            """),
            {"cutoff": cutoff},
        )
        rows = pending.fetchall()

    for row in rows:
        seq_id = str(row.id)
        profile_id = str(row.profile_id)
        phone = row.phone

        try:
            profile_mock = {
                "profile_id": profile_id,
                "email": row.email,
                "phone": phone,
            }
            msg = await generate_message(profile_mock, row.segment, "whatsapp")
            result = await send_whatsapp(phone, msg.get("text", ""))

            async with AsyncSessionFactory() as session:
                if result["success"]:
                    await session.execute(
                        sql_text("""
                            UPDATE kairos_sequences
                            SET status = 'wa_sent', wa_sent_at = NOW(), wa_text = :text
                            WHERE id = :sid
                        """),
                        {"text": msg.get("text", "")[:500], "sid": seq_id},
                    )
                    await session.execute(
                        sql_text("""
                            INSERT INTO kairos_outreach_log
                                (id, sequence_id, profile_id, channel, action,
                                 message_preview, provider_id)
                            VALUES (:id, :sid, :pid, 'whatsapp', 'sent', :preview, :prov)
                        """),
                        {
                            "id": str(uuid.uuid4()),
                            "sid": seq_id,
                            "pid": profile_id,
                            "preview": msg.get("text", "")[:100],
                            "prov": result.get("id"),
                        },
                    )
                    await session.commit()
                    sent += 1
                else:
                    await session.execute(
                        sql_text(
                            "UPDATE kairos_sequences SET status = 'failed' WHERE id = :sid"
                        ),
                        {"sid": seq_id},
                    )
                    await session.commit()
                    errors.append(seq_id)
        except Exception as exc:
            logger.error("WA escalation falhou para sequência %s: %s", seq_id, exc)
            errors.append(str(exc))

        await asyncio.sleep(1)

    return {"wa_sent": sent, "errors": errors}
