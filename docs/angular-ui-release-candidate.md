# Angular frontend release candidate — 2026-10-20

Final UI polish based on `e401203` on `feat/t2-angular-ui`. This is the candidate
for personal visual acceptance before publishing a frontend checkpoint. It does
not change backend code, inference settings, API contracts, Store data or policy.
The shared standalone Angular assistant, typed adapter and illustrative demo shell
retain their existing boundaries. No dependency or lockfile changed.

## What changed

- Welcome copy now describes discovery, capabilities and comparison. Each starting
  action explains what it does; the existing navy/teal identity is retained.
- A documented recommendation has a distinct card treatment and heading. Ordinary
  catalogue/comparison entries have no recommendation badge. The badge still
  requires a positive backend decision and `source_supported` suitability.
- Each newly completed answer retains its own App references. Source buttons open
  the received Store metadata directly, without another request or model call.
  Other catalogue entries are visually separated from the current answer.
- Message typography, paragraph spacing, touch controls and dark scrollbars are
  refined. A latest-response shortcut helps with long conversations; resizing the
  pane follows the latest answer only while the reader is already following it.
- Waiting shows actual elapsed time and plain guidance after 10/30 seconds. No
  simulated reasoning stages, loading percentages or inference-cancellation claims
  are displayed. Reading earlier answers and source evidence, drafting, Stop and
  retry remain available. A late answer does not force focus or reopen a keyboard.
- Short mobile viewports retain the composer. Source/clear dialogs retain focus
  containment and restoration. Waiting announcements sit outside the busy log so
  assistive technology can receive them without reading every timer tick.

## Verification

Actual production-build browser conversations use the unchanged `f7ffc16` gateway,
Rasa, E5, Qwen3 4B and authorized Store services. The live catalogue contains
EdgeConnect and Semantic Treehouse; no authored catalogue or fabricated answer is
used. The ten-turn replay covers browsing, native inspection, provider context,
simplification, original evidence, comparison, history restoration, unconfirmed
free-pricing recovery, an assisted recommendation and mobile inspection. All ten
turns completed with no browser errors. Complete unedited SSE answers are retained
privately, outside Git.

Focused real-service browser checks cover direct source inspection without chat,
recommendation/catalogue distinction, long-history navigation and focus, resize
following, dialog keyboard behavior, reduced motion, cross-origin rejection and
touch/short-viewport layouts. A real response is deliberately held in browser
transport for 38 seconds to inspect the 10/30-second waiting states and confirm
that draft, focus and history remain usable. **That delay is not inference latency.**
Separate historical fault/rendering checks remain explicitly labelled simulations;
they are not recommendation-quality evidence.

Desktop 1440 px, tablet 768 px and touch mobile 390 px are visually inspected in
light/dark and workspace/pane presentations. Overflow and composer visibility are
also checked at 320 px, 1280 px and a short 390 × 520 viewport. Touch screenshots
capture the visible viewport to retain Chromium's touch emulation.

Production AOT build and the three existing SSE/identity unit checks pass. Full and
production-only npm audits report zero findings; all 232 dependency licences pass
the unchanged checker. Existing build budgets and security protections remain.
No backend suite or remote UI CI run is claimed for this UI-only local change.

## Size and timing compared with e401203

| Observation | Previous UI | Release candidate |
| --- | ---: | ---: |
| JavaScript, raw | 347,329 B | 355,097 B |
| JavaScript, gzip | 89,559 B | 91,152 B |
| Global CSS, raw / gzip | 432 / 244 B | 432 / 244 B |
| Self-hosted font files | 73,092 B | 73,092 B |
| Prepared real responses | about 0.2–0.4 s | about 0.2–0.4 s |
| Observed warm assisted turn | 7.7 s | 7.5–8.0 s |
| Observed cold assisted turn | 52.1 s | 50.5 s |
| FCP, median of three alternating fresh contexts | 436 ms | 348 ms |

JavaScript grows by **1,593 B gzip (1.8%)**. Component CSS is included in those JS
bytes. No new runtime requests, libraries, fonts or model processes are introduced.
The startup comparison used the same browser/VM, fresh contexts and alternating
versions. FCP ranged from 336–632 ms before and 304–480 ms after. This small sample
does not establish a speed improvement or WAN performance.
Cold inference remains a backend/infrastructure constraint.

## Preview, freeze and remaining boundaries

The release candidate is private at `http://127.0.0.1:8136/`, using the unchanged
backend services behind gateway 8127 and separate origin-specific
test sessions. Only its static server/systemd unit and copied UI assets are new.
No existing preview is restarted or reconfigured; 8096/8106/8116/8126 remain intact.
Frozen source/asset hashes and recovery instructions live with the private runtime.

```bash
ssh -N -L 8136:127.0.0.1:8136 ubuntu@10.33.10.130
```

Open local `http://127.0.0.1:8136/`; `?view=pane` opens the embedded presentation.
Use a different local port, such as `-L 18136:127.0.0.1:8136`, if necessary.

- History restores text and current App context. Per-turn evidence badges and
  timings are available for turns completed in the current page; the existing
  history API does not retain their decision metadata. No badges are reconstructed
  from prose on reload.
- Store descriptions may be sparse or placeholder-like; the UI displays the source
  instead of rewriting it. Only two real Apps were available for this evaluation.
- Touch Chromium and keyboard checks do not replace physical-device keyboard,
  screen-reader or full WCAG auditing. Host Angular compatibility, authentication,
  navigation and public API coordination remain as described in the existing
  [integration contract](angular-ui-integration.md).
- Stop ends browser waiting; an already-running server/model operation may finish.
  The frontend does not change existing answer quality, inference cost or retries.

The candidate is committed locally, not pushed, merged, tagged or deployed into
an existing environment. After personal visual acceptance, freeze UI scope and
return to T2 backend work.
