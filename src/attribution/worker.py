import asyncio
import json
import logging
from uuid import UUID

from src.attribution import repository as repo
from src.attribution.models_math import Touchpoint, shapley
from src.database import AsyncSessionFactory
from src.nats_client import ensure_attribution_stream, get_nats

logger = logging.getLogger(__name__)
SUBJECT = "attribution.shapley.compute"


async def handle_shapley_job(msg) -> None:
    try:
        payload = json.loads(msg.data.decode())
        conversion_id = UUID(payload["conversion_id"])
        profile_id = UUID(payload["profile_id"])
        revenue = float(payload["revenue"])

        async with AsyncSessionFactory() as session:
            touchpoints = await repo.get_touchpoints_for_profile(session, profile_id)
            if not touchpoints:
                logger.warning("No touchpoints for profile %s", profile_id)
                await msg.ack()
                return

            tp_list = [
                Touchpoint(
                    channel=t.channel,
                    campaign_id=t.campaign_id,
                    occurred_at=t.occurred_at,
                )
                for t in touchpoints
            ]

            credits = shapley(tp_list)
            await repo.save_results(session, conversion_id, profile_id, "shapley", credits, revenue)
            await session.commit()

        logger.info("Shapley computed for conversion %s: %s", conversion_id, credits)
        await msg.ack()
    except Exception as e:
        logger.error("Shapley job failed: %s", e)
        await msg.nak()


async def run_worker() -> None:
    await ensure_attribution_stream()
    nc = await get_nats()
    js = nc.jetstream()

    await js.subscribe(SUBJECT, cb=handle_shapley_job, durable="shapley-worker")
    logger.info("Attribution worker listening on %s", SUBJECT)

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
