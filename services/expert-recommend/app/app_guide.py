"""Explanation knowledge derived from an App's current Store source.

The guide is a pure function of the authoritative source fields, so newly
ingested Apps and every source revision are covered without a separate
preparation job or reindex. It organizes complete source sentences by what they
say (purpose, capability, scheme, limitation, access, attribution) and links
them to general glossary concepts. Nothing here grants recommendation support:
`evidence.py` remains the only verifier.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache

from hedge_shared import glossary
from hedge_shared.store_explanations import _NOISE
from hedge_shared.store_knowledge import explanation

from .evidence import _ANAPHORA, _INSTRUCTION, _OTHER_ACTOR, _REFERENCE, _owned
from .suitability import source_text

GUIDE_VERSION = 1
_FIELDS = ("dataspaceAppDescription.properties.description", "description", "readme")
_SPLIT = re.compile(r"(?<=[.!?])\s+|\s*(?:\n|•)+\s*|\s*[\U0001F300-\U0001FAFF\u2600-\u27BF]+\uFE0F?\s*|"
                    r"(?<=\S)\s+(?=(?:Documentation|Deployed instance|External service|No container)\b)")
_HEADING = re.compile(r"^[^\w“\"]*(?:[A-Z][\w’' -]{0,40}:\s+)?")
_ATTRIBUTION = re.compile(r"\b(?:developed|operated|provided|maintained|built|created|owned|run)\b"
                          r"(?:\s+and\s+\w+)?\s+by\b", re.I)
_ACCESS = re.compile(r"https?://|\b(?:accessible|deployed instance|documentation|container image|registry|"
                     r"install\w*|self-host\w*|public url|web address|log ?in|sign ?up)\b", re.I)
_SCHEME = re.compile(r"^[^\w]*[A-Z][\w’' -]{1,40}:\s+(?:where|when|if|the|each|an?)\b|"
                     r"\b(?:for example|for instance|e\.g\.|such as)\b", re.I)
_RELEASE = re.compile(r"^(?:release (?:notes|version|type)|product:|version\b)", re.I)
_SECTION = re.compile(r"^(?:release summary|summary|description|overview|about)\s*:?\s+(?=[A-Z])", re.I)
# Explanation needs a narrower notion of limitation than verification does:
# "sharing of flexibility needs" is a capability, "only includes 2 aggregators" is not.
_LIMIT = re.compile(r"\b(?:not|no|never|cannot|only|planned|future|roadmap|pilot|simulation|simulated|prototype|"
                    r"beta|experimental|demo|unless|except|although|disabled|unsupported|unavailable|"
                    r"under development)\b|n't\b|\brequires?\s+(?:an?\s+)?(?:external|another|separate|"
                    r"third|additional|licen)", re.I)
# A statement that reads as "<App> does X" (rather than a noun phrase) leads.
_CLAIM = re.compile(r"^(?:it|used to|this (?:app|platform|service|system))\s|^[A-Z][\w-]*(?:\s[A-Z][\w-]*)*\s"
                    r"(?:now\s)?[a-z]+s\b", re.I)
_ROLE_TERMS = ("aggregator", "system-operator", "dso", "tso", "market-operator", "prosumer", "bsp",
               "energy-community")


@dataclass(frozen=True)
class Statement:
    id: str
    path: str
    quote: str          # exact source substring
    text: str           # quote without a leading heading/emoji, or the preparer's rendering
    role: str           # purpose | capability | scheme | limitation | access | attribution | context
    owned: bool
    terms: tuple[str, ...]


@dataclass(frozen=True)
class Guide:
    name: str
    provider: str
    statements: tuple[Statement, ...]
    features: tuple[str, ...]
    terms: tuple[str, ...]
    roles: tuple[str, ...]

    def get(self, sid: str) -> Statement | None:
        return next((s for s in self.statements if s.id == sid), None)

    def by_role(self, *roles: str) -> list[Statement]:
        return [s for s in self.statements if s.role in roles]

    @property
    def main(self) -> list[Statement]:
        """What the App does, most central first: purpose, then capabilities."""
        return [s for s in self.statements if s.owned and s.role in {"purpose", "capability"}]

    @property
    def lead(self) -> Statement | None:
        return next(iter(self.main), None)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(text) if s and s.strip()]


def _display(sentence: str) -> str:
    sentence = _SECTION.sub("", sentence.strip()).rstrip(":").strip()
    stripped = _HEADING.sub("", sentence, count=1).strip()
    # Keep the heading when it is the sentence's grammatical subject ("Top Value: Where ...").
    return sentence if _SCHEME.match(sentence) or len(stripped.split()) < 4 else stripped


def _role(sentence: str, owned: bool, name: str) -> str:
    if _ATTRIBUTION.search(sentence):
        return "attribution"
    if _ACCESS.search(sentence):
        return "access"
    if _SCHEME.search(sentence):
        return "scheme"
    if _LIMIT.search(sentence):
        return "limitation"
    if not owned:
        return "context"
    purpose = re.match(rf"^(?:used to|(?:{re.escape(name)}|it|this (?:app|platform|service)|the (?:app|platform|service))"
                       r"(?:\s+now)?\s+(?:facilitates|provides|enables|supports|deploys|is designed to|helps|"
                       r"allows|lets|publishes|combines|aggregates|collects|monitors|analyses|analyzes|forecasts|"
                       r"predicts|stores|validates|converts|transforms|forwards|calculates|records))\b",
                       _display(sentence), re.I) if name else None
    return "purpose" if purpose or re.match(r"^[A-Z][\w-]*(?:\s+[\w-]+){0,3}\s+(?:hub|platform|tool|service|"
                                            r"registry|enabler|library)\s+(?:of|for)\b", _display(sentence)) else "capability"


def _renderings(app: dict) -> dict[str, str]:
    """The preparer's linked restatements ("It combines bids ...") keyed by exact quote."""
    return {f["quote"]: f["en"] for f in explanation(app).get("facts", [])
            if f.get("simple_en") and f.get("en") != f.get("quote")}


def _digest(app: dict) -> str:
    return hashlib.sha256(json.dumps([GUIDE_VERSION, app.get("name"), app.get("provider"),
                                      source_text(app, "en")], sort_keys=True, ensure_ascii=False)
                          .encode()).hexdigest()


def build(app: dict) -> Guide:
    # Key order is source order; explanation() recomputes preparation from it.
    return _build(_digest(app), json.dumps(app, ensure_ascii=False, default=str))


@lru_cache(maxsize=256)
def _build(digest: str, serialized: str) -> Guide:
    del digest  # cache key: the same source always yields the same guide
    app = json.loads(serialized)
    name = app.get("name") or app.get("app_id") or ""
    fields = source_text(app, "en")
    rendered = _renderings(app)
    names = (name,) if name else ()
    seen: set[str] = set()
    statements: list[Statement] = []
    for path in _FIELDS:
        text = fields.get(path, "")
        sentences = _sentences(text)
        index = 0
        while index < len(sentences):
            sentence = sentences[index]
            index += 1
            # "Those bids are then combined ..." belongs to the sentence it refers to.
            if index < len(sentences) and (_ANAPHORA.match(sentences[index]) or
                                           re.match(r"^(?:those|these|they)\b", sentences[index], re.I)):
                follower = sentences[index]
                if not _INSTRUCTION.search(follower) and not _OTHER_ACTOR.match(follower):
                    sentence = f"{sentence} {follower}"
                    index += 1
            words = len(re.findall(r"[^\W\d_]+", sentence))
            folded = " ".join(sentence.casefold().split())
            if (words < (5 if path == "description" else 4) or folded in seen
                    or _NOISE.search(sentence) and not _ACCESS.search(sentence)
                    or _RELEASE.match(sentence) or _INSTRUCTION.search(sentence)
                    or sentence.endswith(":") and words < 6
                    or _OTHER_ACTOR.match(sentence) or re.fullmatch(r"https?://\S+", sentence)):
                continue
            if any(folded in other or other in folded for other in seen):
                continue  # the same sentence repeated in another field
            seen.add(folded)
            quote = sentence if sentence in text else next((q for q in rendered if sentence in q), sentence)
            owned = _owned(_display(sentence), names) and not _REFERENCE.match(_display(sentence))
            role = _role(sentence, owned, name)
            display = rendered.get(quote) or next((r for q, r in rendered.items() if q in quote and role in {
                "purpose", "capability"}), "") or _display(sentence)
            # Concepts in the displayed wording lead; a heading's extra terms follow.
            terms = [*glossary.mentioned(display.replace(name, " ") if name else display),
                     *glossary.mentioned(sentence.replace(name, " ") if name else sentence)]
            statements.append(Statement(f"S{len(statements) + 1}", path, quote, display, role, owned,
                                        tuple(dict.fromkeys(terms))))
    features = tuple(value for path, value in fields.items()
                     if path.startswith("dataspaceAppDescription.properties.featureList[")
                     and 3 <= len(value) <= 120 and not _NOISE.search(value))
    # Central statements first: explicit purposes, then capabilities that name
    # domain concepts, in source order. Their terms explain what the App is about.
    central = [s for s in statements if s.owned and s.role in {"purpose", "capability"}]
    ordered = sorted(central, key=lambda s: (s.role != "purpose", not _CLAIM.match(s.text), not s.terms,
                                             statements.index(s)))
    ordered += [s for s in statements if s not in ordered]
    terms = list(dict.fromkeys([t for s in ordered for t in s.terms]
                               + [t for f in features for t in glossary.mentioned(f)]))
    roles = tuple(t for t in terms if t in _ROLE_TERMS)
    return Guide(name, app.get("provider") or "", tuple(ordered), features, tuple(terms), roles)
