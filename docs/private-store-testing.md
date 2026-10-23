# Isolated private Store testing on the HEDGE VM

This deployment starts from the accepted Forgejo integration `5f13ab8` and adds
explicit private service wiring. The earlier workspace imported service functions
and patched HTTP calls in one process. Standard service routes had not activated
that path. Here the actual gateway, chat-intent, expert-recommend, discovery-ranking,
metadata API/worker/scheduler, Rasa, PostgreSQL, Qdrant and two Valkey instances run
in separate containers. No validation adapter, monkeypatches, mock catalogue,
second recommender or runtime LLM is involved.

The only new mode is `PRIVATE_STORE_ENABLED=false` by default. When explicitly
true it requires a native Store ID and rejects `APP_ENV=production`. Existing
Store dialogue, sole suitability assessor, English composition, source-bound
preparer and index repair are reused through internal HTTP endpoints. The index
repair implementation is extracted unchanged from the workspace into shared code;
the workspace imports it, preserving its existing tests. Current public/demo
configuration, service images/tags, databases and source records are untouched.

## Access

On a machine that can SSH to the HEDGE VM:

```bash
ssh -N -L 8096:127.0.0.1:8096 ubuntu@10.33.10.130
```

Open **http://127.0.0.1:8096/** locally. If your SSH configuration uses another
VM hostname/user or a jump host, retain that existing access method and add the
same `-L` forwarding. Only this SSH connection provides remote access; no firewall,
public listener, production proxy or TLS deployment was changed. Another local
forwarded port is also possible. The gateway accepts localhost/127.0.0.1 hosts and
same-origin writes; administrative/internal calls still require a backend key.
No Store secret or internal key is sent to the widget.

## Ownership and lifecycle

- Checkout: `/home/ubuntu/hedge-private-test`, based on `5f13ab8`, with its scoped
  deployment follow-up committed locally on `feat/private-store-deployment`.
- Compose: `docker-compose.private-test.yml`, project **expertai-private-test**.
  Never combine it with the default/demo/production Compose files.
- Private configuration/evidence: `/home/ubuntu/.local/share/hedge-private-test`,
  directory mode 0700. `runtime.env` and `credentials/client-secret` are owned
  mode-0600 files outside Git. The existing secure Keycloak credential is copied
  into this owned configuration; the source credential remains unchanged.
- All new networks/volumes/containers have this Compose project prefix. Only
  gateway port **127.0.0.1:8096** is published. Core services use an internal
  network; metadata services have outbound HTTPS access for Keycloak/Store.
- Cached immutable image IDs are pinned in this VM-specific Compose file. Services
  use the dedicated source checkout read-only, with explicit working directories
  and shared-package paths; they do not import stale `/app` image code. Leave the
  deployed checkout stable. No legacy image tag was rebuilt or replaced.
- The cached model image provides the accepted pinned E5 weights at
  `/opt/e5-model`, revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`.
  No model is downloaded at startup. Rasa uses its existing trained image.
- No Ollama, mock-api or additional authentication service is needed for routine
  Store requests. Incoming access is controlled by the private SSH boundary.

From the dedicated checkout:

```bash
scripts/private-test.sh status
scripts/private-test.sh start
scripts/private-test.sh stop
```

`start` validates the private configuration/database target and resource headroom,
starts only this named project, applies ordered migrations to **hedge_private_test**,
starts application services, and performs initial authenticated synchronization.
It is safe to repeat and was verified against the populated private test database.
`stop` retains all data. Do not run volume-deletion/prune commands.

The fresh database received 0001–0005, including Store membership and prepared
knowledge migrations. No existing database was migrated, seeded or restored.
Publication/availability gates and native identity remain authoritative. Missing
Apps in a response are locally unavailable; global Store completeness is not
inferred. English preparation is automatic from checksum/version-bound source.

Celery beat polls every **300 seconds** using the existing ingestion task; the
existing 60-second repair task reconciles pending scoped index state. A successful
real scheduled worker ingestion was observed, in addition to initial and browser
refreshes. Keycloak acquisition/caching/renewal uses the existing M2M provider,
with backend-only read-only credential mounts. Source snapshots stay private.

## Verification and practical limits

Before starting: 8.5 GB disk free and about 3.3 GiB available RAM on 2 CPUs. Reuse
of cached images kept disk consumption small. Containers have memory/CPU/PID caps,
restart policies and rotated logs. E5 received a 1 GiB cap after measuring its
working set; this VM should not host unrestricted concurrent heavy workloads.
No existing resources were reclaimed or stopped to make room.

Real Chromium used port 8096 through all deployed HTTP/SSE boundaries. Sixteen
English turns covering recommendations, progressively simpler answers, unsupported
capacity, prices, comparisons and first/other references completed in 168–741 ms,
median 374 ms. Two separate concurrent browser sessions, page reload/history and
refresh continuity also passed (five more turns, 394–914 ms). This is local VM
HTTP/SSE timing, not a remote-user network or high-concurrency capacity guarantee.
The observed catalogue has **EdgeConnect and Semantic Treehouse**, zero quarantine
and zero pending index operations. No global completeness claim is made.

Relevant regression verification: 118 focused unit checks, seven disposable
managed-sync/index-recovery integration checks, Ruff, default OpenAPI exports,
Compose validation, live aggregate health, Host/Origin/admin rejection and repeated
startup/migration. All 42 pre-existing containers retain their IDs, start times,
running states and mounts. Browser responses and per-turn timings, index/native-ID
receipts, scheduler success, resource/isolation checks and source commit receipt
are retained privately under the evidence directory. The full test suite was not
repeated and remote CI remains unverified.

The existing tokenizer warning is retained in logs; the pinned E5 encoder loads
and indexes the two Apps and the English conversations pass. Comparisons remain
basic and unsupported-capacity answers terse, as already accepted. This is a
private test deployment, not production/native Angular acceptance or proof of
large-real-catalogue quality. No production deployment or Jira change was made.
