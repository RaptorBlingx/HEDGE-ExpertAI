# Contextual Chat over authorized Store observations

This review branch starts at `3ee84f4` (`feat/store-live-integration`). No new Jira
issue number was assigned. It leaves SCRUM-39 and the integration branch separate.
The private preview is [127.0.0.1:8098](http://127.0.0.1:8098).

The [proposal](proposals/HEDGE-IoT-OC1-Proposal-HedgeExpertAI.md) calls for contextual
discovery and short, grounded explanations, not raw metadata displays. The
[HEDGE integration baseline](integration-baseline.md) retains the replied integration
questions: the native Angular pane, authentication and acceptance agreements remain
external decisions. This workspace is preparatory; it is not native Store deployment.

## Reproduction and correction

Before this change, fresh-session “Tell me about the first app” and “Compare the
first two apps” returned zero records and unresolved-reference messages. The page
showed a catalogue but the conversation had no bound result list. A named detail
returned a 1,225-character metadata enumeration; generation was disabled.

- Private contextual mode binds initial ordinal references to the first five
  eligible Apps in native-ID catalogue order. Catalogue pagination uses that same
  ordering. Later ordinals refer to the conversation's retained result list, not a
  newly ranked search. A named initial detail establishes its own reference list;
  “it” follows the selected App. Empty search results never silently become a new
  catalogue list. Unresolvable/withdrawn references require a new selection.
- Application dialogue owns explicit Store names, native IDs, compare/search
  commands and source reads even when Rasa labels them as help. Native IDs remain
  case-sensitive. Other intent classification still uses the existing Rasa client
  with its confidence/availability fallback; there is no new NLU framework.
- Ordinary answers show descriptive fields with citations; exact connector,
  version and billing reads keep the existing source-field behavior and caveats. Natural cost questions
  about a selected App use those supplied billing values and unknown-term caveats,
  rather than implying that no price metadata exists.
  Cards retain all projected evidence. The catalogue and cards offer an App
  explanation action instead of opening an unsolicited README dump.
- The existing pinned local Ollama client makes one bounded structured call after
  App selection. It selects up to two relevant descriptive field paths per App.
  Request-specific schemas constrain ranks and available paths; application
  validation checks identity, order, duplicates and output shape. Model text never
  becomes a served factual claim. Descriptions and short README qualifications
  stay together across source fields. A model cannot trim a sentence into a claim.
- Long fields are omitted whole from prose, with an incomplete-evidence notice;
  expandable source cards now show their complete escaped projected text. This
  does not recover text rejected by ingestion: missing/malformed/oversized statuses
  remain explicit. A projection failure is not proof of source absence.
- Generation errors, invalid output and timeouts yield readable grounded fallback
  text. App identity/publication and the complete projection are rechecked after a
  model call. Changed/withdrawn Apps cannot be served from cached session facts.
  HTTP and SSE use the same decision; unvalidated tokens are never streamed.

This is model-assisted **extractive explanation**, not independently verified
free-form expert reasoning, compatibility assessment or suitability policy.
Unverified terms stay unverified; false/zero billing fields never imply “free”.
SCRUM-39 suitability changes are neither imported nor replaced by this work.

## Run and inspect

Run `bash scripts/store-workspace.sh start|restart|status|stop` from this worktree.
Only the `expertai-store-private` labelled resources are operated on. The existing
private PostgreSQL/Qdrant/Valkey volumes are retained. The runner mounts this source
read-only, the existing credential directory read-only, pinned Ollama 0.32.0 and
its existing `qwen3.5:2b` cache read-only. It never downloads weights. The runner has
3 GiB/2 CPU limits and the private trained Rasa container has 768 MiB/1 CPU limits;
Rasa has no published port and container logging is disabled. Ollama listens only
inside the runner. The frozen demo's model/NLU services are never reused.

The only host listener remains loopback port 8098. No Store mutation, credential
extraction, cloud generation or public indexing is introduced. Protected source
values stay in the authorized private workspace, not this document or Git.

Representative browser sequence (names intentionally omitted):

1. In a fresh Chat, send “Tell me about the first app”. It resolves the first
   observed App and explains its descriptions with field citations.
2. Send “Compare the first two apps”. Both identities remain ordered; supplied
   purposes/documentation can be read together without a superiority claim.
3. Ask “What does <exact App name> do?”, then “Tell me more about it”. The second
   turn retains that App rather than searching for the word “it”.
4. Click “Explain this App” in the source card. Inspect “Source evidence” to read
   the complete projected README, including text omitted from short prose.
5. Ask “Show billing fields for <native App ID>”. Exact source values appear with
   unknown currency/period/taxes/licensing caveats, separately from the overview.

## Evidence and acceptance limits

Permanent unit coverage exercises coherent whole-field quotations, cross-field
qualifications, 1,200/1,201-character boundaries, extraction statuses, fabricated
model output, model failure, initial/named/empty-result context and NLU overrides.
Disposable PostgreSQL/Qdrant/Valkey integration coverage exercises the same browser
HTTP/SSE boundary, source identity, model failure and publication withdrawal.
`tests/browser/store-contextual-chat.cjs` exercises the actual private UI using
records discovered at runtime. It retains only counts/status/timings; no source
names, screenshots, conversations, tokens or protected values are logged.

The earlier authorized refresh observed two Apps. Current refresh reports
`authorization_required`; the saved temporary credential is no longer accepted and browsing uses the
retained authorized API observation, not authored demo Apps. Global catalogue
completeness and current upstream publication are unverified. Local identity,
publication gates, real E5/Qdrant retrieval and persistence remain in place.

Observed CPU model turns take tens of seconds, not the proposal's <5-second target.
There is no latency, retrieval-quality, explanation-accuracy or pilot-acceptance KPI
claim. English contextual commands and field-based explanations are bounded;
multilingual dialogue, paraphrase/reasoning quality and long-document summarization
need a reviewed corpus and acceptance evaluation. No corpus training is performed.

Next priorities: approved renewable backend credentials/current catalogue acceptance;
reviewed source-grounded synthesis and multilingual intent examples; measured model
latency/resource work; independent integration with SCRUM-39 after its security gate;
and the agreed native Angular/authentication contract. The inherited npm audit
failure is unchanged and has no waiver here. No dependency, CI or Tailwind change
is included.

Verification on 16 October 2026: **717 unit tests**, **89.96% shared branch
coverage**, **94 disposable integration tests**, Ruff, pinned-Node JavaScript and
shell syntax, whitespace checks, and six unchanged regenerated OpenAPI documents.
The actual private Chromium run passed six validated Ollama/Rasa turns, fresh
ordinal HTTP/SSE selection, named focus, comparison, card actions, full escaped
README inspection, billing caveats and asynchronous history restoration. Postflight
also verified named dense+lexical retrieval, natural billing questions and zero
pending index work. Final UI model turns ranged from 16–28 seconds; an earlier
cold turn took 36 seconds. Counts/timings-only evidence:
`/home/ubuntu/.codex/artifacts/HEDGE-contextual-chat-2026-10-16/`.
