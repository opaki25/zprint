import httpx
from zprint_agent.worker import AgentWorker
from conftest import order, pay, ready, settle


def test_restart_does_not_reprint(client, auth, agent_headers, tmp_path):
    ready(client,agent_headers)
    _,_,job=order(client,auth)
    settle(client,auth,pay(client,auth,job).json())
    client.headers.update(agent_headers)
    client.get('/api/v1/agent/jobs/next')
    worker=AgentWorker(client,tmp_path/'agent')
    with worker.db:
        worker.db.execute("INSERT INTO jobs VALUES(?, 'DISPATCHING', NULL, 0)",(job['id'],))
    worker.close()
    restarted=AgentWorker(client,tmp_path/'agent')
    restarted.tick()
    assert client.get(f'/api/v1/jobs/{job["id"]}',headers=auth).json()['status']=='COMPLETION_UNCERTAIN'
    assert not list((tmp_path/'agent'/'spool').glob('*.pdf'))
    restarted.close()


def test_outbox_replay_after_connection_loss(client,auth,agent_headers,tmp_path):
    ready(client,agent_headers)
    _,_,job=order(client,auth)
    settle(client,auth,pay(client,auth,job).json())
    client.headers.update(agent_headers)
    client.get('/api/v1/agent/jobs/next')
    client.post(f'/api/v1/agent/jobs/{job["id"]}/events',json={'event_id':'printing-event-12345','state':'PRINTING'})
    worker=AgentWorker(client,tmp_path/'agent')
    with worker.db:
        worker.db.execute("INSERT INTO jobs VALUES(?, 'DISPATCHING', NULL, 0)",(job['id'],))
    worker.enqueue(job['id'],'COMPLETED','simulated-output.pdf')
    class Offline:
        def post(self,*args,**kwargs): raise httpx.ConnectError('offline')
    worker.client=Offline()
    try: worker.flush()
    except httpx.ConnectError: pass
    assert worker.db.execute('SELECT delivered FROM outbox').fetchone()[0]==0
    worker.close()
    restarted=AgentWorker(client,tmp_path/'agent')
    restarted.tick()
    assert client.get(f'/api/v1/jobs/{job["id"]}',headers=auth).json()['status']=='COMPLETED'
    assert restarted.db.execute('SELECT delivered FROM outbox').fetchone()[0]==1
    restarted.close()
