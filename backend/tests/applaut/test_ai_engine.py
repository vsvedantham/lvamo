"""Applaut AI engine with a fake model: the FIFO queue, retries, scoring,
document writing, and the 22:00 nightly run."""
import copy
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import delete, func, select, update

from app.applaut.ai import handlers, nightly, queue, scoring, worker
from app.applaut.ai.provider import Completion, ModelError
from app.applaut.discovery.base import JobListing
from app.applaut.models.ai_queue import AIQueueItem, NightRun
from app.applaut.models.engine_task import EngineTask
from app.applaut.models.generated_document import GeneratedDocument
from app.applaut.models.job_assessment import JobAssessment
from app.applaut.models.master_profile import MasterProfile
from app.applaut.models.profile import Profile
from app.config import settings
from app.db.session import AsyncSessionLocal
from tests.applaut.conftest import TEST_SOURCE
from tests.applaut.test_documents import JOB, PROFILE, WRITTEN

GOOD_FACTS = {
    "role_fit": "same", "german_required": "none", "years_required": 3, "seniority": "senior",
    "contract": "permanent", "work_mode": "hybrid", "flags": ["on-call"],
    "must_have": [{"requirement": "Spark", "matched_by": "Apache PySpark"},
                  {"requirement": "Python", "matched_by": "Python"},
                  {"requirement": "SQL", "matched_by": "SQL"},
                  {"requirement": "Kafka", "matched_by": None}],
    "nice_to_have": [{"requirement": "Airflow", "matched_by": "Airflow"}],
}


class FakeModel:
    """Answers by schema: scoring facts or written text. `script` overrides answers in order."""
    name = "fake-model"

    def __init__(self, facts=None, written=None, script=None):
        self.facts, self.written, self.script, self.calls = facts or GOOD_FACTS, written or WRITTEN, list(script or []), []

    async def complete_json(self, system, user, schema, max_tokens):
        self.calls.append(user)
        if self.script:
            nxt = self.script.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return Completion(nxt, self.name, 100, 50, 10)
        data = self.written if "paragraphs" in schema["properties"] else self.facts
        return Completion(copy.deepcopy(data), self.name, 1000, 200, 1500)


@pytest.fixture(autouse=True)
async def _isolated_queue(monkeypatch):
    async with AsyncSessionLocal() as db:
        others = await db.scalar(select(func.count()).select_from(AIQueueItem).where(AIQueueItem.status == "pending"))
    if others:
        pytest.skip("the local AI queue has pending items from outside the tests")
    stored = {}

    async def fake_store(key, data, content_type):
        stored[key] = data
    monkeypatch.setattr(handlers, "store_file", fake_store)
    yield stored
    async with AsyncSessionLocal() as db:
        await db.execute(delete(NightRun).where(NightRun.run_date < date(2000, 1, 1)))
        await db.commit()


@pytest.fixture
def ai_user(make_user):
    async def _make(master=True, **profile_fields):
        user, profile, headers = await make_user(**profile_fields)
        async with AsyncSessionLocal() as db:
            await db.execute(update(Profile).where(Profile.id == profile.id).values(
                job_engine="applaut_ai", job_engine_changed_at=datetime.now(timezone.utc)))
            if master:
                db.add(MasterProfile(user_id=user.id, data=copy.deepcopy(PROFILE)))
            await db.commit()
        return user, profile
    return _make


async def _raw(user, profile, opp):
    async with AsyncSessionLocal() as db:
        a = JobAssessment(user_id=user.id, profile_id=profile.id, opportunity_id=opp.id, engine="applaut_ai",
                          status="raw", docs_status="not_needed", matched_skills=[], missing_skills=[], flags=[], raw={})
        db.add(a)
        await db.commit()
        await db.refresh(a)
        return a


async def _enqueue(kind, a):
    async with AsyncSessionLocal() as db:
        assert await queue.enqueue(db, kind, a)
        await db.commit()


async def _job(make_opportunity, **kw):
    return await make_opportunity(title=kw.pop("title", JOB.title), description=JOB.description,
                                  location_raw=JOB.location, **kw)


async def _drain(model, limit=50):
    order = []
    for _ in range(limit):
        async with AsyncSessionLocal() as db:
            nxt = await db.scalar(select(AIQueueItem).where(AIQueueItem.status == "pending").order_by(AIQueueItem.seq).limit(1))
        if nxt is None:
            break
        order.append((nxt.kind, nxt.user_id))
        await worker.run_once(model)
    return order


async def _get(model, id_):
    async with AsyncSessionLocal() as db:
        return await db.get(model, id_)


# ---------------------------------------------------------------- scoring rules

def test_score_counts_combined_matches_and_ignores_languages():
    facts = copy.deepcopy(GOOD_FACTS)
    facts["must_have"][0]["matched_by"] = "Apache PySpark, Airflow"       # combined: still a match
    facts["must_have"].append({"requirement": "Fluent English", "matched_by": None})  # not a skill
    facts["must_have"].append({"requirement": "Go", "matched_by": "Golang"})  # not in the profile
    r = scoring.compute(facts, PROFILE, 5, "B2")
    assert r.parts["must_have"] == round(45 * 3 / 5)
    assert r.missing == ["Kafka", "Go"] and r.ignored_matches == 1
    assert r.parts["role_fit"] == 20 and r.parts["language"] == 15 and r.parts["seniority"] == 10


def test_german_above_the_users_level_caps_the_score():
    facts = {**GOOD_FACTS, "german_required": "C1"}
    r = scoring.compute(facts, PROFILE, 5, "B2")
    assert r.german_miss and r.score <= scoring.GERMAN_MISS_CAP
    assert "German C1 required" in scoring.flags_for(facts, r)


def test_years_and_lead_roles_lower_seniority():
    assert scoring.compute({**GOOD_FACTS, "years_required": 8}, PROFILE, 5, "B2").parts["seniority"] == 0
    assert scoring.compute({**GOOD_FACTS, "years_required": 7}, PROFILE, 5, "B2").parts["seniority"] == 5
    assert scoring.compute({**GOOD_FACTS, "seniority": "lead"}, PROFILE, 5, "B2").parts["seniority"] == 3


# ---------------------------------------------------------------- queue

async def test_fifo_across_users_and_stages(ai_user, make_opportunity):
    """All of A's and B's scoring runs before any documents (their write items are queued behind)."""
    a_user, a_prof = await ai_user()
    b_user, b_prof = await ai_user()
    for u, p in ((a_user, a_prof), (a_user, a_prof), (b_user, b_prof)):
        await _enqueue("score_job", await _raw(u, p, await _job(make_opportunity)))
    order = await _drain(FakeModel())
    assert order == [("score_job", a_user.id), ("score_job", a_user.id), ("score_job", b_user.id),
                     ("write_docs", a_user.id), ("write_docs", a_user.id), ("write_docs", b_user.id)]


async def test_job_is_never_queued_twice(ai_user, make_opportunity):
    u, p = await ai_user()
    a = await _raw(u, p, await _job(make_opportunity))
    await _enqueue("score_job", a)
    async with AsyncSessionLocal() as db:
        assert not await queue.enqueue(db, "score_job", a)


async def test_model_failure_retries_at_the_back_then_fails(ai_user, make_opportunity):
    u, p = await ai_user()
    first = await _raw(u, p, await _job(make_opportunity))
    second = await _raw(u, p, await _job(make_opportunity))
    await _enqueue("score_job", first)
    await _enqueue("score_job", second)
    model = FakeModel(facts={**GOOD_FACTS, "role_fit": "different", "must_have": []})  # < 80: no documents
    model.script = [ModelError("server down")]
    await worker.run_once(model)                       # first fails once and goes behind second
    async with AsyncSessionLocal() as db:
        seqs = dict((await db.execute(select(AIQueueItem.assessment_id, AIQueueItem.seq).where(
            AIQueueItem.assessment_id.in_((first.id, second.id))))).all())
    assert seqs[first.id] > seqs[second.id]
    assert len(await _drain(model)) == 2
    assert (await _get(JobAssessment, first.id)).status == "scored"

    third = await _raw(u, p, await _job(make_opportunity))
    await _enqueue("score_job", third)
    model.script = [ModelError("down")] * 3
    await _drain(model)
    async with AsyncSessionLocal() as db:
        item = await db.scalar(select(AIQueueItem).where(AIQueueItem.assessment_id == third.id))
    assert item.status == "failed" and item.attempts == queue.MAX_ATTEMPTS
    assert (await _get(JobAssessment, third.id)).status == "failed"


async def test_no_master_profile_fails_without_retrying(ai_user, make_opportunity):
    u, p = await ai_user(master=False)
    a = await _raw(u, p, await _job(make_opportunity))
    await _enqueue("score_job", a)
    await worker.run_once(FakeModel())
    async with AsyncSessionLocal() as db:
        item = await db.scalar(select(AIQueueItem).where(AIQueueItem.assessment_id == a.id))
    assert item.status == "failed" and item.attempts == 1 and "master profile" in item.last_error


async def test_stale_running_item_is_put_back(ai_user, make_opportunity):
    u, p = await ai_user()
    a = await _raw(u, p, await _job(make_opportunity))
    await _enqueue("score_job", a)
    async with AsyncSessionLocal() as db:
        await db.execute(update(AIQueueItem).where(AIQueueItem.assessment_id == a.id).values(
            status="running", started_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        await db.commit()
        assert await queue.recover_stale(db) == 1


# ---------------------------------------------------------------- handlers

async def test_scoring_writes_the_assessment(ai_user, make_opportunity):
    u, p = await ai_user()
    a = await _raw(u, p, await _job(make_opportunity))
    await _enqueue("score_job", a)
    await worker.run_once(FakeModel())
    a = await _get(JobAssessment, a.id)
    assert a.status == "scored" and a.match_score >= settings.applaut_ai_doc_threshold
    assert a.matched_skills == ["Spark", "Python", "SQL"] and a.missing_skills == ["Kafka"]
    assert a.docs_status == "pending" and "CHECK: on-call" in a.flags
    assert a.raw["parts"]["must_have"] == round(45 * 3 / 4) and a.model == "fake-model"
    async with AsyncSessionLocal() as db:
        kinds = list(await db.scalars(select(AIQueueItem.kind).where(AIQueueItem.assessment_id == a.id)))
    assert sorted(kinds) == ["score_job", "write_docs"]


async def test_low_score_writes_no_documents(ai_user, make_opportunity):
    u, p = await ai_user()
    a = await _raw(u, p, await _job(make_opportunity))
    await _enqueue("score_job", a)
    await worker.run_once(FakeModel(facts={**GOOD_FACTS, "role_fit": "different", "german_required": "C2"}))
    a = await _get(JobAssessment, a.id)
    assert a.match_score <= 60 and a.docs_status == "not_needed"


async def test_write_docs_stores_pdfs(ai_user, make_opportunity, _isolated_queue):
    u, p = await ai_user()
    opp = await _job(make_opportunity)
    a = await _raw(u, p, opp)
    await _enqueue("write_docs", a)
    await worker.run_once(FakeModel())
    assert (await _get(JobAssessment, a.id)).docs_status == "done"
    async with AsyncSessionLocal() as db:
        docs = list(await db.scalars(select(GeneratedDocument).where(GeneratedDocument.opportunity_id == opp.id)))
    assert {d.document_type for d in docs} == {"tailored_resume", "cover_letter"}
    for d in docs:
        assert d.engine == "applaut_ai" and d.content_type == "application/pdf" and d.is_current
        assert d.r2_key.startswith(f"applaut/documents/{u.id}/{opp.id}/")
        assert _isolated_queue[d.r2_key].startswith(b"%PDF")
    assert {d.file_name for d in docs} == {"Alex_Example_CV.pdf", "Alex_Example_CoverLetter.pdf"}


async def test_write_docs_sends_fact_guard_errors_back_once(ai_user, make_opportunity):
    u, p = await ai_user()
    a = await _raw(u, p, await _job(make_opportunity))
    await _enqueue("write_docs", a)
    bad = copy.deepcopy(WRITTEN)
    bad["paragraphs"][1] = bad["paragraphs"][1].replace("40 minutes", "15 minutes")
    model = FakeModel(script=[bad, copy.deepcopy(WRITTEN)])
    await worker.run_once(model)
    assert "number '15'" in model.calls[1] and "broke these rules" in model.calls[1]
    assert (await _get(JobAssessment, a.id)).docs_status == "done"


async def test_write_docs_gives_up_after_two_bad_answers(ai_user, make_opportunity):
    u, p = await ai_user()
    a = await _raw(u, p, await _job(make_opportunity))
    await _enqueue("write_docs", a)
    bad = copy.deepcopy(WRITTEN)
    bad["headline"] = "Data Engineer with 99 skills"
    await worker.run_once(FakeModel(script=[bad, bad]))
    a = await _get(JobAssessment, a.id)
    assert a.docs_status == "failed" and "broke the rules twice" in a.raw["write_docs_error"]


# ---------------------------------------------------------------- nightly

def test_next_run_is_22_berlin_across_dst():
    # 25 Oct 2026: clocks go back. 21:30 UTC on the 24th = 23:30 CEST, past 22:00.
    assert nightly.next_run_at(datetime(2026, 10, 24, 21, 30, tzinfo=timezone.utc)) == \
        datetime(2026, 10, 25, 21, 0, tzinfo=timezone.utc)   # 22:00 CET
    assert nightly.next_run_at(datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)) == \
        datetime(2026, 7, 1, 20, 0, tzinfo=timezone.utc)     # 22:00 CEST


async def test_ensure_nightly_task_is_idempotent():
    async with AsyncSessionLocal() as db:
        await nightly.ensure_nightly_task(db)
        await nightly.ensure_nightly_task(db)
        n = await db.scalar(select(func.count()).select_from(EngineTask).where(
            EngineTask.kind == nightly.KIND_NIGHTLY, EngineTask.status.in_(("pending", "running"))))
    assert n == 1


async def test_nightly_creates_raw_jobs_and_queues_in_opt_in_order(ai_user, make_user, monkeypatch):
    first, first_p = await ai_user()
    second, second_p = await ai_user()
    await make_user()  # a Basic user: no AI work
    listings = [JobListing(source=TEST_SOURCE, external_id=f"n{i}", title=t, company_name="Night GmbH",
                           application_url=f"https://example.invalid/{i}", location_raw="Berlin, Germany",
                           country_code="DE", description=d)
                for i, (t, d) in enumerate([
                    ("Data Engineer", JOB.description), ("Data Engineer (Spark)", JOB.description + " Spark Python SQL"),
                    ("Senior Data Engineer", "Kotlin only."), ("Pastry Chef", "Cakes.")])]

    async def fake_fetch(countries, roles):
        assert countries == ["DE"] and roles == ["Data Engineer"]
        return listings
    monkeypatch.setattr(nightly, "fetch_listings", fake_fetch)
    monkeypatch.setattr(settings, "applaut_ai_score_cap", 2)

    night = await nightly.run_nightly(today=date(1999, 1, 1))
    assert night.users >= 2 and night.jobs_found == 4
    s = night.stats[str(first.id)]
    assert s == {"matched": 3, "new": 3, "queued": 2, "waiting": 1}
    async with AsyncSessionLocal() as db:
        items = list(await db.scalars(select(AIQueueItem).where(AIQueueItem.night_run_id == night.id).order_by(AIQueueItem.seq)))
    owners = [i.user_id for i in items]
    assert owners == [first.id, first.id, second.id, second.id]
    async with AsyncSessionLocal() as db:
        raw = await db.scalar(select(func.count()).select_from(JobAssessment).where(
            JobAssessment.profile_id == first_p.id, JobAssessment.status == "raw"))
    assert raw == 3  # queued ones stay raw until scored; the third waits for tomorrow

    again = await nightly.run_nightly(today=date(1999, 1, 1))  # same postings: nothing new, nothing queued twice
    assert again.stats[str(first.id)]["new"] == 0 and again.jobs_queued == 0
