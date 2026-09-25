'use strict';
// Browser-only contract checks. Every request is fulfilled locally; no radio commands run.
// Tests the current authenticated-control UX, including cancellation after HTTP 401.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.BLUENODE_BROWSER_PATH ? {executablePath:process.env.BLUENODE_BROWSER_PATH} : {})});
  try {
    for (const mode of ['local', 'signed-out', 'authenticated']) {
      const page = await browser.newPage();
      const posts = [];
      let emergency = false;
      const authenticated = mode === 'authenticated';
      await page.route('**/*', async route => {
        const request = route.request();
        const url = new URL(request.url());
        let status = 200;
        let body = {};
        if (url.pathname === '/web/') return route.fulfill({contentType:'text/html',body:html});
        if (request.method() === 'POST') {
          posts.push({path:url.pathname, headers:request.headers(), body:request.postData()});
          // bf91361 protects ordinary controls too when Remote Admin is enabled.
          const protectedRequest = url.pathname.startsWith('/api/admin/') || mode !== 'local';
          if (protectedRequest && !authenticated) {
            status = 401; body = {ok:false,error:'Remote Admin authentication required'};
          } else {
            if (protectedRequest) assert.equal(request.headers()['x-csrf-token'], 'fixture-csrf');
            if (url.pathname.startsWith('/api/control/emergency-')) emergency = url.pathname.endsWith('-enable');
            body = {ok:true,message:'Fixture accepted',emergency_mode:{active:emergency,mode:emergency?'emergency':'normal'},automation:{mode:'maintenance'}};
            if (url.pathname === '/api/control/node-connect') Object.assign(body,
              {outcome:'verified',node:JSON.parse(request.postData()).node});
          }
        } else if (url.pathname === '/api/admin/session') {
          body = {enabled:mode !== 'local',authenticated,csrf_token:authenticated?'fixture-csrf':null};
        } else if (url.pathname === '/api/admin/status') {
          status = authenticated ? 200 : 401;
          body = authenticated ? {services:{monitor:{active:true},web:{active:true},asterisk:{active:true}},version:{commit:'fixture'}} : {error:'Remote Admin authentication required'};
        } else if (url.pathname === '/api/emergency-mode') {
          body = {active:emergency,mode:emergency?'emergency':'normal'};
        } else if (url.pathname === '/api/soft-radio/status') {
          body = {enabled:false};
        } else { status = 404; }
        return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
      });
      let allowConfirmation = true;
      page.on('dialog', dialog => allowConfirmation ? dialog.accept() : dialog.dismiss());
      await page.goto('http://bluenode.test/web/');
      await page.evaluate(() => loadAdminSession());
      await page.evaluate(() => { window.loginCalls = 0; window.adminLogin = () => { window.loginCalls++; }; });
      await page.locator('#manual-node-number').fill('12345');
      await page.evaluate(()=>configureSavedNodes('99999',{}));
      await page.locator('#favorite-node-label').fill('Example favorite');
      await page.getByRole('button',{name:'Save node as favorite',exact:true}).click();
      assert.equal(posts.length,0,'saving a favorite must never send a radio control');
      allowConfirmation = false;
      const cancelledCount = posts.length;
      await page.locator('#emergency-enter').click();
      assert.equal(posts.length, cancelledCount, 'cancelled confirmation cannot send a control');
      allowConfirmation = true;
      const controls = [
        ['#btn-dodropin-connect','dodropin-connect'], ['#btn-dodropin-disconnect','dodropin-disconnect'],
        ['button[onclick="runNodeControl(\'node-connect\', this)"]','node-connect'],
        ['button[onclick="runNodeControl(\'node-disconnect\', this)"]','node-disconnect'],
        ['#saved-node-favorites button[onclick^="disconnectSavedNode"]','node-disconnect'],
        ['#saved-node-favorites button[onclick^="connectSavedNode"]','node-connect'],
        ['#emergency-enter','emergency-enable'], ['#maintenance-toggle','maintenance-enable']
      ];
      for (const [selector, action] of controls) {
        const before = posts.length;
        await page.locator(selector).click();
        if (mode === 'signed-out') {
          await page.waitForFunction(() => pendingControl !== null);
          assert.equal(await page.locator('#admin-login-view').isVisible(), true);
          await page.locator('#control-login-cancel').click();
        }
        await page.waitForFunction(selector => !document.querySelector(selector).disabled, selector);
        assert.equal(posts.length, before + 1);
        assert.equal(posts.at(-1).path, '/api/control/' + action);
        if (action.startsWith('node-')) assert.deepEqual(JSON.parse(posts.at(-1).body),
          action === 'node-switch' ? {node:'12345',from_node:'54321'} : {node:'12345'});
        if (mode === 'signed-out') assert.match(await page.locator(action.startsWith('maintenance-') ? '#automation-action' : '#control-result').innerText(), /cancelled/);
      }
      assert.equal(await page.evaluate(() => window.loginCalls), 0, 'ordinary controls must not invoke login');
      assert.equal(await page.locator('#btn-skywarn-on').isDisabled(), true);
      assert.equal(await page.locator('#btn-skywarn-off').isDisabled(), true);
      assert.match(await page.locator('#skywarn-control-help').innerText(), /read-only/);
      assert.equal(await page.locator('#saved-node-recents button[onclick^="connectSavedNode"]').count(),mode === 'signed-out' ? 0 : 1,
        'only a verified connection enters recents');
      assert.equal(posts.some(request => request.path === '/api/admin/login'), false);
      if (mode !== 'signed-out') {
        await page.locator('button[onclick="toggleEmergencyMode(false, this)"]').click();
        await page.waitForFunction(() => !document.querySelector('button[onclick="toggleEmergencyMode(false, this)"]').disabled);
        assert.equal(posts.at(-1).path, '/api/control/emergency-disable');
      }
      const adminResult = await page.evaluate(async () => {
        const response = await fetch('/api/admin/action', {method:'POST',headers:adminHeaders({'Content-Type':'application/json'}),body:JSON.stringify({action:'refresh-diagnostics'})});
        return response.status;
      });
      assert.equal(adminResult, authenticated ? 200 : 401);
      await page.evaluate(() => { void runAdminAction('refresh-diagnostics', document.createElement('button')); });
      if (!authenticated) {
        await page.waitForFunction(()=>pendingControl !== null);
        await page.locator('#control-login-cancel').click();
      }
      await page.waitForFunction(()=>!controlRequestBusy);
      assert.equal(posts.at(-1).path, '/api/admin/action');
      assert.match(await page.locator('#admin-result').innerText(), authenticated ? /Fixture accepted/ : /cancelled/);
      const beforeReload = posts.length;
      await page.reload();
      await page.evaluate(()=>configureSavedNodes('99999',{}));
      assert.match(await page.locator('#saved-node-favorites').innerText(),/Example favorite/);
      assert.equal(posts.length,beforeReload,'restoring favorites must not reconnect automatically');
      await page.close();
      console.log('PASS control routing: ' + mode);
    }
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
