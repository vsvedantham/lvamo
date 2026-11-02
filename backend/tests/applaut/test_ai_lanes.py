"""Several model hosts on one queue (APPLAUT_AI_V2_PLAN.md §2): FIFO across
lanes, a host going down loses nothing, a lane keeps to its last user, and a
host is used only while it serves the pinned models."""
import httpx
import openai
import pytest
from sqlalchemy import select

from app.applaut.ai import hosts, queue, worker
from app.applaut.ai.hosts import ModelHost, pinned_models
from app.applaut.ai.provider import HostUnreachable, LlamaServerProvider, ModelError
from app.applaut.models.ai_queue import AIQueueItem
from app.db.session import AsyncSessionLocal
from tests.applaut.test_ai_engine import (  # noqa: F401  (fixtures)
    GOOD_FACTS, FakeModel, _enqueue, _isolated_queue, _job, _raw, ai_user,
)

LOW = {**GOOD_FACTS, "role_fit": "different", "must_have": []}  # < 80: no documents queued


class FakeHost:
    """A model host whose models are a FakeModel."""

    def __init__(self, address, model=None):
        self.address, self.model = address, model or FakeModel(facts=LOW)

    def provider(self, kind):
        return self.model


async def _items(*assessments):
    async with AsyncSessionLocal() as db:
        rows = await db.scalars(select(AIQueueItem).where(
            AIQueueItem.assessment_id.in_([a.id for a in assessments])).order_by(AIQueueItem.seq))
        return {i.assessment_id: i for i in rows}


async def _queued(ai_user, make_opportunity, n, user=None):
    u, p = user or await ai_user()
    out = []
    for _ in range(n):
        a = await _raw(u, p, await _job(make_opportunity))
        await _enqueue("score_job", a)
        out.append(a)
    return (u, p), out


async def test_two_hosts_take_the_queue_in_order(ai_user, make_opportunity):
    _, jobs = await _queued(ai_user, make_opportunity, 4)
    a, b = FakeHost("10.8.0.2"), FakeHost("10.8.0.3")
    served = []
    for host in (a, b, a, b):
        served.append(await worker.run_once(host=host))
    items = await _items(*jobs)
    assert [s.item_id for s in served] == [items[j.id].id for j in jobs]  # oldest first, whichever lane asks
    assert [items[j.id].host for j in jobs] == ["10.8.0.2", "10.8.0.3", "10.8.0.2", "10.8.0.3"]
    assert all(i.status == "done" for i in items.values())


async def test_unreachable_host_puts_the_item_back_unchanged(ai_user, make_opportunity):
    _, (job,) = await _queued(ai_user, make_opportunity, 1)
    before = (await _items(job))[job.id]
    down = FakeHost("10.8.0.2", FakeModel(script=[HostUnreachable("host unreachable: APIConnectionError")]))
    served = await worker.run_once(host=down)
    assert served.outcome == "released"
    after = (await _items(job))[job.id]
    assert (after.status, after.attempts, after.seq, after.host) == ("pending", 0, before.seq, None)
    assert "APIConnectionError" in after.last_error

    served = await worker.run_once(host=FakeHost("10.8.0.3"))  # another lane takes it, first try
    after = (await _items(job))[job.id]
    assert served.outcome == "done" and (after.status, after.attempts, after.host) == ("done", 1, "10.8.0.3")


async def test_lane_keeps_to_its_user_within_the_window(ai_user, make_opportunity, monkeypatch):
    alice = await ai_user()
    bob = await ai_user()
    _, (a1,) = await _queued(ai_user, make_opportunity, 1, alice)
    _, (b1,) = await _queued(ai_user, make_opportunity, 1, bob)
    _, (a2,) = await _queued(ai_user, make_opportunity, 1, alice)
    host = FakeHost("10.8.0.2")
    first = await worker.run_once(host=host)
    second = await worker.run_once(host=host, prefer_user=first.user_id)
    items = await _items(a1, b1, a2)
    assert (first.item_id, second.item_id) == (items[a1.id].id, items[a2.id].id)  # Alice's prompt stays cached

    _, (b2,) = await _queued(ai_user, make_opportunity, 1, bob)
    _, (a3,) = await _queued(ai_user, make_opportunity, 1, alice)
    monkeypatch.setattr(queue, "PREFER_WINDOW", 1)  # Alice's next one is beyond the window: FIFO wins
    third = await worker.run_once(host=host, prefer_user=alice[0].id)
    assert third.item_id == (await _items(b1))[b1.id].id


async def test_lane_waits_while_its_host_is_not_usable(ai_user, make_opportunity, monkeypatch):
    _, (job,) = await _queued(ai_user, make_opportunity, 1)
    waits = []

    class Stop(Exception):
        pass

    async def fake_sleep(seconds):
        waits.append(seconds)
        if len(waits) == 3:
            raise Stop

    class Broken(ModelHost):
        async def check(self):
            return "scorer at http://10.8.0.2:8080/v1: ConnectError"

    monkeypatch.setattr(worker.asyncio, "sleep", fake_sleep)
    with pytest.raises(Stop):
        await worker.lane(Broken("10.8.0.2"))
    assert waits == [30, 60, 120]
    assert (await _items(job))[job.id].status == "pending"  # nothing claimed meanwhile
    assert [worker._next_backoff(s) for s in (120, 300)] == [300, 300]


def _models_transport(ids_by_port):
    def handle(request):
        ids = ids_by_port.get(request.url.port)
        if ids is None:
            raise httpx.ConnectError("connection refused", request=request)
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={"data": [{"id": i} for i in ids]})
    return httpx.MockTransport(handle)


async def test_host_is_usable_only_with_the_pinned_models(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "applaut_llm_api_key", "test-key")
    pins = pinned_models()
    real_client = httpx.AsyncClient

    def use(ids_by_port):
        monkeypatch.setattr(hosts.httpx, "AsyncClient",
                            lambda **kw: real_client(transport=_models_transport(ids_by_port), **kw))

    use({8080: [pins["scorer"].served_id], 8081: [pins["writer"].served_id]})
    assert await ModelHost("10.8.0.2").check() is None
    use({8080: [pins["scorer"].served_id], 8081: ["writer:some-other-model@00000000"]})
    assert "models.lock pins" in await ModelHost("10.8.0.2").check()
    use({8080: [pins["scorer"].served_id]})  # the writer isn't running
    assert "ConnectError" in await ModelHost("10.8.0.2").check()


def test_models_lock_pins_both_roles():
    pins = pinned_models()
    assert set(pins) == {"scorer", "writer"}
    for role, m in pins.items():
        assert m.served_id.startswith(f"{role}:") and len(m.sha256) == 64 and m.file.endswith(".gguf")
    host = ModelHost("10.8.0.2")
    assert host.url("scorer") == "http://10.8.0.2:8080/v1" and host.url("writer") == "http://10.8.0.2:8081/v1"
    assert host.provider("write_docs").name == pins["writer"].served_id


@pytest.mark.parametrize("error, unreachable", [
    (lambda r: openai.APIConnectionError(request=r), True),
    (lambda r: openai.InternalServerError("loading", response=httpx.Response(503, request=r), body=None), True),
    (lambda r: openai.AuthenticationError("bad key", response=httpx.Response(401, request=r), body=None), True),
    (lambda r: openai.APITimeoutError(request=r), False),  # this request was too slow: counts as a try
    (lambda r: openai.BadRequestError("too long", response=httpx.Response(400, request=r), body=None), False),
])
async def test_which_errors_mean_the_host_is_down(error, unreachable, monkeypatch):
    p = LlamaServerProvider("http://10.8.0.2:8080/v1", "k", "scorer:x@1")
    request = httpx.Request("POST", "http://10.8.0.2:8080/v1/chat/completions")

    async def fail(**kw):
        raise error(request)
    monkeypatch.setattr(p._client.chat.completions, "create", fail)
    with pytest.raises(ModelError) as exc:
        await p.complete_json("s", "u", {"type": "object"}, 10)
    assert isinstance(exc.value, HostUnreachable) is unreachable
