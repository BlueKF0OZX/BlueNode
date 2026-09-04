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
const radioActivity = html.indexOf('id="radio-activity-panel"');
const intelligence = html.indexOf('<h2>BlueNode Intelligence</h2>');
const sessions = html.indexOf('<h2>Recent Sessions</h2>');
const events = html.indexOf('<h2>Recent Events</h2>');
const automation = html.indexOf('id="automation-title"');
const remoteAdmin = html.indexOf('id="remote-admin-panel"');
assert.ok(disk < connectionStats && connectionStats < radioActivity && radioActivity < controls,
  'Radio Activity must follow status/statistics and precede Controls');
assert.ok(intelligence < sessions && sessions < events,
  'Intelligence must immediately precede Recent Sessions and Recent Events');
assert.ok(controls < automation && automation < remoteAdmin && remoteAdmin < intelligence,
  'Operational order must be Controls, Automation, optional Admin, Intelligence');
assert.doesNotMatch(html, /<h2>Automatic Recovery<\/h2>|id="recovery-panel"|loadRecoveryStatus/,
  'The redundant standalone recovery presentation must remain removed');
assert.match(html, /async function loadAdminSession\(\)/);
assert.match(html, /Type RESTART ASTERISK/);
assert.match(html, /adminHeaders\(\{'Content-Type': 'application\/json'\}\)/);
assert.match(html, /\.grid\s*\+\s*\.grid\s*{[^}]*margin-top:\s*15px/s,
  'Adjacent telemetry grids must use the same 15px gap as card rows');
assert.match(html, /\.controls-panel\s*{[^}]*margin-top:\s*18px/s,
  'Controls must retain a slightly larger gap below the telemetry grids');
assert.equal(html.slice(intelligence, sessions).match(/<h2>/g)?.length, 1,
  'No section heading may appear between Intelligence and Recent Sessions');
for (const id of ['disk', 'connections-today', 'control-result',
  'connectivity-summary', 'connectivity-details',
  'radio-activity-panel', 'radio-activity-title', 'radio-activity-summary',
  'radio-local-rx', 'radio-local-tx', 'radio-node-detail', 'radio-callsign-detail',
  'radio-location-detail', 'radio-duration',
  'automation-panel', 'automation-title', 'automation-summary',
  'automation-recovery-armed', 'automation-protection',
  'automation-maintenance', 'automation-last-check', 'automation-attempts',
  'automation-backoff', 'automation-action', 'maintenance-toggle',
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
assert.match(html, /\/api\/control\/maintenance-/,
  'Maintenance Mode must use the protected control API');
assert.match(html, /\.controls-grid\s*{[^}]*grid-template-columns:\s*repeat\(4,/s,
  'Quick actions must use a four-column desktop row');
assert.match(html, /@media \(max-width: 750px\)[\s\S]*?\.controls-grid\s*,[\s\S]*?repeat\(2,/,
  'Quick actions must collapse to two columns on smaller screens');
assert.match(html, /@media \(max-width: 480px\)[\s\S]*?\.controls-grid\s*,[\s\S]*?1fr/,
  'Quick actions must collapse to one column on narrow screens');
const elements = {};
function element(id) {
  return elements[id] ||= {textContent:'', className:'', dataset:{}, style:{},
    classList:{add(){}, remove(){}}};
}
const context = vm.createContext({Date, Number, Object, Error,
  document: {getElementById:element},
  fetch: async()=>({ok:true, json:async()=>({})})
});
(async()=>{
  const connectivityStart=html.indexOf('    function renderConnectivity');
  const connectivityEnd=html.indexOf('    function radioDuration',connectivityStart);
  vm.runInContext(html.slice(connectivityStart,connectivityEnd),context);
  context.renderConnectivity({diagnosis:'healthy',last_check:new Date().toISOString(),
    checks:{interface:true,gateway:true,dns:true,internet:true,allstar:true}});
  assert.match(element('connectivity-summary').textContent,/Healthy.*Gateway OK.*DNS OK.*AllStar OK/);
  assert.match(element('connectivity-summary').textContent,/checked \d+s ago/);
  assert.equal(element('connectivity-details').style.display,'none');
  context.renderConnectivity({diagnosis:'dns_failure',checks:{interface:true,gateway:true,
    dns:false,internet:true,allstar:true},message:'DNS resolution failed',
    operator_action:'Check DNS',layers:{local_network:{status:'ok'},gateway:{status:'ok'},
      dns:{status:'fail'},internet:{status:'ok'},
      allstar_services:{status:'blocked_by_upstream'}}});
  assert.match(element('connectivity-summary').textContent,/DNS failure.*DNS FAIL.*Internet OK/);
  assert.match(element('connectivity-details').textContent,
    /DNS resolution failed.*DNS FAIL.*Internet OK.*AllStar services BLOCKED_BY_UPSTREAM.*Action: Check DNS/);
  assert.equal(element('connectivity-details').style.display,'');
  const radioStart=html.indexOf('    function radioDuration');
  const radioEnd=html.indexOf('    function automationAge',radioStart);
  vm.runInContext(html.slice(radioStart,radioEnd),context);
  context.renderRadioActivity({status:'idle',local_rx:false,local_tx:false});
  assert.match(element('radio-activity-title').textContent,/IDLE$/);
  assert.equal(element('radio-activity-summary').textContent,'No active transmission');
  context.renderRadioActivity({status:'local_rx',local_rx:true,local_tx:true,
    node:'12345',started_at:new Date(Date.now()-2000).toISOString(),
    tx_origin:{active:true,source_type:'local_rf',confidence:'verified'}});
  assert.match(element('radio-activity-title').textContent,/LOCAL RX$/);
  assert.equal(element('radio-local-tx').textContent,'Keyed');
  assert.match(element('radio-origin-detail').textContent,/Local RF receiver \(verified\)/);
  context.renderRadioActivity({status:'remote_tx',local_rx:false,local_tx:true,
    node:'54321',friendly_name:'Example Link',callsign:'W1ABC',
    display_location:'Orlando, Florida',started_at:new Date().toISOString(),
    tx_origin:{active:true,source_type:'remote_link',source_node:'54321',
      confidence:'verified_ingress'}});
  assert.match(element('radio-node-detail').textContent,/54321.*Example Link/);
  assert.equal(element('radio-callsign-detail').textContent,'Callsign: W1ABC');
  assert.equal(element('radio-location-detail').textContent,'Location: Orlando, Florida');
  assert.match(element('radio-origin-detail').textContent,/Inbound via node 54321.*verified ingress/);
  context.renderRadioActivity({status:'ambiguous',remote_rx_nodes:['11111','22222'],
    tx_origin:{active:true,source_type:'ambiguous',confidence:'ambiguous',
      reason:'Multiple immediate links are keyed'}});
  assert.match(element('radio-origin-detail').textContent,/Ambiguous.*Multiple immediate links/);
  context.renderRadioActivity({status:'remote_tx',node:'99999'});
  assert.equal(element('radio-callsign-detail').textContent,'');
  assert.equal(element('radio-location-detail').textContent,'');
  assert.equal(element('radio-callsign-detail').style.display,'none');
  context.renderRadioActivity({status:'remote_tx',stale:true});
  assert.match(element('radio-activity-title').textContent,/UNAVAILABLE$/);
  const automationStart=html.indexOf('    function automationAge');
  const automationEnd=html.indexOf('    let statusLoading',automationStart);
  context.fetch=async()=>({ok:true,json:async()=>({automation:{mode:'maintenance',maintenance_mode:true}})});
  vm.runInContext(html.slice(automationStart,automationEnd),context);
  context.renderAutomation({mode:'active',automation_armed:true,
    repeated_failure_protection:true,recovery_attempts_today:0,
    last_automation_check:new Date().toISOString()});
  assert.equal(element('automation-title').textContent,'AUTOMATION — ACTIVE');
  assert.equal(element('automation-action').textContent,'No operator action required');
  context.renderAutomation({mode:'active',automation_armed:true,connectivity_status:'offline'});
  assert.match(element('automation-summary').textContent,/no Asterisk restart/);
  context.renderAutomation({mode:'recovering',automation_armed:true,last_result:'Verifying service health'});
  assert.equal(element('automation-title').textContent,'AUTOMATION — RECOVERING');
  context.renderAutomation({mode:'recovered',automation_armed:true,last_result:'Asterisk restored'});
  assert.equal(element('automation-title').textContent,'AUTOMATION — RECOVERED');
  context.renderAutomation({mode:'attention',operator_attention_required:true,
    automation_armed:false,escalation_reason:'Repeated instability detected'});
  assert.equal(element('automation-action').textContent,'Operator attention recommended');
  assert.equal(element('automation-recovery-armed').textContent,'Backed off');
  context.renderAutomation({mode:'maintenance',maintenance_mode:true,automation_armed:false});
  assert.equal(element('maintenance-toggle').textContent,'Disable Maintenance Mode');
  await context.toggleMaintenance(element('maintenance-toggle'));
  assert.equal(element('automation-title').textContent,'AUTOMATION — MAINTENANCE');
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
  console.log('Dashboard presentation and polling guard passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
