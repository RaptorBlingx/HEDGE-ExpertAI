"""Automatic English source preparation; no model calls or per-App rules.

This is extractive preparation, not semantic review. Complete source sentences
remain the facts. A small grammar derives a task phrase only from an explicit
purpose statement; unknown phrasing stays intact. No inferred capabilities.
"""
from __future__ import annotations

import re
from typing import Any

VERSION = 2
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
                        r"may|might|could|planned|future|pilot|experimental)\b", re.I)


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
            candidates.append((priority, path, passage))
    candidates.sort(key=lambda c: c[0], reverse=True)
    unique = []
    for _, path, passage in candidates:
        if passage not in [v["quote"] for v in unique]:
            unique.append({"path": path, "quote": passage, "en": passage})
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
    return {"version": 2, "preparer_version": VERSION,
            "review": {"method": "source_extraction", "reviewer": "deterministic-preparer",
                       "note": "Complete source passages; no semantic or human review claimed."},
            "en": {"summary": summary, "simple": simple, "use_when": task or summary},
            "task_phrase": bool(task), "noun_task": noun_task, "facts": facts}
