# Consolidated private prototype runtime

On 21 October 2026 the owner explicitly authorized retiring obsolete HEDGE
previews, including the historical demo, to prioritize the current prototype.
This supersedes earlier instructions to keep all historical previews running.
No persistent container, database, volume, credential or model cache was deleted.

## Current boundary

- Private entry: `http://10.33.10.130:8156/`, also `hedge.int.arti.ac:8156`.
- Deployment project: `expertai-approved-8156`; gateway loopback port 8157.
- Approved Angular artifact: `c911c4b`, unchanged and hash-verified.
- PostgreSQL, Qdrant, Valkey cache/queue, Rasa, Discovery/E5, Expert, Chat,
  Gateway, metadata API/worker/scheduler and Ollama belong to the current project.
- Real Keycloak M2M ingestion retains only authorized Store applications. Source
  credentials remain backend-only read-only mounts from the existing private
  credential directory; stopping the old services does not remove those files.
- Own Ollama reuses the cached approved `qwen3:4b-instruct-2507-q4_K_M` model,
  read-only model files/binary, one parallel inference, queue limit two,
  2048-token context, q8_0 KV cache, 3072 MiB memory/swap ceiling and 1.5 CPU quota.
  The old shared model container is stopped; there is no 2B fallback.
- Only the private frontend entry is network-accessible. Required same-origin
  API/SSE traffic is proxied; internal/admin/evaluation endpoints remain blocked.
  Public DNS, Cloudflare and reviewer access protection remain administrator work.

## Retired environments and recovery

The five retired projects had 43 running containers: `hedge` (13),
`expertai-private-test` (12), `expertai-t2-demo-1501279` (7),
`expertai-t2-demo-085f846` (6), and `expertai-angular-preview` (5).
Host Node previews on 8126/8136 were stopped. Demo startup, watchdog and cleanup
automation were disabled to prevent silent resurrection or removal of old state.

Private inventory, exact identities/mounts, prior systemd states and restoration
instructions are retained at `/home/ubuntu/.local/share/hedge-runtime-consolidation/`:
`inventory.json`, `compose-projects.json`, `RESTORE.md`. Current deployment config,
release manifest and operations instructions are in
`/home/ubuntu/.local/share/hedge-approved-8156/`.
These directories can contain runtime secrets/private transcripts; do not publish
or blindly execute their files. Restore selected original containers, never a fresh
legacy build/seed/migration. Restoring every old stack alongside loaded inference
would recreate the original memory problem. Recheck capacity and withdraw/stop the
current deployment first where necessary. No unrelated company service was stopped.

## Explanation boundary

Previously, ordinary recovery interpreted a request then returned prepared prose;
resolved metadata/simplification often bypassed inference altogether. The optional
source-cited explanation path now operates on one application already resolved by
the application, with explicit/resolved references taking precedence over old focus.
Its single call distinguishes explanation from other operations and can restate
purpose, explain terminology or give an explicitly illustrative example.

Complete automatically prepared purpose passages and applicable source limitations
form its bounded context. Sparse feature labels are not expanded into invented
workflows. Source paths are validated; model prose never changes recommendation
eligibility, grants reviewed support, enters the index or becomes source evidence.
Code checks current membership again after inference. Provider/pricing reads,
comparisons, discovery commands, capability verdicts and retained filters retain
their existing paths. See [configuration](configuration-reference.md#source-cited-english-explanations).

Citations and structural checks are not a proof of semantic entailment. Generated
paraphrases still require source-to-answer review, and CPU inference remains slow.
Prepared-path latency does not establish LLM latency or proposal KPI acceptance.
Private actual browser responses and resource observations accompany the runtime
inventory; distinguish aborted diagnostic runs from the final completed smoke.

## Bounded verification and limits

448 focused explanation, dialogue, original suitability, similarity and
finalization unit checks passed; Ruff and the default OpenAPI export passed
(no public schema changes). Actual Angular/service-boundary runs cover browsing,
recommendation badges, comparison, an unsupported requirement, metadata follow-up,
App switches, explanations and illustrations. Diagnostic failed prose is retained
separately from subsequent targeted confirmations, outside Git.

The original prepared failure on a comprehension follow-up was reproduced. Qwen
is now actually invoked for explanations and retains the discussed App. A source
bundle overflow and cross-App narrative priming were corrected during verification.
Controlled recommendation decisions remain independent of model prose. Ordinary
metadata/browsing remain fast, while the CPU-only model adds tens of seconds.

Remaining quality limits: repeated simplifications can still be near-paraphrases;
generated wording may overgeneralize roles or what it means to manage a model.
Source citations and prompts do not eliminate that risk. This is a functioning
LLM-enabled private prototype, not unqualified conversational-quality acceptance,
T2 completion or a multi-user/public-load acceptance claim.
