"""Applaut AI document engine: master profile validation, code tailoring,
fact guard, and PDF rendering with the standard (routine) template."""
import copy

import pytest

from app.applaut.documents.fact_guard import check_bullet, check_written
from app.applaut.documents.letter import JobInfo, build_letter, company_display
from app.applaut.documents.profile_schema import ProfileError, parse_yaml, to_yaml, validate_profile
from app.applaut.documents.render import DocumentError, _cv_context, _cv_text, build_documents, render_html, sample_documents
from app.applaut.documents.tailor import (
    apply_picks, drop_one, job_skills, mentioned, order_skill_rows, pick_entries, skill_names,
)

PROFILE = {
    "personal": {"name": "Alex Example", "location": "Berlin, Germany", "email": "alex@example.invalid",
                 "work_authorization": "I hold an EU Blue Card.", "availability": "I am available from January.",
                 "work_authorization_short": "Blue Card", "availability_short": "From January"},
    "default_headline": "Data Engineer (5 years) with expertise in Spark and Azure",
    "default_cover_tagline": "Data Engineer | Spark · Azure · SQL",
    "years_experience": "5",
    "skills": {"Languages": ["Python", "SQL", "Scala"], "Data": ["Apache PySpark", "Airflow", "dbt"],
               "Cloud": ["Microsoft Azure", "AWS"]},
    "additional_skills": ["Data Validation"],
    "skill_aliases": {"Apache PySpark": ["Spark", "PySpark"], "Microsoft Azure": ["Azure"]},
    "experience": [
        {"id": "acme", "title": "Data Engineer", "company": "Acme GmbH", "location": "Berlin", "start": "2022",
         "end": "Present", "technologies": ["Python", "Airflow", "Apache PySpark", "dbt"],
         "facts": ["Built 12 Airflow pipelines loading sales data into the warehouse.",
                   "Rewrote the Spark billing job, cutting runtime from 6 hours to 40 minutes.",
                   "Introduced dbt models and tests for the finance marts.",
                   "Mentored 2 junior engineers.",
                   "Ran the weekly on-call rotation for the data platform."]},
        {"id": "beta", "title": "Junior Data Engineer", "company": "Beta AG", "location": "Hamburg", "start": "2020",
         "end": "2022", "technologies": ["SQL", "Microsoft Azure"],
         "facts": ["Migrated 30 SQL Server reports to Azure.", "Wrote SQL data validation checks for monthly closes."]},
    ],
    "projects": [{"id": "side", "name": "Weather Lake", "subtitle": "Personal project", "start": "2023", "end": "2024",
                  "technologies": ["Python", "AWS"], "facts": ["Collected 3 years of weather data on AWS S3."]}],
    "certifications": [{"name": "Databricks Data Engineer Associate", "status": "2024"}],
    "education": [{"degree": "BSc Computer Science", "school": "TU Example", "period": "2016 – 2020"}],
    "languages": {"english": "C1", "german": "B2", "german_max_required": "B2"},
}

JOB = JobInfo(title="Senior Data Engineer (Spark)", company="Gamma SE", location="Munich, Germany",
              description="We build our lakehouse on Spark and Azure. You know Python and SQL. "
                          "Spark tuning is a must. Nice: Airflow. Team of 8 engineers.")

WRITTEN = {
    "headline": "Data Engineer (5 years) focused on Spark performance and Azure",
    "paragraphs": [
        "Gamma SE is building its lakehouse on Spark and Azure, and this role owns the performance of those "
        "pipelines. That is the work I have done for the last years: making Spark jobs fast and reliable on "
        "Azure for analytics teams that depend on them.",
        "At Acme GmbH I rewrote the Spark billing job and cut its runtime from 6 hours to 40 minutes. I built 12 "
        "Airflow pipelines that load sales data into the warehouse and introduced dbt models and tests for the "
        "finance marts, so analysts trust the numbers they report.",
        "Before that, at Beta AG, I migrated 30 SQL Server reports to Azure and wrote SQL data validation checks "
        "for monthly closes. That gave me a solid base in SQL and in the Azure services your team of 8 uses.",
    ],
}


def profile():
    return validate_profile(copy.deepcopy(PROFILE))


# ---------------------------------------------------------------- master profile

def test_profile_round_trips_through_yaml():
    p = profile()
    assert parse_yaml(to_yaml(p)) == p


def test_profile_errors_name_the_field():
    bad = copy.deepcopy(PROFILE)
    del bad["personal"]["name"]
    bad["experience"][1]["id"] = "acme"
    bad["experience"][0]["cv_bullets"] = "5-3"
    with pytest.raises(ProfileError) as exc:
        validate_profile(bad)
    text = " ".join(exc.value.errors)
    assert "personal.name" in text and "cv_bullets" in text


def test_duplicate_ids_rejected():
    bad = copy.deepcopy(PROFILE)
    bad["experience"][1]["id"] = "acme"
    with pytest.raises(ProfileError, match="unique"):
        validate_profile(bad)


def test_yaml_that_is_not_a_mapping():
    with pytest.raises(ProfileError):
        parse_yaml("- just\n- a list\n")


# ---------------------------------------------------------------- tailoring

def test_job_skills_use_aliases():
    p = profile()
    assert {"Apache PySpark", "Microsoft Azure", "Python", "SQL"} <= job_skills(p, JOB.description)
    assert "AWS" not in job_skills(p, JOB.description)


def test_most_relevant_bullet_first_and_limits_kept():
    p = profile()
    wanted = job_skills(p, JOB.description)
    picks = pick_entries(p, wanted, JOB.description)
    assert picks["acme"].bullets[0].startswith("Rewrote the Spark billing job")
    assert len(picks["acme"].bullets) == 5            # most recent role: up to 5
    assert len(picks["beta"].bullets) == 2            # older role: up to 3, has 2
    assert set(picks["acme"].bullets) <= set(PROFILE["experience"][0]["facts"])  # facts unchanged
    assert picks["acme"].technologies[0] in ("Python", "Apache PySpark")  # job's skills first


def test_cv_bullets_setting_wins():
    p = copy.deepcopy(PROFILE)
    p["experience"][0]["cv_bullets"] = "2-3"
    p = validate_profile(p)
    picks = pick_entries(p, set())
    assert len(picks["acme"].bullets) == 3 and picks["acme"].min_bullets == 2


def test_drop_one_prefers_older_entries_and_stops_at_minimum():
    p = profile()
    picks = pick_entries(p, job_skills(p, JOB.description), JOB.description)
    before = {k: len(v.bullets) for k, v in picks.items()}
    assert drop_one(picks, p, set())
    assert len(picks["side"].bullets) == before["side"] or len(picks["beta"].bullets) < before["beta"]
    while drop_one(picks, p, set()):
        pass
    assert len(picks["acme"].bullets) == 3 and len(picks["beta"].bullets) == 1 and len(picks["side"].bullets) == 1


def test_skill_rows_keep_labels_and_spelling():
    p = profile()
    rows = order_skill_rows(p, job_skills(p, JOB.description))
    assert [r["label"] for r in rows] == list(PROFILE["skills"])
    assert rows[1]["items"][0] == "Apache PySpark"
    assert sorted(rows[2]["items"]) == sorted(PROFILE["skills"]["Cloud"])


# ---------------------------------------------------------------- fact guard

def test_good_text_passes():
    assert check_written(WRITTEN, profile(), JOB.description) == []


def test_invented_number_rejected():
    w = copy.deepcopy(WRITTEN)
    w["paragraphs"][1] = w["paragraphs"][1].replace("40 minutes", "15 minutes")
    errors = check_written(w, profile(), JOB.description)
    assert any("'15'" in e for e in errors)


def test_number_from_the_job_is_allowed_in_the_letter_not_the_headline():
    w = copy.deepcopy(WRITTEN)
    w["headline"] = "Data Engineer ready for a team of 8"
    errors = check_written(w, profile(), JOB.description)
    assert errors == ["headline: number '8' is not in the profile - remove it"]


def test_wrong_paragraph_count_and_length():
    w = {"headline": "Data Engineer", "paragraphs": ["Too short.", "Also short."]}
    errors = check_written(w, profile(), JOB.description)
    assert any("exactly 3 paragraphs" in e for e in errors)
    assert any("paragraph 1 has 2 words" in e for e in errors)


def test_letter_must_be_first_person():
    w = copy.deepcopy(WRITTEN)
    w["paragraphs"][1] = w["paragraphs"][1].replace("At Acme GmbH I rewrote", "In your role at Acme GmbH you rewrote").replace(
        "I built", "You built")
    errors = check_written(w, profile(), JOB.description)
    assert errors == ["paragraph 2 must be in the first person, as the candidate (I, my); "
                      "'you'/'your' may only mean the company"]
    w = copy.deepcopy(WRITTEN)  # "My" opening a sentence is first person too
    w["paragraphs"][0] = w["paragraphs"][0].replace("That is the work I have done", "My work has been exactly this")
    assert check_written(w, profile(), JOB.description) == []
    assert check_written(WRITTEN, profile(), JOB.description) == []  # "your team of 8" is the company



GERMAN = [  # a German letter (the posting was German): first person, but not English
    "Acme entwickelt eine Plattform für Datenprodukte, und genau das ist meine Arbeit. Als Data Engineer habe ich "
    "Pipelines mit Airflow und dbt aufgebaut, die Daten für die Analyse bereitstellen und die ich seit Jahren selbst betreue.",
    "Bei Acme GmbH habe ich den Spark-Job für die Abrechnung neu geschrieben, und die Laufzeit ist von 6 Stunden auf "
    "40 Minuten gesunken. Zudem habe ich 12 Pipelines mit Airflow gebaut, die die Daten in das Warehouse laden.",
    "Ich möchte diese Erfahrung in Ihr Team einbringen, wo die Daten für die Kunden eine große Rolle spielen. "
    "Ich arbeite gern mit dem Team an den Pipelines und an der Qualität der Daten für die Plattform.",
]


def test_a_german_letter_is_named_as_german_not_as_a_pronoun_problem():
    w = {**copy.deepcopy(WRITTEN), "paragraphs": GERMAN}
    errors = check_written(w, profile(), JOB.description)
    assert errors == ["the letter is in German; write the headline and all 3 paragraphs in English, "
                      "even when the job posting is in German"]
    # English with a German company name or a German word or two is still English
    w = copy.deepcopy(WRITTEN)
    w["paragraphs"][0] = w["paragraphs"][0] + " I also enjoy the Datenplattform und die team culture."
    assert not any("German" in e for e in check_written(w, profile(), JOB.description))


def test_a_profile_from_a_cv_import_leaves_no_empty_labels():
    """A CV import gives no photo, work authorization, availability, technologies
    per role or project dates; the documents leave those out instead of printing
    bare labels and separators (a complete profile renders as before)."""
    sparse = copy.deepcopy(PROFILE)
    sparse["personal"].update(work_authorization="", availability="", work_authorization_short="",
                              availability_short="", linkedin_url="", github_url="")
    for e in sparse["experience"]:
        e["technologies"] = []
    sparse["projects"] = [{"id": "side", "name": "Side project", "start": "", "end": "", "technologies": [],
                           "facts": ["Built a small tool that loads 3 CSV files into Postgres every night."]}]
    sparse["certifications"] = []
    mp = validate_profile(sparse)
    ctx = _cv_context(mp, mp["default_headline"], [{"label": "Data", "items": ["SQL"]}], pick_entries(mp, set()))
    cv = render_html("cv.html.j2", ctx)
    assert "Technologies used:" not in cv
    assert "Certifications" not in cv
    assert 'class="with-photo"' not in cv                     # no room kept for a photo that isn't there
    assert '<div class="when"></div>' in cv                   # the project without dates: no lone "–"
    assert 'href=""' not in cv and "LinkedIn" not in cv       # no dead links
    text = _cv_text(ctx)
    assert "Side project" in text and "( – )" not in text and "Education" in text

    cl = {"tagline": "T", "date": "D", "recipient_lines": ["R"], "subject": "S", "salutation": "Hi",
          "paragraphs": ["P"], "closing": "C"}
    letter = render_html("cover_letter.html.j2", {"p": mp, "cl": cl})
    contact = letter.split('<div class="contact">')[1].split("</div>")[0]
    assert " – " not in contact and "&lt;" not in contact     # no bare "–", no escaped markup
    assert contact.count('<span class="sep">|</span>') == contact.count("|") == 1  # Berlin | email

# ---------------------------------------------------------------- the writer's bullets and skills

TAILORED = [  # what the writer returns for JOB, most relevant first
    {"id": "acme.2", "text": "Cut the Spark billing job's runtime from 6 hours to 40 minutes by rewriting it."},
    {"id": "acme.1", "text": "Loaded sales data into the warehouse by building 12 Airflow pipelines."},
    {"id": "acme.3", "text": "Introduced dbt models and AWS tests for the finance marts."},  # AWS: not this role's
    {"id": "acme.2", "text": "A repeat of a fact already picked."},
    {"id": "beta.1", "text": "Migrated 30 SQL Server reports onto Microsoft Azure."},
]


def as_answer(tailored):
    """TAILORED as build_documents takes it: ranked ids, plus the reworded ones.
    "focus" is what the writing call returns instead; the engine tests' fake
    model answers each focus bullet's rewording call from "reworded"."""
    ids = [t["id"] for t in tailored]
    return {"bullets": ids, "reworded": tailored, "focus": [{"id": i, "need": "x"} for i in dict.fromkeys(ids)]}


def _check(source, text, entry="acme"):
    p = profile()
    names = skill_names(p)
    e = next(x for x in p["experience"] + p["projects"] if x["id"] == entry)
    return check_bullet(source, text, mentioned(names, "\n".join(e["facts"] + e["technologies"])), names)


def test_reworded_bullet_checks():
    src = PROFILE["experience"][0]["facts"][1]  # 6 hours to 40 minutes
    assert _check(src, TAILORED[0]["text"]) is None
    assert "numbers changed" in _check(src, "Cut the Spark billing job's runtime from 6 hours to 30 minutes by rewriting it.")
    assert "numbers changed" in _check(src, "Cut the Spark billing job's runtime sharply by rewriting it end to end.")
    assert "AWS" in _check(PROFILE["experience"][0]["facts"][2], TAILORED[2]["text"])
    assert _check(PROFILE["experience"][0]["facts"][2], "Introduced dbt models and Airflow tests for the finance marts.") is None  # same role's tool
    assert "length" in _check(src, "Sped up Spark billing: 6 hours to 40 minutes.")
    assert "drops skills" in _check(src, "Cut the billing job's runtime from 6 hours to 40 minutes by rewriting it.")
    assert _check(src, "Cut the billing job's runtime from 6 hours to 40 minutes by rewriting it in PySpark.") is None  # alias: same skill
    assert "copied" in _check(src, " rewrote the Spark billing job, cutting runtime from 6 hours to 40  minutes.")
    assert "first person" in _check(src, "I cut the Spark billing job's runtime from 6 hours to 40 minutes by rewriting it.")
    side = PROFILE["projects"][0]["facts"][0]  # "...3 years of weather data on AWS S3": two 3s
    assert _check(side, "Collected weather data on AWS S3 for 3 years.", "side") is None
    assert "numbers changed" in _check(side, "Collected 3 years of weather data on AWS S3 in 3 regions.", "side")


def test_reworded_bullet_adds_no_words_of_its_own():
    """Seen on the real model: the posting's need turned into a claim."""
    pipelines = PROFILE["experience"][0]["facts"][0]  # Built 12 Airflow pipelines loading sales data into the warehouse.
    assert _check(pipelines, "Loaded sales data into the warehouse through 12 Airflow pipelines built for it.") is None
    assert "designed" in _check(pipelines, "Designed distributed services: 12 Airflow pipelines loading sales data into the warehouse.")
    oncall = PROFILE["experience"][0]["facts"][4]  # Ran the weekly on-call rotation for the data platform.
    assert _check(oncall, "Ran the data platform's weekly on-call rotation.") is None
    assert "past-tense" in _check(PROFILE["experience"][0]["facts"][1], "Cutting the Spark billing job's runtime from 6 hours to 40 minutes by rewriting it.")
    assert "owned" in _check(oncall, "Owned the weekly on-call rotation for the data platform.")
    assert _check(PROFILE["experience"][1]["facts"][0], "Migrated 30 SQL Server reports onto Microsoft Azure.", "beta") is None  # alias
    assert "repeats" in _check(PROFILE["experience"][1]["facts"][0], "Migrated 30 SQL Server reports onto Azure, Microsoft Azure.", "beta")
    assert "numbers changed" in _check("Owned 20+ Airflow pipelines for the data platform.",
                                       "Owned 20 Airflow pipelines for the data platform.")


def test_writer_picks_with_fallbacks():
    p = profile()
    picks = apply_picks(p, TAILORED, job_skills(p, JOB.description), JOB.description)
    acme = picks["acme"].items
    assert [b.fact_id for b in acme] == ["acme.2", "acme.1", "acme.3"]  # the model's order, the repeat ignored
    assert acme[0].tailored and acme[0].text == TAILORED[0]["text"]
    assert not acme[2].tailored and acme[2].text == PROFILE["experience"][0]["facts"][2] and "AWS" in acme[2].note
    assert picks["beta"].bullets == ["Migrated 30 SQL Server reports onto Microsoft Azure."]
    side = picks["side"].items  # not picked: code fills the minimum with the original fact
    assert [b.text for b in side] == PROFILE["projects"][0]["facts"] and "added by code" in side[0].note


def test_bullets_the_writer_did_not_reword_keep_the_original():
    p = profile()
    picks = apply_picks(p, [{"id": "acme.4", "text": ""}, *TAILORED[:2]], set())
    first = picks["acme"].items[0]
    assert (first.fact_id, first.text, first.tailored, first.note) == ("acme.4", PROFILE["experience"][0]["facts"][3], False, None)


def test_writer_picks_respect_each_roles_maximum():
    p = copy.deepcopy(PROFILE)
    p["experience"][1]["cv_bullets"] = "1-1"
    p = validate_profile(p)
    two = [{"id": "beta.1", "text": PROFILE["experience"][1]["facts"][0]},
           {"id": "beta.2", "text": PROFILE["experience"][1]["facts"][1]}]
    assert [b.fact_id for b in apply_picks(p, two, set())["beta"].items] == ["beta.1"]


def test_fit_drops_code_fills_then_the_models_lowest_ranked():
    p = profile()
    picks = apply_picks(p, TAILORED + [{"id": "acme.5", "text": PROFILE["experience"][0]["facts"][4]}], set())
    assert [b.fact_id for b in picks["acme"].items] == ["acme.2", "acme.1", "acme.3", "acme.5"]
    assert drop_one(picks)
    assert [b.fact_id for b in picks["acme"].items] == ["acme.2", "acme.1", "acme.3"]  # its lowest pick (rank 5)


def test_build_documents_uses_the_writers_bullets_and_skills():
    w = {**copy.deepcopy(WRITTEN), **as_answer(TAILORED), "skills_first": ["dbt", "Apache PySpark", "dbt", "Not A Skill"]}
    docs = build_documents(profile(), JOB, w)
    assert TAILORED[0]["text"] in docs.cv.text and PROFILE["experience"][0]["facts"][2] in docs.cv.text
    assert "Data: dbt, Apache PySpark" in docs.cv.text  # the writer's order leads its row
    by_id = {b["id"]: b for b in docs.bullets}
    assert by_id["acme.2"]["tailored"] and not by_id["acme.3"]["tailored"] and "AWS" in by_id["acme.3"]["note"]


def test_write_schema_only_allows_the_users_facts_and_skills():
    from app.applaut.ai.prompts import write_schema
    schema = write_schema(profile())["properties"]
    ids = ["acme.1", "acme.2", "acme.3", "acme.4", "acme.5", "beta.1", "beta.2", "side.1"]
    assert schema["bullets"]["items"]["enum"] == ids and schema["focus"]["items"]["properties"]["id"]["enum"] == ids
    assert schema["bullets"]["maxItems"] == 5 + 3 + 3 and schema["focus"]["maxItems"] == 5
    assert "dbt" in schema["skills_first"]["items"]["enum"] and "Kafka" not in schema["skills_first"]["items"]["enum"]


# ---------------------------------------------------------------- letter + rendering

def test_company_name_as_the_posting_writes_it():
    assert company_display("helsing", "Helsing is a defence AI company. Join Helsing in Munich. helsing.ai") == "Helsing"
    assert company_display("isaraerospace", "At Isar Aerospace we build launch vehicles.") == "Isar Aerospace"
    assert company_display("dymatrix", "dymatrix is a consulting firm.") == "dymatrix"  # the brand's own lower case
    assert company_display("dymatrix", "ABOUT DYMATRIX\nDYMATRIX\nAt Dymatrix we consult.") == "Dymatrix"  # headings lose
    assert company_display("getyourguide", "Apply at getyourguide.com or jobs@getyourguide.com") == "Getyourguide"
    assert company_display("get-your-guide", "No mention here.") == "Get Your Guide"
    assert company_display("Gamma SE", "gamma se") == "Gamma SE"  # already has capitals: kept


def test_letter_code_parts():
    cl = build_letter(profile(), JobInfo(title="Data Engineer", company="Gamma SE", location="Munich, Germany",
                                         reference="R-42"), WRITTEN["paragraphs"])
    assert cl["recipient_lines"] == ["Hiring Team", "Gamma SE", "Munich"]
    assert cl["subject"] == "Re: Application for Data Engineer (Ref. R-42)"
    assert cl["paragraphs"][:3] == WRITTEN["paragraphs"]
    assert "EU Blue Card" in cl["paragraphs"][3] and "Gamma SE" in cl["paragraphs"][3]
    assert cl["paragraphs"][4].startswith("Thank you")


def test_build_documents_renders_pdfs():
    docs = build_documents(profile(), JOB, WRITTEN)
    assert docs.cv.pdf.startswith(b"%PDF") and docs.cover_letter.pdf.startswith(b"%PDF")
    assert docs.cv.pages <= 2 and docs.cover_letter.pages == 1
    assert "Rewrote the Spark billing job" in docs.cv.text
    assert WRITTEN["headline"] in docs.cv.text
    assert "Dear Hiring Team," in docs.cover_letter.text
    assert len(docs.cv.sha256) == 64


def test_long_letter_loses_sentences_until_it_fits(monkeypatch):
    """Under the word limit but still over a page (long words, long title): code
    drops whole sentences instead of failing the job."""
    from app.applaut.documents import render
    monkeypatch.setattr(render, "LETTER_BODY_MAX_WORDS", 10_000)
    w = copy.deepcopy(WRITTEN)
    extra = " Spark performance engineering on Azure underpinned that responsibility for downstream analytics." * 10
    w["paragraphs"] = [" ".join((p + extra).split()[:155]) + "." for p in w["paragraphs"]]
    assert check_written(w, profile(), JOB.description) == []
    docs = build_documents(profile(), JOB, w)
    assert docs.cover_letter.pages == 1 and docs.sentences_dropped > 0
    assert "I rewrote the Spark billing job" in docs.cover_letter.text  # the first sentences stay


def test_long_profile_is_trimmed_to_two_pages():
    p = copy.deepcopy(PROFILE)
    long_fact = "Delivered a Spark and Airflow platform for the finance team, " * 6
    for i, e in enumerate(p["experience"]):
        e["facts"] = e["facts"][:2] + [f"{long_fact}(part {k})" for k in range(1, 5)]
        e["cv_bullets"] = "1-6"
    p["experience"] += [{**copy.deepcopy(p["experience"][1]), "id": f"old{i}"} for i in range(3)]
    p = validate_profile(p)
    w = copy.deepcopy(WRITTEN)
    docs = build_documents(p, JOB, w)
    assert docs.cv.pages == 2 and docs.bullets_dropped > 0


def test_rejected_text_is_not_rendered():
    w = copy.deepcopy(WRITTEN)
    w["paragraphs"][0] += " We grew revenue by 300% last year."
    with pytest.raises(DocumentError) as exc:
        build_documents(profile(), JOB, w)
    assert any("'300'" in e for e in exc.value.errors)


def test_sample_documents():
    docs = sample_documents(profile())
    assert docs.cv.pages <= 2 and docs.cover_letter.pages == 1
