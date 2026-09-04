const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
assert.match(html, /<title>BlueNode<\/title>/);
assert.match(html, /<h1>BlueNode<\/h1>/);
assert.match(html, /<h2>BlueNode Intelligence<\/h2>/);
assert.doesNotMatch(html, />NodeSmart(?: Intelligence| Controls)?</);
const disk = html.indexOf('id="disk"');
const controls = html.indexOf('<h2>BlueNode Controls</h2>');
const connectionStats = html.indexOf('id="connections-today"');
const intelligence = html.indexOf('<h2>BlueNode Intelligence</h2>');
const sessions = html.indexOf('<h2>Recent Sessions</h2>');
const events = html.indexOf('<h2>Recent Events</h2>');
const recovery = html.indexOf('<h2>Automatic Recovery</h2>');
assert.ok(disk < connectionStats && connectionStats < controls,
  'Status cards and connection statistics must remain together before Controls');
assert.ok(intelligence < sessions && sessions < events,
  'Intelligence must immediately precede Recent Sessions and Recent Events');
assert.ok(controls < intelligence && events < recovery,
  'Controls must precede Intelligence and remaining content must follow Events');
assert.match(html, /\.grid\s*\+\s*\.grid\s*{[^}]*margin-top:\s*15px/s,
  'Adjacent telemetry grids must use the same 15px gap as card rows');
assert.match(html, /\.controls-panel\s*{[^}]*margin-top:\s*18px/s,
  'Controls must retain a slightly larger gap below the telemetry grids');
assert.equal(html.slice(intelligence, sessions).match(/<h2>/g)?.length, 1,
  'No section heading may appear between Intelligence and Recent Sessions');
for (const id of ['disk', 'connections-today', 'control-result',
  'intelligence-panel', 'recent-sessions', 'events',
  'btn-dodropin-connect', 'btn-dodropin-disconnect', 'btn-skywarn-on',
  'btn-skywarn-off', 'manual-node-number', 'node-directory-search']) {
  assert.equal(html.split('id="' + id + '"').length - 1, 1,
    'Moved element ID must remain unique: ' + id);
}
for (const handler of ["runControl('dodropin-connect', this)",
  "runControl('dodropin-disconnect', this)",
  "runControl('skywarn-enable', this)",
  "runControl('skywarn-disable', this)",
  "runNodeControl('node-connect', this)",
  "runNodeControl('node-disconnect', this)", 'searchAllStarNodes()']) {
  assert.ok(html.includes('onclick="' + handler + '"'),
    'Control handler must remain wired: ' + handler);
}
assert.match(html, /fetch\('\/api\/control\/' \+ action/,
  'Control API endpoint must remain unchanged');
assert.match(html, /\.controls-grid\s*{[^}]*grid-template-columns:\s*repeat\(4,/s,
  'Quick actions must use a four-column desktop row');
assert.match(html, /@media \(max-width: 750px\)[\s\S]*?\.controls-grid\s*{[\s\S]*?repeat\(2,/,
  'Quick actions must collapse to two columns on smaller screens');
assert.match(html, /@media \(max-width: 480px\)[\s\S]*?\.controls-grid\s*{[\s\S]*?1fr/,
  'Quick actions must collapse to one column on narrow screens');
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
