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
    asterisk:'online', internet:'online', skywarn:'enabled', cpu_temp_c:48.2,
    weather_alerts:{status:'current',last_success:Date.now()/1000,alerts:[{
      event:'Tornado Warning',county_code:'XXC001',severity:4,end_time:Date.now()/1000+3600,
      description:'<img src=x onerror=alert(1)> Example detailed warning. '.repeat(30)}]},
    memory_percent:31.4, disk_percent:12.8, uptime_seconds:543210,
    last_health_check:now, connected_nodes:['23456'], connected_since:{'23456':now},
    friendly_nodes:{'23456':'Example linked node'},
    health:{cpu:'normal',memory:'normal',disk:'normal'},
    radio_activity:{telemetry_available:true,stale:false},
    health_reasons:detailed?['AllStar service availability is limited.']:[],
    node_behavior:{assessment:'normal',stale:false,evidence_status:'current',reasons:[]},
    automation:{mode:'active',automation_armed:false,recovery_enabled:false,
      repeated_failure_protection:true,last_automation_check:now},
    connection_stats:{connections_today:4,active_connections:1,connected_seconds_today:4138,
      completed_connections_today:0,completed_connected_seconds_today:0,
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
      // This suite advances health fixtures explicitly. Automatic health polling
      // can race a fixture change; polling behavior has its own regression suite.
      await page.addInitScript(() => {
        const schedule = window.setInterval.bind(window);
        window.setInterval = (callback, delay, ...args) =>
          callback.name === 'loadStatus' ? 0 : schedule(callback, delay, ...args);
      });
      const errors = [];
      page.on('pageerror', error=>errors.push(error.message));
      let detailed = true;
      let asteriskCase = null;
      let emergency = false;
      let missing = false;
      let attentionUnavailable = false;
      let intelligenceIncomplete = false;
      let observedZero = false;
      let connectionUnavailable = false;
      let invalidConnectionState = false;
      let injection = false;
      let eventFixture = null;
      let favorites = {ok:true,local_node:'12345',revision:0,favorites:[]};
      const hostile = '<img src=x onerror=alert(1)>';
      let releaseIntelligence;
      const intelligenceGate = new Promise(resolve => { releaseIntelligence = resolve; });
      await page.route('**/*', async route=>{
        const url = new URL(route.request().url());
        if (url.pathname === '/api/favorites') {
          if (route.request().method() === 'POST') {
            const change = route.request().postDataJSON();
            assert.equal(change.operation,'save');
            favorites = {...favorites, revision:favorites.revision+1, favorites:[change.item]};
          }
          return route.fulfill({contentType:'application/json',body:JSON.stringify(favorites)});
        }
        assert.equal(route.request().method(), 'GET', 'Render checks must never invoke controls');
        if (url.pathname === '/web/') return route.fulfill({contentType:'text/html',body:html});
        if (url.pathname === '/logs/events.log') return route.fulfill({contentType:'text/plain',body:eventFixture ??
          Array.from({length:12}, (_, i) => `${now} | CONNECT.SUCCESS | Example event ${i}: ${injection ? hostile : 'long-detail-'.repeat(20)}`).join('\n')});
        let body;
        if (url.pathname === '/state/radio_activity.json' && !missing) body = {
          status:'remote_tx',telemetry_available:true,last_update:new Date().toISOString(),
          stale_after_seconds:6,last_active_at:new Date().toISOString(),
          tx_origin:{active:true,source_type:'remote_link',path_scope:'immediate_peer',
            source_node:'23456',started_at:new Date(Date.now()-17000).toISOString()}
        };
        if (attentionUnavailable && ['/state/intelligence.json','/api/emergency-mode'].includes(url.pathname)) return route.fulfill({status:503,body:'Unavailable'});
        if (url.pathname === '/state/system.json' && !missing) body = fixture(detailed);
        if (url.pathname === '/state/system.json' && body && asteriskCase) {
          body.asterisk = asteriskCase.service;
          body.asterisk_evidence = {service:{status:asteriskCase.service,observed_at:Date.now()/1000-(asteriskCase.stale?60:0)},
            query:{status:asteriskCase.query}, node:{status:asteriskCase.node},max_age_seconds:30};
        }
        if (url.pathname === '/state/system.json' && body && observedZero) {
          body.connected_nodes=[];body.connected_since={};
          body.connection_stats={connections_today:0,active_connections:0,connected_seconds_today:0,
            completed_connections_today:0,completed_connected_seconds_today:0,recent_sessions:[]};
        }
        if (url.pathname === '/state/system.json' && body && invalidConnectionState) body.connection_stats.state_available = false;
        if (url.pathname === '/state/system.json' && body && connectionUnavailable) body.radio_activity={telemetry_available:false,stale:true};
        if (url.pathname === '/state/system.json' && body && injection) {
          body.friendly_nodes['23456'] = hostile;
          body.health_reasons = [hostile];
          body.connection_stats.recent_sessions[0].name = hostile;
        }
        if (url.pathname === '/state/intelligence.json' && !missing) {
          await intelligenceGate;
          body = {
          level:detailed?'warning':'normal',attention_required:detailed,
          summary:'The node remains online. Review the service diagnostic details before taking action.',
          recommendation:{message:'Monitor the next diagnostic observation.'},
          incidents:[{component:'internet',resolved:true,summary:'A prior connection interruption was resolved.',started_at:now,duration_seconds:45}]};
          if (intelligenceIncomplete) body = {level:'normal',summary:'A stale reassuring summary'};
          if (injection) { body.unresolved_issues = [hostile]; body.incidents[0].summary = hostile; }
        }
        if (url.pathname === '/api/version') body = {version:'0.1.2-alpha.0',commit:'a'.repeat(40)};
        if (url.pathname === '/api/admin/session') body = {enabled:true,authenticated:false};
        if (url.pathname === '/events/allstar_state.json' && !missing) body = {links:observedZero?[]:['23456'],connected_since:observedZero?{}:{'23456':now}};
        if (url.pathname === '/api/emergency-mode') body = {active:emergency,mode:emergency?'emergency':'normal',elapsed_seconds:65};
        if (body) return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
        return route.fulfill({status:404,contentType:'text/html',body:'Not Found'});
      });
      await page.goto('http://bluenode.test/web/');
      await page.waitForFunction(()=>document.getElementById('weather-summary').textContent.includes('1 ACTIVE ALERT TYPE'));
      await page.waitForFunction(()=>document.getElementById('live-activity-label').textContent.includes('RECEIVING'));
      assert.match(await page.locator('#live-activity-detail').innerText(), /Via node 23456.*original source unknown/);
      assert.equal(await page.locator('#connections-today').innerText(), 'Waiting for first observation');
      assert.equal(await page.locator('#status').innerText(), 'Loading...', 'weather must render before delayed Intelligence');
      releaseIntelligence();
      await page.waitForFunction(()=>document.getElementById('status').textContent === 'DEGRADED');
      assert.equal(await page.locator('#connections-today').innerText(), '4');
      assert.equal(await page.locator('#completed-connections-today').innerText(), '0');
      assert.match(await page.locator('#dodropin-control-help').innerText(), /mapping is unavailable/);
      assert.equal(await page.locator('.onboarding-help').first().getAttribute('href'), '/web/guide.html');
      assert.equal(await page.locator('.onboarding-help').first().getAttribute('target'), '_blank');
      assert.match(await page.locator('.onboarding-help').first().getAttribute('rel'), /noopener/);
      invalidConnectionState = true;
      await page.evaluate(() => loadStatus());
      assert.equal(await page.locator('#active-connections').innerText(), 'Observation unavailable');
      invalidConnectionState = false;
      await page.evaluate(() => loadStatus());
      const geometry = async()=>page.evaluate(()=>({
        overflow:document.documentElement.scrollWidth>innerWidth,
        heights:[...document.querySelectorAll('#status-grid .card')].slice(0,5).map(e=>e.getBoundingClientRect().height)
      }));
      const checkCardAlignment = async () => {
        const cards = await page.locator('#status-grid .card').evaluateAll(elements => elements.map(card => {
          const bounds = card.getBoundingClientRect();
          const children = [...card.children].filter(child => child.getBoundingClientRect().height > 0);
          const first = children[0].getBoundingClientRect();
          const last = children[children.length - 1].getBoundingClientRect();
          return {
            label: children[0].textContent,
            centered: Math.abs((first.top + last.bottom) / 2 - (bounds.top + bounds.bottom) / 2) < 2,
            textCentered: children.every(child => getComputedStyle(child).textAlign === 'center'),
            contained: children.every(child => {
              const rect = child.getBoundingClientRect();
              return rect.left >= bounds.left && rect.right <= bounds.right &&
                child.scrollWidth <= child.clientWidth + 1;
            })
          };
        }));
        for (const card of cards) {
          assert.ok(card.centered, `${card.label}: vertically centered at ${width}`);
          assert.ok(card.textCentered, `${card.label}: horizontally centered text at ${width}`);
          assert.ok(card.contained, `${card.label}: text fits at ${width}`);
        }
      };
      await checkCardAlignment();
      assert.match(await page.locator('#build-version').innerText(), /0\.1\.2-alpha\.0.*aaaaaaaaaaaa/);
      await page.evaluate(() => loadEvents());
      assert.equal(await page.locator('#events .event-row').count(), 10);
      await page.getByRole('button', {name:'Show More', exact:true}).click();
      await page.waitForFunction(() => document.querySelectorAll('#events .event-row').length === 12);
      assert.equal(await page.locator('#events .event-row').count(), 12);
      const smallTargets = await page.locator('button:visible, .onboarding-help:visible').evaluateAll(elements =>
        elements.filter(e => e.getBoundingClientRect().height < 44).map(e => e.textContent.trim()));
      assert.deepEqual(smallTargets, [], `touch targets at ${width}`);
      await page.locator('#manual-node-number').fill('23456');
      await page.locator('#favorite-node-label').fill('Example favorite');
      await page.getByRole('button',{name:'Save node as favorite',exact:true}).click();
      await page.waitForFunction(()=>document.getElementById('saved-node-favorites').textContent.includes('Example favorite'));
      assert.match(await page.locator('#saved-node-favorites').innerText(),/Example favorite/);
      assert.match(await page.locator('#saved-node-recents').innerText(),/34567/);
      await page.evaluate(()=>loadStatus());
      assert.equal(await page.locator('#saved-node-favorites button[onclick^="connectSavedNode"]').count(),1);
      assert.equal((await geometry()).overflow,false,`favorite overflow at ${width}`);
      await page.locator('.saved-nodes-panel').screenshot({path:path.join(output,`${width}-saved-nodes.png`)});
      await page.getByRole('button', {name:'Show Less', exact:true}).click();
      await page.waitForFunction(() => document.querySelectorAll('#events .event-row').length === 10);
      eventFixture = [
        `${new Date(Date.now()-40000).toISOString()} | RADIO.REMOTE_TX.START | Adjacent peer Node 23456 audio start; ultimate transmitter unknown`,
        `${new Date().toISOString()} | RADIO.REMOTE_TX.END | Adjacent peer Node 23456 audio end; ultimate transmitter unknown`,
        `${now} | NODE.CONNECTED | Example connection`,
        `${now} | SYSTEM.WARNING | Example system notice`
      ].join('\n');
      await page.evaluate(()=>loadEvents());
      await page.getByRole('button', {name:'Radio',exact:true}).click();
      assert.equal(await page.locator('#events .event-row').count(),1);
      assert.match(await page.locator('#events').innerText(),/40 sec recorded interval/);
      await page.locator('#events details summary').click();
      await page.evaluate(()=>loadEvents());
      assert.equal(await page.locator('#events details').evaluate(e=>e.open),true,'refresh preserves expanded raw records');
      assert.equal((await geometry()).overflow,false,`raw event overflow at ${width}`);
      await page.locator('#operational-events-panel').screenshot({path:path.join(output,`${width}-event-history.png`)});
      await page.locator('.activity-history > summary').click();
      assert.match(await page.locator('#activity-history-summary').innerText(), /complete intervals/);
      assert.equal((await geometry()).overflow,false,`activity summary overflow at ${width}`);
      await page.locator('.activity-history').screenshot({path:path.join(output,`${width}-activity-summary.png`)});
      await page.locator('.activity-history > summary').click();
      await page.locator('#events-raw').check();
      assert.equal(await page.locator('#events .event-row').count(),2);
      assert.match(await page.locator('#events pre').first().innerText(),/RADIO.REMOTE_TX.END/);
      await page.getByRole('button', {name:'Connections',exact:true}).click();
      assert.equal(await page.locator('#events .event-row').count(),1);
      assert.match(await page.locator('#events').innerText(),/Example connection/);
      await page.getByRole('button', {name:'System',exact:true}).click();
      assert.match(await page.locator('#events').innerText(),/Example system notice/);
      await page.locator('#events-raw').uncheck();
      await page.getByRole('button', {name:'All',exact:true}).click();
      eventFixture = null;
      await page.evaluate(()=>loadEvents());
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({path:path.join(output,`${width}-dashboard.png`),fullPage:true});
      assert.equal((await geometry()).overflow,false, `overflow at ${width}`);
      assert.equal(await page.locator('#connectivity-disclosure').getAttribute('open'), null);
      const before = (await geometry()).heights;
      assert.ok(Math.max(...before)<240, `top cards too tall at ${width}: ${before}`);
      await page.screenshot({path:path.join(output,`${width}-top.png`)});
      await page.locator('a[href="#weather-disclosure"]').click();
      assert.equal(await page.locator('.weather-link').evaluate(e=>getComputedStyle(e,'::after').content), 'none', 'weather link must not inherit connectivity diagnostic caption');
      assert.equal(await page.locator('#weather-alerts img').count(), 0, 'weather descriptions must remain text');
      assert.match(await page.locator('#weather-alerts').innerText(), /XXC001/);
      assert.equal(await page.locator('#weather-overview').textContent(), 'Up to date');
      assert.match(await page.locator('#weather-freshness').textContent(), /^Last updated: /);
      assert.doesNotMatch(await page.locator('#weather-disclosure').textContent(), /Last complete|Grouped by|CURRENT/);
      await page.locator('#weather-alerts details summary').first().click();
      await page.evaluate(()=>renderWeather(weatherSource));
      assert.equal(await page.locator('#weather-alerts details').first().evaluate(e=>e.open), true, 'refresh preserves expanded description');
      assert.match(await page.locator('#emergency-weather').innerText(), /Tornado Warning/);
      assert.equal(await page.locator('body').evaluate(e=>e.classList.contains('emergency-mode')), false, 'weather must not activate Emergency Mode');
      assert.equal((await geometry()).overflow,false, `weather overflow at ${width}`);
      await page.locator('#weather-disclosure summary').first().click();
      for (const status of ['stale','unavailable']) {
        await page.evaluate(status=>renderWeather({status,alerts:[]}),status);
        assert.match(await page.locator('#weather-summary').innerText(), /Alert information/);
        assert.equal(await page.locator('#weather-alerts .weather-alert').count(),0);
        const label = status === 'stale' ? 'Information may be outdated' : 'Weather information unavailable';
        assert.equal(await page.locator('#weather-overview').textContent(), label);
        assert.equal(await page.locator('#weather-alerts').textContent(), label);
        assert.equal(await page.locator('#weather-freshness').textContent(), '');
        assert.doesNotMatch(await page.locator('#weather-disclosure').textContent(), /No active weather alerts/);
      }
      await page.evaluate(()=>renderWeather({status:'current',last_success:Date.now()/1000,alerts:[]}));
      assert.equal(await page.locator('#weather-summary').innerText(),'No active weather alerts');
      assert.equal(await page.locator('#weather-overview').textContent(), 'Up to date');
      assert.equal(await page.locator('#weather-alerts').textContent(), 'No active weather alerts');
      assert.match(await page.locator('#weather-freshness').textContent(), /^Last updated: /);
      assert.equal(await page.locator('#weather-alerts').evaluate(e=>e.nextElementSibling.id), 'weather-freshness');
      await page.evaluate(()=>renderWeather({status:'current',last_success:Date.now()/1000,alerts:
        ['Tornado Warning','Flash Flood Warning'].map(event=>({event,county_code:'XXC001',severity:4,end_time:Date.now()/1000+60}))}));
      assert.equal(await page.locator('#weather-summary').innerText(),'2 ACTIVE ALERT TYPES');
      assert.match(await page.locator('#emergency-weather').innerText(), /Tornado Warning; Flash Flood Warning/);
      await page.evaluate(()=>renderWeather({status:'current',last_success:Date.now()/1000,alerts:[{event:'Expired Warning',end_time:0}]}));
      assert.equal(await page.locator('#weather-summary').innerText(),'No active weather alerts');
      await page.evaluate(state=>renderWeather(state), fixture(detailed).weather_alerts);
      await page.locator('#connectivity-summary').click();
      assert.equal(await page.locator('#connectivity-disclosure').evaluate(e=>e.open), true);
      await page.locator('#support-prepare').click();
      await page.waitForFunction(() => !document.getElementById('support-download').disabled);
      const report = await page.locator('#support-preview').inputValue();
      assert.match(report, /BlueNode troubleshooting report/);
      assert.doesNotMatch(report, /23456|Example linked node|Do not restart Asterisk/);
      const downloadEvent = page.waitForEvent('download');
      await page.locator('#support-download').click();
      const download = await downloadEvent;
      assert.equal(download.suggestedFilename(), 'bluenode-troubleshooting.txt');
      assert.equal(fs.readFileSync(await download.path(), 'utf8'), report);
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
      assert.match(await page.locator('#emergency-banner').innerText(), /does not change automatic recovery or radio operation/);
      assert.equal((await geometry()).overflow,false,`emergency overflow at ${width}`);
      attentionUnavailable = true;
      await page.evaluate(()=>loadStatus());
      assert.match(await page.locator('#emergency-title').innerText(), /STATUS UNAVAILABLE/);
      assert.equal(await page.locator('#emergency-exit').isDisabled(), true);
      assert.match(await page.locator('#intelligence-details').innerText(), /Attention: UNKNOWN/);
      assert.doesNotMatch(await page.locator('#intelligence-details').innerText(), /Attention: NO|failures: 0/);
      assert.equal(await page.locator('#incident-list').innerText(), 'Incident history unavailable.');
      assert.equal((await geometry()).overflow,false,`unavailable overflow at ${width}`);
      attentionUnavailable = false;
      intelligenceIncomplete = true;
      await page.evaluate(()=>loadStatus());
      assert.equal(await page.locator('#intelligence-summary').innerText(), 'Node intelligence is unavailable.');
      assert.match(await page.locator('#intelligence-details').innerText(), /Attention: UNKNOWN/);
      intelligenceIncomplete = false;
      observedZero = true;
      await page.evaluate(()=>loadStatus());
      assert.equal(await page.locator('#connections-today').innerText(),'0');
      assert.equal(await page.locator('#active-connections').innerText(),'0');
      assert.equal(await page.locator('#current-session').innerText(),'None');
      connectionUnavailable = true;
      await page.evaluate(()=>loadStatus());
      assert.equal(await page.locator('#active-connections').innerText(),'Observation unavailable');
      for (const item of [
        {service:'online',query:'available',node:'available',label:'ONLINE',detail:/configured node observable/},
        {service:'online',query:'unavailable',node:'unknown',label:'RUNNING / LIMITED',detail:/cannot query/},
        {service:'online',query:'available',node:'unavailable',label:'RUNNING / LIMITED',detail:/App_Rpt node not observable/},
        {service:'unknown',query:'unavailable',node:'unknown',label:'UNKNOWN',detail:/automatic restart prohibited/},
        {service:'offline',query:'unavailable',node:'unknown',label:'OFFLINE',detail:/stopped or failed/},
        {service:'offline',query:'unavailable',node:'unknown',stale:true,label:'UNKNOWN',detail:/outdated/}
      ]) {
        asteriskCase = item;
        await page.evaluate(()=>loadStatus());
        assert.equal(await page.locator('#asterisk').innerText(),item.label);
        assert.match(await page.locator('#asterisk-detail').innerText(),item.detail);
        await checkCardAlignment();
        assert.equal((await geometry()).overflow,false,`Asterisk evidence overflow at ${width}`);
      }
      asteriskCase = null;
      const staleRoute = async route => route.fulfill({contentType:'application/json',
        body:JSON.stringify({...fixture(false), last_health_check:new Date(Date.now()-60000).toISOString()})});
      await page.route('**/state/system.json?*', staleRoute);
      await page.evaluate(() => loadStatus());
      assert.equal(await page.locator('#status').innerText(), 'UNAVAILABLE');
      assert.equal(await page.locator('#nodes').innerText(), 'Observation unavailable');
      await page.unroute('**/state/system.json?*', staleRoute);
      missing = true;
      await page.evaluate(() => prepareSupportReport());
      assert.equal(await page.locator('#support-download').isDisabled(), true);
      assert.equal(await page.locator('#support-preview').inputValue(), '');
      assert.match(await page.locator('#support-status').textContent(), /Could not read/);
      await page.evaluate(()=>loadStatus());
      assert.equal(await page.locator('#connections-today').innerText(), 'Observation unavailable');
      await page.evaluate(()=>{updateLiveConnectedTime();updateCurrentSession();});
      assert.equal(await page.locator('#current-session').innerText(), 'Observation unavailable');
      for (const [integration,message] of Object.entries({not_detected:'SkywarnPlus not detected',not_configured:'SkywarnPlus needs configuration',observer_not_configured:'Weather integration not configured',awaiting_snapshot:'Awaiting weather information'})) {
        await page.evaluate(integration=>renderWeather({status:'unavailable',integration,alerts:[]}),integration);
        assert.equal(await page.locator('#weather-summary').innerText(),message);
        assert.doesNotMatch(await page.locator('#weather-alerts').textContent(),/No active weather alerts/);
      }
      assert.equal(await page.locator('#status').innerText(),'UNAVAILABLE');
      await checkCardAlignment();
      assert.equal((await geometry()).overflow,false);
      assert.deepEqual(errors,[],`browser errors at ${width}`);
      missing = false; observedZero = false; connectionUnavailable = false; injection = true;
      await page.evaluate(async () => { await loadStatus(); await loadEvents(); });
      for (const selector of ['#events', '#nodes', '#healthreason', '#recent-sessions', '#incident-list', '#intelligence-details']) {
        assert.equal(await page.locator(selector + ' img').count(), 0, `HTML injection in ${selector}`);
        assert.ok((await page.locator(selector).textContent()).includes(hostile), `literal text in ${selector}`);
      }
      checks++;
      await page.close();
    }
    console.log(`PASS browser rendering: ${checks} viewports; diagnostics, keyboard, emergency, missing state. Screenshots: ${output}`);
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
