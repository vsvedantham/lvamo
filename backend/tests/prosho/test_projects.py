"""Projects API: ownership (404 not 403), slug rules, visibility and the
supervisor rule, manifest-owned fields, audit log."""
import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.prosho.models import ProshoAuditLog, ProshoProject

BASE = "/api/v1/prosho/projects"


async def _create(client, headers, slug="heatrisk-eu", **extra):
    body = {"title": "HeatRisk EU", "slug": slug, "project_type": "data_science", **extra}
    return await client.post(BASE, json=body, headers=headers)


async def _audit(project_id):
    async with AsyncSessionLocal() as db:
        return list(await db.scalars(select(ProshoAuditLog).where(ProshoAuditLog.entity_id == uuid.UUID(project_id))
                                     .order_by(ProshoAuditLog.created_at)))


async def test_create_list_get(client, make_user):
    _, h = await make_user()
    resp = await _create(client, h)
    assert resp.status_code == 201
    p = resp.json()
    assert (p["visibility"], p["manifest_managed"], p["published_at"]) == ("private", False, None)

    assert [x["id"] for x in (await client.get(BASE, headers=h)).json()] == [p["id"]]
    assert (await client.get(f"{BASE}/{p['id']}", headers=h)).json()["slug"] == "heatrisk-eu"
    assert [a.action for a in await _audit(p["id"])] == ["project.create"]


async def test_other_users_project_is_404_and_not_listed(client, make_user):
    _, owner = await make_user("owner")
    _, other = await make_user("other")
    pid = (await _create(client, owner)).json()["id"]
    assert (await client.get(f"{BASE}/{pid}", headers=other)).status_code == 404
    assert (await client.patch(f"{BASE}/{pid}", json={"title": "x"}, headers=other)).status_code == 404
    assert (await client.get(BASE, headers=other)).json() == []
    assert (await client.get(BASE)).status_code == 401


async def test_slug_rules(client, make_user):
    _, h = await make_user()
    for bad in ["ab", "-lead", "trail-", "Has Space", "dashboard", "x" * 61]:
        assert (await _create(client, h, slug=bad)).status_code == 422, bad
    assert (await _create(client, h, slug="HeatRisk-EU")).json()["slug"] == "heatrisk-eu"  # normalised
    assert (await _create(client, h, slug="heatrisk-eu")).status_code == 409


async def test_supervisor_rule_for_public(client, make_user):
    _, h = await make_user()
    pid = (await _create(client, h)).json()["id"]
    url = f"{BASE}/{pid}"

    resp = await client.patch(url, json={"visibility": "public"}, headers=h)
    assert resp.status_code == 409 and "supervisor" in resp.json()["detail"]

    resp = await client.patch(url, json={"visibility": "public", "supervisor_confirmed": True}, headers=h)
    assert resp.status_code == 200
    p = resp.json()
    assert p["visibility"] == "public" and p["supervisor_ok_at"] and p["published_at"]

    # Can't withdraw approval while public…
    assert (await client.patch(url, json={"supervisor_confirmed": False}, headers=h)).status_code == 409
    # …but can after stepping back to unlisted, in the same request.
    resp = await client.patch(url, json={"visibility": "unlisted", "supervisor_confirmed": False}, headers=h)
    assert resp.status_code == 200 and resp.json()["supervisor_ok_at"] is None

    logs = await _audit(pid)
    assert [a.action for a in logs] == ["project.create", "project.update", "project.update"]
    assert logs[1].before["visibility"] == "private" and logs[1].after["visibility"] == "public"
    assert logs[1].after["supervisor_ok_at"]


async def test_slug_locked_once_shared(client, make_user):
    _, h = await make_user()
    pid = (await _create(client, h)).json()["id"]
    url = f"{BASE}/{pid}"
    assert (await client.patch(url, json={"slug": "heatrisk-europe"}, headers=h)).json()["slug"] == "heatrisk-europe"
    await client.patch(url, json={"visibility": "unlisted"}, headers=h)
    await client.patch(url, json={"visibility": "private"}, headers=h)  # published_at stays set
    assert (await client.patch(url, json={"slug": "another-one"}, headers=h)).status_code == 409


async def test_demo_pair_and_url_validation(client, make_user):
    _, h = await make_user()
    url = f"{BASE}/{(await _create(client, h)).json()['id']}"
    assert (await client.patch(url, json={"demo_kind": "streamlit"}, headers=h)).status_code == 422
    assert (await client.patch(url, json={"demo_kind": "url", "demo_url": "javascript:alert(1)"}, headers=h)).status_code == 422
    resp = await client.patch(url, json={"demo_kind": "streamlit", "demo_url": "https://heatrisk.streamlit.app"}, headers=h)
    assert resp.status_code == 200 and resp.json()["demo_url"] == "https://heatrisk.streamlit.app/"
    resp = await client.patch(url, json={"demo_kind": None, "demo_url": None}, headers=h)
    assert resp.json()["demo_kind"] is None


async def test_manifest_owned_fields_are_read_only_after_sync(client, make_user):
    _, h = await make_user()
    pid = (await _create(client, h)).json()["id"]
    async with AsyncSessionLocal() as db:
        project = await db.get(ProshoProject, uuid.UUID(pid))
        project.manifest_synced_at = project.created_at
        await db.commit()
    url = f"{BASE}/{pid}"
    assert (await client.patch(url, json={"title": "New"}, headers=h)).status_code == 409
    assert (await client.patch(url, json={"university": "UE Potsdam"}, headers=h)).status_code == 200
    assert (await client.get(url, headers=h)).json()["manifest_managed"] is True


async def test_no_op_patch_writes_no_audit_row(client, make_user):
    _, h = await make_user()
    pid = (await _create(client, h)).json()["id"]
    await client.patch(f"{BASE}/{pid}", json={"title": "HeatRisk EU", "visibility": "private"}, headers=h)
    assert len(await _audit(pid)) == 1
