// Offline widget check: isolated host with no CSP, mocked fetch, no live services.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.WIDGET_BROWSER_EXECUTABLE ? { executablePath: process.env.WIDGET_BROWSER_EXECUTABLE } : {}),
    args: ["--disable-dev-shm-usage"],
  });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.route("**/*", route => route.fulfill({
      status: 200, contentType: "text/html", body: "<!doctype html><html><head></head><body></body></html>",
    }));
    await page.goto("https://widget-test.invalid");
    await page.addScriptTag({ content: fs.readFileSync(path.resolve(__dirname, "../../frontend/widget/hedge-expert-widget.js"), "utf8") });
    const result = await page.evaluate(async () => {
      const attack = '[open](https://example.invalid/" onpointerenter="window.audit=1)';
      const payloads = [
        attack, '[open](https://example.invalid/" style="color:red" autofocus="true)',
        '<img src=x onerror="window.audit=1"><script>window.audit=1</script>',
        '<svg onload="window.audit=1"></svg>', '[open](javascript:window.audit=1)',
        '[open](data:text/html,attack)', '[open](//example.invalid/)',
        '[open](https://user:password@example.invalid/)',
        '[open](https://example.invalid/\t onfocus=attack)',
        '[open](https://example.invalid/\\attack)',
        '[open](https://example.invalid/<img>)',
      ];
      const widget = new window.HedgeExpertWidget({ apiUrl: "https://widget-test.invalid" });
      widget.sessionId = "mock";
      const violations = [];
      function check(content) {
        for (const element of content.querySelectorAll("*")) {
          if (!/^(A|STRONG|EM|BR|UL|OL|LI|CODE|PRE|DIV)$/.test(element.tagName)) violations.push(element.outerHTML);
          if (element.getAttributeNames().some(name => /^on/i.test(name))) violations.push(element.outerHTML);
          const allowedAttributes = element.tagName === "A" ? ["href", "target", "rel", "class"] : ["class"];
          if (element.getAttributeNames().some(name => !allowedAttributes.includes(name))) violations.push(element.outerHTML);
          if (element.tagName === "A" && (!/^https?:$/.test(new URL(element.href).protocol) || element.rel !== "noopener noreferrer" || element.target !== "_blank")) violations.push(element.outerHTML);
          element.dispatchEvent(new PointerEvent("pointerenter"));
          element.dispatchEvent(new Event("focus"));
          element.dispatchEvent(new Event("error"));
        }
      }
      async function restore(text) {
        window.fetch = async () => ({ ok: true, status: 200, json: async () => ({ messages: [{ role: "assistant", content: text }] }) });
        await widget._restoreHistory();
        check(widget.messagesDiv.querySelector(".he-msg-content"));
      }
      for (const text of payloads) await restore(text);
      // Every prefix also exercises incomplete Markdown without HTML parsing.
      for (let i = 0; i <= attack.length; i++) await restore(attack.slice(0, i));
      const legitimate = "### Heading\n**Bold** and *italic*\n> Quote\n- one\n- two\n1. first\n2. second\n`<img> [code](https://example.invalid/)`\n```\n<script>literal</script>\n```\n[**Docs**](https://example.invalid/?a=1&b=2)";
      await restore(legitimate);
      const content = widget.messagesDiv.querySelector(".he-msg-content");
      const legitimateResult = {
        links: content.querySelectorAll("a").length,
        href: content.querySelector("a").href,
        label: content.querySelector("a strong").textContent,
        unorderedItems: content.querySelectorAll("ul li").length,
        orderedItems: content.querySelectorAll("ol li").length,
        inlineCode: content.querySelector("code").textContent,
        blockCode: content.querySelector("pre").textContent,
      };
      // Exercise the real stream-update and final-render paths, with split deltas.
      const observer = new MutationObserver(() => {
        for (const body of widget.messagesDiv.querySelectorAll(".he-msg-content")) check(body);
      });
      observer.observe(widget.messagesDiv, { childList: true, subtree: true });
      window.fetch = async () => {
        const events = [...(attack + "\n[Docs](https://example.invalid/)")].map(content => ({ type: "explanation_delta", content }));
        events.push({ type: "complete" });
        let index = 0;
        return new Response(new ReadableStream({
          pull(controller) {
            if (index === events.length) return controller.close();
            controller.enqueue(new TextEncoder().encode("data: " + JSON.stringify(events[index++]) + "\n\n"));
          },
        }), { status: 200 });
      };
      window.widget = widget;
      widget.textarea.value = "Test safe rendering";
      widget._send();
      window.markdownReview = { violations, legitimateResult, payloads: payloads.length, prefixes: attack.length + 1, observer };
      return { legitimateResult, payloads: payloads.length, prefixes: attack.length + 1 };
    });
    await page.waitForFunction(() => !window.widget.isStreaming);
    const state = await page.evaluate(() => {
      window.markdownReview.observer.disconnect();
      return { violations: window.markdownReview.violations, executed: window.audit, stage: window.widget.messagesDiv.querySelector(".he-stage").textContent };
    });
    assert.deepEqual(state.violations, []);
    assert.equal(state.executed, undefined);
    assert.equal(state.stage, "Complete");
    assert.equal(result.legitimateResult.links, 1);
    assert.equal(result.legitimateResult.href, "https://example.invalid/?a=1&b=2");
    assert.equal(result.legitimateResult.label, "Docs");
    assert.equal(result.legitimateResult.unorderedItems, 2);
    assert.equal(result.legitimateResult.orderedItems, 2);
    assert.match(result.legitimateResult.inlineCode, /^<img> \[code\]/);
    assert.match(result.legitimateResult.blockCode, /<script>literal<\/script>/);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ ...result, stream: "complete", executableContent: false, csp: "absent" }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
