"""The process that serves the AI queue (compose service `ai-worker`):
`python -m app.applaut.ai.worker`. One lane per model host (APPLAUT_MODEL_HOSTS),
each sending its host one item at a time, in queue order. Kept out of the API
workers so a minutes-long model call never holds up a request.

A lane uses its host only while the host serves the models models.lock pins.
When the host stops answering, the lane puts its item back where it was (the
try not counted) and waits 30 s, 1, 2, then 5 min between checks; the other
lanes carry on with the queue.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass

from app.applaut.ai import queue
from app.applaut.ai.handlers import HANDLERS, PermanentError, mark_failed
from app.applaut.ai.hosts import ModelHost, host_addresses
from app.applaut.ai.provider import AnswerCutOff, HostUnreachable, ModelError, Provider
from app.applaut.models.ai_queue import AIQueueItem
from app.db.session import AsyncSessionLocal

logger = logging.getLogger("applaut.ai.worker")
IDLE_SLEEP_SECONDS = 15
CHECK_EVERY_SECONDS = 600
BACKOFF_SECONDS = (30, 60, 120, 300)
STALE_CHECK_SECONDS = 300


@dataclass
class Served:
    item_id: int
    kind: str
    user_id: uuid.UUID
    outcome: str  # done | retry | failed | released


async def run_once(provider: Provider | None = None, *, host: ModelHost | None = None,
                   prefer_user: uuid.UUID | None = None) -> Served | None:
    """Serve the next item, if any, on `host` (or with `provider`, in tests)."""
    async with AsyncSessionLocal() as db:
        claimed = await queue.claim_next(db, host.address if host else None, prefer_user)
    if claimed is None:
        return None
    async with AsyncSessionLocal() as db:
        item = await db.get(AIQueueItem, claimed.id)
        item_id, kind, user_id = item.id, item.kind, item.user_id  # the rollback below expires `item`
        handler = HANDLERS[kind]
        error, retry, answer = None, True, None
        try:
            usage = await handler(db, item, provider or host.provider(kind))
        except HostUnreachable as exc:
            await db.rollback()
            await queue.release(db, item_id, str(exc))
            logger.warning("AI queue item %s (%s) put back: %s", item_id, kind, exc)
            return Served(item_id, kind, user_id, "released")
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
            return Served(item_id, kind, user_id, "done")
        await db.rollback()
        final = await queue.fail(db, item_id, error, retry)
        if final:
            await mark_failed(db, await db.get(AIQueueItem, item_id), error, answer)
        logger.warning("AI queue item %s (%s) failed: %s", item_id, kind, error)
        return Served(item_id, kind, user_id, "failed" if final else "retry")


def _next_backoff(current: int) -> int:
    later = [s for s in BACKOFF_SECONDS if s > current]
    return later[0] if later else BACKOFF_SECONDS[-1]


async def lane(host: ModelHost) -> None:
    log = logging.getLogger(f"applaut.ai.lane.{host.address}")
    last_user, backoff, checked_at = None, 0, float("-inf")
    while True:
        if backoff or time.monotonic() - checked_at > CHECK_EVERY_SECONDS:
            problem = await host.check()
            checked_at = time.monotonic()
            if problem:
                backoff = _next_backoff(backoff)
                log.warning("Host not usable, next check in %ss: %s", backoff, problem)
                await asyncio.sleep(backoff)
                continue
            if backoff:
                log.info("Host usable again")
            backoff = 0
        served = await run_once(host=host, prefer_user=last_user)
        if served is None:
            await asyncio.sleep(IDLE_SLEEP_SECONDS)
        elif served.outcome == "released":
            backoff = _next_backoff(backoff)
            await asyncio.sleep(backoff)
        else:
            last_user = served.user_id


async def _recover_stale_forever() -> None:
    while True:
        async with AsyncSessionLocal() as db:
            if n := await queue.recover_stale(db):
                logger.info("Put back %d item(s) left running by a stopped worker", n)
        await asyncio.sleep(STALE_CHECK_SECONDS)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    hosts = [ModelHost(a) for a in host_addresses()]
    if not hosts:
        logger.warning("APPLAUT_MODEL_HOSTS is empty; nothing is served. Set it and restart ai-worker.")
        while True:
            await asyncio.sleep(3600)
    logger.info("Serving the AI queue on %d model host(s): %s", len(hosts), ", ".join(h.address for h in hosts))
    await asyncio.gather(_recover_stale_forever(), *(lane(h) for h in hosts))


if __name__ == "__main__":
    asyncio.run(main())
