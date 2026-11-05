FROM python:3.12-slim

WORKDIR /app

# WeasyPrint (Applaut AI's standard CV/cover-letter PDFs) needs Pango and HarfBuzz.
# LibreOffice Writer (headless) turns a user's own .docx template into PDF; the
# fonts are metric-compatible stand-ins for Calibri, Cambria, Arial, Times New
# Roman and Courier New, so a Word layout keeps its line breaks, plus Roboto,
# Open Sans and Lato (Google Docs' common fonts).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
      libreoffice-writer-nogui fonts-crosextra-carlito fonts-crosextra-caladea fonts-liberation fonts-dejavu-core \
      fonts-roboto fonts-open-sans fonts-lato \
 && rm -rf /var/lib/apt/lists/*


# Dev image only: includes test tooling (prod uses Dockerfile.prod).
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
