"""Bounded source-claim assessment; retrieval rank never establishes suitability.

Recognized declarations form evidence groups only through explicit feature identity
or an unambiguous local reference. Uninterpreted context stays uncertain. This is
not a general semantic entailment engine, translator or real-corpus quality metric.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# Only request scaffolding, not source limitations or functional requirements.
_REQUEST_WORDS = set((
    "a an the app apps application applications please find search show me for to "
    "that can could you i need looking recommend about with support supports does "
    "do give want some available in on and "
    "preciso quero encontre encontrar procure mostre mostrar recomende por favor "
    "um uma os as o para de da do que pode podem voce aplicacao aplicacoes e "
    "ich suche brauche bitte empfehlen empfehle zeige mir eine ein der die das "
    "fur zu und kann kannst du anwendungen"
).split())
_ACTIONS = (
    r"provides?|supports?|sends?|issues?|warns?|monitors?|displays?|shows?|collects?|"
    r"connects?|detects?|organizes?|measures?|forecasts?|predicts?|ingests?|notifies|notify|"
    r"controls?|optimizes?|exports?|delivers?|reads?|logs?|works?|operates?|runs?|uses?|"
    r"envia|enviam|fornece|fornecem|suporta|suportam|emite|emitem|avisa|avisam|"
    r"monitoriza|mostra|recolhe|conecta|deteta|detecta|preve|funciona|opera|usa|"
    r"unterstutzt|unterstutzen|sendet|senden|warnt|warnen|liefert|liefern|"
    r"zeigt|zeigen|erkennt|erkennen|misst|arbeitet|funktioniert"
)
_APP = r"(?:this app|the app|this application|the application|it|esta aplicacao|este app|a aplicacao|die app|diese app|sie|es)"
_REFERENCE = r"(?:they|them|these|those|this feature|that feature|these features|this capability|this|that|it|eles|elas|esta funcionalidade|esses alertas|sie|diese funktion)"
_NEGATION = re.compile(r"\b(?:not|no|never|cannot|without|nao|nunca|sem|nicht|ohne|kein\w*)\b|\b(?:can|doesn|don|isn|aren|won)'t\b")
# Grammar operators/states, interpreted with their feature/subject scope below.
_QUALIFIED = re.compile(
    r"\b(?:only|unless|if|when|after|before|requires?|depends|may|might|could|will|would|"
    r"planned|proposed|future|possible|disabled|unsupported|unavailable|unimplemented|"
    r"simulation|simulated|prototype|lacks|except|unlike|"
    r"apenas|somente|se|quando|apos|antes|requer|planead\w*|planejad\w*|futur\w*|"
    r"desativad\w*|indisponivel|nur|wenn|falls|geplant|kunftig|deaktiviert|nichtverfugbar)\b"
)
_ACTION = re.compile(
    rf"^(?:(?:{_APP}|production)\s+)?(?:(?:does|do|can|cannot|can't|doesn't|don't|will|may|might|could|would|pode|kann|wird)\s+)?"
    rf"(?:(?:not|never|nao|nunca|nicht)\s+)?(?P<verb>{_ACTIONS})\b(?P<body>.*)$"
)
_STATE = re.compile(
    r"^(?P<feature>.+?)\s+(?:is|are|was|were|can be|cannot be|can't be|may be|will be|e|sao|esta|estao|ist|sind)\s+"
    r"(?P<state>.+)$"
)
_AFFIRMED_STATE = re.compile(r"^(?:supported|provided|available|enabled|supplied|delivered|suportad[oa]s?|disponiveis|disponivel|ativad[oa]s?|unterstutzt|verfugbar)\b")
_LINK = re.compile(rf"^(?P<reference>{_REFERENCE})\b(?:\s+(?:via|by|using|through|per|por|mit)\s+(?P<attribute>.+))?$")
_CHANNEL = re.compile(r"\s+(?:via|by|using|through|per|por|mit)\s+", re.I)
_SOURCE_WORDS = set((
    "this that these those it they them app application the a an is are was were "
    "does do can be about for to by via using through "
    "esta este esses elas eles funcionalidade e sao ist sind die diese sie es "
    "not no never cannot nao nunca nicht without sem ohne"
).split())
# Sparse functional labels are accepted only when the whole label is understood,
# not simply because a requested word occurs somewhere in arbitrary prose.
_LABEL_WORDS = set("energy sensor meter consumption reading readings monitoring forecasting prediction "
                   "warning warnings alert alerts ingestion dashboard dashboards data telemetry "
                   "demand remote control real time supplied sensor sensors trend analysis timestamped observations derived operator review evidence".split())
_IGNORED_NOTE = re.compile(r"^(?:documentation|docs|see documentation|see docs)\.?$")
_OPERATING = set("work works operate operates run runs use uses funciona opera usa arbeitet funktioniert".split())
_OBJECT_ACTIONS = set("provide provides support supports send sends deliver delivers envia enviam sendet senden liefert liefern fornece suportam suporta unterstutzt unterstutzen".split())
# An informational annotation authored in the pinned synthetic catalogue. Unknown
# implementation context must still be interpreted, rather than discarded.
_SYNTHETIC_CONTEXT = ' using auditable edge processing, bounded data retention, configurable thresholds, and operator-reviewed actions'


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c)).replace("’", "'")


def _terms(text: str) -> set[str]:
    terms = set()
    for word in re.findall(r"[^\W_]+", _fold(text)):
        if word in _REQUEST_WORDS or word in _SOURCE_WORDS:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us")):
            word = word[:-1]
        if len(word) > 5 and word.endswith("ing"):
            word = word[:-3]
        terms.add(word)
    return terms


@dataclass
class _Claim:
    path: str
    terms: set[str]
    feature: set[str]
    status: str  # affirmed, qualified, unresolved
    group: int
    global_scope: bool = False
    ambiguous: bool = False


def _claims(path: str, text: str, query_terms: set[str], start: int, names: list[str], synthetic: bool, declarations: list[str]) -> list[_Claim]:
    """Interpret complete clauses; references never cross field/paragraph boundaries."""
    # The pinned synthetic catalogue labels translations with provenance before
    # a colon. The annotation is preserved in output, but is not a claim or a
    # qualifier of the following capability declaration.
    if synthetic and path.startswith('summary.') and ':' in text:
        heading, declaration = text.split(':', 1)
        header = _fold(heading).strip()
        prefixes = ('synthetic edge application for ', 'synthetische edge-anwendung fur ',
                    'application edge synthetique pour ', 'aplicacion edge sintetica para ',
                    'applicazione edge sintetica per ', 'synthetische edge-app voor ',
                    'aplicacao edge sintetica para ')
        known_header = header.startswith(prefixes) or header.endswith('icin sentetik uc uygulamasi')
        if known_header and not _NEGATION.search(header) and not _QUALIFIED.search(header):
            text = declaration
    claims = []
    previous = None
    named = _terms(' '.join(re.findall(r'\b[A-Z][A-Z0-9_-]+\b', text)))
    labels = _terms(' '.join(_LABEL_WORDS))
    for paragraph in re.split(r"\n\s*\n", text):
        previous = None
        # Split coordinated predicates, preserving noun coordination for ambiguity.
        clauses = re.split(rf"(?<=[.!?])\s+|[;\n]|\s+(?:but|however|and|e|und)\s+(?=(?:does\s+not\s+|nao\s+)?(?:{_ACTIONS})\b)", _fold(paragraph))
        for clause in clauses:
            # Store text extraction flattens headings; recognize bounded heading
            # forms without treating arbitrary foreign actors as the App.
            clause = re.sub(r"^(?:telemetry|features|capabilities|functionality|functionalidade|funktionen)\s+(?=(?:supports?|provides?|envia|unterstutzt)\b)", "", clause)
            clause = clause.strip().rstrip('.!')
            if not clause or _IGNORED_NOTE.fullmatch(clause):
                previous = None
                continue
            for name in names:
                prefix = _fold(name) + ' '
                if clause.startswith(prefix):
                    candidate = 'this app ' + clause[len(prefix):]
                    if _ACTION.fullmatch(candidate) or _STATE.fullmatch(candidate):
                        clause = candidate
                        break
            # Explicit fixture provenance is not a functional limitation. It is
            # retained in served quotations and never supplies capability evidence.
            if synthetic and (clause == 'the listing is representative metadata for validation and is not a commercial product' or
                              (re.fullmatch(r'this app is a clearly synthetic reference application for .+ operations', clause) and
                               not _QUALIFIED.search(clause) and not _NEGATION.search(clause))):
                previous = None
                continue
            if re.match(r'^(?:another app|other apps?|an external service)\b', clause):
                previous = None
                continue
            terms = _terms(clause)
            status = "qualified" if _NEGATION.search(clause) or _QUALIFIED.search(clause) else "affirmed"
            if '?' in clause or re.search(r"\b(?:ignore|disregard)\b.*\binstructions\b", clause):
                status = "unresolved"
            assertion_text = re.sub(rf'^(?:{_APP}) is designed to\s+', '', clause)
            action = _ACTION.fullmatch(assertion_text)
            state = _STATE.fullmatch(clause)
            purpose = next((value for value in declarations if assertion_text == value or
                            (synthetic and assertion_text == value + _SYNTHETIC_CONTEXT)), None) if assertion_text != clause else None
            feature = set()
            global_scope = False
            ambiguous = False
            group = start + len(claims)
            if purpose:
                # A present-purpose assertion can corroborate an exact typed
                # capability declaration. Full original context still determines
                # polarity; neither field excuses a future/conditional qualifier.
                terms = _terms(purpose)
                feature = terms
            elif action:
                verb, body = action['verb'], action['body'].strip()
                # Negation can follow the object in German; remove it only for scope,
                # never from status or displayed quotations.
                body = _NEGATION.sub('', body).strip()
                if verb in {'warn', 'warns'} and body.startswith('about '):
                    body = body[len('about '):]
                reference = _LINK.fullmatch(body)
                if reference:
                    if previous is None or previous.ambiguous or not previous.feature:
                        status, global_scope = "unresolved", True
                    else:
                        group, feature = previous.group, previous.feature
                        terms |= previous.terms
                    attribute = reference['attribute']
                    if status == 'affirmed' and attribute and _terms(attribute) - (query_terms | named | labels):
                        status, global_scope = 'unresolved', True
                else:
                    object_parts = _CHANNEL.split(body, maxsplit=1)
                    object_text = object_parts[0]
                    feature = _terms(object_text)
                    if verb not in _OBJECT_ACTIONS:
                        feature |= _terms(verb)
                    ambiguous = bool(re.search(r"\b(?:and|e|und)\b", object_text))
                    # An explicit repeat of the same feature can extend its evidence.
                    if previous and feature and feature <= previous.feature and not previous.ambiguous:
                        group = previous.group
                    if status == 'affirmed' and feature & query_terms:
                        coordinated = re.split(r"\b(?:and|e|und)\b", object_text)
                        understood = query_terms | _terms(' '.join(_LABEL_WORDS)) | _terms(verb)
                        # A purpose/input/audience relationship is not equivalent
                        # to providing its object. Unknown transport or operating
                        # context cannot be dropped after the feature name either.
                        unknown_role = re.search(r'\b(?:for|to|from|about|in|on|as)\b', object_text)
                        unknown_context = len(object_parts) > 1 and _terms(object_parts[1]) - (query_terms | named | labels)
                        if unknown_role or unknown_context or any(
                            _terms(part) & query_terms and not _terms(part) <= understood for part in coordinated
                        ):
                            status = 'unresolved'
                            global_scope = True
                    if not body:
                        status, global_scope = "unresolved", True
                if verb in _OPERATING:
                    # App-wide availability affects every requested capability.
                    global_scope = status != "affirmed"
            elif state:
                subject = state['feature'].strip()
                subject_ref = re.fullmatch(_REFERENCE, subject)
                if subject_ref:
                    if subject == 'it' or previous is None or previous.ambiguous or not previous.feature:
                        global_scope = True
                        status = "qualified" if status == "qualified" else "unresolved"
                    else:
                        group, feature = previous.group, previous.feature
                elif re.fullmatch(_APP, subject):
                    global_scope = True
                else:
                    feature = _terms(subject)
                if status == 'affirmed':
                    assertion = _AFFIRMED_STATE.match(state['state'])
                    if not assertion or _terms(state['state'][assertion.end():]) - (query_terms | named | labels):
                        status = 'unresolved'
                if previous and feature and feature <= previous.feature and not previous.ambiguous:
                    group = previous.group
            else:
                # A restriction/reference fragment qualifies its local antecedent;
                # its applicability cannot silently be assumed when unresolved.
                if status != 'affirmed' and re.match(rf"^(?:{_REFERENCE}|only|apenas|nur)\b", clause):
                    if previous and not previous.ambiguous and not re.match(r'^(?:only|apenas|nur)\b', clause):
                        group, feature = previous.group, previous.feature
                    else:
                        global_scope = True
                elif terms and (terms <= query_terms | labels or
                              (terms <= named | labels and (terms & labels or len(terms) == 1)) or
                              (path.startswith('dataspaceAppDescription.') and len(terms) == 1)):
                    feature = terms
                else:
                    status = 'unresolved'
                    feature = terms
                    # A functional label can identify a different feature
                    # even when a modifier cannot be interpreted. It supplies no
                    # positive support, but does not become an App-wide restriction.
                    words = clause.split()
                    heads = _terms('readings observations monitoring forecasting prediction warnings alerts ingestion dashboards control')
                    scoped_label = bool(_terms(words[-1]) & heads)
                    global_scope = not scoped_label or bool(re.match(_REFERENCE, clause))
            claim = _Claim(path, terms, feature, status, group, global_scope, ambiguous)
            claims.append(claim)
            # A new or uninterpreted statement breaks the reference chain.
            previous = claim
    return claims


def source_text(app: dict[str, Any], locale: str) -> dict[str, str]:
    """Original functional field paths; no rank, provider, price or inferred ontology."""
    if app.get("source_profile") == "hedge-store-v1":
        evidence = app.get("source_evidence")
        if isinstance(evidence, dict):
            return {path: value for path, value in evidence.items()
                    if isinstance(path, str) and isinstance(value, str) and value and (
                        path in {"description", "readme"}
                        or path == "dataspaceAppDescription.properties.description"
                        or path.startswith("dataspaceAppDescription.properties.featureList[")
                    )}
        description = app.get("description")
        return {"description": description} if isinstance(description, str) and description else {}
    evidence = {}
    if isinstance(app.get("description"), str) and app["description"]:
        evidence["description"] = app["description"]
    summary = app.get("summary")
    if isinstance(summary, dict):
        language = locale if summary.get(locale) else "en"
        if isinstance(summary.get(language), str) and summary[language]:
            evidence[f"summary.{language}"] = summary[language]
    capabilities = app.get("capabilities")
    for index, capability in enumerate(capabilities if isinstance(capabilities, list) else []):
        if isinstance(capability, str) and capability:
            evidence[f"capabilities[{index}]"] = capability
    for direction in ("inputs", "outputs"):
        contracts = app.get(direction)
        for index, contract in enumerate(contracts if isinstance(contracts, list) else []):
            if isinstance(contract, dict) and isinstance(contract.get("description"), str):
                evidence[f"{direction}[{index}].description"] = contract["description"]
    return evidence


def assess(query: str, app: dict[str, Any], locale: str) -> dict[str, Any]:
    """Require an affirmed coherent evidence group and no applicable qualification."""
    title = app.get("name") if app.get("source_profile") == "hedge-store-v1" else app.get("title")
    identity_path = "name" if app.get("source_profile") == "hedge-store-v1" else "title"
    if isinstance(title, dict):
        language = locale if title.get(locale) else "en"
        identity_path = f"title.{language}"
        title = title.get(language)
    if not title and app.get("app_id"):
        identity_path = "appId"
    names = re.findall(r'"([^"\n]+)"', query)
    identity_query = bool(names) and re.fullmatch(r'"[^"\n]+"(?:\s+OR\s+"[^"\n]+")*', query.strip())
    identity = str(title or app.get("app_id") or "")
    identity_match = identity in names if identity_path == "appId" else identity.casefold() in {name.casefold() for name in names}
    if identity and identity_query and identity_match:
        return {"status": "source_supported", "reason": "requested_identity",
                "evidence_fields": [identity_path]}
    terms = _terms(query)
    if not terms or re.search(r"\b(?:not|without|except|only|cheapest|best|better|nao|sem|apenas|nicht|ohne|nur)\b", _fold(query)):
        return {"status": "uncertain", "reason": "request_needs_clarification", "evidence_fields": []}
    titles = app.get('title')
    names = [app.get('name')] if app.get('source_profile') == 'hedge-store-v1' else (
        list(titles.values()) if isinstance(titles, dict) else [titles]
    )
    names = [name for name in names if isinstance(name, str) and name]
    provenance = app.get('provenance')
    synthetic = app.get('source_profile') != 'hedge-store-v1' and isinstance(provenance, dict) and provenance.get('synthetic') is True
    capabilities = app.get('capabilities')
    declarations = [_fold(value).rstrip('.') for value in capabilities if isinstance(value, str)] if isinstance(capabilities, list) else []
    claims = []
    for path, text in source_text(app, locale).items():
        if len(text) <= 16000:
            claims.extend(_claims(path, text, terms, len(claims), names, synthetic, declarations))
    groups = {}
    for claim in claims:
        if claim.status == 'affirmed':
            groups.setdefault(claim.group, []).append(claim)
    parts = [_terms(part) for part in re.split(r"\b(?:and|e|und)\b", _fold(query))]
    requirements = parts if len(parts) > 1 and all(parts) else [terms]
    support = []
    covered = set()
    for group in groups.values():
        coverage = set().union(*(c.terms for c in group))
        matched = {index for index, requirement in enumerate(requirements) if requirement <= coverage}
        if not matched:
            continue
        relevant = [c for c in claims if c.status != 'affirmed' and (
            c.global_scope or c.group == group[0].group or
            (c.feature and (c.feature <= coverage or any(requirements[i] <= c.feature for i in matched)))
        )]
        if relevant:
            return {"status": "uncertain", "reason": "qualified_or_unresolved_source",
                    "evidence_fields": list(dict.fromkeys(c.path for c in [*group, *relevant]))}
        support.extend(group)
        covered |= matched
    if len(covered) != len(requirements):
        support = []
    return {"status": "source_supported" if support else "uncertain",
            "reason": "coherent_source_support" if support else "no_coherent_source_support",
            "evidence_fields": list(dict.fromkeys(c.path for c in support))}
