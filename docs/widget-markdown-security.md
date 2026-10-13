# SCRUM-27: Chat widget Markdown rendering

## Reproduced boundary

Against integration commit `a8cab8f`, Astra finding 9 reproduced in an isolated
Chromium page without CSP. Restoring this assistant message created an actual
`onpointerenter` attribute; dispatching the event executed `window.audit=1`:

```text
[open](https://example.invalid/" onpointerenter="window.audit=1)
```

The previous renderer escaped text-node HTML, then interpolated Markdown URLs
into quoted attributes in generated HTML. Text escaping did not escape quotes
for that attribute context. Both history restoration and streamed/final messages
used the resulting HTML through `innerHTML`.

## Rendering contract

The renderer now builds a DocumentFragment from explicit DOM elements and text
nodes. No assistant text is parsed as HTML. Links use a parsed, absolute HTTP(S)
URL assigned through the anchor's DOM property, with `target="_blank"` and
`rel="noopener noreferrer"`. Other protocols, relative destinations, credentials,
controls/whitespace, backslashes, raw double quotes and angle brackets remain
literal Markdown text. This does not restrict normal percent-encoded URL data.

The existing small Markdown subset remains: headings starting with three or more
hashes, bold, italic, blockquotes, ordered/unordered lists, inline code, fenced
code, line breaks, and web links with inline-formatted labels. Code content stays
literal, and URL punctuation is not interpreted as emphasis. Nesting is bounded;
unrecognized syntax stays text. This is not a full CommonMark parser.

The review corrections preserve the `a8cab8f` DOM shapes for bold nested inside
italic (including blockquotes), italic inside bold, and inline-code spans across
newlines. Bold delimiters are consumed as a complete span inside italic. Complete
code spans are retained before line-based parsing; their newlines become explicit
DOM `br` elements inside `code`, matching the baseline's visible line breaks.

History restoration, incremental streaming and final rendering all consume the
same DOM renderer. Gateway CSP remains an additional host protection, rather
than the basis for this renderer's safety. HTTP(S) links can still lead to
arbitrary external sites; their content or reputation is not assessed here.

## Verification

The default frontend test command includes
`frontend/widget/hedge-expert-widget.test.ts`. Adversarial tests cover attribute
breakout, raw HTML/SVG, unsafe schemes, malformed destinations and controls;
legitimate cases cover the supported Markdown, code, query strings, Unicode,
formatting in labels and literal URL punctuation.
Exact baseline compatibility fixtures cover both review findings in history.

The standalone browser check uses an isolated synthetic host, mocked fetch and
no CSP. It checks malicious messages, every prefix of the reported attack,
real history restoration, incremental stream updates and final rendering, while
dispatching events to detect execution. The browser assertions also check those
fixtures during incremental streaming and after final rendering, including
hostile text inside multiline code. It starts no server or application stack:

```bash
node tests/browser/widget-markdown.cjs
```

As with the existing browser checks, Playwright and its browser must be available
in the test environment. `NODE_PATH` can point to an external test-tool directory;
`WIDGET_BROWSER_EXECUTABLE` optionally selects an existing Chromium binary.
Run `npm ci`, `npm test` and `npm run build` in an isolated frontend copy using
the repository's pinned Node version. Do not use the preserved demo as a test host.
