"""Idées du moment (idée TrendForge) : flux public Google Actualités, filtré par série.

Toujours partir d'un fait réel donne des épisodes moins fades : le titre sert d'étincelle, puis
l'agent le transforme en FICTION dans les règles de la série (jamais de personnes réelles mises en cause).
Les sujets sensibles (décès, violences, drames, politique, accusations, rumeurs) sont écartés.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any

from .core import StudioError

KEYWORDS = {
    "horror": {"fr": "paranormal", "en": "paranormal OR unexplained"},
    "football": {"fr": "football", "en": "football tactics OR Premier League"},
    "isekai": {"fr": "anime OR manga", "en": "anime OR fantasy"},
}
SENSIBLE = re.compile(
    r"\b(mort|morts|décès|décédé\w*|tué\w*|meurtre\w*|assassin\w*|attentat\w*|guerre|otage\w*|victime\w*|"
    r"blessé\w*|accident\w*|viol\w*|suicide|agression\w*|arrest\w*|inculp\w*|accus\w*|procès|condamn\w*|"
    r"scandale|rumeur\w*|élection\w*|président\w*|ministre\w*|gouvernement|politique|died|dead|death|killed|"
    r"murder\w*|shooting|attack\w*|war|victim\w*|crash|arrest\w*|charged|accus\w*|lawsuit|election\w*|president)\b",
    re.I)
_cache: dict[str, tuple[float, list]] = {}
TTL = 1800


def _fetch(url: str) -> bytes:
    import httpx

    r = httpx.get(url, timeout=15, follow_redirects=True,
                  headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) MultiverseStudio/1.0"})
    if r.status_code != 200:
        raise StudioError(f"Flux indisponible ({r.status_code}).")
    return r.content


def _rss(xml: bytes, source: str, limit: int) -> list[dict[str, Any]]:
    items = []
    root = ET.fromstring(xml)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        pub = ""
        src = it.find("source")
        if src is not None and src.text:
            pub = src.text.strip()
            title = re.sub(rf"\s+-\s+{re.escape(pub)}$", "", title)
        items.append({"title": title, "link": (it.findtext("link") or "").strip(), "source": pub or source,
                      "date": (it.findtext("pubDate") or "").strip(), "flagged": bool(SENSIBLE.search(title))})
        if len(items) >= limit:
            break
    return items


def ideas(series_id: str, lang: str = "fr", limit: int = 12) -> dict[str, Any]:
    key = f"{series_id}:{lang}"
    now = time.time()
    if key in _cache and now - _cache[key][0] < TTL:
        return {"items": _cache[key][1], "cached": True}
    from urllib.parse import quote_plus

    q = quote_plus(KEYWORDS.get(series_id, {}).get(lang, "") + " when:7d")
    loc = "hl=fr&gl=FR&ceid=FR:fr" if lang == "fr" else "hl=en-US&gl=US&ceid=US:en"
    news = f"https://news.google.com/rss/search?q={q}&{loc}"
    items, errors = [], []
    for url, src, n in ((news, "Google Actualités", limit),):
        try:
            items += _rss(_fetch(url), src, n)
        except Exception as e:
            errors.append(f"{src} : {e}")
    safe = [i for i in items if not i["flagged"]]
    _cache[key] = (now, safe)
    return {"items": safe, "filtered": len(items) - len(safe), "errors": errors, "cached": False}


def intent_from(title: str, series_name: str) -> str:
    return (f"S'inspirer librement de l'actualité « {title} » et la transformer en fiction pour {series_name}, "
            "avec nos personnages et nos règles (aucune personne réelle).")
