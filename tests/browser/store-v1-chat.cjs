// Run against the disposable runner only. No routes or model results are mocked.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

(async () => {
  const base = process.env.STORE_BROWSER_URL || "http://127.0.0.1:8091";
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({ headless: true, args: ["--disable-dev-shm-usage"] });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    await page.goto(base);
    await page.locator(".he-input").waitFor();
    assert.match(await page.locator("#components").innerText(), /source quotations/);
    if (process.env.STORE_BROWSER_EXPECT_FAILURE === "1") {
      await page.locator(".he-input").fill("EdgeConnect");
      await page.locator(".he-send-btn").click();
      await page.waitForFunction(() => !window.storeEvaluation.isStreaming);
      assert.equal(await page.locator(".he-stage").last().innerText(), "Request failed");
      assert.equal(await page.locator(".he-card").count(), 0);
      assert.match(await page.locator(".he-msg--assistant").last().innerText(), /Offline retrieval unavailable/);
      console.log("Actual database-failure browser check passed: terminal problem, no success/cards");
      return;
    }
    const ask = async (question) => {
      await page.locator(".he-input").fill(question);
      const response = page.waitForResponse(r => r.url().endsWith("/api/v2/chat/stream"));
      await page.locator(".he-send-btn").click();
      const http = await response;
      assert.equal(http.status(), 200);
      const text = await http.text();
      const events = text.split("\n").filter(l => l.startsWith("data: ")).map(l => JSON.parse(l.slice(6)));
      assert.equal(events.at(-1).type, "complete");
      await page.waitForFunction(() => !window.storeEvaluation.isStreaming);
      const apps = events.find(e => e.type === "recommendations").apps;
      if (apps.length) await page.waitForFunction(() => {
        const panel = document.querySelector(".he-panel");
        const main = document.querySelector(".he-panel-main");
        const side = document.querySelector(".he-panel-side");
        return getComputedStyle(side).opacity >= 0.99 && panel.getBoundingClientRect().width >= main.getBoundingClientRect().width + side.getBoundingClientRect().width - 1;
      });
      const narrative = events.filter(e => e.type === "explanation_delta").map(e => e.content).join("");
      console.log(JSON.stringify({ question, nlu: events.at(-1).nlu, apps: apps.map(r => ({ name: r.app.name, rank: r.rank, channels: r.evidence_fields })), narrative }));
      return { apps, narrative };
    };
    let result = await ask("Show me EdgeConnect and Semantic Treehouse");
    assert.equal(result.apps.length, 2);
    await page.locator(".he-card").first().waitFor({ state: "visible" });
    const bounds = await page.locator(".he-card").first().boundingBox();
    assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= 1280);
    const names = result.apps.map(r => r.app.name);
    assert.deepEqual(await page.locator(".he-card-title").allTextContents(), names);
    assert.match(await page.locator(".he-card-score").first().innerText(), /Rank 1/);
    assert.equal(await page.locator("a.he-card").count(), 0);
    assert.match(result.narrative, /description:/);
    result = await ask("Tell me more about the second app");
    assert.equal(result.apps[0].app.name, names[1]);
    await ask("hello");
    result = await ask("Compare the first two apps");
    assert.deepEqual(result.apps.map(r => r.app.name), names);
    assert.match(result.narrative, /Source-field comparison only/);
    if (process.env.STORE_BROWSER_SCREENSHOT) await page.screenshot({ path: process.env.STORE_BROWSER_SCREENSHOT });
    result = await ask("What does it cost?");
    assert.equal(result.apps.length, 0);
    assert.match(result.narrative, /cannot confirm/);
    assert.equal(await page.locator(".he-card").count(), 0);
    await page.reload();
    await page.locator(".he-input").waitFor();
    await page.waitForFunction(() => !window.storeEvaluation.isStreaming);
    assert.ok(await page.locator(".he-msg--user").count() >= 5);
    result = await ask("Tell me more about the first app");
    assert.equal(result.apps[0].app.name, names[0]);
    result = await ask("Does it support MQTT?");
    assert.equal(result.apps.length, 0);
    assert.match(result.narrative, /cannot confirm/);
    result = await ask("Find apps for sensor readings");
    assert.ok(result.apps.some(r => r.app.name === "EdgeConnect"));
    result = await ask("Find apps for semantic data models");
    assert.ok(result.apps.some(r => r.app.name === "Semantic Treehouse"));
    // User text is escaped; no markup is executed in chat.
    await ask('<img src=x onerror="window.unsafeSource=true">');
    assert.equal(await page.evaluate(() => window.unsafeSource), undefined);
    await ask("reset");
    result = await ask("Tell me more about the second app");
    assert.equal(result.apps.length, 0);
    await ask("Show me EdgeConnect and Semantic Treehouse");
    await page.locator(".he-clear-btn").click();
    await page.waitForFunction(() => window.storeEvaluation.sessionId === null);
    result = await ask("Compare first and second");
    assert.equal(result.apps.length, 0);
    // Renderer-only security/compatibility checks; these injected DOM records
    // are not pipeline results or simulated model behavior.
    await page.evaluate(() => window.storeEvaluation._addAppCards(window.storeEvaluation.sideContent, [
      { app: { id: "synthetic-test", title: { en: "Synthetic test" }, description: "Existing v2", publisher: { name: "Fixture" } }, rank: 1, relevance: "medium" }
    ], null));
    assert.equal(await page.locator(".he-card-title").textContent(), "Synthetic test");
    assert.equal(await page.locator(".he-card-score").textContent(), "medium");
    await page.evaluate(() => window.storeEvaluation._addAppCards(window.storeEvaluation.sideContent, [
      { app: { source_profile: "hedge-store-v1", id: "renderer-only", store_id: "fixture", app_id: "adversarial", name: '<img src=x onerror="window.unsafeSource=true">', description: '<script>window.unsafeSource=true</script>', provider: '<img src=x>', app_url: "javascript:alert(1)" }, rank: 1, evidence_fields: ["reference"] }
    ], null));
    assert.equal(await page.locator(".he-cards img, .he-cards script, a.he-card").count(), 0);
    assert.equal(await page.evaluate(() => window.unsafeSource), undefined);
    assert.deepEqual(errors, []);
    console.log("Browser checks passed: actual SSE, cards, grounding, context/reload, unsupported, reset/clear, escaping");
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
