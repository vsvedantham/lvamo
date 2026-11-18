"""Settings → Nightly runs: each Applaut AI night as it went for this user."""
from datetime import date

from sqlalchemy import delete

from app.applaut.models.ai_queue import AIQueueItem, NightRun
from app.applaut.models.job_assessment import JobAssessment
from app.config import settings
from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal
from tests.applaut.test_ai_engine import ai_user  # noqa: F401  (fixture)

API = "/api/v1/applaut/job-engine/ai/runs"


def _auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def _assessment(db, user, profile, opp, score):
    a = JobAssessment(user_id=user.id, profile_id=profile.id, opportunity_id=opp.id, engine="applaut_ai",
                      status="scored" if score is not None else "raw", match_score=score, docs_status="not_needed",
                      matched_skills=[], missing_skills=[], flags=[], raw={})
    db.add(a)
    await db.flush()
    return a


async def test_nightly_runs_show_each_night_for_this_user(client, ai_user, make_user, make_opportunity):  # noqa: F811
    user, profile = await ai_user()
    other, _ = await ai_user()
    _, _, headers = await make_user()
    me = str(user.id)
    opps = [await make_opportunity(title=f"Job {i}") for i in range(4)]
    try:
        async with AsyncSessionLocal() as db:
            first = NightRun(run_date=date(1990, 1, 1), users=2, jobs_found=45, jobs_queued=3,
                             stats={me: {"matched": 41, "new": 41, "queued": 3, "waiting": 38},
                                    str(other.id): {"matched": 1, "new": 1, "queued": 1, "waiting": 0}})
            second = NightRun(run_date=date(1990, 1, 2), users=2, jobs_found=142, jobs_queued=1,
                              stats={me: {"matched": 30, "new": 4, "no_description": 2, "queued": 1, "waiting": 37},
                                     "_pool": {"postings": 142, "new": 97, "closed": 5,
                                               "by_source": {"bundesagentur": 85, "arbeitnow": 28}}})
            db.add_all([first, second])
            await db.flush()
            good = await _assessment(db, user, profile, opps[0], settings.applaut_ai_doc_threshold + 5)
            low = await _assessment(db, user, profile, opps[1], 40)
            broken = await _assessment(db, user, profile, opps[2], None)
            later = await _assessment(db, user, profile, opps[3], None)
            for a, kind, status, night in ((good, "score_job", "done", first), (low, "score_job", "done", first),
                                           (broken, "score_job", "failed", first), (good, "write_docs", "done", first),
                                           (later, "score_job", "pending", second)):
                db.add(AIQueueItem(kind=kind, night_run_id=night.id, user_id=user.id, profile_id=profile.id,
                                   assessment_id=a.id, status=status))
            await db.commit()

        body = (await client.get(API, headers=_auth(user))).json()
        assert body["totals"] == {"nights": 2, "new": 45, "scored": 2, "good": 1, "docs_done": 1}
        newest, oldest = body["nights"]
        assert newest["run_date"] == "1990-01-02" and newest["postings_checked"] == 142
        assert newest["by_source"] == {"bundesagentur": 85, "arbeitnow": 28} and newest["closed"] == 5
        assert (newest["new"], newest["no_description"], newest["queued"], newest["scoring_left"]) == (4, 2, 1, 1)
        assert (oldest["matched"], oldest["scored"], oldest["scoring_failed"], oldest["good"], oldest["docs_done"]) == \
            (41, 2, 1, 1, 1)
        assert oldest["closed"] is None and body["doc_threshold"] == settings.applaut_ai_doc_threshold

        theirs = (await client.get(API, headers=_auth(other))).json()
        assert theirs["totals"]["nights"] == 1 and theirs["nights"][0]["scored"] == 0  # only their own work
        nobody = (await client.get(API, headers=headers)).json()
        assert nobody["nights"] == [] and nobody["totals"]["nights"] == 0
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(NightRun).where(NightRun.run_date < date(1991, 1, 1)))
            await db.commit()

