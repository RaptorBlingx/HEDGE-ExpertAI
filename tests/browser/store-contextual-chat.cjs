// Real private catalogue stays in browser memory; retain only aggregate evidence.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
let checkpoint = "startup";
(async () => {
  const base = process.env.STORE_BROWSER_URL || "http://127.0.0.1:8098";
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({ headless: true, ...(process.env.STORE_BROWSER_EXECUTABLE ? { executablePath: process.env.STORE_BROWSER_EXECUTABLE } : {}), args: ["--disable-dev-shm-usage"] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    page.setDefaultTimeout(90000);
    const errors = [];
    page.on("pageerror", () => errors.push("browser_error"));
    await page.goto(base);
    await page.locator(".he-input").waitFor();
    const catalogue = await (await page.request.get(base + "/api/v2/catalogue")).json();
    assert.ok(catalogue.apps.length >= 2);
    let modelTurns = 0;
    const ask = async (message, trigger) => {
      const pending = page.waitForResponse(r => r.url().endsWith("/api/v2/chat/stream"));
      if (trigger) await trigger();
      else {
        await page.locator(".he-input").fill(message);
        await page.locator(".he-send-btn").click();
      }
      const events = (await (await pending).text()).split("\n").filter(l => l.startsWith("data: ")).map(l => JSON.parse(l.slice(6)));
      await page.waitForFunction(() => !window.storeEvaluation.isStreaming);
      const complete = events.at(-1);
      assert.equal(complete.type, "complete");
      const apps = events.find(e => e.type === "recommendations").apps;
      const text = events.filter(e => e.type === "explanation_delta").map(e => e.content).join("");
      assert.ok(apps.every(r => catalogue.apps.some(a => a.id === r.app.id && a.app_id === r.app.app_id && a.store_id === r.app.store_id)));
      assert.ok(!text.includes("billable:") && !text.includes("price:"));
      if (complete.generation?.source === "ollama") modelTurns++;
      console.log(JSON.stringify({ apps: apps.length, intent: complete.intent, generation: complete.generation?.source, reason: complete.generation?.reason, seconds: complete.generation?.seconds, chars: text.length, nlu: complete.nlu?.source }));
      return { apps, text, complete };
    };
    let r = await ask("Tell me about the first app");
    assert.equal(r.apps.length, 1);
    assert.equal(r.apps[0].app.id, catalogue.apps[0].id);
    assert.ok(r.text.includes("[description]"));
    const normal = await (await page.request.post(base + "/api/v2/chat", { data: {message: "Tell me about the first app"} })).json();
    assert.deepEqual(normal.apps, r.apps);
    assert.ok(normal.message.includes("[description]"));
    r = await ask("Compare the first two apps");
    assert.equal(r.apps.length, 2);
    assert.ok(r.text.includes("no superiority or suitability"));
    const selected = r.apps[1].app;
    r = await ask("What does " + selected.name + " do?");
    assert.equal(r.apps.length, 1);
    assert.equal(r.apps[0].app.id, selected.id);
    r = await ask("Tell me more about it");
    assert.equal(r.apps[0].app.id, selected.id);
    r = await ask(null, () => page.locator(".he-card-explain").first().click());
    assert.equal(r.apps[0].app.id, selected.id);
    // Explicit reads retain exact values and billing caveats, separate from prose.
    checkpoint = "billing fields";
    const fields = await (await page.request.post(base + "/api/v2/chat", { data: {message: "Show billing fields for " + selected.app_id} })).json();
    assert.ok(fields.message.includes("Currency, billing period"));
    assert.ok(fields.message.includes("billable:") && fields.message.includes("price:"));
    checkpoint = "complete README inspection";
    // Long README remains completely inspectable in escaped source cards.
    const long = catalogue.apps[0];
    r = await ask("Describe " + long.app_id);
    const readme = r.apps[0].app.source_evidence.readme;
    await page.locator(".he-card-evidence summary").first().click();
    const evidence = await page.locator(".he-card-evidence").first().textContent();
    assert.ok(evidence.includes(readme));
    assert.equal(await page.locator(".he-card script, .he-card img").count(), 0);
    checkpoint = "history restoration";
    await page.reload();
    await page.locator(".he-input").waitFor();
    await page.waitForFunction(() => !window.storeEvaluation.isStreaming &&
      document.querySelectorAll(".he-msg--user").length > 0);
    assert.equal(errors.length, 0);
    assert.ok(modelTurns > 0, "At least one actual Ollama selection must pass grounding");
    console.log(JSON.stringify({ result: "PASS", catalogue_count: catalogue.total, model_turns: modelTurns,
      checks: "fresh ordinal HTTP/SSE, comparison, named questions, focus, card action, complete escaped sources, billing caveats, restored history" }));
  } finally { await browser.close(); }
})().catch(() => { console.error("Contextual Chat verification failed at " + checkpoint + "; private contents suppressed"); process.exitCode = 1; });
