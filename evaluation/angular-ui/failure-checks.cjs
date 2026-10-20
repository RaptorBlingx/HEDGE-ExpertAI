// Deliberately simulated UI failures; never count these as live Store quality evidence.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const fs=require('fs');const path=require('path');
if(!process.argv[2])throw Error('Provide a private evidence directory outside Git.');
process.umask(0o077);const root=path.resolve(process.argv[2]);fs.mkdirSync(root,{recursive:true,mode:0o700});
const repository=fs.realpathSync(path.resolve(__dirname,'../..'));
if(fs.realpathSync(root).startsWith(repository+path.sep)||fs.realpathSync(root)===repository)throw Error('Keep browser evidence outside the repository.');
const base=process.env.ANGULAR_UI_URL || 'http://127.0.0.1:8126';
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
 const checks=[];try{
 const context=await browser.newContext({viewport:{width:1440,height:1050}});const page=await context.newPage();
 await page.route('**/api/v2/catalogue?**',r=>r.fulfill({status:503,contentType:'application/problem+json',body:'{"title":"Test outage"}'}));
 await page.goto(base);await page.getByRole('button',{name:'Reload catalogue',exact:true}).waitFor();
 if(await page.locator('expert-app-card').count())throw Error('Outage fabricated Apps');checks.push('Catalogue outage is visible, no fabricated data');
 await page.unroute('**/api/v2/catalogue?**');await page.getByRole('button',{name:'Reload catalogue',exact:true}).click();await page.locator('expert-app-card').first().waitFor();checks.push('Catalogue reload recovers real data');
 await page.getByRole('button',{name:'Find an App for your needs',exact:true}).click();await page.waitForFunction(()=>document.querySelector('textarea').value==='I need an App to ');if(!(await page.getByRole('textbox').evaluate(el=>el===document.activeElement)))throw Error('Composer not focused');checks.push('Onboarding need action focuses a real editable composer');
 await page.route('**/api/v2/chat/stream',r=>r.fulfill({status:503,contentType:'application/problem+json',body:'{"title":"Simulated service outage"}'}));
 await page.getByRole('button',{name:'Explain',exact:true}).first().click();await page.getByRole('button',{name:'Retry',exact:true}).waitFor();
 await page.screenshot({path:root+'/error-recovery.png',fullPage:true});
 if(await page.locator('.recommendation-label').count())throw Error('Failure shown as recommendation');checks.push('HTTP failure stays an error with Retry, no false recommendation');
 await page.unroute('**/api/v2/chat/stream');
 const [req]=await Promise.all([page.waitForRequest(r=>r.url().endsWith('/api/v2/chat/stream')),page.getByRole('button',{name:'Retry',exact:true}).click()]);
 if(req.postDataJSON().app_action?.type!=='inspect')throw Error('Retry lost native inspection');
 await page.locator('.assistant-message').last().locator('.response-meta').waitFor();checks.push('Retry retains actual native inspection payload and recovers');
 await page.getByRole('button',{name:'New conversation',exact:true}).first().click();
 await page.locator('.clear-dialog').waitFor();
 await page.waitForFunction(()=>document.querySelector('.clear-dialog')?.contains(document.activeElement));
 for(let i=0;i<5;i++){await page.keyboard.press('Tab');await page.waitForFunction(()=>document.querySelector('.clear-dialog')?.contains(document.activeElement));}
 await page.keyboard.press('Escape');await page.locator('.clear-dialog').waitFor({state:'hidden'});
 await page.waitForFunction(()=>document.activeElement?.getAttribute('aria-label')==='New conversation');checks.push('Clear dialog traps focus through Tab cycles and Escape restores the opener');
 // Separate simulated transport/rendering checks, never live recommendation evidence.
 const injected='**Readable emphasis** <img src=x onerror="window.__injected=true"> [unsafe](javascript:alert(1))';
 const sse=t=>'data: '+JSON.stringify(t)+'\n\n';
 await page.route('**/api/v2/chat/stream',r=>r.fulfill({contentType:'text/event-stream',body:sse({type:'explanation_delta',content:injected})+sse({type:'complete'})}));
 await page.getByRole('textbox').fill('Rendering safety check');await page.getByRole('button',{name:'Send message',exact:true}).click();await page.locator('.assistant-message').last().locator('.response-meta').waitFor();
 if(await page.locator('.assistant-message').last().locator('img,script').count())throw Error('Unsafe markup rendered');
 if(await page.evaluate(()=>window.__injected))throw Error('Unsafe markup executed');
 if(!(await page.locator('.assistant-message').last().locator('strong').count()))throw Error('Markdown emphasis not rendered');checks.push('Simulated Markdown formats; source HTML escaped, script/event handlers do not run');
 await page.unroute('**/api/v2/chat/stream');
 await page.route('**/api/v2/chat/stream',r=>r.fulfill({contentType:'text/event-stream',body:sse({type:'explanation_delta',content:'Partial text, no completion.'})}));
 await page.getByRole('textbox').fill('Interrupted transport check');await page.getByRole('button',{name:'Send message',exact:true}).click();await page.locator('.assistant-message').last().getByText('The response was interrupted. Please try again.').waitFor();checks.push('Truncated SSE is labelled an error, never Complete');
 await page.unroute('**/api/v2/chat/stream');
 // Hold a simulated stream to inspect elapsed-time UI and cancellation without inference.
 await page.route('**/api/v2/chat/stream',async r=>{await new Promise(resolve=>setTimeout(resolve,7000));await r.fulfill({contentType:'text/event-stream',body:sse({type:'complete'})}).catch(()=>{});});
 await page.getByRole('textbox').fill('Slow transport check');await page.getByRole('button',{name:'Send message',exact:true}).click();await page.getByText('Waiting for your answer…',{exact:true}).waitFor();await page.screenshot({path:root+'/slower-response.png',fullPage:true});
 await page.getByRole('button',{name:'Stop response',exact:true}).click();await page.getByText('Stopped waiting. You can send another question.',{exact:true}).waitFor();checks.push('Elapsed-time state and Stop work without fabricated progress');
 await page.unroute('**/api/v2/chat/stream');
 for(const width of [320,390,768,1280]){await page.setViewportSize({width,height:900});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Horizontal overflow '+width);await page.screenshot({path:root+`/responsive-${width}.png`,fullPage:true});}checks.push('No horizontal overflow at 320/390/768/1280 px');
 await page.emulateMedia({reducedMotion:'reduce'});const animation=await page.locator('.assistant-message').last().evaluate(el=>getComputedStyle(el).animationName);if(animation!=='none')throw Error('Reduced motion ignored');checks.push('Reduced-motion animation disabled');
 const request=await context.request.post(base.replace(/\/$/,'')+'/api/v2/chat/stream',{headers:{origin:'http://untrusted.invalid'},data:{message:'not forwarded'}});if(request.status()!==403)throw Error('Cross-origin proxy request accepted');checks.push('Foreign-origin proxy POST rejected before forwarding');
 console.log(JSON.stringify(checks,null,2));fs.writeFileSync(root+'/failure-checks.json',JSON.stringify({scope:'Simulated UI fault/transport checks; not Store recommendation-quality evidence',checks},null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
