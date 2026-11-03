# Persistent hosted backend (Phase 1 demonstration)

`render.yaml` is a deployable Render Blueprint for the existing FastAPI backend. It provisions **paid resources** only after the owner reviews/applies the Render plan. Adding the file to GitHub does not create or pay for services.

## Resources prepared

| Resource | Configuration |
|---|---|
| zprint-backend | Docker web service, Frankfurt, 1 CPU / 2 GB RAM (`1c-2g`) |
| Document/agent disk | 1 GB persistent disk mounted at `/data` |
| zprint-db | PostgreSQL 16, 0.1 CPU / 256 MB (`0.1c-256mb`), 1 GB storage, private-network access only |
| Credentials | Four distinct automatically generated admin, agent, webhook and gateway keys |

The 2 GB service gives the API, bounded PDF parser and simulated printer room to run together. Confirm the current monthly and usage-based quote in Render before provisioning. The Blueprint does not choose a free database that may expire or an ephemeral document directory. Frankfurt is a configurable initial region; keep service/database in the same region.

## Startup and durability

The service runs `python -m zprint.hosted`. At runtime, after the disk is mounted, it validates hosted settings, runs Alembic, idempotently seeds ST001 and starts:

- One Uvicorn API process listening on Render's `PORT`.
- One document-retention process sharing `/data/documents`.
- One simulated print agent with durable `/data/agent/queue.db` and spool files.

The parent monitors all three children. If a child exits, it terminates the remaining processes and exits nonzero so the platform can restart the service. Shutdown sends termination to children and bounds the wait. A print interrupted by restart still goes through the existing uncertainty workflow; it is never blindly repeated.

PostgreSQL connection strings from Render are normalized to the installed psycopg v3 driver. Credentials are environment values, never command arguments or checked-in secrets. Hosted mode refuses default/short/reused keys, SQLite and relative document paths. The container remains non-root. If a platform disk reports a write-permission error, grant the image's UID 10001 ownership of the mounted data directory; do not run the application as root to bypass it.

This is deliberately a **single-instance demonstration**. A disk cannot be shared across Render instances, so do not enable horizontal scaling. Before physical printing, move the agent to the actual station PC and stop the hosted simulated agent; do not run two agents for ST001. Actual gateway and hardware adapters remain unimplemented.

## Deploy and connect

1. Connect Render, or create a Blueprint from `https://github.com/opaki25/zprint` in the Render dashboard. Review the resource/cost proposal before applying it.
2. Wait for PostgreSQL and the backend to become healthy. The backend logs should show migrations, seed, API startup and agent heartbeat. `/health` checks API/database availability; printer readiness is separately checked through the station endpoint.
3. In Vercel's environment settings, set:
   - `ZPRINT_BACKEND_URL` = the actual Render backend HTTPS origin (no `/api` suffix).
   - `ZPRINT_BACKEND_GATEWAY_KEY` = the generated `ZPRINT_GATEWAY_KEY` from the Render backend environment.
4. Redeploy Vercel. It now sends the gateway key server-side on API requests. The key is not returned in `/deployment.json` and is never embedded in the browser. Direct requests to backend `/api/*` without that key fail with 401. Student/admin/agent authentication is still required where applicable.
5. Upload a synthetic PDF through Vercel. Use the generated `ZPRINT_ADMIN_KEY` in the demo operator controls to simulate a payment. Verify independent reconciliation, completion and receipt. Never use the old `local-demo-*` keys for hosted services.

For direct automated verification, run `scripts/demo.py` with `ZPRINT_API_URL`, `ZPRINT_GATEWAY_KEY` and `ZPRINT_ADMIN_KEY` supplied through your local process environment. Keep these values out of terminal history, screenshots and source control. No live provider transaction is performed.

## Limits and remaining deployment work

- The hosted portal accepts 3 MiB PDFs because of Vercel function payload limits. The backend's native 20 MiB limit is unchanged.
- Test only with synthetic documents. Live files expire by application policy, but Render's daily disk snapshots can retain deleted content for seven days. Production needs an approved backup/retention design and the document sandbox/security gate in `infrastructure/deployment/checklist.md`.
- API health does not certify the printer's physical state or successful paper output. Every job/receipt remains explicitly simulated.
- No Render/Vercel credentials or backend origin can be inferred from the public Git repository. Account connections and cost approval are required to provision and wire the hosted services.

Official references: [Blueprint specification](https://render.com/docs/blueprint-spec), [persistent disks](https://render.com/docs/disks), [compute plans](https://render.com/docs/compute-plans).
