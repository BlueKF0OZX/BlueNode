const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(process.argv[2] || path.join(__dirname, '../web/index.html'), 'utf8');
const render = html.match(/document\.getElementById\('cpuusage'\)\.textContent =[\s\S]*?;/)[0];
for (const [value, expected] of [[0,'0.0%'], [25.46,'25.5%'], [100,'100.0%'], [null,'N/A'], [undefined,'N/A'], [-1,'N/A'], [101,'N/A'], ['25','N/A']]) {
  const element = {};
  vm.runInNewContext(render, {data:{cpu_percent:value}, document:{getElementById:()=>element}});
  assert.equal(element.textContent, expected);
}
assert.match(html, /\['lastcheck','cputemp','cpuusage','uptime','memory','disk'\]/);
assert.match(html, /CPU utilization \(%\): ' \+ numeric\(state.cpu_percent\)/);
assert.equal((html.match(/id="cpuusage"/g)||[]).length, 1);
console.log('CPU dashboard rendering, missing/invalid values, export, and stale cleanup passed.');
