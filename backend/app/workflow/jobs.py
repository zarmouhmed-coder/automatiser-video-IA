"""Implémentation des tâches de production. Chaque tâche revérifie verrous et validations."""
from __future__ import annotations

from .. import db, publish
from ..core import StudioError, get_settings, log
from ..agents import agents
from ..render import pipeline
from . import engine
from .queue import JobContext, handler


def _ep(ctx: JobContext) -> dict:
    return engine.get_episode(ctx.job["episode_id"])


def _guard_narrative(ep: dict) -> None:
    if ep["status"] in ("rejected", "published"):
        raise StudioError("Épisode rejeté ou publié : relancez-le explicitement.")
    engine.assert_unlocked(ep)  # règle absolue du vote


@handler("script")
def job_script(ctx: JobContext) -> None:
    ep = _ep(ctx)
    _guard_narrative(ep)
    engine.set_stage(ep["id"], "script", "in_progress")
    ctx.progress(None, "L'agent scénariste écrit…", force=True)
    script, meta = agents.write_script(ep, ctx.params.get("note", ""), int(ctx.params.get("seed", 0)))
    if ctx.cancelled():
        return
    vid = engine.save_script_version(ep, script, "generated", meta.get("note", ctx.params.get("note", "")),
                                     meta["provider"])
    log("script.generated", f"Scénario v{db.row('SELECT version FROM script_versions WHERE id=?', (vid,))['version']}"
        f" écrit ({meta['provider']})", series_id=ep["series_id"], episode_id=ep["id"])
    engine.set_stage(ep["id"], "critique", "in_progress")
    _critique(ctx, ep)


@handler("scene_regen")
def job_scene(ctx: JobContext) -> None:
    ep = _ep(ctx)
    _guard_narrative(ep)
    cur = engine.latest_script(ep["id"])
    idx = int(ctx.params["scene_index"])
    if not cur or idx < 0 or idx >= len(cur["content"]["scenes"]):
        raise StudioError("Scène introuvable.")
    ctx.progress(None, f"Réécriture de la scène {idx + 1} uniquement…", force=True)
    script, meta = agents.rewrite_scene(ep, cur["content"], idx, ctx.params.get("note", ""),
                                        seed=engine._next_seed(ep) + 11)
    if ctx.cancelled():
        return
    engine.save_script_version(ep, script, "scene_regen", f"Scène {idx + 1} : {ctx.params.get('note', '')}",
                               meta["provider"])
    engine.set_stage(ep["id"], "critique", "in_progress")
    _critique(ctx, ep)


@handler("critique")
def job_critique(ctx: JobContext) -> None:
    ep = _ep(ctx)
    _guard_narrative(ep)
    _critique(ctx, ep)


def _chain(ep: dict, kind: str, params: dict | None = None) -> None:
    """Enchaîne l'étape suivante (mode « une validation par épisode »), sans attendre d'intervention."""
    db.execute("INSERT INTO jobs(episode_id, series_id, kind, heavy, status, params, created_at) VALUES(?,?,?,?,?,?,?)",
               (ep["id"], ep["series_id"], kind, 1 if kind in engine.HEAVY_JOBS else 0, "queued",
                db.jdumps(params or {}), db.now()))


def _critique(ctx: JobContext, ep: dict) -> None:
    cur = engine.latest_script(ep["id"])
    ctx.progress(None, "Le directeur/critique relit le scénario…", force=True)
    report, meta = agents.critique(ep, cur["content"])
    if ctx.cancelled():
        return
    db.execute("INSERT INTO critiques(episode_id, script_version_id, content, provider, created_at) VALUES(?,?,?,?,?)",
               (ep["id"], cur["id"], db.jdumps(report), meta["provider"], db.now()))
    if engine.is_episode_mode(ep):
        engine.set_stage(ep["id"], "storyboard", "in_progress")
        _chain(ep, "storyboard")
    else:
        engine._open_gate(ep, "script", cur["id"])


def _ensure_translation(ctx: JobContext, ep: dict, cur: dict) -> dict:
    """Ajoute les traductions au script (sans changer la version : le récit est identique)."""
    from ..agents import translate

    langs = pipeline.languages()
    script = cur["content"]
    if "en" not in langs or (script.get("i18n") or {}).get("en"):
        return script
    ctx.progress(None, "Traduction FR → EN…", force=True)
    res = translate.translate_script(script, ep["id"])
    script["i18n"] = {"en": res["en"]}
    script["i18n_meta"] = {"source": res["source"], "missing": res["missing"], "errors": res["errors"]}
    db.execute("UPDATE script_versions SET content=? WHERE id=?", (db.jdumps(script), cur["id"]))
    if res["missing"]:
        log("translation.missing", f"Traduction incomplète ({len(res['missing'])} texte(s) restés en français) : "
            + "; ".join(res["errors"])[:300], level="warning", series_id=ep["series_id"], episode_id=ep["id"])
    else:
        log("translation.done", f"Version anglaise prête ({res['source']})", series_id=ep["series_id"],
            episode_id=ep["id"])
    return script


@handler("storyboard")
def job_storyboard(ctx: JobContext) -> None:
    from .. import inspiration

    ep = _ep(ctx)
    _guard_narrative(ep)
    cur = engine.latest_script(ep["id"])
    if not engine.is_episode_mode(ep):
        engine.require_gate(ep, "script", cur["id"])
    engine.set_stage(ep["id"], "storyboard", "in_progress")
    cur["content"] = _ensure_translation(ctx, ep, cur)
    base = ctx.params.get("base")
    plan = base if base else pipeline.build_plan(ep, cur["content"], style=inspiration.style_for(ep))
    if base:  # édition d'un plan : recalcul des temps de début
        t = 0.0
        for sh in plan["shots"]:
            sh["start"] = round(t, 3)
            sh["duration"] = max(1.0, min(12.0, float(sh["duration"])))
            t += sh["duration"]
        plan["total"] = round(t, 3)
    with db.transaction() as c:
        v = c.execute("SELECT COALESCE(MAX(version),0)+1 FROM storyboards WHERE episode_id=?", (ep["id"],)).fetchone()[0]
    total = len(plan["shots"])
    done = {"n": 0}

    def check():
        ctx.check(get_settings()["render_timeout_s"])
        done["n"] += 1
        ctx.progress(min(1.0, done["n"] / total), f"Vignette {done['n']}/{total}")

    pipeline.storyboard_thumbnails(ep, plan, v, check)
    sid = db.execute("INSERT INTO storyboards(episode_id, version, script_version_id, content, created_at) VALUES(?,?,?,?,?)",
                     (ep["id"], v, cur["id"], db.jdumps(plan), db.now()))
    if engine.is_episode_mode(ep):
        engine.set_stage(ep["id"], "assets", "in_progress")
        _chain(ep, "assets")
    else:
        engine._open_gate(ep, "storyboard", sid)


@handler("assets")
def job_assets(ctx: JobContext) -> None:
    ep = _ep(ctx)
    sb = engine.latest_storyboard(ep["id"])
    if not sb:
        raise StudioError("Storyboard manquant.")
    if not engine.is_episode_mode(ep):
        engine.require_gate(ep, "storyboard", sb["id"])
    engine.set_stage(ep["id"], "assets", "in_progress")
    ctx.progress(None, "Personnages, décors, voix et effets…", force=True)
    pipeline.sync_library()
    timeout = get_settings()["render_timeout_s"]
    manifest = pipeline.prepare_assets(ep, _script_from_storyboard(ep, sb), lambda: ctx.check(timeout),
                                       lambda p, m: ctx.progress(p, m))
    for w in (manifest["warnings"] + [w for l in manifest["langs"].values() for w in l["warnings"]])[:4]:
        log("assets.warning", w, level="warning", series_id=ep["series_id"], episode_id=ep["id"])
    log("assets.ready", f"Assets prêts — {manifest['voice_status']}", series_id=ep["series_id"], episode_id=ep["id"])
    if engine.is_episode_mode(ep):
        engine.set_stage(ep["id"], "final", "in_progress")
        _chain(ep, "final")
    elif ctx.params.get("then") == "preview":
        engine.set_stage(ep["id"], "preview", "in_progress")
        _chain(ep, "preview")


def _script_from_storyboard(ep: dict, sb: dict) -> dict:
    """Le rendu suit le storyboard validé (y compris les plans édités)."""
    plan = sb["content"]
    cur = db.row("SELECT content FROM script_versions WHERE id=?", (sb["script_version_id"],))
    script = db.jloads(cur["content"], {})
    by_id = {s["shot_id"]: s for s in plan["shots"]}
    for sc in script["scenes"]:
        for sh in sc["shots"]:
            p = by_id.get(sh["id"])
            if p:
                for k in ("camera", "duration", "characters", "sfx"):
                    sh[k] = p[k]
                if p.get("caption") != sh.get("caption"):  # caption modifiée à la main dans le storyboard
                    sh["caption"] = p["caption"]
    return script


def _render(ctx: JobContext, kind: str) -> None:
    from . import report as report_mod

    ep = _ep(ctx)
    sb = engine.latest_storyboard(ep["id"])
    episode_mode = engine.is_episode_mode(ep)
    if not episode_mode:
        engine.require_gate(ep, "storyboard", sb["id"])
        if kind == "final":
            engine.require_gate(ep, "preview")
    engine.set_stage(ep["id"], kind, "in_progress")
    timeout = get_settings()["render_timeout_s"]
    script = _script_from_storyboard(ep, sb)
    langs = pipeline.languages() if kind == "final" else ["fr"]
    rids, renders = [], []
    for lang in langs:
        res = pipeline.render_video(ep, script, kind, lambda p, m: ctx.progress(p, m), lambda: ctx.check(timeout), lang)
        rid = db.execute("INSERT INTO renders(episode_id, kind, storyboard_id, path, width, height, fps, duration_s,"
                         " size_bytes, meta, lang, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                         (ep["id"], kind, sb["id"], res["path"], res["width"], res["height"], res["fps"],
                          res["duration_s"], res["size_bytes"], db.jdumps(res["meta"]), lang, db.now()))
        rids.append(rid)
        renders.append({**res, "id": rid})
    ctx.progress(1.0, f"Rendu {kind} terminé ({', '.join(l.upper() for l in langs)})", force=True)
    if episode_mode:
        crit = db.row("SELECT * FROM critiques WHERE script_version_id=? ORDER BY id DESC LIMIT 1",
                      (sb["script_version_id"],))
        if crit:
            crit["content"] = db.jloads(crit["content"], {})
        rep = report_mod.build(ep, script, sb, renders, crit)
        engine._open_gate(ep, "episode", sb["id"], rep)
    else:
        engine._open_gate(ep, kind, rids[0])


@handler("preview")
def job_preview(ctx: JobContext) -> None:
    _render(ctx, "preview")


@handler("final")
def job_final(ctx: JobContext) -> None:
    _render(ctx, "final")


@handler("publish")
def job_publish(ctx: JobContext) -> None:
    ep = _ep(ctx)
    sb = engine.latest_storyboard(ep["id"])
    if engine.is_episode_mode(ep):
        engine.require_gate(ep, "episode", sb["id"])
    else:
        g = db.row("SELECT * FROM gates WHERE episode_id=? AND stage='final' ORDER BY id DESC LIMIT 1", (ep["id"],))
        if not g:
            raise StudioError("Rendu final manquant.")
        engine.require_gate(ep, "final", g["ref_id"])
        r = db.row("SELECT * FROM renders WHERE id=?", (g["ref_id"],))
        sb = db.row("SELECT * FROM storyboards WHERE id=?", (r["storyboard_id"],))
        sb["content"] = db.jloads(sb["content"], {})
    script = _script_from_storyboard(ep, sb)
    packs, first_rid = {}, None
    for lang in pipeline.languages():
        r = db.row("SELECT * FROM renders WHERE episode_id=? AND kind='final' AND storyboard_id=? AND lang=?"
                   " ORDER BY id DESC LIMIT 1", (ep["id"], sb["id"], lang))
        if not r:
            continue
        ctx.progress(None, f"Pack de publication {lang.upper()}…", force=True)
        packs[lang] = publish.build_pack(ep, script, r, lang)
        first_rid = first_rid or r["id"]
    if not packs:
        raise StudioError("Aucun rendu final trouvé pour ce storyboard.")
    from pathlib import Path
    folder = str(Path(next(iter(packs.values()))["folder"]).parent)
    publish.save_pack(ep, first_rid, {"langs": packs, "folder": folder})
    engine.set_stage(ep["id"], "ready", "ready_to_publish")
    log("publish.ready", f"Packs {', '.join(l.upper() for l in packs)} prêts dans {folder} — publication manuelle.",
        series_id=ep["series_id"], episode_id=ep["id"])


@handler("library_seed")
def job_library(ctx: JobContext) -> None:
    from .. import library

    ctx.progress(None, "Génération des ressources procédurales de la Bibliothèque…", force=True)
    n = library.generate_procedural(lambda: ctx.check())
    ctx.progress(None, f"{n} éléments vérifiés", force=True)


@handler("models_download")
def job_models(ctx: JobContext) -> None:
    from ..agents import translate
    from ..render import voices

    voices.download(None, lambda p, m: ctx.progress(p, m))
    if not translate.local_ready():
        translate.download_local(lambda p, m: ctx.progress(p, m))
    ctx.progress(1.0, "Voix et modèle de traduction installés", force=True)
