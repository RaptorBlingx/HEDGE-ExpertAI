# Conversational UX follow-up — 19 October 2026

Initial local UX evaluation on `perf/prepared-store-discovery`, based on `0ed1533`.
The later [response-composition review](2026-10-19-response-composition.md) records
the subsequent fixes and final verification. Figures below describe this earlier pass.
No push, branch merge, deployment or Jira update. The existing private workspace
and preserved demo were not changed or used as evaluation endpoints.

## Product review and changes

Updated AGENTS.md first with concise guidance on direct, natural, useful English
and Turkish conversations, internal validation, evidence-backed confidence and
actual widget evaluation.

The initial 20-turn Chromium widget review exposed substantive requests routed to
generic help/greeting and even reset, broken follow-ups, raw metadata dumps and
unrelated candidate prose. Application-owned routing now reserves destructive and
static actions for explicit controls. Natural browse, comparison and reference
forms reach the existing dialogue. Bounded linguistic equivalents preserve unknown
requirements, negation, quoted identities and preceding technical constraints.

The existing Expert conversation module now presents concise source-based answers,
details, pricing and documented starting links through one presentation callback.
Common Turkish purpose statements and the data-model term receive readable Turkish
explanations. Source inspection still exposes complete fields. Sentence excerpts
retain adjacent qualifications; over-bound quotations are omitted, never cut.

The SCRUM-39 assessor remains the only recommendation eligibility boundary. Richer
unparsed requests can receive an attributed source passage and a clarification,
with an identity bound only for subsequent inspection. Such a candidate is not
promoted to a recommendation, card or recommendation impression. Current-row,
late-change, withdrawal and session checks remain. No new model, dependency,
recommendation service, response cache or runtime generation loop was introduced.

## Actual browser evidence

Final review: 46 turns in nine clean EN/TR conversations, including the original
20 turns, 20 fresh variations and six suggested-prompt/plain-language turns. Five
additional checks verified the final friendly help wording, actual page-button
interaction and complete source-card text. The real widget sent HTTP/SSE requests;
complete rendered replies, raw SSE metadata and screenshots were inspected.

| Browser sample | Median | p95 | Maximum |
| --- | ---: | ---: | ---: |
| 46 final turns | 0.151 s | 0.235 s | 0.443 s |
| 40 core turns | 0.152 s | 0.206 s | 0.257 s |

45/46 final turn records used real Rasa; one used its existing regex fallback.
Rasa's raw classifications can still be wrong with high confidence. The policy
recovered observed requests; this is not a claim that the trained NLU improved.

Timing includes input/send, loopback HTTP/SSE and completed response text in the
DOM, excluding bootstrap, reading time and a separate 450 ms pause for animations.
The shared host was not reserved. Real PostgreSQL, Qdrant and pinned E5 were used;
the adapter retains existing Python service bridges rather than separate service
network hops. Input was the saved, authorized **two-App** catalogue, with no fresh
Store fetch or live-model generation.

Full source-bearing conversations and screenshots remain **outside Git** in
`/home/ubuntu/.local/share/hedge-ux-evaluation-2026-10-19/`: `evaluation.md`,
`conversations.md`, per-phase JSON, `measurements.json`, screenshots, JUnit and
benchmark files. Answers in that transcript are complete actual captures, not
rewritten examples. The directory is private to the workspace user.

## Synthetic runtime scaling

| Authored Apps | Requests | Preparation/index | Median | p95 | Max | Peak runner memory |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 20 | 7.50 s | 0.073 s | 0.079 s | 0.085 s | 655 MiB |
| 100 | 20 | 12.47 s | 0.084 s | 0.101 s | 0.113 s | 752 MiB |
| 300 | 20 | 21.24 s | 0.151 s | 0.164 s | 0.188 s | 715 MiB |

Each fresh runner had one CPU and 1 GiB, real pinned E5, disposable infrastructure
and regex NLU. Four cases repeated five times: browse, EN/TR data-model discovery
and unsupported earthquake/SMS. All 60 requests returned HTTP 200. Every served
positive identity belonged to its authored functional family; negative cases
served no Apps. The result cap remained five. Bootstrap is separate from requests.

These are invented short descriptions in six functional families. They test runtime
behavior at tens/hundreds of records, not recommendation quality on a rich real
catalogue. No concurrent throughput or production-load acceptance is claimed.
Current membership resolution still scans catalogue rows during turns; larger and
concurrent workloads require measurement. Routine generation remains absent.

## Verification and dependencies

- Full unit suite: **1,229 passed**, **89.45%** shared branch coverage (80% gate).
- Focused disposable integration suite: **145 passed**, including prepared
  knowledge, Store conversation, retrieval/recommendations and dialogue.
- Ruff and `git diff --check` passed. All six OpenAPI exports match tracked files.
- Source/model/image/dependency pins and public indexing boundaries unchanged.
  No claim of fully green remote CI or production security certification.

SCRUM-39 `c881c6d` is already an ancestor of this performance branch. Comparing
`c881c6d` with integration `0a02b5a` shows no differences in services/shared/frontend
application sources. No integrated work was copied, overwritten or merged again.
The existing Store workspace composition in `de2fc1b` remains a branch prerequisite.

## Remaining product problems

- Complex and unfamiliar requirements can still require clarification. Some rich
  source passages are useful exploration rather than confirmed recommendations.
- Arbitrary English README prose is still quoted in English during Turkish chats;
  several widget controls are also English. This is not general bilingual synthesis.
- Comparisons explain source differences but cannot invent unlisted costs,
  deployment support or a best choice for an unspecified environment. After a
  failed new search, comparing earlier Apps can require naming them again.
- Real-corpus quality coverage is still two saved Apps plus authored regressions.
  Synthetic scale measurements do not replace held-out real-catalogue evaluation.
