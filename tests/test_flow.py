import io
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from pypdf import PdfReader
from sqlalchemy import select
from zprint.models import Attempt, Document, Event, Job, MockTransaction, Payment, Quote, Reading, Tier, now
from zprint.maintenance import cleanup
from zprint_agent.worker import AgentWorker
from conftest import order, pay, pdf_bytes, ready, settle


def test_end_to_end(client, auth, agent_headers, tmp_path):
    ready(client, agent_headers)
    doc, quote, job = order(client, auth)
    assert (doc["page_count"], quote["printed_sides"], quote["sheets"], quote["total_ugx"]) == (15, 30, 16, 6000)
    payment = pay(client, auth, job).json()
    assert client.get("/api/v1/agent/jobs/next", headers=agent_headers).json() == {"job": None}
    assert settle(client, auth, payment).json()["status"] == "SUCCEEDED"
    client.headers.update(agent_headers)
    worker = AgentWorker(client, tmp_path / "agent")
    assert worker.tick() == job["id"]
    assert worker.tick() is None
    result = client.get(f'/api/v1/jobs/{job["id"]}', headers=auth).json()
    assert result["status"] == "COMPLETED"
    assert result["receipt"]["total_ugx"] == 6000
    assert result["completion_evidence"] == "SIMULATED_OUTPUT_ONLY"
    assert [event['event_type'] for event in result['events']] == ['AWAITING_PAYMENT','PAYMENT_PENDING','PAID','QUEUED','PRINTING','COMPLETED']
    output = tmp_path / "agent" / "spool" / (job["id"] + ".pdf")
    pages = PdfReader(output).pages
    assert len(pages) == 32  # Odd duplex padding is physical output, not billable sides.
    assert float(pages[0].mediabox.width) == float(pages[16].mediabox.width) == 595
    assert len(list((tmp_path / "agent").glob("*.download.pdf"))) == 0
    with client.app.state.factory() as db:
        assert len(db.scalars(select(Attempt)).all()) == 1
        assert len(db.scalars(select(Event).where(Event.event_type == "PAID")).all()) == 1
    worker.close()


@pytest.mark.parametrize("sides,total", [(9,2700),(10,2500),(29,7250),(30,6000),(99,19800),(100,15000)])
def test_thresholds(client, auth, sides, total):
    _, quote, _ = order(client, auth, pages=sides, copies=1)
    assert quote["total_ugx"] == total


def test_private_upload_and_validation(client, auth):
    doc, _, _ = order(client, auth)
    other = client.post('/api/v1/sessions', json={"station_code":"ST001"}).json()
    headers = {"Authorization":"Bearer " + other["token"]}
    assert client.get(f'/api/v1/documents/{doc["id"]}/preview',headers=headers).status_code == 404
    assert client.get(f'/api/v1/documents/{doc["id"]}/preview',headers=auth).status_code == 200
    assert client.post('/api/v1/documents',headers=auth,files={"file":("bad.pdf",b"not pdf","application/pdf")}).status_code == 422
    assert client.post('/api/v1/documents',headers=auth,files={"file":("bad.docx",b"PK","application/octet-stream")}).status_code == 415
    assert client.post('/api/v1/quotes',headers=auth,json={"document_id":doc["id"],"mode":"COLOUR"}).status_code == 422
    assert client.post('/api/v1/quotes',headers=auth,json={"document_id":doc["id"],"page_range":"0-999999999"}).status_code == 422
    assert client.post('/api/v1/quotes',headers=auth,json={"document_id":doc["id"],"copies":0}).status_code == 422
    assert client.post('/api/v1/quotes',headers=auth,json={"document_id":doc["id"],"total_ugx":1}).status_code == 422
    response = client.post('/api/v1/quotes',headers=auth,json={"document_id":doc["id"],"page_range":"1-3,3,5","copies":2,"duplex":True}).json()
    assert (response["printed_sides"], response["sheets"]) == (8,4)


@pytest.mark.parametrize("overrides", [{"state":"NOT_READY"},{"state":"UNKNOWN"},{"paper_status":"EMPTY"},{"errors":["paper-jam"]}])
def test_readiness_blocks_payment(client, auth, agent_headers, overrides):
    ready(client, agent_headers, **overrides)
    _, _, job = order(client, auth)
    assert pay(client, auth, job).status_code == 409


def test_bulk_unknown_and_stale(client, auth, agent_headers):
    ready(client, agent_headers, paper_status="UNKNOWN")
    _, _, job = order(client, auth, pages=100, copies=1)
    assert pay(client, auth, job).status_code == 409
    ready(client, agent_headers)
    with client.app.state.factory.begin() as db:
        db.scalar(select(Reading)).observed_at = now() - 100
    assert pay(client, auth, job).status_code == 409


def test_webhook_verifies_ledger_and_replays(client, auth, agent_headers):
    ready(client, agent_headers)
    _, _, job = order(client, auth)
    payment = pay(client, auth, job).json()
    body = json.dumps({"merchant_ref":payment["merchant_ref"],"status":"SUCCEEDED"}).encode()
    path = '/api/v1/payments/webhook'
    assert client.post(path,content=body,headers={"X-Signature":"spoof"}).status_code == 401
    headers = {"X-Signature":client.app.state.gateway.sign(body)}
    assert client.post(path,content=body,headers=headers).json()["status"] == "PENDING"
    client.post(f'/api/v1/demo/payments/{payment["id"]}/settle',headers={"X-Admin-Key":"test-admin"},json={"status":"SUCCEEDED"})
    assert client.get(f'/api/v1/jobs/{job["id"]}',headers=auth).json()["status"] == "AWAITING_PAYMENT"
    assert client.post(path,content=body,headers=headers).json()["status"] == "SUCCEEDED"
    assert client.post(path,content=body,headers=headers).json()["duplicate"] is True
    assert client.get('/api/v1/agent/jobs/next',headers=agent_headers).json()["job"]["id"] == job["id"]
    assert client.get('/api/v1/agent/jobs/next',headers=agent_headers).json()["job"] is None


@pytest.mark.parametrize("field,value",[("amount_ugx",1),("currency","USD"),("provider","AIRTEL"),("provider_ref","wrong")])
def test_mismatched_payment_never_prints(client, auth, agent_headers, field, value):
    ready(client,agent_headers)
    _,_,job=order(client,auth)
    payment=pay(client,auth,job).json()
    with client.app.state.factory.begin() as db:
        tx=db.scalar(select(MockTransaction))
        tx.status="SUCCEEDED"
        setattr(tx,field,value)
    assert client.post(f'/api/v1/payments/{payment["id"]}/reconcile',headers=auth).status_code==409
    assert client.get('/api/v1/agent/jobs/next',headers=agent_headers).json()["job"] is None


def test_retry_and_quote_idempotency(client, auth, agent_headers):
    ready(client,agent_headers)
    _,quote,job=order(client,auth)
    assert client.post('/api/v1/jobs',headers=auth,json={"quote_id":quote["id"]}).json()["id"]==job["id"]
    payment=pay(client,auth,job).json()
    assert pay(client,auth,job).json()["id"]==payment["id"]
    assert settle(client,auth,payment,"FAILED").json()["status"]=="FAILED"
    retry=pay(client,auth,job,"AIRTEL").json()
    assert retry["id"]!=payment["id"]
    assert settle(client,auth,retry).json()["status"]=="SUCCEEDED"
    assert pay(client,auth,job).status_code==409


def test_readiness_recheck_and_claim_expiry(client, auth, agent_headers):
    ready(client,agent_headers)
    _,_,job=order(client,auth)
    settle(client,auth,pay(client,auth,job).json())
    ready(client,agent_headers,state="NOT_READY")
    assert client.get('/api/v1/agent/jobs/next',headers=agent_headers).status_code==409
    ready(client,agent_headers)
    client.get('/api/v1/agent/jobs/next',headers=agent_headers)
    ready(client,agent_headers,state="NOT_READY")
    assert client.post(f'/api/v1/agent/jobs/{job["id"]}/events',headers=agent_headers,json={"event_id":"dispatch-intent-1234","state":"PRINTING"}).status_code==409
    with client.app.state.factory.begin() as db:
        db.get(Job,job["id"]).lease_until=now()-1
    assert client.get('/api/v1/agent/jobs/next',headers=agent_headers).json()["job"] is None
    assert client.get(f'/api/v1/jobs/{job["id"]}',headers=auth).json()["status"]=="COMPLETION_UNCERTAIN"


def test_retention_expiry_and_immutable_prices(client, auth, agent_headers):
    ready(client,agent_headers)
    doc,quote,job=order(client,auth)
    with client.app.state.factory.begin() as db:
        for tier in db.scalars(select(Tier)):
            tier.rate_ugx=999
        db.get(Quote,quote["id"]).expires_at=now()-1
    assert client.get(f'/api/v1/quotes/{quote["id"]}',headers=auth).json()["total_ugx"]==6000
    assert pay(client,auth,job).status_code==410
    with client.app.state.factory.begin() as db:
        db.get(Document,doc["id"]).expires_at=now()-1
    assert cleanup(client.app.state.factory,client.app.state.settings.data_dir)==1
    assert client.get(f'/api/v1/documents/{doc["id"]}/preview',headers=auth).status_code==410
    assert not list(client.app.state.settings.data_dir.glob('*.pdf'))


def test_concurrent_claim_at_most_once(client,auth,agent_headers):
    ready(client,agent_headers)
    _,_,job=order(client,auth)
    settle(client,auth,pay(client,auth,job).json())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:client.get('/api/v1/agent/jobs/next',headers=agent_headers),range(2)))
    assert sum(r.status_code==200 and r.json().get('job') is not None for r in results)==1


def test_admin_and_agent_auth(client):
    assert client.get('/api/v1/admin/reports').status_code==401
    assert client.get('/api/v1/agent/jobs/next').status_code==401
    assert client.post('/api/v1/sessions',json={"station_code":"unknown"}).status_code==404


def test_encrypted_and_active_pdfs_rejected(client,auth):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, DictionaryObject
    for encrypted in (True,False):
        writer=PdfWriter(); writer.add_blank_page(595,842)
        if encrypted: writer.encrypt('password')
        else: writer._root_object[NameObject('/OpenAction')]=DictionaryObject()
        buffer=io.BytesIO(); writer.write(buffer)
        assert client.post('/api/v1/documents',headers=auth,files={'file':('file.pdf',buffer.getvalue(),'application/pdf')}).status_code==422
