'use strict';
// Optional development-only browser check: NODE_PATH must resolve Playwright.
// All requests are intercepted; this never connects to an AllStar node.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
const output = process.env.BLUENODE_RENDER_OUTPUT || fs.mkdtempSync(path.join(os.tmpdir(), 'bluenode-render-'));
fs.mkdirSync(output, {recursive:true});
const now = new Date().toISOString();
function fixture(detailed) {
  return {node:'12345', callsign:'N0CALL', status:detailed?'degraded':'healthy',
    asterisk:'online', internet:'online', skywarn:'unknown', cpu_temp_c:48.2,
    memory_percent:31.4, disk_percent:12.8, uptime_seconds:543210,
    last_health_check:now, connected_nodes:['23456'], connected_since:{'23456':now},
    friendly_nodes:{'23456':'Example linked node'},
    health:{cpu:'normal',memory:'normal',disk:'normal'},
    health_reasons:detailed?['AllStar service availability is limited.']:[],
    node_behavior:{assessment:'normal',stale:false,evidence_status:'current',reasons:[]},
    automation:{mode:'active',automation_armed:false,recovery_enabled:false,
      repeated_failure_protection:true,last_automation_check:now},
    connection_stats:{connections_today:4,active_connections:1,connected_seconds_today:4138,
      recent_sessions:[{node:'34567',name:'Example previous session',duration_seconds:350,disconnected_at:now}]},
    connectivity:{diagnosis:detailed?'allstar_services_failure':'healthy',last_check:now,
      checks:{interface:true,gateway:true,dns:true,internet:true,allstar:!detailed},
      message:'The network and DNS are reachable, but the AllStar registration endpoint is not responding. '.repeat(6),
      layers:{local_network:{status:'ok'},gateway:{status:'ok'},dns:{status:'ok'},
        internet:{status:'ok'},allstar_services:{status:'fail'},allstar_registration:{status:'unknown'}},
      operator_action:'Review the AllStar service status and retry after the next diagnostic observation. Do not restart Asterisk for an external service failure.'}};
}
(async()=>{
  const browser = await chromium.launch({headless:true,
    ...(process.env.BLUENODE_BROWSER_PATH ? {executablePath:process.env.BLUENODE_BROWSER_PATH} : {})});
  let checks = 0;
  try {
    for (const width of [1440,1024,768,390,320]) {
      const page = await browser.newPage({viewport:{width,height:1000}});
      const errors = [];
      page.on('pageerror', error=>errors.push(error.message));
      let detailed = true;
      let emergency = false;
      let missing = false;
      await page.route('**/*', async route=>{
        const url = new URL(route.request().url());
        assert.equal(route.request().method(), 'GET', 'Render checks must never invoke controls');
        if (url.pathname === '/web/') return route.fulfill({contentType:'text/html',body:html});
        let body;
        if (url.pathname === '/state/system.json' && !missing) body = fixture(detailed);
        if (url.pathname === '/state/intelligence.json' && !missing) body = {
          level:detailed?'warning':'normal',attention_required:detailed,
          summary:'The node remains online. Review the service diagnostic details before taking action.',
          recommendation:{message:'Monitor the next diagnostic observation.'},
          incidents:[{component:'internet',resolved:true,summary:'A prior connection interruption was resolved.',started_at:now,duration_seconds:45}]};
        if (url.pathname === '/api/admin/session') body = {enabled:true,authenticated:false};
        if (url.pathname === '/api/emergency-mode') body = {active:emergency,mode:emergency?'emergency':'normal',elapsed_seconds:65};
        if (body) return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
        return route.fulfill({status:404,contentType:'text/html',body:'Not Found'});
      });
      await page.goto('http://bluenode.test/web/');
      await page.waitForFunction(()=>document.getElementById('status').textContent === 'DEGRADED');
      const geometry = async()=>page.evaluate(()=>({
        overflow:document.documentElement.scrollWidth>innerWidth,
        heights:[...document.querySelectorAll('#status-grid .card')].slice(0,5).map(e=>e.getBoundingClientRect().height)
      }));
      assert.equal((await geometry()).overflow,false, `overflow at ${width}`);
      assert.equal(await page.locator('#connectivity-disclosure').getAttribute('open'), null);
      const before = (await geometry()).heights;
      assert.ok(Math.max(...before)<240, `top cards too tall at ${width}: ${before}`);
      await page.screenshot({path:path.join(output,`${width}-top.png`)});
      await page.locator('#connectivity-summary').click();
      assert.equal(await page.locator('#connectivity-disclosure').evaluate(e=>e.open), true);
      assert.match(await page.locator('#connectivity-details').innerText(), /Do not restart Asterisk/);
      assert.equal((await geometry()).overflow,false, `expanded overflow at ${width}`);
      assert.deepEqual((await geometry()).heights,before, 'diagnostics must not resize top cards');
      await page.screenshot({path:path.join(output,`${width}-details.png`),fullPage:true});
      await page.locator('#connectivity-disclosure summary').focus();
      await page.keyboard.press('Enter');
      assert.equal(await page.locator('#connectivity-disclosure').evaluate(e=>e.open),false);
      await page.locator('#manual-node-number').focus();
      await page.keyboard.press('Tab');
      await page.keyboard.press('Shift+Tab');
      assert.equal(await page.locator('#manual-node-number').evaluate(e=>getComputedStyle(e).outlineWidth),'3px');
      const danger = await page.locator('#emergency-enter').evaluate(e=>({
        background:getComputedStyle(e).backgroundColor,height:e.getBoundingClientRect().height}));
      assert.equal(danger.background,'rgb(127, 29, 29)');
      assert.ok(danger.height>=44);
      detailed = false;
      await page.evaluate(()=>loadStatus());
      assert.equal(await page.locator('#connectivity-summary').innerText(),'Healthy');
      assert.equal((await geometry()).overflow,false);
      emergency = true;
      await page.evaluate(()=>loadStatus());
      assert.equal(await page.locator('#emergency-banner').isVisible(),true);
      assert.equal((await geometry()).overflow,false,`emergency overflow at ${width}`);
      missing = true;
      await page.evaluate(()=>loadStatus());
      assert.equal(await page.locator('#status').innerText(),'UNAVAILABLE');
      assert.equal((await geometry()).overflow,false);
      assert.deepEqual(errors,[],`browser errors at ${width}`);
      checks++;
      await page.close();
    }
    console.log(`PASS browser rendering: ${checks} viewports; diagnostics, keyboard, emergency, missing state. Screenshots: ${output}`);
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
