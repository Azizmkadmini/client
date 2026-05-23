"""Découpage des champs mot-clé / hashtag (plusieurs termes en une saisie)."""

from __future__ import annotations

import re

_SPLIT_RE = re.compile(r"[,;\n\r]+")
_HASHTAG_TOKEN_RE = re.compile(r"#([\w.]+)", re.UNICODE)


def split_scraper_queries(raw: str, *, mode: str = "keyword") -> list[str]:
    """
    Retourne une liste de requêtes distinctes.

    Séparateurs : virgule, point-virgule, saut de ligne.
    Les espaces seuls ne séparent pas (« founder saas » reste une recherche).

    Mode ``hashtag`` : si des ``#tag`` sont présents, chaque tag est une requête
    (ex. ``#startup #marketing``). Sinon même découpage que keyword (sans ``#`` en tête).
    """
    text = (raw or "").strip()
    if not text:
        return []

    if mode == "hashtag":
        tags = _HASHTAG_TOKEN_RE.findall(text)
        if tags:
            return _dedupe_preserve_order(tag.strip().lstrip("#") for tag in tags if tag.strip())

    parts = _SPLIT_RE.split(text)
    if len(parts) == 1 and parts[0].strip() == text:
        return _dedupe_preserve_order([_normalize_single_query(parts[0].strip(), mode)])

    out: list[str] = []
    for part in parts:
        q = part.strip()
        if not q:
            continue
        out.append(_normalize_single_query(q, mode))
    return _dedupe_preserve_order(out)


def _normalize_single_query(q: str, mode: str) -> str:
    if mode == "hashtag":
        return q.lstrip("#").strip()
    return q


def _dedupe_preserve_order(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
