'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
const source = html.slice(html.indexOf('function buildSupportReport('), html.indexOf('let supportReportText'));
const context = vm.createContext({});
vm.runInContext(source, context);
const now = new Date('2026-09-13T12:00:00Z');
const report = context.buildSupportReport({status:'DEGRADED', asterisk:'online',
  last_health_check:'2026-09-13T11:59:00Z', memory_percent:35.25,
  callsign:'SECRET', connected_nodes:['SECRET'], config:{password:'SECRET'},
  internet:'SECRET', cpu_temp_c:'SECRET', health_reasons:['SECRET'],
  connectivity:{checks:{interface:true,gateway:false,dns:'SECRET'},message:'SECRET'}}, now);
assert.doesNotMatch(report, /SECRET/);
assert.match(report, /Overall health: degraded/);
assert.match(report, /60 seconds old/);
assert.match(report, /gateway: fail/);
assert.match(report, /dns: unavailable/);
assert.match(report, /Memory used \(%\): 35.3/);
assert.match(context.buildSupportReport({last_health_check:'2099-01-01',disk_percent:Infinity}, now), /invalid timestamp/);
assert.match(context.buildSupportReport(null, now), /Overall health: unavailable/);
console.log('PASS support report: privacy allowlist, missing values, observation age, invalid timestamps');
