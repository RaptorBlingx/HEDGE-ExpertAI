const assert = require("node:assert/strict");
const { chromium } = require("playwright");
(async () => {
  const base = process.env.STORE_BROWSER_URL || "http://127.0.0.1:8098";
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const browser = await chromium.launch({ headless: true, args: ["--disable-dev-shm-usage"] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(base);
    await page.locator(".he-input").waitFor();
    const status = await (await page.request.get(base + "/api/v2/status")).json();
    assert.equal(status.managed_workspace, true);
    assert.equal(status.simulation_controls, false);
    assert.equal(status.synchronization.snapshot_complete, false);
    assert.ok(status.synchronization.snapshot_at);
    let all = [], offset = 0;
    do {
      const data = await (await page.request.get(base + "/api/v2/catalogue?offset=" + offset)).json();
      all.push(...data.apps); offset = data.next_offset;
    } while (offset !== null);
    assert.equal(all.length, status.synchronization.available);
    assert.ok(all.length > 0);
    const ask = async message => {
      await page.locator(".he-input").fill(message);
      const pending = page.waitForResponse(r => r.url().endsWith("/api/v2/chat/stream"));
      await page.locator(".he-send-btn").click();
      const events = (await (await pending).text()).split("\n").filter(l => l.startsWith("data: ")).map(l => JSON.parse(l.slice(6)));
      assert.equal(events.at(-1).type, "complete");
      await page.waitForFunction(() => !window.storeEvaluation.isStreaming);
      const apps = events.find(e => e.type === "recommendations").apps;
      const text = events.filter(e => e.type === "explanation_delta").map(e => e.content).join("");
      assert.match(text, /Local Store snapshot observed at/);
      assert.match(text, /complete catalogue coverage/);
      assert.ok(apps.every(r => all.some(a => a.id === r.app.id && a.app_id === r.app.app_id && a.store_id === r.app.store_id)));
      return { apps, text, session_id: events.at(-1).session_id };
    };
    let result = await ask("Show me all available applications");
    assert.equal(result.apps.length, Math.min(5, all.length));
    result = await ask("Show README for " + all[0].app_id);
    assert.equal(result.apps[0].app.id, all[0].id);
    const normal = await (await page.request.post(base + "/api/v2/chat", { data: {
      session_id: result.session_id, message: "Show README for " + all[0].app_id,
    } })).json();
    assert.equal(normal.message, result.text);
    assert.deepEqual(normal.apps, result.apps);
    assert.equal(await page.locator(".he-card script, .he-card img").count(), 0);
    result = await ask("Show me " + all[0].name);
    const found = result.apps.find(r => r.app.id === all[0].id);
    assert.ok(found);
    assert.ok(found.evidence_fields.includes("dense") && found.evidence_fields.includes("lexical"));
    if (all.length >= 2) {
      await ask("Show me all available applications");
      result = await ask("Compare the first two apps");
      assert.equal(result.apps.length, 2);
      assert.match(result.text, /no superiority or suitability/);
    }
    await page.locator("#refresh-store").click();
    await page.waitForFunction(() => !document.getElementById("refresh-store").disabled);
    const after = await (await page.request.get(base + "/api/v2/status")).json();
    if (after.synchronization.state === "authorization_required") assert.equal(after.synchronization.available, all.length);
    assert.ok(["authorization_required", "observed_api"].includes(after.synchronization.state));
    await page.reload(); await page.locator(".he-input").waitFor();
    await page.waitForFunction(() => !window.storeEvaluation.isStreaming);
    assert.ok(await page.locator(".he-msg--user").count() > 0);
    assert.deepEqual(errors, []);
    // Counts/status only: do not persist names, queries, bodies, tokens or screenshots.
    console.log(JSON.stringify({ result: "PASS", actual_observed_apps: all.length,
      source_kind: after.synchronization.source_kind, refresh_state: after.synchronization.state,
      index_pending: after.synchronization.index_pending,
      checks: "whole observed catalogue, HTTP/SSE parity, real dense+lexical retrieval, source reads, comparison, refresh, history" }));
  } finally { await browser.close(); }
})().catch(() => { console.error("Managed Store browser verification failed; private record contents suppressed"); process.exitCode = 1; });
