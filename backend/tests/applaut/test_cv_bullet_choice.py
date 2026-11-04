"""Original vs tailored bullets on an Applaut AI CV (APPLAUT_AI_V2_PLAN.md §3,
B4): the CV keeps what it was built from, and switching one bullet builds it
again in code, as a new current version."""
import copy
import time
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.applaut.ai import worker
from app.applaut.documents.render import build_documents, rerender_cv
from app.applaut.models.generated_document import GeneratedDocument
from app.applaut.models.master_profile import MasterProfile
from app.applaut.models.profile import Profile
from app.db.session import AsyncSessionLocal
from tests.applaut.test_ai_engine import (  # noqa: F401  (fixtures)
    FakeModel, _enqueue, _isolated_queue, _job, _raw,
)
from tests.applaut.test_documents import JOB, PROFILE, TAILORED, WRITTEN, as_answer, profile

API = "/api/v1/applaut/documents"
SPARK = PROFILE["experience"][0]["facts"][1]  # acme.2, reworded as TAILORED[0]


async def _cv_for(make_user, make_opportunity):
    """A user with Applaut AI whose CV for one job the writer has written; (headers, cv)."""
    user, prof, headers = await make_user()
    async with AsyncSessionLocal() as db:
        await db.execute(update(Profile).where(Profile.id == prof.id).values(
            job_engine="applaut_ai", job_engine_changed_at=datetime.now(timezone.utc)))
        db.add(MasterProfile(user_id=user.id, data=copy.deepcopy(PROFILE)))
        await db.commit()
    opp = await _job(make_opportunity)
    a = await _raw(user, prof, opp)
    await _enqueue("write_docs", a)
    await worker.run_once(FakeModel(written={**WRITTEN, **as_answer(TAILORED)}))
    return headers, await _current_cv(opp.id)


async def _current_cv(opportunity_id):
    async with AsyncSessionLocal() as db:
        return await db.scalar(select(GeneratedDocument).where(
            GeneratedDocument.opportunity_id == opportunity_id, GeneratedDocument.document_type == "tailored_resume",
            GeneratedDocument.is_current == True))  # noqa: E712


async def test_cv_details_list_each_bullet_both_ways(client, make_user, make_opportunity):
    headers, cv = await _cv_for(make_user, make_opportunity)
    doc = (await client.get(f"{API}/{cv.id}", headers=headers)).json()
    assert doc["has_details"] is True and "details" not in doc
    details = (await client.get(f"{API}/{cv.id}/details", headers=headers)).json()
    bullets = {b["fact_id"]: b for b in details["bullets"]}
    assert bullets["acme.2"] == {"fact_id": "acme.2", "entry": "Data Engineer at Acme GmbH", "original": SPARK,
                                 "tailored": TAILORED[0]["text"], "use": "tailored", "note": None}
    assert bullets["acme.3"]["tailored"] is None and "AWS" in bullets["acme.3"]["note"]  # rejected: fact as written


async def test_switching_a_bullet_makes_a_new_current_cv(client, make_user, make_opportunity, _isolated_queue):
    headers, cv = await _cv_for(make_user, make_opportunity)
    assert TAILORED[0]["text"] in cv.content
    r = await client.post(f"{API}/{cv.id}/bullets/acme.2/use", json={"version": "original"}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    new = await _current_cv(cv.opportunity_id)
    assert body["document"]["id"] == str(new.id) != str(cv.id) and body["document"]["is_current"]
    assert SPARK in new.content and TAILORED[0]["text"] not in new.content
    assert _isolated_queue[new.r2_key].startswith(b"%PDF") and new.r2_key != cv.r2_key
    assert {b["fact_id"]: b["use"] for b in body["details"]["bullets"]}["acme.2"] == "original"
    assert [(c["fact_id"], c["use"], c["from_document"]) for c in new.details["choices"]] == \
        [("acme.2", "original", str(cv.id))]
    async with AsyncSessionLocal() as db:
        assert (await db.get(GeneratedDocument, cv.id)).is_current is False  # the old version stays, not current

    back = await client.post(f"{API}/{new.id}/bullets/acme.2/use", json={"version": "tailored"}, headers=headers)
    assert back.status_code == 200 and TAILORED[0]["text"] in (await _current_cv(cv.opportunity_id)).content


async def test_bullet_choice_refusals(client, make_user, make_opportunity):
    headers, cv = await _cv_for(make_user, make_opportunity)
    use = f"{API}/{cv.id}/bullets"
    assert (await client.post(f"{use}/acme.3/use", json={"version": "tailored"}, headers=headers)).status_code == 422
    assert (await client.post(f"{use}/acme.9/use", json={"version": "original"}, headers=headers)).status_code == 404
    same = await client.post(f"{use}/acme.2/use", json={"version": "tailored"}, headers=headers)  # already: no new version
    assert same.status_code == 200 and same.json()["document"]["id"] == str(cv.id)

    _, _, stranger = await make_user()
    assert (await client.get(f"{API}/{cv.id}/details", headers=stranger)).status_code == 404
    assert (await client.post(f"{use}/acme.2/use", json={"version": "original"}, headers=stranger)).status_code == 404

    assert (await client.post(f"{use}/acme.2/use", json={"version": "original"}, headers=headers)).status_code == 200
    stale = await client.post(f"{use}/beta.1/use", json={"version": "original"}, headers=headers)  # cv is no longer current
    assert stale.status_code == 409


async def test_documents_without_details_have_no_bullets_to_switch(client, make_user, make_opportunity):
    headers, cv = await _cv_for(make_user, make_opportunity)
    async with AsyncSessionLocal() as db:
        letter = await db.scalar(select(GeneratedDocument).where(
            GeneratedDocument.opportunity_id == cv.opportunity_id, GeneratedDocument.document_type == "cover_letter"))
    assert (await client.get(f"{API}/{letter.id}", headers=headers)).json()["has_details"] is False
    assert (await client.get(f"{API}/{letter.id}/details", headers=headers)).status_code == 404


def test_rerender_needs_no_model_and_takes_under_a_second():
    docs = build_documents(profile(), JOB, {**WRITTEN, **as_answer(TAILORED)})
    details = copy.deepcopy(docs.cv_details)
    next(b for e in details["entries"] for b in e["bullets"] if b["id"] == "acme.2")["use"] = "original"
    started = time.monotonic()
    cv, after = rerender_cv(details)
    assert time.monotonic() - started < 1.0
    assert SPARK in cv.text and TAILORED[0]["text"] not in cv.text and cv.pdf.startswith(b"%PDF")
    assert cv.text.split("\n")[1] == WRITTEN["headline"]  # headline and the rest as built
    assert [e["id"] for e in after["entries"]] == [e["id"] for e in details["entries"]]


def test_details_keep_the_profile_as_it_was():
    p = profile()
    docs = build_documents(p, JOB, {**WRITTEN, **as_answer(TAILORED)})
    p["personal"]["name"] = "Changed Later"
    cv, _ = rerender_cv(docs.cv_details)
    assert cv.text.startswith("Alex Example")
