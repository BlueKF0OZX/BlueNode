'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
const code = html.slice(html.indexOf('    // Live activity is polled'), html.indexOf('    let statusLoading'));
const now = Date.now();
const stamp = seconds => new Date(now + seconds * 1000).toISOString();
const elements = {};
const element = id => elements[id] ||= {textContent:'', dataset:{}};
const context = vm.createContext({Date, AbortController, setTimeout, clearTimeout,
  document:{getElementById:element}, fetch:async()=>({ok:false})});
vm.runInContext(code, context);
const sample = (type='remote_link') => ({status:'remote_tx', telemetry_available:true,
  last_update:stamp(0), stale_after_seconds:6, last_active_at:stamp(0),
  tx_origin:{active:true,source_type:type,source_node:'23456',path_scope:'immediate_peer',started_at:stamp(-17)}});
const view = value => context.activityView(value,now);
assert.match(view(sample()).label,/RECEIVING.*00:17/);
assert.match(view(sample()).detail,/Via node 23456.*original source unknown/);
assert.match(view(sample('local_rf')).label,/LOCAL RECEIVER/);
assert.match(view(sample('ambiguous')).label,/MULTIPLE SOURCES/);
assert.doesNotMatch(view(sample('ambiguous')).detail,/23456/);
assert.match(view(sample('internal_or_unknown')).label,/NODE TRANSMITTING/);
for (const value of [null, {}, {...sample(),last_update:stamp(-7)},
  {...sample(),last_update:stamp(1)}, {...sample(),telemetry_available:false},
  {...sample(),stale:true}, {...sample(),last_update:'broken'}]) {
  assert.equal(view(value).state,'unknown');
  assert.equal(view(value).warning,'');
}
const idle = {...sample(),status:'idle',last_active_at:stamp(-42),tx_origin:{active:false,source_type:'none'}};
assert.equal(view(idle).label,'IDLE');
assert.match(view(idle).detail,/42s ago/);
assert.equal(view({...idle,last_active_at:null}).detail,'No activity observed yet');
const long = sample(); long.tx_origin.started_at = stamp(-301);
assert.match(view(long).warning,/5 minutes/);
long.last_update = stamp(-10);
assert.equal(view(long).warning,'');
const corrupt = sample(); corrupt.tx_origin.started_at=stamp(1);
assert.equal(view(corrupt).label,'RECEIVING');
corrupt.tx_origin.source_node='<img src=x onerror=alert(1)>';
assert.equal(view(corrupt).state,'unknown');
(async()=>{
  context.fetch = async()=>({ok:true,json:async()=>sample()});
  await context.loadLiveActivity();
  assert.match(element('live-activity-label').textContent,/RECEIVING/);
  context.fetch = async()=>{throw new Error('offline');};
  await context.loadLiveActivity();
  assert.equal(element('live-activity-label').textContent,'Activity unavailable');
  let release;
  let requests=0;
  context.fetch=()=>{requests++;return new Promise(resolve=>{release=resolve;});};
  const pending=context.loadLiveActivity();
  await context.loadLiveActivity();
  assert.equal(requests,1,'overlapping polling must be suppressed');
  release({ok:true,json:async()=>idle}); await pending;
  console.log('PASS live activity attribution, timers, expiry, history, warnings, and polling failures');
})().catch(error=>{console.error(error);process.exitCode=1;});
