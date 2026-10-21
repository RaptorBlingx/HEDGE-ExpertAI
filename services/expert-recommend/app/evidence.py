"""Requirement-level source evidence for recommendations.

A request is split into the functions the user asked for. Each App's functional
source text is split into whole sentences. A requirement is documented when the
sentence that best matches it states it affirmatively. When that sentence negates
it, or states it only under a limitation (planned, simulation-only, requiring
another application), the limitation is recorded instead. An App is a complete
match only when every requirement is documented; otherwise it is at most partial.

Semantic similarity comes from the pinned E5 model in Discovery. Normalized
lexical overlap covers exact vocabulary and keeps decisions available, more
conservatively, when the similarity service is unavailable. A limitation applies
only when it concerns what was requested (or the App's operation as a whole), so
an unrelated limitation elsewhere in a README does not hide a documented
capability. Retrieval rank never establishes support.
"""
from __future__ import annotations

import logging
import os
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

# Chosen once on the authored development queries (evaluation/retrieval), then
# checked on separately authored unseen scenarios (evaluation/recommendation);
# never tuned per App or query.
DENSE_MATCH = 0.87      # close enough on its own
Z_MATCH = 2.0           # stands out among the pool's sentences for this requirement...
STANDOUT_FLOOR = 0.83   # ...without being weakly related in absolute terms
Z_WITH_TERMS = 1.5      # a weaker standout suffices with shared vocabulary
GAP_MATCH = 0.82        # a limitation sentence relevant to the requirement
GAP_MARGIN = 0.07       # ...about as relevant as the affirmative evidence
MIN_COMPARISON = 12
TITLE_WORDS = 4         # "Maintenance reference library" needs shared vocabulary
TIE = 0.02

_NEGATIVE = re.compile(
    r"\b(?:not|no|never|cannot|neither|nor|lacks?|unsupported|unavailable|excluded|disabled|deactivated|"
    r"deprecated|discontinued|unimplemented|unlike|nao|nunca|nicht|kein\w*|aucun\w*|desativad\w*|"
    r"deaktiviert\w*|indisponivel)\b|n't\b")
_LIMITED = re.compile(
    r"\b(?:only|planned|future|roadmap|upcoming|will|may|might|possible|pending|subject to|requires?|required|"
    r"necessary|needed|needs|prerequisites?|depends? on|simulation|simulated|prototype|pilot|beta|experimental|demo|"
    r"mock|proposed|under development|another (?:app|application|service)|other apps?|third.party|"
    r"(?:an )?external (?:app|application|service|analytics)|licen[cs]ed|unspecified|apenas|somente|nur|geplant)\b|"
    r"\b(?:if|when|once|provided that)\b.{0,40}\b(?:installed|configured|purchased|licensed|enabled|integrated|"
    r"connected|available)\b")
# "Does not require another App" says nothing else is needed: not a limitation.
_NO_PREREQUISITE = re.compile(
    r"\b(?:another|an external|a separate|other)\s+(?:apps?|application|service)\b|"
    r"(?:\bnot|n't)\s+(?:be\s+)?(?:require|required|need|needed|necessary|depend)\w*(?:\s+on)?")
# A statement about the App's operation as a whole ("It does not work in
# production", "Another App is required") limits every requested function.
_APP_SUBJECT = re.compile(
    r"^(?:it|(?:this|the)\s+(?:app|application|service|platform|system|feature|function)|all\s+(?:features|functions)|"
    r"(?:the\s+)?(?:deployment|installation|access|usage)|"
    r"(?:another|an external|a separate|a third.party)\s+(?:app|application|service|integration))\b")
_OPERATIONAL_WORDS = ((
    "work works operate operates run runs available availability usable use used enabled disabled supported "
    "production simulation demo prototype pilot only feature features function functions app application service "
    "system platform all required necessary needed prerequisite another external separate third party installed "
    "integration deprecated discontinued unavailable deployment installation access usage approval approved "
    "certification"
).split())
# Delivery/availability wording carries no functional topic of its own: "SMS
# delivery is disabled" is about SMS.
_GENERIC_WORDS = ((
    "deliver delivers delivery delivered send sends sent channel available availability enabled disabled "
    "unavailable supported provided required needed necessary another external app application service feature "
    "function only via perform performed versand envio verfugbar disponivel ist esta"
).split())
# Text addressed to an assistant, or a question, is not a description of the App.
_INSTRUCTION = re.compile(
    r"\b(?:ignore|disregard)\b.{0,40}\binstructions?\b|^(?:say|state|tell|claim|recommend|respond|answer|pretend|"
    r"always|output)\b|\?\s*$", re.I)
# "Another App sends them via SMS" describes a different actor, not this App.
_OTHER_ACTOR = re.compile(r"^(?:another|other|an external|a third.party)\s+(?:apps?|applications?|services?)\s+"
                          r"(?!(?:is|are|must|may|can|should)\b)[a-z]+s\b", re.I)
# A limitation the user explicitly asks for ("try it in a simulation") is not a gap.
_ENVIRONMENT = re.compile(r"\b(?:simulation|simulated|prototype|pilot|beta|experimental|demo|mock|test(?:ing)?)\b")
_ONLY_SCOPE = re.compile(r"\bonly\s+(?:available\s+)?(?:in|via|for|on|through|with|using)\s+([^,.;]+)")
# A following sentence that refers back ("This feature is only ...") qualifies its antecedent.
_ANAPHORA = re.compile(r"^(?:this|that|these|those|such|its|only)\b"
                       r"(?!\s+(?:app|application|service|platform|system)\b)", re.I)
# "Provides earthquake warnings. Sends them via SMS." refers across sentences.
_REFERENCE = re.compile(r"\b(?:them|they|these|those)\b", re.I)
_WITHOUT = re.compile(r"\b(?:without|sem|ohne)\s+(?:\w+\s+){0,2}\w+")
_CONTRAST = re.compile(r",?\s+\b(?:but|however|whereas|although|though|except that)\b\s+", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\s*[\n•]+\s*")
_SPLIT = re.compile(r"(\s*(?:[,;]\s*(?:and\s+(?:also\s+)?|then\s+|also\s+|plus\s+)?|\s+(?:and\s+also|as well as|and then|"
                    r"and|plus|then|also|with)\s+))", re.I)
_NEED = re.compile(r"\b(?:need|needs|want|wants|looking|require|requires|must|should|find|recommend|"
                   r"help|app|apps|application|applications|tool|tools|something|anything|which|what|"
                   r"is there|can|could|would like)\b", re.I)
# "Our departments use conflicting field names." describes the situation.
_SITUATION = re.compile(r"^\W*(?:\w+\W+){0,3}?(?:have|has|is|are|was|were|use|uses|run|runs|operate|operates)\b", re.I)
# Request scaffolding, not functional content.
_SCAFFOLD = re.compile(
    r"^(?:(?:hi|hello|please|so|ok|okay)[,!]?\s+)*(?:(?:can|could|would) you\s+)?(?:please\s+)?"
    r"(?:(?:find|show|recommend|suggest|search for|give)(?: me| us)?\s+(?:an?\s+|some\s+|the\s+)?"
    r"(?:(?:good|best)\s+)?(?:(?:applications?|apps?|tools?|software|something|services?)\b)?\s*(?:(?:for|to|that|which)\b)?\s*|"
    r"(?:i|we)(?:'d| would)? (?:need|want|like|require|am looking for|are looking for)\s+(?:to have\s+)?"
    r"(?:an?\s+|some\s+)?(?:(?:applications?|apps?|tools?|software|something|services?|way|place)\s+"
    r"(?:that|which|to|for)\s+(?:can\s+)?)?|"
    r"(?:is there|are there)\s+(?:an?\s+|any\s+)?(?:applications?|apps?|tools?|something|anything|services?)\b\s*"
    r"(?:that|which|to|for)?\s*(?:can\s+)?|"
    r"(?:which|what)\s+(?:apps?|applications?|tools?)\s+(?:can|could|will|would|do|does)?\s*|"
    r"(?:applications?|apps?|tools?|something|software)\s+(?:that|which|to|for)\s+(?:can\s+)?)", re.I)
_LEAD = re.compile(r"^(?:(?:which|what)(?:\s+(?:one|ones|apps?))?(?:\s+of\s+(?:them|these|those|the two|both))?\s+"
                   r"(?:can|could|does|do|will)\s+(?:also\s+)?|"
                   r"(?:does|do|can|could|will|is|are)\s+(?:(?:it|they|this app|that app|this one|that one)\s+)?(?:also\s+)?|"
                   r"(?:one|a|an|the|this|that|our|my)\s+(?:single\s+)?(?:apps?|applications?|tools?)\s+"
                   r"(?:must|should|needs? to|has to|can)\s+|(?:must|should|can|to)\s+|(?:tell me|help (?:me|us))\s+)", re.I)
_STOP = set((
    "a an the and or of to for in on at by with from into onto as is are be been being was were it its this that "
    "these those they them their there here we us our you your i me my he she his her can could would should "
    "will shall may might must do does did done have has had please find show recommend suggest search give "
    "need needs want wants like looking look require requires app apps application applications tool tools "
    "software service services something anything which what who how when where some any one single also "
    "too very really just than then so such way place help able get make let using use used about "
    "support supports provide provides offer offers "
    "preciso quero encontre encontrar procure mostre mostrar recomende por favor um uma os as o para de da do que "
    "pode podem voce aplicacao aplicacoes e ich suche brauche bitte empfehlen empfehle zeige mir eine ein der die "
    "das fur zu und kann kannst du anwendungen"
).split())
# "Estimate prices rather than consumption", "... but I don't need validation":
# what follows is not requested (unlike "must not", which is a constraint).
_EXCLUSION = re.compile(r",?\s+\b(?:rather than|instead of|but not|not including|"
                        r"(?:but|and)\s+(?:i|we)\s+(?:don't|do not)\s+(?:need|want|require|care about))\b", re.I)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

Status = Literal["documented", "limited", "excluded", "not_documented"]


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c)).replace("’", "'")


_SUFFIXES = (("ators", ""), ("ator", ""), ("ations", ""), ("ation", ""), ("ating", ""), ("ated", ""), ("ates", ""), ("ate", ""),
             ("ments", ""), ("ment", ""), ("ures", ""), ("ure", ""), ("ings", ""), ("ing", ""), ("ions", ""), ("ion", ""),
             ("ies", "y"), ("es", ""), ("ed", ""), ("s", ""), ("e", ""))


def _stem(word: str) -> str:
    """Light inflectional/derivational normalization (aggregates ~ aggregation)."""
    for _ in range(2):  # settlements -> settlement -> settl
        for suffix, replacement in _SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 3 and not word.endswith(("ss", "us", "is")):
                word = word[: len(word) - len(suffix)] + replacement
                break
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiou":
        word = word[:-1]
    return word


def terms(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[^\W_]+", _fold(text)) if w not in _STOP and not w.isdigit()}


_OPERATIONAL = {_stem(w) for w in _OPERATIONAL_WORDS}
_GENERIC = {_stem(w) for w in _GENERIC_WORDS}


@dataclass(frozen=True)
class Clause:
    path: str
    quote: str  # complete original sentence(s), never cut
    text: str   # the clause assessed for polarity
    polarity: Literal["affirmed", "limited", "negative"]
    app_wide: bool = False

    @cached_property
    def terms(self) -> set[str]:
        # "Provides warnings without SMS" does not cover SMS.
        return terms(_WITHOUT.sub(" ", _fold(self.text)))

    @cached_property
    def content(self) -> set[str]:
        """Topic terms other than negation and delivery/availability wording."""
        return terms(_WITHOUT.sub(" ", self.topic)) - _GENERIC

    @cached_property
    def topic(self) -> str:
        """What the clause is about. Embeddings under-rate negated sentences, so
        "It does not forecast prices" is matched as "forecast prices"; its
        polarity is kept separately and decides the outcome."""
        return " ".join(_NEGATIVE.sub(" ", _fold(self.text)).split())


def _polarity(text: str) -> Literal["affirmed", "limited", "negative"]:
    folded = _fold(text)
    if re.search(r"(?:\bnot|n't)\s+(?:be\s+)?(?:require|need|necessary|depend)", folded):
        folded = _NO_PREREQUISITE.sub(" ", folded)
    if _NEGATIVE.search(folded):
        return "negative"
    return "limited" if _LIMITED.search(folded) else "affirmed"


def _app_wide(text: str, polarity: str, names: tuple[str, ...]) -> bool:
    folded = _fold(text).strip(" .!")
    subject = bool(_APP_SUBJECT.match(folded)) or any(folded.startswith(_fold(n) + " ") for n in names if n)
    named = set().union(*(terms(n) for n in names)) if names else set()
    content = terms(_NEGATIVE.sub(" ", folded)) - named
    return polarity != "affirmed" and subject and content <= _OPERATIONAL


def clauses(evidence: dict[str, str], names: tuple[str, ...] = ()) -> list[Clause]:
    """Whole sentences; contrastive parts keep their own polarity, same quote.

    References never cross a field: "Sends them via SMS" in a README does not
    refer to the description's warnings.
    """
    result = []
    for path, text in evidence.items():
        sentences = [s.strip() for s in _SENTENCE.split(text) if s and s.strip()]
        skipped = False
        for index, sentence in enumerate(sentences):
            refers = index > 0 and bool(_ANAPHORA.match(sentence) or _REFERENCE.search(sentence))
            # "Another App sends them via SMS" describes a different actor, and so
            # does a sentence referring back to one.
            if (_INSTRUCTION.search(sentence) or (refers and skipped) or len(terms(sentence)) == 0
                    or _OTHER_ACTOR.match(sentence) and not _CONTRAST.search(sentence) and ";" not in sentence):
                skipped = True
                continue
            skipped = False
            # "Those bids are then combined ..." is quoted with the sentence it refers to.
            quote = f"{sentences[index - 1]} {sentence}" if refers else sentence
            following = sentences[index + 1] if index + 1 < len(sentences) else ""
            qualifier = following if _ANAPHORA.match(following) and _polarity(following) != "affirmed" else ""
            if qualifier:
                quote = f"{quote} {qualifier}"
            if refers:
                # The referring sentence's own polarity applies to the combined statement.
                polarity = _polarity(sentence)
                if qualifier and polarity == "affirmed":
                    polarity = _polarity(qualifier)
                result.append(Clause(path, quote, f"{sentences[index - 1]} {sentence}", polarity))
            # "Although the pilot only includes 2 sensors, the system handles more": the
            # conceded part is context, not a statement about the App's capability.
            concession = re.match(r"(?:although|though|while)\s+[^,]+,\s*(.+)$", sentence, re.I)
            parts = [concession[1]] if concession else [
                part for piece in sentence.split(";") for part in _CONTRAST.split(piece.strip())]
            parts = [piece for part in parts if not _OTHER_ACTOR.match(part) for piece in _predicates(part)]
            for part in (p for p in parts if p and terms(p)):
                polarity = _polarity(part)
                if qualifier and polarity == "affirmed":
                    polarity = _polarity(qualifier)
                wide = not (refers and _ANAPHORA.match(sentence)) and _app_wide(part, polarity, names)
                result.append(Clause(path, quote, part, polarity, wide))
    return result


def _predicates(text: str) -> list[str]:
    """A sentence plus its coordinated predicates ("aggregates X and submits Y")."""
    pieces = re.split(r",?\s+and\s+(?=[a-z]+s\s)", text)
    if len(pieces) > 1 and all(len(terms(piece)) >= 3 for piece in pieces):
        return [text, *pieces]
    return [text]


def requirements(query: str) -> list[str]:
    """The functions requested; situation sentences are context, not requirements."""
    sentences = [s.strip(" .!?") for s in re.split(r"(?<=[.!?])\s+", query.strip()) if s.strip(" .!?")]
    needs = [s for s in sentences if _NEED.search(s) or not _SITUATION.search(s)] or sentences
    parts = []
    for sentence in needs:
        sentence = _SCAFFOLD.sub("", sentence, count=1).strip()
        sentence = _EXCLUSION.split(sentence, maxsplit=1)[0].strip()
        sentence = _LEAD.sub("", sentence, count=1).strip()
        pieces = _SPLIT.split(sentence)
        first = len(parts)
        for separator, piece in zip(["", *pieces[1::2]], pieces[::2], strict=True):
            piece = _LEAD.sub("", piece.strip(" ,."), count=1)
            if not piece:
                continue
            # A coordinated noun ("vocabularies and mappings") or a modifier
            # ("with partners") is not a separate function; keep it attached.
            if len(parts) > first and (len(terms(piece)) < 2 or len(terms(parts[-1])) < 2) and not _NUMBER.search(piece):
                parts[-1] = f"{parts[-1]} {separator.strip()} {piece}".replace(" , ", ", ")
            else:
                parts.append(piece)
    # A lone leading fragment ("mqtt") still forms one requirement.
    return [p for p in parts if terms(p) or _NUMBER.search(p)] or ([query.strip()] if terms(query) else [])


@dataclass(frozen=True)
class Finding:
    requirement: str
    status: Status
    clause: Clause | None = None


def _remote_similarity(queries: list[str], passages: list[str]) -> list[list[float]] | None:
    """Pinned E5 similarities from Discovery; None keeps lexical-only matching."""
    global _unavailable_until
    url = os.getenv("DISCOVERY_RANKING_URL")
    if not url or time.monotonic() < _unavailable_until:
        return None
    try:
        response = _client.post(f"{url}/api/v2/evidence/similarity",
                                json={"queries": queries, "passages": passages})
        response.raise_for_status()
        scores = response.json()["scores"]
        if len(scores) != len(queries) or any(len(row) != len(passages) for row in scores):
            raise ValueError("Similarity shape mismatch")
        return scores
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        # Fail closed to lexical evidence for a short period, without per-call timeouts.
        logger.warning("Evidence similarity unavailable; using lexical evidence")
        _unavailable_until = time.monotonic() + 30
        return None


_client = httpx.Client(timeout=httpx.Timeout(5.0, connect=1.0), trust_env=False)
_unavailable_until = 0.0
_similarity: Callable[[list[str], list[str]], list[list[float]] | None] = _remote_similarity


def set_similarity(function: Callable[[list[str], list[str]], list[list[float]] | None]) -> None:
    """Replace the similarity backend (offline evaluation and tests)."""
    global _similarity
    _similarity = function


def _match(wanted: set[str], numbers: set[str], clause: Clause, dense: float | None,
           z: float | None, anchored: bool) -> float | None:
    """Match strength, or None when the clause does not address the requirement.

    E5 cosine scores sit in a narrow band, so a semantic match must either be
    very close in absolute terms or stand out from the other candidate sentences
    for this same requirement (z). Shared vocabulary lowers the bar. A match
    with little shared vocabulary must still be anchored in the App's own
    wording: an unrelated request ("a CRM for sales leads") otherwise finds
    its least unrelated sentence.
    """
    if numbers and not numbers <= set(_NUMBER.findall(clause.text)):
        return None  # "5000 bids per second" needs that number in the source
    coverage = len(wanted & clause.terms) / len(wanted) if wanted else 0.0
    full = coverage == 1.0 and len(clause.text.split()) > 1
    if dense is None:
        stated_absence = clause.polarity == "negative" and coverage >= .5
        return coverage if full or stated_absence or (len(wanted) >= 3 and coverage >= .75) else None
    # An explicit limitation only ever withholds support, so the same bar as
    # the gap check below suffices to recognize it.
    if clause.polarity == "negative" and coverage >= .5 and dense >= GAP_MATCH:
        return dense + .05 * coverage
    if len(clause.text.split()) <= TITLE_WORDS and coverage < .5:
        return None  # short titles score high with E5 regardless of meaning
    if full or (coverage >= .5 and z is not None and z >= Z_WITH_TERMS):
        return dense + .05 * coverage
    if anchored and (dense >= DENSE_MATCH or (z is not None and z >= Z_MATCH and dense >= STANDOUT_FLOOR)):
        return dense + .05 * coverage
    return None


def _assess(requirement: str, query: str, candidates: list[tuple[Clause, float | None, float | None]],
            ) -> Finding:
    wanted, numbers = terms(requirement), set(_NUMBER.findall(requirement))
    affirmed_terms = set().union(*(c.terms for c, _, _ in candidates if c.polarity != "negative"))
    anchored = bool(wanted & affirmed_terms)
    scored = sorted(((strength, clause) for clause, dense, z in candidates
                     if (strength := _match(wanted, numbers, clause, dense, z, anchored)) is not None),
                    key=lambda pair: pair[0], reverse=True)
    if not scored:
        return Finding(requirement, "not_documented")
    best = scored[0][1]
    if _NEGATIVE.search(_fold(requirement)):
        # "Must not need a cloud account" is met only by an explicit absence.
        return Finding(requirement, "documented" if best.polarity == "negative" else "not_documented",
                       best if best.polarity == "negative" else None)
    affirmed = [(s, c) for s, c in scored if c.polarity == "affirmed" or _requested_limitation(query, c)]
    reference = affirmed[0][0] if affirmed else float("-inf")
    # An explicit limitation on the same matter wins a tie with an affirmation.
    for polarity, status in (("negative", "excluded"), ("limited", "limited")):
        stated = next(((s, c) for s, c in scored if c.polarity == polarity and (s, c) not in affirmed), None)
        if stated and stated[0] >= reference - TIE:
            return Finding(requirement, status, stated[1])
    # Quote a complete descriptive sentence rather than a short title when both match.
    _, clause = max((pair for pair in affirmed if pair[0] >= affirmed[0][0] - .03),
                    key=lambda pair: (len(pair[1].quote.split()) >= 6, pair[0]))
    # Limitations stated elsewhere still apply when they concern this request.
    restriction = next((c for c, _, _ in candidates if c.app_wide), None)
    if restriction:
        return Finding(requirement, "limited", restriction)
    for other, _, _ in candidates:
        if other.polarity != "affirmed" and not _requested_limitation(query, other) and _applies(other, wanted):
            return Finding(requirement, "excluded" if other.polarity == "negative" else "limited", other)
    # "Forecasts consumption" covers forecasting; "does not forecast prices"
    # then excludes the price part the affirmative sentences leave uncovered.
    gap = wanted - affirmed_terms  # requested, but affirmed nowhere in this App's sources
    supporting = next(d for c, d, _ in candidates if c is clause)
    for other, dense, _ in candidates:
        if other.polarity != "negative" or not gap & other.terms:
            continue
        relevant = (len(wanted & other.terms) / len(wanted) >= .5 if dense is None or supporting is None
                    else dense >= GAP_MATCH and dense >= supporting - GAP_MARGIN)
        if relevant:
            return Finding(requirement, "excluded", other)
    return Finding(requirement, "documented", clause)


def assess_pool(query: str, evidences: list[dict[str, str]],
                names: list[tuple[str, ...]] | None = None) -> list[list[Finding]]:
    """Findings per requirement for each App, judged against the whole candidate pool."""
    needed = requirements(query)
    if not needed:
        return [[] for _ in evidences]
    per_app = [clauses(evidence, (names or [()] * len(evidences))[i]) for i, evidence in enumerate(evidences)]
    passages = list(dict.fromkeys(c.topic for found in per_app for c in found))
    # A single requirement is the whole request, including its situation context.
    texts = [_EXCLUSION.split(query.strip(), maxsplit=1)[0]] if len(needed) == 1 else needed
    scores = _similarity(texts, passages) if passages else None
    column = {text: i for i, text in enumerate(passages)}
    stats = []
    for row in scores if scores is not None else []:
        # Relative standing needs enough comparison sentences to be meaningful.
        mean = sum(row) / len(row)
        std = (sum((v - mean) ** 2 for v in row) / len(row)) ** .5
        stats.append((mean, std) if len(row) >= MIN_COMPARISON and std > 0 else None)
    findings = []
    for found in per_app:
        result = []
        for index, requirement in enumerate(needed):
            candidates = []
            for clause in found:
                dense = None if scores is None else float(scores[index][column[clause.topic]])
                z = (dense - stats[index][0]) / stats[index][1] if dense is not None and stats[index] else None
                candidates.append((clause, dense, z))
            result.append(_assess(requirement, query, candidates))
        findings.append(result)
    return findings


def _applies(limitation: Clause, wanted: set[str]) -> bool:
    """Whether a limitation concerns what was requested.

    "SMS delivery is disabled" limits "earthquake warnings via SMS"; "Water
    readings via SMS are disabled" does not. "Earthquake warnings are only
    available via MQTT" restricts a requested feature to something not requested.
    """
    content = limitation.content
    if not content:
        return bool(limitation.terms & {_stem(w) for w in ("delivery", "channel")})
    if content <= wanted:
        return True
    scope = _ONLY_SCOPE.search(_fold(limitation.text))
    subject = content - terms(scope[1]) if scope else set()
    return bool(subject) and subject <= wanted


def _requested_limitation(query: str, clause: Clause) -> bool:
    """"Only in simulation" or "only via SMS" documents the function when that is what is asked."""
    if clause.polarity != "limited":
        return False
    folded = _fold(clause.text)
    scope = _ONLY_SCOPE.search(folded)
    restricted = (terms(scope[1]) if scope else set()) | _environment(folded)
    if not restricted or not restricted <= terms(query):
        return False
    remainder = _ENVIRONMENT.sub(" ", _ONLY_SCOPE.sub(" ", folded))
    return not _LIMITED.search(re.sub(r"\bonly\b", " ", remainder))


def _environment(text: str) -> set[str]:
    return terms(" ".join(m[0] for m in _ENVIRONMENT.finditer(_fold(text))))
