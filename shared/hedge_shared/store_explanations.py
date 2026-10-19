"""Automatic English source preparation; no model calls or per-App rules.

This is extractive preparation, not semantic review. Complete source sentences
remain the facts. A small grammar derives a task phrase only from an explicit
purpose statement; unknown phrasing stays intact. No inferred capabilities.
"""
from __future__ import annotations

import re
from typing import Any

VERSION = 3
# Exclude operational headings, navigation, obvious instructions and links, not
# negative capability statements: limitations must remain attached to facts.
_NOISE = re.compile(r"https?://|release (?:version|type|notes)|^product:|"
                    r"ignore\b.{0,100}\binstructions|system prompt|"
                    r"\byou are (?:an?|the)\b|[<>\[\]]",
                    re.I)
_PURPOSE = re.compile(r"^(?:used to |(?:this (?:app|platform|service)\s+|.{1,90}?\s+)"
                      r"(?:facilitates|provides|supports|enables|allows|helps|is designed to)\s+)",
                      re.I)
_QUALIFIER = re.compile(r"\b(?:not|no|only|unless|except|although|however|requires?|must|"
                        r"may|might|could|planned|future|pilot|experimental|if|when|after|before|depends|"
                        r"will|would|possible|disabled|unsupported|unavailable|simulation|prototype|"
                        r"licensed|subscription|paid)\b", re.I)


_PASSIVES = {"combined": "combines", "merged": "merges", "aggregated": "aggregates",
             "collected": "collects", "stored": "stores", "exported": "exports",
             "validated": "validates", "processed": "processes", "published": "publishes"}


def plain_english(text: str) -> str:
    """Small lexical explanations; never used as recommendation evidence."""
    for pattern, replacement in (
        (r"\bshared data models and mappings\b",
         "data definitions and the links between them"),
        (r"\bshared data models\b", "shared data definitions"),
        (r"\bpublish\b", "share"), (r"\bmanage\b", "organise"),
        (r"\bbids\b", "offers"), (r"\bbid\b", "offer"),
        (r"\baggregators\b", "participants"),
        (r"\bonboarding and certification of users\b",
         "setting up users and checking their requirements"),
    ):
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text


def short_purpose(task: str) -> str:
    """Condense explicit coordinated actions without adding a new benefit."""
    verbs = {'publish': 'shared', 'manage': 'kept organised', 'monitor': 'tracked',
             'validate': 'checked', 'collect': 'collected', 'export': 'exported'}
    match = re.fullmatch(r"(" + "|".join(verbs) + r") and (" + "|".join(verbs) +
                         r") (.+)", task.rstrip('.'), re.I)
    if not match:
        return ''
    objects = plain_english(match[3])
    objects = objects.replace('the links between them', 'their connections')
    return (objects[0].upper() + objects[1:] + ', ' + verbs[match[1].lower()] +
            ' and ' + verbs[match[2].lower()] + '.')


def linked_passage(previous: str, sentence: str, name: str) -> dict[str, str]:
    """Bind an explicit current-App statement to its adjacent passive reference.

    No arbitrary sentence concatenation: require a named/current-App actor, an
    affirmative service predicate, and the same plural object. Explicit other
    actors, qualifications and negation remain outside this small grammar.
    """
    if (_QUALIFIER.search(previous + " " + sentence) or _NOISE.search(previous + " " + sentence)
            or re.search(r"\b(?:another app|other apps?|external service|by)\b",
                         previous + " " + sentence, re.I)):
        return {}
    actor = re.escape(name) + "|" if name else ""
    if not re.search(r"(?:^|: )(?:" + actor + r"the (?:app|platform|service|system)) "
                     r"(?:now )?(?:provides|supports|offers|deploys|collects|handles)\b",
                     previous, re.I):
        return {}
    passive = re.match(r"^(?:Those|These|Such) (?P<object>[\w-]+) are (?:then |now )?"
                       r"(?P<verb>" + "|".join(_PASSIVES) + r")\b(?P<tail>.*)$", sentence, re.I)
    if not passive or not re.search(r"\b" + re.escape(passive['object']) + r"\b", previous, re.I):
        return {}
    origin = re.search(r"\b" + re.escape(passive['object']) +
                       r" (?:coming )?from (?P<source>[^.!?]+)[.!]?$", previous, re.I)
    if not origin:
        return {}
    # Summarise only the understood assertion. Unknown tails may contain a
    # requirement; never discard them while composing an unconditional claim.
    if not re.fullmatch(
        r"(?:, according to (?:multiple |several )?available [\w -]{1,80})?"
        r"(?: and sent (?:under|as|to) [\w -]{1,80})?[.!]?", passive['tail'], re.I,
    ):
        return {}
    simple = "It " + _PASSIVES[passive['verb'].lower()] + " " + passive['object'].lower()
    simple += " from " + origin['source'].rstrip(".") + "."
    # Preserve a separately asserted delivery destination. Never infer an output
    # type from a common channel/licence: the noun must repeat the combined object.
    delivery = re.search(r"\band sent (?P<prep>under|as|to) (?P<target>[^.!?]+)[.!]?$",
                         passive['tail'], re.I)
    short = ""
    if delivery:
        target = delivery['target'].strip()
        simple = simple[:-1] + ", then sends them " + delivery['prep'] + " " + target + "."
        object_word = passive['object'].lower().rstrip('s')
        if (passive['verb'].lower() in {'combined', 'merged', 'aggregated'}
                and re.match(r"a common ", target, re.I)
                and re.search(r"\b" + re.escape(object_word) + r"s?\b", target, re.I)):
            simple = simple.replace("sends them under ", "sends them as ")
            short = ("It " + _PASSIVES[passive['verb'].lower()] + " multiple " +
                     passive['object'].lower())
            scope = re.search(r"\bin one ([\w-]+)$", origin['source'], re.I)
            if scope:
                short += " within one " + scope[1]
            short += " into " + re.sub(r"^a common ", "one ", target, flags=re.I) + "."
    return {"en": simple, "simple_en": plain_english(simple),
            "short_en": plain_english(short or simple)}


def extract(evidence: dict[str, str], name: str = "") -> dict[str, Any]:
    candidates = []
    for path, text in evidence.items():
        if path not in {"readme", "description", "dataspaceAppDescription.properties.description"}:
            continue
        # HTML has already been normalized upstream. Keep the original substring
        # exactly, including internal whitespace; no arbitrary truncation.
        sentences = []
        for match in re.finditer(r"[^\n]+?(?:[.!?](?=\s|$)|(?=\n|$))", text):
            raw = match.group()
            sentence = raw.strip()
            if sentence:
                start = match.start() + len(raw) - len(raw.lstrip())
                sentences.append((sentence, start, match.end()))
        for i, (sentence, start, _end) in enumerate(sentences):
            if not 20 <= len(sentence) <= 700 or _NOISE.search(sentence):
                continue
            passage = sentence
            if i + 1 < len(sentences) and _QUALIFIER.search(sentences[i + 1][0]):
                passage = text[start:sentences[i + 1][2]].strip()
            if len(passage) > 900 or _NOISE.search(passage):
                # A paragraph boundary can split an adjacent qualification. Never
                # silently omit it to obtain a shorter or more positive statement.
                continue
            named_purpose = bool(name and re.match(
                re.escape(name) + r"(?: now)? (?:facilitates|provides|supports|enables|deploys)\b",
                sentence, re.I))
            priority = (3 if named_purpose else 2 if sentence.lower().startswith("used to ")
                        else 1 if _PURPOSE.search(sentence) else 0,
                        path == "readme", -len(sentence))
            candidates.append((priority, path, passage, {}))
            linked = linked_passage(sentences[i - 1][0], sentence, name) if i else {}
            if linked:
                quote = text[sentences[i - 1][1]:_end].strip()
                if len(quote) <= 900:
                    candidates.append((priority, path, quote, linked))
    candidates.sort(key=lambda c: c[0], reverse=True)
    unique = []
    for _, path, passage, rendering in candidates:
        if passage not in [v["quote"] for v in unique]:
            unique.append({"path": path, "quote": passage, "en": passage,
                           "qualified": bool(_QUALIFIER.search(passage)), **rendering})
    if not unique:
        # Sparse Store Apps may expose only the established structured feature
        # list. Attribute those labels without fabricating a purpose/workflow.
        for path, label in evidence.items():
            if (re.fullmatch(r"dataspaceAppDescription\.properties\.featureList\[\d+\]", path)
                    and label not in {"true", "false", "null"}
                    and re.search(r"[^\W\d_]", label)
                    and 3 <= len(label) <= 180 and not _NOISE.search(label)
                    and not _QUALIFIER.search(label)):
                unique.append({"path": path, "quote": label,
                               "en": "Features include " + label.rstrip(".") + "."})
    if not unique:
        return {}
    facts = unique[:20]
    summary = facts[0]["en"]
    task = ""
    noun_task = False
    # Infinitive purpose statements have an explicit task boundary. Other
    # constructions retain their full original sentence instead of guessing.
    if not _QUALIFIER.search(summary):
        match = re.match(r"^Used to (.+?)[.!]?$", summary, re.I)
        if not match:
            match = re.match(r"^(?:This (?:app|platform|service)|" + re.escape(name) +
                             r") (?:is designed to|helps (?:users |you )?to) (.+?)[.!]?$",
                             summary, re.I) if name else None
        if match:
            task = match[1].rstrip(".! ")
    if not task and name and not _QUALIFIER.search(summary):
        nominal = re.match(re.escape(name) + r" (?:facilitates|provides) (.+?)[.!]?$",
                           summary, re.I)
        if nominal:
            first = nominal[1].split(",", 1)[0].strip()
            if len(first) >= 10 and not re.search(r"\b(?:which|that|when|if|but)\b", first, re.I):
                task, noun_task = first, True
    if task:
        simple = (("It helps with " if noun_task else "It helps you ") +
                  task[0].lower() + task[1:] + ".")
    else:
        simple = summary
    if not _QUALIFIER.search(simple):
        simple = plain_english(simple)
    short = short_purpose(task) if task and not noun_task else ""
    return {"version": 2, "preparer_version": VERSION,
            "review": {"method": "source_extraction", "reviewer": "deterministic-preparer",
                       "note": "Complete source passages; no semantic or human review claimed."},
            "en": {"summary": summary, "simple": simple, "use_when": task or summary},
            "task_phrase": bool(task), "noun_task": noun_task,
            "short_simple_en": short, "facts": facts}
