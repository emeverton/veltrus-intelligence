import asyncio
import json
import logging

from sqlalchemy import text as sql_text

from src.agents.graph import run_agent
from src.database import AsyncSessionFactory
from src.nats_client import ensure_agents_stream, get_nats

logger = logging.getLogger(__name__)
SUBJECT = "agents.jobs.run"


async def handle_agent_job(msg) -> None:
    payload = json.loads(msg.data.decode())
    job_id = payload.get("job_id")
    task = payload.get("task", "")
    context = payload.get("context", {})

    logger.info("Agent job received: %s — %s", job_id, task[:60])

    try:
        async with AsyncSessionFactory() as session:
            await session.execute(
                sql_text(
                    "UPDATE agent_jobs SET status='running', updated_at=NOW() WHERE id=:id"
                ),
                {"id": job_id},
            )
            await session.commit()

        result = await run_agent(task, context)

        async with AsyncSessionFactory() as session:
            await session.execute(
                sql_text(
                    "UPDATE agent_jobs SET status='done', result=CAST(:result AS jsonb), "
                    "updated_at=NOW() WHERE id=:id"
                ),
                {"id": job_id, "result": json.dumps({"answer": result})},
            )
            await session.commit()

        logger.info("Agent job done: %s", job_id)
        await msg.ack()
    except Exception as e:
        logger.error("Agent job failed: %s — %s", job_id, e)
        async with AsyncSessionFactory() as session:
            await session.execute(
                sql_text(
                    "UPDATE agent_jobs SET status='failed', error=:error, updated_at=NOW() "
                    "WHERE id=:id"
                ),
                {"id": job_id, "error": str(e)},
            )
            await session.commit()
        await msg.nak()


async def run_agent_worker() -> None:
    await ensure_agents_stream()
    nc = await get_nats()
    js = nc.jetstream()

    await js.subscribe(SUBJECT, cb=handle_agent_job, durable="agent-worker")
    logger.info("Agent worker listening on %s", SUBJECT)

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_agent_worker())
