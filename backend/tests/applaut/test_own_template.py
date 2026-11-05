"""The user's own CV template (APPLAUT_AI_V2_PLAN.md §5): a .docx made into a
template from the model's line labels, proven by a round trip, then filled per
job from the master profile. Layout and every other line stay as uploaded."""
import copy
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update

from app.applaut.ai import handlers, worker
from app.applaut.ai.provider import ModelError
from app.applaut.documents import own_template as ot
from app.applaut.documents.render import OwnCv, build_documents, rerender_cv
from app.applaut.models.audit_log import AuditLog
from app.applaut.models.cv_template import CvTemplate
from app.applaut.models.generated_document import GeneratedDocument
from app.applaut.models.master_profile import MasterProfile
from app.applaut.models.profile import Profile
from app.config import settings
from app.db.session import AsyncSessionLocal
from tests.applaut.cv_docx import GERMAN_LABELS, LABELS, TABLE_LABELS, german_cv, plain_cv, table_cv
from tests.applaut.test_ai_engine import FakeModel, _enqueue, _isolated_queue, _job, _raw  # noqa: F401
from tests.applaut.test_documents import JOB, PROFILE, TAILORED, WRITTEN, as_answer, profile

API = "/api/v1/applaut/cv-template"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SPARK = PROFILE["experience"][0]["facts"][1]


def _answer(labels) -> dict:
    """The model's answer for a CV whose lines all have text."""
    return {"labels": {str(n): lab for n, lab in enumerate(labels)}}


def _own(src=None, labels=LABELS) -> OwnCv:
    src = src or plain_cv()
    built = ot.build(src, list(labels))
    return OwnCv("t1", built.template, built.slots, ot.to_pdf(src)[1])


# ---------------------------------------------------------------- building

def test_the_template_gives_the_upload_back():
    src = plain_cv()
    built = ot.build(src, list(LABELS))
    assert ot.round_trip(src, built) == []
    s = built.slots
    assert s.headline and [r.label for r in s.rows] == ["Languages", "Data", "Cloud"]
    assert [len(b.original_bullets) for b in s.blocks] == [3, 2, 1] and s.blocks[0].tech_key
    assert ot.match_entries(s, profile()) == {0: "acme", 1: "beta", 2: "side"}
    assert ot.match_rows(s, profile()) == {"r0": "Languages", "r1": "Data", "r2": "Cloud"}


@pytest.mark.parametrize("make, labels", [(table_cv, TABLE_LABELS), (german_cv, GERMAN_LABELS)])
def test_tables_and_typed_bullets(make, labels):
    src = make()
    built = ot.build(src, list(labels))
    assert ot.round_trip(src, built) == []
    assert ot.match_entries(built.slots, profile()) == {0: "acme", 1: "beta"}
    docs = build_documents(profile(), JOB, {**WRITTEN, **as_answer(TAILORED)}, own=OwnCv("t", built.template,
                                                                                         built.slots, 1))
    assert TAILORED[0]["text"] in docs.cv.text and "M.Sc. Informatik, TU Berlin" in docs.cv.text
    if make is german_cv:  # the typed "•" stays in front of each new bullet; the certificate line stays
        assert f"• {TAILORED[0]['text']}" in docs.cv.text
        assert "• AWS Certified Data Engineer – Associate (2024)" in docs.cv.text


def test_labels_are_made_consistent():
    labels = list(LABELS)
    labels[3] = "headline"   # a second headline (and a long one): other
    labels[23] = "bullet"    # a bullet after the Education heading, outside any role: other
    built = ot.build(plain_cv(), labels)
    assert built.labels[3] == "other" and built.labels[23] == "other"
    assert ot.round_trip(plain_cv(), built) == []


def test_bullets_split_by_another_line_are_refused():
    labels = LABELS[:13] + ["other"] + LABELS[13:]  # "(Team of four)" between two bullets, then the rest
    labels[14] = "bullet"
    with pytest.raises(ot.TemplateError) as exc:
        ot.build(plain_cv(extra_bullet_gap=True), labels)
    assert "aren't one list" in exc.value.problems[0]


def test_template_marks_in_the_text_are_refused():
    from docx import Document
    import io
    d = Document(io.BytesIO(plain_cv()))
    d.paragraphs[3].text = "I write {{ curly }} braces."
    out = io.BytesIO()
    d.save(out)
    with pytest.raises(ot.TemplateError):
        ot.build(out.getvalue(), list(LABELS))


def test_unknown_fonts_are_reported():
    from docx import Document
    import io
    d = Document(io.BytesIO(plain_cv()))
    d.paragraphs[0].runs[0].font.name = "Garamond Premier"
    out = io.BytesIO()
    d.save(out)
    assert {"font": "Garamond Premier", "shown_as": "a similar font"} in ot.font_report(out.getvalue())
    assert ot.font_report(plain_cv()) == []  # Calibri and Cambria have metric twins


# ---------------------------------------------------------------- filling

def test_a_job_cv_fills_only_the_slots():
    own = _own()
    docs = build_documents(profile(), JOB, {**WRITTEN, **as_answer(TAILORED)}, own=own)
    text = docs.cv.text
    assert WRITTEN["headline"] in text and "Data Engineer (5 years) with Python, Airflow and dbt" not in text
    assert TAILORED[0]["text"] in text and "Introduced dbt models and tests for the finance marts." in text
    for kept in ("Alex Example", "A short profile paragraph", "M.Sc. Computer Science — TU Berlin, 2018 – 2020",
                 "Data Engineer — Acme GmbH, Berlin", "2020 – 2022"):
        assert kept in text
    assert docs.cv.pdf.startswith(b"%PDF") and docs.cv.pages <= own.pages
    assert docs.cv_details["template"] == {"id": "t1"}
    assert docs.cover_letter.pdf.startswith(b"%PDF")  # the letter stays standard


def test_the_cv_keeps_to_the_uploads_pages():
    p = profile()
    long = "Designed and ran the {} for the finance, sales and marketing teams across three countries and " \
           "two data centres, with documentation, alerting and a weekly review of every failed run."
    p["experience"][0]["facts"] = [long.format(f"pipeline number {n}") for n in range(1, 13)]
    p["experience"][0]["cv_bullets"] = "1-12"
    own = _own()
    written = {**WRITTEN, "bullets": None}
    docs = build_documents(p, JOB, written, own=own, check=False)
    assert docs.cv.pages == own.pages and docs.bullets_dropped > 0


def test_switching_a_bullet_rebuilds_with_the_same_template():
    own = _own()
    docs = build_documents(profile(), JOB, {**WRITTEN, **as_answer(TAILORED)}, own=own)
    details = copy.deepcopy(docs.cv_details)
    next(b for e in details["entries"] for b in e["bullets"] if b["id"] == "acme.2")["use"] = "original"
    cv, _ = rerender_cv(details, own)
    assert SPARK in cv.text and TAILORED[0]["text"] not in cv.text and "M.Sc. Computer Science" in cv.text
    with pytest.raises(Exception):
        rerender_cv(details)  # the template is needed


# ---------------------------------------------------------------- API + queue

@pytest.fixture
def files(_isolated_queue, monkeypatch):
    """R2 in memory: what store_file stored, fetch_file gives back."""
    async def fake_fetch(key):
        return _isolated_queue[key]
    monkeypatch.setattr(handlers, "fetch_file", fake_fetch)
    monkeypatch.setattr(settings, "applaut_model_hosts", "10.8.0.2")
    return _isolated_queue


async def _ai_user(make_user, engine="applaut_ai"):
    user, prof, headers = await make_user()
    async with AsyncSessionLocal() as db:
        await db.execute(update(Profile).where(Profile.id == prof.id).values(
            job_engine=engine, job_engine_changed_at=datetime.now(timezone.utc)))
        db.add(MasterProfile(user_id=user.id, data=copy.deepcopy(PROFILE)))
        await db.commit()
    return user, prof, headers


def _upload(data=None, name="my_cv.docx", ctype=DOCX):
    return {"file": (name, data if data is not None else plain_cv(), ctype)}


async def test_upload_read_use_and_generate(client, make_user, make_opportunity, files):
    user, prof, headers = await _ai_user(make_user)
    r = await client.post(API, files=_upload(), headers=headers)
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "reading" and r.json()["ahead"] == 0
    tid = r.json()["id"]

    model = FakeModel(script=[_answer(LABELS)])
    assert (await worker.run_once(model)).outcome == "done"
    assert "[List Bullet] Built 12 Airflow pipelines" in model.calls[0]
    latest = (await client.get(API, headers=headers)).json()["latest"]
    assert latest["status"] == "ready" and latest["can_use"] and latest["pages"] == 1
    assert [x["entry"] for x in latest["report"]["roles"]] == [
        "Data Engineer at Acme GmbH", "Junior Data Engineer at Beta AG", "Project: Weather Lake"]
    assert latest["report"]["differences"] == [] and latest["report"]["fonts"] == []
    assert files[f"applaut/templates/{user.id}/{tid}/rebuilt.pdf"].startswith(b"%PDF")

    r = await client.post(f"{API}/{tid}/use", headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "active"
    async with AsyncSessionLocal() as db:
        audit = await db.scalar(select(AuditLog).where(AuditLog.action == "cv_template.use", AuditLog.entity_id == tid))
    assert audit.after_state == {"template_id": tid, "file_name": "my_cv.docx"}

    opp = await _job(make_opportunity)
    a = await _raw(user, prof, opp)
    await _enqueue("write_docs", a)
    await worker.run_once(FakeModel(written={**WRITTEN, **as_answer(TAILORED)}))
    async with AsyncSessionLocal() as db:
        cv = await db.scalar(select(GeneratedDocument).where(GeneratedDocument.opportunity_id == opp.id,
                                                             GeneratedDocument.document_type == "tailored_resume"))
    assert "M.Sc. Computer Science — TU Berlin" in cv.content and cv.details["template"] == {"id": tid}

    switched = await client.post(f"/api/v1/applaut/documents/{cv.id}/bullets/acme.2/use",
                                 json={"version": "original"}, headers=headers)
    assert switched.status_code == 200, switched.text
    async with AsyncSessionLocal() as db:
        new = await db.scalar(select(GeneratedDocument).where(GeneratedDocument.opportunity_id == opp.id,
                                                              GeneratedDocument.document_type == "tailored_resume",
                                                              GeneratedDocument.is_current == True))  # noqa: E712
    assert SPARK in new.content and "M.Sc. Computer Science" in new.content

    assert (await client.delete(f"{API}/{tid}", headers=headers)).status_code == 204
    state = (await client.get(API, headers=headers)).json()
    assert state == {"active": None, "latest": None}
    async with AsyncSessionLocal() as db:
        assert await db.scalar(select(AuditLog).where(AuditLog.action == "cv_template.stop", AuditLog.entity_id == tid))


async def test_a_template_that_doesnt_round_trip_cant_be_used(client, make_user, files, monkeypatch):
    _, _, headers = await _ai_user(make_user)
    tid = (await client.post(API, files=_upload(), headers=headers)).json()["id"]
    monkeypatch.setattr(ot, "round_trip", lambda src, built: ['line 3: "a" came back as "b"'])
    await worker.run_once(FakeModel(script=[_answer(LABELS)]))
    latest = (await client.get(API, headers=headers)).json()["latest"]
    assert latest["status"] == "ready" and not latest["can_use"]
    assert (await client.post(f"{API}/{tid}/use", headers=headers)).status_code == 409


async def test_a_new_upload_replaces_one_not_switched_on(client, make_user, files):
    _, _, headers = await _ai_user(make_user)
    first = (await client.post(API, files=_upload(), headers=headers)).json()["id"]
    second = (await client.post(API, files=_upload(), headers=headers)).json()["id"]
    assert (await client.get(API, headers=headers)).json()["latest"]["id"] == second
    async with AsyncSessionLocal() as db:
        assert (await db.get(CvTemplate, first)).status == "discarded"
    assert (await worker.run_once(FakeModel(script=[_answer(LABELS)]))).outcome == "done"  # only the second
    assert (await worker.run_once(FakeModel())) is None


async def test_failures_reach_the_user(client, make_user, files):
    _, _, headers = await _ai_user(make_user)
    await client.post(API, files=_upload(plain_cv(extra_bullet_gap=True)), headers=headers)
    labels = LABELS[:13] + ["other"] + LABELS[13:]
    labels[14] = "bullet"
    await worker.run_once(FakeModel(script=[_answer(labels)]))
    latest = (await client.get(API, headers=headers)).json()["latest"]
    assert latest["status"] == "failed" and "aren't one list" in latest["error"]

    await client.post(API, files=_upload(), headers=headers)
    for _ in range(3):  # the model keeps labelling the wrong number of lines
        await worker.run_once(FakeModel(script=[{"labels": {"0": "name"}}]))
    latest = (await client.get(API, headers=headers)).json()["latest"]
    assert latest["status"] == "failed" and "labelled 1 of 24" in latest["error"]


async def test_upload_refusals(client, make_user, files):
    _, _, headers = await _ai_user(make_user)
    pdf = await client.post(API, files=_upload(b"%PDF-1.7", "cv.pdf", "application/pdf"), headers=headers)
    assert pdf.status_code == 415 and ".docx" in pdf.json()["detail"]
    assert (await client.post(API, files=_upload(b"hello", "cv.txt", "text/plain"), headers=headers)).status_code == 415
    assert (await client.post(API, files=_upload(b"not a zip"), headers=headers)).status_code == 422
    _, _, basic = await _ai_user(make_user, engine="basic")
    assert (await client.post(API, files=_upload(), headers=basic)).status_code == 409
    _, _, stranger = await _ai_user(make_user)
    tid = (await client.post(API, files=_upload(), headers=headers)).json()["id"]
    assert (await client.post(f"{API}/{tid}/use", headers=stranger)).status_code == 404
    assert (await client.delete(f"{API}/{tid}", headers=stranger)).status_code == 404
