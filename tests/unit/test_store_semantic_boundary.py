"""Semantic recovery may publish only reviewed, request/current-source-bound evidence."""
from copy import deepcopy

from scripts.store_v1_playground import load_service

assessor = load_service("unit_t2_boundary", "expert-recommend")("suitability")

APP = {"id": "local", "source_profile": "hedge-store-v1", "app_id": "native", "store_id": "contract-test-only", "name": "Example",
       "source_evidence": {"readme": "The service joins regional flexibility offers into a single market submission."}}
QUESTION = "Coordinate our participants' offers for the system operator"


def receipt(app=APP, **changes):
    return assessor.ReviewedSupport(**{
        "request": QUESTION, "app_id": app["id"], "source_digest": assessor.source_digest(app, "en"),
        "quotes": (("readme", app["source_evidence"]["readme"]),), **changes})


def test_semantic_receipt_extends_lexical_assessment_without_changing_native_identity():
    assert assessor.assess(QUESTION, APP, "en")["status"] == "uncertain"
    result = assessor.assess(QUESTION, APP, "en", reviewed_support=receipt())
    assert result["status"] == "source_supported"
    assert result["evidence_spans"] == [APP["source_evidence"]["readme"]]


def test_unreviewed_network_dictionary_and_invented_quotes_are_not_proof():
    for proof in ({"reviewed": True, "request": QUESTION},
                  receipt(quotes=(("readme", "An invented supported capability."),))):
        assert assessor.assess(QUESTION, APP, "en", reviewed_support=proof)["status"] == "uncertain"


def test_receipt_cannot_cross_requests_apps_or_source_revisions():
    for proof in (receipt(request="A different need"), receipt(app_id="other")):
        assert assessor.assess(QUESTION, APP, "en", reviewed_support=proof)["status"] == "uncertain"
    changed = deepcopy(APP)
    # The quotation is still present; a newly added restriction invalidates the receipt.
    changed["source_evidence"]["readme"] += " Live operation is disabled."
    assert assessor.assess(QUESTION, changed, "en", reviewed_support=receipt())["status"] == "uncertain"
