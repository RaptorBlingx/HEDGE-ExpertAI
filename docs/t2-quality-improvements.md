# T2 conversation quality follow-up

Based on checkpoint `1501279`, on `feat/t2-quality-improvements`.
For the subsequent broader routing/action investigation, see
[conversation reliability](t2-conversation-reliability.md).
This changes conversation policy and presentation, not Store synchronization,
E5, indexing, the one-pass Qwen interpreter, or suitability eligibility.

## Diagnosis and changes

- Real Rasa labelled direct provider questions as comparison/refinement. The
  prepared presenter could answer some forms, but the fast-path gate unnecessarily
  sent them to an interpreter with no provider mode. It sometimes replaced the
  correct answer with access instructions. Closed provider/purpose questions now
  read current metadata directly, through the existing source-field route. Exact
  names, opaque native IDs, singular/plural references and ambiguous targets use
  existing identity bindings; added functional constraints cannot become a
  metadata-only answer. Missing providers remain unknown, never model inventions.
- Explanation selection used word overlap again on each simplification, losing
  the actual passage just explained. Context now retains up to five source-bound
  passage references by App identity, including the rendered explanation. Factual
  interludes preserve those bindings; purpose changes reset the topic. A request
  to simplify an already readable answer selects its shorter supported form.
- Practical explanations appended long or irrelevant source paragraphs. Prefer
  complementary causal details, resolve adjacent recorded-information references,
  and use conservative English grammar for recorded measures and their purpose.
  Original quotations and qualifications stay intact; presentation is not evidence
  for suitability. Unknown constructions keep source wording. No per-App prose,
  extra model calls, knowledge-version bump or database rewrite is required.
- A model clarification cannot discard an already resolved App when the existing
  assessor found no support for a feature. Reassess the original request and keep
  the focused App in the source-based answer. The discourse word “too” is request
  scaffolding, not an additional capability; restrictions/numbers still survive.

## Verification boundary

Replay the original 18-question widget checklist and separately frozen English
variations through gateway → Rasa/chat → Expert → Discovery with real synchronized
Store data, E5 and `qwen3:4b-instruct-2507-q4_K_M`. Read complete answers, record
prepared/model-assisted timings separately, and retain raw evidence outside Git.
A separate disposable 8116 stack reuses existing inference/retrieval endpoints;
ports 8096 and 8106, their source mounts, configuration and data are unchanged.
No model substitution, push, merge or deployment is part of this change.

These are engineering conversations against two real Apps, not independently
labelled catalogue-scale results or T2 acceptance KPIs. The grammar is deliberately
limited: repeated requests can exhaust the shorter explanation, comparisons remain
basic, and model-assisted turns retain the CPU inference latency and uncertainty.
Broader paraphrasing and larger-catalogue quality still need evaluation.
