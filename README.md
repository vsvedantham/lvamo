# LVAMO

A platform of career tools ("verticals") sharing one backend, one database
and one frontend app:

| Vertical | Frontend | API | Status |
|---|---|---|---|
| **Applaut** — AI job discovery and tailored applications | `/applaut` | `/api/v1/applaut` | Live (hidden from hub) |
| **Jobref** — employee referrals for job seekers | `/jobref` | `/api/v1/jobref` | Live |
| **ProSho** — evidence-backed capstone project pages | `/prosho` | `/api/v1/prosho` | Planned — see `docs/prosho/BETA_PLAN.md` |

Platform-wide endpoints (e.g. hub settings) live under `/api/v1/platform`.
The structure rules every vertical follows are in [`CLAUDE.md`](CLAUDE.md);
current status is in [`PROGRESS.md`](PROGRESS.md) and `PROGRESS_<VERTICAL>.md`.

## Prerequisites

- Docker & Docker Compose (recommended)
- **Or** manually: Python 3.12+, Node 20+, PostgreSQL 16

## Quick start (Docker)

```bash
# 1. Clone and enter the repo (folder is still named after the repo, lvamo-applaut)
git clone <repo-url>
cd lvamo-applaut

# 2. Create your .env file
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY to a random string

# 3. Start all services
docker compose up --build

# 4. Run database migrations (first time, and after new migrations)
docker compose exec backend alembic upgrade head
```

Services will be available at:

| Service  | URL |
|----------|-----|
| Frontend (LVAMO hub) | http://localhost:5173 |
| Backend  | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| Health   | http://localhost:8000/api/v1/applaut/health, http://localhost:8000/api/v1/jobref/health |

---

## Manual setup (without Docker)

### PostgreSQL

Create a database and user matching your `.env`:

```sql
CREATE USER lvamo WITH PASSWORD 'applaut_dev';
CREATE DATABASE lvamo OWNER lvamo;
```

Migrations create one Postgres schema per vertical (`applaut`, `jobref`, …)
plus `platform` for LVAMO-wide tables.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example .env          # then edit .env

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install

# Create a local .env (Vite reads .env in the frontend/ directory)
echo "VITE_PLATFORM_API_BASE_URL=http://localhost:8000
VITE_APPLAUT_API_BASE_URL=http://localhost:8000
VITE_JOBREF_API_BASE_URL=http://localhost:8000" > .env.local

npm run dev
```

---

## Running migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Generate a new migration (after editing models)
alembic revision --autogenerate -m "describe your change"
```

Run these from the `backend/` directory (or via `docker compose exec backend`).
There is one migration chain for the whole platform; name new files
`NNNN_<vertical>_<what>.py` or `NNNN_platform_<what>.py`.

---

## Project structure

```
lvamo-applaut/
├── CLAUDE.md                 # LVAMO master spec — structure rules for every vertical
├── PROGRESS.md               # Platform status; PROGRESS_<VERTICAL>.md per vertical
├── docs/<vertical>/          # Per-vertical specs and plans
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app; mounts /api/v1/platform and each vertical
│   │   ├── config.py         # Settings (loaded from .env)
│   │   ├── db/, core/        # Shared infra: DB session, security, R2 storage
│   │   ├── platform/         # LVAMO-wide models + API (schema `platform`)
│   │   ├── applaut/          # Applaut vertical (schema `applaut`)
│   │   └── jobref/           # Jobref vertical (schema `jobref`)
│   ├── migrations/           # One shared Alembic chain
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.tsx           # React Router root — /, /applaut/*, /jobref/*
│       ├── pages/Hub.tsx     # LVAMO hub
│       ├── components/, hooks/   # Shared UI
│       ├── applaut/          # Applaut vertical UI
│       └── jobref/           # Jobref vertical UI
├── nginx/                    # Reverse proxy + TLS cert renewal scripts
├── deploy.sh                 # Production deploy (run on the VM)
├── docker-compose.yml
└── .env.example
```

---

## Environment variables

See `.env.example` for the full list. Required variables to get started:

| Variable       | Description                            |
|----------------|----------------------------------------|
| `DATABASE_URL` | asyncpg connection string              |
| `SECRET_KEY`   | JWT signing secret (min 32 chars)      |

All other variables (R2, OpenAI, Google OAuth, LinkedIn OAuth) can be left
empty during initial development.
