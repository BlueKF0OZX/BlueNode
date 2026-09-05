'use strict';
// No request reaches a node. Sessions and control side effects are synthetic.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../web/index.html'), 'utf8');
(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.BLUENODE_BROWSER_PATH ? {executablePath:process.env.BLUENODE_BROWSER_PATH} : {})});
  try {
    const page = await browser.newPage();
    let authenticated = false, validPassword = true, csrfRejected = false, emergency = false;
    let sessionUnavailable = false;
    const executed = [], requests = [], errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    await page.route('**/*', async route => {
      const request = route.request(), url = new URL(request.url());
      const authorized = authenticated && (request.headers().cookie || '').includes('bluenode_admin=fixture-session');
      if (url.pathname === '/web/') return route.fulfill({contentType:'text/html',body:html});
      requests.push(url.pathname);
      let status = 200, body = {}, headers = {};
      if (url.pathname === '/api/admin/session') body = {enabled:true,authenticated:authorized,csrf_token:authorized?'fixture-csrf':null};
      else if (url.pathname === '/api/admin/login') {
        authenticated = validPassword;
        status = authenticated ? 200 : 401;
        body = authenticated ? {ok:true,csrf_token:'fixture-csrf'} : {error:'Invalid credentials'};
        if (authenticated) headers['Set-Cookie'] = 'bluenode_admin=fixture-session; Path=/; Max-Age=2592000; Secure; HttpOnly; SameSite=Strict';
      } else if (url.pathname === '/api/admin/logout') {
        authenticated = false; body = {ok:true};
        headers['Set-Cookie'] = 'bluenode_admin=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Strict';
      }
      else if (url.pathname === '/api/admin/status') {
        status = authorized ? 200 : 401;
        body = {services:{monitor:{active:true},web:{active:true},asterisk:{active:true}},version:{commit:'fixture'}};
      } else if (url.pathname === '/api/soft-radio/status') body = {enabled:false};
      else if (url.pathname === '/api/emergency-mode') body = {active:emergency,mode:emergency?'emergency':'normal'};
      else if (url.pathname.startsWith('/api/control/')) {
        status = !authorized ? 401 : csrfRejected || request.headers()['x-csrf-token'] !== 'fixture-csrf' ? 403 : 200;
        if (status === 200) {
          const payload = JSON.parse(request.postData());
          executed.push({action:url.pathname.split('/').pop(),payload});
          if (url.pathname.includes('emergency-')) emergency = url.pathname.endsWith('-enable');
          body = {ok:true,message:'Fixture completed',emergency_mode:{active:emergency,mode:emergency?'emergency':'normal'},automation:{mode:'active'}};
        } else body = {ok:false,error:status===401?'Remote Admin authentication required':'Invalid CSRF token'};
      } else { status = 404; }
      if (url.pathname === '/api/admin/session' && sessionUnavailable) status = 503;
      return route.fulfill({status,headers,contentType:'application/json',body:JSON.stringify(body)});
    });
    const login = async () => {
      await page.locator('#admin-username').fill('operator');
      await page.locator('#admin-password').fill('fixture password');
      await page.locator('button[onclick="adminLogin(this)"]').click();
      await page.waitForFunction(() => !adminLoginBusy && !controlRequestBusy);
    };
    await page.goto('https://bluenode.test/web/');
    await page.evaluate(() => loadAdminSession());
    const controls = [
      ['#btn-dodropin-connect','dodropin-connect'], ['#btn-dodropin-disconnect','dodropin-disconnect'],
      ['#btn-skywarn-on','skywarn-enable'], ['#btn-skywarn-off','skywarn-disable'],
      ['button[onclick="runNodeControl(\'node-connect\', this)"]','node-connect'],
      ['button[onclick="runNodeControl(\'node-disconnect\', this)"]','node-disconnect'],
      ['#emergency-enter','emergency-enable'],
      ['button[onclick="toggleEmergencyMode(false, this)"]','emergency-disable'],
      ['#maintenance-toggle','maintenance-enable']
    ];
    await page.locator('#manual-node-number').fill('12345');
    for (const [selector, action] of controls) {
      authenticated = false; // Includes expiry while the page still believes it is signed in.
      const count = executed.length;
      await page.locator(selector).click();
      await page.waitForFunction(() => pendingControl !== null);
      assert.equal(executed.length, count);
      assert.equal(await page.locator('#admin-login-view').isVisible(), true);
      // A second control cannot replace or duplicate the first one.
      await page.evaluate(() => runControl('skywarn-disable', document.createElement('button')));
      await login();
      assert.equal(executed.length, count + 1);
      assert.equal(executed.at(-1).action, action);
      if (action.startsWith('node-')) assert.deepEqual(executed.at(-1).payload, {node:'12345'});
      await page.evaluate(() => adminLogin(document.createElement('button')));
      assert.equal(executed.length, count + 1, 'another login must not replay consumed action');
    }
    const count = executed.length;
    const logins = requests.filter(p=>p==='/api/admin/login').length;
    await page.locator('#btn-dodropin-connect').click();
    await page.waitForFunction(() => !controlRequestBusy);
    assert.equal(executed.length, count + 1);
    assert.equal(requests.filter(p=>p==='/api/admin/login').length, logins);
    await page.reload();
    await page.evaluate(() => loadAdminSession());
    const cookie = (await page.context().cookies()).find(cookie => cookie.name === 'bluenode_admin');
    assert.ok(cookie.httpOnly && cookie.secure && cookie.sameSite === 'Strict');
    assert.ok(cookie.expires > Date.now() / 1000 + 29 * 86400);
    assert.equal(await page.evaluate(() => document.cookie.includes('bluenode_admin')), false);
    assert.equal(await page.locator('#control-auth-status').innerText(), 'Controls unlocked');
    await page.locator('#btn-dodropin-disconnect').click();
    await page.waitForFunction(() => !controlRequestBusy);
    assert.equal(executed.length, count + 2);
    for (const outcome of ['failed', 'cancelled', 'reload']) {
      authenticated = false;
      const before = executed.length;
      await page.locator('#btn-dodropin-connect').click();
      await page.waitForFunction(() => pendingControl !== null);
      if (outcome === 'failed') { validPassword = false; await login(); validPassword = true; }
      if (outcome === 'cancelled') await page.locator('#control-login-cancel').click();
      if (outcome === 'reload') await page.reload();
      await login();
      assert.equal(executed.length, before, outcome + ' must discard pending action');
    }
    await page.locator('#control-sign-out').click();
    await page.waitForFunction(() => adminCsrfToken === null);
    await page.locator('#btn-skywarn-on').click();
    await page.waitForFunction(() => pendingControl !== null);
    csrfRejected = true;
    const before = executed.length;
    await login();
    assert.equal(executed.length, before);
    assert.match(await page.locator('#control-result').innerText(), /CSRF/);
    csrfRejected = false;
    authenticated = false;
    await page.locator('#btn-dodropin-connect').click();
    await page.waitForFunction(() => pendingControl !== null);
    sessionUnavailable = true;
    await login();
    assert.equal(executed.length, before, 'failed session verification must prevent resume');
    sessionUnavailable = false;
    await page.evaluate(() => loadAdminSession());
    const requestCount = requests.length;
    await page.evaluate(async () => {
      for (const [action,payload] of [['../admin/action',{}],['node-connect',{node:'123;bad'}],['skywarn-enable',{extra:true}]]) {
        let rejected = false;
        try { await requestOrdinaryControl(action,payload); } catch (_) { rejected = true; }
        if (!rejected) throw new Error('Malformed control accepted');
      }
    });
    assert.equal(requests.length, requestCount);
    assert.deepEqual(errors, []);
    console.log('PASS control auth UX: nine controls; resume once, expiry, reload, logout, failure, cancellation, CSRF and injection');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
