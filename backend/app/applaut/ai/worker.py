"""The single process that serves the AI queue (compose service `ai-worker`):
`python -m app.applaut.ai.worker`. One item at a time, in queue order; kept out
of the API workers so a minutes-long model call never holds up a request."""
from __future__ import annotations

import asyncio
import logging

from app.applaut.ai import queue
from app.applaut.ai.handlers import HANDLERS, PermanentError, mark_failed
from app.applaut.ai.provider import AnswerCutOff, ModelError, Provider, get_provider
from app.applaut.models.ai_queue import AIQueueItem
from app.config import settings
from app.db.session import AsyncSessionLocal

logger = logging.getLogger("applaut.ai.worker")
IDLE_SLEEP_SECONDS = 15


async def run_once(provider: Provider | None = None) -> bool:
    """Serve the next item, if any. Returns whether one was served."""
    async with AsyncSessionLocal() as db:
        claimed = await queue.claim_next(db)
    if claimed is None:
        return False
    async with AsyncSessionLocal() as db:
        item = await db.get(AIQueueItem, claimed.id)
        item_id, kind = item.id, item.kind  # the rollback below expires `item`
        handler = HANDLERS[kind]
        error, retry, answer = None, True, None
        try:
            usage = await handler(db, item, provider or get_provider())
        except (PermanentError, AnswerCutOff) as exc:
            error, retry, answer = str(exc), False, getattr(exc, "answer", None)
        except ModelError as exc:
            error = str(exc)
        except Exception as exc:  # noqa: BLE001  (one bad item must not stop the queue)
            logger.exception("AI queue item %s (%s) failed", item_id, kind)
            error = f"{type(exc).__name__}: {exc}"
        if error is None:
            await queue.finish(db, item_id, model=usage.model, prompt_tokens=usage.prompt_tokens,
                               output_tokens=usage.output_tokens, duration_ms=usage.duration_ms)
            logger.info("AI queue item %s (%s) done in %.0fs", item_id, kind, usage.duration_ms / 1000)
        else:
            await db.rollback()
            if await queue.fail(db, item_id, error, retry):
                await mark_failed(db, await db.get(AIQueueItem, item_id), error, answer)
            logger.warning("AI queue item %s (%s) failed: %s", item_id, kind, error)
    return True


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if not settings.applaut_llm_base_url:
        logger.warning("APPLAUT_LLM_BASE_URL is not set; the AI queue will wait until it is")
    while True:
        async with AsyncSessionLocal() as db:
            if await queue.recover_stale(db):
                logger.info("Put back items left running by a stopped worker")
        if not settings.applaut_llm_base_url:
            await asyncio.sleep(300)
            continue
        while await run_once():
            pass
        await asyncio.sleep(IDLE_SLEEP_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
