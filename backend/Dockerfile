FROM python:3.12-slim

WORKDIR /app

# Dev image only: includes test tooling (prod uses Dockerfile.prod).
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
