"""Phase 3: admin tools, mentor access, milestones, feedback."""
import uuid

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.prosho.models import ProshoAuditLog, ProshoClaim
from app.prosho.models.enums import ProshoUserRole

API = "/api/v1/prosho"


@pytest.fixture
async def team(client, make_user):
    """A student's unlisted project, an admin, and a mentor assigned to it."""
    student, sh = await make_user("student")
    admin, ah = await make_user("founder", role=ProshoUserRole.admin)
    mentor, mh = await make_user("mentor", role=ProshoUserRole.mentor)
    slug = f"tm-{uuid.uuid4().hex[:8]}"
    pid = (await client.post(f"{API}/projects", json={"title": "Team", "slug": slug, "project_type": "data_science"},
                             headers=sh)).json()["id"]
    resp = await client.post(f"{API}/admin/projects/{pid}/mentors", json={"mentor_id": str(mentor.id)}, headers=ah)
    assert resp.status_code == 201
    return {"pid": pid, "slug": slug, "student": student, "sh": sh, "admin": admin, "ah": ah,
            "mentor": mentor, "mh": mh}


async def _audit_actions(entity_id):
    async with AsyncSessionLocal() as db:
        return [a.action for a in await db.scalars(select(ProshoAuditLog).where(ProshoAuditLog.entity_id == entity_id)
                                                   .order_by(ProshoAuditLog.created_at))]


# --- admin -------------------------------------------------------------------

async def test_admin_endpoints_need_admin(client, team):
    for h in (team["sh"], team["mh"]):
        assert (await client.get(f"{API}/admin/users", headers=h)).status_code == 403
        assert (await client.post(f"{API}/admin/projects/{team['pid']}/mentors",
                                  json={"mentor_id": str(team["mentor"].id)}, headers=h)).status_code == 403
    assert (await client.get(f"{API}/admin/audit")).status_code == 401


async def test_assign_mentor_rules(client, team, make_user):
    url, ah = f"{API}/admin/projects/{team['pid']}/mentors", team["ah"]
    projects = (await client.get(f"{API}/admin/projects", headers=ah)).json()
    mine = next(p for p in projects if p["id"] == team["pid"])
    assert [m["github_login"] for m in mine["mentors"]] == ["mentor"] and mine["owner"]["github_login"] == "student"

    assert (await client.post(url, json={"mentor_id": str(team["mentor"].id)}, headers=ah)).status_code == 409  # twice
    assert (await client.post(url, json={"mentor_id": str(team["student"].id)}, headers=ah)).status_code == 409  # a student
    assert (await client.post(url, json={"mentor_id": str(uuid.uuid4())}, headers=ah)).status_code == 404
    # The owner can't mentor their own project, even as a mentor.
    async with AsyncSessionLocal() as db:
        (await db.get(type(team["student"]), team["student"].id)).role = ProshoUserRole.mentor
        await db.commit()
    assert (await client.post(url, json={"mentor_id": str(team["student"].id)}, headers=ah)).status_code == 409

    # Can't stop being a mentor while assigned to projects.
    resp = await client.patch(f"{API}/admin/users/{team['mentor'].id}", json={"role": "student"}, headers=ah)
    assert resp.status_code == 409
    assert (await client.delete(f"{url}/{team['mentor'].id}", headers=ah)).status_code == 200
    assert (await client.delete(f"{url}/{team['mentor'].id}", headers=ah)).status_code == 404
    assert (await client.get(f"{API}/projects/{team['pid']}", headers=team["mh"])).status_code == 404

    assert await _audit_actions(uuid.UUID(team["pid"])) == ["project.create", "mentor.assign", "mentor.remove"]


async def test_admin_user_and_project_updates(client, team):
    ah = team["ah"]
    # Not on yourself: the beta has one admin.
    assert (await client.patch(f"{API}/admin/users/{team['admin'].id}", json={"is_active": False}, headers=ah)).status_code == 409

    users = (await client.patch(f"{API}/admin/users/{team['student'].id}", json={"is_active": False}, headers=ah)).json()
    assert next(u for u in users if u["github_login"] == "student")["is_active"] is False
    assert (await client.get(f"{API}/projects", headers=team["sh"])).status_code == 401  # signed out
    await client.patch(f"{API}/admin/users/{team['student'].id}", json={"is_active": True}, headers=ah)

    await client.patch(f"{API}/admin/projects/{team['pid']}", json={"is_active": False}, headers=ah)
    assert (await client.get(f"{API}/projects/{team['pid']}", headers=team["sh"])).status_code == 404
    assert (await client.get(f"{API}/projects/{team['pid']}", headers=team["mh"])).status_code == 404

    log = (await client.get(f"{API}/admin/audit?limit=5", headers=ah)).json()
    assert log[0]["action"] == "project.update" and log[0]["actor_login"] == "founder"
    assert log[0]["after"] == {"is_active": False}
    assert [e["action"] for e in log[1:3]] == ["user.update", "user.update"]


# --- mentor access -------------------------------------------------------------

async def test_mentor_can_view_but_not_change(client, team):
    pid, mh = team["pid"], team["mh"]
    listed = (await client.get(f"{API}/projects", headers=mh)).json()
    assert [(p["id"], p["access"]) for p in listed] == [(pid, "mentor")]
    p = (await client.get(f"{API}/projects/{pid}", headers=mh)).json()
    assert p["access"] == "mentor" and p["has_mentor"] is True
    assert (await client.get(f"{API}/projects/{pid}", headers=team["sh"])).json()["access"] == "owner"

    for path in ("claims", "evidence", "data-module", "milestones", "feedback", "timeline", "stats"):
        assert (await client.get(f"{API}/projects/{pid}/{path}", headers=mh)).status_code == 200, path
    assert (await client.patch(f"{API}/projects/{pid}", json={"title": "x"}, headers=mh)).status_code == 404
    assert (await client.get(f"{API}/projects/{pid}/tokens", headers=mh)).status_code == 404
    assert (await client.post(f"{API}/projects/{pid}/sync", headers=mh)).status_code == 404
    assert (await client.post(f"{API}/projects/{pid}/milestones", json={"title": "x"}, headers=mh)).status_code == 404


async def test_public_page_badge_and_mentor_preview(client, team, make_user):
    slug, mh = team["slug"], team["mh"]
    _, stranger = await make_user("stranger")
    # Private: the mentor gets a preview, everyone else a 404.
    page = (await client.get(f"{API}/public/projects/{slug}", headers=mh)).json()
    assert page["preview"] and page["viewer_is_team"] and page["mentored"]
    assert (await client.get(f"{API}/public/projects/{slug}", headers=stranger)).status_code == 404

    await client.patch(f"{API}/projects/{team['pid']}", json={"visibility": "unlisted"}, headers=team["sh"])
    page = (await client.get(f"{API}/public/projects/{slug}")).json()
    assert page["mentored"] is True and page["viewer_is_team"] is False
    assert "mentor" not in str(page).replace("mentored", "")  # never named


# --- milestones ---------------------------------------------------------------

async def test_milestone_lifecycle_and_review(client, team):
    base, sh, mh = f"{API}/projects/{team['pid']}/milestones", team["sh"], team["mh"]
    later = (await client.post(base, json={"title": "Write-up", "due_on": "2027-01-20"}, headers=sh)).json()
    undated = (await client.post(base, json={"title": "  Polish  "}, headers=sh)).json()
    first = (await client.post(base, json={"title": "Pipeline", "due_on": "2026-11-15"}, headers=sh)).json()
    assert undated["title"] == "Polish"
    assert [m["title"] for m in (await client.get(base, headers=mh)).json()] == ["Pipeline", "Write-up", "Polish"]

    url = f"{base}/{first['id']}"
    assert (await client.patch(url, json={"reviewed": True}, headers=mh)).status_code == 409  # not completed yet
    assert (await client.patch(url, json={"completed": True}, headers=mh)).status_code == 409  # student's job
    assert (await client.patch(url, json={"completed": True}, headers=sh)).json()["completed_at"]
    assert (await client.patch(url, json={"reviewed": True}, headers=sh)).status_code == 409  # mentor's job
    m = (await client.patch(url, json={"reviewed": True}, headers=mh)).json()
    assert m["reviewed_at"] and m["reviewed_by"]["github_login"] == "mentor"

    # Moving the date keeps the review; renaming or reopening drops it.
    assert (await client.patch(url, json={"due_on": "2026-11-20"}, headers=sh)).json()["reviewed_at"]
    assert (await client.patch(url, json={"title": "Pipeline v2"}, headers=sh)).json()["reviewed_at"] is None
    await client.patch(url, json={"reviewed": True}, headers=mh)
    m = (await client.patch(url, json={"completed": False}, headers=sh)).json()
    assert m["completed_at"] is None and m["reviewed_at"] is None

    await client.patch(f"{base}/{later['id']}", json={"completed": True}, headers=sh)
    await client.patch(f"{base}/{later['id']}", json={"reviewed": True}, headers=mh)
    await client.patch(f"{API}/projects/{team['pid']}", json={"visibility": "unlisted"}, headers=sh)
    page = (await client.get(f"{API}/public/projects/{team['slug']}")).json()
    assert [(m["title"], m["reviewed"], bool(m["completed_at"])) for m in page["milestones"]] == [
        ("Pipeline v2", False, False), ("Write-up", True, True), ("Polish", False, False)]

    assert (await client.delete(f"{base}/{undated['id']}", headers=mh)).status_code == 404
    assert (await client.delete(f"{base}/{undated['id']}", headers=sh)).status_code == 204
    assert (await client.patch(f"{base}/{undated['id']}", json={"completed": True}, headers=sh)).status_code == 404
    assert await _audit_actions(uuid.UUID(undated["id"])) == ["milestone.create", "milestone.delete"]


async def test_milestones_are_private_to_the_team(client, team, make_user):
    _, other = await make_user("other")
    base = f"{API}/projects/{team['pid']}/milestones"
    mid = (await client.post(base, json={"title": "Pipeline"}, headers=team["sh"])).json()["id"]
    assert (await client.get(base, headers=other)).status_code == 404
    assert (await client.patch(f"{base}/{mid}", json={"title": "x"}, headers=other)).status_code == 404


# --- feedback -------------------------------------------------------------------

async def test_feedback_threads(client, team, make_user):
    pid, sh, mh = team["pid"], team["sh"], team["mh"]
    url = f"{API}/projects/{pid}/feedback"
    mid = (await client.post(f"{API}/projects/{pid}/milestones", json={"title": "Pipeline"}, headers=sh)).json()["id"]
    async with AsyncSessionLocal() as db:
        claim = ProshoClaim(project_id=uuid.UUID(pid), key="maps", text="Five maps", position=0)
        db.add(claim)
        await db.commit()
        claim_id = str(claim.id)

    threads = (await client.post(url, json={"body": "Add a data dictionary", "milestone_id": mid}, headers=mh)).json()
    tid = threads[0]["id"]
    assert (threads[0]["author_role"], threads[0]["milestone_title"]) == ("mentor", "Pipeline")
    threads = (await client.post(url, json={"body": "Is five enough?", "claim_id": claim_id}, headers=sh)).json()
    assert (threads[0]["author_role"], threads[0]["claim_text"]) == ("owner", "Five maps")
    assert (await client.get(f"{API}/projects", headers=sh)).json()[0]["open_feedback"] == 2

    threads = (await client.post(url, json={"body": "Done — see README", "parent_id": tid}, headers=sh)).json()
    thread = next(t for t in threads if t["id"] == tid)
    assert [r["body"] for r in thread["replies"]] == ["Done — see README"]

    # Resolved threads sink to the bottom; a reply reopens one.
    threads = (await client.patch(f"{url}/{tid}", json={"resolved": True}, headers=mh)).json()
    assert threads[-1]["id"] == tid and threads[-1]["resolved_at"]
    assert (await client.get(f"{API}/projects", headers=sh)).json()[0]["open_feedback"] == 1
    threads = (await client.post(url, json={"body": "One more thing", "parent_id": tid}, headers=mh)).json()
    assert next(t for t in threads if t["id"] == tid)["resolved_at"] is None

    reply_id = thread["replies"][0]["id"]
    assert (await client.post(url, json={"body": "x", "parent_id": reply_id}, headers=sh)).status_code == 404
    assert (await client.patch(f"{url}/{reply_id}", json={"resolved": True}, headers=sh)).status_code == 404
    assert (await client.post(url, json={"body": "x", "parent_id": tid, "milestone_id": mid}, headers=sh)).status_code == 422
    assert (await client.post(url, json={"body": "   "}, headers=sh)).status_code == 422
    assert (await client.post(url, json={"body": "x", "milestone_id": str(uuid.uuid4())}, headers=sh)).status_code == 404

    _, other = await make_user("other")
    assert (await client.get(url, headers=other)).status_code == 404
    assert (await client.post(url, json={"body": "hi"}, headers=other)).status_code == 404

    await client.patch(f"{API}/projects/{pid}", json={"visibility": "unlisted"}, headers=sh)
    page = (await client.get(f"{API}/public/projects/{team['slug']}")).text
    assert "data dictionary" not in page and "feedback" not in page
