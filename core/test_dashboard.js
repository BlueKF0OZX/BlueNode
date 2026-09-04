const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
const start = html.indexOf('    async function loadRecoveryStatus()');
const end = html.indexOf('    let statusLoading', start);
const elements = {};
function element(id) {
  return elements[id] ||= {textContent:'', className:'', classList:{add(){}, remove(){}}};
}
let display;
const context = vm.createContext({Date, Number, Object, Error,
  document: {getElementById:element},
  fetch: async url => ({ok:true, json:async()=>url.includes('intelligence')
    ? {recovery_display:display} : {last_recovery:{status:'failed'}}})
});
vm.runInContext(html.slice(start,end),context);
(async()=>{
  display=null;
  await context.loadRecoveryStatus();
  assert.equal(element('recovery-status').textContent,'Ready');
  assert.equal(element('recovery-detail').textContent,'');
  display={status:'failed', component:'asterisk', message:'Restart failed'};
  await context.loadRecoveryStatus();
  assert.equal(element('recovery-status').textContent,'Recovery failed');
  display={status:'lockout',component:'asterisk',message:'Rate limited'};
  await context.loadRecoveryStatus();
  assert.equal(element('recovery-status').textContent,'Recovery locked out');
  display=null;
  await context.loadRecoveryStatus();
  assert.equal(element('recovery-status').className,'value normal');
  const statusStart=html.indexOf('    let statusLoading');
  const statusEnd=html.indexOf('    function setValue',statusStart);
  let resolveFetch, calls=0;
  context.fetch=()=>{calls++;return new Promise(resolve=>{resolveFetch=resolve;});};
  vm.runInContext(html.slice(statusStart,statusEnd),context);
  const first=context.loadStatus();
  await context.loadStatus();
  assert.equal(calls,1,'Concurrent status refresh must be suppressed');
  resolveFetch({json:async()=>{throw new Error('Fixture failure');}});
  await first;
  const next=context.loadStatus();
  assert.equal(calls,2,'Refresh guard must reset after failure');
  resolveFetch({json:async()=>{throw new Error('Fixture failure');}});
  await next;
  console.log('Dashboard recovery transitions and polling guard passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
