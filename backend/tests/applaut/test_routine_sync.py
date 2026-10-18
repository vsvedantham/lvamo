"""The sync (docs/applaut/JOB_ENGINES_DESIGN.md §6.4): routine jobs become
private opportunities with an assessment, PDFs are copied once per change,
new jobs land in To review, and nothing leaks to other users."""
import pytest
from sqlalchemy import select

from app.applaut.models.application import Application
from app.applaut.models.audit_log import AuditLog
from app.applaut.models.generated_document import GeneratedDocument
from app.applaut.models.job_assessment import JobAssessment
from app.applaut.models.notification import Notification
from app.applaut.models.opportunity import Opportunity
from app.applaut.models.routine import RoutineConnection, RoutineJob, RoutineSync
from app.applaut.routine import sync as routine_sync
from app.applaut.routine.source import SourceError
from app.db.session import AsyncSessionLocal
from tests.applaut.routine_fake import *  # noqa: F401,F403

API = "/api/v1/applaut"


async def _rows(model, *where):
    async with AsyncSessionLocal() as db:
        return list(await db.scalars(select(model).where(*where)))


@pytest.fixture
async def connected(client, make_user, fake_source, fake_r2, stored_files, routine_env):
    user, profile, headers = await make_user()
    r = await connect_routine(client, headers, fake_source)
    assert r.status_code == 200, r.text
    return user, profile, headers


async def test_sync_creates_jobs_assessments_documents_and_review_queue(connected, client, fake_source, fake_r2, stored_files):
    user, profile, headers = connected
    await fake_source.add_job("acme__data-engineer__berlin", notes="CHECK: recruiting agency (Hays)\nmore",
                              application_url="https://jobs.example.com/apply/1?utm_source=x")
    await fake_source.add_job("beta__analytics-engineer__remote", company="Beta AG", work_mode="remote",
                              docs_status="pending", docs_path=None)
    add_job_files(fake_r2, "acme__data-engineer__berlin")

    record = await routine_sync.sync_user(user.id, "manual")
    assert (record.status, record.jobs_new, record.docs_copied) == ("succeeded", 2, 2), record.problems

    opps = await _rows(Opportunity, Opportunity.owner_user_id == user.id)
    assert {o.external_id for o in opps} == {"acme__data-engineer__berlin", "beta__analytics-engineer__remote"}
    acme = next(o for o in opps if o.external_id.startswith("acme"))
    assert acme.source == "own_routine" and acme.country_code == "DE" and acme.remote_option == "hybrid"
    assert acme.employment_type == "full_time"
    assert acme.description.startswith("# Data Engineer")
    assert acme.application_url == "https://jobs.example.com/apply/1?utm_source=x"

    a = (await _rows(JobAssessment, JobAssessment.opportunity_id == acme.id))[0]
    assert a.engine == "own_routine" and a.match_score == 82 and a.profile_id == profile.id
    assert a.matched_skills == ["Python", "PySpark", "Airflow"] and a.missing_skills == ["Kafka"]
    assert a.flags == ["CHECK: recruiting agency (Hays)"]

    docs = await _rows(GeneratedDocument, GeneratedDocument.opportunity_id == acme.id)
    assert {d.document_type for d in docs} == {"tailored_resume", "cover_letter"}
    for d in docs:
        assert d.engine == "own_routine" and d.content_type == "application/pdf" and d.is_current
        assert d.r2_key == f"applaut/documents/{user.id}/{acme.id}/{d.content_sha256[:8]}/" + (
            "cv.pdf" if d.document_type == "tailored_resume" else "cover_letter.pdf")
        assert stored_files[d.r2_key] == (fake_r2.objects[f"{PREFIX}/acme__data-engineer__berlin/" + d.file_name],
                                          "application/pdf")
    cv = next(d for d in docs if d.document_type == "tailored_resume")
    assert "Built a lakehouse" in cv.content
    cl = next(d for d in docs if d.document_type == "cover_letter")
    assert "I build pipelines." in cl.content

    apps = await _rows(Application, Application.user_id == user.id)
    assert len(apps) == 2 and {a.status for a in apps} == {"pending_review"}

    notes = await _rows(Notification, Notification.user_id == user.id, Notification.type == "routine_sync")
    assert len(notes) == 1 and notes[0].title.startswith("Your routine found 2 new jobs")
    assert await _rows(AuditLog, AuditLog.user_id == user.id, AuditLog.action == "routine.sync")

    # The job shows on the user's Opportunities page with its documents.
    r = await client.get(f"{API}/opportunities?engine=own_routine", headers=headers)
    assert r.status_code == 200, r.text


async def test_second_sync_without_changes_copies_nothing(connected, fake_source, fake_r2, stored_files):
    user, _, _ = connected
    await fake_source.add_job("acme__de__berlin")
    add_job_files(fake_r2, "acme__de__berlin")
    await routine_sync.sync_user(user.id)
    reads = len(fake_r2.reads)

    record = await routine_sync.sync_user(user.id)
    assert (record.rows_read, record.jobs_new, record.jobs_updated, record.docs_copied) == (0, 0, 0, 0)
    assert len(fake_r2.reads) == reads  # no R2 reads at all
    assert len(await _rows(Notification, Notification.user_id == user.id, Notification.type == "routine_sync")) == 1


async def test_changed_pdf_replaces_current_document(connected, fake_source, fake_r2, stored_files):
    user, _, _ = connected
    await fake_source.add_job("acme__de__berlin")
    add_job_files(fake_r2, "acme__de__berlin")
    await routine_sync.sync_user(user.id)

    # The routine re-renders the CV in a later run (same row, new file).
    fake_r2.put(f"{PREFIX}/acme__de__berlin/Test_Person_CV.pdf", b"%PDF-1.7 cv v2")
    await fake_source.add_job("acme__de__berlin", times_seen=2, last_seen_run_id="20261017_2008",
                              last_seen_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    record = await routine_sync.sync_user(user.id)
    assert (record.jobs_updated, record.docs_copied) == (1, 1)

    cvs = await _rows(GeneratedDocument, GeneratedDocument.user_id == user.id,
                      GeneratedDocument.document_type == "tailored_resume")
    assert len(cvs) == 2 and sum(d.is_current for d in cvs) == 1
    assert len(await _rows(Application, Application.user_id == user.id)) == 1  # no second review item
    a = (await _rows(JobAssessment, JobAssessment.user_id == user.id))[0]
    assert a.times_seen == 2


async def test_links_to_shared_posting_with_same_apply_url(connected, make_opportunity, fake_source, fake_r2, stored_files):
    user, _, _ = connected
    shared = await make_opportunity(application_url="https://www.jobs.example.com/apply/77/", description="Basic's text")
    await fake_source.add_job("shared__de__berlin", application_url="https://jobs.example.com/apply/77?utm_medium=feed")
    add_job_files(fake_r2, "shared__de__berlin")
    record = await routine_sync.sync_user(user.id)
    assert record.jobs_new == 1

    assert await _rows(Opportunity, Opportunity.owner_user_id == user.id) == []  # not duplicated
    link = (await _rows(RoutineJob, RoutineJob.user_id == user.id))[0]
    assert link.opportunity_id == shared.id and link.linked_to_shared
    assert (await _rows(JobAssessment, JobAssessment.opportunity_id == shared.id))[0].user_id == user.id
    assert len(await _rows(GeneratedDocument, GeneratedDocument.opportunity_id == shared.id)) == 2
    refreshed = (await _rows(Opportunity, Opportunity.id == shared.id))[0]
    assert refreshed.description == "Basic's text"  # the shared posting isn't rewritten


async def test_private_jobs_never_leak(connected, client, make_user, fake_source, fake_r2, stored_files):
    user, _, _ = connected
    await fake_source.add_job("acme__de__berlin")
    add_job_files(fake_r2, "acme__de__berlin")
    await routine_sync.sync_user(user.id)
    opp = (await _rows(Opportunity, Opportunity.owner_user_id == user.id))[0]
    doc = (await _rows(GeneratedDocument, GeneratedDocument.opportunity_id == opp.id))[0]

    _, _, other = await make_user()
    assert (await client.get(f"{API}/opportunities/{opp.id}", headers=other)).status_code == 404
    listed = (await client.get(f"{API}/opportunities", headers=other)).json()
    items = listed["items"] if isinstance(listed, dict) else listed
    assert str(opp.id) not in {str(o["id"]) for o in items}
    assert (await client.get(f"{API}/documents/{doc.id}/file", headers=other)).status_code == 404


async def test_removed_rows_are_kept_and_marked(connected, fake_source, fake_r2, stored_files):
    user, _, _ = connected
    await fake_source.add_job("gone__de__berlin", docs_status="pending")
    await routine_sync.sync_user(user.id)
    await fake_source.delete_job("gone__de__berlin")
    record = await routine_sync.sync_user(user.id)
    assert record.jobs_removed == 1
    job = (await _rows(RoutineJob, RoutineJob.user_id == user.id))[0]
    assert job.removed_at is not None
    assert len(await _rows(Opportunity, Opportunity.id == job.opportunity_id)) == 1


async def test_bad_files_skipped_and_reported(connected, fake_source, fake_r2, stored_files):
    user, _, _ = connected
    await fake_source.add_job("bad__de__berlin")
    add_job_files(fake_r2, "bad__de__berlin", cv=b"<html>not a pdf</html>", cover=b"%PDF-" + b"x" * 5_000_001)
    record = await routine_sync.sync_user(user.id)
    assert record.status == "partial" and record.docs_copied == 0 and record.docs_skipped == 2
    assert any("isn't a PDF" in p for p in record.problems) and any("larger than 5 MB" in p for p in record.problems)
    assert stored_files == {}
    # Still a job, with its assessment, and retried next time.
    assert len(await _rows(Opportunity, Opportunity.owner_user_id == user.id)) == 1
    job = (await _rows(RoutineJob, RoutineJob.user_id == user.id))[0]
    assert job.cv_etag is None


async def test_failed_documents_reason_reported(connected, fake_source, fake_r2, stored_files):
    user, _, _ = connected
    await fake_source.add_job("f__de__berlin", docs_status="failed", docs_error="render: CV is 3 pages")
    record = await routine_sync.sync_user(user.id)
    assert record.jobs_new == 1 and any("CV is 3 pages" in p for p in record.problems)


async def test_untrusted_urls_dropped(connected, fake_source, fake_r2, stored_files):
    user, _, _ = connected
    await fake_source.add_job("x__de__berlin", jd_url="javascript:alert(1)", application_url="ftp://x/y", docs_status="pending")
    await routine_sync.sync_user(user.id)
    opp = (await _rows(Opportunity, Opportunity.owner_user_id == user.id))[0]
    assert opp.application_url is None


async def test_source_failure_recorded(connected, fake_source, fake_r2, stored_files):
    user, _, _ = connected
    await fake_source.drop()  # the database is gone (role and schema)
    with pytest.raises(SourceError):
        await routine_sync.sync_user(user.id)
    record = (await _rows(RoutineSync, RoutineSync.user_id == user.id))[0]
    assert record.status == "failed" and record.error
    conn = (await _rows(RoutineConnection, RoutineConnection.user_id == user.id))[0]
    assert conn.status == "error" and conn.consecutive_failures == 1
    notes = await _rows(Notification, Notification.user_id == user.id)
    assert {n.type for n in notes} >= {"routine_connection", "routine_sync"}
    await fake_source.create()  # so the fixture's drop succeeds


async def test_sync_now_rate_limited(connected, client, fake_source, fake_r2, stored_files):
    _, _, headers = connected
    r = await client.post(f"{API}/job-engine/routine/sync-now", headers=headers)
    assert r.status_code == 200 and r.json()["queued"] is True, r.text
    r = await client.post(f"{API}/job-engine/routine/sync-now", headers=headers)
    assert r.status_code == 429 and "Retry-After" in r.headers


async def test_sync_copies_run_tracker_rows(connected, fake_source, fake_r2, stored_files):
    from datetime import datetime, timedelta, timezone
    from app.applaut.models.routine import RoutineRun
    user, _, _ = connected
    started = datetime.now(timezone.utc) - timedelta(hours=5)
    await fake_source.add_run("20261018_0809", started, status="succeeded", finished_at=started + timedelta(minutes=12),
                              current_step="summary", jobs_new=1, docs_done=1, docs_failed=0,
                              sources_failed="jobs.sap.com: blocked (403)")
    await routine_sync.sync_user(user.id)
    runs = await _rows(RoutineRun, RoutineRun.user_id == user.id)
    assert [(r.run_id, r.outcome, r.jobs_new) for r in runs] == [("20261018_0809", "problems", 1)]
    assert runs[0].notified_at is None  # a sync copies; only the status check notifies
