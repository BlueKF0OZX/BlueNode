'use strict';
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.BLUENODE_BROWSER_PATH?{executablePath:process.env.BLUENODE_BROWSER_PATH}:{})});
 try {
  const page=await browser.newPage(); const posts=[]; let multiple=false, choice='11111';
  let favorites=[];
  page.on('dialog',d=>choice===null?d.dismiss():d.accept(choice));
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());
   if(url.pathname==='/web/') return route.fulfill({contentType:'text/html',body:html});
   if(url.pathname==='/api/favorites') {
    if(req.method()==='POST') favorites=[req.postDataJSON().item];
    return route.fulfill({json:{ok:true,local_node:'99999',revision:1,favorites}});
   }
   let body={},status=200;
   if(req.method()==='POST'){
    const payload=JSON.parse(req.postData()); posts.push({path:url.pathname,payload});
    if(multiple && payload.replace_current){status=409;body={ok:false,reason:'choose_current_node',connected_nodes:['11111','22222']};}
    else body={ok:true,outcome:'verified',node:payload.node,message:'Completed'};
   } else if(url.pathname==='/api/admin/session') body={enabled:false,authenticated:false};
   else {status=404;}
   await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  });
  const connect=page.locator('button[onclick="runNodeControl(\'node-connect\', this)"]');
  const setup=async()=>{await page.goto('http://bluenode.test/web/');await page.evaluate(()=>configureSavedNodes('99999',{}));await page.locator('#manual-node-number').fill('33333');};
  const click=async()=>{await connect.click();await page.waitForFunction(()=>!document.querySelector('button[onclick="runNodeControl(\'node-connect\', this)"]').disabled);};
  await setup();assert.equal(await page.locator('#auto-disconnect-current').isChecked(),false);
  assert.equal(await page.locator('#switch-from-node').count(),0);
  await click();assert.deepEqual(posts.at(-1).payload,{node:'33333'});
  await page.locator('#auto-disconnect-current').check();await click();assert.deepEqual(posts.at(-1).payload,{node:'33333',replace_current:true});
  await setup();assert.equal(await page.locator('#auto-disconnect-current').isChecked(),true,'preference survives reload');
  await page.evaluate(()=>configureSavedNodes('88888',{}));assert.equal(await page.locator('#auto-disconnect-current').isChecked(),false,'preference is scoped');
  await page.evaluate(()=>configureSavedNodes('99999',{}));assert.equal(await page.locator('#auto-disconnect-current').isChecked(),true);
  multiple=true;await click();assert.deepEqual(posts.at(-1),{path:'/api/control/node-switch',payload:{node:'33333',from_node:'11111'}});
  choice=null;let count=posts.length;await click();assert.equal(posts.length,count+1,'cancel sends no switch');assert.match(await page.locator('#control-result').textContent(),/cancelled/);
  choice='77777';count=posts.length;await click();assert.equal(posts.length,count+1,'invalid selection sends no switch');
  multiple=false;await page.locator('#favorite-node-label').fill('Favorite');await page.getByRole('button',{name:'Save node as favorite',exact:true}).click();
  await page.locator('#saved-node-favorites button[onclick^="connectSavedNode"]').click();
  await page.waitForFunction(()=>!document.querySelector('#saved-node-favorites button[onclick^="connectSavedNode"]').disabled);
  assert.deepEqual(posts.at(-1).payload,{node:'33333'},'favorites do not inherit manual switch setting');
  await page.locator('#auto-disconnect-current').uncheck();await click();assert.deepEqual(posts.at(-1).payload,{node:'33333'});
  console.log('PASS automatic switch preference, persistence, scope, multi-peer selection/cancel, and independent favorite controls');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
