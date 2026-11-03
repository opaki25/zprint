from zprint_agent.worker import AgentWorker
from conftest import order, pay, ready, settle


def test_paid_queue_backlog_recovers_after_printer_outage(client, auth, agent_headers, tmp_path):
    ready(client, agent_headers)
    jobs = []
    for pages in (15, 100):
        _, _, job = order(client, auth, pages=pages, copies=1)
        settle(client, auth, pay(client, auth, job).json())
        jobs.append(job)
    client.headers.update(agent_headers)
    directory = tmp_path / 'agent'
    worker = AgentWorker(client, directory)
    (directory / 'printer-state.txt').write_text('NOT_READY')
    assert worker.tick() is None
    assert all(client.get(f'/api/v1/jobs/{job["id"]}', headers=auth).json()['status'] == 'PAID' for job in jobs)
    (directory / 'printer-state.txt').write_text('READY')
    printed = {worker.tick(), worker.tick()}
    assert printed == {job['id'] for job in jobs}
    assert worker.tick() is None
    assert all(client.get(f'/api/v1/jobs/{job["id"]}', headers=auth).json()['status'] == 'COMPLETED' for job in jobs)
    worker.close()
