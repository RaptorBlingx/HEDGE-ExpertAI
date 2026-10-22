"""Find the Store Apps a message names, however the user spells them.

Publishers write names freely ("EdgeConnect", "Edge-Connect", "e-Flex Hub") and
users type them freely ("edge connect", "e flex hub", "Turbine watch"). A name is
matched on its letters and digits alone, ignoring case, spacing and punctuation,
with a one- or two-letter typo tolerated in long names. Other names the App's
own source gives it (its data-space listing name, an acronym of a multi-word
name that its source uses) count too, and so does its provider's name
("TNO's app"). Native App IDs stay exact and case-sensitive.

This module only finds mentions. Which App a pronoun or ordinal refers to, and
what the user wants done, are decided elsewhere.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WORD = re.compile(r"[^\W_]+")
_MAX_WINDOW = 5
# Short or very common-looking names need the exact spelling the publisher used.
_EXACT_CASE_BELOW = 6
# A provider shared by many Apps ("Authored evaluation fixture") names no subject.
_MAX_PROVIDER_APPS = 3
_SOURCE_NAMES = ("dataspaceAppDescription.properties.name",)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def compact(text: str) -> str:
    """Letters and digits only: "Edge-Connect" and "edge connect" are the same name."""
    return "".join(_WORD.findall(_fold(text)))


def _distance(a: str, b: str, limit: int) -> int:
    """Damerau-Levenshtein distance, stopping early above limit."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous2, previous = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            if previous2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                current[j] = min(current[j], previous2[j - 2] + 1)
        if min(current) > limit:
            return limit + 1
        previous2, previous = previous, current
    return previous[-1]


def _tolerance(length: int) -> int:
    return 0 if length < 7 else 1 if length < 12 else 2


@dataclass(frozen=True)
class Mention:
    start: int
    end: int
    text: str
    app_ids: tuple[str, ...]
    kind: str  # "id", "name", "provider", or "id_case" (a native ID with the wrong case)

    @property
    def ambiguous(self) -> bool:
        return len(self.app_ids) != 1


@dataclass(frozen=True)
class _Alias:
    key: str          # compact form
    written: str      # as the publisher wrote it, for exact-case aliases
    app_id: str
    kind: str


class AppLinker:
    """Mentions of the given Apps in free text."""

    def __init__(self, apps: list[dict]):
        self.apps = {app["id"]: app for app in apps}
        aliases: list[_Alias] = []
        for app in apps:
            source = app.get("source_evidence", {})
            names = [app.get("name") or ""] + [str(source.get(p) or "") for p in _SOURCE_NAMES]
            for name in dict.fromkeys(n.strip() for n in names if n and n.strip()):
                aliases += [_Alias(compact(form), form, app["id"], "name")
                            for form in _forms(name) if compact(form)]
                acronym = _acronym(name)
                if acronym and re.search(rf"(?<!\w){acronym}(?!\w)", _source_text(app)):
                    aliases.append(_Alias(compact(acronym), acronym, app["id"], "name"))
        providers: dict[str, list[str]] = {}
        for app in apps:
            if app.get("provider"):
                providers.setdefault(app["provider"].strip(), []).append(app["id"])
        for provider, ids in providers.items():
            if len(ids) <= _MAX_PROVIDER_APPS and compact(provider):
                aliases += [_Alias(compact(provider), provider, i, "provider") for i in ids]
        self._aliases: dict[str, list[_Alias]] = {}
        for alias in aliases:
            self._aliases.setdefault(alias.key, []).append(alias)
        self._fuzzy = [key for key in self._aliases if _tolerance(len(key))]

    def mentions(self, text: str) -> list[Mention]:
        """Non-overlapping mentions, longest first; exact native IDs win."""
        found: list[Mention] = []
        taken: list[tuple[int, int]] = []
        for app in self.apps.values():
            for match in re.finditer(rf"(?<!\w){re.escape(app['app_id'])}(?!\w)", text, re.I):
                exact = match[0] == app["app_id"]
                ids, kind = ((app["id"],), "id") if exact else ((), "id_case")
                found.append(Mention(match.start(), match.end(), match[0], ids, kind))
                taken.append(match.span())
        tokens = [m for m in _WORD.finditer(text)]
        candidates = []
        for size in range(min(_MAX_WINDOW, len(tokens)), 0, -1):
            for i in range(len(tokens) - size + 1):
                window = tokens[i:i + size]
                start, end = window[0].start(), window[-1].end()
                surface = text[start:end]
                key = compact(surface)
                aliases = self._match(key, surface)
                if aliases:
                    candidates.append((start, end, aliases))
        for start, end, aliases in candidates:
            if any(start < e and s < end for s, e in taken):
                continue
            # "TNO's app" names TNO's Apps; the possessive and noun are part of the reference.
            tail = re.match(r"(?:['’]s)?(?:\s+(?:app|apps|application|one|tool))?\b",
                            text[end:], re.I)
            if aliases[0].kind == "provider" and tail and tail.end():
                end += tail.end()
            ids = tuple(dict.fromkeys(a.app_id for a in aliases))
            kind = "name" if any(a.kind == "name" for a in aliases) else "provider"
            if kind == "name":
                ids = tuple(dict.fromkeys(a.app_id for a in aliases if a.kind == "name"))
            found.append(Mention(start, end, text[start:end], ids, kind))
            taken.append((start, end))
        return sorted(found, key=lambda m: m.start)

    def _match(self, key: str, surface: str) -> list[_Alias]:
        exact = [a for a in self._aliases.get(key, [])
                 if len(key) >= _EXACT_CASE_BELOW or a.written == surface
                 or a.kind == "provider" and surface.casefold() == a.written.casefold()]
        if exact or not _tolerance(len(key)):
            return exact
        limit = _tolerance(len(key))
        near = [k for k in self._fuzzy if abs(len(k) - len(key)) <= limit and k[0] == key[0]
                and _distance(key, k, limit) <= limit]
        return [a for k in near for a in self._aliases[k] if a.kind == "name"]


def _forms(name: str) -> list[str]:
    """The name, and its leading part before a listing's slogan ("EdgeConnect-the best service")."""
    forms = [name]
    head = re.split(r"\s+[-–—:|]\s+|(?<=[a-z0-9])-(?=the\b|a\b|your\b)", name, maxsplit=1)[0]
    if head != name and len(compact(head)) >= 4:
        forms.append(head)
    return forms


def _acronym(name: str) -> str:
    words = _WORD.findall(name)
    letters = "".join(w[0] for w in words if w[0].isalpha()).upper()
    return letters if len(words) >= 3 and len(letters) == len(words) else ""


def _source_text(app: dict) -> str:
    values = [app.get("description") or "", *app.get("source_evidence", {}).values()]
    return " ".join(str(v) for v in values)
