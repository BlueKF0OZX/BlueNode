'use strict';
// Two independent browser stores against the real HTTP/persistence implementation.
// All state is disposable; no radio or external requests are allowed.
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {chromium} = require('playwright');
const root = path.resolve(__dirname,'..');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(),'bluenode-favorites-'));
const html = fs.readFileSync(path.join(root,'web/index.html'),'utf8');
const fixture = `import sys
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(Path.cwd() / 'core'))
import web_server
web_server.ROOT = Path(sys.argv[1])
web_server.CONFIG['node'] = '12345'
web_server._safe_config = lambda: {'state':'DISABLED'}
server = ThreadingHTTPServer(('127.0.0.1',0), web_server.NodeSmartHandler)
print(server.server_port, flush=True)
server.serve_forever()
`;
const child = spawn(process.env.BLUENODE_TEST_PYTHON || (process.platform==='win32'?'python':'python3'),
  ['-u','-c',fixture,temporary],{cwd:root,windowsHide:true,env:{...process.env,NODESMART_CONFIG:path.join(root,'config/nodesmart.example.json')}});
let browser, stderr='';
child.stderr.on('data',data=>stderr+=data);
(async()=>{
  const port = await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('Fixture startup timed out: '+stderr)),10000);
    child.once('error',e=>{clearTimeout(timer);reject(e);});
    child.once('exit',code=>{clearTimeout(timer);reject(Error('Fixture exited '+code+': '+stderr));});
    child.stdout.once('data',data=>{clearTimeout(timer);resolve(Number(String(data).trim()));});
  });
  assert.ok(Number.isInteger(port)&&port>0);
  const origin='http://127.0.0.1:'+port;
  browser=await chromium.launch({headless:true,...(process.env.BLUENODE_BROWSER_PATH?{executablePath:process.env.BLUENODE_BROWSER_PATH}:{})});
  const pc=await browser.newPage({viewport:{width:1440,height:1000}});
  const phone=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const errors=[];
  for(const page of [pc,phone]) {
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',async route=>{
      const request=route.request(), url=new URL(request.url());
      assert.equal(url.origin,origin);
      if(url.pathname==='/api/favorites') return route.continue();
      assert.equal(request.method(),'GET','favorites must never invoke a control');
      if(url.pathname==='/web/') return route.fulfill({contentType:'text/html',body:html});
      if(url.pathname==='/state/system.json') return route.fulfill({contentType:'application/json',body:JSON.stringify({
        node:'12345',callsign:'N0CALL',status:'healthy',asterisk:'online',internet:'online',
        connected_nodes:[],friendly_nodes:{},last_health_check:new Date().toISOString()})});
      if(url.pathname==='/api/admin/session') return route.fulfill({json:{enabled:false,authenticated:false,state:'DISABLED'}});
      return route.fulfill({status:404,json:{}});
    });
  }
  await pc.addInitScript(()=>localStorage.setItem('bluenode:nodes:v1:12345',JSON.stringify({favorites:[{node:'23456',label:'Imported favorite'}],recent:[]})));
  await pc.goto(origin+'/web/');await phone.goto(origin+'/web/');
  await pc.waitForFunction(()=>sharedFavoritesState==='ready');
  await phone.waitForFunction(()=>sharedFavoritesState==='ready');
  await pc.locator('#import-browser-favorites').click();
  await phone.waitForFunction(()=>document.getElementById('saved-node-favorites').textContent.includes('Imported favorite'));
  phone.once('dialog',dialog=>dialog.accept('Phone rename'));
  await phone.getByRole('button',{name:'Edit name for favorite node 23456',exact:true}).click();
  await pc.waitForFunction(()=>document.getElementById('saved-node-favorites').textContent.includes('Phone rename'));
  await pc.locator('#manual-node-number').fill('34567');
  await pc.locator('#favorite-node-label').fill('PC favorite');
  await pc.getByRole('button',{name:'Save node as favorite',exact:true}).click();
  await phone.waitForFunction(()=>document.getElementById('saved-node-favorites').textContent.includes('PC favorite'));
  await phone.getByRole('button',{name:'Remove favorite node 23456',exact:true}).click();
  await pc.waitForFunction(()=>!document.getElementById('saved-node-favorites').textContent.includes('Phone rename'));
  for(const page of [pc,phone]) {
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal overflow');
    assert.equal(await page.locator('#saved-node-favorites button').evaluateAll(buttons=>buttons.every(b=>b.getBoundingClientRect().height>=44)),true);
  }
  if(process.env.BLUENODE_RENDER_OUTPUT) {
    fs.mkdirSync(process.env.BLUENODE_RENDER_OUTPUT,{recursive:true});
    await pc.locator('.saved-nodes-panel').screenshot({path:path.join(process.env.BLUENODE_RENDER_OUTPUT,'shared-favorites-pc.png')});
    await phone.locator('.saved-nodes-panel').screenshot({path:path.join(process.env.BLUENODE_RENDER_OUTPUT,'shared-favorites-phone.png')});
  }
  await phone.reload();
  await phone.waitForFunction(()=>document.getElementById('saved-node-favorites').textContent.includes('PC favorite'));
  assert.deepEqual(await phone.evaluate(()=>JSON.parse(localStorage.getItem('bluenode:nodes:v1:12345')).favorites),[],'shared favorites do not depend on the PC browser store');
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(temporary,'state/favorites.json'),'utf8')).favorites,[{node:'34567',label:'PC favorite'}]);
  assert.deepEqual(errors,[]);
  console.log('PASS real HTTP favorites: independent phone/PC import, save, rename, removal, automatic refresh, reload, touch targets and persistence');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  if(browser) await browser.close();
  if(child.exitCode===null) {const stopped=once(child,'exit');child.kill();await stopped;}
  if(path.dirname(temporary)===os.tmpdir()&&path.basename(temporary).startsWith('bluenode-favorites-')) fs.rmSync(temporary,{recursive:true,force:true});
});
