"""Public page visibility rules (BETA_PLAN §13)."""
import uuid

from sqlalchemy import update

from app.db.session import AsyncSessionLocal
from app.prosho.models import ProshoClaim, ProshoProject, ProshoUser
from app.prosho.models.enums import ClaimManualStatus, ClaimTargetOp

API = "/api/v1/prosho"


async def _project(client, h, **patch):
    slug = f"pub-{uuid.uuid4().hex[:8]}"
    pid = (await client.post(f"{API}/projects", json={"title": "Pub", "slug": slug, "project_type": "data_science"},
                             headers=h)).json()["id"]
    if patch:
        assert (await client.patch(f"{API}/projects/{pid}", json=patch, headers=h)).status_code == 200
    return slug, uuid.UUID(pid)


async def _page(client, slug, headers=None):
    return await client.get(f"{API}/public/projects/{slug}", headers=headers or {})


async def test_visibility_rules(client, make_user):
    _, owner = await make_user("owner", name="Owner Name")
    _, other = await make_user("other")

    private, _ = await _project(client, owner)
    assert (await _page(client, private)).status_code == 404
    assert (await _page(client, private, other)).status_code == 404
    resp = await _page(client, private, owner)
    assert resp.status_code == 200 and resp.json()["preview"] is True
    assert resp.headers["cache-control"] == "private, no-store"

    unlisted, _ = await _project(client, owner, visibility="unlisted")
    resp = await _page(client, unlisted)
    assert resp.status_code == 200 and resp.json()["preview"] is False
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.json()["owner"] == {"name": "Owner Name", "github_login": "owner", "avatar_url": None}

    public, _ = await _project(client, owner, visibility="public", supervisor_confirmed=True)
    assert (await _page(client, public.upper())).status_code == 200  # slugs are case-insensitive
    assert (await _page(client, "no-such-page")).status_code == 404

    # A junk token is just "anonymous", not an error.
    assert (await _page(client, unlisted, {"Authorization": "Bearer junk"})).status_code == 200


async def test_inactive_project_or_owner_is_404(client, make_user):
    owner_user, owner = await make_user("owner")
    slug, pid = await _project(client, owner, visibility="unlisted")
    async with AsyncSessionLocal() as db:
        await db.execute(update(ProshoProject).where(ProshoProject.id == pid).values(is_active=False))
        await db.commit()
    assert (await _page(client, slug)).status_code == 404

    slug2, _ = await _project(client, owner, visibility="unlisted")
    async with AsyncSessionLocal() as db:
        await db.execute(update(ProshoUser).where(ProshoUser.id == owner_user.id).values(is_active=False))
        await db.commit()
    assert (await _page(client, slug2)).status_code == 404


async def test_claims_on_the_page(client, make_user):
    _, owner = await make_user("owner")
    slug, pid = await _project(client, owner, visibility="unlisted")
    async with AsyncSessionLocal() as db:
        db.add_all([
            ProshoClaim(project_id=pid, key="measured", text="Within 25%", metric_key="err",
                        target_op=ClaimTargetOp.abs_lte, target_value=25, position=0),
            ProshoClaim(project_id=pid, key="manual", text="Five maps", position=1,
                        manual_status=ClaimManualStatus.in_progress),
            ProshoClaim(project_id=pid, key="gone", text="Dropped", position=2),
        ])
        await db.commit()
        await db.execute(update(ProshoClaim).where(ProshoClaim.key == "gone", ProshoClaim.project_id == pid)
                         .values(archived_at=ProshoClaim.created_at))  # dropped from prosho.yaml
        await db.commit()
    claims = (await _page(client, slug)).json()["claims"]
    assert [(c["key"], c["status"], c["self_reported"]) for c in claims] == [
        ("measured", "awaiting_evidence", False), ("manual", "in_progress", True)]
