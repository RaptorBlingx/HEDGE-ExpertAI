# Isolated Store Ollama evaluation

This opt-in path reuses the existing Ollama client and Store dialogue/recommendation
pipeline. It reads the already authorized private JSON snapshot; it makes no Store
requests, enables no public results and adds no production service or dependency.
The default synthetic v2 generation path is unchanged.

## Grounding contract

Ollama chooses concise complete source sentences from `description` and `provider`.
The model must return typed schema JSON for all selected ranks in their original
order. Code checks each selected sentence against the exact supplied candidates,
rejects extra claims/fields, partial quotes that drop negation, omissions, duplicate
fields and reordering, then renders natural connective prose with field citations.
App names, native identity, publication eligibility and ranking come from the
existing PostgreSQL/retrieval/dialogue path, never from the model. README/HTML,
embedded metadata and conversation history are excluded from model input; source
strings and questions remain untrusted data. Output strings are escaped.

This is **real model execution for extractive selection**, not unrestricted LLM
paraphrasing or proof of expert reasoning/training. The current synthetic validator
checks title order, not factual entailment, so it cannot safely admit free-form
Store claims. Sparse metadata still limits usefulness. Prices, suitability,
superiority and unsupported capabilities remain explicit deterministic abstentions.
Missing results, any App without a usable excerpt, and non-English requests retain the existing fallback.

A single model request uses `think=false`, JSON schema, temperature 0, 2048-token
context, one CPU thread, bounded output and a 40-second request timeout. It has no
retry or continuation. Failed, incomplete, malformed or unsupported generation
returns the existing source-grounded fallback. Generation provenance/completion
and elapsed seconds appear on the isolated response/SSE complete event; each reply
labels validated Ollama excerpts or deterministic fallback. Nothing unvalidated is
streamed. Current PostgreSQL fields/publication are checked again after generation;
if an App changed/withdrew, the reply fails closed and clears stale references.

## Runtime setup

The host currently cannot safely store the full GPU Ollama image alongside model
weights, so a private CPU-only copy of **the same pinned Ollama 0.32.0 release** is
used inside the existing disposable runner. No system installation, Docker Compose
service, demo volume, global model cache or host Ollama port is used. Public runtime
and model artifacts are outside Git. Prepare once (already prepared on this host):

```sh
runtime_dir=/home/ubuntu/.cache/hedge-store-ollama/0.32.0
install -d -m 700 "$runtime_dir"
curl --fail --location --output "$runtime_dir/runtime.tar.zst" \
  https://github.com/ollama/ollama/releases/download/v0.32.0/ollama-linux-amd64.tar.zst
printf '%s  %s\n' \
  56362d7609dfa9e35aaebb7c9cab25605d8f0528ec3d5d585dc83d6642002bab \
  "$runtime_dir/runtime.tar.zst" | sha256sum --check
tar --zstd --extract --file "$runtime_dir/runtime.tar.zst" --directory "$runtime_dir" \
  --no-same-owner --wildcards --exclude='lib/ollama/*/*' 'bin/ollama' 'lib/ollama/*'
rm -- "$runtime_dir/runtime.tar.zst"
```

This requires `zstd`; it keeps only CPU files (about 65 MiB), not CUDA/ROCm libraries.
The archive was verified against the release digest before extraction. See official
[structured output documentation](https://docs.ollama.com/capabilities/structured-outputs)
and the [runtime release](https://github.com/ollama/ollama/releases/tag/v0.32.0).
Schema compliance alone is not evidence of factual grounding; the additional
source-candidate validation is required.

Use the existing [private-input setup](store-v1-authorized-evaluation.md) and an
unused loopback port, with **`--apps-json`**, never the token-file option:

```sh
cd /home/ubuntu/hedge
bash scripts/store-v1-playground.sh --browser --ollama --ollama-model qwen3.5:2b-q4_K_M --port 8095 \
  --apps-json /private/already-fetched-apps.json \
  --store-id 56779afa-bdcc-4abe-a8b0-d306dc07bed1
```

The default model remains `qwen3.5:2b`. An explicitly approved test-only model
variant can be selected with `--ollama-model`; application defaults stay unchanged.
The public model is pulled into `/home/ubuntu/.cache/hedge-store-ollama/models` and
retained for reuse. The daemon runs only inside the uniquely named disposable
runner, bound to its own loopback. Its home/profile is ephemeral; no system home
variable is repurposed. Prompts and model output are not logged. Private input stays
read-only and mode 0600. Ctrl-C cleans only this run's containers/networks/data;
public runtime/model caches remain. Remove only known task-owned evaluation resources
if recovering an abandoned run; do not prune or stop existing evaluations.

The launcher checks host memory before starting: 3200 MiB available for CPU Ollama,
3800 MiB for Ollama plus E5; Rasa diagnostics run separately. Runner limits are
2.5 GiB without E5 (3 GiB with E5), one CPU and no additional swap allowance.
Model residency expires after two minutes. These limits protect other workloads;
they are not throughput/latency acceptance evidence. Existing E5 evaluations are
independent. Compare deterministic and generated replies with **identical retrieval
configuration**; never treat missing lexical matches as successful semantic retrieval.

## Verification protocol

Use the exact five questions, in order within one conversation:

1. Show me all available applications
2. Tell me more about the second app
3. Compare EdgeConnect and Semantic Treehouse
4. Find applications for organizing semantic information
5. How much does EdgeConnect cost?

Run each conversation with generation off/on, compare returned Apps/identity/rank,
check source citations, references, missing-price abstention, injection and timings.
The privacy-preserving browser regression logs only counts, timing, character lengths
and generation diagnostics; no records, names, screenshots or traces:

```sh
NODE_PATH=/tmp/hedge-browse-browser-tools/node_modules \
PLAYWRIGHT_BROWSERS_PATH=/tmp/hedge-browse-browser-tools/browsers \
STORE_DETERMINISTIC_URL=http://127.0.0.1:8096 \
STORE_LLM_URL=http://127.0.0.1:8095 node tests/browser/store-v1-grounded-chat.cjs
```

The first configured `qwen3.5:2b` attempt exceeded the isolated memory cap: its
worker was killed, while the UI returned a safe deterministic response (HTTP 200,
two Apps, about 4.65 seconds). That is recovery evidence, **not successful model
execution**. The host's existing containers/mounts/start times were preserved.
Real-model acceptance requires a verified run within the available resources;
no production readiness or proposal KPI is claimed from these checks.

## Observed authorized-snapshot run — 2026-10-13

The user approved **`qwen3.5:2b-q4_K_M` for this evaluation only**. Application
model defaults remain unchanged. Ollama 0.32.0 reported CPU execution, zero VRAM,
model residency about 1.49 GiB and model manifest digest
`1e2d21a4f03ab9e4a9c1976a4b7e88f21de61d65f2c5485d8fde8942be73f1e7`.
The already authorized private snapshot contained two eligible Apps; no further
authenticated Store requests were made. Both conversations used lexical retrieval
and regex NLU, not E5 or Rasa. Existing E5/demo evaluations were left running.

| Question (above) | Apps | Deterministic seconds | Ollama-enabled seconds | Observed generation |
|---|---:|---:|---:|---|
| 1 — list | 2 | 0.192 | 25.684 | Validated source excerpts |
| 2 — ordinal details | 1 | 0.464 | 27.285 | Model completed; unsupported output rejected, deterministic fallback |
| 3 — comparison | 2 | 0.336 | 28.533 | Validated source excerpts |
| 4 — semantic-information search | 0 | 0.301 | 0.986 | No lexical match; no model call |
| 5 — price | 0 | 0.427 | 0.443 | Explicit missing-price abstention; no model call |

The five-question browser regression passed with **identical complete App results
and order** between modes, incomplete-snapshot warning, ordinal context, source
validation and two injection probes (including a named-App request reaching the
generation seam). No raw responses, model text, private records, screenshots or
traces were retained in Git. Tests report only aggregates and generation provenance.

Initial Q4 requests returned empty evidence arrays and were correctly rejected.
The schema now requires evidence; requests with any App lacking a usable excerpt
skip generation entirely. This preserves sparse-record fallback without fabricating
fields. Provider values remain complete; description candidates are whole sentences.
A Q4 reload at the earlier 2.25 GiB cap killed one model worker, with a safe fallback.
After checking about 3.7 GiB available host RAM and stopping only task-owned runs,
the final 2.5 GiB capped runner completed the browser evaluation with **zero OOM
events/kills**. Its peak reached the cap and incurred memory reclaim, so headroom
is tight; this is not evidence for concurrent-model throughput. Existing container
identities, images, mounts and start times matched the preservation baseline, and
the demo checkout remained clean at its pinned revision.

The LLM offers constrained excerpt selection and connective presentation, with
field citations and explicit comparison limits. It adds no facts to the very short
source descriptions and did not improve ordinal details in this run. At these
latencies the deterministic path is more practical; generation remains optional.
Missing semantic retrieval in this lexical run is not resolved by generation.
Combined E5/Ollama was not started because available headroom did not meet the
3800 MiB guard. No multilingual or free-form reasoning acceptance is claimed.

Verification: 520 unit tests (92.46% shared-package branch coverage), 43 focused
isolated PostgreSQL/Qdrant integration tests, Ruff, Bash/JavaScript syntax,
`git diff --check`, and all six OpenAPI documents unchanged. Failure tests cover
timeouts, invalid/partial/reordered evidence, negation-dropping excerpts, sparse
records, injection/markup and authoritative publication rechecks after generation.
Task-owned comparison runs are stopped after verification; restart with the
command above and your existing private snapshot. No demo or existing evaluation
resources need to be stopped.
