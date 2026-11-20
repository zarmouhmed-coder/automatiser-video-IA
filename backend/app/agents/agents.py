"""Agents : trois scénaristes spécialisés + un directeur/critique.

Chaque scénariste a ses consignes (configs/<série>.json) et sa mémoire (bible validée,
épisodes récents, votes validés, notes du directeur). Le critique ne modifie jamais le script :
il produit un rapport. Le fournisseur (démo, Claude, Ollama) se règle dans Paramètres.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .. import bible
from ..core import get_settings
from ..llm import providers
from . import demo_writer
from .schema import (LOCATIONS, critique_schema, normalize_script, observer_schema, scene_schema,
                     script_duration, script_schema)

CONFIG_DIR = Path(__file__).parent / "configs"


def agent_config(name: str) -> dict[str, Any]:
    return json.loads((CONFIG_DIR / f"{name}.json").read_text(encoding="utf-8"))


def all_agents() -> list[dict[str, Any]]:
    return [agent_config(n) for n in ("horror", "football", "isekai", "critic")]


def _provider() -> str:
    return get_settings()["llm_provider"]


def _vote_rule(ep: dict) -> str:
    return {0: "INTERDIT : ne termine pas sur un vote.",
            1: "Autorisé seulement si un vrai dilemme existe (pas systématique).",
            2: "OBLIGATOIRE : termine sur un vote court (2 à 4 options de moins de 25 caractères)."}[int(ep["allow_vote"])]


def _writer_prompt(ep: dict, mem: dict, extra: str = "") -> str:
    chars = ", ".join(f"{c['id']} ({c['name']})" for c in mem["characters"])
    return (
        f"MÉMOIRE DE LA SÉRIE (canon validé uniquement) :\n{json.dumps(mem, ensure_ascii=False, indent=1)}\n\n"
        f"ÉPISODE n°{ep['number']} — durée cible : {ep['duration_s']} secondes (somme des durées des plans).\n"
        f"Intention du réalisateur : {ep['intent']}\n"
        f"Style demandé : {ep.get('style') or 'selon la direction artistique de la série'}\n"
        f"Vote de fin : {_vote_rule(ep)}\n"
        f"Lieux disponibles : {', '.join(LOCATIONS[ep['series_id']])}\n"
        f"Identifiants de personnages disponibles : {chars}. Utilise exactement ces identifiants.\n"
        "Plans de 1,5 à 6 secondes, 3 scènes environ, maximum 3 personnages par plan.\n"
        f"{_style_hint(ep)}"
        f"{extra}"
    )


def _style_hint(ep: dict) -> str:
    from .. import inspiration

    st = inspiration.style_for(ep)
    if not st:
        return ""
    hint = f"Inspiration de style choisie par le réalisateur : {st.get('description', '')}."
    if st.get("avg_shot_s"):
        hint += f" Vise des plans d'environ {st['avg_shot_s']} s."
    if st.get("hook_pattern"):
        hint += f" Accroche (2 premières secondes) selon ce motif : {st['hook_pattern']}."
    if st.get("structure"):
        hint += " Structure à suivre : " + " → ".join(
            f"{p.get('part')}" + (f" ({p['pattern']})" if p.get("pattern") else "") for p in st["structure"]) + "."
    if st.get("tone"):
        hint += f" Ton : {st['tone']}."
    return hint + " (Ne reprends aucun contenu de la référence : seulement le rythme et l'énergie.)\n"


# ------------------------------------------------------------------ scénaristes

def write_script(ep: dict, note: str = "", seed: int = 0) -> tuple[dict, dict]:
    mem = bible.writer_memory(ep["series_id"])
    provider = _provider()
    if provider == "demo":
        script = demo_writer.generate(ep, mem, seed=seed)
        meta = {"provider": "demo", "model": "gabarits locaux", "cost_usd": 0.0,
                "note": "MODE DÉMO : scénario assemblé à partir de gabarits, sans IA."
                        + (" La note du réalisateur est enregistrée mais n'est pas interprétée en mode démo." if note else "")}
    else:
        cfg = agent_config(ep["series_id"])
        extra = f"Note du réalisateur à appliquer : {note}\n" if note else ""
        script, meta = providers.generate_json(cfg["system_prompt"], _writer_prompt(ep, mem, extra),
                                               script_schema(ep["series_id"]), purpose="script",
                                               episode_id=ep["id"])
    return normalize_script(script, ep["series_id"]), meta


def rewrite_scene(ep: dict, script: dict, scene_index: int, note: str, seed: int) -> tuple[dict, dict]:
    mem = bible.writer_memory(ep["series_id"])
    provider = _provider()
    if provider == "demo":
        scene = demo_writer.regenerate_scene(ep, mem, script, scene_index, seed)
        meta = {"provider": "demo", "model": "gabarits locaux", "cost_usd": 0.0,
                "note": "MODE DÉMO : variante tirée des gabarits (la note n'est pas interprétée)."}
    else:
        cfg = agent_config(ep["series_id"])
        extra = (f"SCRIPT ACTUEL :\n{json.dumps(script, ensure_ascii=False)}\n\n"
                 f"Réécris UNIQUEMENT la scène {scene_index + 1} (id {script['scenes'][scene_index]['id']}). "
                 f"Garde la continuité avec les scènes voisines. Note du réalisateur : {note or 'améliorer la scène'}\n")
        scene, meta = providers.generate_json(cfg["system_prompt"], _writer_prompt(ep, mem, extra),
                                              scene_schema(ep["series_id"]), purpose="scene", episode_id=ep["id"])
    new = json.loads(json.dumps(script))
    new["scenes"][scene_index] = scene
    return normalize_script(new, ep["series_id"]), meta


# ------------------------------------------------------------------ critique

FLAT_LINES = {"ok", "d'accord", "oui", "non", "bon", "bon.", "ok.", "oui.", "non.", "très bien", "allons-y", "quoi ?"}
TENSION_WORDS = {
    "horror": ["voix", "ombre", "bruit", "porte", "derrière", "nuit", "sang", "disparu", "enregistrement", "?"],
    "football": ["minute", "but", "poteau", "pressing", "élan", "maintien", "duel", "crampes", "carton", "!"],
    "isekai": ["système", "mana", "niveau", "effac", "danger", "mort", "carte", "choix", "!"],
}
STOP = set("dans avec pour plus mais tout tous cette comme elle elles nous vous leur leurs sans sous être avoir "
           "était sont faire fait encore jamais toujours quelque chose rien".split())


def hook_score(script: dict) -> dict[str, Any]:
    """Note de l'accroche (idée TrendForge) : ce qui se passe dans les ~3 premières secondes."""
    first, t = [], 0.0
    for sc in script["scenes"]:
        for sh in sc["shots"]:
            if t < 3.0:
                first.append(sh)
            t += sh["duration"]
    txt = " ".join((sh["text"] + " " + sh["caption"] + " " + sh["narration"]) for sh in first)
    checks = {
        "texte ou réplique visible": bool(txt.strip()),
        "question, chiffre ou mot fort": bool(re.search(r"\?|\d|!|jamais|personne|mort|secret|interdit|dernier", txt, re.I)),
        "effet sonore d'ouverture": any(sh["sfx"] for sh in first),
        "personnage ou mouvement de caméra": any(sh["characters"] or sh["camera"] in ("push_in", "shake", "pan_left",
                                                                                    "pan_right") for sh in first),
        "premier plan court (≤ 3 s)": bool(first) and first[0]["duration"] <= 3.0,
    }
    score = round(sum(checks.values()) * 2)
    return {"score": score, "checks": checks, "missing": [k for k, v in checks.items() if not v],
            "text": txt.strip()[:160]}


def heuristic_critique(ep: dict, script: dict) -> dict[str, Any]:
    """Analyse locale réelle (gratuite) : rythme, répétitions, cohérence avec la bible, tension."""
    series = ep["series_id"]
    cmap = bible.character_map(series)
    issues: list[dict] = []
    words: Counter[str] = Counter()
    reveals = 0
    total = script_duration(script)
    shots = [(sc, sh) for sc in script["scenes"] for sh in sc["shots"]]

    def add(sc, sh, typ, sev, msg, sug):
        issues.append({"scene": sc["id"] if sc else "", "shot": sh["id"] if sh else "", "type": typ,
                       "severity": sev, "message": msg, "suggestion": sug})

    if shots:
        sc0, first = shots[0]
        if first["duration"] > 3.5 and not (first["caption"] or first["text"] or first["sfx"]):
            add(sc0, first, "rythme", "forte", "Accroche lente : le premier plan n'a ni texte, ni son, ni action.",
                "Ouvrir sur une image anormale, une phrase choc ou un effet sonore dès la première seconde.")
    if abs(total - ep["duration_s"]) > 0.2 * ep["duration_s"]:
        add(None, None, "rythme", "moyenne", f"Durée {total:.0f}s pour une cible de {ep['duration_s']}s.",
            "Raccourcir ou ajouter des plans pour respecter la durée cible.")
    prev_text = ""
    for sc, sh in shots:
        txt = sh["text"]
        if sh["kind"] == "reveal":
            reveals += 1
        if sh["duration"] > 5.5 and not (txt or sh["narration"] or sh["caption"]) and sh["kind"] not in ("pause", "establishing"):
            add(sc, sh, "rythme", "moyenne", "Plan long sans texte ni intention dramatique (plan vide).",
                "Le raccourcir, ou le transformer en pause dramatique assumée avec un son.")
        if txt:
            if txt.lower().strip(" .!?") in {f.strip(" .!?") for f in FLAT_LINES} or len(txt.split()) < 3:
                add(sc, sh, "dialogue_plat", "faible", f"Réplique peu porteuse : « {txt} ».",
                    "Donner une intention, un sous-texte ou une information nouvelle.")
            if len(txt) > 90:
                add(sc, sh, "lisibilite", "moyenne", "Réplique trop longue pour un sous-titre mobile.",
                    "Couper en deux répliques de moins de 90 caractères.")
            if txt == prev_text:
                add(sc, sh, "repetition", "moyenne", "Réplique identique à la précédente.", "Varier la formulation.")
            prev_text = txt
            for w in re.findall(r"[a-zàâçéèêëîïôûùüÿœ']{5,}", txt.lower()):
                if w not in STOP:
                    words[w] += 1
        if sh["speaker"]:
            if sh["speaker"] not in cmap:
                add(sc, sh, "incoherence", "forte", f"Personnage inconnu de la bible : {sh['speaker']}.",
                    "Utiliser un personnage existant ou le proposer comme nouveau personnage (validation requise).")
            elif sh["speaker"] not in [c["id"] for c in sh["characters"]] and not sh["narration"]:
                add(sc, sh, "lisibilite", "faible", "Le personnage qui parle n'est pas à l'écran.",
                    "L'ajouter au plan ou indiquer qu'il parle hors champ.")
        for c in sh["characters"]:
            if c["id"] not in cmap:
                add(sc, sh, "incoherence", "forte", f"Personnage absent de la bible : {c['id']}.",
                    "Corriger l'identifiant ou proposer ce personnage pour validation.")
            elif cmap[c["id"]]["status"] != "canon":
                add(sc, sh, "canon", "moyenne", f"{cmap[c['id']]['name']} n'est pas encore canon.",
                    "Valider le personnage dans la bible avant production.")
    for w, n in words.most_common(5):
        if n >= 3:
            add(None, None, "repetition", "faible", f"Le mot « {w} » revient {n} fois.", "Varier le vocabulaire.")
    if series == "horror" and reveals > 1:
        add(None, None, "canon", "forte", f"{reveals} révélations majeures : la bible en autorise une seule.",
            "Garder une révélation et transformer l'autre en indice.")
    if series == "football":
        techs = {e["name"].upper(): e["data"].get("porteur") for e in bible.full_bible(series)["entries"]
                 if e["kind"] == "technique"}
        for sc, sh in shots:
            for name, owner in techs.items():
                if name in sh["caption"].upper() and owner and owner not in [c["id"] for c in sh["characters"]]:
                    add(sc, sh, "incoherence", "forte", f"{name} utilisée sans son porteur ({owner}) à l'écran.",
                        "Montrer le porteur de la technique ou retirer la technique.")
            if sh["kind"] == "technique" and "ÉLAN" not in sh["caption"].upper() and "/" not in sh["caption"]:
                add(sc, sh, "canon", "moyenne", "Technique montrée sans son coût (Jauge d'Élan ou limite d'usage).",
                    "Afficher le coût dans la caption (ex. « ÉLAN -30 »).")
    if series == "isekai":
        for sc in script["scenes"]:
            n_sys = sum(1 for sh in sc["shots"] if sh["kind"] == "system")
            if n_sys > 1 and not any("OBSERVATEUR" in sh["caption"].upper() for sh in sc["shots"]):
                add(sc, None, "canon", "faible", "Plusieurs fenêtres du Système dans la même scène.",
                    "Limiter à une fenêtre du Système par scène.")
    all_text = " ".join((sh["text"] + " " + sh["caption"] + " " + sh["narration"]).lower() for _, sh in shots)
    tension_hits = sum(all_text.count(w) for w in TENSION_WORDS[series])
    if tension_hits < 3:
        add(None, None, "tension", "moyenne", "Peu de marqueurs de tension dans les dialogues.",
            "Ajouter un enjeu explicite, un compte à rebours ou une menace.")
    if script["ending"]["type"] == "resolution":
        add(None, None, "tension", "faible", "Fin résolue : aucune raison de revenir à l'épisode suivant.",
            "Terminer sur une question ouverte, une révélation ou un dilemme.")
    if script["ending"]["type"] == "vote":
        for o in script["ending"]["vote_options"]:
            if len(o) > 25:
                add(None, None, "lisibilite", "moyenne", f"Option de vote trop longue : « {o} ».",
                    "Moins de 25 caractères par option.")

    hook = hook_score(script)
    if hook["score"] < 6:
        add(shots[0][0] if shots else None, shots[0][1] if shots else None, "tension", "moyenne",
            f"Accroche faible ({hook['score']}/10) : {', '.join(hook['missing'])}.",
            "Les 2 premières secondes doivent poser une question, un chiffre ou une image anormale, avec du son.")
    weights = {"faible": 4, "moyenne": 9, "forte": 18}
    axes = {"dialogues": ["dialogue_plat"], "coherence": ["incoherence", "canon"], "rythme": ["rythme"],
            "repetitions": ["repetition"], "tension": ["tension"], "lisibilite_mobile": ["lisibilite"]}
    scores = {a: max(0, 100 - sum(weights[i["severity"]] for i in issues if i["type"] in t)) for a, t in axes.items()}
    summary = (f"{len(issues)} point(s) relevé(s) par l'analyse locale. Durée {total:.0f}s, "
               f"{len(shots)} plans, fin : {script['ending']['type']}.")
    scores["accroche"] = hook["score"] * 10
    return {"summary": summary, "scores": scores, "issues": issues, "hook": hook}


def critique(ep: dict, script: dict) -> tuple[dict, dict]:
    local = heuristic_critique(ep, script)
    if _provider() == "demo":
        return {**local, "source": "analyse locale (mode démo)"}, {"provider": "demo", "cost_usd": 0.0}
    cfg = agent_config("critic")
    mem = bible.writer_memory(ep["series_id"])
    prompt = (f"BIBLE ET CANON :\n{json.dumps(mem, ensure_ascii=False)}\n\nINTENTION : {ep['intent']}\n"
              f"DURÉE CIBLE : {ep['duration_s']}s\n\nSCRIPT À CRITIQUER :\n{json.dumps(script, ensure_ascii=False)}\n\n"
              f"L'analyse automatique locale a déjà relevé : {json.dumps(local['issues'], ensure_ascii=False)}")
    data, meta = providers.generate_json(cfg["system_prompt"], prompt, critique_schema(), purpose="critique",
                                         episode_id=ep["id"])
    seen = {(i["shot"], i["message"]) for i in data.get("issues", [])}
    data["issues"] = data.get("issues", []) + [i for i in local["issues"] if (i["shot"], i["message"]) not in seen]
    data["source"] = f"{meta['provider']} + analyse locale"
    return data, meta


# ------------------------------------------------------------ Observateurs (isekai)

FORBIDDEN = {
    "omniscience": ["omniscien", "tout savoir", "connaître l'avenir", "voir le futur", "prédire l'avenir", "avenir"],
    "immortalité": ["immortel", "immortalité", "invincib", "ne peut pas mourir", "invulnérable"],
    "résurrection": ["ressusc", "résurrection", "revenir à la vie", "ramener à la vie"],
    "puissance excessive": ["niveau 100", "niveau max", "+10 niveaux", "puissance infinie", "one shot", "illimité",
                            "infini"],
}


def analyze_observer(series_id: str, proposal: dict) -> dict[str, Any]:
    """Vérifie un don d'Observateur contre les règles du monde. Ne rend RIEN canon."""
    text = proposal["content"].lower()
    reasons, verdict = [], "compatible"
    for rule, keys in FORBIDDEN.items():
        if any(k in text for k in keys):
            reasons.append(f"Contraire aux règles du monde : {rule} interdite pour un don d'Observateur.")
            verdict = "incompatible"
    m = re.search(r"\+\s*(\d+)\s*niveau", text)
    if m and int(m.group(1)) > 1:
        reasons.append("Un don ne peut pas dépasser un palier de puissance (+1 niveau maximum).")
        verdict = "a_adapter" if verdict == "compatible" else verdict
    accepted_recent = bible.writer_memory(series_id)["accepted_observer_gifts"]
    if proposal["kind"] != "commentaire":
        reasons.append("Rappel : au plus un don accepté par épisode ; chaque don crée une Dette d'Observation.")
    if proposal.get("pseudo_kind") not in ("fictif", "consenti"):
        reasons.append("Pseudo à confirmer : utiliser un pseudo fictif ou consenti uniquement.")
        verdict = "a_adapter" if verdict == "compatible" else verdict
    target = proposal.get("target_character")
    if target and target not in bible.character_map(series_id):
        reasons.append(f"Personnage cible inconnu : {target}.")
        verdict = "a_adapter" if verdict == "compatible" else verdict
    adaptation = ""
    if verdict != "incompatible":
        adaptation = (f"Don de l'Observateur « {proposal['pseudo']} » : {proposal['content'].strip()} "
                      "— limité à un usage par jour, crée une Dette d'Observation.")
    analysis = {"verdict": verdict, "reasons": reasons or ["Aucune règle du monde enfreinte."],
                "adaptation": adaptation, "source": "règles locales", "previous_gifts": len(accepted_recent)}
    if _provider() != "demo":
        cfg = agent_config("isekai")
        prompt = (f"RÈGLES DU MONDE :\n{json.dumps(bible.writer_memory(series_id)['bible'], ensure_ascii=False)}\n"
                  f"PROPOSITION D'OBSERVATEUR :\n{json.dumps(proposal, ensure_ascii=False)}\n"
                  f"PRÉ-ANALYSE LOCALE : {json.dumps(analysis, ensure_ascii=False)}\n"
                  "Évalue la compatibilité et propose une adaptation conforme. Tu ne décides pas : l'humain valide.")
        try:
            data, meta = providers.generate_json(cfg["system_prompt"], prompt, observer_schema(),
                                                 purpose="observer")
            # La règle locale « incompatible » prime : l'IA ne peut pas assouplir une interdiction.
            if verdict == "incompatible":
                data["verdict"] = "incompatible"
            analysis = {**data, "source": f"{meta['provider']} + règles locales",
                        "local_reasons": reasons}
        except Exception as e:  # l'analyse locale reste disponible
            analysis["llm_error"] = str(e)
    return analysis
