# BosoDrive Optimizer

Foreground-first PWA for planning a Boso Peninsula drive day, with a FastAPI backend, OR-Tools-backed route solving, Alembic migrations, and SQLite-first storage.

## Requirements

- Python **3.12** (recommended; see `.python-version`)
- Node.js **20+** for the Next.js frontend

## Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:///./bosodrive.db
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Health: `GET http://127.0.0.1:8000/health`
- API: `http://127.0.0.1:8000/api/...`

The backend no longer relies on runtime `create_all` by default. Apply migrations first, then optionally seed the curated Boso POIs.

Environment variables:

- `DATABASE_URL` (default `sqlite:///./bosodrive.db`)
- `CORS_ORIGINS` (comma-separated, default `http://localhost:3000`)
- `GOOGLE_MAPS_API_KEY` (optional; Places/Routes clients return mocks when empty)
- `RUN_MIGRATIONS_ON_STARTUP` (default `false`; opt-in local convenience only)
- `RUN_SEED_ON_STARTUP` (default `false`; opt-in local convenience only)

### Alembic

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

If you already have an older local SQLite DB that was created with the old
`create_all` startup flow, start from a fresh DB file or stamp it only after
you confirm the schema matches:

```bash
cd backend
source .venv/bin/activate
mv bosodrive.db bosodrive.pre_alembic.db
alembic upgrade head
python -m app.db.seed
```

Create a new revision after model changes:

```bash
cd backend
source .venv/bin/activate
alembic revision --autogenerate -m "describe_change"
```

Seed the canonical POIs after migrations:

```bash
cd backend
source .venv/bin/activate
python -m app.db.seed
```

## Frontend

```bash
cd frontend
npm install
export NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
npm run dev
```

Open `http://localhost:3000`. For an iPhone-style PWA, use Safari **Add to Home Screen** (icons can be added later in `public/`).

## Tests

```bash
cd backend
pytest tests/ -q
```

Useful subsets:

```bash
cd backend
pytest tests/test_api_trips.py -q
pytest tests/test_api_pois.py -q
pytest tests/test_migrations.py -q
```

## Docker (backend)

```bash
cd backend
docker build -t bosodrive-api .
docker run -p 8000:8000 -v bosodata:/app/data bosodrive-api
```

## Deployment notes

- **Vercel**: deploy the `frontend` app; set `NEXT_PUBLIC_API_URL` to your Railway API URL.
- **Railway**: deploy `backend` with `backend` as root; set `DATABASE_URL` to a persistent SQLite path or Postgres; set `CORS_ORIGINS` to your Vercel origin; run `alembic upgrade head` before serving traffic.

## Data model

Canonical POIs live in `poi_master` and related tables; trips use `trip_candidate` rows for inserts and removals. Times are stored as **integer minutes** from midnight. See `.cursor/plans/` for the full architecture (do not edit that file unless you intend to change the plan).
