// Real-service UI evaluation; review complete answers, do not grade quality from keyword matches.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const fs=require('fs');const path=require('path');
if(!process.argv[2]) throw Error('Provide a private evidence directory outside Git.');
process.umask(0o077);const root=path.resolve(process.argv[2]);fs.mkdirSync(root,{recursive:true,mode:0o700});
const repository=fs.realpathSync(path.resolve(__dirname,'../..'));
if(fs.realpathSync(root).startsWith(repository+path.sep)||fs.realpathSync(root)===repository)throw Error('Keep real Store evidence outside the repository.');
const base=process.env.ANGULAR_UI_URL || 'http://127.0.0.1:8126';
const wait=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.BROWSER_EXECUTABLE?{executablePath:process.env.BROWSER_EXECUTABLE}:{})});
 try {
 const page=await browser.newPage({viewport:{width:1440,height:1050}});const errors=[],turns=[],uiChecks=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('console',e=>{if(e.type()==='error')errors.push(e.text())});
 await page.addInitScript(()=>{window.__records=[];const original=window.fetch;window.fetch=async(...args)=>{const started=performance.now();const r=await original(...args);if(String(args[0]).endsWith('/api/v2/chat/stream'))r.clone().text().then(body=>window.__records.push({request:JSON.parse(args[1].body),status:r.status,elapsedMs:performance.now()-started,body}));return r}});
 async function idle(){await page.waitForFunction(()=>window.__records.length>0,null,{timeout:150000});await page.waitForFunction(()=>!document.querySelector('button[aria-label="Stop response"]'),null,{timeout:150000});await page.waitForTimeout(300);const rows=await page.evaluate(()=>window.__records.splice(0));for(const r of rows)turns.push({...r,events:r.body.split(/\r?\n/).filter(l=>l.startsWith('data:')).map(l=>JSON.parse(l.slice(5)))});}
 async function ask(q){await wait(3100);await page.getByLabel('Ask ExpertAI about Store applications',{exact:true}).fill(q);await page.getByRole('button',{name:'Send message',exact:true}).click();const captures=[12,35].map(seconds=>setTimeout(()=>{if(!page.isClosed())page.locator('.waiting').count().then(n=>n&&page.screenshot({path:root+`/actual-wait-${seconds}s.png`,fullPage:true})).catch(()=>{});},seconds*1000));try{await idle();}finally{captures.forEach(clearTimeout);}console.log('ANSWER',q,'\n',await page.locator('.assistant-message').last().innerText());}
 await page.goto(base);const catalogue=await page.evaluate(async()=>{const r=await fetch('/api/v2/catalogue');if(!r.ok)throw Error('Catalogue unavailable');return r.json()});
 if(catalogue.apps.length<2)throw Error('This comparative smoke check needs two authorized Apps.');const [first,second]=catalogue.apps;
 await page.getByRole('button',{name:first.name,exact:true}).waitFor();await page.waitForTimeout(900);
 const startup=await page.evaluate(()=>({navigation:performance.getEntriesByType('navigation').map(e=>({domContentLoaded:e.domContentLoadedEventEnd,load:e.loadEventEnd})),paint:performance.getEntriesByType('paint').map(e=>({name:e.name,milliseconds:e.startTime})),resources:performance.getEntriesByType('resource').filter(e=>/\.(js|css|woff2)$/.test(e.name)).map(e=>({name:e.name.split('/').pop(),encodedBytes:e.encodedBodySize,decodedBytes:e.decodedBodySize}))}));
 await page.screenshot({path:root+'/desktop.png',fullPage:true});
 await page.getByRole('button',{name:'Switch to dark theme'}).click();await wait(300);await page.screenshot({path:root+'/desktop-dark.png',fullPage:true});await page.getByRole('button',{name:'Switch to light theme'}).click();await wait(300);
 await page.getByRole('button',{name:'Embedded pane',exact:true}).click();await wait(300);await page.screenshot({path:root+'/embedded.png',fullPage:true});
 await page.getByRole('button',{name:'Close assistant',exact:true}).click();await page.getByRole('button',{name:/Ask ExpertAI/}).click();
 await page.getByRole('button',{name:'Expand workspace',exact:true}).click();
 await page.getByRole('button',{name:'Explore the catalogue',exact:true}).click();await idle();
 await page.getByRole('button',{name:'Explain',exact:true}).first().click();await idle();
 const requestsBefore=turns.length;
 await page.locator('.answer-source').last().click();await page.locator('.source-fields').waitFor();
 if(!(await page.locator('.source-fields').innerText()).includes('readme'))throw Error('Inline source lacks real evidence');
 await page.keyboard.press('Escape');if(turns.length!==requestsBefore||await page.evaluate(()=>window.__records.length))throw Error('Source inspection sent a chat turn');uiChecks.push('Answer source opens actual metadata without inference');
 await ask('Who provides it?');
 await page.getByRole('button',{name:'Make it simpler',exact:true}).click();await idle();
 await page.getByRole('button',{name:first.name,exact:true}).click();await idle();
 await page.getByRole('button',{name:'Source evidence',exact:true}).click();await page.screenshot({path:root+'/source-evidence.png',fullPage:true});
 if(!(await page.locator('.source-fields').innerText()).includes('readme'))throw Error('Missing real evidence');
 await page.keyboard.press('Escape');
 await page.getByRole('button',{name:'Select '+first.name+' for comparison',exact:true}).click();await page.getByRole('button',{name:'Select '+second.name+' for comparison',exact:true}).click();
 await page.getByRole('button',{name:'Compare',exact:true}).click();await idle();await page.screenshot({path:root+'/comparison.png',fullPage:true});
 if(await page.locator('.recommendation-label').count())throw Error('Comparison labelled recommendation');
 uiChecks.push('Catalogue/comparison entries are not recommendations');
 await page.locator('.conversation-scroll').evaluate(el=>{el.scrollTop=0;});await page.getByRole('button',{name:'Latest response',exact:true}).click();
 await page.waitForFunction(()=>{const el=document.querySelector('.conversation-scroll');return el.scrollHeight-el.scrollTop-el.clientHeight<3});
 if(!(await page.locator('.conversation-scroll').evaluate(el=>el===document.activeElement)))throw Error('Latest response lost keyboard focus');
 uiChecks.push('Long conversation can scroll back and return to latest with focus');
 // Reload must restore the same server session and full answers.
 const before=await page.locator('.messages').innerText();const session=await page.evaluate(()=>sessionStorage.getItem('hedge-expertai-angular-session'));
 await page.reload();await page.getByText('Restoring your conversation…').waitFor({state:'hidden'});await page.waitForTimeout(300);
 const after=await page.locator('.messages').innerText();if(!session||!(after.includes('Who provides it?')&&after.includes(first.provider)))throw Error('History/context not restored');
 await ask('List only free applications.');
 await page.getByRole('button',{name:'New conversation',exact:true}).first().click();await page.getByRole('button',{name:'Start fresh',exact:true}).click();await page.getByRole('button',{name:'Explore the catalogue',exact:true}).waitFor();
 await ask(process.env.MODEL_QUESTION || 'Our partners use different names and formats for the same data. We need everyone to understand the data consistently. What would you suggest?');
 await page.locator('expert-app-card').first().locator('.recommendation-label').waitFor();
 await page.screenshot({path:root+'/recommendation.png',fullPage:true});
 await page.getByRole('button',{name:'Switch to dark theme'}).click();await wait(300);await page.screenshot({path:root+'/recommendation-dark.png',fullPage:true});await page.getByRole('button',{name:'Switch to light theme'}).click();await wait(300);
 uiChecks.push('Real source-supported recommendation first with evidence and documented-match badge');
 await ask('Who provides it?');
 await page.screenshot({path:root+'/conversation.png',fullPage:true});
 await page.getByRole('button',{name:'Embedded pane',exact:true}).click();await wait(300);await page.screenshot({path:root+'/embedded-conversation.png',fullPage:true});
 await page.getByRole('button',{name:'Switch to dark theme'}).click();await wait(300);await page.screenshot({path:root+'/embedded-dark.png',fullPage:true});await page.getByRole('button',{name:'Switch to light theme'}).click();await wait(300);
 await page.setViewportSize({width:390,height:844});await wait(300);await page.waitForFunction(()=>{const el=document.querySelector('.conversation-scroll');return el.scrollHeight-el.scrollTop-el.clientHeight<3});uiChecks.push('Latest answer remains visible after pane/mobile resize');await page.screenshot({path:root+'/mobile-conversation.png',fullPage:true});
 await page.getByRole('button',{name:new RegExp('Apps '+catalogue.total)}).click();await page.screenshot({path:root+'/mobile-apps.png',fullPage:true});
 await page.getByRole('button',{name:second.name,exact:true}).click();await idle();await page.screenshot({path:root+'/mobile-details.png',fullPage:true});await page.keyboard.press('Escape');
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);if(overflow)throw Error('Mobile horizontal overflow');
 await page.getByRole('button',{name:'Conversation',exact:true}).click();
 await page.getByRole('button',{name:'New conversation',exact:true}).first().click();await page.getByRole('button',{name:'Start fresh',exact:true}).click();await page.locator('.clear-dialog').waitFor({state:'hidden'});await page.getByRole('button',{name:'Explore the catalogue',exact:true}).waitFor();await page.screenshot({path:root+'/mobile.png',fullPage:true});
 fs.writeFileSync(root+'/browser-results.json',JSON.stringify({errors,turns,startup,uiChecks,historyRestored:after.includes(first.provider),overflow},null,2));console.log('DONE',JSON.stringify({turns:turns.length,errors,overflow}));} finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1)});
