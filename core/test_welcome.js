'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
const html = fs.readFileSync(path.join(__dirname,'../web/welcome.html'),'utf8');
(async()=>{
  const browser = await chromium.launch({headless:true,
    ...(process.env.BLUENODE_BROWSER_PATH ? {executablePath:process.env.BLUENODE_BROWSER_PATH} : {})});
  try {
    for (const width of [375,1280]) {
      const page = await browser.newPage({viewport:{width,height:900}});
      const mutations = [];
      await page.route('**/*',route=>{
        if (route.request().method() !== 'GET') mutations.push(route.request().method());
        if (new URL(route.request().url()).pathname==='/state/system.json') {
          return route.fulfill({contentType:'application/json',body:JSON.stringify({node:'23456',callsign:'<img src=x onerror=alert(1)>'})});
        }
        return route.fulfill({contentType:'text/html',body:html});
      });
      await page.goto('http://bluenode.test/web/welcome.html');
      await page.locator('#station').filter({hasText:'Node 23456'}).waitFor();
      assert.equal(await page.locator('#station img').count(),0);
      assert.equal(await page.locator('.button').getAttribute('href'),'/web/');
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      assert.deepEqual(mutations,[],'welcome page must never issue radio commands');
      if (process.env.BLUENODE_WELCOME_SCREENSHOTS) {
        fs.mkdirSync(process.env.BLUENODE_WELCOME_SCREENSHOTS,{recursive:true});
        await page.screenshot({path:path.join(process.env.BLUENODE_WELCOME_SCREENSHOTS,'welcome-'+width+'.png'),fullPage:true});
      }
      await page.route('**/state/system.json',route=>route.fulfill({status:503,body:'unavailable'}));
      await page.reload();
      await page.locator('#station').filter({hasText:'not available'}).waitFor();
      await page.close();
    }
    console.log('PASS welcome page mobile/desktop, escaped station text, unavailable state and read-only behavior');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
