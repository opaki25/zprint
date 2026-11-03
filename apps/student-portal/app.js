const $ = id => document.getElementById(id);
const state = {token: sessionStorage.getItem('zprint-token'), document: null, quote: null, job: sessionStorage.getItem('zprint-job'), payment: sessionStorage.getItem('zprint-payment'), preview: null};
const station = new URLSearchParams(location.search).get('station') || 'ST001';
const money = n => new Intl.NumberFormat('en-UG').format(n);
let maxUploadBytes = 20 * 1024 * 1024;
async function api(path, {method='GET', body, admin=false}={}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (admin) headers['X-Admin-Key'] = $('admin-key').value;
  if (body && !(body instanceof FormData)) {headers['Content-Type'] = 'application/json'; body = JSON.stringify(body);}
  const response = await fetch(`/api/v1${path}`, {method, headers, body});
  if (!response.ok) {const error = await response.json().catch(()=>({detail:`Request failed (${response.status}). Please try again.`})); throw new Error(typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail));}
  return response;
}
function handle(fn) {return async () => { $('error').textContent = ''; try {await fn();} catch(e) {$('error').textContent = e.message;} };}
function invalidate() {state.quote = null; $('pay').disabled = true; $('total').textContent = '— UGX'; $('breakdown').textContent = 'Calculate a new quote for these settings.';}
async function init() {
  const response = await fetch('/deployment.json');
  if (!response.ok) throw new Error('Could not read portal configuration. Reload to try again.');
  const deployment = await response.json();
  maxUploadBytes = deployment.max_upload_bytes;
  $('deployment-notice').textContent = deployment.message;
  $('upload-limit').textContent = `PDF only · Up to ${maxUploadBytes / 1024 / 1024} MiB / 500 pages`;
  if (!deployment.backend_configured) {
    $('station-state').textContent = 'Backend not connected';
    $('status').textContent = 'Portal preview';
    $('message').textContent = 'Printing becomes available after the backend is connected.';
    state.job = null;
    return;
  }
  const info = await (await api(`/stations/${encodeURIComponent(station)}`)).json();
  $('station-name').textContent = info.code;
  $('station-state').textContent = `${info.readiness === 'READY' ? '● Ready to print' : '○ Agent not ready'} · ${info.name}`;
  if (!state.token) {const s = await (await api('/sessions', {method:'POST', body:{station_code:station}})).json(); state.token = s.token; sessionStorage.setItem('zprint-token', s.token);}
  $('file').disabled = false;
  if (state.job) await poll();
}
$('file').addEventListener('change', handle(async () => {
  const file = $('file').files[0];
  if (!file) return;
  invalidate(); state.document = null;
  $('quote').disabled = true; $('preview').disabled = true;
  if (state.preview) { URL.revokeObjectURL(state.preview); state.preview = null; }
  $('file').disabled = true;
  $('document-info').textContent = 'Validating PDF and counting pages…';
  try {
    if (file.size > maxUploadBytes) throw new Error(`This portal accepts PDFs up to ${maxUploadBytes / 1024 / 1024} MiB.`);
    const form = new FormData(); form.append('file', file);
    state.document = await (await api('/documents', {method:'POST', body:form})).json();
    $('document-info').textContent = `${state.document.original_name} · ${state.document.page_count} pages · ready. ${(state.document.warnings || []).join(' ')}`;
    $('quote').disabled = false; $('preview').disabled = false;
  } catch (error) {
    $('document-info').textContent = `Upload failed. ${error.message}`;
    throw error;
  } finally {
    $('file').disabled = false;
    $('file').value = ''; // Selecting the same file again must trigger a fresh upload.
  }
}));
for (const id of ['copies','pages','mode','duplex']) $(id).addEventListener('input', invalidate);
$('preview').addEventListener('click', handle(async () => {
  const response = await api(`/documents/${state.document.id}/preview`);
  if (state.preview) URL.revokeObjectURL(state.preview);
  state.preview = URL.createObjectURL(await response.blob());
  window.open(state.preview, '_blank', 'noopener');
}));
$('quote').addEventListener('click', handle(async () => {
  state.quote = await (await api('/quotes', {method:'POST',body:{document_id:state.document.id,copies:Number($('copies').value),page_range:$('pages').value,mode:$('mode').value,duplex:$('duplex').value==='true',paper_size:'A4'}})).json();
  $('total').textContent = `${money(state.quote.total_ugx)} UGX`;
  $('breakdown').textContent = `${state.quote.printed_sides} printed sides · ${state.quote.sheets} sheets · UGX ${money(state.quote.rate_ugx)}/side. Quote valid for 10 minutes.`;
  $('pay').disabled = false;
}));
$('pay').addEventListener('click', handle(async () => {
  $('pay').disabled = true;
  try {
    const job = await (await api('/jobs', {method:'POST',body:{quote_id:state.quote.id}})).json();
    state.job = job.id; sessionStorage.setItem('zprint-job',job.id);
    const payment = await (await api('/payments/initiate', {method:'POST',body:{job_id:job.id,provider:$('provider').value,msisdn:$('phone').value}})).json();
    state.payment = payment.id; sessionStorage.setItem('zprint-payment',payment.id);
    $('settle').disabled = false; $('fail').disabled = false; $('demo-controls').open = true;
    $('message').textContent = 'Payment pending. Use the demo operator controls to settle the simulated provider transaction.';
    await poll();
  } catch(e) {$('pay').disabled = false; throw e;}
}));
async function settle(status) {
  await api(`/demo/payments/${state.payment}/settle`, {method:'POST',body:{status},admin:true});
  await api(`/payments/${state.payment}/reconcile`, {method:'POST'});
  $('settle').disabled = true; $('fail').disabled = true; $('admin-key').value = '';
  await poll();
}
$('settle').addEventListener('click',handle(()=>settle('SUCCEEDED')));
$('fail').addEventListener('click',handle(()=>settle('FAILED')));
async function poll() {
  if (!state.job) return;
  const job = await (await api(`/jobs/${state.job}`)).json();
  $('status').textContent = job.status.replaceAll('_',' ');
  const messages = {PAID:'Payment independently verified. Waiting for the local print agent.',QUEUED:'Your job has been safely claimed by the agent.',PRINTING:'The simulated printer is preparing your output.',COMPLETED:'Demo complete. A simulated PDF output was produced; no physical pages were printed.',PAYMENT_FAILED:'Payment failed. You may retry before the quote expires.',COMPLETION_UNCERTAIN:'Printing outcome is uncertain. An operator must investigate; no automatic reprint.',PAUSED:'Your paid job is held for operator assistance.'};
  if (messages[job.status]) $('message').textContent = messages[job.status];
  $('events').replaceChildren(...job.events.map(event=>{const li=document.createElement('li');li.textContent=event.event_type.replaceAll('_',' ');return li;}));
  if (job.receipt) $('receipt').textContent = `SIMULATED RECEIPT · UGX ${money(job.receipt.total_ugx)} · Reference ${job.id}`;
  if (job.status==='PAYMENT_FAILED' && state.quote) $('pay').disabled = false;
  if (job.status==='AWAITING_PAYMENT' && state.payment) {$('settle').disabled=false;$('fail').disabled=false;}
}
$('reset').addEventListener('click',()=>{sessionStorage.clear();location.reload();});
handle(init)();
setInterval(()=>{if(state.job) handle(poll)();},3000);
