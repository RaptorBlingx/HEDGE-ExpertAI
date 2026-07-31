# URI-Level SAREF Catalogue Profile

The v2 catalogue profile targets ETSI SAREF Core 4.1.1 and the reviewed extension registry in `hedge_shared/saref.py`. It is a pragmatic catalogue alignment profile, not a claim of formal EN 303 760 conformance.

## Supported extensions

The synthetic validation catalogue contains ten applications for each of SAREF4ENER, SAREF4ENVI, SAREF4BLDG, SAREF4CITY, SAREF4INMA, SAREF4AGRI, SAREF4AUTO, SAREF4EHAW, SAREF4WEAR, SAREF4WATR, SAREF4LIFT and SAREF4GRID. Business `domains[]` remain separate from ontology annotations.

Every `semantic_annotations[]` item records:

- term URI and human label;
- ontology/extension URI and pinned version;
- relation type such as domain, function, property or device;
- provenance (`publisher`, `curated` or `inferred`);
- review state/date and confidence for inferred values.

Ingestion rejects ontology roots outside the reviewed registry. Multiple annotations are supported and catalogue detail is available as normal JSON or JSON-LD at `/api/v2/catalog/apps/{id}.jsonld`. The legacy broad `saref_type` exists only in the v1 compatibility representation for one release.

The current 120 records are explicitly synthetic and annotations/translations are marked unreviewed. They are suitable for engineering validation but must not be represented as real commercial listings or expert-reviewed semantic evidence.
