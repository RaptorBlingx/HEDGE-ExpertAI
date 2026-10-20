// UI acceptance checks against the real services. One real response is deliberately
// delayed in transport to inspect waiting/focus; its latency is NOT inference evidence.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const fs=require('fs'); const path=require('path');
if(!process.argv[2])throw Error('Provide a private evidence directory outside Git.');
process.umask(0o077);
const root=path.resolve(process.argv[2]);fs.mkdirSync(root,{recursive:true,mode:0o700});
const repository=fs.realpathSync(path.resolve(__dirname,'../..'));
if(fs.realpathSync(root).startsWith(repository+path.sep)||fs.realpathSync(root)===repository)throw Error('Keep Store evidence outside Git.');
const base=process.env.ANGULAR_UI_URL || 'http://127.0.0.1:8136';
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
 const checks=[],errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1050}});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.locator('expert-app-card').first().waitFor();
  await page.getByRole('button',{name:'Explore the catalogue',exact:true}).click();
  await page.locator('.assistant-message .response-meta').waitFor();
  await page.locator('.answer-source').first().click();
  await page.waitForFunction(()=>document.querySelector('.detail-dialog')?.contains(document.activeElement));
  for(let i=0;i<8;i++){
   await page.keyboard.press(i<4?'Tab':'Shift+Tab');
   if(!(await page.locator('.detail-dialog').evaluate(el=>el.contains(document.activeElement))))throw Error('Source dialog lost keyboard focus');
  }
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>document.activeElement?.classList.contains('answer-source'));
  checks.push('Actual source dialog traps Tab/Shift+Tab, Escape restores the exact opener');
  await wait(3100);
  const responsePromise=page.waitForResponse(r=>r.url().endsWith('/api/v2/chat/stream'),{timeout:60000});
  // The endpoint really processes this request. Only delivery to this test tab is held.
  await page.route('**/api/v2/chat/stream',async route=>{
   const response=await route.fetch();
   await wait(38000);
   await route.fulfill({response});
  });
  await page.getByRole('textbox').fill('List the Apps and explain what they do.');
  await page.getByRole('button',{name:'Send message',exact:true}).click();
  await page.getByRole('textbox').fill('My next question is still a draft');
  await page.locator('.slow-note').waitFor({timeout:20000});
  await page.screenshot({path:root+'/waiting-10s.png',fullPage:true});
  await page.locator('.conversation-scroll').evaluate(el=>{el.scrollTop=0;});
  await page.locator('.answer-source').first().click();
  await page.locator('.source-fields').waitFor();
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Latest response',exact:true}).click();
  await page.getByRole('textbox').focus();
  await page.getByText('This is taking longer than usual. You can keep waiting, or stop and try again.',{exact:true}).waitFor({timeout:35000});
  await page.screenshot({path:root+'/waiting-30s.png',fullPage:true});
  await responsePromise;
  await page.getByRole('button',{name:'Stop response',exact:true}).waitFor({state:'hidden',timeout:20000});
  if(await page.getByRole('textbox').inputValue()!=='My next question is still a draft')throw Error('Draft lost after delayed answer');
  if(!(await page.getByRole('textbox').evaluate(el=>el===document.activeElement)))throw Error('Completion stole focus');
  if(!(await page.locator('.assistant-message').last().innerText()).includes('Semantic Treehouse'))throw Error('Delayed real response missing');
  checks.push('10–38s delayed real response: honest waiting, readable history/source, preserved draft/focus, real recovery');
  await page.unroute('**/api/v2/chat/stream');
  await page.getByRole('button',{name:'New conversation',exact:true}).first().click();
  await page.waitForFunction(()=>document.querySelector('.clear-dialog')?.contains(document.activeElement));
  await page.keyboard.press('Escape');
  await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')==='New conversation');
  checks.push('Clear confirmation traps and restores focus');
  await page.emulateMedia({reducedMotion:'reduce'});
  if(await page.locator('.assistant-message').last().evaluate(el=>getComputedStyle(el).animationName)!=='none')throw Error('Reduced motion ignored');
  checks.push('Reduced motion respected');
  const foreign=await page.request.post(base+'/api/v2/chat/stream',{headers:{origin:'http://untrusted.invalid'},data:{message:'not forwarded'}});
  if(foreign.status()!==403)throw Error('Foreign origin forwarded');
  checks.push('Foreign-origin POST still rejected');
  // Viewport captures preserve Chromium touch emulation; full-page captures can
  // reset pointer media queries when they temporarily resize a tablet viewport.
  // A separate touch browser: CSS pointer/hover behavior differs from a resized mouse window.
  const mobile=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:1});
  mobile.on('pageerror',e=>errors.push(e.message));
  await mobile.goto(base+'/?view=pane');await mobile.locator('expert-app-card').first().waitFor({state:'attached'});
  await wait(350);await mobile.screenshot({path:root+'/mobile.png',fullPage:false});
  const sizes=[];
  for(const [width,height] of [[320,640],[390,520],[390,844],[768,1024],[1280,800]]){
   await mobile.setViewportSize({width,height});await wait(200);
   const size=await mobile.evaluate(()=>({width:innerWidth,height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth,composer:document.querySelector('.composer').getBoundingClientRect().toJSON()}));
   if(size.overflow||size.composer.bottom>height+1)throw Error('Overflow/composer below viewport '+width+'x'+height);
   sizes.push(size);
   if(width===768)await mobile.screenshot({path:root+'/tablet.png',fullPage:false});
  }
  await mobile.setViewportSize({width:390,height:844});await wait(250);
  await mobile.getByRole('button',{name:/^Apps /}).click();
  await mobile.locator('.select-app').first().waitFor();
  if(!(await mobile.evaluate(()=>matchMedia('(pointer: coarse)').matches)))throw Error('Browser lost touch emulation');
  const select=await mobile.locator('.select-app').first().evaluate(el=>el.getBoundingClientRect().toJSON());
  if(select.width<43.9||select.height<43.9)throw Error('Touch comparison target too small: '+JSON.stringify(select));
  await mobile.screenshot({path:root+'/mobile-apps.png',fullPage:false});
  checks.push('Touch targets and visible composer at 320/390/768/1280 widths, including short 520px viewport');
  await mobile.getByRole('button',{name:'Conversation',exact:true}).click();
  await mobile.getByRole('button',{name:'Explore the catalogue',exact:true}).click();
  await mobile.locator('.assistant-message .response-meta').waitFor();
  await mobile.screenshot({path:root+'/mobile-conversation.png',fullPage:false});
  if(await mobile.getByRole('textbox').evaluate(el=>el===document.activeElement))throw Error('Touch completion forced a keyboard focus');
  await mobile.getByRole('button',{name:'Switch to dark theme'}).click();await wait(300);
  await mobile.screenshot({path:root+'/mobile-dark.png',fullPage:false});
  checks.push('Actual mobile catalogue conversation, no forced keyboard on completion, dark theme');
  // Remove only the conversations created by this check.
  for(const current of [page,mobile]){
   await current.getByRole('button',{name:'New conversation',exact:true}).first().click();
   await current.getByRole('button',{name:'Start fresh',exact:true}).click();
   await current.locator('.clear-dialog').waitFor({state:'hidden'});
  }
  fs.writeFileSync(root+'/polish-checks.json',JSON.stringify({scope:'Real services; waiting screenshots use deliberately delayed transport, not measured inference',checks,sizes,errors},null,2));
  if(errors.length)throw Error(errors.join('\n'));
  console.log(JSON.stringify({checks,errors},null,2));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
