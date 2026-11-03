import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from zprint.config import Settings
from zprint.db import connect
from zprint.domain import price, select_pages, transition
from zprint.models import Agent, Attempt, Document, Event, Job, MockTransaction, Payment, Printer, Quote, Reading, Session, Station, Tier, now, uid
from zprint.schemas import AgentEvent, Heartbeat, JobInput, PaymentInput, QuoteInput, SessionInput, Settlement
from zprint_documents.processor import process_pdf
from zprint_payments.adapter import SimulatedGateway


def public(row, *fields):
    return {key: getattr(row, key) for key in fields}


def create_app(settings=None):
    cfg = settings or Settings()
    cfg.validate()
    engine, factory = connect(cfg.database_url)
    gateway = SimulatedGateway(cfg.webhook_secret)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title="Z-PRINT · Phase 1 simulation", version="0.1.0", lifespan=lifespan)
    app.state.factory, app.state.settings, app.state.gateway = factory, cfg, gateway
    buckets, bucket_lock = defaultdict(deque), Lock()

    @app.middleware("http")
    async def basic_limits(request, call_next):
        # One-process development limiter. Production needs shared per-session/IP limits.
        if request.url.path.startswith("/api/"):
            key = request.client.host if request.client else "local"
            with bucket_lock:
                current = time.monotonic()
                queue = buckets[key]
                while queue and queue[0] < current - 60:
                    queue.popleft()
                if len(queue) >= 240:
                    return JSONResponse({"detail": "Rate limit exceeded"}, 429)
                queue.append(current)
            length = request.headers.get("content-length")
            if length and (not length.isdigit() or int(length) > cfg.max_upload + 65536):
                return JSONResponse({"detail": "Request too large"}, 413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    @app.exception_handler(IntegrityError)
    async def conflict(request, exc):
        return JSONResponse({"detail": "Concurrent update; retry using the same resource"}, 409)

    def db_session():
        with factory() as db:
            yield db

    def require_key(given, expected):
        if not given or not hmac.compare_digest(given, expected):
            raise HTTPException(401, "Invalid credential")

    def admin(x_admin_key: str = Header(default="")):
        require_key(x_admin_key, cfg.admin_key)

    def agent_auth(x_agent_key: str = Header(default="")):
        require_key(x_agent_key, cfg.agent_key)

    def student(authorization: str = Header(default=""), db=Depends(db_session)):
        token = authorization.removeprefix("Bearer ")
        session = db.scalar(select(Session).where(Session.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        if not session or session.expires_at <= now() or session.status != "ACTIVE":
            raise HTTPException(401, "Session missing or expired")
        return session

    def station_by_code(db, code):
        station = db.scalar(select(Station).where(Station.code == code))
        if station is None:
            raise HTTPException(404, "Station not found")
        return station

    def printer_for(db, station_id):
        printer = db.scalar(select(Printer).where(Printer.station_id == station_id, Printer.enabled.is_(True)))
        if printer is None:
            raise HTTPException(409, "No enabled printer")
        return printer

    def owned_quote(db, quote_id, session):
        quote = db.get(Quote, quote_id)
        if not quote or quote.session_id != session.id:
            raise HTTPException(404, "Quote not found")
        return quote

    def owned_job(db, job_id, session):
        job = db.get(Job, job_id)
        if not job:
            raise HTTPException(404, "Job not found")
        owned_quote(db, job.quote_id, session)
        return job

    def machine_job(db, job_id):
        job = db.get(Job, job_id)
        station = station_by_code(db, cfg.station)
        if not job or job.station_id != station.id:
            raise HTTPException(404, "Job not found for this agent")
        return job

    def readiness(db, printer, sides):
        station = db.get(Station, printer.station_id)
        if station.status != "ACTIVE" or not printer.enabled:
            raise HTTPException(409, "Station or printer paused")
        reading = db.scalar(select(Reading).where(Reading.printer_id == printer.id).order_by(Reading.observed_at.desc(), Reading.created_at.desc(), Reading.id.desc()))
        if not reading or now() - reading.observed_at > cfg.heartbeat_ttl:
            raise HTTPException(409, "Printer heartbeat missing or stale")
        if reading.reachability != "READY" or reading.errors_json or "EMPTY" in (reading.paper_status, reading.toner_status):
            raise HTTPException(409, "Printer is not ready; operator assistance required")
        if sides >= 100 and "UNKNOWN" in (reading.paper_status, reading.toner_status):
            raise HTTPException(409, "Bulk order requires confirmed supplies")
        return reading

    def audit(db, job, event_type, source, key=None, payload=None):
        sequence = (db.scalar(select(func.max(Event.sequence)).where(Event.job_id == job.id)) or 0) + 1
        db.add(Event(job_id=job.id, sequence=sequence, event_type=event_type, source=source, idempotency_key=key or uid(), event_payload_json=payload or {}))

    def lock_job(db, job):
        version = job.lock_version
        changed = db.execute(update(Job).where(Job.id == job.id, Job.lock_version == version).values(lock_version=version + 1))
        if changed.rowcount != 1:
            raise HTTPException(409, "Concurrent job operation; retry")
        db.refresh(job)

    def quote_json(quote):
        return public(quote, "id", "document_id", "settings_json", "printed_sides", "sheets", "rate_ugx", "total_ugx", "pricing_version", "expires_at") | {"currency": "UGX", "illustrative_prices": True}

    @app.get("/health")
    def health(db=Depends(db_session)):
        db.execute(select(Station.id).limit(1))
        return {"status": "ok", "mode": "SIMULATION", "real_money": False, "real_printer": False}

    @app.get("/api/v1/stations/{code}")
    def station_info(code: str, db=Depends(db_session)):
        station = station_by_code(db, code)
        printer = printer_for(db, station.id)
        reading = db.scalar(select(Reading).where(Reading.printer_id == printer.id).order_by(Reading.observed_at.desc(), Reading.id.desc()))
        return public(station, "code", "name", "status") | {"printer": public(printer, "model", "supports_colour", "supports_duplex", "media_json"), "readiness": reading.reachability if reading and now() - reading.observed_at <= cfg.heartbeat_ttl else "UNKNOWN", "simulation": True}

    @app.post("/api/v1/sessions", status_code=201)
    def new_session(body: SessionInput, db=Depends(db_session)):
        station = station_by_code(db, body.station_code)
        if station.status != "ACTIVE":
            raise HTTPException(409, "Station paused")
        token = secrets.token_urlsafe(32)
        session = Session(station_id=station.id, source=body.source, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=now() + 86400)
        db.add(session)
        db.commit()
        return {"id": session.id, "token": token, "expires_at": session.expires_at}

    @app.post("/api/v1/documents", status_code=201)
    def upload(file: UploadFile = File(...), session=Depends(student), db=Depends(db_session)):
        filename = file.filename or "document.pdf"
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(415, "Phase 1 supports PDF only; DOCX conversion is scheduled for Phase 2")
        if file.content_type not in ("application/pdf", "application/octet-stream"):
            raise HTTPException(415, "Expected PDF content type")
        identifier = uid()
        source, target = cfg.data_dir / (identifier + ".upload"), cfg.data_dir / (identifier + ".pdf")
        try:
            size = 0
            with source.open("xb") as output:
                while chunk := file.file.read(65536):
                    size += len(chunk)
                    if size > cfg.max_upload:
                        raise HTTPException(413, "PDF exceeds 20 MiB")
                    output.write(chunk)
            try:
                pages, digest = process_pdf(source, target, cfg.max_pages)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            doc = Document(id=identifier, station_id=session.station_id, owner_session_id=session.id, storage_key=target.name,
                           original_name=Path(filename.replace("\\", "/")).name[:160], mime_type="application/pdf", sha256=digest,
                           page_count=pages, expires_at=now() + cfg.retention_seconds)
            db.add(doc)
            db.commit()
            return public(doc, "id", "original_name", "page_count", "sha256", "expires_at")
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            source.unlink(missing_ok=True)
            file.file.close()

    def document_file(doc):
        if not doc or doc.deleted_at or doc.expires_at <= now() or not (cfg.data_dir / doc.storage_key).is_file():
            raise HTTPException(410, "Document expired or removed")
        return FileResponse(cfg.data_dir / doc.storage_key, media_type="application/pdf", headers={"Content-Disposition": "inline; filename=document.pdf"})

    @app.get("/api/v1/documents/{document_id}/preview")
    def preview(document_id: str, session=Depends(student), db=Depends(db_session)):
        doc = db.get(Document, document_id)
        if not doc or doc.owner_session_id != session.id:
            raise HTTPException(404, "Document not found")
        return document_file(doc)

    @app.post("/api/v1/quotes", status_code=201)
    def new_quote(body: QuoteInput, session=Depends(student), db=Depends(db_session)):
        doc = db.get(Document, body.document_id)
        if not doc or doc.owner_session_id != session.id:
            raise HTTPException(404, "Document not found")
        if doc.deleted_at or doc.expires_at <= now():
            raise HTTPException(410, "Document expired")
        printer = printer_for(db, session.station_id)
        if body.mode == "COLOUR" and not printer.supports_colour or body.duplex and not printer.supports_duplex:
            raise HTTPException(422, "Printer does not support selected mode")
        try:
            pages = select_pages(body.page_range, doc.page_count)
            if len(pages) * body.copies > cfg.max_sides:
                raise ValueError("Order exceeds 2,000 printed sides")
            tiers = db.scalars(select(Tier).where(Tier.station_id == session.station_id, Tier.mode == body.mode, Tier.active.is_(True))).all()
            totals = price(pages, body.copies, body.duplex, tiers)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        quote = Quote(session_id=session.id, document_id=doc.id, settings_json=body.model_dump(exclude={"document_id", "page_range"}) | {"pages": pages}, expires_at=min(now() + 600, doc.expires_at), **totals)
        db.add(quote)
        db.commit()
        return quote_json(quote)

    @app.get("/api/v1/quotes/{quote_id}")
    def get_quote(quote_id: str, session=Depends(student), db=Depends(db_session)):
        return quote_json(owned_quote(db, quote_id, session))

    @app.post("/api/v1/jobs", status_code=201)
    def new_job(body: JobInput, session=Depends(student), db=Depends(db_session)):
        quote = owned_quote(db, body.quote_id, session)
        existing = db.scalar(select(Job).where(Job.quote_id == quote.id))
        if existing:
            return public(existing, "id", "status")
        if quote.expires_at <= now():
            raise HTTPException(410, "Quote expired; request a new quote")
        job = Job(quote_id=quote.id, station_id=session.station_id, printer_id=printer_for(db, session.station_id).id)
        db.add(job)
        db.flush()
        audit(db, job, "AWAITING_PAYMENT", "backend")
        db.commit()
        return public(job, "id", "status")

    @app.post("/api/v1/payments/initiate")
    def initiate(body: PaymentInput, session=Depends(student), db=Depends(db_session)):
        job = owned_job(db, body.job_id, session)
        lock_job(db, job)
        quote = db.get(Quote, job.quote_id)
        if job.status not in ("AWAITING_PAYMENT", "PAYMENT_FAILED"):
            raise HTTPException(409, "Job cannot accept another payment")
        pending = db.scalar(select(Payment).where(Payment.job_id == job.id, Payment.status == "PENDING"))
        if pending:
            return public(pending, "id", "status", "merchant_ref", "amount_ugx", "provider")
        if quote.expires_at <= now():
            raise HTTPException(410, "Quote expired")
        document_file(db.get(Document, quote.document_id))
        readiness(db, db.get(Printer, job.printer_id), quote.printed_sides)
        payment = Payment(job_id=job.id, provider=body.provider, msisdn_masked=body.msisdn[:4] + "*****" + body.msisdn[-3:], amount_ugx=quote.total_ugx, merchant_ref=uid())
        db.add(payment)
        tx = gateway.initiate_charge(db, payment.merchant_ref, payment.amount_ugx, payment.provider)
        payment.provider_ref = tx.provider_ref
        if job.status == "PAYMENT_FAILED":
            transition(job, "AWAITING_PAYMENT")
        audit(db, job, "PAYMENT_PENDING", "mock-gateway")
        db.commit()
        return public(payment, "id", "status", "merchant_ref", "amount_ugx", "provider") | {"simulation": True, "message": "No charge or PIN prompt was sent"}

    def reconcile(db, merchant_ref):
        payment = db.scalar(select(Payment).where(Payment.merchant_ref == merchant_ref))
        if not payment:
            raise HTTPException(404, "Payment not found")
        job = db.get(Job, payment.job_id)
        lock_job(db, job)
        db.refresh(payment)
        tx = gateway.verify_transaction(db, merchant_ref)
        if not tx or (tx.amount_ugx, tx.currency, tx.provider, tx.provider_ref, tx.merchant_ref) != (payment.amount_ugx, "UGX", payment.provider, payment.provider_ref, payment.merchant_ref):
            raise HTTPException(409, "Provider verification mismatch; payment held")
        if payment.status in ("SUCCEEDED", "FAILED"):
            return {"status": payment.status, "duplicate": True}
        if tx.status == "SUCCEEDED":
            if job.status not in ("AWAITING_PAYMENT", "PAYMENT_FAILED"):
                raise HTTPException(409, "Payment requires manual reconciliation")
            payment.status = "SUCCEEDED"
            transition(job, "PAID")
            job.paid_at = now()
            audit(db, job, "PAID", "verified-mock-gateway", "paid:" + payment.id)
        elif tx.status == "FAILED":
            payment.status = "FAILED"
            transition(job, "PAYMENT_FAILED")
            audit(db, job, "PAYMENT_FAILED", "verified-mock-gateway", "failed:" + payment.id)
        db.commit()
        return {"status": payment.status}

    @app.post("/api/v1/payments/webhook")
    async def webhook(request: Request, x_signature: str = Header(default=""), db=Depends(db_session)):
        body = await request.body()
        if len(body) > 8192:
            raise HTTPException(413, "Webhook too large")
        try:
            merchant_ref = gateway.parse_verified_webhook(body, x_signature)
        except ValueError as exc:
            raise HTTPException(401, "Invalid webhook") from exc
        return reconcile(db, merchant_ref)

    @app.post("/api/v1/payments/{payment_id}/reconcile")
    def poll_payment(payment_id: str, session=Depends(student), db=Depends(db_session)):
        payment = db.get(Payment, payment_id)
        if not payment:
            raise HTTPException(404, "Payment not found")
        owned_job(db, payment.job_id, session)
        return reconcile(db, payment.merchant_ref)

    @app.post("/api/v1/demo/payments/{payment_id}/settle", dependencies=[Depends(admin)])
    def mock_settle(payment_id: str, body: Settlement, db=Depends(db_session)):
        payment = db.get(Payment, payment_id)
        if not payment:
            raise HTTPException(404, "Payment not found")
        tx = gateway.query_status(db, payment.merchant_ref)
        if tx.status != "PENDING" and tx.status != body.status:
            raise HTTPException(409, "Mock transaction already finalized")
        tx.status = body.status
        db.commit()
        return {"provider_status": tx.status, "next": "Reconcile or deliver a signed webhook; settlement alone does not release printing"}

    @app.get("/api/v1/jobs/{job_id}")
    def job_status(job_id: str, session=Depends(student), db=Depends(db_session)):
        job = owned_job(db, job_id, session)
        events = db.scalars(select(Event).where(Event.job_id == job.id).order_by(Event.sequence)).all()
        quote = db.get(Quote, job.quote_id)
        return public(job, "id", "status", "paid_at", "completed_at") | {"quote": quote_json(quote), "events": [public(e, "event_type", "source", "created_at") for e in events],
                "receipt": {"reference": job.id, "total_ugx": quote.total_ugx, "currency": "UGX", "simulation": True} if job.paid_at else None,
                "completion_evidence": "SIMULATED_OUTPUT_ONLY" if job.status == "COMPLETED" else "NONE"}

    @app.post("/api/v1/agent/heartbeat", dependencies=[Depends(agent_auth)])
    def heartbeat(body: Heartbeat, db=Depends(db_session)):
        station = station_by_code(db, cfg.station)
        printer = printer_for(db, station.id)
        agent = db.scalar(select(Agent).where(Agent.station_id == station.id))
        agent.last_seen_at = now()
        # Keep a current snapshot plus audit of actual job decisions, avoiding unbounded heartbeat growth.
        reading = db.scalar(select(Reading).where(Reading.printer_id == printer.id))
        if reading is None:
            reading = Reading(printer_id=printer.id, reachability=body.state)
            db.add(reading)
        reading.observed_at, reading.reachability = now(), body.state
        reading.paper_status, reading.toner_status, reading.errors_json = body.paper_status, body.toner_status, body.errors
        db.commit()
        return {"agent_id": agent.id, "observed_at": reading.observed_at}

    @app.get("/api/v1/agent/jobs/next", dependencies=[Depends(agent_auth)])
    def claim(db=Depends(db_session)):
        station = station_by_code(db, cfg.station)
        # Expired claims are never recycled; dispatch may have occurred before a crash.
        expired = db.scalars(select(Job).where(Job.station_id == station.id, Job.status.in_(["QUEUED", "PRINTING"]), Job.lease_until < now())).all()
        for job in expired:
            lock_job(db, job)
            transition(job, "COMPLETION_UNCERTAIN")
            audit(db, job, "COMPLETION_UNCERTAIN", "lease-watchdog")
        db.commit()
        job = db.scalar(select(Job).where(Job.station_id == station.id, Job.status == "PAID").order_by(Job.created_at).limit(1))
        if not job:
            return {"job": None}
        quote = db.get(Quote, job.quote_id)
        doc = db.get(Document, quote.document_id)
        if doc.deleted_at or doc.expires_at <= now():
            lock_job(db, job)
            transition(job, "PAUSED")
            audit(db, job, "DOCUMENT_EXPIRED", "agent-claim")
            db.commit()
            return {"job": None}
        readiness(db, db.get(Printer, job.printer_id), quote.printed_sides)
        changed = db.execute(update(Job).where(Job.id == job.id, Job.status == "PAID", Job.lock_version == job.lock_version).values(status="QUEUED", lock_version=job.lock_version + 1, lease_until=now() + 120))
        if changed.rowcount != 1:
            db.rollback()
            return {"job": None}
        agent = db.scalar(select(Agent).where(Agent.station_id == station.id))
        db.add(Attempt(job_id=job.id, agent_id=agent.id))
        audit(db, job, "QUEUED", "agent-claim", "claim:" + job.id)
        db.commit()
        return {"job": {"id": job.id, "settings": quote.settings_json, "sha256": doc.sha256, "document_url": f"/api/v1/agent/jobs/{job.id}/document"}}

    @app.get("/api/v1/agent/jobs/{job_id}/document", dependencies=[Depends(agent_auth)])
    def agent_document(job_id: str, db=Depends(db_session)):
        job = machine_job(db, job_id)
        if job.status not in ("QUEUED", "PRINTING"):
            raise HTTPException(409, "No active print claim")
        return document_file(db.get(Document, db.get(Quote, job.quote_id).document_id))

    @app.post("/api/v1/agent/jobs/{job_id}/events", dependencies=[Depends(agent_auth)])
    def agent_event(job_id: str, body: AgentEvent, db=Depends(db_session)):
        job = machine_job(db, job_id)
        key = "agent:" + job.id + ":" + body.event_id
        if db.scalar(select(Event).where(Event.idempotency_key == key)):
            return {"status": job.status, "duplicate": True}
        lock_job(db, job)
        attempt = db.scalar(select(Attempt).where(Attempt.job_id == job.id))
        if not attempt:
            raise HTTPException(409, "Agent must claim job first")
        if body.state == "PRINTING":
            readiness(db, db.get(Printer, job.printer_id), db.get(Quote, job.quote_id).printed_sides)
        if body.state == "COMPLETED" and not body.spooler_job_id:
            raise HTTPException(422, "Completion requires simulated output reference")
        try:
            transition(job, body.state)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        attempt.state, attempt.spooler_job_id = body.state, body.spooler_job_id or attempt.spooler_job_id
        if body.state in ("COMPLETED", "COMPLETION_UNCERTAIN", "FAILED", "PAUSED"):
            attempt.ended_at = now()
            attempt.outcome_confidence = "SIMULATED" if body.state == "COMPLETED" else "UNKNOWN"
        if body.state == "COMPLETED":
            job.completed_at = now()
            doc = db.get(Document, db.get(Quote, job.quote_id).document_id)
            # Remove shortly after completion, preserving a minute for the demo preview.
            doc.expires_at = min(doc.expires_at, now() + 60)
        audit(db, job, body.state, "simulated-agent", key, body.model_dump())
        db.commit()
        return {"status": job.status}

    @app.get("/api/v1/admin/reports", dependencies=[Depends(admin)])
    def report(db=Depends(db_session)):
        jobs = db.scalars(select(Job)).all()
        payments = db.scalars(select(Payment).where(Payment.status == "SUCCEEDED")).all()
        return {"simulation": True, "verified_sales_ugx": sum(p.amount_ugx for p in payments), "jobs": [public(j, "id", "status", "created_at") for j in jobs]}

    @app.get("/api/v1/admin/pricing", dependencies=[Depends(admin)])
    def pricing(db=Depends(db_session)):
        return [public(t, "mode", "min_sides", "max_sides", "rate_ugx", "version") for t in db.scalars(select(Tier).where(Tier.active.is_(True))).all()]

    portal = Path(__file__).resolve().parents[3] / "apps" / "student-portal"
    if portal.exists():
        app.mount("/", StaticFiles(directory=portal, html=True), name="demo-portal")
    return app
