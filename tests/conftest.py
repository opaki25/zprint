import io
import os
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from zprint.api import create_app
from zprint.config import Settings
from zprint.seed import seed


def pdf_bytes(pages=15):
    writer, buffer = PdfWriter(), io.BytesIO()
    for i in range(pages):
        page = writer.add_blank_page(width=595, height=842)
        # Distinct page dimensions make page selection/copy ordering testable.
        page.mediabox.upper_right = (595 + i, 842)
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = os.getenv("TEST_DATABASE_URL", "sqlite:///" + str(tmp_path / "test.db"))
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    cfg = Settings(database_url=url, data_dir=tmp_path / "documents", admin_key="test-admin", agent_key="test-agent", webhook_secret="test-secret")
    app = create_app(cfg)
    # TEST_DATABASE_URL must refer to a disposable CI database.
    if os.getenv("TEST_DATABASE_URL"):
        from zprint.models import Base
        with app.state.factory.begin() as db:
            for table in reversed(Base.metadata.sorted_tables):
                db.execute(table.delete())
    seed(app.state.factory)
    with TestClient(app) as test:
        yield test


@pytest.fixture
def auth(client):
    session = client.post("/api/v1/sessions", json={"station_code": "ST001"}).json()
    return {"Authorization": "Bearer " + session["token"]}


@pytest.fixture
def agent_headers():
    return {"X-Agent-Key": "test-agent"}


def ready(client, headers, **overrides):
    return client.post("/api/v1/agent/heartbeat", headers=headers, json=dict(state="READY", paper_status="SUFFICIENT", toner_status="SUFFICIENT") | overrides)


def order(client, auth, pages=15, copies=2, duplex=True):
    upload = client.post("/api/v1/documents", headers=auth, files={"file": ("sample.pdf", pdf_bytes(pages), "application/pdf")})
    assert upload.status_code == 201, upload.text
    quote = client.post("/api/v1/quotes", headers=auth, json={"document_id": upload.json()["id"], "copies": copies, "duplex": duplex})
    assert quote.status_code == 201, quote.text
    job = client.post("/api/v1/jobs", headers=auth, json={"quote_id": quote.json()["id"]})
    return upload.json(), quote.json(), job.json()


def pay(client, auth, job, provider="MTN"):
    return client.post("/api/v1/payments/initiate", headers=auth, json={"job_id": job["id"], "provider": provider, "msisdn": "+256771234567"})


def settle(client, auth, payment, status="SUCCEEDED"):
    response = client.post(f'/api/v1/demo/payments/{payment["id"]}/settle', headers={"X-Admin-Key": "test-admin"}, json={"status": status})
    assert response.status_code == 200, response.text
    return client.post(f'/api/v1/payments/{payment["id"]}/reconcile', headers=auth)
