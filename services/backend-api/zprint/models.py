"""Portable relational schema. Epoch timestamps are UTC seconds; IDs are UUID strings."""
import time
import uuid
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return str(uuid.uuid4())


def now():
    return int(time.time())


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[int] = mapped_column(default=now)


class Station(Identity, Base):
    __tablename__ = "stations"
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str]
    location_label: Mapped[str] = mapped_column(default="Development station")
    status: Mapped[str] = mapped_column(default="ACTIVE")
    local_url: Mapped[str | None]


class Printer(Identity, Base):
    __tablename__ = "printers"
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), index=True)
    model: Mapped[str] = mapped_column(default="Simulated A4 printer")
    ipp_uri: Mapped[str] = mapped_column(default="simulated://ST001")
    supports_colour: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_duplex: Mapped[bool] = mapped_column(Boolean, default=True)
    media_json: Mapped[list] = mapped_column(JSON, default=lambda: ["A4"])
    enabled: Mapped[bool] = mapped_column(default=True)


class Reading(Identity, Base):
    __tablename__ = "printer_readings"
    printer_id: Mapped[str] = mapped_column(ForeignKey("printers.id"), index=True)
    observed_at: Mapped[int] = mapped_column(default=now)
    reachability: Mapped[str]
    paper_status: Mapped[str] = mapped_column(default="UNKNOWN")
    toner_status: Mapped[str] = mapped_column(default="UNKNOWN")
    errors_json: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(default="SIMULATED")
    source: Mapped[str] = mapped_column(default="simulated-agent")


class Session(Identity, Base):
    __tablename__ = "sessions"
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    source: Mapped[str]
    expires_at: Mapped[int]
    status: Mapped[str] = mapped_column(default="ACTIVE")


class Document(Identity, Base):
    __tablename__ = "documents"
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"))
    owner_session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    storage_key: Mapped[str]
    original_name: Mapped[str]
    mime_type: Mapped[str]
    sha256: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int]
    expires_at: Mapped[int] = mapped_column(index=True)
    deleted_at: Mapped[int | None]


class Tier(Identity, Base):
    __tablename__ = "pricing_tiers"
    __table_args__ = (CheckConstraint("min_sides > 0 AND rate_ugx > 0"), UniqueConstraint("station_id", "mode", "version", "min_sides"))
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"))
    mode: Mapped[str]
    min_sides: Mapped[int]
    max_sides: Mapped[int | None]
    rate_ugx: Mapped[int]
    version: Mapped[int]
    active: Mapped[bool] = mapped_column(default=True)


class Quote(Identity, Base):
    __tablename__ = "quotes"
    __table_args__ = (CheckConstraint("total_ugx > 0 AND printed_sides > 0 AND sheets > 0"),)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    settings_json: Mapped[dict] = mapped_column(JSON)
    printed_sides: Mapped[int]
    sheets: Mapped[int]
    rate_ugx: Mapped[int]
    total_ugx: Mapped[int]
    pricing_version: Mapped[int]
    expires_at: Mapped[int]


class Job(Identity, Base):
    __tablename__ = "print_jobs"
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), unique=True)
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), index=True)
    printer_id: Mapped[str] = mapped_column(ForeignKey("printers.id"))
    status: Mapped[str] = mapped_column(default="AWAITING_PAYMENT", index=True)
    paid_at: Mapped[int | None]
    completed_at: Mapped[int | None]
    lock_version: Mapped[int] = mapped_column(default=0)
    lease_until: Mapped[int | None]


class Payment(Identity, Base):
    __tablename__ = "payment_attempts"
    job_id: Mapped[str] = mapped_column(ForeignKey("print_jobs.id"), index=True)
    provider: Mapped[str]
    msisdn_masked: Mapped[str]
    amount_ugx: Mapped[int]
    merchant_ref: Mapped[str] = mapped_column(unique=True)
    provider_ref: Mapped[str | None] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="PENDING")


class Agent(Identity, Base):
    __tablename__ = "agent_devices"
    station_id: Mapped[str] = mapped_column(ForeignKey("stations.id"), unique=True)
    public_key_or_credential_ref: Mapped[str] = mapped_column(default="env:ZPRINT_AGENT_KEY")
    last_seen_at: Mapped[int] = mapped_column(default=now)
    status: Mapped[str] = mapped_column(default="ACTIVE")


class Attempt(Identity, Base):
    __tablename__ = "print_attempts"
    __table_args__ = (UniqueConstraint("job_id", "attempt_no"),)
    job_id: Mapped[str] = mapped_column(ForeignKey("print_jobs.id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent_devices.id"))
    attempt_no: Mapped[int] = mapped_column(default=1)
    spooler_job_id: Mapped[str | None]
    state: Mapped[str] = mapped_column(default="CLAIMED")
    started_at: Mapped[int] = mapped_column(default=now)
    ended_at: Mapped[int | None]
    outcome_confidence: Mapped[str] = mapped_column(default="UNKNOWN")


class Event(Identity, Base):
    __tablename__ = "job_events"
    sequence: Mapped[int] = mapped_column(default=1)
    job_id: Mapped[str] = mapped_column(ForeignKey("print_jobs.id"), index=True)
    event_type: Mapped[str]
    event_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str]
    idempotency_key: Mapped[str] = mapped_column(unique=True)


class Refund(Identity, Base):
    __tablename__ = "refunds"
    job_id: Mapped[str] = mapped_column(ForeignKey("print_jobs.id"))
    payment_attempt_id: Mapped[str] = mapped_column(ForeignKey("payment_attempts.id"))
    amount_ugx: Mapped[int]
    reason: Mapped[str]
    status: Mapped[str]
    provider_ref: Mapped[str | None] = mapped_column(unique=True)


class User(Identity, Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    role: Mapped[str]
    enabled: Mapped[bool] = mapped_column(default=True)


class Outbox(Identity, Base):
    __tablename__ = "sync_outbox"
    event_uuid: Mapped[str] = mapped_column(unique=True)
    entity_type: Mapped[str]
    entity_id: Mapped[str]
    payload_json: Mapped[dict] = mapped_column(JSON)
    delivered_at: Mapped[int | None]


class MockTransaction(Identity, Base):
    """Separate simulated provider ledger, never populated from webhook claims."""
    __tablename__ = "mock_provider_transactions"
    merchant_ref: Mapped[str] = mapped_column(unique=True)
    provider_ref: Mapped[str] = mapped_column(unique=True)
    provider: Mapped[str]
    amount_ugx: Mapped[int]
    currency: Mapped[str] = mapped_column(default="UGX")
    status: Mapped[str] = mapped_column(default="PENDING")
