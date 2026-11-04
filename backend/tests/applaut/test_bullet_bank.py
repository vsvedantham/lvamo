"""Bullet bank builder (APPLAUT_AI_V2_PLAN.md §4): the writer drafts CV bullets
for one role from the user's notes; code checks them; nothing reaches the
master profile until the user keeps it."""
import copy
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update

from app.applaut.ai import worker
from app.applaut.ai.provider import ModelError
from app.applaut.documents.fact_guard import check_drafts
from app.applaut.models.ai_queue import AIQueueItem
from app.applaut.models.audit_log import AuditLog
from app.applaut.models.bullet_draft import BulletDraft
from app.applaut.models.master_profile import MasterProfile
from app.applaut.models.profile import Profile
from app.config import settings
from app.db.session import AsyncSessionLocal
from tests.applaut.test_ai_engine import FakeModel, _isolated_queue  # noqa: F401  (fixture)
from tests.applaut.test_documents import PROFILE, profile

API = "/api/v1/applaut/master-profile"
ACME = PROFILE["experience"][0]
NOTES = ("At Acme I set up Great Expectations checks on the 12 Airflow pipelines and paged the on-call engineer "
         "when a check failed. Cut failed loads from about 10 a week to 2. Also wrote the runbook for the team.")


@pytest.fixture
def drafter(make_user, monkeypatch):
    """async drafter(engine="applaut_ai") -> auth headers of a user with a master profile
    (its user id as `drafter.user_id`)."""
    monkeypatch.setattr(settings, "applaut_model_hosts", "10.8.0.2")

    async def _make(engine="applaut_ai"):
        user, prof, headers = await make_user()
        async with AsyncSessionLocal() as db:
            await db.execute(update(Profile).where(Profile.id == prof.id).values(
                job_engine=engine, job_engine_changed_at=datetime.now(timezone.utc)))
            db.add(MasterProfile(user_id=user.id, data=copy.deepcopy(PROFILE)))
            await db.commit()
        _make.user_id = user.id
        return headers
    return _make


# ---------------------------------------------------------------- checks

def _check(texts, notes=NOTES):
    return check_drafts(profile(), profile()["experience"][0], notes, texts)


def test_drafts_keep_what_the_notes_say_and_flag_new_numbers():
    kept, left_out = _check([
        "Added Great Expectations checks to 12 Airflow pipelines, cutting failed loads from about 10 a week to 2.",
        "Wrote the on-call runbook for the data team, so failed checks paged the right engineer within 15 minutes.",
    ])
    assert left_out == []
    assert kept[0]["confirm"] == [] and kept[1]["confirm"] == ["15"]  # 15 isn't in the notes: the user checks it


def test_drafts_that_name_something_new_or_repeat_are_left_out():
    kept, left_out = _check([
        "Added Great Expectations checks to 12 Airflow pipelines and streamed the alerts through Kafka to PagerDuty.",
        "Rewrote the Spark billing job, cutting its runtime from 6 hours to 40 minutes for finance.",  # existing fact
        "I added Great Expectations checks to the 12 Airflow pipelines that load sales data.",
        "Wrote a runbook.",
        "Added Great Expectations checks to 12 Airflow pipelines, cutting failed loads from about 10 a week to 2.",
        "Added Great Expectations checks to all 12 Airflow pipelines, cutting failed loads from 10 a week to 2.",
    ])
    reasons = [x["reason"] for x in left_out]
    assert "Kafka, PagerDuty" in reasons[0] and "isn't in your notes" in reasons[0]
    assert reasons[1:] == ["already one of this role's bullets", "written in the first person",
                           "3 words; a CV bullet needs 6-45", "repeats another draft"]
    assert len(kept) == 1


def test_names_are_matched_as_whole_words():
    notes = "Moved the reports to PostgreSQL and wrote the views."
    kept, left_out = check_drafts(profile(), profile()["experience"][0], notes,
                                  ["Moved the finance reports to PostgreSQL and wrote SQL views for the warehouse team.",
                                   "Moved the finance reports to PostgreSQL and wrote Looker views for the analysts."])
    assert [k["text"][:30] for k in kept] == ["Moved the finance reports to P"]  # SQL is a profile skill
    assert "Looker" in left_out[0]["reason"]


# ---------------------------------------------------------------- API + queue

async def test_draft_queue_keep_flow(client, drafter):
    headers = await drafter()
    r = await client.post(f"{API}/entries/acme/draft-bullets", json={"notes": NOTES}, headers=headers)
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "pending" and r.json()["ahead"] == 0
    assert (await client.post(f"{API}/entries/acme/draft-bullets", json={"notes": NOTES},
                              headers=headers)).status_code == 409  # one open set per role

    model = FakeModel(script=[{"bullets": [
        "Added Great Expectations checks to 12 Airflow pipelines, cutting failed loads from about 10 a week to 2.",
        "Streamed pipeline alerts through Kafka to the on-call engineer for the data platform team.",
    ]}])
    served = await worker.run_once(model)
    assert served.outcome == "done" and "Candidate's notes:" in model.calls[0] and ACME["facts"][0] in model.calls[0]

    drafts = (await client.get(f"{API}/entries/acme/drafts", headers=headers)).json()
    assert drafts["status"] == "done" and len(drafts["drafts"]) == 1 and "Kafka" in drafts["left_out"][0]["reason"]

    edited = drafts["drafts"][0]["text"].replace("Added", "Introduced")
    saved = await client.post(f"{API}/entries/acme/facts", json={"facts": [edited], "draft_id": drafts["id"]},
                              headers=headers)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    acme = next(e for e in body["data"]["experience"] if e["id"] == "acme")
    assert acme["facts"] == ACME["facts"] + [edited] and body["version"] == 2
    assert (await client.get(f"{API}/entries/acme/drafts", headers=headers)).json() is None  # closed once kept


async def test_add_facts_is_audited(client, drafter):
    headers = await drafter()
    r = await client.post(f"{API}/entries/beta/facts", json={"facts": ["Documented 30 SQL Server reports before the move."]},
                          headers=headers)
    assert r.status_code == 200
    async with AsyncSessionLocal() as db:
        audit = await db.scalar(select(AuditLog).where(AuditLog.action == "master_profile.add_facts",
                                                       AuditLog.user_id == drafter.user_id))
    assert audit.after_state == {"entry_id": "beta", "added": 1, "from_version": 1, "draft_id": None}


async def test_drafting_refusals(client, drafter):
    basic = await drafter(engine="basic")
    assert (await client.post(f"{API}/entries/acme/draft-bullets", json={"notes": NOTES},
                              headers=basic)).status_code == 409
    headers = await drafter()
    assert (await client.post(f"{API}/entries/nope/draft-bullets", json={"notes": NOTES},
                              headers=headers)).status_code == 404
    assert (await client.post(f"{API}/entries/acme/draft-bullets", json={"notes": "too short"},
                              headers=headers)).status_code == 422
    assert (await client.post(f"{API}/entries/nope/facts", json={"facts": ["Did a thing for six weeks."]},
                              headers=headers)).status_code == 404


async def test_discard_and_a_failed_draft(client, drafter):
    headers = await drafter()
    await client.post(f"{API}/entries/acme/draft-bullets", json={"notes": NOTES}, headers=headers)
    for _ in range(3):  # every try fails: the drafts show the error
        await worker.run_once(FakeModel(script=[ModelError("model returned invalid JSON")]))
    drafts = (await client.get(f"{API}/entries/acme/drafts", headers=headers)).json()
    assert drafts["status"] == "failed" and "invalid JSON" in drafts["error"]
    assert (await client.delete(f"{API}/entries/acme/drafts", headers=headers)).status_code == 204
    assert (await client.get(f"{API}/entries/acme/drafts", headers=headers)).json() is None
    again = await client.post(f"{API}/entries/acme/draft-bullets", json={"notes": NOTES}, headers=headers)
    assert again.status_code == 202  # a new set once the old one is gone


async def test_draft_items_wait_their_turn_in_the_queue(client, drafter):
    first, second = await drafter(), await drafter()
    await client.post(f"{API}/entries/acme/draft-bullets", json={"notes": NOTES}, headers=first)
    r = await client.post(f"{API}/entries/beta/draft-bullets", json={"notes": NOTES}, headers=second)
    assert r.json()["ahead"] == 1
    async with AsyncSessionLocal() as db:
        items = list(await db.scalars(select(AIQueueItem).where(AIQueueItem.kind == "draft_bullets",
                                                                AIQueueItem.status == "pending")))
        drafts = {d.id: d for d in await db.scalars(select(BulletDraft))}
    assert all(i.assessment_id is None and i.bullet_draft_id in drafts for i in items)


async def test_discarding_before_the_writer_starts_leaves_the_queue(client, drafter):
    headers = await drafter()
    await client.post(f"{API}/entries/acme/draft-bullets", json={"notes": NOTES}, headers=headers)
    assert (await client.delete(f"{API}/entries/acme/drafts", headers=headers)).status_code == 204
    async with AsyncSessionLocal() as db:
        left = await db.scalar(select(AIQueueItem).join(BulletDraft, AIQueueItem.bullet_draft_id == BulletDraft.id)
                               .where(BulletDraft.user_id == drafter.user_id))
    assert left is None  # the writer won't spend time on drafts nobody wants
