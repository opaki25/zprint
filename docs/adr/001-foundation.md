# ADR 001: deployable Python foundation, portable development database

Status: accepted for Phase 1.

Use FastAPI, Pydantic, SQLAlchemy and Alembic for the backend; PostgreSQL is the deployment database. A native SQLite backend mode permits a runnable Windows demonstration without Docker. Agent durability always uses its own SQLite database. UUID strings and UTC epoch seconds keep the migration portable. Revisit native UUID/timestamptz storage only via an explicit migration.

The Phase 1 web client is static and dependency-free; it proves the canonical APIs without adding a frontend build prerequisite. This is a temporary demonstration client, not a replacement for the blueprint's Next.js student and React kiosk applications. Full frontends come in the stated milestones. Separate Python packages preserve service seams without premature network calls for every internal operation.

Live adapter startup is blocked until the payment/hardware/security requirements are verified. No fake vendor endpoints are supplied. An ambiguous dispatch is quarantined even when that means operator work. This favors preventing duplicate prints over unattended retry.
