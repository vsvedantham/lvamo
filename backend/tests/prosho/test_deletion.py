"""Deleting a project and deleting a whole account."""
import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.prosho.models import (
    ProshoAuditLog, ProshoFeedback, ProshoMilestone, ProshoProject, ProshoRetiredSlug, ProshoUser,
)
from app.prosho.models.enums import ProshoUserRole

API = "/api/v1/prosho"


@pytest.fixture
async def tombstones():
    """Tombstones and retired slugs outlive the test users; tidy them up."""
    ids: list[uuid.UUID] = []
    slugs: list[str] = []
    yield ids, slugs
    async with AsyncSessionLocal() as db:
        await db.execute(delete(ProshoAuditLog).where(ProshoAuditLog.entity_id.in_(ids)))
        await db.execute(delete(ProshoRetiredSlug).where(ProshoRetiredSlug.slug.in_(slugs)))
        await db.commit()


async def _new_project(client, h, visibility=None):
    slug = f"del-{uuid.uuid4().hex[:8]}"
    pid = (await client.post(f"{API}/projects", json={"title": "Doomed", "slug": slug, "project_type": "frontend"},
                             headers=h)).json()["id"]
    if visibility:
        await client.patch(f"{API}/projects/{pid}", json={"visibility": visibility}, headers=h)
    return pid, slug


async def _audit(entity_id):
    async with AsyncSessionLocal() as db:
        return [(a.action, a.after) for a in await db.scalars(
            select(ProshoAuditLog).where(ProshoAuditLog.entity_id == entity_id))]


async def test_delete_private_project(client, make_user, tombstones):
    _, h = await make_user("student")
    _, other = await make_user("other")
    pid, slug = await _new_project(client, h)
    mid = (await client.post(f"{API}/projects/{pid}/milestones", json={"title": "Step"}, headers=h)).json()["id"]
    tombstones[0].append(uuid.UUID(pid))

    assert (await client.delete(f"{API}/projects/{pid}", headers=other)).status_code == 404
    assert (await client.delete(f"{API}/projects/{pid}", headers=h)).status_code == 204
    assert (await client.get(f"{API}/projects/{pid}", headers=h)).status_code == 404
    assert (await client.delete(f"{API}/projects/{pid}", headers=h)).status_code == 404

    async with AsyncSessionLocal() as db:
        assert await db.get(ProshoMilestone, uuid.UUID(mid)) is None
        assert await db.get(ProshoRetiredSlug, slug) is None  # never shared: free again
    assert await _audit(uuid.UUID(pid)) == [("project.delete", {"slug_retired": False})]
    assert await _audit(uuid.UUID(mid)) == []
    # The address can be reused.
    assert (await client.post(f"{API}/projects", json={"title": "Again", "slug": slug, "project_type": "frontend"},
                              headers=h)).status_code == 201


async def test_shared_address_is_retired(client, make_user, tombstones):
    _, h = await make_user("student")
    pid, slug = await _new_project(client, h, visibility="unlisted")
    tombstones[0].append(uuid.UUID(pid)); tombstones[1].append(slug)
    assert (await client.delete(f"{API}/projects/{pid}", headers=h)).status_code == 204
    assert (await client.get(f"{API}/public/projects/{slug}")).status_code == 404
    resp = await client.post(f"{API}/projects", json={"title": "Squat", "slug": slug, "project_type": "frontend"},
                             headers=h)
    assert resp.status_code == 409


async def test_delete_account(client, make_user, tombstones):
    student, sh = await make_user("student")
    admin, ah = await make_user("founder", role=ProshoUserRole.admin)
    mentor, mh = await make_user("mentor", role=ProshoUserRole.mentor)
    pid, slug = await _new_project(client, sh, visibility="unlisted")
    tombstones[1].append(slug)

    # The mentor also mentors someone else's project, and wrote there.
    other, oh = await make_user("other")
    opid, _ = await _new_project(client, oh)
    for p in (pid, opid):
        assert (await client.post(f"{API}/admin/projects/{p}/mentors", json={"mentor_id": str(mentor.id)},
                                  headers=ah)).status_code == 201
    fid = (await client.post(f"{API}/projects/{opid}/feedback", json={"body": "Nice work"}, headers=mh)).json()[0]["id"]

    url = f"{API}/auth/me"
    assert (await client.request("DELETE", url, json={"confirm": "wrong"}, headers=mh)).status_code == 422
    assert (await client.request("DELETE", url, json={"confirm": "founder"}, headers=ah)).status_code == 409

    # Deleting the mentor: their name leaves the audit log, their note stays unsigned.
    assert (await client.request("DELETE", url, json={"confirm": "MENTOR"}, headers=mh)).status_code == 204
    tombstones[0].append(mentor.id)
    assert (await client.get(url, headers=mh)).status_code == 401
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProshoFeedback, uuid.UUID(fid))).author_id is None
        rows = list(await db.scalars(select(ProshoAuditLog).where(ProshoAuditLog.action == "mentor.assign",
                                                                 ProshoAuditLog.entity_id == uuid.UUID(opid))))
        assert rows and all("mentor_login" not in r.after for r in rows)
    thread = (await client.get(f"{API}/projects/{opid}/feedback", headers=oh)).json()[0]
    assert thread["author"] is None and thread["body"] == "Nice work"

    # Deleting the student: projects go, shared address retired, only tombstones left.
    assert (await client.request("DELETE", url, json={"confirm": "student"}, headers=sh)).status_code == 204
    tombstones[0].append(student.id)
    async with AsyncSessionLocal() as db:
        assert await db.get(ProshoUser, student.id) is None
        assert await db.get(ProshoProject, uuid.UUID(pid)) is None
        assert await db.get(ProshoRetiredSlug, slug) is not None
    assert await _audit(uuid.UUID(pid)) == []
    assert await _audit(student.id) == [("user.delete", {"projects_deleted": 1})]
