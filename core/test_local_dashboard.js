'use strict';
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
(async () => {
  const browser = await chromium.launch({headless:true,
    ...(process.env.BLUENODE_BROWSER_PATH ? {executablePath:process.env.BLUENODE_BROWSER_PATH} : {})});
  try {
    for (const width of [390, 1440]) {
      const page = await browser.newPage({viewport:{width,height:900}});
      const errors = [], requests = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => requests.push(request.url()));
      const url = pathToFileURL(path.join(__dirname, '../web/index.html')).href;
      await page.goto(url);
      assert.equal(await page.locator('#local-file-notice').isVisible(), true);
      assert.equal(await page.locator('#emergency-banner').isVisible(), false);
      assert.equal(await page.locator('#status-grid').isVisible(), false);
      assert.equal(await page.locator('button:enabled').count(), 0);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      assert.deepEqual(requests, [url]);
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log('PASS local-file guidance: mobile/desktop, no requests, disabled controls');
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
