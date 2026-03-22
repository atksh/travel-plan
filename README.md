# BosoDrive Optimizer

Foreground-first PWA for planning a Boso Peninsula drive day, with a FastAPI backend, OR-Tools-backed route solving, Alembic migrations, and SQLite-first storage.

This repository now follows a strict runtime policy:

- fail-fast
- no fallback
- contract-first

In practice, that means missing config, invalid backend state, and bad external API responses are treated as explicit errors instead of being silently repaired with mocks, estimates, or cached data.

## Requirements

- Python **3.12** (recommended; see `.python-version`)
- Node.js **20+**
- A valid Google Maps Platform API key with the APIs used by the app enabled

## Required environment variables

### Backend

Copy `backend/.env.example` to `backend/.env` and set real values:

```bash
DATABASE_URL=sqlite:///./bosodrive.db
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
GOOGLE_MAPS_API_KEY=your_real_key
RUN_MIGRATIONS_ON_STARTUP=false
RUN_SEED_ON_STARTUP=false
```

Important notes:

- `GOOGLE_MAPS_API_KEY` is required. The backend will fail on startup if it is missing.
- `CORS_ORIGINS` must include the exact frontend origin you use.
- If you run the frontend on `3001`, include `http://localhost:3001`.

### Frontend

Copy `frontend/.env.example` to `frontend/.env` and set real values:

```bash
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=your_real_key
```

Important notes:

- `NEXT_PUBLIC_API_URL` is required.
- `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` is required.
- The frontend will fail at runtime if either value is missing.

## Backend setup

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

If port `8000` is already in use, start the backend on another port such as `8001` and update `frontend/.env` accordingly:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

- Health: `GET http://127.0.0.1:8000/health`
- API: `http://127.0.0.1:8000/api/...`

The backend no longer relies on runtime `create_all`. Run migrations explicitly before serving traffic.

### Alembic

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

If you already have an older local SQLite DB from the pre-Alembic flow, start from a fresh DB file after backing up the old one:

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

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

If `3000` is occupied, Next.js may move to `3001`. In that case:

1. make sure `backend/.env` includes `http://localhost:3001` in `CORS_ORIGINS`
2. restart the backend

For an iPhone-style PWA, use Safari **Add to Home Screen**.

## Stable E2E verification

For final browser verification, prefer a production-style frontend server instead of `next dev`:

```bash
cd frontend
rm -rf .next
npm run build
PORT=3001 npm run start
```

Keep the backend running separately while doing this.

## Tests

Backend:

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

Frontend:

```bash
cd frontend
npm run test
npm run build
```

## Docker (backend)

```bash
cd backend
docker build -t bosodrive-api .
docker run -p 8000:8000 -v bosodata:/app/data bosodrive-api
```

When running with Docker, provide the same required environment variables as above.

## Deployment notes

- **Vercel**: deploy the `frontend` app and set both `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`.
- **Railway**: deploy `backend` with `backend` as root; set `DATABASE_URL`, `CORS_ORIGINS`, and `GOOGLE_MAPS_API_KEY`; run `alembic upgrade head` before serving traffic.

## Data model

Canonical POIs live in `poi_master` and related tables; trips use `trip_candidate` rows for inserts and removals. Times are stored as **integer minutes** from midnight.

The canonical backend contracts now drive the UI directly:

- trip detail returns `latest_solve`
- active trip uses a canonical `active-bootstrap` payload
- frontend should not reconstruct solve state from fragmented backend fields

See `AGENTS.md` for the repo-wide design rules that keep these guarantees in place.
