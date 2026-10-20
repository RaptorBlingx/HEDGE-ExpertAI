const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const fs = require('fs');
(async () => {
  process.umask(0o077);
  const browser = await chromium.launch({ headless: true, ...(process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {}) });
  try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on('response', response => { if (response.status() >= 400) errors.push(response.status() + ' ' + response.url()); });
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  await page.goto(process.env.WIDGET_BASE_URL || 'http://127.0.0.1:8106');
  await page.waitForSelector('.he-input', { timeout: 600000 });
  const sessions = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const out = [];
  for (const session of sessions) {
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
    await page.reload();
    await page.waitForSelector('.he-input');
    await page.evaluate(() => window.storeEvaluation.open());
    await page.locator('.he-locale').selectOption(session.locale);
    for (const q of session.questions) {
      const start = Date.now();
      // A question can be text or {click: <displayed App name>}. Exercise the
      // actual card handler, not an imitation of its expected HTTP payload.
      const [response] = await Promise.all([
        page.waitForResponse(r => r.url().endsWith('/api/v2/chat/stream'), { timeout: 600000 }),
        (async () => {
          if (typeof q === 'object') {
            await page.getByRole('button', {name: 'Explain ' + q.click, exact: true}).last().click();
          } else {
            await page.locator('.he-input').fill(q);
            await page.locator('.he-input').press('Enter');
          }
        })(),
      ]);
      const body = await response.text();
      await page.waitForFunction(() => !document.querySelector('.he-input').disabled, { timeout: 600000 });
      const seconds = (Date.now() - start) / 1000;
      const events = body.split('\n').filter(l => l.startsWith('data: ')).map(l => JSON.parse(l.slice(6)));
      const complete = events.find(e => e.type === 'complete') || {};
      const recommendations = events.find(e => e.type === 'recommendations') || {};
      const row = {
        started_at: new Date(start).toISOString(), completed_at: new Date().toISOString(),
        session: session.name, locale: session.locale, question: q,
        request: response.request().postDataJSON(),
        user_text: await page.locator('.he-msg--user').last().innerText(),
        answer: await page.locator('.he-msg--assistant .he-msg-content').last().innerText(),
        raw_message: events.filter(e => e.type === 'explanation_delta').map(e => e.content).join(''),
        seconds, cards: await page.locator('.he-card').count(),
        intent: complete.intent, nlu: complete.nlu, generation: complete.generation, decision: complete.decision, events,
        apps: (recommendations.apps || []).map(r => ({ name: r.app.name, native_id: r.app.app_id })),
        candidate_count: (recommendations.candidates || []).length,
      };
      out.push(row);
      fs.writeFileSync(process.argv[3] + '.json', JSON.stringify(out, null, 2));
      fs.appendFileSync(process.argv[3] + '.jsonl', JSON.stringify(row) + '\n');
      console.log(JSON.stringify({session: row.session, question: row.question, seconds, generation: row.generation?.source, decision: row.decision}));
      // Respect the default 20 chat requests/minute without relaxing the gate.
      await page.waitForTimeout(Math.max(3500 - (Date.now() - start), 450));
    }
  }
  await page.screenshot({ path: process.argv[3] + '.png', fullPage: true });
  fs.writeFileSync(process.argv[3] + '.json', JSON.stringify(out, null, 2));
  fs.writeFileSync(process.argv[3] + '.errors.json', JSON.stringify(errors, null, 2));
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
