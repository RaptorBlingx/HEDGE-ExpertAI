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

from . import answers, app_guide
from .evidence import terms as evidence_terms
from .llm_client import OllamaClient
from .recommender import _quoted_store_text

# Each App is explained through progressively different representations.
# "Explain it differently" moves to the next one not yet used for that App.
LADDER = ("overview", "simple", "analogy", "example", "how")
PREPARED_ACTS = {*LADDER, "term", "compare", "choose", "differently", "meaning", "audience", *answers.FIELDS}
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


def _state(state: dict, app_id: str) -> dict:
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
    entry = _state(state, app_id)
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
    entry = _state(state, app_id)
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
    entry = _state(state, app_id)
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


def audience(guide: app_guide.Guide, state: dict, app_id: str) -> str:
    """Who an App is for: the roles its description names, else a labelled general note."""
    roles = [glossary.BY_ID[r] for r in guide.roles]
    if roles:
        def plural(term):
            return term if term.acronym else re.sub(r"y$", "ie", term.term) + "s"
        names = [f"**{plural(r)}**" for r in roles[:4]]
        lines = ["Its description names these roles: " + (", ".join(names[:-1]) + " and " + names[-1]
                                                          if len(names) > 1 else names[0]) + "."]
        lines.append("\n".join(f"- {_definition(r)}" for r in roles[:4] if r.id not in _defined(state)))
        naming = next((s for s in guide.statements if set(s.terms) & set(guide.roles) and s.owned), None)
        if naming:
            lines.append(f"For example, it says: “{_q(naming.text)}”")
        _defined(state).extend(r.id for r in roles[:4])
        return "\n\n".join(line for line in lines if line)
    if not guide.lead:
        return ""
    category = glossary.BY_ID[_central_terms(guide, 1)[0]].category if _central_terms(guide, 1) else ""
    users = glossary.CATEGORIES[category].users if category else ""
    people = guide.by_role("context")[:1]
    answer = (f"{_name(guide)}’s description doesn’t say who uses it. It describes what it does: "
              + _claim(guide, guide.lead).replace(_name(guide), "it", 1).replace("it’s description says", "it says"))
    if people:
        answer += f" It also mentions: “{_q(people[0].text)}”"
    if users:
        answer += (f"\n\nIn general, tools for {glossary.CATEGORIES[category].label} are used by {users}. "
                   "*(General background, not a statement about this App.)*")
    return answer


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


_LAYERS = {"overview": overview, "simple": simple, "analogy": analogy, "example": example, "how": how,
           "audience": audience}


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
    entry = _state(state, app_id)
    if act in answers.FIELDS:
        return answers.fact_answer(act, apps), act
    if act in {"differently", "meaning"}:
        # A different representation each time; never the same overview again.
        for candidate in [a for a in LADDER[1:] if a not in entry["used"]]:
            message = _LAYERS[candidate](guide, state, app_id)
            if message:
                entry["used"].append(candidate)
                return message, candidate
        return "", act
    message = _LAYERS[act](guide, state, app_id)
    if message:
        entry["used"].append(act)
    return message, act


# --- Model-assisted answers -------------------------------------------------

SYSTEM = (
    "You are ExpertAI, a friendly guide to the HEDGE-IoT App Store. Answer the latest question in plain "
    "English for someone without technical background, in at most 80 words.\n"
    "- App facts come only from the numbered statements and the listed provider; cite statements like [S2]. "
    "Never add features, users, "
    "integrations, guarantees, prices or access conditions they don't state.\n"
    "- You may explain general ideas in your own words, as general background, not as App features.\n"
    "- Don't add benefits, outcomes, customers or industries the statements don't mention; mark any example "
    "as hypothetical. Avoid words like ensures or guarantees.\n"
    "- Keep stated limitations. If the statements don't say something (such as who uses it, accuracy or price), "
    "say so first; any reasoning after that is general, not about this App.\n"
    "- Don't decide whether an App meets a requirement and don't start with Yes or No. No headings or links."
)
_RISKY = re.compile(r"\b(?:guarantee\w*|certif\w*|complian\w*|free of charge|integrat\w*|automatic\w*|"
                    r"real[- ]time|machine learning|artificial intelligence|ai-powered|encrypt\w*|secure\w*)\b", re.I)
_CITATION = re.compile(r"\s*\[(S\d+(?:\s*,\s*S\d+)*)\]")
_MARKER = re.compile(r"\s*\[(?:background|general|bg|b\d+)[^\]]{0,20}\]", re.I)  # not statement keys
_SENTENCE_END = re.compile(r"(?<=[.!?])(?:\s*\[S\d+(?:\s*,\s*S\d+)*\])?\s+")
# Whole statements only, never cut: a budget chooses fewer and shorter ones instead.
_BUDGET = {"statements": 4, "long_statement": 260, "short_description": 420, "background": 2, "previous": 200}


def _concepts(question: str, guide: app_guide.Guide) -> set[str]:
    """Glossary concepts a question is about, by name or by meaning ("who gets paid?" -> settlement)."""
    words = evidence_terms(question)
    related = {t for t in guide.terms if words & evidence_terms(glossary.BY_ID[t].plain + " " + glossary.BY_ID[t].why)}
    return set(glossary.mentioned(question)) | related


def _relevant(guide: app_guide.Guide, question: str, limit: int) -> list[app_guide.Statement]:
    """Whole short statements: all of them for a short description, else the most relevant."""
    candidates = [s for s in guide.statements if s.role not in {"access", "attribution"}
                  and len(s.text) <= _BUDGET["long_statement"]]
    if sum(len(s.text) for s in candidates) <= _BUDGET["short_description"]:
        return candidates
    asked, concepts = evidence_terms(question), _concepts(question, guide)

    def score(s):
        return len(asked & evidence_terms(s.text)) + 2 * len(concepts & set(s.terms))

    scored = sorted(candidates, key=lambda s: (-score(s), len(s.text)))
    chosen = [s for s in guide.main[:1]]
    chosen += [s for s in scored if s not in chosen and score(s)]
    limitations = [s for s in guide.by_role("limitation") if s not in chosen and s in candidates][:1]
    return list(dict.fromkeys(chosen[:limit - len(limitations)] + limitations))[:limit]


def _prompt(question: str, guides: list[app_guide.Guide], history: list[dict]):
    """A small prompt: prompt reading, not generation, dominates CPU latency on this hardware."""
    sources, payload = {}, []
    for guide in guides:
        statements = {}
        for statement in _relevant(guide, question, _BUDGET["statements"] if len(guides) == 1 else 2):
            key = f"S{len(sources) + 1}"
            sources[key] = (guide, statement)
            statements[key] = statement.text
        # The Store record's provider is a fact too ("who runs it?").
        payload.append({"app": guide.name, **({"provider": guide.provider} if guide.provider else {}),
                        "statements": statements})
    terms = list(dict.fromkeys(glossary.mentioned(question) + [t for g in guides for t in _central_terms(g, 2)]))
    background = {glossary.BY_ID[t].term: glossary.BY_ID[t].plain for t in terms[:_BUDGET["background"]]}
    # The previous answer gives "that" a referent; it is not evidence. Every
    # prompt character costs reading time, so include it only when referred to.
    refers = re.search(r"\b(?:that|this|those|these|differently|again|still)\b", question, re.I)
    previous = next((" ".join(str(m.get("content", "")).split()) for m in reversed(history)
                     if m.get("role") == "assistant"), "")[:_BUDGET["previous"]] if refers else ""
    data = {"apps": payload, "background": background, "previous_answer": previous, "question": question}
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False, separators=(",", ":"))}]
    # Only source statements and the curated glossary notes can ground a claim:
    # the user's wording and earlier (generated) answers never do.
    grounds = " ".join([*background.values(), *(s.text for _, s in sources.values()),
                        *(g.provider for g in guides if g.provider)])
    # A negative claim about an App needs a stated limitation of that App.
    limits = {"names": [g.name for g in guides],
              "terms": set().union(*[evidence_terms(s.text) for g in guides for s in g.by_role("limitation")])}
    return messages, sources, grounds, limits


_NEGATED = re.compile(r"\b(?:does not|doesn't|do not|don't|cannot|can't|is not|isn't|won't|will not|never|"
                      r"no longer|lacks?)\b", re.I)


# "The statements do not say how accurate it is" is about the description, not the App.
_META = re.compile(r"\b(?:statements?|description|information|details?|sources?)\b.{0,30}(?:\bnot\b|n't)|"
                   r"(?:\bnot\b|n't)\s+(?:say|mention|state|specify|document|describe|include|indicate|cover)", re.I)


def _negative_claim(text: str, limits: dict) -> bool:
    """An App-subject negation ("X itself does not handle payments") no stated limitation supports."""
    if not limits or not _NEGATED.search(text) or _META.search(text):
        return False
    names = [n for n in limits["names"] if n]
    subject = any(n.casefold() in text.casefold() for n in names) or re.search(
        r"\b(?:it|itself|the app)\s+(?:also\s+)?(?:does not|doesn't|cannot|can't|is not|isn't|won't|will not|never|lacks?)\b",
        text, re.I)
    if not subject:
        return False
    claimed = evidence_terms(_NEGATED.sub(" ", text)) - set().union(*[evidence_terms(n) for n in names])
    return not claimed & limits["terms"]


def _sentence_problems(sentence: str, sources: dict, grounds: str, limits: dict | None = None) -> list[str]:
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
    if _negative_claim(text, limits or {}):
        problems.append("unsupported_negation")
    return problems


class _Gate:
    """Release model text one checked sentence at a time; stop at the first ungrounded one."""

    def __init__(self, sources: dict, grounds: str, emit=None, limits: dict | None = None):
        self.sources, self.grounds, self.emit, self.limits = sources, grounds, emit, limits
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
        problems = _sentence_problems(sentence, self.sources, self.grounds, self.limits)
        if problems:
            self.problems = problems
            raise _Ungrounded()
        self.cited += [k for group in _CITATION.findall(sentence) for k in re.split(r"\s*,\s*", group)]
        text = _MARKER.sub("", _CITATION.sub("", sentence)).strip()
        if not self.released:
            # Suitability verdicts belong to the verifier, not to an explanation.
            text = re.sub(r"^(?:yes|no)\s*[,.!]\s*", "", text, flags=re.I)
            text = text[:1].upper() + text[1:]
        text = _q(text)  # model text is untrusted: no markup of its own
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
    messages, sources, grounds, limits = _prompt(question, guides, history)
    gate = _Gate(sources, grounds, on_delta, limits)
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
    # Streamed or not, the reply is the checked sentences before the first failure.
    if not gate.released:
        return {"completed": False, "reason": "ungrounded_answer", "checks": gate.problems or ["empty"], **stats}
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
    # An open question: the statements that bear on it, quoted, rather than a refusal.
    return answers.extractive_answer(question, apps) if apps else ""


def respond(act: str, question: str, apps: list[dict], state: dict, history: list[dict],
            phrase: str = "", *, on_delta=None) -> dict:
    """Prepared explanation, else one bounded model answer, else an honest fallback."""
    settings = Settings()
    message, used = prepared(act, question, apps, state, phrase=phrase) if act in PREPARED_ACTS else ("", act)
    if message:
        return {"message": message, "act": used, "state": _bounded(state), "generation": {
            "source": "prepared", "reason": f"explanation_{used}", "model_completed": False}}
    # After every prepared representation, a targeted question helps more than a
    # slow generated paraphrase (observed live: a muddled analogy after 39 s).
    model = settings.STORE_SEMANTIC_ENABLED and settings.STORE_EXPLANATIONS_ENABLED and act not in {
        "differently", "meaning"}
    if model and apps:
        asked = question
        if act == "example":
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
        checks = answer.get("checks", [])
    else:
        checks = []
        fallback_reason = "model_disabled" if act not in {"differently", "meaning"} else "clarification"
    return {"message": _without_model(act, question, apps, state, phrase), "act": act, "state": _bounded(state),
            "generation": {"source": "prepared", "reason": f"explanation_{act}_fallback",
                           "model_completed": False, "model_fallback": fallback_reason,
                           **({"model_checks": checks} if checks else {})}}


def _bounded(state: dict) -> dict:
    apps = state.get("apps", {})
    state["apps"] = dict(list(apps.items())[-5:])
    state["defined"] = list(dict.fromkeys(state.get("defined", [])))[-30:]
    return state
