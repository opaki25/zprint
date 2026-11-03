# Z-PRINT

Phase 1 of the Z-PRINT Development Blueprint v1.0 (27 October 2026). A runnable, payment-gated printing demonstration with a FastAPI backend, relational migrations, private PDF processing, browser portal, and durable local print agent.

**Simulation only: no real money moves and no physical printer is connected.** `ZPRINT_DEMO=false` refuses startup. Default credentials are public development values. Bind to loopback; do not expose this build to the internet.

## Run with Docker

Requires Docker Engine/Desktop with Compose v2. From the repository root:

```sh
docker compose up --build -d
docker compose logs -f backend agent
```

Open http://localhost:8000. Compose starts PostgreSQL 16, runs Alembic and an idempotent seed, then starts the API, agent and document-retention service. PostgreSQL has no published host port. Only localhost:8000 is published.

```sh
docker compose down
```

This preserves named volumes. Do not delete volumes containing needed transaction history.

## Run locally (Windows PowerShell)

Python 3.11+ is required. Run from the repository root. Local development uses SQLite; Docker uses PostgreSQL with the same models and migration.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e '.[test]'
New-Item -ItemType Directory -Force data | Out-Null
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m zprint.seed
.venv/Scripts/python.exe -m uvicorn zprint.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
.venv/Scripts/python.exe -m zprint_agent.worker
```

In a third terminal (required to enforce file deletion):

```powershell
.venv/Scripts/python.exe -m zprint.maintenance
```

On Linux/macOS use `.venv/bin/python` and `mkdir -p data`. Environment values are read from the process. `.env.example` documents them; Python does **not** automatically load `.env`. Compose reads `.env` for its key substitutions. To override a native setting use `$env:ZPRINT_ADMIN_KEY='your-local-key'` (PowerShell) or `export ZPRINT_ADMIN_KEY=...` (POSIX).

## Try the full demonstration

1. Open http://127.0.0.1:8000/?station=ST001. Wait until the agent is ready.
2. Upload a plain, non-interactive PDF. A deterministic 15-page fixture can be generated with `python scripts/make_sample.py` using the installed environment.
3. Select 2 copies and double-sided printing. The 15-page sample quotes **30 billable sides, 16 sheets, UGX 6,000**.
4. Enter a number in `+2567XXXXXXXX` format and select simulated MTN or Airtel. No PIN prompt or charge is sent.
5. Open Demo operator controls, enter `local-demo-admin-change-me` (or your configured key), then choose Simulate success. This settles the separate mock ledger; the application independently reconciles the transaction before releasing the job.
6. Watch PAID → QUEUED → PRINTING → COMPLETED, event history and a clearly labeled simulated receipt.
7. Native simulated output is `data/agent/spool/<job-id>.pdf`. Docker output is in the agent volume. It contains selected pages, copies and blank duplex separators. It is removed after approximately one minute. This is a print-plan simulation; it does not rasterize colour content into grayscale or certify physical output.

The demo portal is a small dependency-free responsive client. Next.js student application, QR generation, restricted kiosk and full administrator UI are later phases; folders and acceptance tracking are included. API docs: http://127.0.0.1:8000/docs. OpenAPI: `/openapi.json`.

## Verify

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m alembic check
.venv/Scripts/python.exe scripts/demo.py
```

`scripts/demo.py` exercises the running API and agent using a generated PDF, confirms the exact quote and waits for completion. It uses development keys from environment/defaults. Tests migrate isolated databases and cover the full agent flow, pricing thresholds, signed callbacks and independent verification, wrong amount/currency/provider, retry/idempotency, races, readiness, claim expiry, privacy, retention, and crash/outbox recovery. Set `TEST_DATABASE_URL` only to a **disposable** PostgreSQL database: tests clear its application tables. CI runs SQLite and PostgreSQL jobs.

To simulate failure, write `NOT_READY` to `data/agent/printer-state.txt`; restore `READY` for recovery. `UNKNOWN` is also supported. The agent publishes this state within three seconds. A paid job is held while unavailable. Ambiguous dispatches become `COMPLETION_UNCERTAIN` and require operator investigation; Phase 1 deliberately provides no automatic reprint/refund button.

## Repository

```text
apps/student-portal/          Runnable Phase 1 demonstration
apps/kiosk-portal/            Phase 4 boundary and acceptance contract
apps/admin-dashboard/         Later-phase admin UI boundary
services/backend-api/zprint/  API, business rules, database models, retention
services/document-processor/  Isolated bounded PDF parser
services/payment-service/     Payment protocol and simulated provider ledger
services/print-agent/         SQLite queue/outbox, printer interface, simulation
packages/shared-types/        OpenAPI generation contract
packages/shared-ui/           Shared design direction for later React clients
database/migrations/          Frozen Alembic schema and future migration history
database/seeds/               Seed entrypoint documentation
infrastructure/docker/        Non-root application image
infrastructure/deployment/    Pilot readiness checklist
docs/                        Architecture, ADRs, integration needs, requirement matrix
tests/                       Unit/integration/end-to-end tests
```

## Scope and next milestones

Read [requirements.md](docs/requirements.md) for **every FR-01–FR-15 requirement and all blueprint acceptance cases**, including partial/deferred work. [Architecture](docs/architecture.md) explains transaction and crash boundaries. [Integrations](docs/integrations.md) lists hardware, credentials and documentation needed. [Validation](docs/validation.md) records what was actually executed locally and what remains unverified.

This is a foundation, not a completed production self-service station. Remaining work includes sandboxed DOCX conversion, real payment onboarding, CUPS/IPP capability/telemetry integration, full local offline service/sync, OS USB lockdown, role-based admin accounts, price editing and recovery/refund workflows. No later-phase requirement is silently represented as complete.
