# Approved private prototype checkpoint — 22 October 2026

The owner approved the personally tested conversational experience as a prototype baseline. This is **not production or formal consortium/KPI acceptance**. The known model-review limitations (qualified source claims and consumed inputs promoted as capabilities) remain accepted for private evaluation. No dialogue or recommendation code was changed during release finalization.

## Frozen components

Repository: `git@code.arti.ac:europe/HEDGE-IoT.git`, branch `feat/t2-conversational-architecture`.
Annotated tag `t2-conversational-architecture-20261022` points to approved application commit **05be201f6c06df8a3b1a0cc2894d15f16c31bac0**. Later documentation commits do not change the deployed application. Workspace: `/home/ubuntu/hedge-t2-architecture`.

- Gateway, Chat, Expert and Discovery: `05be201f6c06df8a3b1a0cc2894d15f16c31bac0`.
- Metadata API, worker and scheduler: compatible unchanged `a2a02ad72d5611ed4ffb8bd970d921ebc71468f3`.
- Approved Angular artifact: `c911c4b0f1ac57f220807a00ff58638defe13afe`, unchanged.
- Rasa: trained `hedge-expertai-nlu-v3`; artifact SHA-256 `368e11f8322c83cc021428eae43afb948390cdf09aa4bfc6a66ff0b0b12a5148`. Keep the retained binary for byte-identical recovery; rebuilding from the corpus need not reproduce serialized bytes.
- Existing Ollama/Qwen instance and weights: `qwen3:4b-instruct-2507-q4_K_M`, unchanged. One parallel request, 2048 context, 5 GiB memory cap, 1.5 CPU quota. No second inference service.

[Manifest](t2-prototype-20261022.manifest.json) records exact image IDs, component SHAs, limits, restart policies and log rotation. Image IDs identify locally retained images; they are not promises of availability from a public registry.

## Runtime and access

`https://hedge.aartimuhendislik.com/` reaches existing origin `10.33.10.130:8156` via company-managed Cloudflare infrastructure. Basic authentication protects both UI and API; unauthenticated requests return 401. No DNS/Cloudflare changes were made. TLS terminates at company infrastructure; origin traffic is private-network HTTP. Do not remove the origin password gate without an explicit access decision.

Private runtime: `/home/ubuntu/.local/share/hedge-approved-8156`, Compose project `expertai-approved-8156`. **Never commit its env files, credentials, database dumps, transcripts or full Compose configuration.** Gateway's host port 8157 is loopback only. Data and internal services have no public port mapping.

Sources are archived under `releases/<SHA>` and mounted read-only. The frontend artifact and model cache are also read-only mounts. PostgreSQL, Qdrant, queue and cache have named persistent volumes. Backend credentials remain securely configured; reproduction requires the existing private runtime bundle or separately provisioned credentials, never a secret copied into this document.

All long-running services use `unless-stopped`. The enabled `expertai-approved-8156-ingress.service` serves Angular/API/SSE. Docker logs rotate at 5 MiB × 2 files per container. Gateway was aligned with the new interpretation-plus-answer timeout; origin upstream timeout is 180 seconds. No live reboot/database restart was performed solely for verification.

Normal recovery, on this VM with retained private configuration:

```bash
docker compose -f /home/ubuntu/.local/share/hedge-approved-8156/compose.json config --quiet
docker compose -f /home/ubuntu/.local/share/hedge-approved-8156/compose.json up -d
sudo systemctl start expertai-approved-8156-ingress.service
curl --fail http://127.0.0.1:8157/ready
```

Do not issue `down -v`, broad cleanup commands or start retired previews. Existing credentials can be read by the authorized owner through SSH from `evidence/release-05be201/private-access.json`; do not print them into shared logs. No UI rebuild or data migration is needed for this checkpoint.

## Backups and rollback

`backup.py` under the private runtime creates private, hashed bundles of PostgreSQL custom dumps, Qdrant collection snapshots, Valkey RDB snapshots, configuration, access credentials, Rasa v3 and Angular artifacts. Only snapshots created by that invocation are removed from Qdrant after successful download. Seven successful backup bundles are retained; incomplete bundles remain for inspection. Daily systemd timer: `expertai-approved-8156-backup.timer`, 04:15 UTC plus up to ten minutes jitter. Sources, old model and local pinned images are retained separately.

The PostgreSQL dump was restored successfully into a disposable network-isolated PostgreSQL container, yielding the two Store records. That container was removed. Qdrant/config/model/UI backups are checksum-verified; a full disaster-recovery rehearsal of all services was not performed. Valkey queue RDBs are forensic recovery material: the active queue uses AOF, so do not blindly copy an RDB over live AOF files. Reconcile the durable ingestion/index outbox when recovering derived state.

Previous code rollback (no data restore):

```bash
python3 /home/ubuntu/.local/share/hedge-approved-8156/evidence/release-05be201/rollback.py
```

This stops/recreates Gateway, Chat, Expert, Discovery and Rasa using the saved prior configuration: Chat/Expert `86fa782`, Gateway/Discovery `a2a02ad`, prior Rasa. It leaves database/vector/session volumes, Qwen and the private access gate intact. Afterwards wait for Rasa model loading, check Gateway readiness and Rasa parse, then perform one authenticated browser discovery/provider turn. This procedure is configuration-validated and its source/model assets verified; it was **not executed against the live site** just to demonstrate rollback. A checkpoint of the pre-finalization 05be201 mixed runtime is also retained in `evidence/freeze-20261022`.

Backups currently reside on the same VM. They protect against operational mistakes, not VM/disk loss. Off-VM encrypted backup replication is a remaining operator responsibility. Never restore a dump into the live database casually; stop writers and first validate recovery in separately named resources.

## Verification and remaining limits

The concise authenticated HTTPS browser smoke covers catalogue discovery, card identity, explanations, provider context, comparison and a documented recommendation. Real Rasa/E5/Qwen service boundaries are used. Private evidence is retained in `evidence/freeze-20261022`; earlier browser evidence and accepted misrouted open questions remain in `evidence/release-05be201`.

Two real authorized Apps remain synchronized, with no quarantine/index backlog. No synthetic Apps were seeded. The separate canceled 8176 preview's containers/networks and ingress unit were removed; its volumes are retained. Other teams' QA and historical recovery data were not modified.

CPU inference remains slow and concurrent-user capacity is unproven. Open questions can misroute and generated prose can embellish; the model-promotion limitations remain. No new quality research, broad test replay, model changes, Jira updates, merge or public-release approval is implied.

Final freeze smoke: six HTTPS browser turns passed with no browser errors. Prepared responses were 0.33–0.44 s; the Qwen-assisted recommendation took 21.74 s. Gateway now reports `05be201` accurately. All core services were healthy with zero restarts/OOMs, the two Store Apps had no pending index/quarantine/error, anonymous UI/API returned 401, and all 24 other running containers retained their identities/start times. Approximately 5.0 GiB host RAM remained available with Qwen loaded. This is a single-user smoke, not capacity certification.
