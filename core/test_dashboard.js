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
const automation = html.indexOf('id="automation-title"');
const remoteAdmin = html.indexOf('id="remote-admin-panel"');
const softRadio = html.indexOf('id="soft-radio-panel"');
const emergencyBanner = html.indexOf('id="emergency-banner"');
assert.ok(disk < connectionStats && connectionStats < controls,
  'Controls must follow the status/statistics area');
assert.doesNotMatch(html, /id="radio-activity-panel"|renderRadioActivity|radioDuration/,
  'The standalone Radio Activity presentation must remain removed');
assert.ok(intelligence < sessions && sessions < events,
  'Intelligence must immediately precede Recent Sessions and Recent Events');
assert.ok(controls < automation && automation < remoteAdmin && remoteAdmin < softRadio && softRadio < intelligence,
  'Operational order must be Controls, Automation, optional Admin/RX, Intelligence');
assert.ok(emergencyBanner > 0 && emergencyBanner < disk,
  'Emergency status must precede operational health content');
assert.match(html, /body\.emergency-mode #status-grid\s*{\s*order:\s*1/);
assert.match(html, /body\.emergency-mode #intelligence-panel\s*{\s*order:\s*2/);
assert.match(html, /body\.emergency-mode #node-behavior-panel\s*{\s*order:\s*3/);
assert.match(html, /body\.emergency-mode #operational-events-panel\s*{\s*order:\s*4/);
assert.match(html, /skywarn-card/);
assert.match(html, /connected-nodes-card/);
assert.match(html, /@media \(max-width: 480px\)[\s\S]*\.emergency-banner-heading \.control-button \{ width: 100%; \}/,
  'Emergency controls must remain usable without horizontal scrolling on mobile');
assert.ok(html.includes('const emergencyPattern = /EMERGENCY|ASTERISK|CONNECT|DISCONNECT|INTERNET|DNS|GATEWAY|ALLSTAR|SKYWARN|INCIDENT|RECOVERY|AUTOMATION|CONTROL/i'),
  'Emergency event view must prioritize operational transitions');
assert.doesNotMatch(html, /<h2>Automatic Recovery<\/h2>|id="recovery-panel"|loadRecoveryStatus/,
  'The redundant standalone recovery presentation must remain removed');
assert.match(html, /async function loadAdminSession\(\)/);
assert.match(html, /Type RESTART ASTERISK/);
assert.match(html, /adminHeaders\(\{'Content-Type': 'application\/json'\}\)/);
assert.match(html, /\/api\/soft-radio\/ticket/);
assert.match(html, /\/api\/soft-radio\/ws`,\s*\['bluenode-rx', `ticket\.\$\{result\.ticket\}`\]/);
assert.match(html, /new AudioWorkletNode\(softRadioContext, 'bluenode-ulaw-player'/);
const worklet = fs.readFileSync(path.join(__dirname, '../web/soft-radio-worklet.js'), 'utf8');
assert.match(worklet, /maximumSamples\s*=\s*8000 \* 0\.24/);
assert.match(worklet, /targetSamples\s*=\s*8000 \* 0\.06/);
assert.match(worklet, /this\.samples\.splice\(0, this\.samples\.length - this\.targetSamples\)/,
  'RX jitter buffer must drop stale samples instead of growing latency');
const softRadioCode = html.slice(html.indexOf('async function loadSoftRadioState'),
  html.indexOf('async function runControl'));
assert.doesNotMatch(softRadioCode, /getUserMedia|mediaDevices|push.to.talk|\bPTT\b/i,
  'Soft Radio Phase A must not contain microphone or transmit controls');
assert.match(html, /\.grid\s*\+\s*\.grid\s*{[^}]*margin-top:\s*15px/s,
  'Adjacent telemetry grids must use the same 15px gap as card rows');
assert.match(html, /\.controls-panel\s*{[^}]*margin-top:\s*18px/s,
  'Controls must retain a slightly larger gap below the telemetry grids');
assert.equal(html.slice(intelligence, sessions).match(/<h2>/g)?.length, 1,
  'No section heading may appear between Intelligence and Recent Sessions');
for (const id of ['disk', 'connections-today', 'control-result',
  'connectivity-summary', 'connectivity-details',
  'automation-panel', 'automation-title', 'automation-summary',
  'automation-recovery-armed', 'automation-protection',
  'automation-maintenance', 'automation-last-check', 'automation-attempts',
  'automation-backoff', 'automation-action', 'maintenance-toggle',
  'soft-radio-panel', 'soft-radio-title', 'soft-radio-auth', 'soft-radio-status',
  'soft-radio-listen', 'soft-radio-stop', 'soft-radio-volume', 'soft-radio-level',
  'intelligence-panel', 'recent-sessions', 'events',
  'emergency-banner', 'emergency-enter', 'emergency-exit', 'emergency-meta',
  'emergency-summary', 'status-grid', 'statistics-grid',
  'recent-sessions-panel', 'operational-events-panel',
  'node-behavior-panel', 'node-behavior-title', 'node-behavior-summary',
  'node-behavior-evidence',
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
  confirm:()=>true,
  document: {getElementById:element, body:{classList:{toggle(_name,value){this.active=value;}}}},
  fetch: async()=>({ok:true, json:async()=>({})})
});
(async()=>{
  const connectivityStart=html.indexOf('    function renderConnectivity');
  const connectivityEnd=html.indexOf('    function automationAge',connectivityStart);
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
  context.renderNodeBehavior({assessment:'normal',stale:false,reasons:[]});
  assert.match(element('node-behavior-title').textContent,/NODE BEHAVIOR.*NORMAL/);
  assert.equal(element('node-behavior-summary').textContent,
    'No unusual local or network activity detected.');
  context.renderNodeBehavior({assessment:'warning',stale:false,
    operator_review_recommended:true,reasons:[{summary:'Repeated connection attempts observed',
      evidence:'Node 12345: 8 attempts within 5 minutes'}]});
  assert.match(element('node-behavior-title').textContent,/NODE BEHAVIOR.*WARNING/);
  assert.match(element('node-behavior-evidence').textContent,
    /Node 12345.*Operator review recommended.*no corrective action/);
  context.renderNodeBehavior({assessment:'warning',stale:true,reasons:[]});
  assert.match(element('node-behavior-title').textContent,/DATA UNAVAILABLE/);
  context.renderNodeBehavior({assessment:'normal',stale:false,evidence_status:'partial',
    ambiguity:'Local RF telemetry is unavailable or stale; RF behavior was not assessed',reasons:[]});
  assert.match(element('node-behavior-title').textContent,/LIMITED DATA/);
  assert.match(element('node-behavior-evidence').textContent,/RF behavior was not assessed/);
  context.renderEmergencyMode({active:true, mode:'emergency', elapsed_seconds:65,
    activated_at:new Date().toISOString()}, {status:'healthy',asterisk:'online',
    connectivity:{diagnosis:'healthy'},intelligence:{attention_required:false}});
  assert.equal(context.document.body.classList.active,true);
  assert.match(element('emergency-meta').textContent,/00:01:05/);
  assert.match(element('emergency-summary').textContent,/Overall: HEALTHY.*No operator action required/);
  context.renderEmergencyMode({active:true, mode:'emergency', elapsed_seconds:66},
    {status:'degraded',asterisk:'online',connectivity:{diagnosis:'dns_failure'},
      intelligence:{attention_required:true}});
  assert.match(element('emergency-summary').textContent,
    /Overall: DEGRADED.*Connectivity: DNS FAILURE.*OPERATOR ATTENTION REQUIRED/);
  context.renderEmergencyMode({active:false,mode:'normal',elapsed_seconds:0});
  assert.equal(context.document.body.classList.active,false);
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
