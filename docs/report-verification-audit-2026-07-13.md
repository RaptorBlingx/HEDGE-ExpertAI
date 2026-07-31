# Verification Audit — Follow-Up Report and D2.1

**Audit date:** 13 July 2026  
**Audit revision:** 1.1 — final independent review  
**Audited snapshot:** Git commit `146c2a50d41c8fa426948f498888e30c231feca1` (`146c2a5`)  
**Documents:**

- `docs/follow-up-progress-report-2026-07-12.md`
- `docs/deliverables/D2.1-System-Architecture-Specification.md`

## 1. Assurance boundary

This audit verifies statements that can be checked against the pushed repository snapshot, its Git history, reproducible local commands, and cited authoritative upstream sources. It does not convert repository declarations into independent proof of contractual, legal, organizational, or external-system facts.

In particular:

- the repository contains a proposal file, but not a signed approval record or grant-agreement copy proving that it is the controlling approved version;
- the repository cannot prove legal ownership or contributor assignment merely because its `LICENSE` file names a copyright holder;
- no retained evidence in the audited commit proves consortium approval, live HEDGE sandbox access, compatibility with the real App Store API, production deployment, or final HEDGE KPI acceptance;
- the GitHub repository, audited branch, and commit were independently accessible without authentication on 13 July 2026; visibility proves public disclosure, not release authorization or rights clearance;
- upstream license declarations identify relevant terms but do not replace legal review or an artifact-level software bill of materials (SBOM).

## 2. Material corrections made

| Finding | Original issue | Corrected evidence |
|---|---|---|
| Proposal approval status | Both reports called the repository proposal “approved” or the controlling approved source without an approval record in the repository. | It is now identified as the proposal version stored in the repository; signed/approved status must be confirmed through project document control. |
| Test counts and coverage | D2.1 reported 154 total tests, 122 unit tests, and 61.93% coverage. Those values came from uncommitted local code/test changes that were not in the pushed report commit. | A clean Python 3.11.15 container against `146c2a5` produced 152 passing tests. The CI coverage command produced 120 passing unit tests and 58.70% coverage, failing the 80% gate. |
| Searchable fields | D2.1 stated that publisher and the SAREF value were part of the combined searchable text. | The pushed implementation embeds and lexically scores title, description, and tags. Publisher is payload only. `saref_type` is used only by the separate optional match boost. |
| Feedback/KPI semantics | D2.1 stated that the widget could submit click/accept/dismiss actions and implied the counters supported the later acceptance KPI. | The widget emits accept/dismiss, while the API also accepts click. The widget submits one action for each displayed App; counters are App-action based, not session-acceptance based, and cannot establish the proposal KPI without redesign. |
| Complete-session evidence | The event model was described without the streaming-path limitation. | The streaming widget path does not currently record a complete start/message/recommendation/end lifecycle, so the ten-complete-session KPI still requires implementation and an agreed definition. |
| Historical runtime wording | The original report gave an unretained historical statement about services not running. | The corrected report states only what the retained evidence supports: no live sandbox, real API, end-to-end latency, or final KPI evidence is present. |
| Review completeness | “Complete/content-complete” was used as if it were an objective fact. | The reports now say the document is prepared/documented for review; completeness and acceptance are consortium decisions. |
| Conflicting retained status reports | An April progress note and D3.1 declare deliverables complete, sandbox validation, and KPI PASS without retained raw evidence sufficient for independent reproduction; D3.1 also says 69 queries while the committed JSON has 68. | The corrected reports acknowledge those files but do not rely on their claims as proof of D1.1 delivery, D2.1 approval, official sandbox validation, or final KPI acceptance. |
| Public disclosure | The earlier audit left public visibility open. | The repository, audited branch, and commit were verified as publicly accessible. Internal-marked reports and other project assets already exposed there now require retrospective authorization/IPR/dissemination review. |

## 3. Reproduced checks

| Check | Environment | Result |
|---|---|---|
| Full repository test collection | Clean `python:3.11.15-slim` container; snapshot `146c2a5` | **152 passed**; seven warnings; no deployed services required |
| Exact CI coverage command | Same clean Python 3.11.15 container | **120 passed; 58.70% coverage; failed** the configured 80% threshold |
| Exact configured Ruff command | Clean Python 3.11.15 container; unpinned Ruff resolved to 0.15.21 | **Failed with 20 errors** |
| Frontend install and production build | Snapshot `146c2a5`; `npm ci`; TypeScript and Vite build | Passed |
| Widget JavaScript syntax | `node --check` | Passed |
| Compose structure | `docker compose config --quiet` with `.env.example` copied to `.env` in the isolated worktree | Passed |
| Six static OpenAPI files | JSON parsing and declared-version check | Passed; each declares OpenAPI 3.1.0, but this does not prove conformance or synchronization |
| Runtime OpenAPI regeneration | Repository export script against `146c2a5` | Four committed exports changed; streaming/recorded-session paths and health text were stale, while regenerated SSE/request-body contracts remain incomplete |
| GitHub branch and visibility | Remote ref plus unauthenticated web access | Branch resolves to `146c2a5`; repository, branch, and commit are public |

The test suite uses mocked and in-process integration tests. Passing it is not evidence of a live container stack, HEDGE sandbox integration, real catalogue behavior, model quality, latency compliance, user acceptance, or TRL advancement.

## 4. Additional verified observations relevant to management

- The pushed snapshot has an Apache-2.0 `LICENSE` file with `Copyright 2026 A Arti Muhendislik`.
- Git history uses one generic author identity, `HEDGE-IoT <dev@hedge-iot.eu>`. Git metadata alone does not identify the human authors or prove employer/contractor IP assignment.
- No `NOTICE`, `THIRD_PARTY_NOTICES`, SBOM, `CONTRIBUTING`, CLA, DCO policy, or `CODEOWNERS` file was found in the snapshot.
- Python application requirements use version ranges rather than an exact lock file. Torch and Sentence Transformers are installed without versions in a Dockerfile.
- Several container bases are floating tags, including `ollama/ollama:latest`, `redis:7-alpine`, `python:3.11-slim`, and `node:20-alpine`. Therefore the exact deployed artifacts and their full license set cannot be reconstructed from the commit alone.
- The frontend lock file fixes a JavaScript graph for `npm ci`, with a recorded license-field summary of 263 MIT, 12 ISC, four Apache-2.0, and one each of CC-BY-4.0, BSD-3-Clause, and 0BSD. The gateway Dockerfile copies only `package.json` and runs `npm install`, so the production image build does not consume that lock.
- A current `npm audit` against the pushed lock file reported four known issues: one low, two moderate, and one high. This is a time-sensitive supply-chain observation, not an IPR conclusion.
- The mock catalogue contains 75 records and the evaluation query file contains 68 records. Their authorship/source provenance is not recorded in a dedicated data register.
- The ingestion task writes Redis checksums before confirming that the discovery service indexed the batch. If indexing fails, the configured retry can see those checksums and skip the records; the existence of Celery retry must not be reported as proof of reliable recovery.
- On 13 July 2026, the floating `redis:7-alpine` tag resolved to Redis 7.4.9-alpine. Official Redis terms place 7.4–7.8 under RSALv2/SSPLv1, so the current artifact must not be described as permissive open source.
- The public audited branch includes the proposal, code, mock catalogue, evaluation queries, Rasa examples, prompts/configuration, and reports marked internal. Existing disclosure requires project/legal review; this audit does not establish authorization.

## 5. Conclusion

The local and Google Drive review copies of the two reports have been corrected to match the evidence in the pushed code snapshot and the final checks recorded above. Commit `146c2a5` itself still contains the earlier report text; these corrected report revisions have not been pushed in this audit. The corrected copies deliberately leave contractual approval, legal ownership, third-party clearance, release authorization, live integration, and KPI acceptance open where the evidence does not prove them.

This audit is an engineering and repository-evidence review, not a legal opinion. Final IPR clearance must be approved by the responsible manager and, where needed, qualified legal counsel.
