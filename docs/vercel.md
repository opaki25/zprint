# Vercel portal deployment

The original build failed with FASTAPI_ENTRYPOINT_NOT_FOUND because the application lived outside Vercel's default entrypoint paths. The repository now declares `[tool.vercel] entrypoint = "vercel_app:app"` and pins Python 3.12 in `.python-version`. `vercel.json` includes the portal assets and selects FastAPI.

The original `zprint.main:app` is a persistent service: it writes a database/document directory, depends on migrations and works with long-running print/retention processes. Pointing Vercel directly at that module only fixes detection; it does not provide the storage or worker lifecycle. This deployment therefore uses a stateless portal gateway. The local/Docker backend entrypoint is unchanged.

## Redeploy the portal

1. In the Vercel project, use repository `opaki25/zprint`, branch `main`, Root Directory **repository root** (leave blank).
2. Framework Preset: **FastAPI**. Remove custom Build Command, Install Command and Output Directory overrides; use the framework defaults.
3. Deploy the latest commit, not the original `b946f1d` deployment. A retry of that old commit still has the old configuration.
4. Without a backend URL, the portal renders in **Portal preview** mode. Uploads/payments are disabled, API requests return 503, and `/health` reports only portal availability. No ephemeral database or fake payment success is created.

## Connect printing services

Run the backend with a persistent document volume, PostgreSQL, migrations, seed and retention service on a persistent host. Run the print agent on the station PC with outbound access to that backend. The existing Docker Compose setup describes these components, but its API is deliberately bound to localhost; do not expose it unchanged as a public service. Complete the deployment/security gate before public user traffic, including document sandbox hardening and replacing the published development keys. Use a protected staging backend for hosted demo testing.

Set the Vercel environment variable `ZPRINT_BACKEND_URL` to the backend's **HTTPS origin**, such as `https://your-backend.example` (illustration only; no service is provisioned at that address), then redeploy. Do not include `/api/v1`, credentials, query parameters or the Vercel portal's own URL. The backend must be reachable from Vercel with the credentials already provided by the client/agent. The gateway does not add a privileged credential or bypass backend authentication.

The portal forwards `/api/v1/*` to that fixed backend. It preserves student tokens, explicitly supplied admin/agent/signature headers, request bytes and response status. It does not forward browser cookies or follow upstream redirects. Configure agent/provider callback URLs directly against the persistent backend where possible. Never point the agent at localhost on Vercel.

Vercel has a 4.5 MB function request/response limit. The hosted UI caps PDF uploads at **3 MiB**, leaving multipart overhead room; the gateway bounds request and response buffering. The native backend portal retains its 20 MiB upload limit. Full-sized remote upload/preview support requires a private object-storage upload/download design in a later phase.

## Verification

Run `python -m pytest tests/test_vercel.py -q`. Tests cover entrypoint import, read-only/no-database startup, assets, unconfigured setup behavior, upstream authentication/body preservation, redirects, errors, timeouts and payload bounds. Run the full suite to verify the local backend still works. These are local checks; an actual Vercel build requires the connected project and is not implied by passing unit tests.

Official references:
- https://vercel.com/docs/frameworks/backend/fastapi#exporting-the-fastapi-application
- https://vercel.com/docs/functions/limitations
