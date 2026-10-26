// Exercise the actual page on synthetic in-memory CRM only.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.SALES_COACHING_HARNESS_URL||'http://127.0.0.1:5065';
assert.ok(['localhost','127.0.0.1'].includes(new URL(base).hostname));
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  for(const width of [1440,390]){
   const page=await browser.newPage({viewport:{width,height:900}});
   const errors=[],unexpected=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('request',r=>{if(/email-proposal|reminder-email|brevo/.test(r.url()))unexpected.push(r.url());});
   await page.goto(base+'/__test__/login',{waitUntil:'networkidle'});
   await page.waitForFunction(()=>typeof insightsLoaded!=='undefined'&&insightsLoaded);
   for(const id of ['d-reminder-btn','email-modal-backdrop','email-performance-panel','settings-btn','view-settings','d-email-tracking-section']){
    assert.equal(await page.locator('#'+id).count(),0,id);
   }
   // These shared controls previously lived next to email-only filter logic.
   await page.locator('#chip-focus').click();
   await page.locator('#filter-modal-body input[value="second_purchase"]').check();
   await page.locator('#filter-modal-close').click();
   await page.locator('#filter-modal').waitFor({state:'hidden'});
   assert.equal(await page.evaluate(()=>filterState.focus.has('second_purchase')),true);
   await page.locator('#clear-filters-btn').click();
   assert.equal(await page.evaluate(()=>listWorkFilter==='all'&&Object.values(filterState).every(s=>s.size===0)),true);
   await page.locator('#chip-latest-contact').click();
   assert.equal(await page.locator('#filter-modal-body input[type=checkbox]').count(),4);
   await page.locator('#filter-modal-close').click();
   await page.locator('#filter-modal').waitFor({state:'hidden'});
   await page.evaluate(()=>openDetail(customers[0].row));
   await page.locator('#view-detail').waitFor({state:'visible'});
   assert.equal(await page.locator('#d-mail-btn').count(),1);
   assert.equal(await page.locator('#d-plan-btn').count(),1);
   await page.evaluate(()=>openPlanningView());
   await page.waitForFunction(()=>!planningLoading&&!planningAttentionLoading);
   assert.equal(await page.locator('#view-planning').count(),1);
   fs.mkdirSync('artifacts/email-removal',{recursive:true});
   await page.screenshot({path:path.join('artifacts/email-removal',`planning-${width}.png`)});
   // Dispatch the real footer button's handler, then verify server session removal.
   const logoutResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/logout'&&r.request().method()==='POST');
   await page.evaluate(()=>document.getElementById('logout-btn').click());
   assert.equal((await logoutResponse).status(),200);
   await page.locator('#login-screen').waitFor({state:'visible'});
   assert.equal((await page.request.get(base+'/session')).status(),401);
   assert.deepEqual(errors,[]);
   assert.deepEqual(unexpected,[]);
   await page.close();
   console.log(`${width}px: no send/tracking UI or requests; filters/reset, manual mail, planning and logout PASS`);
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
