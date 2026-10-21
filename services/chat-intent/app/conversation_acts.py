"""What a conversational turn asks for, independent of which App it is about.

One closed grammar for the explanation acts people use when exploring an App
("explain it simply", "what does that mean?", "give me an example", "compare
them in plain English"). Capability checks, searches, filters and metadata
reads are deliberately *not* acts: they keep their verified paths. An utterance
that does not match falls through unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from hedge_shared import glossary
from hedge_shared.store_language import catalogue_question


@dataclass(frozen=True)
class Act:
    kind: str          # overview simple example how term meaning differently compare choose facts open
    phrase: str = ""   # the concept asked about (term) or the App operand (overview)


_PRONOUN = r"(?:it|that|this|they|them|these|those|this app|that app|that one|this one|the app)"
_PRONOUNS = re.compile(rf"^{_PRONOUN}$", re.I)
_QUOTE = "\"“”'‘’"
# Capability questions and new searches belong to the verified decision path.
# "Can I rely on it?" is about the user's situation, not an App capability.
_CAPABILITY = re.compile(r"^(?:does|do|can|could|will|is|are)\s+(?!(?:i|we|you)\b)(?:it|they|this|that|\w+)\s+(?:also\s+)?"
                         r"(?:support|supports|provide|provides|offer|offers|handle|handles|do|have|has|"
                         r"generate|generates|send|sends|integrate|integrates|work with|connect|connects|"
                         r"forecast|forecasts|combine|combines|submit|submits|transform|transforms|validate|"
                         r"validates|able to|capable of|compatible)\b|"
                         r"^(?:does|do|can|could)\s+(?!(?:i|we|you)\b)(?:it|they|this|that|\w+)\s+\w+", re.I)
_SEARCH = re.compile(r"\b(?:find|search|recommend|looking for|show me (?:something|an app|apps)|"
                     r"i need|i want|we need|is there (?:an|any) app|which apps?\b(?! (?:should|would) i))\b", re.I)
_CRITERION = re.compile(r"\b(?:for|in terms of|regarding|when it comes to)\s+(?!(?:a |an |the )?"
                        r"(?:beginner|non-?expert|layperson|someone|me|us)\b)\w+", re.I)
_SIMPLE = re.compile(r"\b(?:simple|simpler|simply|plain|everyday|layman'?s?|non-?technical|less technical|"
                     r"basic) ?(?:language|english|terms|words|way)?\b|\bsimplify\b|\beli5\b|"
                     r"\blike i'?m (?:five|5|a child)\b|\bto (?:someone|somebody|a person|people|me as someone)\b"
                     r".{0,30}\b(?:unfamiliar|new|without|who (?:doesn't|does not|isn't))\b|"
                     r"\bfor (?:a )?(?:beginner|non-?expert|layperson|newcomer)s?\b", re.I)
_DIFFERENTLY = re.compile(r"\b(?:explain|say|put|describe|phrase)\b.{0,15}\b(?:differently|another way|"
                          r"in (?:a )?different way|some other way)\b|\b(?:another|different) (?:way|explanation|"
                          r"angle)\b|\btry again\b|\bstill (?:don'?t|do not|didn'?t) (?:understand|get)\b", re.I)
_MEANING = re.compile(rf"^(?:so )?what (?:does|do|did) {_PRONOUN} (?:mean|stand for)$|\bwhat do you mean\b|"
                      r"^(?:i )?(?:still )?(?:don'?t|do not|didn'?t) (?:get|understand)(?: (?:it|that|this|you))?$|"
                      r"\bi'?m (?:still )?(?:confused|lost)\b|^(?:huh|sorry|meaning|pardon)$|"
                      r"^(?:that|this|it) (?:is|was|sounds) (?:confusing|complicated|too technical)$|"
                      r"\bbreak (?:it|that|this) down\b|\bunpack (?:it|that|this)\b|\bin other words\b", re.I)
_EXAMPLE = re.compile(r"\b(?:give|show|provide|share|offer)(?: me| us)? (?:an? |some )?(?:practical |concrete |"
                      r"real(?:[- ]world|[- ]life)? |simple |everyday )?(?:examples?|use cases?|scenarios?)\b|"
                      r"^(?:an? |any )?(?:practical |concrete |real(?:[- ]world)? )?examples?(?: please)?$|"
                      r"^(?:for example|for instance|like what|such as)$|"
                      rf"\bwhat (?:would|does) {_PRONOUN} look like in (?:practice|real life)\b", re.I)
_HOW = re.compile(rf"^how (?:does|do|would) (?:{_PRONOUN}|(?P<x>.+?)) (?:actually )?work(?: in practice)?$", re.I)
_COMPARE = re.compile(r"\bcompare\b|\b(?:difference|differences) between\b|\bhow (?:do|does|are|is)\b.{1,60}"
                      r"\b(?:differ|different)\b|\b(?:the same as|similar to|different from)\b|\bvs\.?\b|"
                      r"\bversus\b", re.I)
_CHOOSE = re.compile(r"\bwhy (?:would|should|might) (?:i|we|someone|anyone|you) (?:choose|pick|use|prefer|"
                     r"go for)\b|\bwhich (?:one |app )?(?:should|would) (?:i|we) (?:choose|pick|use|go for)\s*$|"
                     r"\bwhen (?:should|would) (?:i|we) (?:use|choose|pick)\b|\bpick one over\b|"
                     r"\bone over the other\b", re.I)
_TERM = (
    re.compile(rf"^(?:so )?what (?:does|do) [{_QUOTE}]?(?P<t>[^{_QUOTE}]+?)[{_QUOTE}]? (?:mean|stand for)$", re.I),
    re.compile(r"^(?:so )?what(?:'s| is| are)(?: the meaning of)? (?:an? |the )?(?:term |word )?"
               rf"[{_QUOTE}]?(?P<t>[^{_QUOTE}]+?)[{_QUOTE}]?(?: exactly)?$", re.I),
    re.compile(rf"^(?:please )?(?:define|explain the (?:term|word)|what do you mean by) [{_QUOTE}]?(?P<t>[^{_QUOTE}]+?)"
               rf"[{_QUOTE}]?$", re.I),
    re.compile(rf"^(?:can you |could you )?(?:please )?explain what (?:an? |the )?[{_QUOTE}]?(?P<t>[^{_QUOTE}]+?)[{_QUOTE}]? "
               r"(?:is|are|means)$", re.I),
)
_OVERVIEW = (
    re.compile(r"^(?:so )?(?:what(?:'s| is| are)|who is) (?P<x>.+?)(?: (?:useful|good|used|meant|designed))?(?: for)?$",
               re.I),
    re.compile(r"^(?:can you |could you )?(?:please )?(?:tell me (?:more )?about|describe|introduce|explain|"
               r"what about|how about|and) (?P<x>.+?)(?: please)?$", re.I),
    re.compile(r"^what (?:does|do) (?P<x>.+?) do$", re.I),
    re.compile(r"^(?:what can|what would) (?P<x>.+?) (?:do|help (?:me )?with)(?: for me)?$", re.I),
)
_PROVIDER = re.compile(r"\bwho\b.{0,30}\b(?:provides?|makes|develops|developed|operates|offers|supplies|is behind)\b|"
                       r"\bprovider\b", re.I)
_ACCESS = re.compile(r"\b(?:access|get started|start using|sign up|log ?in|try it|where (?:can|do) i (?:find|use))\b", re.I)
# Price, access, licence, version and similar metadata questions have prepared
# source-field answers; they are never open model questions.
# Words such as "paid" also occur in ordinary questions ("who gets paid in the end?").
_METADATA = re.compile(r"\b(?:cost|costs|price|prices|pricing|fees?|subscription|licen[cs]e\w*|open[- ]source|versions?|"
                       r"(?:is|are) (?:it|they|this|that)\s+(?:free|paid)|free (?:to use|of charge|apps?)|"
                       r"paid (?:apps?|plan|version)|"
                       r"install\w*|download\w*|deploy\w*|container|self-host\w*|ratings?|reviews?|rated|"
                       r"certifi\w*|support (?:contact|team)|contact)\b", re.I)
# Any other question about an App already in the conversation is answered by the
# cited explainer. It cannot recommend, so a misread question costs one hedged
# answer instead of a planner call that may turn it into a capability verdict.
_QUESTION = re.compile(r"\?\s*$|^(?:what|why|how|who|when|where|would|could|should|can (?:i|we)|is|are|"
                       r"do (?:i|we)|does (?:it|that) matter|so|explain why|tell me why)\b", re.I)


def _clean(message: str) -> str:
    text = " ".join(message.replace("’", "'").split())
    return text.strip().rstrip("?!.,;:").strip()


def parse(message: str, app_names: list[str] | tuple[str, ...] = ()) -> Act | None:
    """The explanation act this utterance asks for, or None for the verified paths."""
    text = _clean(message)
    if not text or len(text) > 300:
        return None
    named = [n for n in app_names if n and re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text, re.I)]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    last = _clean(sentences[-1]) if sentences else text
    # "Compare their prices" or "explain the licence simply" read source fields;
    # only a definition question ("what does open source mean?") is an act.
    if _METADATA.search(text) and not any(p.match(last) for p in _TERM):
        return None
    if _COMPARE.search(text) or _CHOOSE.search(text):
        # A functional criterion ("compare them for bid aggregation") is a decision.
        criterion = _CRITERION.search(re.sub(r"\b(?:in )?plain (?:english|language)\b|\bin simple terms\b", "", text, flags=re.I))
        if criterion and not _CHOOSE.search(text):
            return None
        return Act("choose" if _CHOOSE.search(text) else "compare")
    if _SEARCH.search(text):
        return None
    if _PROVIDER.search(text) and _ACCESS.search(text):
        return Act("facts")
    if _DIFFERENTLY.search(text):
        return Act("differently")
    if _MEANING.search(last) or _MEANING.search(text):
        return Act("meaning")
    if _EXAMPLE.search(text):
        return Act("example")
    if _SIMPLE.search(text) and not _CAPABILITY.match(text):
        return Act("simple")
    how = _HOW.match(text)
    if how and (not how["x"] or named):
        return Act("how")
    for pattern in _TERM:
        match = pattern.match(last)
        if match:
            phrase = match["t"].strip()
            if _PRONOUNS.match(phrase) or any(phrase.casefold() == n.casefold() for n in named):
                break
            if glossary.lookup(phrase):
                return Act("term", phrase)
            if pattern is _TERM[0] or pattern is _TERM[2] or pattern is _TERM[3]:
                return Act("term", phrase)  # explicitly a definition question, even if unknown
            break
    for pattern in _OVERVIEW:
        match = pattern.match(text)
        if match:
            operand = match["x"].strip(_QUOTE + " ")
            operand = re.sub(r"^(?:the )?(?:app|application)\s+", "", operand, flags=re.I)
            if _PRONOUNS.match(operand) or any(operand.casefold() == n.casefold() for n in named):
                return Act("overview", operand)
            return None
    if (_QUESTION.search(message.strip()) and not _CAPABILITY.match(text) and not _PROVIDER.search(text)
            and not _ACCESS.search(text) and not re.match(r"which\b", text, re.I) and not catalogue_question(text)):
        return Act("open")
    return None


_ELLIPTICAL = re.compile(
    r"^(?:(?:can|could) you )?(?:please )?(?:show|find|give|recommend|suggest)(?: me| us)? "
    r"(?:something|one|an app|apps|any(?:thing| app| apps)?|another(?: one| app)?|an alternative|alternatives)"
    r"(?: (?:that|which) (?:can|does|do|could|will|would)(?: (?:it|that|this|so))?)?$|"
    r"^(?:is|are) there (?:one|any|an app|apps|something|anything|another)"
    r"(?: (?:that|which) (?:can|does|do))?(?: (?:it|that))?$|"
    r"^(?:which|what) (?:app|one) (?:can|does|do)(?: (?:it|that))?$", re.I)
_AUXILIARY = re.compile(r"^(?:(?:so|and)\s+)?(?:does|do|can|could|will|would|is|are)\s+"
                        r"(?:it|they|this|that|this app|that app)?\s*(?:also\s+)?(?:able to\s+)?", re.I)


def elliptical_search(message: str, need: str) -> str | None:
    """'Find me one that does' after a capability question searches for that same need."""
    if not need or not _ELLIPTICAL.match(_clean(message)):
        return None
    need = _AUXILIARY.sub("", _clean(need)).strip()
    return f"Find an app to {need}" if need else None
