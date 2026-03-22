# BosoDrive Agent Principles

This file defines the default engineering rules for this repository.
Treat these rules as repo-wide and non-optional unless the user explicitly asks to change them.

## Core Principles

### 1. Fail Fast

- Validate required config at startup.
- Validate request shape at the API boundary.
- Validate external API response shape before using it.
- Reject invalid state immediately instead of repairing it in place.

### 2. No Fallback

- Do not return mock data in runtime code.
- Do not fall back to cached, stale, estimated, or partial data for core trip flows.
- Do not silently convert external API failures into local approximations.
- Do not auto-correct invalid timestamps, missing fields, or broken relations.
- If a dependency is required, fail explicitly when it is unavailable.

### 3. Contract First

- Backend schemas are the single source of truth.
- Frontend must render backend contracts, not reconstruct them.
- If a UI needs a field, add it to the backend contract instead of inferring it client-side.
- Use explicit typed models for core payloads. Avoid unstructured `dict[str, Any]` for stable contracts.

## Backend Rules

- Required runtime config must be validated in startup code.
- Use explicit application errors with stable error codes and messages.
- Core route solving must use a complete travel matrix contract. No estimate fallback.
- Solver failures must remain explicit failures. No heuristic fallback unless the public contract is changed first.
- Google Places and Routes integrations must fail on invalid or incomplete responses.
- Imported POIs must be rejected if required source fields are missing or unsupported.
- Persist canonical solve snapshots that frontend can consume directly.
- Use `Field(default_factory=list)` style defaults for schema collection fields, not mutable literals.

## Frontend Rules

- Required env vars must be read through strict config helpers, not `process.env.X || default`.
- Do not rebuild solve state from fragmented backend fields.
- Do not derive active trip state from multiple endpoints if the backend can provide a canonical payload.
- Do not infer missing coordinates, labels, or route geometry from secondary sources.
- Do not swallow bootstrap failures for required screens.
- Offline or degraded behavior for core trip flows is not allowed unless the product contract is explicitly updated first.

## Change Protocol

When changing a core contract, update all of the following in the same change:

1. Backend schema
2. Backend serializer / route
3. Frontend type
4. Frontend consumer
5. Tests

If one side still needs reconstruction logic, the contract is incomplete.

## Forbidden Patterns

- `process.env.SOME_KEY || "default"` for required runtime config
- `Promise.allSettled(...)` for required bootstrap data
- `try/except` or `catch` that returns stale, estimated, mock, or partial runtime data
- Placeholder repair logic like `label || trip.origin_label` for required fields
- Frontend synthesis of `SolveResponse` from `TripDetailOut`
- Runtime mocks in Google API client code
- Silent replacement of missing external data with fabricated values

## Allowed Optionality

- A field may be optional only if the backend schema says it is optional and the UI has an explicit product-approved empty state.
- Optional must mean "not required by contract", not "missing but guessed later".

## Testing Expectations

- Tests must set required env values explicitly.
- Tests should use explicit test doubles for external dependencies instead of relying on runtime fallback.
- Add or update tests whenever a contract, failure mode, or error code changes.
- Prefer asserting explicit failure codes/messages over generic success-path behavior.

## Local Server Operations

### Backend

- Standard dev start:
  - `cd backend`
  - `source .venv/bin/activate`
  - `alembic upgrade head`
  - `python -m app.db.seed`
  - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- If port `8000` is already occupied in the local machine, use:
  - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8001`
- Code changes in Python files should be reflected automatically by `--reload`.
- Fully restart the backend process instead of trusting hot reload when any of the following changes:
  - startup/config validation
  - environment variables
  - migrations or DB initialization
  - dependency wiring or app lifespan behavior
- Health check after restart:
  - `curl http://127.0.0.1:8000/health`
  - or `curl http://127.0.0.1:8001/health`

### Frontend

- Standard dev start:
  - `cd frontend`
  - `npm run dev`
- If port `3000` is already occupied, Next.js may move to `3001`. Confirm the actual port from server output.
- React/Next code changes should usually reflect automatically during `npm run dev`.
- Fully restart the frontend dev server when any of the following happens:
  - stale chunk or asset 404s
  - HMR loops or invalid hot-update messages
  - client-side runtime config changes
  - unexplained hydration mismatch after a refactor
- If dev artifacts look corrupted, do a clean rebuild:
  - `cd frontend`
  - `rm -rf .next`
  - `npm run build`
  - `npm run dev`

### Stable E2E Verification

- For final browser verification, prefer production-style frontend serving instead of `next dev`:
  - `cd frontend`
  - `rm -rf .next`
  - `npm run build`
  - `PORT=3001 npm run start`
- Keep backend running separately while doing this.
- If production-style E2E uses a non-default frontend port, make sure `CORS_ORIGINS` includes that exact origin before testing.

## Review Checklist

Before finishing a change, verify:

- Does this introduce any silent recovery path?
- Does backend remain the single source of truth?
- Are required fields validated at the boundary?
- Are external dependency failures explicit?
- Did schema, route, frontend, and tests change together?
