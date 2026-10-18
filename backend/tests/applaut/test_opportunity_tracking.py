"""Opportunities page: the user's routine jobs first, and the per-job actions
Mark as applied / Not available / Undo with their tabs."""
from sqlalchemy import select

from app.applaut.models.application import Application
from app.applaut.models.job_assessment import JobAssessment
from app.applaut.models.routine import RoutineJob
from app.db.session import AsyncSessionLocal

API = "/api/v1/applaut/opportunities"


async def _routine_job(user, profile, opp, uid: str, score: int, docs_status: str = "done") -> None:
    async with AsyncSessionLocal() as db:
        db.add(RoutineJob(user_id=user.id, uid=uid, opportunity_id=opp.id, docs_status=docs_status))
        db.add(JobAssessment(user_id=user.id, profile_id=profile.id, opportunity_id=opp.id, engine="own_routine",
                             match_score=score, matched_skills=[], missing_skills=[], flags=[], raw={}))
        await db.commit()


async def test_routine_jobs_first_with_folder_info(client, make_user, make_opportunity):
    user, profile, headers = await make_user(job_engine="own_routine")
    shared = await make_opportunity(title="Shared job")  # no score: would sort last anyway
    low = await make_opportunity(owner=user, title="Routine low")
    high = await make_opportunity(owner=user, title="Routine high", application_url="https://jobs.example.com/1")
    await _routine_job(user, profile, low, "acme__low__berlin", 71, docs_status="pending")
    await _routine_job(user, profile, high, "acme__high__berlin", 95)

    r = await client.get(API, headers=headers, params={"page_size": 100, "include_shared": "true"})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    titles = [i["title"] for i in items]
    assert titles[:2] == ["Routine high", "Routine low"]
    assert titles.index("Shared job") > 1
    first = items[0]
    assert first["routine"] == {"uid": "acme__high__berlin", "docs_ready": True, "removed": False}
    assert items[1]["routine"]["docs_ready"] is False
    assert first["tracking"]["state"] == "open"
    assert next(i for i in items if i["id"] == str(shared.id))["routine"] is None


async def test_mark_applied_unavailable_and_undo(client, make_user, make_opportunity):
    user, _, headers = await make_user()
    a = await make_opportunity(title="A")
    b = await make_opportunity(title="B")
    c = await make_opportunity(title="C")

    r = await client.put(f"{API}/{a.id}/tracking", json={"state": "applied"}, headers=headers)
    assert r.status_code == 200 and r.json()["state"] == "applied" and r.json()["status"] == "submitted"
    assert r.json()["applied_at"] is not None
    r = await client.put(f"{API}/{b.id}/tracking", json={"state": "unavailable", "reason": "cannot_apply"}, headers=headers)
    assert r.json()["state"] == "unavailable" and r.json()["status"] == "withdrawn"
    r = await client.put(f"{API}/{c.id}/tracking", json={"state": "unavailable", "reason": "closed"}, headers=headers)
    assert r.json()["status"] == "closed"

    res = (await client.get(API, headers=headers, params={"state": "open", "page_size": 100})).json()
    ours = {"A", "B", "C"}
    assert not ours & {i["title"] for i in res["items"]}
    assert res["counts"]["applied"] >= 1 and res["counts"]["unavailable"] >= 2
    applied = (await client.get(API, headers=headers, params={"state": "applied"})).json()
    assert [i["title"] for i in applied["items"]] == ["A"]
    unavailable = {i["title"] for i in (await client.get(API, headers=headers, params={"state": "unavailable"})).json()["items"]}
    assert unavailable == {"B", "C"}

    # Undo puts it back to review and forgets the applied date; one application per job.
    r = await client.put(f"{API}/{a.id}/tracking", json={"state": "open"}, headers=headers)
    assert r.json()["state"] == "open" and r.json()["applied_at"] is None
    async with AsyncSessionLocal() as db:
        apps = list(await db.scalars(select(Application).where(Application.user_id == user.id)))
    assert len(apps) == 3


async def test_tracking_is_per_user_and_private_jobs_hidden(client, make_user, make_opportunity):
    owner, _, owner_headers = await make_user()
    _, _, other_headers = await make_user()
    private = await make_opportunity(owner=owner)
    shared = await make_opportunity()

    r = await client.put(f"{API}/{private.id}/tracking", json={"state": "applied"}, headers=other_headers)
    assert r.status_code == 404
    await client.put(f"{API}/{shared.id}/tracking", json={"state": "applied"}, headers=owner_headers)
    seen_by_other = (await client.get(API, headers=other_headers, params={"state": "open", "page_size": 100})).json()
    assert str(shared.id) in {i["id"] for i in seen_by_other["items"]}  # still to review for them


async def test_bad_tracking_input(client, make_user, make_opportunity):
    _, _, headers = await make_user()
    opp = await make_opportunity()
    r = await client.put(f"{API}/{opp.id}/tracking", json={"state": "deleted"}, headers=headers)
    assert r.status_code == 422


async def test_routine_users_hide_shared_basic_jobs_by_default(client, make_user, make_opportunity):
    user, profile, headers = await make_user(job_engine="own_routine")
    shared = await make_opportunity(title="Shared only")
    linked = await make_opportunity(title="Shared, also found by my routine")
    mine = await make_opportunity(owner=user, title="Mine")
    await _routine_job(user, profile, linked, "linked__de__berlin", 88)
    await _routine_job(user, profile, mine, "mine__de__berlin", 90)

    res = (await client.get(API, headers=headers, params={"page_size": 100})).json()
    assert res["include_shared"] is False
    assert {i["title"] for i in res["items"]} == {"Mine", "Shared, also found by my routine"}
    assert res["counts"]["all"] == 2

    res = (await client.get(API, headers=headers, params={"page_size": 100, "include_shared": "true"})).json()
    assert res["include_shared"] is True and str(shared.id) in {i["id"] for i in res["items"]}

    stats = (await client.get("/api/v1/applaut/stats", headers=headers)).json()
    assert stats["opportunities_found"] == 2 and stats["good_matches"] == 2

    # Basic users keep seeing the shared pool.
    _, _, basic_headers = await make_user()
    res = (await client.get(API, headers=basic_headers, params={"page_size": 100})).json()
    assert res["include_shared"] is True and str(shared.id) in {i["id"] for i in res["items"]}
