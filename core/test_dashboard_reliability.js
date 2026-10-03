'use strict';
// Synthetic routes only: no radio command reaches an operating node.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.BLUENODE_BROWSER_PATH ? {executablePath:process.env.BLUENODE_BROWSER_PATH} : {})});
  try {
    for (const width of [320,390,1440]) {
      const page = await browser.newPage({viewport:{width,height:1000}});
      const posts = [], errors = [];
      let eventStatus = 200;
      let holdSession = false, heldSession, controlStatus = 200;
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', async route => {
        const req = route.request(), pathname = new URL(req.url()).pathname;
        if (pathname === '/web/') return route.fulfill({contentType:'text/html',body:html});
        if (pathname === '/api/admin/session') {
          if (holdSession) { heldSession = route; holdSession = false; return; }
          return route.fulfill({json:{enabled:true,authenticated:true,csrf_token:'fixture-csrf'}});
        }
        if (pathname === '/api/admin/status') return route.fulfill({json:{services:{},version:{}}});
        if (pathname === '/api/soft-radio/status') return route.fulfill({json:{enabled:false}});
        if (pathname === '/api/favorites') return route.fulfill({json:{ok:true,local_node:'12345',revision:0,favorites:[]}});
        if (pathname === '/logs/events.log') return route.fulfill({status:eventStatus,body:
          '2026-10-01T12:00:00Z | RADIO.LOCAL_RX.START | Local receiver start\n2026-10-01T12:00:10Z | RADIO.LOCAL_RX.END | Local receiver end'});
        if (pathname.startsWith('/api/control/')) {
          posts.push({path:pathname,body:req.postDataJSON()});
          assert.equal(req.headers()['x-csrf-token'],'fixture-csrf');
          return route.fulfill({status:controlStatus,json:{ok:controlStatus===200,outcome:'verified',node:'23456',message:'Verified fixture',error:'Not confirmed'}});
        }
        if (pathname === '/stalled') return; // Used to exercise timeout cleanup.
        return route.fulfill({status:404,body:'{}'});
      });
      await page.goto('https://fixture.invalid/web/');
      await page.evaluate(async () => { await configureSavedNodes('12345',{}); await loadAdminSession(); });
      await page.locator('#dtmf-panel > summary').click();
      const send = async command => {
        await page.locator('#dtmf-command').fill(command);
        await page.locator('#dtmf-send').click();
        await page.waitForFunction(() => !document.getElementById('dtmf-send').disabled);
      };
      await send('*323456');
      assert.equal(posts.length,1);
      assert.deepEqual(posts[0],{path:'/api/control/node-connect',body:{node:'23456'}});
      assert.match(await page.locator('#dtmf-history').textContent(),/Verified/);
      await page.locator('#dtmf-history button').click();
      assert.equal(posts.length,1,'history selection never sends');
      for (const invalid of ['*99','*312345','*323456;reboot']) await send(invalid);
      assert.equal(posts.length,1,'invalid and self-target commands are rejected');
      controlStatus = 504;
      await send('*123456');
      assert.match(await page.locator('#dtmf-history').textContent(),/Not confirmed/);
      await page.reload();
      await page.evaluate(async () => { await configureSavedNodes('12345',{}); await loadAdminSession(); });
      assert.equal(await page.locator('#dtmf-history button').count(),2,'history survives reload');
      assert.equal(posts.length,2,'reload never replays');
      await page.evaluate(() => configureSavedNodes('34567',{}));
      assert.equal(await page.locator('#dtmf-history button').count(),0,'separate node history');
      await page.evaluate(() => configureSavedNodes('12345',{}));
      await page.evaluate(() => clearDtmfHistory());
      assert.equal(await page.locator('#dtmf-history button').count(),0);

      await page.evaluate(() => loadEvents());
      assert.match(await page.locator('#activity-history-summary').textContent(),/10 sec/);
      eventStatus = 503; await page.evaluate(() => loadEvents());
      assert.match(await page.locator('#activity-history-summary').textContent(),/unavailable/);
      eventStatus = 404; await page.evaluate(() => loadEvents());
      assert.doesNotMatch(await page.locator('#activity-history-summary').textContent(),/10 sec/);

      holdSession = true;
      await page.evaluate(() => { window.oldSessionRead = loadAdminSession(); });
      await page.waitForFunction(() => true);
      while (!heldSession) await new Promise(resolve => setTimeout(resolve,10));
      await page.evaluate(() => loadAdminSession());
      await heldSession.fulfill({json:{enabled:true,authenticated:false}});
      await page.evaluate(() => window.oldSessionRead);
      assert.equal(await page.locator('#control-auth-status').textContent(),'Controls unlocked','late signed-out read cannot overwrite newer session');
      const timeout = await page.evaluate(async () => {
        try { await dashboardRequest('/stalled',{},50); } catch (error) { return error.message; }
      });
      assert.match(timeout,/timed out/);
      assert.equal(posts.length,2,'recovery never replays a command');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      assert.deepEqual(errors,[]);
      await page.close();
    }
    console.log('PASS DTMF verified commands/history, stale auth recovery, event outage cleanup, bounded requests, phone/desktop layout');
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
