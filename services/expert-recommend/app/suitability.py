"""Bounded source-claim assessment; retrieval rank never establishes suitability.

Each assertion retains its feature owner, attributes, qualification and source span.
Only the same feature or an unambiguous local reference can compose evidence.
Uninterpreted context stays uncertain. This is not a general semantic entailment
engine, translator or real-corpus quality metric.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from hedge_shared.store_knowledge import explanation

# Only request scaffolding, not source limitations or functional requirements.
_REQUEST_WORDS = set((
    "a an the app apps application applications please find search show me for to "
    "that can could you i need looking recommend about with support supports does which "
    "do give want some available in on and "
    "we us our would help useful here there something anything please software tool "
    "choose pick option use have trying "
    "teams team partners partner agree same could any what how more me way different "
    "preciso quero encontre encontrar procure mostre mostrar recomende por favor "
    "um uma os as o para de da do que pode podem voce aplicacao aplicacoes e "
    "ich suche brauche bitte empfehlen empfehle zeige mir eine ein der die das "
    "fur zu und kann kannst du anwendungen"
).split())
_ACTIONS = (
    r"provides?|supports?|sends?|issues?|warns?|monitors?|displays?|shows?|collects?|"
    r"connects?|detects?|organizes?|measures?|forecasts?|predicts?|ingests?|notifies|notify|"
    r"controls?|optimizes?|exports?|delivers?|reads?|logs?|works?|operates?|runs?|uses?|publishes|publish|manages|manage|"
    r"envia|enviam|fornece|fornecem|suporta|suportam|emite|emitem|avisa|avisam|"
    r"monitoriza|mostra|recolhe|conecta|deteta|detecta|preve|funciona|opera|usa|"
    r"unterstutzt|unterstutzen|sendet|senden|warnt|warnen|liefert|liefern|"
    r"zeigt|zeigen|erkennt|erkennen|misst|arbeitet|funktioniert"
)
_APP = r"(?:this app|the app|this application|the application|it|esta aplicacao|este app|a aplicacao|die app|diese app|sie|es)"
_REFERENCE = r"(?:they|them|these|those|(?:this|that|the|these|those) (?:features?|capabilit(?:y|ies))|this|that|it|eles|elas|esta funcionalidade|esses alertas|sie|diese funktion)"
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
_AFFIRMED_STATE = re.compile(r"^(?:supported|provided|available|enabled|supplied|delivered|sent|suportad[oa]s?|disponiveis|disponivel|ativad[oa]s?|unterstutzt|verfugbar)\b")
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
                   "warning warnings alert alerts ingestion dashboard dashboards data telemetry shared model models mapping mappings "
                   "demand remote control real time supplied sensor sensors trend analysis timestamped observations derived operator review evidence".split())
_IGNORED_NOTE = re.compile(r"^(?:documentation|docs|see documentation|see docs)\.?$")
_OPERATING = set("work works operate operates run runs use uses funciona opera usa arbeitet funktioniert".split())
_OBJECT_ACTIONS = set("provide provides support supports send sends deliver delivers envia enviam sendet senden liefert liefern fornece suportam suporta unterstutzt unterstutzen".split())
# An informational annotation authored in the pinned synthetic catalogue. Unknown
# implementation context must still be interpreted, rather than discarded.
_SYNTHETIC_CONTEXT = ' using auditable edge processing, bounded data retention, configurable thresholds, and operator-reviewed actions'
_FOREIGN = r'(?:another app|other apps?|an external service)'
# Atomic assertions and coordinated feature names are supported. Other compound
# syntax must survive as uncertainty rather than disappear into a regex argument.
_COMPOUND = re.compile(r'[,(\[\])]|\b(?:but|however)\b')
_COORDINATION = re.compile(r'\b(?:and|e|und)\b')
_ENVIRONMENT = re.compile(r'\b(?:simulation|simulated|prototype|production)\b')
_EXCLUSIVE = re.compile(r'\b(?:only|apenas|somente|nur)\b')
_PROHIBITION = re.compile(r'\b(?:disabled|unsupported|unavailable|unimplemented|lacks|desativad\w*|indisponivel|deaktiviert|nichtverfugbar)\b')
_Kind = Literal['affirmation', 'prohibition', 'exclusive', 'environment',
                'condition', 'prerequisite', 'no_prerequisite', 'unresolved']
_Scope = Literal['feature', 'channel', 'unresolved']


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c)).replace("’", "'")


def _terms(text: str) -> set[str]:
    terms = set()
    for word in re.findall(r"[^\W_]+", _fold(text)):
        word = {"publishes": "publish", "managing": "manage", "combining": "combine",
                "combined": "combine", "combines": "combine"}.get(word, word)
        if word in _REQUEST_WORDS or word in _SOURCE_WORDS:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us")):
            word = word[:-1]
        if len(word) > 5 and word.endswith("ing"):
            word = word[:-3]
        terms.add(word)
    return terms


_FEATURE_HEADS = _terms('readings observations monitoring forecasting prediction warnings alerts ingestion dashboards control')


@dataclass(frozen=True)
class _Claim:
    path: str
    span: str  # Complete original source sentence/segment, before normalization.
    # None means App-wide or unresolved scope, never positive capability evidence.
    feature: frozenset[str] | None
    attributes: frozenset[str]
    kind: _Kind
    scope: _Scope
    complete: bool = True

    @property
    def status(self) -> str:
        if not self.complete or self.kind == 'unresolved':
            return 'unresolved'
        return 'affirmed' if self.kind == 'affirmation' else 'qualified'


def _source_clauses(text: str) -> Iterator[tuple[str, str]]:
    """Keep original spans even when a supported action coordination is split."""
    for span in re.split(r'(?<=[.!?])\s+|[;\n]', text):
        # HTML extraction can flatten adjacent metadata paragraphs. Recognize
        # their explicit headings; retain the whole original span for evidence.
        segments = re.split(r"\s+(?=(?:deployed instance(?: \(|:)|documentation:|"
                            r"external service, accessible via its public url))", span, flags=re.I)
        for segment in segments:
            folded = _fold(segment)
            shared_object = re.fullmatch(
                rf"(?P<prefix>used to )?(?P<first>{_ACTIONS}) and (?P<second>{_ACTIONS}) (?P<body>.+)", folded)
            if shared_object:
                # Explicit coordinated predicates share their complete object,
                # including its restrictions. Never share objects across sentences.
                body = shared_object['body']
                yield span, (shared_object['prefix'] or '') + shared_object['first'] + ' ' + body
                yield span, shared_object['second'] + ' ' + body
                continue
            for clause in re.split(rf'\s+(?:but|however|and|e|und)\s+(?=(?:does\s+not\s+|nao\s+)?(?:{_ACTIONS})\b)', _fold(segment)):
                yield span, clause


def _qualification(clause: str, status: str, attributes: frozenset[str], *, channel_subject: bool,
                   delivery_predicate: bool) -> tuple[_Kind, _Scope]:
    """Kind and grammatical target are independent of incidental transport text."""
    scope: _Scope = 'channel' if channel_subject else 'feature'
    if status == 'unresolved':
        return 'unresolved', 'feature'  # lost/ambiguous attributes cannot narrow uncertainty
    if status == 'affirmed':
        return 'affirmation', scope
    negative = bool(_NEGATION.search(clause) or _PROHIBITION.search(clause))
    operators = [m[0] for m in _QUALIFIED.finditer(clause) if not _PROHIBITION.fullmatch(m[0])]
    if _ENVIRONMENT.search(clause):
        return 'environment', scope
    if _EXCLUSIVE.search(clause):
        # Exclusivity has feature-wide force. Mixed negation or additional
        # conditions cannot establish an unconditional allowed-channel set.
        if negative or any(not _EXCLUSIVE.fullmatch(op) for op in operators) or not attributes or channel_subject:
            return 'condition', scope
        return 'exclusive', 'feature'
    if operators:
        return 'condition', scope
    if negative:
        # A direct negative delivery assertion prohibits that channel; a
        # feature availability state does not acquire channel-local scope just
        # because its predicate also mentions a transport.
        return 'prohibition', 'channel' if attributes and delivery_predicate else scope
    return 'condition', scope


def _scope_text(text: str) -> str:
    """Identify the subject/value without treating qualification as its identity.

    Polarity is assessed on the complete original clause before this helper runs.
    """
    text = _NEGATION.sub('', text)
    operator = _QUALIFIED.search(text)
    return (text[:operator.start()] if operator else text).strip()


def _owners(text: str, previous: list[_Claim], *, subject: bool = False) -> list[frozenset[str] | None]:
    """One owner per declaration; coordination never becomes one merged feature."""
    if subject and text == 'it':
        return [None]
    if re.fullmatch(_REFERENCE, text):
        return [previous[0].feature] if len(previous) == 1 else [None]
    if re.fullmatch(_APP, text):
        return [None]
    owners = []
    for part in re.split(r'\s+(?:and|e|und)\s+|,\s*', text):
        feature = frozenset(_terms(_scope_text(part)))
        # A local noun-head repeat ("warnings") can refer to "earthquake
        # warnings". Arbitrary subset/sibling features cannot inherit attributes.
        if len(previous) == 1 and previous[0].feature and len(feature) == 1 and feature <= _FEATURE_HEADS and feature <= previous[0].feature:
            feature = previous[0].feature
        owners.append(feature or None)
    return owners


def _transport(text: str) -> tuple[str, frozenset[str]]:
    parts = _CHANNEL.split(text, maxsplit=1)
    return parts[0], frozenset(_terms(_scope_text(parts[1]))) if len(parts) > 1 else frozenset()


def _claims(path: str, text: str, query_terms: set[str], names: list[str], synthetic: bool, declarations: list[str]) -> list[_Claim]:
    """Extract owned assertions; references never cross field/paragraph boundaries."""
    # Preserve the pinned fixture's informational annotations in output, without
    # making them functional assertions. This does not waive unknown context.
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
    named = _terms(' '.join(re.findall(r'\b[A-Z][A-Z0-9_-]+\b', text)))
    labels = _terms(' '.join(_LABEL_WORDS))
    for paragraph in re.split(r"\n\s*\n", text):
        previous = []
        purpose_context = False
        for span, clause in _source_clauses(paragraph):
            clause = re.sub(r"^(?:telemetry|features|capabilities|functionality|functionalidade|funktionen)\s+(?=(?:supports?|provides?|envia|unterstutzt)\b)", "", clause)
            clause = clause.strip().rstrip('.!')
            if not clause or _IGNORED_NOTE.fullmatch(clause):
                previous = []
                continue
            # README provenance is not a functional predicate or an App-wide
            # restriction. Recognize only complete bounded metadata forms;
            # negation/qualifications/instructions still require assessment.
            provenance = clause
            for name in names:
                if provenance.startswith(_fold(name) + ' '):
                    provenance = provenance[len(_fold(name)) + 1:]
                    break
            if (not _NEGATION.search(provenance) and not _QUALIFIED.search(provenance)
                    and not re.search(r"\b(?:ignore|disregard)\b", provenance)
                    and re.fullmatch(
                        r"(?:developed and operated by [\w -]{1,100}|"
                        r"(?:deployed instance(?: \([^()]{1,100}\))?|documentation): https?://\S+|"
                        r"vocabulary hub of [\w .-]{1,100} data space)", provenance)):
                purpose_context = provenance.startswith('vocabulary hub of ')
                previous = []
                continue
            # A short acronym label is not a predicate about every capability.
            # Keep its uncertainty on the labelled topic (e.g. "SMS demo app"
            # still prevents confirming production SMS), rather than discarding it.
            if path == 'description' and re.fullmatch(r"[A-Z][A-Z0-9_-]{1,12} demo app[.!]?", span):
                claims.append(_Claim(path, span, frozenset(_terms(span)), frozenset(),
                                     'unresolved', 'feature'))
                previous = []
                continue
            if re.fullmatch(r"no container image in the appstore registry", provenance):
                claims.append(_Claim(path, span, frozenset(_terms('container image registry deployment')),
                                     frozenset(), 'prohibition', 'feature'))
                previous = []
                continue
            if provenance == 'external service, accessible via its public url':
                claims.append(_Claim(path, span, frozenset(_terms('external service deployment offline')),
                                     frozenset(), 'condition', 'feature'))
                previous = []
                continue
            for name in names:
                prefix = _fold(name) + ' '
                if clause.startswith(prefix):
                    candidate = 'this app ' + clause[len(prefix):]
                    if _ACTION.fullmatch(candidate) or _STATE.fullmatch(candidate):
                        clause = candidate
                        break
            if synthetic and (clause == 'the listing is representative metadata for validation and is not a commercial product' or
                              (re.fullmatch(r'this app is a clearly synthetic reference application for .+ operations', clause) and
                               not _QUALIFIED.search(clause) and not _NEGATION.search(clause))):
                previous = []
                continue
            status = 'qualified' if _NEGATION.search(clause) or _QUALIFIED.search(clause) else 'affirmed'
            if '?' in clause or re.search(r"\b(?:ignore|disregard)\b.*\binstructions\b", clause):
                status = 'unresolved'
            assertion_text = re.sub(rf'^(?:{_APP}) is (?:designed|used) to\s+', '', clause)
            if purpose_context and assertion_text.startswith('used to '):
                assertion_text = assertion_text[len('used to '):]
                purpose_context = False
            action = _ACTION.fullmatch(assertion_text)
            state = _STATE.fullmatch(clause)
            purpose = next((value for value in declarations if assertion_text == value or
                            (synthetic and assertion_text == value + _SYNTHETIC_CONTEXT)), None) if assertion_text != clause else None
            dependency = re.fullmatch(r"(?P<target>.+?)\s+(?:(?P<negated>(?:does|do) not|doesn't|don't)\s+)?(?:requires?|depends? on)\s+(?P<argument>.+)", clause)
            prerequisite = re.fullmatch(r'(?P<negated>not\s+)?(?:required|needed|necessary)(?:\s+for\s+(?P<target>.+))?', state['state']) if state else None
            # A full regex match is not proof that its arbitrary argument was
            # interpreted. Only the existing simple external-actor arguments
            # have a complete dependency interpretation; other arguments or
            # compound tails remain uncertainty, including negated prerequisites.
            complete = not _COMPOUND.search(clause) or bool(purpose)
            if not (action or state or dependency or prerequisite) and not _NEGATION.search(clause) and not _QUALIFIED.search(clause):
                # Commas can coordinate fully understood functional labels, but
                # cannot conceal another predicate inside an ignored argument.
                complete = complete or (not _COMPOUND.search(clause.replace(',', '')) and
                                        _terms(clause) <= query_terms | named | labels)
            if dependency:
                complete = complete and bool(re.fullmatch(_FOREIGN, dependency['argument']))
            elif prerequisite:
                target = prerequisite['target'] or ''
                complete = complete and bool(re.fullmatch(_FOREIGN, state['feature'])) and not (
                    _COORDINATION.search(target) or _QUALIFIED.search(target) or _NEGATION.search(target) or ':' in target
                )
            if action and len(_CHANNEL.split(action['body'])) > 2:
                complete = False
            if state and (len(_CHANNEL.split(state['feature'])) > 2 or len(_CHANNEL.split(state['state'])) > 2):
                complete = False
            if not complete:
                previous = [_Claim(path, span, None, frozenset(), 'unresolved', 'unresolved', False)]
                claims.extend(previous)
                continue
            attributes = frozenset()
            channel_subject = False
            delivery_predicate = False
            dependency_kind: _Kind | None = None
            if dependency or prerequisite:
                # The dependency is an argument, not the feature's actor. A
                # missing/ambiguous target qualifies the App rather than vanishing.
                absent = (prerequisite and prerequisite['negated']) or (dependency and dependency['negated'])
                target = dependency['target'] if dependency else prerequisite['target']
                owner_text, attributes = _transport(target) if target else ('', frozenset())
                owners = _owners(owner_text, previous) if owner_text else [None]
                if owner_text and not re.fullmatch(_REFERENCE, owner_text) and not _terms(owner_text) & (query_terms | named | labels):
                    owners = [None]
                status = 'qualified'
                dependency_kind = 'no_prerequisite' if absent else 'prerequisite'
                channel_subject = bool(attributes)
            elif purpose:
                owners = _owners(purpose, previous)
            elif action:
                verb, body = action['verb'], _NEGATION.sub('', action['body']).strip()
                delivery_predicate = True
                if verb in {'warn', 'warns'} and body.startswith('about '):
                    body = body[len('about '):]
                owner_text, attributes = _transport(body)
                if verb not in _OBJECT_ACTIONS and not re.fullmatch(_REFERENCE, owner_text):
                    owner_text = verb + ' ' + owner_text
                owners = _owners(owner_text, previous)
                if verb in _OPERATING:
                    owners = [None]
                elif status == 'affirmed' and any(owner and owner & query_terms for owner in owners):
                    understood = query_terms | labels | _terms(verb)
                    if re.search(r'\b(?:for|to|from|about|in|on|as|with)\b', owner_text) or any(
                        owner and owner & query_terms and not owner <= understood for owner in owners
                    ):
                        status, owners = 'unresolved', [None]
            elif state:
                owner_text, subject_attributes = _transport(state['feature'].strip())
                descriptor, predicate_attributes = _transport(state['state'])
                delivery_predicate = bool(re.fullmatch(r'(?:delivered|sent)', _NEGATION.sub('', descriptor).strip()))
                owners = _owners(owner_text, previous, subject=True)
                attributes = subject_attributes | predicate_attributes
                channel_subject = bool(subject_attributes)
                if subject_attributes and predicate_attributes and subject_attributes != predicate_attributes:
                    status, attributes = 'unresolved', frozenset()
                assertion = _AFFIRMED_STATE.match(_NEGATION.sub('', descriptor).strip())
                if status == 'affirmed' and (not assertion or _terms(_NEGATION.sub('', descriptor).strip()[assertion.end():]) - (query_terms | named | labels)):
                    status, attributes = 'unresolved', frozenset()
            else:
                foreign = re.match(rf'^{_FOREIGN}\s+', clause)
                if foreign and _ACTION.fullmatch(clause[foreign.end():]):
                    if not _COORDINATION.search(clause) and ':' not in clause:
                        previous = []
                        continue  # complete other-actor assertion, not a dependency
                    previous = [_Claim(path, span, None, frozenset(), 'unresolved', 'unresolved', False)]
                    claims.extend(previous)
                    continue
                owner_text, attributes = _transport(clause)
                owners = _owners(owner_text, previous)
                if status != 'affirmed' and re.match(rf'^(?:{_REFERENCE})\b', clause):
                    owners = [previous[0].feature] if len(previous) == 1 else [None]
                else:
                    if not all(owner and (owner <= query_terms | labels or
                               (owner <= named | labels and (owner & labels or len(owner) == 1)) or
                               (path.startswith('dataspaceAppDescription.') and len(owner) == 1)) for owner in owners):
                        status = 'unresolved'
                        # An uninterpreted functional label may identify a separate
                        # feature. Other unknown prose has unresolved App-wide scope.
                        scope = _scope_text(owner_text).split()
                        if foreign or not _terms(scope[-1] if scope else '') & _FEATURE_HEADS:
                            owners = [None]
            if attributes - (query_terms | named | labels):
                status, attributes = 'unresolved', frozenset()
            if status != 'affirmed':
                # A parsed state is not proof that an unknown subject denotes a
                # different feature (e.g. "the delivery channel is disabled").
                owners = [owner if owner and owner & (query_terms | named | labels) else None for owner in owners]
            if None in owners and status == 'affirmed' and not state:
                status = 'unresolved'
            kind, scope = _qualification(clause, status, attributes, channel_subject=channel_subject,
                                         delivery_predicate=delivery_predicate)
            if dependency_kind and status != 'unresolved':
                kind = dependency_kind
                scope = 'channel' if attributes else 'feature'
            previous = [_Claim(path, span, owner, attributes, kind, scope) for owner in owners]
            claims.extend(previous)
            if kind == 'no_prerequisite':
                previous = []  # absence supplies no capability or new antecedent
    return claims


def _applies(restriction: _Claim, feature: frozenset[str], required_attributes: set[str],
             affirmed_attributes: set[str]) -> bool:
    """Partial overlap is uncertainty, never a reason to drop a restriction.

    An explicit owner+channel restriction stays on that feature and channel. A
    channel-wide restriction (e.g. "SMS delivery") also qualifies required SMS
    attributes. Unresolved scope cannot establish an unrelated exception.
    """
    if restriction.kind == 'no_prerequisite' and restriction.complete:
        return False
    if not restriction.complete or restriction.scope == 'unresolved' or restriction.feature is None:
        return True
    same_feature = bool(restriction.feature & feature)
    if restriction.kind == 'exclusive':
        # A compatible explicitly requested channel can be corroborated. With
        # no requested channel, keep the limitation rather than certify an
        # unconditional feature or silently reconcile conflicting channel sets.
        return same_feature and (not required_attributes or bool(
            (required_attributes | affirmed_attributes) - restriction.attributes
        ))
    if restriction.scope == 'channel':
        return same_feature and bool(restriction.attributes & required_attributes)
    return same_feature or bool(restriction.feature & required_attributes)


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


def _prepared_support(query: str, app: dict, locale: str, claims: list[_Claim]) -> dict | None:
    """Interpret reviewed coherent passages within the existing assessor.

    Preparation may explain compound prose the bounded clause grammar cannot
    interpret. Require request coverage in BOTH the explanation and its original
    quotation, so generated keywords never become independent feature evidence.
    Strict/negative requests remain on the normal conservative path. A source
    change invalidates preparation in the authoritative projection reader.
    """
    prepared = explanation(app)
    if not prepared:
        return None
    terms = _terms(query)
    if any(c.kind not in {'affirmation', 'unresolved', 'no_prerequisite'}
           and _applies(c, frozenset(terms), terms, set()) for c in claims):
        return None
    # Uninterpreted negative assertions are not cleared by positive preparation.
    if any(c.kind == 'unresolved' and _NEGATION.search(_fold(c.span)) for c in claims):
        return None
    for fact in prepared.get("facts", []):
        path, quote, prose = fact.get("path"), fact.get("quote", ""), fact.get("en", "")
        if not quote or quote not in source_text(app, locale).get(path, ""):
            continue
        if (_NEGATION.search(_fold(quote)) or _QUALIFIED.search(_fold(quote))
                or _NEGATION.search(_fold(prose)) or _QUALIFIED.search(_fold(prose))):
            continue
        if terms and terms <= _terms(quote) and terms <= _terms(prose):
            return {"status": "source_supported", "reason": ("source_extracted_passage" if prepared.get("version") == 2
                                                      else "reviewed_source_passage"),
                    "evidence_fields": [path], "evidence_spans": [quote]}
    return None


def assess(query: str, app: dict[str, Any], locale: str) -> dict[str, Any]:
    """Require owned feature/constraint evidence and no applicable qualification."""
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
    if not terms or _NEGATION.search(_fold(query)) or re.search(r"\b(?:except|only|cheapest|best|better|apenas|nur)\b", _fold(query)):
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
            claims.extend(_claims(path, text, terms, names, synthetic, declarations))
    features = {}
    for claim in claims:
        if claim.status == 'affirmed' and claim.feature:
            features.setdefault(claim.feature, []).append(claim)
    parts = [_terms(part) for part in re.split(r"\b(?:and|e|und)\b", _fold(query))]
    requirements = parts if len(parts) > 1 and all(parts) else [terms]
    support = []
    covered = set()
    for feature, evidence in features.items():
        attributes = set().union(*(c.attributes for c in evidence))
        for index, requirement in enumerate(requirements):
            if not requirement <= feature | attributes:
                continue
            relevant = [c for c in claims if c.status != 'affirmed' and
                        _applies(c, feature, requirement - feature, attributes)]
            if relevant:
                return {"status": "uncertain", "reason": "qualified_or_unresolved_source",
                        "evidence_fields": list(dict.fromkeys(c.path for c in [*evidence, *relevant]))}
            support.extend(evidence)
            covered.add(index)
    if len(covered) != len(requirements):
        support = []
    if not support:
        prepared = _prepared_support(query, app, locale, claims)
        if prepared:
            return prepared
    return {"status": "source_supported" if support else "uncertain",
            "reason": "coherent_source_support" if support else "no_coherent_source_support",
            "evidence_fields": list(dict.fromkeys(c.path for c in support)),
            "evidence_spans": list(dict.fromkeys(c.span for c in support))}
