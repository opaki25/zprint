# Phase 1 validation — 27 October 2026

Executed on Windows, Python 3.12, native SQLite:

- 26 integration/agent tests passed after the event-order correction.
- 4 additional backlog/domain tests passed (30 tests total).
- Alembic upgraded a fresh database through both migrations; `alembic check` reported no new operations.
- Python compileall and JavaScript `node --check` passed.
- Separate running backend, print agent and retention processes exercised by `scripts/demo.py`: 15 pages × 2 copies, duplex, 30 billable sides, 16 sheets, UGX 6,000, COMPLETED with simulated evidence.
- Browser UI exercised with the same generated PDF: upload/count, settings, quote, mock initiation, admin mock settlement, independent reconciliation and live completion/receipt. Mobile-width layout inspected. Browser check discovered same-second audit ordering; fixed with per-job event sequences and added an exact event-order assertion.

One test warning comes from Starlette's deprecated AnyIO BlockingPortal alias; no test failed. Pinned direct dependencies make the development baseline explicit; production requires the dependency security review recorded in the deployment gate.

Not executed here: Docker Compose build/start and PostgreSQL runtime tests, because Docker is not installed/available on this host. PostgreSQL CI service and migration-based test suite are configured but have not been run remotely. No CI success is claimed. Real hardware, actual MTN/Airtel, USB lockdown, DOCX, full offline operation and production load/security remain later-phase work.

Local demo processes remain running on loopback port 8000 for review. Logs are under data/. To stop only this checkout's native demo processes, run scripts/stop-dev.ps1. Content/spool output is automatically cleaned by the running retention/agent services.
