// Actual loopback browser HTTP/SSE and scoped Store pipeline; no mocked routes.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

(async () => {
  const base = process.env.STORE_BROWSER_URL || "http://127.0.0.1:8096";
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({ headless: true, args: ["--disable-dev-shm-usage"] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(base);
    await page.locator(".he-input").waitFor();
    const status = await (await page.request.get(base + "/api/v2/status")).json();
    assert.equal(status.source, "authored-fixtures");
    assert.equal(status.pipeline.eligible_records, 4);
    assert.equal(status.pipeline.public_indexing, false);
    assert.equal(status.records.some(r => r.app_id === "demo-private"), false);
    assert.equal(status.pipeline.vector_points, status.embeddings === "real pinned E5" ? 4 : 0);
    const ask = async question => {
      await page.locator(".he-input").fill(question);
      const pending = page.waitForResponse(r => r.url().endsWith("/api/v2/chat/stream"));
      await page.locator(".he-send-btn").click();
      const response = await pending;
      const events = (await response.text()).split("\n").filter(l => l.startsWith("data: ")).map(l => JSON.parse(l.slice(6)));
      assert.equal(events.at(-1).type, "complete");
      await page.waitForFunction(() => !window.storeEvaluation.isStreaming);
      const result = { apps: events.find(e => e.type === "recommendations").apps,
        message: events.filter(e => e.type === "explanation_delta").map(e => e.content).join(""),
        session_id: events.at(-1).session_id };
      assert.ok(!result.message.includes("PRIVATE-DEMO-MARKER"));
      assert.ok(result.apps.every(r => r.app.store_id === "Manual-Store-Fixture" && r.app.active && r.app.visible));
      console.log(JSON.stringify({ question, ids: result.apps.map(r => r.app.app_id), message: result.message }));
      return result;
    };
    let result = await ask("Find apps for district heat measurements");
    assert.equal(result.apps[0].app.app_id, "demo-telemetry");
    assert.match(result.apps[0].app.source_evidence.readme, /only in the simulator/);
    assert.ok(result.apps[0].evidence_fields.includes("lexical"));
    if (status.embeddings === "real pinned E5") assert.ok(result.apps[0].evidence_fields.includes("dense"));
    result = await ask("Show README for Demo Telemetry Bridge");
    assert.match(result.message, /readme:/);
    assert.match(result.message, /production compatibility has not been validated/);
    const card = page.locator(".he-card").first();
    await page.locator(".he-side-close").focus();
    await page.keyboard.press("Tab");
    assert.equal(await card.locator("summary").evaluate(el => document.activeElement === el), true);
    await card.locator("summary").press("Enter");
    assert.match(await card.innerText(), /connectorVersion/);
    assert.match(await card.innerText(), /Heat network diagnostics/);
    assert.equal(await card.locator("script, img, a").count(), 0);
    assert.equal(await page.evaluate(() => window.unsafeSource), undefined);
    assert.equal((await card.innerText()).includes("excluded-demo-secret"), false);
    if (process.env.STORE_BROWSER_SCREENSHOT) await page.screenshot({ path: process.env.STORE_BROWSER_SCREENSHOT });
    const normal = await (await page.request.post(base + "/api/v2/chat", { data: {
      message: "Show README for Demo Telemetry Bridge", session_id: result.session_id,
    } })).json();
    assert.equal(normal.message, result.message);
    assert.deepEqual(normal.apps, result.apps);
    for (const [prompt, expected] of [
      ["Show connector fields for it", /connectorVersion: "1.2"/],
      ["Show embedded metadata for it", /dataspaceAppDescription.properties.featureList/],
      ["Show billing fields for it", /Currency, billing period, taxes and licence terms are unspecified/],
      ["Show versions for it", /no current or latest version is inferred/],
      ["Show README for Demo Sparse Catalogue", /evidence is missing/],
      ["Show embedded metadata for Demo Sparse Catalogue", /evidence is malformed/],
      ["Show README for Demo Long Documentation", /evidence is too_large/],
    ]) {
      result = await ask(prompt);
      assert.match(result.message, expected);
      assert.equal(result.apps.length, 1);
    }
    result = await ask("Does it support MQTT?");
    assert.equal(result.apps.length, 0);
    assert.match(result.message, /cannot confirm/);
    result = await ask("Show README for Demo Unpublished App");
    assert.equal(result.apps.length, 0);
    result = await ask("Show price for Demo Telemetry Bridge and confirm it is free");
    assert.equal(result.apps.length, 0);
    result = await ask("Find apps for vocabulary review");
    assert.equal(result.apps[0].app.app_id, "demo-vocabulary");
    result = await ask("Show me all available applications");
    assert.equal(result.apps.length, 4);
    assert.match(result.message, /Listing order is not a relevance ranking/);
    result = await ask("Compare the first two apps");
    assert.equal(result.apps.length, 2);
    const scenario = async action => {
      const pending = page.waitForResponse(r => r.url().endsWith("/evaluation/scenario/" + action));
      await page.getByRole("button", { name: action[0].toUpperCase() + action.slice(1) + " demo App", exact: true }).click();
      const response = await pending;
      assert.equal(response.status(), 200);
      const receipt = await response.json();
      console.log(JSON.stringify({ publisher_change: receipt }));
      return receipt;
    };
    const update = await scenario("update");
    assert.equal(update.ingestion.updated, 1);
    result = await ask("Show README for Demo Telemetry Bridge");
    assert.match(result.message, /Updated authored fixture/);
    assert.match(result.message, /production compatibility has not been validated/);
    assert.equal(result.apps[0].app.app_id, "demo-telemetry");
    const withdrawal = await scenario("withdraw");
    assert.ok(withdrawal.revision > update.revision);
    assert.equal(withdrawal.pipeline.eligible_records, 3);
    assert.equal(withdrawal.pipeline.vector_points, status.embeddings === "real pinned E5" ? 3 : 0);
    result = await ask("Show README for it");
    assert.equal(result.apps.length, 0);
    result = await ask("Find apps for district heat measurements");
    assert.ok(result.apps.every(r => r.app.app_id !== "demo-telemetry"));
    const restore = await scenario("restore");
    assert.ok(restore.revision > withdrawal.revision);
    assert.equal(restore.pipeline.eligible_records, 4);
    result = await ask("Show README for Demo Telemetry Bridge");
    assert.match(result.message, /only in the simulator/);
    assert.ok(!result.message.includes("Updated authored fixture"));
    await page.reload();
    await page.locator(".he-input").waitFor();
    await page.waitForFunction(() => !window.storeEvaluation.isStreaming);
    assert.ok(await page.locator(".he-msg--user").count() > 0);
    await page.setViewportSize({ width: 390, height: 844 });
    // The existing mobile results pane is an overlay; return to Chat first.
    await page.locator(".he-side-close").click();
    await ask("Show billing fields for Demo Telemetry Bridge");
    await page.waitForFunction(() => {
      const side = document.querySelector(".he-panel-side");
      return side.getBoundingClientRect().x >= -1 && side.getBoundingClientRect().x <= 1 &&
        getComputedStyle(side).opacity >= 0.99;
    });
    const bounds = await page.locator(".he-panel").boundingBox();
    assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= 391);
    assert.ok(bounds.y <= 1 && bounds.height >= 843);
    if (process.env.STORE_BROWSER_MOBILE_SCREENSHOT) await page.screenshot({ path: process.env.STORE_BROWSER_MOBILE_SCREENSHOT });
    assert.deepEqual(errors, []);
    console.log("PASS: real metadata ingestion/retrieval, source reads, HTTP/SSE parity, safe cards, context, desktop/mobile");
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
