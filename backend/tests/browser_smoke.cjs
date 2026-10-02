// Real Chrome smoke test via its local DevTools protocol; no npm dependencies.
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const base = process.argv[2];
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'securityops-browser-'));
const chrome = spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  ['--headless=new', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], {stdio:'ignore', windowsHide:true});
let socket;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function poll(fn) {
  for (let i=0;i<150;i++) { const result = await fn(); if(result) return result; await delay(100); }
  throw new Error('Timed out waiting for browser state');
}
(async () => {
  console.log('Iniciando comprobación en Chrome…');
  const portFile = path.join(profile, 'DevToolsActivePort');
  await poll(() => fs.existsSync(portFile));
  const port = fs.readFileSync(portFile,'utf8').split('\n')[0];
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {method:'PUT'})).json();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject) => {socket.onopen=resolve;socket.onerror=reject;});
  let sequence=0;
  const pending = new Map();
  socket.onmessage = event => { const data=JSON.parse(event.data); if(pending.has(data.id)) { const {resolve,reject}=pending.get(data.id); pending.delete(data.id); data.error ? reject(new Error(JSON.stringify(data.error))) : resolve(data.result); } };
  socket.onclose = event => { for(const {reject} of pending.values()) reject(new Error('DevTools closed: '+event.code+' '+event.reason)); };
  socket.onerror = event => { console.error('DevTools connection error',event.message); };
  function command(method,params={}) {return new Promise((resolve,reject) => {
    const id=++sequence;
    const timer=setTimeout(()=>reject(new Error('DevTools timeout: '+method)),10000);
    pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});
    socket.send(JSON.stringify({id,method,params}));
  });}
  async function evaluate(expression) {
    const result=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if(result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  const wait = expression => poll(() => evaluate(expression));
  await command('Page.enable');
  await command('Emulation.setDeviceMetricsOverride',{width:1280,height:900,deviceScaleFactor:1,mobile:false});
  await command('Emulation.setTimezoneOverride',{timezoneId:'America/Argentina/Buenos_Aires'});
  await command('Page.navigate',{url:base});
  await wait(`document.getElementById('list-feedback')?.textContent.includes('Todavía')`);
  assert.equal(await evaluate(`document.documentElement.lang`),'es');
  await evaluate(`document.getElementById('new-button').click()`);
  const payload = '<img src=x onerror="window.xss=true">';
  await evaluate(`(() => {const f=document.getElementById('create-form');f.elements.title.value=${JSON.stringify(payload)};f.elements.description.value='Descripción de prueba <script>alert(1)</script>';f.elements.severity.value='high';f.requestSubmit();})()`);
  await wait(`document.getElementById('detail-content').hidden === false && document.getElementById('history-feedback').textContent.includes('Todavía')`);
  assert.equal(await evaluate(`document.getElementById('detail-title').textContent`),payload);
  assert.equal(await evaluate(`document.getElementById('detail-title').querySelector('img') === null && !window.xss`),true);
  await evaluate(`document.getElementById('status-form').elements.status.value='investigating';document.getElementById('status-form').requestSubmit()`);
  await wait(`document.getElementById('history-list').textContent.includes('Abierto → En investigación')`);
  await evaluate(`document.getElementById('note-form').elements.content.value='   ';document.getElementById('note-form').requestSubmit()`);
  await wait(`document.getElementById('message').textContent.includes('entre 1 y 5000')`);
  await evaluate(`document.getElementById('note-form').elements.content.value=${JSON.stringify('  '+payload+'  ')};document.getElementById('note-form').requestSubmit()`);
  await wait(`document.getElementById('notes-list').children.length === 1`);
  assert.equal(await evaluate(`document.querySelector('#notes-list p').textContent`),payload);
  assert.equal(await evaluate(`document.querySelector('#notes-list img') === null && !window.xss`),true);
  assert.equal(await evaluate(`document.querySelector('#notes-list time').textContent === new Intl.DateTimeFormat('es',{dateStyle:'medium',timeStyle:'short'}).format(new Date(document.querySelector('#notes-list time').dateTime))`),true);
  await evaluate(`document.getElementById('back-button').click()`);
  await wait(`document.querySelectorAll('.incident').length === 1`);
  await evaluate(`document.getElementById('filter-form').elements.status.value='resolved';document.getElementById('filter-form').requestSubmit()`);
  await wait(`document.getElementById('list-feedback').textContent.includes('coincidan')`);
  await evaluate(`const f=document.getElementById('filter-form');f.elements.status.value='investigating';f.elements.severity.value='high';f.requestSubmit()`);
  await wait(`document.querySelectorAll('.incident').length === 1`);
  await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  assert.equal(await evaluate(`document.documentElement.scrollWidth <= window.innerWidth`),true);
  await evaluate(`document.querySelector('.incident-title').click()`);
  await wait(`document.getElementById('notes-list').children.length === 1 && !document.getElementById('detail-content').hidden`);
  assert.equal(await evaluate(`document.documentElement.scrollWidth <= window.innerWidth`),true);
  // Exercise the network failure message, then restore and retry.
  await evaluate(`window.originalFetch=window.fetch;window.fetch=async()=>{throw new TypeError('offline')};document.getElementById('back-button').click()`);
  await wait(`document.getElementById('list-feedback').textContent.includes('No se pudo conectar')`);
  await evaluate(`window.fetch=window.originalFetch;document.getElementById('filter-form').requestSubmit()`);
  await wait(`document.querySelectorAll('.incident').length === 1`);
  const docs=await fetch(base+'/docs');assert.equal(docs.status,200);
  console.log('OK: creación, detalle, estado, historial, notas, filtros, listas vacías, XSS, fechas locales, errores de red, /docs y anchos 1280/390.');
  await command('Browser.close');
})().catch(error => { console.error(error);process.exitCode=1; }).finally(async () => {
  if(socket) socket.close();
  if(chrome.exitCode===null) {chrome.kill(); await delay(500);}
  const resolvedProfile=path.resolve(profile);
  assert.equal(path.dirname(resolvedProfile),path.resolve(os.tmpdir()));
  assert.ok(path.basename(resolvedProfile).startsWith('securityops-browser-'));
  fs.rmSync(resolvedProfile,{recursive:true,force:true,maxRetries:10,retryDelay:200});
});
