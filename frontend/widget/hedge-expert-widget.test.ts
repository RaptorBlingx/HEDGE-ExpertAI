import { beforeEach, describe, expect, it, vi } from "vitest";

import script from "./hedge-expert-widget.js?raw";

type Widget = { sessionId: string; _restoreHistory(): Promise<void>; messagesDiv: HTMLElement };

async function restore(text: string) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ messages: [{ role: "assistant", content: text }] }),
  }));
  const WidgetClass = (window as unknown as { HedgeExpertWidget: new (config: object) => Widget }).HedgeExpertWidget;
  const widget = new WidgetClass({ apiUrl: "https://widget-test.invalid" });
  widget.sessionId = "mock";
  await widget._restoreHistory();
  return widget.messagesDiv.querySelector(".he-msg-content") as HTMLElement;
}

beforeEach(() => {
  document.body.replaceChildren();
  sessionStorage.clear();
  window.eval(script);
});

describe("untrusted assistant Markdown", () => {
  it.each([
    ["*Outer **bold** tail*", '<em>Outer <strong>bold</strong> tail</em>'],
    ["> *quote **bold***", '<div class="he-blockquote"><em>quote <strong>bold</strong></em></div>'],
    ["**Outer *italic* tail**", '<strong>Outer <em>italic</em> tail</strong>'],
    ["`first\nsecond`", '<code class="he-code-inline">first<br>second</code>'],
    ["Before `first\nsecond` after", 'Before <code class="he-code-inline">first<br>second</code> after'],
  ])("preserves baseline history rendering for %s", async (text, baselineHTML) => {
    expect((await restore(text)).innerHTML).toBe(baselineHTML);
  });

  it("keeps hostile multiline code literal", async () => {
    const content = await restore('`<img src=x onerror=attack>\n[open](javascript:attack) **literal**`');
    expect(content.querySelectorAll("code")).toHaveLength(1);
    expect(content.querySelectorAll("code br")).toHaveLength(1);
    expect(content.querySelectorAll("img,a,strong,script")).toHaveLength(0);
    expect(content.querySelector("code")?.textContent).toContain("<img src=x onerror=attack>");
  });

  it.each([
    '[open](https://example.invalid/" onpointerenter="window.audit=1)',
    '[open](https://example.invalid/" style="color:red" autofocus="true)',
    "[open](https://example.invalid/' onfocus='window.audit=1)",
    '<img src=x onerror="window.audit=1"><script>window.audit=1</script>',
    '<svg onload="window.audit=1"><a xlink:href="javascript:alert(1)">x</a></svg>',
    '[open](javascript:alert(1))', '[open](data:text/html,attack)',
    '[open](vbscript:attack)', '[open](//example.invalid/path)',
    '[open](https://user:password@example.invalid/)',
    '[open](https://example.invalid/\n onpointerenter=attack)',
    '[open](https://example.invalid/\\attack)',
    '[open](https://example.invalid/\tattack)',
    '[open](https://example.invalid/<img>)',
    '[open](java\u0000script:attack)',
  ])("does not turn %s into executable elements, attributes or unsafe links", async text => {
    const content = await restore(text);
    expect(content.querySelectorAll("a,script,img,svg,iframe,object,embed,style")).toHaveLength(0);
    for (const element of content.querySelectorAll("*")) {
      expect(element.getAttributeNames().some(name => /^on/i.test(name))).toBe(false);
    }
    expect(content.textContent).toContain(text.split("\n")[0]);
  });

  it("keeps supported formatting, code, lists, Unicode and web links", async () => {
    const content = await restore([
      "### Heading", "**Bold** and *italic*; Türkçe & <literal>", "> Quote",
      "- first", "- **second**", "1. one", "2. two",
      "`[literal](https://example.invalid/) <img>`",
      "```\n**literal** <script> [code](https://example.invalid/)\n```",
      "[**Docs**](https://example.invalid/?a=1&b=2#part) [HTTP](http://example.invalid/)",
    ].join("\n"));
    expect(content.querySelector(".he-heading")?.textContent).toBe("Heading");
    expect(content.querySelector("em")?.textContent).toBe("italic");
    expect(content.querySelector(".he-blockquote")?.textContent).toBe("Quote");
    expect(content.querySelectorAll("ul li")).toHaveLength(2);
    expect(content.querySelectorAll("ol li")).toHaveLength(2);
    expect(content.querySelector("code")?.textContent).toBe("[literal](https://example.invalid/) <img>");
    expect(content.querySelector("pre")?.textContent).toContain("**literal** <script> [code]");
    expect(content.querySelectorAll("pre a,code a,img,script")).toHaveLength(0);
    const links = content.querySelectorAll("a");
    expect(links).toHaveLength(2);
    expect(links[0].href).toBe("https://example.invalid/?a=1&b=2#part");
    expect(links[0].querySelector("strong")?.textContent).toBe("Docs");
    expect(links[1].href).toBe("http://example.invalid/");
    for (const link of links) {
      expect(link.target).toBe("_blank");
      expect(link.rel).toBe("noopener noreferrer");
    }
  });

  it("does not parse URL punctuation as formatting or decode HTML entities into markup", async () => {
    const content = await restore('[Docs](https://example.invalid/**path**?x=*value*&y=%22quote%22) [Book](https://example.invalid/O\'Reilly) &lt;img onerror=attack&gt;');
    expect(content.querySelector("a")?.href).toBe("https://example.invalid/**path**?x=*value*&y=%22quote%22");
    expect(content.querySelectorAll("strong,em,img")).toHaveLength(0);
    expect(content.querySelectorAll("a")[1].href).toBe("https://example.invalid/O'Reilly");
    expect(content.textContent).toContain("&lt;img onerror=attack&gt;");
  });
});


it("labels recommendation cards by evidence rather than a high retrieval band", () => {
  const WidgetClass = (window as unknown as { HedgeExpertWidget: new (config: object) => {
    _addAppCards(parent: HTMLElement, apps: object[], impressionId: string | null): void;
  } }).HedgeExpertWidget;
  const widget = new WidgetClass({ apiUrl: "https://widget-test.invalid" });
  const parent = document.createElement("div");
  widget._addAppCards(parent, [{ app: { id: "qa", title: "Warning App", description: "Earthquake warnings." },
    rank: 1, relevance: "high", suitability: { status: "source_supported" } }], null);
  expect(parent.querySelector(".he-card-score")?.textContent).toBe("Source evidence");
});
