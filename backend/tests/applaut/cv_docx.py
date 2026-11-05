"""Test .docx CVs for the own-template tests (fictional "Alex Example"), built
in code so no real CV sits in the repo. `LABELS` is what a correct labelling
of `plain_cv()` looks like, line by line."""
import io

from docx import Document
from docx.shared import Pt, RGBColor


def _bold_label(p, label: str, rest: str) -> None:
    r = p.add_run(label)
    r.bold = True
    p.add_run(rest)


def plain_cv(extra_bullet_gap: bool = False) -> bytes:
    """One-column CV: name, headline, contact, skills rows with bold labels, two
    jobs with title and company lines, bullets and a technologies line, one
    project, education. `extra_bullet_gap` puts a note between two bullets."""
    d = Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10.5)
    h = d.add_paragraph()
    r = h.add_run("Alex Example")
    r.bold, r.font.size, r.font.color.rgb = True, Pt(20), RGBColor(0x11, 0x55, 0xCC)
    d.add_paragraph("Data Engineer (5 years) with Python, Airflow and dbt")
    d.add_paragraph("Berlin, Germany | alex@example.invalid | +49 30 000000")
    d.add_paragraph("A short profile paragraph the candidate wrote about themselves, which stays as it is.")
    d.add_heading("Skills", level=2)
    _bold_label(d.add_paragraph(), "Languages:", " Python | SQL | Scala")
    _bold_label(d.add_paragraph(), "Data:", " Apache PySpark | Airflow | dbt")
    _bold_label(d.add_paragraph(), "Cloud:", " Microsoft Azure | AWS")
    d.add_heading("Experience", level=2)
    _bold_label(d.add_paragraph(), "Data Engineer", " — Acme GmbH, Berlin")
    d.add_paragraph("2022 – Present")
    d.add_paragraph("Built 12 Airflow pipelines loading sales data into the warehouse.", style="List Bullet")
    d.add_paragraph("Rewrote the Spark billing job, cutting runtime from 6 hours to 40 minutes.", style="List Bullet")
    if extra_bullet_gap:
        d.add_paragraph("(Team of four)")
    d.add_paragraph("Mentored 2 junior engineers.", style="List Bullet")
    _bold_label(d.add_paragraph(), "Technologies:", " Python, Airflow, Apache PySpark, dbt")
    _bold_label(d.add_paragraph(), "Junior Data Engineer", " — Beta AG, Munich")
    d.add_paragraph("2020 – 2022")
    d.add_paragraph("Migrated 30 SQL Server reports to Azure.", style="List Bullet")
    d.add_paragraph("Wrote SQL data validation checks for monthly closes.", style="List Bullet")
    d.add_heading("Projects", level=2)
    _bold_label(d.add_paragraph(), "Weather Lake", " (side project, 2023 – 2024)")
    d.add_paragraph("Collected 3 years of weather data on AWS S3.", style="List Bullet")
    d.add_heading("Education", level=2)
    d.add_paragraph("M.Sc. Computer Science — TU Berlin, 2018 – 2020")
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()


LABELS = (["name", "headline", "contact", "other", "section", "skills", "skills", "skills", "section",
           "role", "role", "bullet", "bullet", "bullet", "technologies",
           "role", "role", "bullet", "bullet", "section", "role", "bullet", "section", "other"])


def table_cv() -> bytes:
    """Two-column CV: a table with the dates on the left and the role, company
    and bullets on the right (common in German CVs), skills in a table too."""
    d = Document()
    d.styles["Normal"].font.name = "Arial"
    d.styles["Normal"].font.size = Pt(10)
    p = d.add_paragraph()
    r = p.add_run("Alex Example")
    r.bold, r.font.size = True, Pt(18)
    d.add_paragraph("Data Engineer · Python · Airflow · dbt")
    d.add_paragraph("alex@example.invalid · +49 30 000000 · linkedin.com/in/alex-example")
    d.add_heading("Berufserfahrung", level=1)
    t = d.add_table(rows=2, cols=2)
    for row, (dates, title, company, bullets) in zip(t.rows, [
        ("01/2022 – heute", "Data Engineer", "Acme GmbH, Berlin",
         ["Built 12 Airflow pipelines loading sales data into the warehouse.",
          "Rewrote the Spark billing job, cutting runtime from 6 hours to 40 minutes."]),
        ("03/2020 – 12/2021", "Junior Data Engineer", "Beta AG, München",
         ["Migrated 30 SQL Server reports to Azure."]),
    ]):
        row.cells[0].text = dates
        cell = row.cells[1]
        cell.paragraphs[0].add_run(title).bold = True
        cell.add_paragraph(company)
        for b in bullets:
            cell.add_paragraph(b, style="List Bullet")
    d.add_heading("Kenntnisse", level=1)
    _bold_label(d.add_paragraph(), "Languages:", " Python, SQL, Scala")
    _bold_label(d.add_paragraph(), "Cloud:", " Microsoft Azure, AWS")
    d.add_heading("Ausbildung", level=1)
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = "2018 – 2020"
    t.rows[0].cells[1].text = "M.Sc. Informatik, TU Berlin"
    d.add_heading("Sprachen", level=1)
    d.add_paragraph("Deutsch (C1), Englisch (C2)")
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()


def german_cv() -> bytes:
    """A German CV: a summary, title and company on one line with a tab before
    the dates, bullets typed as "•" in Normal paragraphs, no technologies lines."""
    d = Document()
    d.styles["Normal"].font.name = "Calibri"
    p = d.add_paragraph()
    p.add_run("Alex Example").bold = True
    d.add_paragraph("Berlin · alex@example.invalid · +49 30 000000")
    d.add_paragraph("Data Engineer mit 5 Jahren Erfahrung in Python, Airflow und dbt")
    d.add_paragraph("Ich baue verlässliche Datenplattformen und arbeite gern eng mit Fachbereichen zusammen. "
                    "Zuletzt habe ich bei Acme die Abrechnung beschleunigt und das Team im Aufbau begleitet.")
    d.add_heading("Berufserfahrung", level=2)
    _bold_label(d.add_paragraph(), "Data Engineer, Acme GmbH", "\t2022 – heute")
    d.add_paragraph("•\tBuilt 12 Airflow pipelines loading sales data into the warehouse.")
    d.add_paragraph("•\tRewrote the Spark billing job, cutting runtime from 6 hours to 40 minutes.")
    d.add_paragraph("•\tMentored 2 junior engineers.")
    _bold_label(d.add_paragraph(), "Junior Data Engineer, Beta AG", "\t2020 – 2022")
    d.add_paragraph("•\tMigrated 30 SQL Server reports to Azure.")
    d.add_paragraph("•\tWrote SQL data validation checks for monthly closes.")
    d.add_heading("IT-Kenntnisse", level=2)
    _bold_label(d.add_paragraph(), "Data:", " Apache PySpark, Airflow, dbt")
    _bold_label(d.add_paragraph(), "Cloud:", " Microsoft Azure, AWS")
    d.add_heading("Ausbildung", level=2)
    d.add_paragraph("M.Sc. Informatik, TU Berlin\t2018 – 2020")
    d.add_heading("Zertifikate", level=2)
    d.add_paragraph("•\tAWS Certified Data Engineer – Associate (2024)")
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()


TABLE_LABELS = ["name", "headline", "contact", "section", "role", "role", "role", "bullet", "bullet",
                "role", "role", "role", "bullet", "section", "skills", "skills", "section", "other", "other",
                "section", "other"]
GERMAN_LABELS = ["name", "contact", "headline", "other", "section", "role", "bullet", "bullet", "bullet",
                 "role", "bullet", "bullet", "section", "skills", "skills", "section", "other", "section", "other"]
