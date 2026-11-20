"""Intégrations de modèles configurables.

- demo      : aucun appel externe, aucun coût. Les agents utilisent des générateurs locaux
              déterministes (clairement étiquetés « MODE DÉMO » dans l'interface).
- anthropic : API Claude (clé ANTHROPIC_API_KEY requise, facturée séparément de tout abonnement claude.ai).
- ollama    : modèle local via un serveur Ollama installé par l'utilisateur (gratuit, hors-ligne).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from .. import db
from ..core import ConfigRequired, StudioError, get_settings, log

# Prix USD par million de jetons (entrée, sortie) — à vérifier sur la page tarifaire officielle.
ANTHROPIC_PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-2": (8.0, 40.0),
}


def provider_status() -> dict[str, Any]:
    s = get_settings()
    return {
        "active": s["llm_provider"],
        "demo": {"ready": True, "label": "Mode démo local (gratuit, sans IA)"},
        "anthropic": {
            "ready": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "label": "API Claude (Anthropic)",
            "model": s["anthropic_model"],
            "note": "Nécessite une clé API de la console Anthropic ; facturation à l'usage, "
                    "distincte d'un abonnement claude.ai.",
        },
        "ollama": {"ready": None, "label": "Ollama local", "model": s["ollama_model"], "url": s["ollama_url"]},
    }


def month_spend() -> float:
    start = datetime.now(timezone.utc).strftime("%Y-%m-01")
    r = db.row("SELECT COALESCE(SUM(cost_usd),0) AS t FROM cost_ledger WHERE ts >= ?", (start,))
    return float(r["t"]) if r else 0.0


def episode_spend(episode_id: int | None) -> tuple[float, int]:
    if episode_id is None:
        return 0.0, 0
    r = db.row("SELECT COALESCE(SUM(cost_usd),0) AS t, COUNT(*) AS n FROM cost_ledger WHERE episode_id=?"
               " AND provider != 'demo'", (episode_id,))
    return float(r["t"]), int(r["n"])


def _check_limits(episode_id: int | None) -> None:
    s = get_settings()
    if month_spend() >= float(s["budget_monthly_usd"]):
        raise StudioError("Budget mensuel atteint : génération bloquée. Ajustez le budget dans Paramètres.",
                          code="budget")
    spent, calls = episode_spend(episode_id)
    if spent >= float(s["budget_episode_usd"]):
        raise StudioError("Budget de l'épisode atteint : génération bloquée.", code="budget")
    if calls >= int(s["max_llm_calls_per_episode"]):
        raise StudioError("Quota d'appels IA de l'épisode atteint.", code="quota")


def _record(provider: str, model: str, episode_id: int | None, purpose: str, tin: int, tout: int,
            cost: float) -> None:
    db.execute("INSERT INTO cost_ledger(ts, provider, model, episode_id, purpose, input_tokens, output_tokens, cost_usd)"
               " VALUES(?,?,?,?,?,?,?,?)", (db.now(), provider, model, episode_id, purpose, tin, tout, cost))


def generate_json(system: str, prompt: str, schema: dict[str, Any], *, purpose: str,
                  episode_id: int | None = None, provider: str | None = None) -> tuple[dict[str, Any], dict]:
    """Appelle le fournisseur configuré et renvoie (objet JSON, métadonnées)."""
    s = get_settings()
    provider = provider or s["llm_provider"]
    if provider == "demo":
        raise StudioError("Le fournisseur démo n'appelle pas de modèle.", code="demo")
    _check_limits(episode_id)
    if provider == "anthropic":
        return _anthropic(system, prompt, schema, purpose, episode_id, s)
    if provider == "ollama":
        return _ollama(system, prompt, schema, purpose, episode_id, s)
    raise ConfigRequired(f"Fournisseur inconnu : {provider}")


def _anthropic(system, prompt, schema, purpose, episode_id, s):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ConfigRequired("Configuration requise : ajoutez une clé ANTHROPIC_API_KEY dans Paramètres.")
    import anthropic

    client = anthropic.Anthropic(timeout=float(s["llm_timeout_s"]), max_retries=2)
    model = s["anthropic_model"]
    kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": s["anthropic_effort"], "format": {"type": "json_schema", "schema": schema}},
    )
    try:
        if s.get("anthropic_fallbacks", True):
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            response = client.messages.create(**kwargs)
    except anthropic.AuthenticationError as e:
        raise ConfigRequired(f"Clé API Anthropic refusée : {e.message}") from e
    except anthropic.RateLimitError as e:
        raise StudioError(f"Limite de débit Anthropic atteinte, réessayez plus tard : {e.message}",
                          code="rate_limit") from e
    except anthropic.APIStatusError as e:
        raise StudioError(f"Erreur de l'API Anthropic ({e.status_code}) : {e.message}", code="api") from e
    except anthropic.APIConnectionError as e:
        raise StudioError(f"Connexion à l'API Anthropic impossible : {e}", code="network") from e

    usage = response.usage
    tin, tout = int(usage.input_tokens or 0), int(usage.output_tokens or 0)
    pin, pout = ANTHROPIC_PRICES.get(response.model, ANTHROPIC_PRICES.get(model, (4.0, 20.0)))
    cost = tin / 1e6 * pin + tout / 1e6 * pout
    _record("anthropic", response.model, episode_id, purpose, tin, tout, cost)
    if response.stop_reason == "refusal":
        raise StudioError("Le modèle a refusé cette demande (refus de sécurité). Reformulez l'intention.",
                          code="refusal")
    if response.stop_reason == "max_tokens":
        raise StudioError("Réponse tronquée (limite de jetons). Réduisez la durée de l'épisode.", code="truncated")
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise StudioError("Réponse du modèle illisible (JSON invalide).", code="bad_json") from e
    log("llm.call", f"Claude ({response.model}) — {purpose} : {tin}+{tout} jetons, {cost:.4f} $",
        episode_id=episode_id)
    return data, {"provider": "anthropic", "model": response.model, "cost_usd": cost}


def _ollama(system, prompt, schema, purpose, episode_id, s):
    import httpx

    url = s["ollama_url"].rstrip("/") + "/api/chat"
    body = {"model": s["ollama_model"], "stream": False, "format": schema,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
    try:
        r = httpx.post(url, json=body, timeout=float(s["llm_timeout_s"]))
    except httpx.HTTPError as e:
        raise ConfigRequired(f"Configuration requise : serveur Ollama injoignable à {s['ollama_url']} ({e}).") from e
    if r.status_code != 200:
        raise StudioError(f"Ollama a répondu {r.status_code} : {r.text[:300]}", code="api")
    payload = r.json()
    content = payload.get("message", {}).get("content", "")
    _record("ollama", s["ollama_model"], episode_id, purpose, int(payload.get("prompt_eval_count", 0)),
            int(payload.get("eval_count", 0)), 0.0)
    try:
        return json.loads(content), {"provider": "ollama", "model": s["ollama_model"], "cost_usd": 0.0}
    except ValueError as e:
        raise StudioError("Réponse Ollama illisible (JSON invalide).", code="bad_json") from e
