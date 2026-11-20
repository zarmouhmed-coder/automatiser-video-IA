"""Moteur de production : étapes, validations humaines obligatoires et verrou des votes.

Chaîne : scénario → critique → [VALIDATION] → storyboard → [VALIDATION] → assets (voix, sons)
→ prévisualisation → [VALIDATION] → rendu final → [VALIDATION] → pack de publication manuelle.

Règles absolues :
- aucune étape ne démarre sans la validation humaine de l'étape précédente (vérifiée dans chaque job) ;
- un épisode qui se termine sur un vote BLOQUE le suivant de la même série tant que le résultat
  officiel n'a pas été saisi ET validé ; vérifié à la création et avant chaque étape narrative.
"""
from __future__ import annotations

import json
from typing import Any

from .. import bible, db
from ..core import LockedError, StudioError, log, record_choice

STAGE_LABELS = {
    "script": "Écriture du scénario",
    "critique": "Critique du directeur",
    "validation_script": "Validation du scénario",
    "storyboard": "Storyboard",
    "validation_storyboard": "Validation du storyboard",
    "assets": "Personnages, décors, voix, effets",
    "preview": "Prévisualisation",
    "validation_preview": "Validation de la prévisualisation",
    "final": "Rendu final",
    "validation_final": "Validation du rendu final",
    "publication": "Pack de publication",
    "ready": "Prêt à publier (manuellement)",
    "published": "Publié",
    "rejected": "Rejeté",
}
STAGE_ORDER = list(STAGE_LABELS)
GATE_STAGES = ["script", "storyboard", "preview", "final"]
NARRATIVE_JOBS = {"script", "scene_regen", "critique", "storyboard"}
HEAVY_JOBS = {"preview", "final"}


# ----------------------------------------------------------------------- helpers

def get_episode(episode_id: int) -> dict[str, Any]:
    ep = db.row("SELECT * FROM episodes WHERE id=?", (episode_id,))
    if not ep:
        raise StudioError(f"Épisode introuvable : {episode_id}", status_code=404)
    ep["published_info"] = db.jloads(ep["published_info"], {})
    return ep


def latest_script(episode_id: int) -> dict[str, Any] | None:
    r = db.row("SELECT * FROM script_versions WHERE episode_id=? ORDER BY version DESC LIMIT 1", (episode_id,))
    if r:
        r["content"] = db.jloads(r["content"], {})
    return r


def latest_storyboard(episode_id: int) -> dict[str, Any] | None:
    r = db.row("SELECT * FROM storyboards WHERE episode_id=? ORDER BY version DESC LIMIT 1", (episode_id,))
    if r:
        r["content"] = db.jloads(r["content"], {})
    return r


def latest_render(episode_id: int, kind: str) -> dict[str, Any] | None:
    r = db.row("SELECT * FROM renders WHERE episode_id=? AND kind=? ORDER BY id DESC LIMIT 1", (episode_id, kind))
    if r:
        r["meta"] = db.jloads(r["meta"], {})
    return r


def set_stage(episode_id: int, stage: str, status: str | None = None, **fields: Any) -> None:
    sets, params = ["stage=?", "updated_at=?"], [stage, db.now()]
    if status:
        sets.append("status=?")
        params.append(status)
    for k, v in fields.items():
        sets.append(f"{k}=?")
        params.append(v)
    db.execute(f"UPDATE episodes SET {', '.join(sets)} WHERE id=?", (*params, episode_id))


def enqueue(kind: str, episode: dict | None, params: dict | None = None) -> int:
    if episode:
        busy = db.row("SELECT id FROM jobs WHERE episode_id=? AND status IN ('queued','running')", (episode["id"],))
        if busy:
            raise StudioError("Une tâche est déjà en cours pour cet épisode. Attendez-la ou annulez-la.",
                              code="busy", status_code=409)
    jid = db.execute(
        "INSERT INTO jobs(episode_id, series_id, kind, heavy, status, params, created_at) VALUES(?,?,?,?,?,?,?)",
        (episode["id"] if episode else None, episode["series_id"] if episode else None, kind,
         1 if kind in HEAVY_JOBS else 0, "queued", db.jdumps(params or {}), db.now()))
    log("job.queued", f"Tâche « {kind} » mise en file", series_id=episode["series_id"] if episode else None,
        episode_id=episode["id"] if episode else None, job_id=jid)
    return jid


# ------------------------------------------------------------------ verrou des votes

def vote_lock_status(series_id: str, before_number: int | None = None) -> dict[str, Any]:
    """Indique si la création / poursuite d'un épisode canonique est bloquée par un vote."""
    sql = "SELECT * FROM episodes WHERE series_id=? AND status != 'rejected'"
    params: list[Any] = [series_id]
    if before_number is not None:
        sql += " AND number < ?"
        params.append(before_number)
    prev = db.row(sql + " ORDER BY number DESC LIMIT 1", params)
    if not prev:
        return {"locked": False}
    approved_script = db.row("SELECT id FROM gates WHERE episode_id=? AND stage='script' AND status='approved'",
                             (prev["id"],))
    if not approved_script:
        return {"locked": True, "episode_id": prev["id"], "reason":
                f"L'épisode {prev['number']} n'a pas encore de scénario validé : on ne sait pas s'il se termine "
                "sur un vote. Validez-le (ou rejetez-le) avant d'écrire le suivant."}
    if prev["ends_with_vote"]:
        vote = db.row("SELECT * FROM votes WHERE episode_id=? ORDER BY id DESC LIMIT 1", (prev["id"],))
        if not vote or vote["status"] != "validated":
            state = "pas encore ouvert (publiez l'épisode)" if not vote else {
                "open": "en attente du résultat officiel", "result_entered": "résultat saisi, validation requise"}[
                vote["status"]]
            return {"locked": True, "episode_id": prev["id"], "vote_id": vote["id"] if vote else None,
                    "reason": f"Vote de l'épisode {prev['number']} {state}. L'épisode suivant reste bloqué."}
    return {"locked": False}


def assert_unlocked(ep: dict) -> None:
    st = vote_lock_status(ep["series_id"], before_number=ep["number"])
    if st["locked"]:
        raise LockedError(st["reason"], code="vote_lock")


# ----------------------------------------------------------------------- création

def create_episode(series_id: str, intent: str, duration_s: int = 45, style: str = "",
                   allow_vote: int = 1) -> dict[str, Any]:
    bible.get_series(series_id)
    intent = (intent or "").strip()
    if len(intent) < 5:
        raise StudioError("Décrivez votre intention en une phrase au minimum.")
    duration_s = max(10, min(180, int(duration_s)))
    if int(allow_vote) not in (0, 1, 2):
        raise StudioError("Politique de vote invalide.")
    st = vote_lock_status(series_id)
    if st["locked"]:
        log("vote.lock", f"Création refusée : {st['reason']}", level="warning", series_id=series_id)
        raise LockedError(st["reason"], code="vote_lock")
    from ..core import get_setting

    with db.transaction() as c:
        n = c.execute("SELECT COALESCE(MAX(number),0)+1 FROM episodes WHERE series_id=?", (series_id,)).fetchone()[0]
        ts = db.now()
        eid = c.execute(
            "INSERT INTO episodes(series_id, number, intent, duration_s, style, allow_vote, stage, status, provider,"
            " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (series_id, n, intent, duration_s, style, int(allow_vote), "script", "in_progress",
             get_setting("llm_provider"), ts, ts)).lastrowid
    ep = get_episode(eid)
    log("episode.created", f"Épisode {n} créé : {intent[:80]}", series_id=series_id, episode_id=eid)
    enqueue("script", ep)
    return ep


# ------------------------------------------------------------------------ gates

def _open_gate(ep: dict, stage: str, ref_id: int) -> int:
    db.execute("UPDATE gates SET status='superseded', decided_at=? WHERE episode_id=? AND status='pending'",
               (db.now(), ep["id"]))
    gid = db.execute("INSERT INTO gates(episode_id, stage, ref_id, status, created_at) VALUES(?,?,?,?,?)",
                     (ep["id"], stage, ref_id, "pending", db.now()))
    set_stage(ep["id"], f"validation_{stage}", "waiting_validation")
    log("gate.open", f"En attente de votre validation : {STAGE_LABELS[f'validation_{stage}']}",
        series_id=ep["series_id"], episode_id=ep["id"])
    return gid


def require_gate(ep: dict, stage: str, ref_id: int | None = None) -> None:
    sql = "SELECT * FROM gates WHERE episode_id=? AND stage=? ORDER BY id DESC LIMIT 1"
    g = db.row(sql, (ep["id"], stage))
    if not g or g["status"] != "approved" or (ref_id is not None and g["ref_id"] != ref_id):
        raise LockedError(f"Validation humaine manquante : {STAGE_LABELS['validation_' + stage]}.",
                          code="gate_required")


def decide_gate(gate_id: int, action: str, note: str = "", scene_index: int | None = None) -> dict[str, Any]:
    g = db.row("SELECT * FROM gates WHERE id=?", (gate_id,))
    if not g:
        raise StudioError("Validation introuvable.", status_code=404)
    if g["status"] != "pending":
        raise StudioError("Cette validation a déjà été traitée.", status_code=409)
    if action not in ("approve", "changes", "reject"):
        raise StudioError("Action invalide.")
    ep = get_episode(g["episode_id"])
    stage = g["stage"]
    # La validation doit porter sur la version la plus récente.
    current = {"script": latest_script, "storyboard": latest_storyboard}.get(stage)
    if current:
        cur = current(ep["id"])
        if not cur or cur["id"] != g["ref_id"]:
            raise StudioError("Une version plus récente existe : rechargez la page.", status_code=409)
    status = {"approve": "approved", "changes": "changes_requested", "reject": "rejected"}[action]
    db.execute("UPDATE gates SET status=?, note=?, decided_at=? WHERE id=?", (status, note, db.now(), gate_id))
    label = {"approve": "approuvé", "changes": "modifications demandées", "reject": "rejeté"}[action]
    record_choice(ep["series_id"], "gate", f"Épisode {ep['number']} — {stage} : {label}", episode_id=ep["id"],
                  data={"stage": stage, "note": note, "ref_id": g["ref_id"]})
    log("gate.decided", f"{STAGE_LABELS['validation_' + stage]} : {label}" + (f" — {note}" if note else ""),
        series_id=ep["series_id"], episode_id=ep["id"])
    if note and action == "changes":
        bible.add_agent_memory(ep["series_id"], f"Ép.{ep['number']} ({stage}) : {note}")

    if action == "reject":
        set_stage(ep["id"], "rejected", "rejected")
        return get_episode(ep["id"])

    if action == "changes":
        set_stage(ep["id"], stage if stage != "script" else "script", "in_progress")
        if stage == "script":
            if scene_index is not None:
                enqueue("scene_regen", ep, {"scene_index": int(scene_index), "note": note})
            else:
                enqueue("script", ep, {"note": note, "seed": _next_seed(ep)})
        elif stage == "storyboard":
            enqueue("storyboard", ep, {"note": note})
        elif stage == "preview":
            enqueue("assets", ep, {"then": "preview"})
        elif stage == "final":
            enqueue("final", ep, {})
        return get_episode(ep["id"])

    # approve
    if stage == "script":
        _on_script_approved(ep)
        set_stage(ep["id"], "storyboard", "in_progress")
        enqueue("storyboard", get_episode(ep["id"]))
    elif stage == "storyboard":
        set_stage(ep["id"], "assets", "in_progress")
        enqueue("assets", ep, {"then": "preview"})
    elif stage == "preview":
        set_stage(ep["id"], "final", "in_progress")
        enqueue("final", ep)
    elif stage == "final":
        sc = latest_script(ep["id"])
        db.execute("INSERT INTO timeline(series_id, episode_id, label, text, created_at) VALUES(?,?,?,?,?)",
                   (ep["series_id"], ep["id"], f"Épisode {ep['number']}",
                    f"{sc['content'].get('title', '')} — {sc['content'].get('logline', '')}", db.now()))
        set_stage(ep["id"], "publication", "in_progress")
        enqueue("publish", ep)
    return get_episode(ep["id"])


def _next_seed(ep: dict) -> int:
    r = db.row("SELECT COUNT(*) AS n FROM script_versions WHERE episode_id=?", (ep["id"],))
    return int(r["n"]) if r else 0


def _on_script_approved(ep: dict) -> None:
    sc = latest_script(ep["id"])["content"]
    ends_vote = 1 if sc.get("ending", {}).get("type") == "vote" else 0
    title = sc.get("title", "")
    db.execute("UPDATE episodes SET ends_with_vote=?, title=? WHERE id=?", (ends_vote, title, ep["id"]))
    ts = db.now()
    for p in sc.get("canon_proposals", []):
        db.execute("INSERT INTO canon_facts(series_id, text, category, status, source, episode_id, created_at)"
                   " VALUES(?,?,?,?,?,?,?)", (ep["series_id"], p["text"], p.get("category", "fait"), "proposed",
                                              "episode", ep["id"], ts))
    prefix = {"horror": "hor", "football": "fb", "isekai": "isk"}[ep["series_id"]]
    for ch in sc.get("new_characters", []):
        import re
        cid = f"{prefix}." + (re.sub(r"[^a-z0-9]+", "_", ch["name"].lower()).strip("_") or "nouveau")
        if db.row("SELECT id FROM characters WHERE id=?", (cid,)):
            continue
        db.execute("INSERT INTO characters(id, series_id, name, role, description, appearance, status, version,"
                   " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (cid, ep["series_id"], ch["name"], ch.get("role", ""), ch.get("description", ""),
                    db.jdumps({"archetype": "human"}), "proposed", 1, ts, ts))


# ------------------------------------------------------------ éditions ciblées

def edit_script(episode_id: int, content: dict, note: str = "") -> dict[str, Any]:
    from ..agents.schema import normalize_script

    ep = get_episode(episode_id)
    if ep["status"] in ("published",):
        raise StudioError("Épisode déjà publié : créez un nouvel épisode.")
    if db.row("SELECT id FROM jobs WHERE episode_id=? AND status IN ('queued','running')", (episode_id,)):
        raise StudioError("Une tâche est en cours pour cet épisode.", status_code=409)
    assert_unlocked(ep)
    script = normalize_script(content, ep["series_id"])
    vid = save_script_version(ep, script, "manual_edit", note, "humain")
    # Toute modification du scénario invalide les validations en aval.
    db.execute("UPDATE gates SET status='superseded', decided_at=? WHERE episode_id=? AND status IN ('pending','approved')",
               (db.now(), episode_id))
    set_stage(episode_id, "critique", "in_progress")
    enqueue("critique", ep)
    log("script.edited", "Scénario modifié manuellement (nouvelle version)", series_id=ep["series_id"],
        episode_id=episode_id, data={"version_id": vid})
    return get_episode(episode_id)


def save_script_version(ep: dict, script: dict, origin: str, note: str, provider: str) -> int:
    with db.transaction() as c:
        v = c.execute("SELECT COALESCE(MAX(version),0)+1 FROM script_versions WHERE episode_id=?",
                      (ep["id"],)).fetchone()[0]
        vid = c.execute("INSERT INTO script_versions(episode_id, version, content, origin, note, provider, created_at)"
                        " VALUES(?,?,?,?,?,?,?)", (ep["id"], v, db.jdumps(script), origin, note, provider,
                                                   db.now())).lastrowid
        c.execute("UPDATE episodes SET title=?, updated_at=? WHERE id=?", (script.get("title", ""), db.now(), ep["id"]))
    return vid


def edit_storyboard_shot(episode_id: int, shot_id: str, changes: dict) -> dict[str, Any]:
    """Modifie un seul plan du storyboard (caméra, expression, durée…) sans tout régénérer."""
    ep = get_episode(episode_id)
    sb = latest_storyboard(episode_id)
    if not sb:
        raise StudioError("Aucun storyboard pour cet épisode.")
    if db.row("SELECT id FROM jobs WHERE episode_id=? AND status IN ('queued','running')", (episode_id,)):
        raise StudioError("Une tâche est en cours pour cet épisode.", status_code=409)
    require_gate(ep, "script")
    allowed = {"camera", "duration", "characters", "caption", "sfx", "transition"}
    bad = set(changes) - allowed
    if bad:
        raise StudioError(f"Champs non modifiables ici : {', '.join(sorted(bad))} (modifiez le scénario).")
    content = json.loads(json.dumps(sb["content"]))
    shot = next((s for s in content["shots"] if s["shot_id"] == shot_id), None)
    if not shot:
        raise StudioError("Plan introuvable.", status_code=404)
    shot.update(changes)
    db.execute("UPDATE gates SET status='superseded', decided_at=? WHERE episode_id=? AND stage IN ('storyboard','preview','final')"
               " AND status IN ('pending','approved')", (db.now(), episode_id))
    set_stage(episode_id, "storyboard", "in_progress")
    enqueue("storyboard", ep, {"base": content, "edited_shot": shot_id})
    return get_episode(episode_id)


def retry_stage(episode_id: int) -> dict[str, Any]:
    """Relance l'étape courante (après un échec ou une annulation), sans contourner de validation."""
    ep = get_episode(episode_id)
    stage = ep["stage"]
    mapping = {"script": "script", "critique": "critique", "storyboard": "storyboard", "assets": "assets",
               "preview": "preview", "final": "final", "publication": "publish"}
    if stage == "rejected":
        set_stage(episode_id, "script", "in_progress")
        db.execute("UPDATE gates SET status='superseded', decided_at=? WHERE episode_id=? AND status='approved'",
                   (db.now(), episode_id))
        enqueue("script", ep, {"seed": _next_seed(ep)})
        return get_episode(episode_id)
    if stage not in mapping:
        raise StudioError("Rien à relancer : l'épisode attend une validation ou est terminé.")
    enqueue(mapping[stage], ep, {"then": "preview"} if stage == "assets" else {})
    return get_episode(episode_id)


# --------------------------------------------------------------------- votes

def mark_published(episode_id: int, platform: str, url: str = "", published_at: str = "") -> dict[str, Any]:
    ep = get_episode(episode_id)
    if ep["status"] not in ("ready_to_publish", "published"):
        raise StudioError("L'épisode n'est pas prêt à publier.")
    info = ep["published_info"]
    info.setdefault("platforms", []).append({"platform": platform, "url": url,
                                             "at": published_at or db.now()})
    db.execute("UPDATE episodes SET status='published', stage='published', published_at=COALESCE(published_at, ?),"
               " published_info=?, updated_at=? WHERE id=?",
               (published_at or db.now(), db.jdumps(info), db.now(), episode_id))
    if ep["ends_with_vote"] and not db.row("SELECT id FROM votes WHERE episode_id=?", (episode_id,)):
        sc = latest_script(episode_id)["content"]
        db.execute("INSERT INTO votes(series_id, episode_id, question, options, status, created_at) VALUES(?,?,?,?,?,?)",
                   (ep["series_id"], episode_id, sc["ending"]["vote_question"],
                    db.jdumps(sc["ending"]["vote_options"]), "open", db.now()))
        log("vote.opened", f"Vote ouvert pour l'épisode {ep['number']} : saisissez le résultat officiel une fois clos.",
            series_id=ep["series_id"], episode_id=episode_id)
    record_choice(ep["series_id"], "publication", f"Épisode {ep['number']} publié manuellement sur {platform}",
                  episode_id=episode_id, data={"url": url})
    return get_episode(episode_id)


def enter_vote_result(vote_id: int, platform: str, result_at: str, winner: str,
                      counts: dict | None = None, note: str = "") -> dict[str, Any]:
    v = db.row("SELECT * FROM votes WHERE id=?", (vote_id,))
    if not v:
        raise StudioError("Vote introuvable.", status_code=404)
    if v["status"] == "validated":
        raise StudioError("Résultat déjà validé : il est définitif et historisé.", status_code=409)
    options = db.jloads(v["options"], [])
    if winner not in options:
        raise StudioError("La décision gagnante doit être l'une des options du vote.")
    if not platform.strip() or not result_at.strip():
        raise StudioError("Plateforme de référence et date/heure du résultat obligatoires.")
    db.execute("UPDATE votes SET status='result_entered', platform=?, result_at=?, winner=?, counts=?, note=? WHERE id=?",
               (platform.strip(), result_at.strip(), winner, db.jdumps(counts or {}), note, vote_id))
    log("vote.result", f"Résultat saisi : « {winner} » ({platform}). Validation requise.",
        series_id=v["series_id"], episode_id=v["episode_id"])
    return db.row("SELECT * FROM votes WHERE id=?", (vote_id,))


def validate_vote(vote_id: int) -> dict[str, Any]:
    v = db.row("SELECT * FROM votes WHERE id=?", (vote_id,))
    if not v:
        raise StudioError("Vote introuvable.", status_code=404)
    if v["status"] != "result_entered":
        raise StudioError("Saisissez d'abord le résultat officiel du vote.")
    db.execute("UPDATE votes SET status='validated', validated_at=? WHERE id=?", (db.now(), vote_id))
    ep = get_episode(v["episode_id"])
    db.execute("INSERT INTO canon_facts(series_id, text, category, status, source, episode_id, created_at, decided_at)"
               " VALUES(?,?,?,?,?,?,?,?)", (v["series_id"], f"Vote de l'épisode {ep['number']} — {v['question']} → "
                                            f"{v['winner']}", "vote", "canon", "vote", ep["id"], db.now(), db.now()))
    record_choice(v["series_id"], "vote", f"Vote ép.{ep['number']} validé : {v['winner']} ({v['platform']})",
                  episode_id=ep["id"], data={"counts": db.jloads(v["counts"], {}), "result_at": v["result_at"]})
    log("vote.validated", f"Résultat officiel validé : « {v['winner']} ». La série peut continuer.",
        series_id=v["series_id"], episode_id=ep["id"])
    return db.row("SELECT * FROM votes WHERE id=?", (vote_id,))
