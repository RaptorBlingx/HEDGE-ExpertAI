// Protected answers remain in the private session/UI. Console evidence is aggregate only.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
(async () => {
  const base = process.env.STORE_BROWSER_URL || 'http://127.0.0.1:8098';
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({headless:true,
    ...(process.env.STORE_BROWSER_EXECUTABLE ? {executablePath:process.env.STORE_BROWSER_EXECUTABLE}:{}),
    args:['--disable-dev-shm-usage']});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    page.setDefaultTimeout(900000);
    const errors=[];
    page.on('pageerror',()=>errors.push('browser_error'));
    await page.goto(base);
    await page.locator('.he-input').waitFor();
    const catalogue=await(await page.request.get(base+'/api/v2/catalogue')).json();
    assert.ok(catalogue.apps.length>=2);
    const turns=[];
    const ask=async(label,question)=>{
      const pending=page.waitForResponse(r=>r.url().endsWith('/api/v2/chat/stream'));
      await page.locator('.he-input').fill(question);
      await page.locator('.he-send-btn').click();
      const started=Date.now();
      const monitor=setInterval(async()=>{
        try {
          const stage=await page.locator('.he-stage').last().textContent();
          const phase=/Checking/.test(stage)?'review':/Refining/.test(stage)?'revision':
            /Writing/.test(stage)?'writing':/Understanding/.test(stage)?'interpretation':'working';
          console.log(JSON.stringify({case:label,progress:phase,elapsed_seconds:Math.round((Date.now()-started)/1000)}));
        } catch (_) { /* Browser may close after a failed assertion. */ }
      },60000);
      let payload;
      try {payload=await(await pending).text();} finally {clearInterval(monitor);}
      const events=payload.split('\n').filter(l=>l.startsWith('data: ')).map(l=>JSON.parse(l.slice(6)));
      await page.waitForFunction(()=>window.storeEvaluation&&!window.storeEvaluation.isStreaming);
      const complete=events.at(-1);
      const apps=events.find(e=>e.type==='recommendations')?.apps || [];
      const text=events.filter(e=>e.type==='explanation_delta').map(e=>e.content).join('');
      const summary={case:label,terminal:complete?.type,intent:complete?.intent,apps:apps.length,
        generation:complete?.generation?.source,reason:complete?.generation?.reason,
        stage:complete?.generation?.stage,repair_count:complete?.generation?.repair_count || 0,
        review_reason:complete?.generation?.review_reason,commercial_assessment:complete?.generation?.commercial_assessment,failure_type:complete?.generation?.failure_type,
        seconds:complete?.generation?.seconds,characters:text.length,
        citation_count:complete?.generation?.citations?.length || 0,
        citation_fields:[...new Set((complete?.generation?.citations||[]).map(c=>c.field))],
        named_apps:apps.filter(r=>r.app.name&&text.includes(r.app.name)).length,
        stages:[...new Set(events.filter(e=>e.type==='stage').map(e=>e.stage))]};
      console.log(JSON.stringify(summary));
      assert.equal(complete.type,'complete');
      assert.equal(complete.generation?.source,'ollama');
      assert.equal(complete.generation?.reason,'reviewed_source_synthesis');
      if (apps.length) assert.ok(apps.every(r=>complete.generation.citations.some(c=>c.rank===r.rank)));
      assert.ok(!text.includes('These are source records') && !text.includes('Local Store snapshot observed at'));
      assert.ok(!text.includes('Compatibility, suitability and billing terms are not verified'));
      assert.ok(apps.every(r=>catalogue.apps.some(a=>a.id===r.app.id&&a.app_id===r.app.app_id&&a.store_id===r.app.store_id)));
      assert.ok(text.length>30&&text.length<3000);
      assert.equal(await page.locator('.he-card script, .he-card img').count(),0);
      turns.push({label,question,text,apps,complete});
      return turns.at(-1);
    };
    const inspectSource=async(app)=>{
      const card=page.locator('.he-card').filter({has:page.getByRole('button',{name:'Explain '+(app.name||'Unnamed App'),exact:true})}).first();
      await card.locator('.he-card-evidence summary').click();
      const values=await card.locator('.he-card-evidence dd').allTextContents();
      assert.ok(app.source_evidence?.readme);
      assert.ok(values.some(value=>value.replace(/\r\n/g,'\n')===app.source_evidence.readme.replace(/\r\n/g,'\n')));
      assert.equal(await card.locator('script, img').count(),0);
    };
    if (process.env.STORE_CONVERSATION_HTTP === 'true') {
      let result;
      if (process.env.STORE_CONVERSATION_SESSION_FILE) {
        result={session_id:require('node:fs').readFileSync(process.env.STORE_CONVERSATION_SESSION_FILE,'utf8').trim()};
        console.log(JSON.stringify({case:'HTTP discovery checkpoint',resumed:true}));
      } else {
        const response=await page.request.post(base+'/api/v2/chat',{timeout:900000,
          data:{message:process.env.STORE_CONVERSATION_SEARCH_QUERY||'Find Apps for semantic data modelling'}});
        assert.equal(response.status(),200);
        result=await response.json();
        const channels=[...new Set(result.apps.flatMap(r=>r.evidence_fields||[]))];
        console.log(JSON.stringify({case:'HTTP discovery',intent:result.intent,apps:result.apps.length,
          nlu:result.nlu?.source,generation:result.generation?.source,reason:result.generation?.reason,
          citation_count:result.generation?.citations?.length,channels}));
        assert.equal(result.intent,'search');
        assert.equal(result.generation.source,'ollama');
        assert.ok(result.apps.length>0&&result.generation.citations.length>0);
        assert.ok(channels.some(channel=>['dense','lexical'].includes(channel)));
      }
      await page.evaluate(id=>sessionStorage.setItem('hedge_session_id',id),result.session_id);
      await page.reload();
      await page.waitForFunction(()=>window.storeEvaluation&&!window.storeEvaluation.isStreaming&&document.querySelectorAll('.he-msg--user').length>0);
      assert.ok((await page.locator('.he-msg--assistant').allInnerTexts()).some(text=>text.includes('Sources:')));
      if (process.env.STORE_CONVERSATION_SMOKE === 'true') {
        assert.ok(!process.env.STORE_CONVERSATION_SESSION_FILE);
        console.log(JSON.stringify({result:'HTTP_SMOKE_PASS',checks:'fresh HTTP retrieval and reviewed model answer restored in browser with source citations'}));
        return;
      }
      const suitable=await ask('contextual use case','Which one would help me work with semantic models, and why?');
      assert.ok(suitable.apps.length>0 && suitable.complete.generation.citations.length>0);
      await ask('cited simplification','Explain that in simpler terms, without technical jargon.');
      if (turns.at(-1).complete.generation.citations.length) {
        assert.ok((await page.locator('.he-msg--assistant').last().innerText()).includes('Sources:'));
      }
      assert.deepEqual(errors,[]);
      const focus=catalogue.apps[0];
      let detail=await ask('named detail','What would I use '+focus.name+' for?');
      assert.deepEqual(detail.complete.generation.focus_ids,[focus.id]);
      assert.ok(detail.apps.some(row=>row.app.id===focus.id));
      await inspectSource(detail.apps.find(r=>r.app.id===focus.id).app);
      detail=await ask('other App','What about the other one?');
      assert.equal(detail.complete.generation.focus_ids.length,1);
      assert.notEqual(detail.complete.generation.focus_ids[0],focus.id);
      const comparison=await ask('comparison after focus','How do their deployment requirements differ?');
      assert.equal(comparison.apps.length,2);
      await ask('billing uncertainty','Are they free, and do you know what currency the Store uses?');
      const negative=await ask('genuine no match','Would either warn me about earthquakes?');
      assert.equal(negative.apps.length,0);
      assert.equal(negative.complete.impression_id,null);
      assert.ok(/earthquake/i.test(negative.text));
      const source=await(await page.request.post(base+'/api/v2/chat',{data:{message:'Show README for '+focus.app_id}})).json();
      assert.equal(source.intent,'source_fields');
      assert.equal(source.apps[0].app.id,focus.id);
      await page.reload();
      await page.waitForFunction(()=>window.storeEvaluation&&!window.storeEvaluation.isStreaming&&document.querySelectorAll('.he-msg--user').length>0);
      assert.equal(await page.locator('.he-card').count(),0);
      console.log(JSON.stringify({result:process.env.STORE_CONVERSATION_SESSION_FILE?'RESUMED_CONVERSATION_PASS':'HTTP_PASS',fresh_http:!process.env.STORE_CONVERSATION_SESSION_FILE,turns:turns.length+(process.env.STORE_CONVERSATION_SESSION_FILE?0:1),checks:'restored UI, contextual SSE with citations, named/other references, comparison, billing unknowns, no-match without impressions, complete README inspection'}));
      return;
    }
    let r;
    if (process.env.STORE_CONVERSATION_SESSION_FILE) {
      const id=require('node:fs').readFileSync(process.env.STORE_CONVERSATION_SESSION_FILE,'utf8').trim();
      await page.evaluate(value=>sessionStorage.setItem('hedge_session_id',value),id);
      await page.reload();
      await page.waitForFunction(()=>window.storeEvaluation&&!window.storeEvaluation.isStreaming&&document.querySelectorAll('.he-msg--user').length>0);
      assert.equal(await page.locator('.he-card').count(),2);
      turns.push({label:'restored approved introduction',text:await page.locator('.he-msg--assistant').last().innerText()});
      console.log(JSON.stringify({case:'approved introduction',restored:true,apps:2}));
    } else {
      r=await ask('introduction','What apps are available, and what is each one useful for?');
      assert.equal(r.apps.length,2);
    }
    r=await ask('natural comparison','What is the main difference between them?');
    assert.equal(r.apps.length,2);
    assert.notEqual(r.text,turns[0].text);
    if (process.env.STORE_CONVERSATION_SMOKE === 'true') {
      console.log(JSON.stringify({result:'SMOKE_PASS',turns:2,catalogue_count:catalogue.total}));
      return;
    }
    r=await ask('contextual use case','Which one would help me work with semantic models, and why?');
    assert.ok(r.apps.length>0 && r.complete.generation.citations.length>0);
    r=await ask('simplification','Explain that in simpler terms, without technical jargon.');
    assert.notEqual(r.text,turns.at(-2).text);
    const focus=catalogue.apps[0];
    r=await ask('named detail','What would I use '+focus.name+' for?');
    assert.deepEqual(r.complete.generation.focus_ids,[focus.id]);
    assert.ok(r.apps.some(row=>row.app.id===focus.id));
    await inspectSource(r.apps.find(row=>row.app.id===focus.id).app);
    r=await ask('other App','What about the other one?');
    assert.equal(r.complete.generation.focus_ids.length,1);
    assert.notEqual(r.complete.generation.focus_ids[0],focus.id);
    r=await ask('comparison after focus','How do their deployment requirements differ?');
    assert.equal(r.apps.length,2);
    r=await ask('billing uncertainty','Are they free, and do you know what currency the Store uses?');
    r=await ask('genuine no match','Would either warn me about earthquakes?');
    assert.equal(r.apps.length,0);
    assert.equal(r.complete.impression_id,null);
    assert.ok(/earthquake/i.test(r.text));
    // Source inspection remains available separately from fluent conversation.
    const source=await(await page.request.post(base+'/api/v2/chat',{data:{message:'Show README for '+focus.app_id}})).json();
    assert.equal(source.intent,'source_fields');
    assert.equal(source.apps[0].app.id,focus.id);
    await page.reload();
    await page.locator('.he-input').waitFor();
    await page.waitForFunction(()=>window.storeEvaluation&&!window.storeEvaluation.isStreaming&&document.querySelectorAll('.he-msg--user').length>0);
    await page.waitForFunction(()=>document.querySelectorAll('.he-card').length===0);
    const session=await page.evaluate(()=>window.storeEvaluation.sessionId);
    const ordinal=await page.request.post(base+'/api/v2/chat',{timeout:900000,
      data:{message:'Tell me about the first App',session_id:session}});
    assert.equal(ordinal.status(),200);
    const normal=await ordinal.json();
    console.log(JSON.stringify({case:'normal HTTP ordinal follow-up',apps:normal.apps.length,
      generation:normal.generation?.source,reason:normal.generation?.reason,
      citations:normal.generation?.citations?.length}));
    assert.equal(normal.generation?.source,'ollama');
    assert.deepEqual(normal.generation.focus_ids,[catalogue.apps[0].id]);
    assert.ok(normal.apps.some(row=>row.app.id===catalogue.apps[0].id));
    assert.ok(normal.generation.citations.length>0);
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({result:'PASS',turns:turns.length+1,catalogue_count:catalogue.total,
      checks:'real synthesis and review, conversational comparisons, use-case reasoning, simplification, named/other references, billing unknowns, abstention, source inspection, restored history'}));
  } finally {await browser.close();}
})().catch(error=>{console.error(JSON.stringify({result:'FAIL',error_type:error.name,location:/store-expert-conversation\.cjs:\d+:\d+/.exec(error.stack||'')?.[0],details:'protected prose suppressed'}));process.exitCode=1;});
