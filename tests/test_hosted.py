import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import order, pay, ready, settle
from vercel_app import create_portal
from zprint.config import Settings
from zprint.db import normalize_database_url
from zprint.hosted import first_exited, stop_children
from zprint_agent.worker import AgentWorker


@pytest.mark.parametrize('url', ['postgres://name:password@host/db?sslmode=require', 'postgresql://name:password@host/db?sslmode=require'])
def test_provider_database_url_uses_installed_driver(url):
    assert normalize_database_url(url) == 'postgresql+psycopg://name:password@host/db?sslmode=require'


def hosted_settings(tmp_path, **changes):
    values = dict(hosted=True, database_url='postgresql://user:password@example/db', data_dir=tmp_path / 'documents',
                  admin_key='a'*40, agent_key='b'*40, webhook_secret='c'*40, gateway_key='d'*40)
    return Settings(**(values | changes))


@pytest.mark.parametrize('changes', [{'admin_key':'local-demo-admin-change-me'}, {'gateway_key':''}, {'agent_key':'a'*40}, {'database_url':'sqlite:///local.db'}])
def test_hosted_configuration_fails_closed(tmp_path, changes):
    with pytest.raises(RuntimeError):
        hosted_settings(tmp_path, **changes).validate()
    assert not (tmp_path / 'documents').exists()


def test_hosted_configuration_accepts_generated_credentials(tmp_path):
    cfg = hosted_settings(tmp_path)
    cfg.validate()
    assert cfg.data_dir.is_dir()


def test_direct_backend_requires_gateway_without_exposing_secret(client):
    client.app.state.settings.gateway_key = 'server-only-secret'
    assert client.get('/health').status_code == 200
    assert client.post('/api/v1/sessions', json={'station_code':'ST001'}).status_code == 401
    wrong = client.get('/api/v1/stations/ST001', headers={'X-Zprint-Gateway-Key':'wrong'})
    assert wrong.status_code == 401
    assert 'server-only-secret' not in wrong.text
    assert client.get('/api/v1/stations/ST001', headers={'X-Zprint-Gateway-Key':'server-only-secret'}).status_code == 200


def test_gateway_injects_server_secret_not_browser_value():
    seen = []
    def upstream(request):
        seen.append(request.headers['x-zprint-gateway-key'])
        return httpx.Response(200,json={'ok':True})
    with TestClient(create_portal('https://backend.example', httpx.MockTransport(upstream), gateway_key='server-only')) as portal:
        result = portal.get('/api/v1/stations/ST001', headers={'X-Zprint-Gateway-Key':'attacker'})
        assert result.status_code == 200
        assert 'server-only' not in portal.get('/deployment.json').text
        assert 'server-only' not in result.text
    assert seen == ['server-only']


def test_full_print_flow_through_hosted_gateway(client, agent_headers, tmp_path):
    secret = 'gateway-integration-test'
    client.app.state.settings.gateway_key = secret
    client.headers['X-Zprint-Gateway-Key'] = secret
    ready(client, agent_headers)
    with TestClient(create_portal('https://backend.example', httpx.ASGITransport(app=client.app), gateway_key=secret)) as portal:
        session = portal.post('/api/v1/sessions',json={'station_code':'ST001'}).json()
        auth = {'Authorization':'Bearer '+session['token']}
        _, quote, job = order(portal, auth)
        assert quote['total_ugx'] == 6000
        assert settle(portal, auth, pay(portal, auth, job).json()).status_code == 200
        client.headers.update(agent_headers)
        worker = AgentWorker(client, tmp_path/'agent')
        try:
            assert worker.tick() == job['id']
            assert portal.get(f'/api/v1/jobs/{job["id"]}',headers=auth).json()['status'] == 'COMPLETED'
        finally:
            worker.close()


def test_process_manager_stops_remaining_children():
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
    children = [('test-helper', process)]
    try:
        assert first_exited(children) is None
        stop_children(children)
        assert process.poll() is not None
        assert first_exited(children)[0] == 'test-helper'
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
