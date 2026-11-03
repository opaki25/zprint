const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function setup(uploadResponse) {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {value:'', files:[], disabled:false, textContent:'', handlers:{},
      addEventListener(event, handler) {this.handlers[event]=handler;}, replaceChildren() {}});
    return elements.get(id);
  };
  const context = vm.createContext({
    document:{getElementById:element}, location:{search:'',reload(){}},
    sessionStorage:{getItem(){return null;},setItem(){},clear(){}},
    URLSearchParams, Intl, Number, JSON, Error, FormData: class {append(){}},
    URL:{revokeObjectURL(){}}, setInterval(){},
    fetch:async path => ({ok:true,json:async()=>path==='/deployment.json' ? {backend_configured:true,max_upload_bytes:20*1024*1024,message:'test'} : path.includes('/stations/') ? {code:'ST001',readiness:'READY',name:'Test'} : path.endsWith('/sessions') ? {token:'test'} : uploadResponse}),
  });
  vm.runInContext(fs.readFileSync('apps/student-portal/app.js','utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  return {element,context};
}

test('failed upload clears stale document and exits validating state',async()=>{
  const {element,context}=await setup({});
  vm.runInContext("state.document={id:'previous'};state.preview='blob:previous';",context);
  context.fetch=async()=>({ok:false,status:422,json:async()=>({detail:'This PDF contains unsupported annotations.'})});
  element('file').files=[{size:100}];
  await element('file').handlers.change();
  assert.match(element('document-info').textContent,/Upload failed/);
  assert.doesNotMatch(element('document-info').textContent,/Validating/);
  assert.equal(element('quote').disabled,true);
  assert.equal(element('preview').disabled,true);
  assert.equal(element('file').disabled,false);
  assert.equal(element('file').value,'');
  assert.equal(vm.runInContext('state.document',context),null);
});

test('successful upload displays count and link-removal notice',async()=>{
  const {element}=await setup({id:'new',original_name:'lecture.pdf',page_count:19,warnings:['Clickable links were removed from the print copy.']});
  element('file').files=[{size:100}];
  await element('file').handlers.change();
  assert.match(element('document-info').textContent,/19 pages/);
  assert.match(element('document-info').textContent,/Clickable links/);
  assert.equal(element('quote').disabled,false);
  assert.equal(element('preview').disabled,false);
  assert.equal(element('file').disabled,false);
});
