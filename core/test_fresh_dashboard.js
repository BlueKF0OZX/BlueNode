'use strict';
// Execute the entire shipped dashboard script with actual first-run responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {textContent:'', innerHTML:'', style:{},
    dataset:{}, value:'', disabled:false, classList:{add(){},remove(){},toggle(){}},
    addEventListener(){}, querySelectorAll(){return [];}});
  return elements.get(id);
}
const requests = [];
const context = vm.createContext({console, Date, URL, URLSearchParams,
  setInterval(){}, clearInterval(){}, setTimeout, clearTimeout,
  window:{addEventListener(){},location:{protocol:'http:',host:'localhost'}},
  document:{getElementById:element, querySelectorAll(){return [];},
    body:element('body'), addEventListener(){}},
  fetch: async url => {
    requests.push(url);
    let payload;
    if (url.startsWith('/api/admin/session')) payload = {enabled:false,authenticated:false};
    if (url.startsWith('/api/emergency-mode')) payload = {active:false,mode:'normal',elapsed_seconds:0};
    return {ok:payload !== undefined, status:payload === undefined ? 404 : 200,
      json:async()=>{if (payload === undefined) throw new Error('404 HTML'); return payload;},
      text:async()=>'<html>Not Found</html>'};
  }
});
(async()=>{
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
  for (const script of scripts) vm.runInContext(script[1], context);
  await new Promise(resolve=>setTimeout(resolve,20));
  await context.loadStatus();
  await context.loadEvents();
  await context.loadAdminSession();
  assert.equal(element('status').textContent, 'UNAVAILABLE');
  assert.match(element('node-behavior-title').textContent, /UNAVAILABLE/);
  assert.match(element('intelligence-summary').textContent, /unavailable/i);
  assert.match(element('error').textContent, /Waiting for BlueNode monitoring data/);
  for (const id of ['lastcheck','cputemp','uptime','memory','disk']) assert.equal(element(id).textContent,'Unavailable');
  for (const id of ['nodes','connections-today','current-session','recent-sessions']) assert.equal(element(id).textContent,'Observation unavailable');
  assert.doesNotMatch(element('events').textContent, /<html>/);
  assert.ok(requests.some(url=>url.startsWith('/api/emergency-mode')));
  context.updateControlStates({skywarn:'unknown', friendly_nodes:{}, connected_nodes:[]});
  assert.equal(element('btn-skywarn-on').disabled, true);
  assert.equal(element('btn-skywarn-off').disabled, true);
  console.log('PASS full dashboard first load: no state, logs, history, or optional integrations');
})().catch(error=>{console.error(error);process.exitCode=1;});
