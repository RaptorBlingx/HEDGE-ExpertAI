"""What the user wants this turn, about which Apps: one interpretation per turn.

The interpreter owns intent and identity; nothing downstream re-reads the
message to change them.

- **Apps** are found by the App linker (names however spelled, source aliases,
  providers, exact native IDs). Pronouns, ordinals and "the other one" resolve
  against the dialogue state: what was shown, what is in focus.
- **The act** (describe, check, find, compare, ...) comes from two independent
  classifiers over the same labelled examples (hedge_shared/dialogue_acts.json),
  with App mentions masked so they hold for any future App: Rasa's DIET model,
  and E5 nearest examples. They fail differently, so agreement is the
  confidence signal. A disagreement is put to the language model as a choice
  between the two readings; without it, the user is asked which they meant.
- **Structure** completes the frame: an act that needs a subject gets one from
  the state or becomes a clarification; words beyond the act's own vocabulary
  are a functional need, so "Can X forecast solar?" is a capability check
  rather than a description, and "list apps for meters" a search, not a listing.

Facts and recommendations are not decided here; executors do that from sources.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files

from hedge_shared.app_linker import AppLinker, Mention
from hedge_shared.config import Settings

PLACEHOLDER = "APP"

# Acts by the slots they take.
SUBJECT_ACTS = {"describe", "simple", "example", "analogy", "how", "differently", "meaning", "audience",
                "provider", "price", "access", "details", "check", "ask"}
SET_ACTS = {"compare", "choose"}
NEED_ACTS = {"check", "find", "choose"}
EXPLANATION_ACTS = {"describe", "simple", "example", "analogy", "how", "differently", "meaning", "audience"}
SMALL_TALK = {"greeting", "thanks", "help", "reset", "out_of_scope"}

# Closed-class words: contractions and reference expressions, not vocabulary.
_CONTRACTIONS = [(r"\b(\w+)n['’]t\b", r"\1 not"), (r"\bcan not\b", "cannot"), (r"\bwo not\b", "will not"),
                 (r"\b(i)['’]m\b", r"\1 am"), (r"\b(\w+)['’]re\b", r"\1 are"), (r"\b(\w+)['’]ve\b", r"\1 have"),
                 (r"\b(\w+)['’]ll\b", r"\1 will"), (r"\b(\w+)['’]d\b", r"\1 would"),
                 (r"\b(it|that|what|who|where|how|there|here|which)['’]s\b", r"\1 is")]
_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3,
             "fifth": 4, "5th": 4, "last": -1}
_REFERENCES = [
    ("other", re.compile(r"\bthe other(?:\s+(?:one|app|application))?\b", re.I)),
    ("ordinal", re.compile(r"\b(?:the\s+)?(" + "|".join(_ORDINALS) + r")(?:\s+(?:one|app|application))?\b", re.I)),
    ("set", re.compile(r"\b(?:both(?:\s+of\s+them)?|them|they|these(?:\s+apps)?|those(?:\s+(?:apps|two))?|"
                       r"the\s+two|either|each\s+of\s+them)\b", re.I)),
    ("focus", re.compile(r"\b(?:it|its|itself|this(?:\s+(?:app|one|application))?|that\s+(?:app|one|application)|"
                         r"the\s+app)\b", re.I)),
]


# English function words carry no functional need ("what apps do *we* have?").
_FUNCTION_WORDS = frozenset((
    "a an the this that these those it its they them their there here we us our you your i me my he she his "
    "her who whom whose which what when where why how is are was were be been being am do does did done have "
    "has had will would shall should can could may might must of to for in on at by with from into about as "
    "and or but if so than then too very just also not no any some all each every other another such own "
    "please ok okay yes yeah hi hey thanks thank well really actually maybe"
).split())


def expand_contractions(text: str) -> str:
    for pattern, replacement in _CONTRACTIONS:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text


@lru_cache(maxsize=1)
def acts() -> dict[str, dict]:
    return json.loads(files("hedge_shared").joinpath("dialogue_acts.json").read_text(encoding="utf-8"))["acts"]


_NEED_SPAN = re.compile(r"\[([^\]]+)\]\(need\)")


def plain(example: str) -> str:
    """An example utterance without its need-span markup."""
    return _NEED_SPAN.sub(r"\1", example)


@dataclass
class Frame:
    act: str
    subjects: list[str] = field(default_factory=list)  # catalogue identities, never names
    need: str = ""        # the functional need, for check/find/choose
    phrase: str = ""      # the words a term question asks about
    source: str = ""      # how the act was decided: agreement, rasa, semantic, model, action, ...
    options: list[dict] = field(default_factory=list)  # competing readings, when unresolved
    problem: str = ""     # why a clarification is needed
    signals: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {"act": self.act, "subjects": self.subjects, "need": self.need, "source": self.source,
                **({"problem": self.problem} if self.problem else {}), "signals": self.signals}


@dataclass
class Reference:
    kind: str  # focus, other, ordinal, set
    start: int
    end: int
    index: int | None = None


def references(text: str) -> list[Reference]:
    found: list[Reference] = []
    for kind, pattern in _REFERENCES:
        for match in pattern.finditer(text):
            if any(match.start() < r.end and r.start < match.end() for r in found):
                continue
            index = _ORDINALS[match[1].casefold()] if kind == "ordinal" else None
            found.append(Reference(kind, match.start(), match.end(), index))
    return sorted(found, key=lambda r: r.start)


def mask(text: str, mentions: list[Mention]) -> str:
    """App mentions as the placeholder, as in the labelled examples."""
    for mention in sorted(mentions, key=lambda m: -m.start):
        text = text[:mention.start] + PLACEHOLDER + text[mention.end:]
    return text


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", expand_contractions(text).casefold()))


@lru_cache(maxsize=1)
def _operation_vocabulary() -> frozenset[str]:
    """Words that ask *about* Apps or *for* one, never what one should do.

    The needless acts' examples, plus the wording around the marked need spans
    of the need acts' examples ("is there an app for [...]"), less any word a
    need span itself uses.
    """
    asking: set[str] = set()
    for name, act in acts().items():
        if name not in NEED_ACTS | {"term", "ask", "out_of_scope", "same", "remove_constraint"}:
            for example in act["examples"]:
                asking |= _words(example)
    return frozenset(asking | _request_vocabulary())


@lru_cache(maxsize=1)
def _request_vocabulary() -> frozenset[str]:
    """Only the wording around need spans ("is there an app for"), never other acts' words such as "free"."""
    requesting, inside = set(), set()
    for name in NEED_ACTS:
        for example in acts()[name]["examples"]:
            inside |= {w for span in _NEED_SPAN.findall(example) for w in _words(span)}
            requesting |= _words(_NEED_SPAN.sub(" ", example))
    return frozenset((requesting - inside) | _FUNCTION_WORDS
                     | {PLACEHOLDER.casefold(), "app", "apps", "application", "applications", "one"})


def residual(masked: str, refs: list[Reference] = ()) -> str:
    """The words left once App mentions, references and act vocabulary are removed."""
    text = masked
    for ref in sorted(refs, key=lambda r: -r.start):
        text = text[:ref.start] + " " + text[ref.end:]
    vocabulary = _operation_vocabulary()
    # Original case survives: "BSP" is an acronym, "bsp" may not be.
    kept = [w for w in re.findall(r"[^\W_]+(?:[-'][^\W_]+)*", expand_contractions(text))
            if w.casefold() not in vocabulary]
    return " ".join(kept)


def need_text(message: str, mentions: list[Mention], refs: list[Reference]) -> str:
    """The request without App mentions, reference words, or clauses that only ask ("which app should I use?").

    The verifier strips the remaining request wording from each requirement.
    """
    spans = sorted([(m.start, m.end) for m in mentions] + [(r.start, r.end) for r in refs], reverse=True)
    text = message
    for start, end in spans:
        text = text[:start] + " " + text[end:]
    text = expand_contractions(text)
    text = re.sub(r"\b(?:too|also|as well|then|anyway|instead|please|ok|okay|so)\b", " ", text, flags=re.I)
    clauses = [c for c in re.split(r"\s*[,;.?!:]+\s*", text) if c.strip()]
    kept = [_trim(c) for c in clauses if residual(c)] or clauses
    return " ".join(" ".join(kept).split()).strip(" ,.?!")


def _trim(clause: str) -> str:
    """Drop the asking words a clause starts with ("which is better for [settlement]")."""
    words, vocabulary = clause.split(), _request_vocabulary()
    while len(words) > 1 and set(re.findall(r"[a-z0-9]+", words[0].casefold())) <= vocabulary:
        words.pop(0)
    return " ".join(words)


_GLOSSES = {
    "describe": "explain what {apps} is", "simple": "explain {apps} in simpler terms",
    "example": "give an example of {apps} in use", "analogy": "give an analogy for {apps}",
    "how": "explain how {apps} works", "differently": "explain {apps} another way",
    "meaning": "clarify what I said about {apps}", "audience": "say who {apps} is for",
    "provider": "say who provides {apps}", "price": "show what is listed about the price of {apps}",
    "access": "show how to access {apps}", "details": "show the technical details of {apps}",
    "check": "check whether {apps} can {need}", "find": "find an App that can {need}",
    "compare": "compare {apps}", "choose": "say which of {apps} suits {need}", "ask": "answer that about {apps}",
    "list": "list the Apps in the Store", "term": "explain the term", "remove_constraint": "drop the earlier condition",
    "greeting": "say hello", "thanks": "wrap up", "help": "explain what I can help with", "reset": "start over",
    "out_of_scope": "treat it as a question outside the App Store",
}


def gloss(frame: Frame, names: dict[str, str]) -> str:
    """A plain-English reading of a frame, for the model's choice or the user's."""
    apps = " and ".join(f"**{names.get(i, i)}**" for i in frame.subjects) or "it"
    need = re.sub(r"^(?:(?:can|could|does|do|will|would|is there|are there)\s+)?(?:(?:an?|any)\s+apps?\s+)?"
                  r"(?:that\s+|which\s+|to\s+|for\s+)?", "", frame.need, flags=re.I) or "do that"
    return _GLOSSES.get(frame.act, frame.act).format(apps=apps, need=need)


class Interpreter:
    """Turn a message plus dialogue state into one Frame."""

    def __init__(self, *, rasa: Callable[[str], list[tuple[str, float]] | None],
                 semantic: Callable[[str, list[str]], list[float] | None],
                 arbitrate: Callable[[str, list[dict], dict], int | None] | None = None):
        self.rasa, self.semantic, self.arbitrate = rasa, semantic, arbitrate
        examples = [(name, plain(e)) for name, act in acts().items() for e in act["examples"]]
        self._labels, self._examples = [n for n, _ in examples], [e for _, e in examples]

    def classify(self, masked: str) -> dict:
        """Both classifiers' readings of a masked message."""
        signals: dict = {}
        ranking = self.rasa(masked)
        if ranking:
            signals["rasa"] = ranking[0][0]
            signals["rasa_confidence"] = round(ranking[0][1], 3)
        scores = self.semantic(masked, self._examples)
        if scores:
            best: dict[str, float] = {}
            for label, score in zip(self._labels, scores, strict=True):
                best[label] = max(best.get(label, -1.0), score)
            ranked = sorted(best.items(), key=lambda kv: -kv[1])
            signals["semantic"] = ranked[0][0]
            signals["semantic_margin"] = round(ranked[0][1] - ranked[1][1], 4)
        return signals

    def interpret(self, message: str, state: dict, catalogue: list[dict], *, history: list[dict] = (),
                  clicked: list[str] | None = None) -> Frame:
        if clicked is not None:
            return Frame("describe", clicked, source="action") if len(clicked) == 1 else Frame(
                "clarify", problem="unavailable_action")
        linker = AppLinker(catalogue)
        mentions = linker.mentions(message)
        if any(m.kind == "id_case" for m in mentions):
            return Frame("clarify", problem="id_case")
        ambiguous = [m for m in mentions if m.ambiguous]
        if ambiguous:
            return Frame("clarify", problem="ambiguous_name", options=[{"subjects": list(ambiguous[0].app_ids)}])
        refs = references(message)
        masked = mask(message, mentions)
        named = list(dict.fromkeys(i for m in mentions for i in m.app_ids))
        signals = self.classify(masked)
        # A Rasa reading below the configured confidence is not a reading.
        confident = signals.get("rasa_confidence", 0) >= Settings().RASA_CONFIDENCE_THRESHOLD
        readings = list(dict.fromkeys(a for a in (signals.get("rasa") if confident else None,
                                                  signals.get("semantic")) if a))
        if not readings:
            return Frame("clarify", problem="understanding_unavailable", signals=signals)
        content = residual(masked, refs)
        frames = []
        for act in readings:
            frame = self._complete(act, message, named, mentions, refs, content, state, catalogue, readings)
            if all(frame.act != f.act or frame.subjects != f.subjects for f in frames):
                frames.append(frame)
        # A reading that fails its own structure (a search without a need) is no reading,
        # and a message about an App it names or refers to is not out of scope.
        frames = [f for f in frames if f.act != "clarify"] or frames[:1]
        if any(f.subjects for f in frames):
            frames = [f for f in frames if f.act != "out_of_scope"]
        if len(frames) == 1:
            frames[0].source = "agreement" if len(readings) == 1 and confident and "semantic" in signals else "consistent"
            frames[0].signals = signals
            return frames[0]
        # Two readings remain: ask the model to choose, else ask the user.
        names = {a["id"]: a.get("name") or a["app_id"] for a in catalogue}
        options = [{"act": f.act, "subjects": f.subjects, "need": f.need, "gloss": gloss(f, names)} for f in frames]
        choice = self.arbitrate(message, options, {"history": list(history)[-2:]}) if self.arbitrate else None
        if choice is not None and 0 <= choice < len(frames):
            frames[choice].source, frames[choice].signals = "model", signals
            return frames[choice]
        return Frame("clarify", problem="two_readings", options=options, signals=signals)

    def _complete(self, act: str, message: str, named: list[str], mentions: list[Mention],
                  refs: list[Reference], content: str, state: dict, catalogue: list[dict],
                  readings: list[str] = ()) -> Frame:
        """Fill the act's slots from the message and the dialogue state, adjusting the act to its structure."""
        last = state.get("last", {})
        need = need_text(message, mentions, refs)
        if act == "same":
            # "And the other one?" / "What about X?": the previous question, new subject.
            previous = last.get("act") if last.get("act") not in {None, "same", "clarify", "list", "find"} else "describe"
            if not named and not refs and content and last.get("act") in NEED_ACTS:
                # "What about for solar?": the previous operation with a new need.
                return self._complete(last["act"], message, named, mentions, refs, content, state, catalogue, readings)
            act, need = previous, last.get("need", "") if previous in NEED_ACTS else ""
            content = need
        # A functional need turns a description into a check and a listing into a search
        # ("Can X forecast solar?", "list apps for meters"). Qualified explanations
        # ("explain it like I'm new to energy") keep their act.
        # A listing never absorbs a need; a description does only when the other
        # reading also heard one.
        if content and (act == "list" or act == "describe" and NEED_ACTS & set(readings)):
            act = "check" if act == "describe" and (named or self._subjects("check", mentions, refs, state, catalogue)) else "find"
        # "Can it shut down the turbine?" asks about the App in focus, not for another App.
        if act == "find" and content and (len(named) == 1 or not named and any(r.kind == "focus" for r in refs)
                                         and self._subjects("check", mentions, refs, state, catalogue)):
            act = "check"
        if act in NEED_ACTS and not content:
            need = last.get("need", "") or state.get("need", "")
        subjects = self._subjects(act, mentions, refs, state, catalogue)
        # Asking whether *an* App can do something names no subject: without a name
        # or reference, a check that the other classifier read as a search is one.
        if act == "check" and (not subjects or not named and not refs and "find" in readings):
            act, subjects = "find", []
        if act == "choose" and len(subjects) < 2:
            act, subjects = ("find", []) if need else ("clarify", subjects)
        if act == "find" and not need.strip():
            return Frame("clarify", problem="no_need")
        if act in SUBJECT_ACTS and not subjects:
            return Frame("clarify", act if act != "clarify" else "", problem="no_subject")
        if act == "compare" and len(subjects) < 2:
            return Frame("clarify", subjects, problem="no_comparison_pair")
        phrase = residual(mask(message, mentions), refs) if act == "term" else ""
        if act == "term" and not phrase:
            return Frame("clarify", problem="no_term")
        return Frame(act, subjects, need if act in NEED_ACTS else "", phrase)

    @staticmethod
    def _subjects(act: str, mentions: list[Mention], refs: list[Reference], state: dict, catalogue: list[dict]) -> list[str]:
        if act not in SUBJECT_ACTS | SET_ACTS:
            return []
        named = list(dict.fromkeys(i for m in mentions for i in m.app_ids))
        current = {a["id"] for a in catalogue}
        shown = [i for i in state.get("shown", []) if i in current]
        focus = [i for i in state.get("focus", []) if i in current]
        group = shown if len(shown) > 1 else [i for i in state.get("compared", []) if i in current]
        resolved: list[tuple[int, str]] = []  # (position in the message, identity)
        for ref in refs:
            if ref.kind == "ordinal" and group:
                position = ref.index if ref.index is not None else 0
                if -len(group) <= position < len(group):
                    resolved.append((ref.start, group[position]))
            elif ref.kind == "other" and len(focus) == 1:
                # The rest of the latest set: shown or compared Apps, those discussed, or the catalogue.
                for pool in (group, state.get("discussed", []), [a["id"] for a in catalogue]):
                    rest = [i for i in pool if i not in focus and i in current]
                    if rest:
                        resolved += [(ref.start, rest[0])] if len(rest) == 1 else []
                        break
            elif ref.kind == "set" and len(group) > 1:
                resolved += [(ref.start, i) for i in group]
            elif ref.kind == "focus" and len(focus) == 1:
                resolved += [(ref.start, focus[0])]
        # Apps in the order the message mentions them: "compare it with X" starts with it.
        ordered = sorted([(m.start, i) for m in mentions for i in m.app_ids] + resolved, key=lambda p: p[0])
        if act in SET_ACTS:
            subjects = list(dict.fromkeys(i for _, i in ordered))
            if len(subjects) == 1 and len(focus) == 1 and focus != subjects:
                subjects = focus + subjects  # "What's the difference with X?" compares X with the focus
            if len(subjects) < 2:
                discussed = [i for i in state.get("discussed", []) if i in current]
                subjects = (group if len(group) > 1 else discussed[-2:] if len(discussed) > 1
                            else [a["id"] for a in catalogue] if len(catalogue) == 2 else subjects)
            return subjects[:5]
        if named:
            return named
        if resolved:
            return list(dict.fromkeys(i for _, i in resolved))
        if any(r.kind in {"other", "ordinal", "set"} for r in refs):
            return []  # an explicit reference that resolves to nothing is not the focus
        if len(focus) == 1:
            return focus
        if len(shown) == 1:
            return shown
        return [a["id"] for a in catalogue] if len(catalogue) == 1 else []
