"""Job discovery (2026-11-18): related titles and skill-led titles, no student
roles, the Bundesagentur and Arbeitnow searches, descriptions filled from the
source, one listing per job, stale postings dropped, closed jobs expiring."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.applaut.discovery import engine
from app.applaut.discovery.base import JobListing
from app.applaut.discovery.location import dedupe_key, matches_roles, resolve_country, wanted_place
from app.applaut.discovery.search import arbeitnow, bundesagentur, personio_page
from app.applaut.models.opportunity import Opportunity
from app.db.session import AsyncSessionLocal
from tests.applaut.conftest import TEST_SOURCE

NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
ROLES = ["Data Engineer"]
SKILLS = ["Python", "Databricks", "Apache PySpark", "Airflow"]


def _listing(i, title="Data Engineer", company="Acme GmbH", source=TEST_SOURCE, **kw):
    return JobListing(source=source, external_id=f"t{i}", title=title, company_name=company,
                      application_url=f"https://example.invalid/{i}", country_code="DE", **kw)


# ---------------------------------------------------------------- titles

def test_related_titles_and_skill_led_titles_match():
    for title in ("Senior Data Engineer (m/w/d)", "Consultant Data Engineering (all genders)", "DWH Developer",
                  "Analytics Engineer", "Databricks Developer", "PySpark Entwickler (m/w/d)"):
        assert matches_roles(title, ROLES, SKILLS + ["PySpark"]), title
    for title in ("Databricks Account Executive", "Python Developer", "Pastry Chef", "Internal Tools Engineer"):
        assert not matches_roles(title, ROLES, SKILLS), title  # no role word, or a skill every job names


def test_student_and_trainee_roles_never_match_unless_asked_for():
    for title in ("Werkstudent Data Engineering (m/w/d)", "Working Student - Content Data Engineer",
                  "Data Engineer Intern", "Praktikum Data Engineering", "Masterarbeit Data Engineering"):
        assert not matches_roles(title, ROLES, SKILLS), title
    assert matches_roles("International Data Engineer", ROLES)
    assert matches_roles("Werkstudent Data Engineering", ["Werkstudent Data Engineering"])


def test_places():
    assert resolve_country("Manchester, UK") == "GB" and resolve_country("Wien") == "AT"
    assert resolve_country("North Macedonia - Remote") == "MK"
    assert wanted_place("DE", "onsite", ["DE"]) and wanted_place(None, "remote", ["DE"])
    assert not wanted_place(None, "onsite", ["DE"]) and not wanted_place("GB", "remote", ["DE"])


def test_one_key_per_job_whatever_the_site_writes():
    assert dedupe_key("MaibornWolff GmbH", "Senior Data Engineer (m/w/d)") == \
        dedupe_key("maibornwolff", "Senior Data Engineer (m/w/d)") == ("maibornwolff", "senior data engineer")
    assert dedupe_key("Acme SE & Co. KG", "Data Engineer*in (w/m/d)") == dedupe_key("ACME", "Data Engineer")
    assert dedupe_key("Acme", "Data Engineer") != dedupe_key("Acme", "Senior Data Engineer")


# ---------------------------------------------------------------- one listing per job, no stale postings

def test_prepare_drops_old_postings_and_merges_the_same_job():
    listings = [
        _listing(1, "Senior Data Engineer (m/w/d)", "Maibornwolff", location_raw="Berlin", posted_at=NOW),
        _listing(2, "Senior Data Engineer (m/w/d)", "Maibornwolff", location_raw="Hamburg", posted_at=NOW),
        _listing(3, "Senior Data Engineer", "MaibornWolff GmbH", source=bundesagentur.SOURCE,
                 location_raw="München", posted_at=NOW),
        _listing(4, "Data Engineer", "Old AG", posted_at=NOW - timedelta(days=engine.MAX_AGE_DAYS + 1)),
        _listing(5, "Data Engineer", "Undated AG"),
    ]
    out = engine.prepare(listings, now=NOW)
    assert [x.external_id for x in out] == ["t1", "t5"]  # the employer's own board wins; t4 is too old
    assert out[0].location_raw == "Berlin / Hamburg / München"
    assert [a["external_id"] for a in out[0].raw_data["also_posted"]] == ["t2", "t3"]


# ---------------------------------------------------------------- the job-board searches

BA_JOB = {"stellenangebotsTitel": "Data Engineer (m/w/d)", "firma": "ELA Container GmbH",
          "referenznummer": "12288-5002848046-S", "datumErsteVeroeffentlichung": "2026-11-17",
          "stellenlokationen": [{"adresse": {"ort": "Haren (Ems)", "land": "DEUTSCHLAND"}}],
          "homeofficemoeglich": True, "externeURL": "https://example.invalid/apply"}


async def test_bundesagentur_search_keeps_matching_postings_in_germany(monkeypatch):
    vienna = {**BA_JOB, "referenznummer": "x-2", "stellenlokationen": [{"adresse": {"ort": "Wien", "land": "ÖSTERREICH"}}]}
    chef = {**BA_JOB, "referenznummer": "x-3", "stellenangebotsTitel": "Koch (m/w/d)"}
    terms = []

    async def fake_get(client, url, params=None, **kw):
        terms.append(params["was"])
        assert params["veroeffentlichtseit"] == 60 and params["arbeitszeit"] == "vz"
        return {"ergebnisliste": [BA_JOB, vienna, chef] if params["was"] == "data engineer" else [BA_JOB]}
    monkeypatch.setattr(bundesagentur, "get_json", fake_get)

    found = await bundesagentur.search(["DE"], ROLES, ["Python", "Databricks"])
    assert [x.external_id for x in found] == ["12288-5002848046-S"]  # once, however many terms found it
    x = found[0]
    assert (x.company_name, x.location_raw, x.country_code, x.remote_option) == \
        ("ELA Container GmbH", "Haren (Ems)", "DE", "hybrid")
    assert x.application_url.endswith("/jobdetail/12288-5002848046-S") and x.description is None
    assert "databricks" in terms and "python" not in terms  # skill-led terms, but not the generic ones
    assert await bundesagentur.search(["NL"], ROLES) == []


async def test_arbeitnow_keeps_german_and_remote_jobs_until_too_old(monkeypatch):
    new, old = int(NOW.timestamp()), int((NOW - timedelta(days=61)).timestamp())
    page = [
        {"slug": "a", "title": "Data Engineer", "company_name": "A", "location": "Gescher", "remote": False, "created_at": new},
        {"slug": "b", "title": "Data Engineer", "company_name": "B", "location": "London", "remote": False, "created_at": new},
        {"slug": "c", "title": "Senior Data Engineer", "company_name": "C", "location": "", "remote": True, "created_at": new},
        {"slug": "d", "title": "Recruiter", "company_name": "D", "location": "Berlin", "remote": False, "created_at": new},
    ]
    pages = {1: page, 2: [{**page[0], "slug": "e", "created_at": old}]}
    calls = []

    async def fake_get(client, url, params=None, **kw):
        calls.append(params["page"])
        return {"data": pages.get(params["page"], [])}

    async def no_pause(_):
        return None
    monkeypatch.setattr(arbeitnow, "get_json", fake_get)
    monkeypatch.setattr(arbeitnow.asyncio, "sleep", no_pause)
    found = await arbeitnow.search(["DE"], ROLES)
    assert [(x.external_id, x.country_code) for x in found] == [("a", "DE"), ("c", None)]
    assert calls == [1, 2]  # page 2 is all older than the window: done


def test_personio_page_description():
    page = ('<html><script type="application/ld+json">{"@type": "BreadcrumbList"}</script>'
            '<script type="application/ld+json">{"@type": "JobPosting", "title": "Data Engineer", '
            '"description": "&lt;p&gt;Build pipelines with Spark.&lt;/p&gt;"}</script></html>')
    assert personio_page.description_from_page(page) == "<p>Build pipelines with Spark.</p>"
    assert personio_page.description_from_page("<html></html>") is None


# ---------------------------------------------------------------- storing, last seen, closing

async def test_store_fills_descriptions_marks_seen_and_reopens(monkeypatch):
    async def describe(client, listing):
        return f"Full posting for {listing.title}."
    monkeypatch.setitem(engine.DESCRIBERS, TEST_SOURCE, describe)
    async with AsyncSessionLocal() as db:
        db.add(Opportunity(source=TEST_SOURCE, external_id="t1", title="Data Engineer", company_name="Acme",
                           is_active=False, raw_data={}, last_seen_at=NOW - timedelta(days=10)))
        await db.commit()
        new = await engine.store_listings([_listing(1), _listing(2, description="Given."), _listing(3, "BI Developer")], db)
        rows = {o.external_id: o for o in await db.scalars(select(Opportunity).where(Opportunity.source == TEST_SOURCE))}
    assert new == 2
    assert rows["t1"].is_active and rows["t1"].last_seen_at > NOW  # seen again: open again
    assert rows["t2"].description == "Given." and rows["t3"].description == "Full posting for BI Developer."
    assert all(o.last_seen_at for o in rows.values())


async def test_jobs_unseen_for_three_days_close(make_user, make_opportunity):
    user, _, _ = await make_user()
    now = datetime.now(timezone.utc)
    gone = await make_opportunity(external_id="gone", last_seen_at=now - timedelta(days=4))
    fresh = await make_opportunity(external_id="fresh", last_seen_at=now - timedelta(days=1))
    own = await make_opportunity(owner=user, source=TEST_SOURCE, external_id="own", last_seen_at=now - timedelta(days=9))
    async with AsyncSessionLocal() as db:
        assert await engine.expire_unseen(db, sources={TEST_SOURCE}) == 1
        state = {o.external_id: o.is_active for o in await db.scalars(
            select(Opportunity).where(Opportunity.id.in_([gone.id, fresh.id, own.id])))}
    assert state == {"gone": False, "fresh": True, "own": True}  # a user's own job never expires here
