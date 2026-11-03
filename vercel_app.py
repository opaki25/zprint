"""Stateless Vercel portal; the durable printing services run on a separate host.

Never import zprint.main here: its database and document directory belong to the
persistent backend. A missing upstream must not create ephemeral payment state.
"""
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

PORTAL = Path(__file__).resolve().parent / "apps" / "student-portal"
REQUEST_LIMIT = 3 * 1024 * 1024 + 65536
RESPONSE_LIMIT = 4 * 1024 * 1024
SETUP_MESSAGE = "Portal preview only. Connect the persistent Z-PRINT backend before uploading or printing."


def create_portal(backend_url=None, transport=None, gateway_key=None):
    upstream = (backend_url if backend_url is not None else os.getenv("ZPRINT_BACKEND_URL", "")).strip().rstrip("/")
    gateway_key = gateway_key if gateway_key is not None else os.getenv("ZPRINT_BACKEND_GATEWAY_KEY", "")
    parsed = urlsplit(upstream)
    configured = bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
                      and not parsed.path and not parsed.query and not parsed.fragment)
    app = FastAPI(title="Z-PRINT hosted portal", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    @app.get("/deployment.json")
    def deployment():
        return {"hosting": "vercel-portal", "backend_configured": configured,
                "max_upload_bytes": 3 * 1024 * 1024,
                "message": "Hosted demo · PDF uploads up to 3 MiB." if configured else SETUP_MESSAGE}

    @app.get("/health")
    def health():
        # Portal liveness only, never a claim about backend/printer readiness.
        return {"status": "portal_available", "backend_configured": configured, "simulation": True}

    @app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy(path: str, request: Request):
        if not configured:
            return JSONResponse({"detail": SETUP_MESSAGE}, status_code=503)
        if request.url.hostname == parsed.hostname:
            return JSONResponse({"detail": "Backend must be a separate persistent service, not this portal."}, status_code=503)
        # Keep the upstream path within the intended API; never follow client-selected destinations.
        if any(part in (".", "..") for part in path.split("/")) or "\\" in path or "%" in path:
            return JSONResponse({"detail": "Invalid API path"}, status_code=400)
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > REQUEST_LIMIT:
                return JSONResponse({"detail": "Hosted portal uploads are limited to 3 MiB."}, status_code=413)
            chunks.append(chunk)
        forwarded = {name: request.headers[name] for name in (
            "authorization", "content-type", "x-admin-key", "x-agent-key", "x-signature", "idempotency-key"
        ) if name in request.headers}
        if gateway_key:
            # Deployment secret, never supplied by browser JavaScript or reflected in responses.
            forwarded["x-zprint-gateway-key"] = gateway_key
        try:
            async with httpx.AsyncClient(transport=transport, timeout=30, follow_redirects=False) as client:
                async with client.stream(request.method, upstream + "/api/v1/" + path,
                                         params=request.query_params.multi_items(), headers=forwarded,
                                         content=b"".join(chunks)) as result:
                    if 300 <= result.status_code < 400:
                        return JSONResponse({"detail": "Backend returned a redirect; configure its final HTTPS origin."}, status_code=502)
                    output, size = [], 0
                    async for chunk in result.aiter_bytes():
                        size += len(chunk)
                        if size > RESPONSE_LIMIT:
                            return JSONResponse({"detail": "Backend response exceeds the hosted portal limit. Use the persistent backend portal for this document."}, status_code=502)
                        output.append(chunk)
                    response_headers = {key: result.headers[key] for key in ("content-type", "content-disposition", "retry-after") if key in result.headers}
                    return Response(b"".join(output), status_code=result.status_code, headers=response_headers)
        except httpx.TimeoutException:
            return JSONResponse({"detail": "Backend timed out. Check job status before retrying a payment."}, status_code=504)
        except httpx.HTTPError:
            return JSONResponse({"detail": "Printing backend is unreachable. Try again later."}, status_code=502)

    app.mount("/", StaticFiles(directory=PORTAL, html=True), name="portal")
    return app


app = create_portal()
