"""Exercise a running backend + agent, without real payments or printer hardware."""
import io
import os
import time
import httpx
from pypdf import PdfWriter

writer, buffer = PdfWriter(), io.BytesIO()
for _ in range(15):
    writer.add_blank_page(595,842)
writer.write(buffer)


def result(response):
    response.raise_for_status()
    return response.json()


with httpx.Client(base_url=os.getenv('ZPRINT_API_URL','http://127.0.0.1:8000'),timeout=30) as client:
    if os.getenv('ZPRINT_GATEWAY_KEY'):
        client.headers['X-Zprint-Gateway-Key'] = os.environ['ZPRINT_GATEWAY_KEY']
    session=result(client.post('/api/v1/sessions',json={'station_code':'ST001'}))
    client.headers['Authorization']='Bearer '+session['token']
    doc=result(client.post('/api/v1/documents',files={'file':('demo.pdf',buffer.getvalue(),'application/pdf')}))
    quote=result(client.post('/api/v1/quotes',json={'document_id':doc['id'],'copies':2,'duplex':True}))
    assert (quote['printed_sides'],quote['sheets'],quote['total_ugx'])==(30,16,6000)
    job=result(client.post('/api/v1/jobs',json={'quote_id':quote['id']}))
    payment=result(client.post('/api/v1/payments/initiate',json={'job_id':job['id'],'provider':'MTN','msisdn':'+256771234567'}))
    result(client.post(f'/api/v1/demo/payments/{payment["id"]}/settle',headers={'X-Admin-Key':os.getenv('ZPRINT_ADMIN_KEY','local-demo-admin-change-me')},json={'status':'SUCCEEDED'}))
    result(client.post(f'/api/v1/payments/{payment["id"]}/reconcile'))
    for _ in range(30):
        status=result(client.get(f'/api/v1/jobs/{job["id"]}'))
        if status['status']=='COMPLETED':
            print(f'PASS: {job["id"]} | 30 sides | 16 sheets | UGX 6000 | SIMULATED COMPLETED')
            break
        time.sleep(1)
    else:
        raise RuntimeError(f'Agent did not complete job: {status["status"]}')
