"""A job an AI engine brought in for one user is invisible to everyone else,
and a dismissal hides a shared job only for the user who dismissed it."""
from sqlalchemy import select

from app.applaut.models.generated_document import GeneratedDocument
from app.applaut.models.job_assessment import JobAssessment
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.score import Score
from app.applaut.services import document as document_service
from app.applaut.services.scoring import run_scoring
from app.db.session import AsyncSessionLocal

API = "/api/v1/applaut"


async def _add_assessment(user, profile, opp, **fields):
    async with AsyncSessionLocal() as db:
        db.add(JobAssessment(
            user_id=user.id, profile_id=profile.id, opportunity_id=opp.id, engine="own_routine",
            match_score=fields.pop("match_score", 75),
            matched_skills=fields.pop("matched_skills", ["Python", "SQL"]),
            missing_skills=fields.pop("missing_skills", ["dbt"]),
            flags=fields.pop("flags", []), raw={}, **fields,
        ))
        await db.commit()


async def _list_ids(client, headers, **params):
    r = await client.get(f"{API}/opportunities", headers=headers, params={"page_size": 100, **params})
    assert r.status_code == 200, r.text
    return {item["id"]: item for item in r.json()["items"]}


async def test_private_job_is_listed_with_its_assessment_for_its_owner(client, make_user, make_opportunity):
    owner, profile, headers = await make_user()
    opp = await make_opportunity(owner=owner, title="Owner's Job")
    await _add_assessment(owner, profile, opp, match_score=71, flags=["CHECK: fixed-term?"])

    items = await _list_ids(client, headers, engine="own_routine")
    item = items[str(opp.id)]
    assert item["is_private"] is True
    assert item["assessment"]["match_score"] == 71
    assert item["assessment"]["missing_skills"] == ["dbt"]
    assert "owner_user_id" not in item

    r = await client.get(f"{API}/opportunities/{opp.id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["assessment"]["flags"] == ["CHECK: fixed-term?"]


async def test_private_job_is_invisible_to_other_users(client, make_user, make_opportunity):
    owner, _, _ = await make_user()
    _, _, other_headers = await make_user()
    opp = await make_opportunity(owner=owner)

    assert str(opp.id) not in await _list_ids(client, other_headers)
    assert (await client.get(f"{API}/opportunities/{opp.id}", headers=other_headers)).status_code == 404
    r = await client.post(f"{API}/applications", headers=other_headers, json={"opportunity_id": str(opp.id)})
    assert r.status_code == 404
    r = await client.post(f"{API}/opportunities/{opp.id}/documents", headers=other_headers)
    assert r.status_code == 404


async def test_other_users_scoring_and_stats_skip_private_jobs(client, make_user, make_opportunity):
    owner, _, _ = await make_user()
    other, other_profile, other_headers = await make_user()
    shared = await make_opportunity()

    before = (await client.get(f"{API}/stats", headers=other_headers)).json()["opportunities_found"]
    opp = await make_opportunity(owner=owner)
    after = (await client.get(f"{API}/stats", headers=other_headers)).json()["opportunities_found"]
    assert after == before

    async with AsyncSessionLocal() as db:
        await run_scoring(other, db, mode="rule_based")
        scored = set(await db.scalars(select(Score.opportunity_id).where(Score.profile_id == other_profile.id)))
    assert shared.id in scored
    assert opp.id not in scored


async def test_dismissing_a_shared_job_hides_it_only_for_that_user(client, make_user, make_opportunity):
    user_a, profile_a, headers_a = await make_user()
    _, _, headers_b = await make_user()
    shared = await make_opportunity()
    async with AsyncSessionLocal() as db:
        score = Score(opportunity_id=shared.id, profile_id=profile_a.id, user_id=user_a.id,
                      total_score=72, explanation={}, scoring_mode="rule_based", user_decision="pending_review")
        db.add(score)
        await db.commit()
        await db.refresh(score)

    r = await client.post(f"{API}/scores/{score.id}/decide", headers=headers_a, json={"action": "dismiss"})
    assert r.status_code == 200, r.text

    async with AsyncSessionLocal() as db:
        assert (await db.get(Opportunity, shared.id)).is_active is True
    assert str(shared.id) not in await _list_ids(client, headers_a)
    assert str(shared.id) in await _list_ids(client, headers_b)


async def test_applaut_templates_cannot_overwrite_an_engines_documents(client, make_user, make_opportunity):
    owner, _, headers = await make_user()
    opp = await make_opportunity(owner=owner)
    r = await client.post(f"{API}/opportunities/{opp.id}/documents", headers=headers)
    assert r.status_code == 409


async def test_pdf_link_only_for_the_documents_owner(client, make_user, make_opportunity, monkeypatch):
    owner, profile, headers = await make_user()
    _, _, other_headers = await make_user()
    opp = await make_opportunity(owner=owner)
    async with AsyncSessionLocal() as db:
        pdf = GeneratedDocument(
            user_id=owner.id, profile_id=profile.id, opportunity_id=opp.id, document_type="tailored_resume",
            generation_mode="ai", engine="own_routine", content="CV text", content_type="application/pdf",
            r2_key="applaut/documents/x/cv.pdf", is_current=True,
        )
        markdown = GeneratedDocument(
            user_id=owner.id, profile_id=profile.id, opportunity_id=opp.id, document_type="cover_letter",
            generation_mode="template", content="Letter", is_current=True,
        )
        db.add_all([pdf, markdown])
        await db.commit()
        await db.refresh(pdf)
        await db.refresh(markdown)

    calls = []

    def fake_presign(key, expires_in=300, download_name=None):
        calls.append((key, download_name))
        return "https://signed.example/cv.pdf"

    monkeypatch.setattr(document_service, "generate_presigned_url", fake_presign)
    monkeypatch.setattr(document_service.settings, "r2_bucket_name", "")
    r = await client.get(f"{API}/documents/{pdf.id}/file", headers=headers)
    assert r.status_code == 503
    monkeypatch.setattr(document_service.settings, "r2_bucket_name", "test-bucket")

    r = await client.get(f"{API}/opportunities/{opp.id}/documents", headers=headers)
    assert r.json()["tailored_resume"]["has_file"] is True
    assert r.json()["cover_letter"]["has_file"] is False

    r = await client.get(f"{API}/documents/{pdf.id}/file", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"url": "https://signed.example/cv.pdf", "expires_in": 300, "file_name": "CV.pdf"}
    assert calls == [("applaut/documents/x/cv.pdf", "CV.pdf")]

    assert (await client.get(f"{API}/documents/{pdf.id}/file", headers=other_headers)).status_code == 404
    assert (await client.get(f"{API}/documents/{markdown.id}/file", headers=headers)).status_code == 404
    assert (await client.get(f"{API}/documents/not-a-uuid/file", headers=headers)).status_code == 404
