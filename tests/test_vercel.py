import importlib
from pathlib import Path
import tomllib

import httpx
import pytest
from fastapi.testclient import TestClient

from vercel_app import REQUEST_LIMIT, RESPONSE_LIMIT, create_portal


def test_configured_entrypoint_exports_application():
    config = tomllib.loads(Path('pyproject.toml').read_text())
    module, name = config['tool']['vercel']['entrypoint'].split(':')
    assert getattr(importlib.import_module(module), name).title == 'Z-PRINT hosted portal'


def test_unconfigured_portal_loads_without_database_or_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(create_portal('')) as client:
        assert client.get('/').status_code == 200
        assert client.get('/app.js').status_code == 200
        assert client.get('/styles.css').status_code == 200
        assert client.get('/deployment.json').json()['backend_configured'] is False
        assert client.get('/health').json()['status'] == 'portal_available'
        response = client.post('/api/v1/sessions', json={'station_code':'ST001'})
        assert response.status_code == 503
        assert 'preview only' in response.json()['detail']
        assert response.headers['cache-control'] == 'no-store'
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('url', ['http://backend.example', 'https://user:secret@backend.example', 'https://backend.example/api', 'https://backend.example?key=secret'])
def test_invalid_origin_is_unconfigured(url):
    with TestClient(create_portal(url)) as client:
        assert client.get('/deployment.json').json()['backend_configured'] is False
        assert client.get('/api/v1/stations/ST001').status_code == 503


def test_proxy_preserves_body_authorization_query_and_status():
    seen = []
    def upstream(request):
        seen.append(request)
        return httpx.Response(409, json={'detail':'Printer not ready'}, headers={'Set-Cookie':'must-not-forward=1'})
    with TestClient(create_portal('https://backend.example', httpx.MockTransport(upstream))) as client:
        response = client.post('/api/v1/payments/initiate?attempt=1', content=b'{"job_id":"123"}',
                               headers={'Authorization':'Bearer student', 'X-Admin-Key':'provided-key', 'Content-Type':'application/json', 'Cookie':'private-cookie=1'})
        assert response.status_code == 409
        assert response.json()['detail'] == 'Printer not ready'
        assert 'set-cookie' not in response.headers
    assert str(seen[0].url) == 'https://backend.example/api/v1/payments/initiate?attempt=1'
    assert seen[0].content == b'{"job_id":"123"}'
    assert seen[0].headers['Authorization'] == 'Bearer student'
    assert seen[0].headers['X-Admin-Key'] == 'provided-key'
    assert 'cookie' not in seen[0].headers


def test_upload_and_preview_bytes_forward_unchanged():
    def upstream(request):
        assert b'%PDF-' in request.content
        assert request.headers['content-type'].startswith('multipart/form-data; boundary=')
        return httpx.Response(200, content=b'%PDF-preview', headers={'Content-Type':'application/pdf', 'Content-Disposition':'inline; filename=document.pdf'})
    with TestClient(create_portal('https://backend.example', httpx.MockTransport(upstream))) as client:
        response = client.post('/api/v1/documents', files={'file':('test.pdf',b'%PDF-test','application/pdf')})
        assert response.content == b'%PDF-preview'
        assert response.headers['content-type'] == 'application/pdf'


@pytest.mark.parametrize('kind,status', [('redirect',502),('timeout',504),('unreachable',502),('oversized',502)])
def test_upstream_failure_never_reports_success(kind, status):
    def upstream(request):
        if kind == 'redirect': return httpx.Response(307, headers={'Location':'https://other.example'})
        if kind == 'timeout': raise httpx.ReadTimeout('internal timeout')
        if kind == 'unreachable': raise httpx.ConnectError('internal failure')
        return httpx.Response(200, content=b'x'*(RESPONSE_LIMIT+1))
    with TestClient(create_portal('https://backend.example', httpx.MockTransport(upstream))) as client:
        response = client.get('/api/v1/stations/ST001')
        assert response.status_code == status
        assert 'internal' not in response.text


def test_request_limit_and_self_proxy_blocked():
    with TestClient(create_portal('https://backend.example')) as client:
        assert client.post('/api/v1/documents', content=b'x'*(REQUEST_LIMIT+1)).status_code == 413
    with TestClient(create_portal('https://testserver')) as client:
        assert client.get('/api/v1/stations/ST001').status_code == 503


def test_native_backend_deployment_metadata(client):
    data = client.get('/deployment.json').json()
    assert data['backend_configured'] is True
    assert data['max_upload_bytes'] == 20 * 1024 * 1024
