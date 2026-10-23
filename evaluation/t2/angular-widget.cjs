// Capture complete real Angular conversations; grading is a separate human review.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  process.umask(0o077);
  if (!process.argv[2] || !process.argv[3] || path.resolve(process.argv[2]) === path.resolve(process.argv[3] + '.json')) {
    throw new Error('Use distinct question-input and result-output paths.');
  }
  let browser;
  const rows = [], errors = [];
  try {
    for (const session of JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))) {
      // Bound browser memory between independent conversations; retain every turn
      // inside each conversation on the same page and server-side session.
      browser = await chromium.launch({headless: true, ...(process.env.BROWSER_EXECUTABLE ? {executablePath: process.env.BROWSER_EXECUTABLE} : {})});
      const page = await browser.newPage({viewport: {width: 1440, height: 1050}});
      page.on('pageerror', e => errors.push(e.message));
      page.on('response', r => {if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`);});
      await page.addInitScript(() => {
        window.__widgetRecords = [];
        const original = window.fetch;
        window.fetch = async (...args) => {
          const response = await original(...args);
          if (String(args[0]).endsWith('/api/v2/chat/stream')) {
            response.clone().text().then(body => window.__widgetRecords.push({request: JSON.parse(args[1].body), body}));
          }
          return response;
        };
      });
      await page.goto(process.env.WIDGET_BASE_URL);
      await page.evaluate(() => {sessionStorage.clear(); localStorage.clear();});
      await page.reload();
      const input = page.getByLabel('Ask ExpertAI about Store applications', {exact: true});
      await input.waitFor();
      for (const question of session.questions) {
        const start = Date.now();
        await Promise.all([
          page.waitForResponse(r => r.url().endsWith('/api/v2/chat/stream'), {timeout: 180000}),
          (async () => {
            if (typeof question === 'object') {
              await page.getByRole('button', {name: question.click, exact: true}).click();
            } else {
              await input.fill(question);
              await page.getByRole('button', {name: 'Send message', exact: true}).click();
            }
          })(),
        ]);
        await page.waitForFunction(() => window.__widgetRecords.length > 0, null, {timeout: 180000});
        const {body, request} = await page.evaluate(() => window.__widgetRecords.shift());
        const events = body.split(/\r?\n/).filter(l => l.startsWith('data:')).map(l => JSON.parse(l.slice(5)));
        const complete = events.find(e => e.type === 'complete');
        if (!complete) throw new Error(`Incomplete stream: ${session.name}: ${JSON.stringify(question)}`);
        await page.getByRole('button', {name: 'Stop response', exact: true}).waitFor({state: 'hidden', timeout: 180000});
        const row = {session: session.name, question, request,
          answer: await page.locator('.assistant-message .answer-text').last().innerText(),
          seconds: (Date.now() - start) / 1000, events, ...complete};
        rows.push(row);
        fs.writeFileSync(process.argv[3] + '.json', JSON.stringify(rows, null, 2));
        console.log(JSON.stringify({session: row.session, question, seconds: row.seconds, intent: row.intent, nlu: row.nlu, decision: row.decision, generation: row.generation}));
        const close = page.getByRole('button', {name: 'Close App details', exact: true});
        if (await close.isVisible()) await close.click();
        await page.waitForTimeout(Math.max(3500 - (Date.now() - start), 450));
      }
      await page.screenshot({path: process.argv[3] + '.png', fullPage: true});
      await browser.close();
      browser = undefined;
    }
  } finally {
    fs.writeFileSync(process.argv[3] + '.errors.json', JSON.stringify(errors, null, 2));
    if (browser) await browser.close();
  }
})().catch(e => {console.error(e); process.exitCode = 1;});
