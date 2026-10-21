"""Conversational explanations of Store Apps: grounded, layered, non-repeating.

Each answer keeps two kinds of content visibly apart:

* what an App's Store description says (its own sentences, from `app_guide`), and
* general background about the domain (the reviewed-pending `glossary`).

Prepared acts compose these instantly. Questions that need flexible reasoning
use one bounded Qwen call over the same material (`open_answer`). Nothing here
can recommend an App or grant support: capability questions stay with the
evidence verifier.
"""
from __future__ import annotations

import json
import re
import time

from hedge_shared import glossary
from hedge_shared.config import Settings

from . import app_guide
from .evidence import terms as evidence_terms
from .llm_client import OllamaClient
from .recommender import _quoted_store_text

# Each App is explained through progressively different representations.
# "Explain it differently" moves to the next one not yet used for that App.
LADDER = ("overview", "simple", "analogy", "example", "how")
PREPARED_ACTS = {*LADDER, "term", "compare", "choose", "differently", "meaning", "facts"}
MODEL_ACTS = {"open"}
_MAX_DEFINITIONS = 3


def _q(text: str) -> str:
    return _quoted_store_text(text) or ""


def _name(guide: app_guide.Guide) -> str:
    return f"**{_q(guide.name)}**"


def _claim(guide: app_guide.Guide, statement: app_guide.Statement) -> str:
    """A documented statement attributed to the App, in its own words."""
    text = statement.text.strip()
    name = guide.name
    lowered = text[:1].lower() + text[1:]
    if re.match(r"^it\s", text, re.I):
        return f"{_name(guide)} {_q(text[3:])}"
    if re.match(r"^used to\s", text, re.I):
        return f"{_name(guide)} is {_q(lowered)}"
    if re.match(r"^this (?:app|platform|service|system)\s", text, re.I):
        rest = re.sub(r"^this \w+\s", "", text, flags=re.I)
        return f"{_name(guide)} {_q(rest)}"
    if name and text.casefold().startswith(name.casefold() + " "):
        return f"{_name(guide)} {_q(text[len(name) + 1:])}"
    if not re.search(r"\b(?:is|are|was|were|has|have|can|will|[a-z]+s)\b", text.split(",")[0]):
        return f"{_name(guide)} is described as: “{_q(text)}”"
    return f"{_name(guide)}’s description says: “{_q(text)}”"


def _phrase(guide: app_guide.Guide, statement: app_guide.Statement) -> str:
    """'combines bids from ...' / 'to publish ...' for 'if you need something that ...'."""
    text = statement.text.strip().rstrip(".")
    name = guide.name
    if re.match(r"^used to\s", text, re.I):
        return "you need to " + _q(text[8:])
    for prefix in (r"^it\s", r"^this (?:app|platform|service|system)\s", rf"^{re.escape(name)}\s(?:now\s)?"):
        if name and re.match(prefix, text, re.I):
            return "you need something that " + _q(re.sub(prefix, "", text, count=1, flags=re.I))
    return f"what you need matches “{_q(text)}”"


def related_statement(guide: app_guide.Guide, question: str, exclude: tuple[str, ...] = ()) -> app_guide.Statement | None:
    """The App's sentence sharing the most content words with a question; context, never confirmation."""
    asked = evidence_terms(question) - evidence_terms(guide.name)
    best, score = None, 0
    for statement in guide.statements:
        if statement.id in exclude or statement.role in {"attribution", "access"}:
            continue
        overlap = len(asked & evidence_terms(statement.text))
        if overlap > score:
            best, score = statement, overlap
    return best


def _definition(term: glossary.Term, *, why: bool = False) -> str:
    line = f"**{term.term[:1].upper() + term.term[1:]}**: {term.plain}."
    if why and term.why:
        line += " " + glossary.sentence(term.why)
    return line


def _state(state: dict, guide: app_guide.Guide, app_id: str) -> dict:
    entry = state.setdefault("apps", {}).setdefault(app_id, {})
    entry.setdefault("used", [])
    entry.setdefault("shown", [])
    return entry


def _defined(state: dict) -> list[str]:
    return state.setdefault("defined", [])


def _central_terms(guide: app_guide.Guide, limit: int = 4) -> list[str]:
    """Concepts in what the App does; others (e.g. from a negation) only if there are none."""
    terms = list(dict.fromkeys(t for s in guide.main[:3] for t in s.terms))
    return (terms or list(guide.terms))[:limit]


def _fresh_terms(guide: app_guide.Guide, state: dict, limit: int = _MAX_DEFINITIONS) -> list[glossary.Term]:
    """Undefined central concepts, each preceded by the more basic idea it builds on."""
    defined = set(_defined(state))
    ordered: list[str] = []
    for term_id in _central_terms(guide, 4):
        basics = [r for r in glossary.BY_ID[term_id].related if r != term_id
                  and glossary.BY_ID[r].category == "flexibility" and (r in guide.terms or r == "flexibility")]
        ordered += [*basics[:1], term_id]
    return [glossary.BY_ID[t] for t in dict.fromkeys(ordered) if t not in defined][:limit]


def _caveats(guide: app_guide.Guide, limit: int = 2) -> list[app_guide.Statement]:
    return guide.by_role("limitation")[:limit]


def overview(guide: app_guide.Guide, state: dict, app_id: str) -> str:
    entry = _state(state, guide, app_id)
    main = guide.main
    if not main:
        statements = [s for s in guide.statements if s.role in {"limitation", "context", "scheme"}]
        if not statements:
            return f"{_name(guide)}’s Store entry doesn’t describe what it does yet."
        main = statements
    lines = [_claim(guide, main[0])]
    more = [s for s in main[1:] if s.terms][:2] or main[1:2]
    context = guide.by_role("context")[:1]
    if more or context:
        lines.append("Its description also says:\n" + "\n".join(
            f"- “{_q(s.text)}”" for s in [*more, *context]))
    if guide.features:
        lines.append("Listed features: " + " · ".join(_q(f) for f in guide.features) + ".")
    shown = {s.id for s in [main[0], *more, *context]}
    caveats = [c for c in guide.by_role("limitation") if c.id not in shown][:1]
    if caveats:
        lines.append(f"Worth knowing: “{_q(caveats[0].text)}”")
    terms = [glossary.BY_ID[t].term for t in _central_terms(guide, 3) if t not in _defined(state)][:2]
    if terms:
        lines.append("If terms like " + " or ".join(f"*{t}*" for t in terms)
                     + " are unfamiliar, ask me, or say “explain it simply”.")
    entry["shown"] = [s.id for s in [main[0], *more, *context]]
    state["last_terms"] = _central_terms(guide, 4)
    return "\n\n".join(lines)


def simple(guide: app_guide.Guide, state: dict, app_id: str) -> str:
    entry = _state(state, guide, app_id)
    lead = guide.lead
    terms = _fresh_terms(guide, state)
    if not lead:
        return overview(guide, state, app_id)
    lines = []
    category = terms[0].category if terms else (
        glossary.BY_ID[_central_terms(guide, 1)[0]].category if _central_terms(guide, 1) else "")
    if terms or category:
        background = [glossary.CATEGORIES[category].context] if category else []
        lines.append("**The background, in general terms:** " + " ".join(background))
        if terms:
            lines.append("\n".join(f"- {_definition(t, why=i == 0)}" for i, t in enumerate(terms)))
    lines.append(f"**What {_q(guide.name)} does, according to its description:** "
                 + _claim(guide, lead).replace(_name(guide), "it", 1).replace("it’s description says", "it says"))
    caveats = _caveats(guide, 1)
    if caveats and caveats[0].id not in entry["shown"]:
        lines.append(f"One limitation it states: “{_q(caveats[0].text)}”")
    _defined(state).extend(t.id for t in terms)
    entry["shown"] = list(dict.fromkeys([*entry["shown"], lead.id]))
    state["last_shown"] = [lead.id]
    state["last_terms"] = [t.id for t in terms]
    return "\n\n".join(lines) + "\n\nWould a practical example help?"


def example(guide: app_guide.Guide, state: dict, app_id: str) -> str:
    """Concrete cases from the description first, then a labelled illustrative scenario.

    Each request shows something not shown before: source cases once, then the
    scenario for the next concept that has one.
    """
    entry = _state(state, guide, app_id)
    entry.setdefault("examples", [])
    lines = []
    schemes = [s for s in guide.by_role("scheme") if s.id not in entry["shown"]][:2]
    if schemes:
        lines.append(f"**From {_q(guide.name)}’s description**, these specific cases:\n"
                     + "\n".join(f"- “{_q(s.text)}”" for s in schemes))
    illustrative = next((glossary.BY_ID[t] for t in _central_terms(guide, 8)
                         if glossary.BY_ID[t].example and t not in entry["examples"]), None)
    if illustrative:
        lines.append(f"**An illustrative scenario** (made up to show the idea of *{illustrative.term}*, not taken "
                     f"from the App’s description): {glossary.sentence(illustrative.example)}")
        entry["examples"].append(illustrative.id)
    workflow = [s for s in guide.by_role("context") if s.id not in entry["shown"]][:2]
    if workflow and not schemes:
        lines.insert(0, "**How it is used, according to its description:**\n"
                     + "\n".join(f"- “{_q(s.text)}”" for s in workflow))
        schemes = workflow
    lead = guide.lead
    if lead and lines and lead.id not in state.get("last_shown", []):
        lines.append(f"**Where {_q(guide.name)} fits, per its description:** "
                     + _claim(guide, lead).replace(_name(guide), "it", 1))
    if not lines:
        return ""
    entry["shown"] = list(dict.fromkeys([*entry["shown"], *(s.id for s in schemes)]))
    state["last_shown"] = [s.id for s in schemes] + ([lead.id] if lead else [])
    state["last_terms"] = [illustrative.id] if illustrative else []
    return "\n\n".join(lines)


def analogy(guide: app_guide.Guide, state: dict, app_id: str) -> str:
    candidates = [glossary.BY_ID[t] for t in _central_terms(guide, 6) if glossary.BY_ID[t].analogy]
    if not candidates or not guide.lead:
        return ""
    term = candidates[0]
    lines = [f"Here’s another way to picture it. In general, **{term.term}** means {term.plain}. "
             f"{glossary.sentence(term.analogy)} *(This is an analogy for the idea, not a description of the App.)*"]
    if guide.lead.id not in state.get("last_shown", []):
        lines.append(f"With that picture in mind: {_claim(guide, guide.lead)}")
    if len(candidates) > 1:
        other = candidates[1]
        lines.append(f"Similarly, for **{other.term}**: {glossary.sentence(other.analogy)}")
    state["last_terms"] = [t.id for t in candidates[:2]]
    state["last_shown"] = [guide.lead.id]
    _defined(state).extend(t.id for t in candidates[:2])
    return "\n\n".join(lines)


def how(guide: app_guide.Guide, state: dict, app_id: str) -> str:
    steps = [s for s in guide.statements if s.role in {"purpose", "capability", "scheme", "context"}
             and (s.terms or s.role == "context")][:4]
    if len(steps) < 2 or not any(s.role in {"scheme", "context"} for s in steps):
        return ""
    lines = [f"Here’s how {_q(guide.name)} works, step by step, as its description puts it:",
             "\n".join(f"{i}. “{_q(s.text)}”" for i, s in enumerate(steps, 1))]
    terms = _fresh_terms(guide, state, 2)
    if terms:
        lines.append("\n".join(f"- {_definition(t)}" for t in terms))
        _defined(state).extend(t.id for t in terms)
    state["last_terms"] = [t.id for t in terms]
    return "\n\n".join(lines)


def term(phrase: str, guides: list[app_guide.Guide], state: dict) -> str:
    entry = glossary.lookup(phrase)
    if not entry:
        return ""
    lines = [f"**{entry.term[:1].upper() + entry.term[1:]}**, in general, means {entry.plain}."]
    if entry.why:
        lines[0] += " " + glossary.sentence(entry.why)
    if entry.example:
        lines.append(f"For example: {glossary.sentence(entry.example)}")
    for guide in guides[:1]:
        used = next((s for s in guide.statements if entry.id in s.terms), None)
        if used:
            lines.append(f"In {_q(guide.name)}’s description it appears here: “{_q(used.text)}”")
        else:
            lines.append(f"{_q(guide.name)}’s description doesn’t use this term.")
    related = [glossary.BY_ID[r].term for r in entry.related if r in glossary.BY_ID and r not in _defined(state)]
    if related:
        lines.append("Related ideas: " + ", ".join(f"*{r}*" for r in related[:3]) + ".")
    _defined(state).append(entry.id)
    state["last_terms"] = [entry.id]
    return "\n\n".join(lines)


def _areas(guide: app_guide.Guide) -> list[str]:
    return list(dict.fromkeys(glossary.BY_ID[t].category for t in _central_terms(guide, 4)))


def compare(guides: list[app_guide.Guide], state: dict, *, choose: bool = False) -> str:
    """What each App does, side by side; 'choose' turns the same evidence into a decision guide."""
    leads = [(g, g.lead) for g in guides]
    if any(lead is None for _, lead in leads):
        return ""
    areas = [_areas(g) for g in guides]
    shared = set(areas[0]).intersection(*map(set, areas[1:])) if areas[0] else set()
    names = " and ".join(_name(g) for g in guides) if len(guides) == 2 else ", ".join(_name(g) for g in guides)
    overlap = ("" if shared else " Their descriptions don’t overlap, so they aren’t alternatives to each other.")
    just_compared = state.get("last_act") == "compare" and state.get("last_apps") == [g.name for g in guides]
    if choose:
        lines = ["**It depends on the job you need done:**",
                 "\n".join(f"- Choose **{_q(g.name)}** if {_phrase(g, lead)}." for g, lead in leads)]
        if overlap:
            lines.append(overlap.strip())
        if not just_compared:
            notes = [f"{_q(g.name)}: “{_q(c.text)}”" for g in guides for c in _caveats(g, 1)]
            if notes:
                lines.append("**Before deciding, note:** " + " ".join(notes))
        lines.append("If you describe the task in your own words, I’ll check it against "
                     + ("both descriptions." if len(guides) == 2 else "their descriptions."))
    else:
        if shared:
            label = glossary.CATEGORIES[next(a for a in areas[0] if a in shared)].label
            lines = [f"{names} are both about {label}, but they do different things:"]
        else:
            labels = [glossary.CATEGORIES[a[0]].label for a in areas if a]
            lines = [f"{names} do different jobs" + (f" in different areas ({' and '.join(labels)})"
                                                     if len(labels) == len(guides) else "") + ":"]
        lines.append("\n".join(f"- {_claim(g, lead)}" for g, lead in leads))
        # Concepts documented for only one of them make a close comparison concrete.
        differences = []
        for g in guides:
            own = [t for st in g.main[:3] for t in st.terms]
            others = {t for other in guides if other is not g for st in other.main[:3] for t in st.terms}
            unique = [glossary.BY_ID[t].term for t in dict.fromkeys(own) if t not in others][:3]
            if unique:
                differences.append(f"only {_q(g.name)}’s description covers " + ", ".join(f"*{u}*" for u in unique))
        if differences and shared and len(guides) == 2:
            lines.append("The difference in short: " + "; ".join(differences) + ".")
        elif overlap:
            lines.append(overlap.strip())
        notes = [f"{_q(g.name)}: “{_q(c.text)}”" for g in guides for c in _caveats(g, 1)]
        if notes:
            lines.append("**Worth knowing:** " + " ".join(notes))
        terms = list(dict.fromkeys(t for g in guides for t in _central_terms(g, 2) if t not in _defined(state)))
        lines.append(("I can explain " + ", ".join(f"*{glossary.BY_ID[t].term}*" for t in terms[:3]) + ", or tell"
                      if terms else "Tell") + " me what you need to do and I’ll check which description covers it.")
        state["last_terms"] = terms[:3]
    state["last_act"], state["last_apps"] = "compare", [g.name for g in guides]
    return "\n\n".join(lines)


def facts(guide: app_guide.Guide, app: dict, question: str) -> str:
    """Provider and access, from the source record, in one answer."""
    lines = []
    if re.search(r"\b(?:who|provider|provides|developed|makes|operates|vendor)\b", question, re.I):
        lines.append(f"{_name(guide)} is provided by **{_q(guide.provider)}**." if guide.provider
                     else f"No provider is listed for {_name(guide)}.")
    if re.search(r"\b(?:access|use it|get started|start using|log ?in|sign ?up|install|open|url|link)\b", question, re.I):
        access = guide.by_role("access")
        urls = list(dict.fromkeys(u.rstrip(".,;)") for s in access for u in re.findall(r"https?://[^\s<>\"\\]+", s.quote)
                                  if not re.search(r"[\[\]()]", u.rstrip(".,;)"))))
        notes = [s.text for s in access if not re.search(r"https?://", s.text)]
        if urls or notes:
            lines.append("**Access**, according to its Store entry:" + "".join(f"\n- “{_q(n)}”" for n in notes)
                         + "".join(f"\n- [{u}]({u})" for u in urls[:3]))
        else:
            lines.append("Its description doesn’t say how to access it. You can open its Store entry from the "
                         "App card, and the provider can confirm how to get access.")
    return "\n\n".join(lines)


def prepared(act: str, question: str, apps: list[dict], state: dict, *, phrase: str = "") -> tuple[str, str]:
    """(message, act actually used); an empty message means this act has nothing to add."""
    guides = [app_guide.build(app) for app in apps]
    if act == "term":
        return term(phrase, guides, state), "term"
    if act in {"compare", "choose"}:
        return (compare(guides, state, choose=act == "choose") if len(guides) > 1 else ""), act
    if not guides:
        return "", act
    guide, app_id = guides[0], apps[0]["id"]
    entry = _state(state, guide, app_id)
    if act == "facts":
        return facts(guide, apps[0], question), act
    if act in {"differently", "meaning"}:
        # A different representation each time; never the same overview again.
        for candidate in [a for a in LADDER[1:] if a not in entry["used"]]:
            message = globals()[candidate](guide, state, app_id)
            if message:
                entry["used"].append(candidate)
                return message, candidate
        return "", act
    message = globals()[act](guide, state, app_id)
    if message:
        entry["used"].append(act)
    return message, act


# --- Model-assisted answers -------------------------------------------------

SYSTEM = (
    "You are ExpertAI, a friendly guide to the HEDGE-IoT App Store. Answer the latest question in plain "
    "English for someone without technical background, in at most 80 words.\n"
    "- App facts come only from the numbered statements; cite them like [S2]. Never add features, users, "
    "integrations, guarantees, prices or access conditions they don't state.\n"
    "- You may explain general ideas in your own words, as general background, not as App features.\n"
    "- Keep stated limitations. If the statements don't answer the question, say so and say what they cover.\n"
    "- Don't decide whether an App meets a requirement. No headings or links."
)
_RISKY = re.compile(r"\b(?:guarantee\w*|certif\w*|complian\w*|free of charge|integrat\w*|automatic\w*|"
                    r"real[- ]time|machine learning|artificial intelligence|ai-powered|encrypt\w*|secure\w*)\b", re.I)
_CITATION = re.compile(r"\s*\[(S\d+(?:\s*,\s*S\d+)*)\]")
_SENTENCE_END = re.compile(r"(?<=[.!?])(?:\s*\[S\d+(?:\s*,\s*S\d+)*\])?\s+")
_BUDGET = {"statements": 5, "background": 3, "previous": 240}


def _relevant(guide: app_guide.Guide, question: str, limit: int) -> list[app_guide.Statement]:
    """The lead, then the statements sharing most with the question; one limitation at most."""
    asked = evidence_terms(question)
    scored = sorted((s for s in guide.statements if s.role not in {"access", "attribution"}),
                    key=lambda s: -len(asked & evidence_terms(s.text)))
    chosen = [s for s in guide.main[:1]]
    chosen += [s for s in scored if s not in chosen and asked & evidence_terms(s.text)]
    limitations = [s for s in guide.by_role("limitation") if s not in chosen][:1]
    return list(dict.fromkeys(chosen[:limit - len(limitations)] + limitations))[:limit]


def _prompt(question: str, guides: list[app_guide.Guide], history: list[dict]):
    """A small prompt: prompt reading, not generation, dominates CPU latency on this hardware."""
    sources, payload = {}, []
    for guide in guides:
        statements = {}
        for statement in _relevant(guide, question, _BUDGET["statements"] if len(guides) == 1 else 3):
            key = f"S{len(sources) + 1}"
            sources[key] = (guide, statement)
            statements[key] = statement.text
        payload.append({"app": guide.name, "statements": statements})
    terms = list(dict.fromkeys(glossary.mentioned(question) + [t for g in guides for t in _central_terms(g, 2)]))
    background = {glossary.BY_ID[t].term: glossary.BY_ID[t].plain for t in terms[:_BUDGET["background"]]}
    # The previous answer gives "that"/"it" a referent; it is not evidence.
    previous = next((" ".join(str(m.get("content", "")).split()) for m in reversed(history)
                     if m.get("role") == "assistant"), "")[:_BUDGET["previous"]]
    data = {"apps": payload, "background": background, "previous_answer": previous, "question": question}
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False, separators=(",", ":"))}]
    grounds = " ".join([question, previous, *background.values(), *(s.text for _, s in sources.values())])
    return messages, sources, grounds


def _sentence_problems(sentence: str, sources: dict, grounds: str) -> list[str]:
    problems = []
    cited = [k for group in _CITATION.findall(sentence) for k in re.split(r"\s*,\s*", group)]
    if any(k not in sources for k in cited):
        problems.append("citations")
    text = _CITATION.sub("", sentence)
    if re.search(r"https?://|<[a-z/]|\]\(", text, re.I):
        problems.append("markup")
    if set(re.findall(r"\d+(?:[.,]\d+)?", text)) - set(re.findall(r"\d+(?:[.,]\d+)?", grounds)):
        problems.append("quantity")
    if {m.casefold() for m in _RISKY.findall(text)} - {m.casefold() for m in _RISKY.findall(grounds)}:
        problems.append("unsupported_claim")
    return problems


class _Gate:
    """Release model text one checked sentence at a time; stop at the first ungrounded one."""

    def __init__(self, sources: dict, grounds: str, emit=None):
        self.sources, self.grounds, self.emit = sources, grounds, emit
        self.raw, self.released, self.cited, self.problems = "", [], [], []

    def feed(self, chunk: str) -> None:
        self.raw += chunk
        while not self.problems:
            match = _SENTENCE_END.search(self.raw)
            if not match:
                return
            self._release(self.raw[:match.end()])
            self.raw = self.raw[match.end():]
        raise _Ungrounded()

    def finish(self) -> None:
        if self.raw.strip() and not self.problems:
            self._release(self.raw)
        self.raw = ""

    def _release(self, sentence: str) -> None:
        problems = _sentence_problems(sentence, self.sources, self.grounds)
        if problems:
            self.problems = problems
            raise _Ungrounded()
        self.cited += [k for group in _CITATION.findall(sentence) for k in re.split(r"\s*,\s*", group)]
        text = _q(_CITATION.sub("", sentence).strip())  # model text is untrusted: no markup of its own
        if text:
            text = ("" if not self.released else " ") + text
            self.released.append(text)
            if self.emit:
                self.emit(text)

    @property
    def text(self) -> str:
        return "".join(self.released)


class _Ungrounded(Exception):
    pass


def open_answer(question: str, apps: list[dict], history: list[dict], *, on_delta=None) -> dict:
    """One bounded, cited model answer; never a recommendation or new evidence.

    With on_delta, checked sentences are released as they are generated. A
    sentence failing a check stops the answer there; without streaming the
    whole answer falls back. Released text is never withdrawn.
    """
    settings = Settings()
    guides = [app_guide.build(app) for app in apps]
    messages, sources, grounds = _prompt(question, guides, history)
    gate = _Gate(sources, grounds, on_delta)
    started = time.monotonic()
    try:
        streamed = []
        text = OllamaClient().chat_text(messages, max_tokens=settings.STORE_EXPLANATION_TOKENS,
                                        context_tokens=settings.STORE_MODEL_CONTEXT_TOKENS,
                                        timeout=settings.STORE_MODEL_TIMEOUT_SECONDS,
                                        deadline=started + settings.STORE_MODEL_TIMEOUT_SECONDS,
                                        on_delta=lambda chunk: (streamed.append(chunk), gate.feed(chunk)))
        if not streamed:
            gate.feed(text)
        gate.finish()
    except _Ungrounded:
        pass
    except Exception:
        if not gate.released:
            return {"completed": False, "reason": "model_unavailable"}
        gate.problems = gate.problems or ["incomplete"]
    elapsed = time.monotonic() - started
    stats = {"seconds": elapsed, "prompt_chars": sum(len(m["content"]) for m in messages)}
    if not gate.released or not on_delta and (gate.problems or not gate.cited):
        return {"completed": False, "reason": "ungrounded_answer", "checks": gate.problems or ["citations"], **stats}
    message = gate.text
    if gate.problems:
        message += " …\n\n*(I stopped there: I couldn’t ground the rest in the description.)*"
    basis = [sources[k] for k in dict.fromkeys(gate.cited)][:2] or [(g, g.lead) for g in guides[:1] if g.lead]
    label = "From" if gate.cited else "For reference, from"
    message += "\n\n" + "\n".join(f"*{label} {_q(g.name)}’s description:* “{_q(s.text)}”" for g, s in basis)
    return {"completed": True, "message": message, "streamed": gate.text if on_delta else "", **stats,
            "cited": bool(gate.cited), "stopped": gate.problems,
            "evidence": [{"app": g.name, "path": s.path, "quote": s.quote} for g, s in basis]}


def _unclear(guide: app_guide.Guide, state: dict) -> str:
    terms = [glossary.BY_ID[t].term for t in _central_terms(guide, 3)]
    options = ", ".join(f"*{t}*" for t in terms[:2]) + (f", or what {_q(guide.name)} does with them" if terms else "")
    return ("I’ve explained it a few different ways now. Which part is still unclear"
            + (f": {options}?" if terms else "?") + " Tell me, and I’ll focus on just that.")


def _without_model(act: str, question: str, apps: list[dict], state: dict, phrase: str) -> str:
    guides = [app_guide.build(app) for app in apps]
    if act in {"differently", "meaning"} and guides:
        return _unclear(guides[0], state)
    if act == "example" and guides and guides[0].lead:
        return (f"{_q(guides[0].name)}’s description doesn’t include a worked example, and I don’t have a "
                f"general one ready for this topic. What it documents: {_claim(guides[0], guides[0].lead)}")
    if act == "term":
        lines = [f"I don’t have a reliable general definition of “{_q(phrase)}”."]
        for guide in guides[:1]:
            used = next((s for s in guide.statements if phrase.casefold() in s.text.casefold()), None)
            lines.append(f"{_q(guide.name)}’s description uses it here: “{_q(used.text)}”" if used else
                         f"{_q(guide.name)}’s description doesn’t use that term.")
        return " ".join(lines)
    if guides and guides[0].lead:
        names = " and ".join(_name(g) for g in guides)
        documented = "\n".join(f"- {_claim(g, g.lead)}" for g in guides if g.lead)
        return (f"I can’t reason through that specific situation right now, so here is what the description"
                f"{'s' if len(guides) > 1 else ''} of {names} document{'' if len(guides) > 1 else 's'}:\n"
                f"{documented}\n\nIf you name a specific capability you need, I can check it against the description.")
    return ""


def respond(act: str, question: str, apps: list[dict], state: dict, history: list[dict],
            phrase: str = "", *, on_delta=None) -> dict:
    """Prepared explanation, else one bounded model answer, else an honest fallback."""
    settings = Settings()
    message, used = prepared(act, question, apps, state, phrase=phrase) if act in PREPARED_ACTS else ("", act)
    if message:
        return {"message": message, "act": used, "state": _bounded(state), "generation": {
            "source": "prepared", "reason": f"explanation_{used}", "model_completed": False}}
    model = settings.STORE_SEMANTIC_ENABLED and settings.STORE_EXPLANATIONS_ENABLED
    if model and apps:
        asked = question
        if act in {"differently", "meaning"}:
            asked = (f"{question} — The user is still confused after the earlier explanations in the conversation. "
                     "Explain the App's main idea once more from a new angle, with one everyday comparison, "
                     "in simpler words than before.")
        elif act == "example":
            asked = (f"{question} — Give one short, clearly hypothetical everyday example of using this App, "
                     "built only from what its statements document.")
        elif act == "term":
            asked = f"What does “{phrase}” mean in general, and how is it used in this App's description? ({question})"
        answer = open_answer(asked, apps, history, on_delta=on_delta)
        if answer.get("completed"):
            return {"message": answer["message"], "act": "open", "state": _bounded(state), "generation": {
                "source": "ollama", "reason": "explanation_open", "model_completed": True, "model_calls": 1,
                "model": settings.OLLAMA_MODEL, "explanation_seconds": answer["seconds"],
                "prompt_chars": answer["prompt_chars"], "cited": answer["cited"], "stopped": answer["stopped"],
                "evidence": answer["evidence"]}}
        fallback_reason = answer.get("reason")
    else:
        fallback_reason = "model_disabled"
    return {"message": _without_model(act, question, apps, state, phrase), "act": act, "state": _bounded(state),
            "generation": {"source": "prepared", "reason": f"explanation_{act}_fallback",
                           "model_completed": False, "model_fallback": fallback_reason}}


def _bounded(state: dict) -> dict:
    apps = state.get("apps", {})
    state["apps"] = dict(list(apps.items())[-5:])
    state["defined"] = list(dict.fromkeys(state.get("defined", [])))[-30:]
    return state
