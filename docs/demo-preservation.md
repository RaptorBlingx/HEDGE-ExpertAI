# Preserved stakeholder demo

Verified on this host on **2026-10-08**. Use this demo for synthetic catalogue
search and streamed recommendations; it is not real HEDGE Store integration,
a production-readiness demonstration, or evidence of Qwen generation quality.

## Revision and separation

- Preserved source: `fa06952a01a251d0b5da37c7c63c7907ddc3d7d0`, detached and
  locked at `/home/ubuntu/hedge-demo`. This is the latest pre-integration HEAD,
  now verified against the running demo. The earlier retained stack acceptance
  is [31 July](evidence/2026-07-31-local-acceptance.md); this revision also includes
  the August CSP/synthetic-link and favicon fixes.
- Integration development remains at `/home/ubuntu/hedge` on
  `feat/hedge-store-v1-integration`, separate from the pinned demo revision.
  Demo preservation did not change application code.
- Reuse the existing **`hedge` Compose project**, fixed `hedge-*` containers,
  network, ports, and persistent volumes. Do not duplicate this stack locally.
  The host has 6.7 GiB RAM; retrieval uses about 720 MiB of its 768 MiB limit,
  and Rasa about 872 MiB of its 1 GiB limit.
- Private local artifacts at `/home/ubuntu/hedge-demo-preserved`: `manifest.json`,
  `compose.demo.json`, a frozen `preserved_demo.py`, browser transcripts and
  screenshots. The Compose snapshot pins current image IDs, existing external
  volumes/network, resolved environment, and the preserved initialization SQL;
  it contains **no build or migrations service**. It contains environment values:
  keep this directory private and do not commit/share the Compose snapshot.
- Local `ops/demo-preserved.path` routes the existing startup/watchdog scripts
  to the frozen helper. No systemd unit, timer, container, or running service was
  restarted. The helper checks captured identities/images/mounts, and can start
  only stopped original containers. It never builds, pulls, migrates, recreates,
  seeds, or deletes data; running-but-unhealthy or changed containers fail closed.

The running services match the preserved application source and widget assets.
The live classifier has an outdated module docstring; its executable AST matches
this revision. Current image IDs, rather than fresh rebuilds, preserve that exact
runtime. PostgreSQL has only migrations `0001_initial` and
`0002_retention_aggregates`: **Phase 1 migration `0003` is not applied**.

## Access and startup

Open **<http://10.33.10.130:8080/demo.html>** on the host or its private network.
The internal React validation console is at `/`; use `/demo.html` for the meeting.
The listener is bound to `10.33.10.130`, so host `localhost:8080` is not equivalent.
Remote stakeholder connectivity has not been verified. If needed, use your normal
SSH route to the host:

```bash
ssh -N -L 18080:10.33.10.130:8080 ubuntu@<demo-host>
# Then open http://127.0.0.1:18080/demo.html locally.
```

Check or start independently of the integration checkout:

```bash
python3 /home/ubuntu/hedge-demo-preserved/preserved_demo.py plan
python3 /home/ubuntu/hedge-demo-preserved/preserved_demo.py start
python3 /home/ubuntu/hedge-demo-preserved/preserved_demo.py check
```

`plan` reports any stopped captured containers. `start` was verified as a no-op
with all 13 running; a cold stop/start was not attempted. After a future cold
start, allow Rasa and retrieval to warm up and repeat `check`. No migration or
ingestion is needed for the existing data. Do not run `make up`, `make build`,
`make e2e`, `make migrate`, `make seed`, or the original checkout's recovery
script for this demo. The E2E smoke script triggers ingestion and is not a
read-only readiness check.

## Verified capabilities and meeting script

| Check | Observed result |
|---|---|
| UI | Chromium loaded widget/assets under the existing CSP; desktop/mobile input was usable, with no console/page errors. |
| Retrieval | English and German SAREF4ENER-filtered searches each returned two Apps; PostgreSQL has 120 active/searchable synthetic Apps, Qdrant has 120 points and a green current collection. |
| NLU | Actual Rasa classified the German energy-search prompt as `search`, confidence `1.0`; this single case does not establish multilingual accuracy. |
| Recommendations | Five cards and SSE `recommendations`, `explanation_delta`, `complete` appeared; synthetic cards had no external App links. |
| Conversation | Greeting, search and help completed in the widget; all tested follow-ups terminated without transport errors. Semantic limits below still apply. |
| Detail data | `/api/v2/catalog/apps/app-009` returned Energy Tariff Advisor metadata. |
| Recovery guards | Mocked changed-image/container/volume cases refused startup before any mutation; only an unchanged stopped container was eligible for start. |

Explain first: **120 synthetic Apps; real retrieval/Rasa; deterministic generation
fixture with application-validated fallback summaries.** `expert-recommend` uses
`OLLAMA_BASE_URL=http://mock-api:9000`, `OLLAMA_MODEL=deterministic-e2e`; no Ollama
container or real Qwen model is running. These fast timings are not LLM latency
or proposal-KPI evidence. The preserved page's “production widget” wording does
not establish production readiness or an approved HEDGE UI integration.

Rehearse: open widget → `Hello` → `Find energy monitoring apps` → inspect the
five synthetic cards and source-based summaries → `Help`. Keep advanced
follow-ups out of the meeting script: `Tell me about the first app` changed the
ranking instead of faithfully explaining the referenced App; comparison returned
generic recommendations, and `Only free apps` did not establish a structured
price filter. These are existing limitations, not fixed in the preserved demo.
Browser checks used fresh test sessions and created ordinary session/impression
traffic; they did not submit acceptance feedback or delete earlier sessions/data.

## Recovery and continued development

- Stopped original containers: use `start`, then `check`. The enabled watchdog
  also uses the frozen helper; running unhealthy containers are left untouched.
- If check fails, inspect `docker logs --tail 100 hedge-gateway` and the relevant
  dependency. Do not run the legacy force-recreate path during the meeting.
  A damaged network endpoint or replacement container requires a deliberate
  maintenance decision; automatic disruptive repair is intentionally disabled.
- Missing/replaced containers: the helper refuses them. After operator review,
  the private Compose snapshot supports recovery of a specific service using:

  ```bash
  docker compose -p hedge -f /home/ubuntu/hedge-demo-preserved/compose.demo.json \
    up -d --no-build --pull never --no-recreate --no-deps SERVICE
  ```

  This was configuration-validated only, not executed. Verify existing volumes, image,
  port ownership and data before recovery; refresh the manifest only after
  validating the replacement. Never recreate an empty database as a shortcut.
- Keep `hedge_postgres-data`, `hedge_qdrant-v118-data`,
  `hedge_valkey-queue-data`, `hedge_embedding-model-cache` and the captured
  anonymous volumes. Do not remove/prune demo containers, volumes or pinned
  images. Preserved mounts/configuration are not an off-host backup or a new
  restore drill; use the existing backup/restore workflow in an isolated
  environment if data recovery becomes necessary.
- Continue integration with offline/unit tests and disposable test databases.
  A later integration stack must use a different host/daemon or explicitly
  separate **all** container names, ports, networks and volumes. `-p` alone
  cannot isolate this repository's fixed `container_name` and host ports.
  Reserve the existing `hedge` project and recovery guards for the demo; do not
  bind integration code/migrations or point integration clients at demo storage.
