# SCRUM-38 — Store App metadata preservation

Implemented from verified integration baseline `949305a` on
`feat/SCRUM-38-store-metadata`. This corrects Astra finding #1 through the existing
Store client, shared source model, PostgreSQL projection, scoped retrieval and
recommendation code. No Store indexing/publication activation, live ingestion,
ranking, abstention, deployment or Jira status change is part of this issue.

## Reproduction and evidence authority

Before changing code, executing `normalize_store_v1_app` with a constructed real-v1
App dropped `builtForConnector`, `connectorVersion`, `type`, `billable`, `price`
and `dataspaceAppDescription`. The index text was exactly
`Connector . Data integration.` despite supplied README utility text and embedded
properties. Recommendation output also omitted retained version records.
Inspection then confirmed PostgreSQL lexical retrieval independently reconstructed
only name/description/provider, so correcting the model alone was insufficient.

On 14 October 2026, an unauthenticated HTTPS GET of the
[public OpenAPI](https://store.haslab-dataspace.pt/backend/api/v1/api-docs)
returned 200. SHA-256 remained
`f5090c9cad06ea314a70ca1676dc433d97006ddbd7a65f9273058480239793a3`.
`App` declares these fields but no required-property list. `getAllApps` and `getApp`
return App shapes and require Authorization. The public
[deployed Angular App module](https://store.haslab-dataspace.pt/5.f86649fb085d6f8c258c.js)
still displays connector/type values, reads billing fields and parses embedded
`dataspaceAppDescription`; this is observable frontend behavior, not an agreed
compatibility, billing or embedded serialization contract. Its Java-string cleanup
is deliberately not copied into the normalizer.

Available tracked examples were inspected: the existing sanitized shapes reconstruct
formats **reported** from a previous authorized two-App sample, including HTML
README and a JSON string for the embedded description. They are invented records,
not original authenticated payloads. Connector/type/billing values in this issue's
[new contract fixture](../tests/fixtures/store-v1/metadata-app.json) are authored
OpenAPI examples. Neither that fixture nor the historical two-App smoke report
establishes current real field population. No original private snapshot, token or
protected Store endpoint was accessed during this issue.

## Field-to-projection map

All retained facts belong to the native Store/App pair. New fields are optional;
missing/null values remain unknown, and blank strings normalize to missing. No
translations, licences, ontology annotations or external Asset identity are added.

| Store field | Verified declaration / available shape evidence | Local retention and retrieval/recommendation use | Interpretation limit |
|---|---|---|---|
| `builtForConnector` | App string; frontend display observed; live population unverified | `built_for_connector`; utility search text; quoted `builtForConnector` evidence | Source claim only; no connector identity mapping or universal compatibility assertion |
| `connectorVersion` | App string; frontend display observed; live population unverified | `connector_version`; utility search text; quoted source evidence | No version-range evaluation or inference that an App version is a connector version |
| `type` | App string; frontend uses type; live values unverified | `app_type`; text search and source evidence | No invented enum or capability/taxonomy mapping |
| `billable` | App boolean; frontend purchase/pull logic observed; live population unverified | Strict nullable boolean; recommendation value and source quotation, including false | False is not a claim of zero total cost, free licensing or perpetual access |
| `price` | App number/double; frontend reads price; live population unverified | Strict finite number; recommendation value and source quotation, including zero | No currency, billing period, tax, licence or comparison policy; not a pricing filter/ranking signal |
| `dataspaceAppDescription` | App string; reported sanitized JSON-string shape; frontend parses it | Raw string retained locally. Bounded embedded `properties.name`, `description`, `applicationCategory`, `operatingSystem`, `featureList[i]` become search text and source-path quotations | AssetProperties documents these paths on AssetRequest, but does not guarantee every embedded string uses that schema. No Asset join, authority override, JSON-LD expansion, Java-string repair, offers/rating/provider interpretation or remote lookup |
| `readme` | App string; reported HTML shape; frontend reads README | Raw source retained locally; visible text becomes search text and quoted `readme` evidence | Untrusted publisher text, never rendered/executed or accepted as instructions. Links/resources are not fetched |
| `appVersionList` | AppVersion array; reported source-order/null/empty shapes | Full existing normalized versions now retained in recommendation output; bounded version/comments evidence participates in search | No latest/current version chosen. Existing parent-ID validation remains |
| `name`, `description`, `provider` | App strings; existing reported shapes | Existing fields retained; utility text uses the same plain-text extractor; original paths remain evidence | No language, review, suitability or applicability guarantee |
| identity / publication / dates / existing URLs | Existing v1 contract and reported shapes | Existing normalization and Store/App identity retained | `visible && active` conservative eligibility unchanged; registration date is not update time; URLs are not canonical navigation contracts |
| owner/account/wallet/download records, unknown fields, embedded offers/dataAddress | Out of utility scope or meaning/access unknown | Not promoted into recommendations; unknown App fields remain ignored and the private-input reducer still excludes account fields | No new permission or public-data claim |

`source_evidence` maps exact original source paths to derived plain strings, alongside
`source_profile`, `store_id` and `app_id`. This is evidence from the supplied App,
not independently verified truth. Raw README/embedded JSON stay out of recommendation
projections and generation prompts. Existing scalar/version output stays source-shaped.
`readme_status` distinguishes missing, too_large, extracted and not_projected (no visible text or evidence budget exhausted);
`dataspace_description_status` distinguishes missing, too_large, malformed,
unsupported_shape, no_supported_text and extracted. Extracted means some supported
text was obtained, not complete or verified coverage of the embedded document.

## Handling and compatibility

HTML parsing removes markup, attributes, comments and script/style/iframe/object/
SVG/template/head contents. Visible instruction-like prose remains **untrusted
quoted data**. Output uses the existing HTML/Markdown escaping. The opt-in extractive
LLM seam can select exact supplied candidates by their source path; unsupported
paths, altered quotations and invented currency/claims fall back deterministically.
No free-form grounding or real-model quality improvement is claimed here.

Text fields above 16,000 characters are preserved locally but omitted from derived
text rather than cutting a qualification into a complete fact. Embedded JSON above
65,536 characters is retained without parsing. Duplicate keys, non-finite JSON
constants, malformed/deep JSON and unsupported shapes yield no embedded evidence.
Only supported string paths are read; malformed siblings cannot turn numbers,
objects or offers into capabilities. Extraction considers up to 64 feature entries
and 64 source versions; the combined evidence is bounded to 128 fields / 65,536
text characters. These limits describe the derived view, not raw-source completeness.

Wrong types for known fields, including string prices and boolean numbers, retain
the existing strict rejection/quarantine behavior. Invalid embedded **string content**
is instead preserved with its status and does not reject an otherwise valid App.
The existing real client still rejects an entire response containing an invalid
App; this issue does not resolve Astra finding #11 about malformed-neighbor
withdrawals. That remains a separate activation blocker.

PostgreSQL persists raw normalized fields and revision history. Shared evidence
builds the lexical search document and vector text; lexical SQL now uses that
stored derived document. Upserts refresh search text even when source checksum
and publication are unchanged. New absent fields do not change historical Store
checksums. Added/changed source values do change checksums/revisions. Old sparse
payloads still validate, and native IDs and revision/publication rules remain intact.

**Before using this change on an approved existing Store corpus, reingest its
approved source and rebuild its scoped derived vectors.** Existing records cannot
recover fields already discarded; old search documents/vector embeddings cannot
acquire new README evidence merely by upgrading Python. No such production action
was run here. Store rows still create no public indexing outbox work, and public
v2 routes, request models and filters still exclude Store records.

The one-shot private-input reducer now retains the same six useful App fields
instead of discarding embedded metadata before normalization. Input and temporary
storage remain private; no permissions, schedules or external fetch scope expand.
The offline dialogue's broad metadata/price refusal rules are unchanged. This issue
makes facts available to retrieval and recommendation evidence; interpreting natural
language constraints or revising dialogue refusal policy requires its own reviewed
work, especially where business semantics remain unresolved.

## Verification and integration decisions

Tests use MockTransport for the actual HTTPS v1 client, actual disposable
PostgreSQL/Qdrant service boundaries and deterministic embeddings. They cover field
retention, serialized persistence/checksums, README and embedded-only lexical matches,
source-path recommendation/extractive evidence, false/zero/missing values, wrong
optional types, malformed/deep/duplicate embedded JSON, active HTML, size bounds,
legacy document refresh, version order, stale vectors/current metadata, withdrawal
and public-source separation. Test fixtures are authored and contain no private data.

Initial verification at `9c56692` using the existing locked Python 3.11.15
developer image: **656 unit tests** passed with **93.32% shared branch coverage**
(80% gate); **76 focused disposable PostgreSQL/Qdrant integration tests** passed.
Ruff and whitespace checks passed. All six regenerated public OpenAPI files were
byte-identical. One existing Starlette/httpx deprecation warning remains. The
frozen demo and existing runtime services were not used or changed.

Before integration/activation, Store owners should confirm representative authorized
field population, connector identifiers/version semantics, type vocabulary, billing
units/currency/terms, actual embedded formats and README/embedded reuse permissions.
Existing publication/access/completeness and unattended credential decisions remain
open. Code can be reviewed with unknown semantics retained; enabling protected or
anonymous use requires those decisions. No merge or Jira transition is authorized
by this delivery.


## Review corrections — bounded quotations and extraction limits

Both P2 findings were reproduced against `9c56692`: a 1,254-character README
lost its simulation-only qualification at character 1,200; a 16,001-character
README was marked `too_large` but described as absent. Permanent regressions
failed against that commit before the correction.

The quotation helper now returns only complete whitespace-normalized source
values of at most 1,200 characters, with the existing HTML/Markdown escaping.
Longer values are omitted from prose in their entirety and labelled by original
source path: `complete quotation omitted (exceeds 1,200 characters)`. The full
projected evidence remains available in the App result. No arbitrary prefix,
selected tail or guessed qualification is presented as a complete quotation.
Valid short quotations are unchanged. The extractive model's validated quotations
remain bounded to 400 characters; oversized display names use the existing result
rank as a neutral label, retaining App identity in the structured result.

Narratives report README/embedded extraction limitations, including when other
source fields can still be quoted. They assert missing descriptive metadata only
when the supported fields are absent and both extraction statuses explicitly say
`missing`. Limited extraction, oversized retained fields and older projections
without those statuses receive `No descriptive source text could be extracted or
projected`, with supplied processing statuses where available. Human-readable
status labels in prose do not replace the unchanged structured status codes.

The follow-up changes are confined to recommendation rendering, tests and these
notes. Normalization, persistence, checksums, retrieval, source evidence, publication,
ranking, dialogue and model selection remain unchanged. Regressions cover 1,199 /
1,200 / 1,201 / 1,254 / 16,000 / 16,001 character cases, malformed/unsupported
embedded statuses, absent/legacy metadata, escaping, valid extractive responses,
source identity and matching normal/streamed output. Disposable service tests also
verify retained PostgreSQL README values, revisions, indexing and withdrawal.

Follow-up verification: **677 unit tests** passed with **93.58% shared branch
coverage**; **78 focused disposable PostgreSQL/Qdrant integration tests** passed.
Ruff and whitespace checks passed; all six generated public OpenAPI documents
remain byte-identical. These checks establish the rendering corrections and
source/persistence behavior, not live Store or model acceptance.
