"""Master profile from the user's CV (APPLAUT_AI_V2_PLAN.md §5): the writer
points at the CV's lines; code builds the draft from them, so nothing in it is
new wording. The user reviews the draft in the editor and saves it."""
import copy
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update

from app.applaut.ai import prompts, worker
from app.applaut.ai.provider import ModelError
from app.applaut.documents.profile_import import ImportProblem, build_profile, read_cv
from app.applaut.documents.profile_schema import parse_yaml, validate_profile
from app.applaut.models.ai_queue import AIQueueItem
from app.applaut.models.audit_log import AuditLog
from app.applaut.models.profile import Profile
from app.applaut.models.profile_import import ProfileImport
from app.config import settings
from app.db.session import AsyncSessionLocal
from tests.applaut.cv_docx import german_cv, plain_cv
from tests.applaut.test_ai_engine import FakeModel, _isolated_queue  # noqa: F401  (fixture)

API = "/api/v1/applaut/master-profile"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# What a correct answer for plain_cv() looks like (its lines are numbered from 1).
ANSWER = {
    "name_line": 1, "headline_line": 2, "location": "Berlin, Germany",
    "roles": [
        {"title": "Data Engineer", "company": "Acme GmbH", "location": "Berlin", "start": "2022", "end": "Present",
         "bullets": [[12], [13], [14]], "technologies_line": 15},
        {"title": "Junior Data Engineer", "company": "Beta AG", "location": "Munich", "start": "2020", "end": "2022",
         "bullets": [[18], [19]], "technologies_line": 0},
    ],
    "projects": [{"name": "Weather Lake", "bullets": [[22]], "technologies_line": 0}],
    "skills_lines": [6, 7, 8],
    "education": [{"degree": "M.Sc. Computer Science", "school": "TU Berlin", "period": "2018 – 2020"}],
    "certifications": [],
    "languages": {"english": "", "german": ""},
}


def _lines():
    return read_cv(plain_cv(), "cv.docx")


# ---------------------------------------------------------------- reading the file

def test_reads_a_docx_line_by_line():
    lines = _lines()
    assert lines[0] == "Alex Example" and lines[11].startswith("Built 12 Airflow") and len(lines) == 24


def test_reads_a_pdf():
    from weasyprint import HTML
    pdf = HTML(string="<h1>Alex Example</h1><p>Data Engineer</p><ul><li>Built 12 Airflow pipelines.</li></ul>").write_pdf()
    lines = read_cv(pdf, "CV.PDF")
    assert lines[0] == "Alex Example" and "Built 12 Airflow pipelines." in " ".join(lines)


def test_refuses_what_it_cant_read():
    with pytest.raises(ImportProblem, match=".docx or .pdf"):
        read_cv(b"hello", "cv.txt")
    with pytest.raises(ImportProblem):
        read_cv(b"not a zip", "cv.docx")
    with pytest.raises(ImportProblem, match="couldn't read this PDF"):
        read_cv(b"%PDF-1.4 garbage", "cv.pdf")


# ---------------------------------------------------------------- the answer → a draft

def test_a_good_answer_gives_a_profile_that_saves_once_checked():
    draft, notes = build_profile(_lines(), ANSWER)
    p = draft["personal"]
    assert p["name"] == "Alex Example" and p["email"] == "alex@example.invalid" and p["phone"] == "+49 30 000000"
    assert draft["default_headline"] == "Data Engineer (5 years) with Python, Airflow and dbt"
    assert draft["skills"] == {"Languages": ["Python", "SQL", "Scala"], "Data": ["Apache PySpark", "Airflow", "dbt"],
                               "Cloud": ["Microsoft Azure", "AWS"]}
    acme, beta = draft["experience"]
    assert acme["id"] == "acme_gmbh_data_engineer" and acme["facts"][1].startswith("Rewrote the Spark")
    assert acme["technologies"] == ["Python", "Airflow", "Apache PySpark", "dbt"] and beta["technologies"] == []
    assert draft["projects"][0]["name"] == "Weather Lake"
    assert draft["education"] == [{"period": "2018 – 2020", "degree": "M.Sc. Computer Science", "school": "TU Berlin"}]
    assert not any(n.startswith("Left out") for n in notes)
    validate_profile(draft)  # nothing missing here, so it saves as it is


def test_nothing_in_the_draft_is_new_wording():
    answer = copy.deepcopy(ANSWER)
    answer["roles"][0]["title"] = "Senior Data Engineer"   # not in the CV
    answer["roles"][1]["company"] = "Beta AG (Munich)"      # not written that way
    answer["education"][0]["school"] = "Technische Universität Berlin"
    answer["roles"][0]["bullets"] = [[12], [12], [99], [13]]  # a repeat and a line that isn't there
    draft, notes = build_profile(_lines(), answer)
    acme, beta = draft["experience"]
    assert acme["title"] == "" and beta["company"] == "" and draft["education"][0]["school"] == ""
    assert len(acme["facts"]) == 2  # line 12 once; line 99 dropped
    assert any('"Senior Data Engineer"' in n for n in notes) and any("line 99" in n for n in notes)
    assert any("job title of Acme GmbH" in n for n in notes) and any("company of Junior Data Engineer" in n for n in notes)
    text = str(draft)
    for word in ("Senior", "Technische", "(Munich)"):
        assert word not in text


def test_a_bullet_wrapped_over_lines_is_joined():
    lines = ["Alex Example", "Data Engineer — Acme", "• Built 12 Airflow pipelines loading", "sales data into the data-",
             "warehouse every night."]
    answer = {"name_line": 1, "roles": [{"title": "Data Engineer", "company": "Acme", "bullets": [[3, 4, 5]]}]}
    draft, _ = build_profile(lines, answer)
    assert draft["experience"][0]["facts"] == [
        "Built 12 Airflow pipelines loading sales data into the data-warehouse every night."]


def test_an_empty_answer_says_what_to_fill_in():
    draft, notes = build_profile(_lines(), {"roles": []})
    assert draft["personal"]["name"] == "" and draft["experience"] == []
    joined = " ".join(notes)
    for part in ("personal.name", "skills", "experience", "default_headline"):
        assert part in joined


def test_a_piece_over_two_lines_and_a_skills_heading():
    lines = ["Alex Example", "TECHNICAL SKILLS", "Languages: Python | SQL", "Certified Data Engineer",
             "Academy learning path", "Pipelines | Performance"]
    answer = {"name_line": 1, "skills_lines": [2, 3], "roles": [],
              "certifications": [{"name": "Certified Data Engineer",
                                  "detail": "Academy learning path | Pipelines | Performance"},
                                 {"name": "Certified Data Engineer", "detail": "Academy learning paths"}]}
    draft, notes = build_profile(lines, answer)
    assert draft["skills"] == {"Languages": ["Python", "SQL"]}
    assert draft["certifications"][0]["detail"] == "Academy learning path | Pipelines | Performance"
    assert draft["certifications"][1]["detail"] == ""  # "paths" isn't in the CV
    assert any('"Academy learning paths"' in n for n in notes)


def test_dates_are_not_a_phone_number():
    lines = ["Alex Example", "Acme 03/2020 - 12/2021", "alex@example.invalid"]
    draft, _ = build_profile(lines, {"name_line": 1, "roles": []})
    assert "phone" not in draft["personal"]


def test_prompt_shows_numbered_lines():
    msg = prompts.import_message(read_cv(german_cv(), "cv.docx"))
    assert "1| Alex Example" in msg and "19| • AWS Certified" in msg


# ---------------------------------------------------------------- the API

@pytest.fixture
def importer(make_user, monkeypatch):
    """async importer(engine="applaut_ai") -> auth headers (user id as `importer.user_id`)."""
    monkeypatch.setattr(settings, "applaut_model_hosts", "10.8.0.2")

    async def _make(engine="applaut_ai"):
        user, prof, headers = await make_user()
        async with AsyncSessionLocal() as db:
            await db.execute(update(Profile).where(Profile.id == prof.id).values(
                job_engine=engine, job_engine_changed_at=datetime.now(timezone.utc)))
            await db.commit()
        _make.user_id = user.id
        return headers
    return _make


def _upload(data=None, name="cv.docx"):
    return {"file": (name, data if data is not None else plain_cv(), DOCX)}


async def test_import_review_save_flow(client, importer):
    headers = await importer()
    assert (await client.get(f"{API}/import", headers=headers)).json() is None
    r = await client.post(f"{API}/import", files=_upload(), headers=headers)
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "reading" and r.json()["ahead"] == 0 and r.json()["yaml"] is None

    model = FakeModel(script=[ANSWER])
    served = await worker.run_once(model)
    assert served.outcome == "done" and "12| Built 12 Airflow pipelines" in model.calls[0]

    got = (await client.get(f"{API}/import", headers=headers)).json()
    assert got["status"] == "ready" and "Alex Example" in got["yaml"] and got["notes"]
    assert parse_yaml(got["yaml"])["experience"][0]["company"] == "Acme GmbH"
    assert got["yaml"].startswith("personal:\n  name: Alex Example\n")  # in reading order, not JSONB's
    y = got["yaml"]
    assert y.index("default_headline") < y.index("skills:") < y.index("experience:")
    assert y.index("Languages:") < y.index("Data:") < y.index("Cloud:")  # the CV's order of skill rows

    saved = await client.put(API, json={"yaml": got["yaml"]}, headers=headers)  # the user's review: as it is
    assert saved.status_code == 200, saved.text
    assert (await client.delete(f"{API}/import", headers=headers)).status_code == 204
    assert (await client.get(f"{API}/import", headers=headers)).json() is None
    async with AsyncSessionLocal() as db:
        imp = await db.get(ProfileImport, got["id"])
        audit = await db.scalar(select(AuditLog).where(AuditLog.action == "master_profile.import",
                                                       AuditLog.user_id == importer.user_id))
    assert imp.closed_at is not None and imp.lines is None and imp.draft is None  # the CV's text is gone
    assert audit.after_state == {"file": "cv.docx", "lines": 24}


async def test_import_refusals(client, importer):
    basic = await importer(engine="basic")
    assert (await client.post(f"{API}/import", files=_upload(), headers=basic)).status_code == 409
    headers = await importer()
    assert (await client.post(f"{API}/import", files=_upload(b"hello", "cv.txt"), headers=headers)).status_code == 422
    big = (await client.post(f"{API}/import", files=_upload(b"x" * (5 * 1024 * 1024 + 1)), headers=headers))
    assert big.status_code == 413


async def test_no_model_host_means_no_import(client, importer, monkeypatch):
    headers = await importer()
    monkeypatch.setattr(settings, "applaut_model_hosts", "")
    assert (await client.post(f"{API}/import", files=_upload(), headers=headers)).status_code == 409


async def test_a_failed_import_and_a_new_upload(client, importer):
    headers = await importer()
    await client.post(f"{API}/import", files=_upload(), headers=headers)
    for _ in range(3):  # every try fails: the import shows the error
        await worker.run_once(FakeModel(script=[ModelError("model returned invalid JSON")]))
    got = (await client.get(f"{API}/import", headers=headers)).json()
    assert got["status"] == "failed" and "invalid JSON" in got["error"]
    again = await client.post(f"{API}/import", files=_upload(), headers=headers)
    assert again.status_code == 202 and again.json()["id"] != got["id"]  # a new upload replaces it
    async with AsyncSessionLocal() as db:
        old = await db.get(ProfileImport, got["id"])
    assert old.closed_at is not None and old.lines is None


async def test_cancelling_before_the_writer_starts_leaves_the_queue(client, importer):
    headers = await importer()
    r = await client.post(f"{API}/import", files=_upload(), headers=headers)
    second = await client.post(f"{API}/import", files=_upload(), headers=headers)  # replaces the first
    assert (await client.delete(f"{API}/import", headers=headers)).status_code == 204
    async with AsyncSessionLocal() as db:
        left = list(await db.scalars(select(AIQueueItem).where(
            AIQueueItem.profile_import_id.in_((r.json()["id"], second.json()["id"])))))
    assert left == []
