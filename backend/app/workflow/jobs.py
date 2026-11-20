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


def _critique(ctx: JobContext, ep: dict) -> None:
    cur = engine.latest_script(ep["id"])
    ctx.progress(None, "Le directeur/critique relit le scénario…", force=True)
    report, meta = agents.critique(ep, cur["content"])
    if ctx.cancelled():
        return
    db.execute("INSERT INTO critiques(episode_id, script_version_id, content, provider, created_at) VALUES(?,?,?,?,?)",
               (ep["id"], cur["id"], db.jdumps(report), meta["provider"], db.now()))
    engine._open_gate(ep, "script", cur["id"])


@handler("storyboard")
def job_storyboard(ctx: JobContext) -> None:
    ep = _ep(ctx)
    _guard_narrative(ep)
    cur = engine.latest_script(ep["id"])
    engine.require_gate(ep, "script", cur["id"])
    engine.set_stage(ep["id"], "storyboard", "in_progress")
    base = ctx.params.get("base")
    plan = base if base else pipeline.build_plan(ep, cur["content"])
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
    engine._open_gate(ep, "storyboard", sid)


@handler("assets")
def job_assets(ctx: JobContext) -> None:
    ep = _ep(ctx)
    sb = engine.latest_storyboard(ep["id"])
    if not sb:
        raise StudioError("Storyboard manquant.")
    engine.require_gate(ep, "storyboard", sb["id"])
    engine.set_stage(ep["id"], "assets", "in_progress")
    ctx.progress(None, "Personnages, décors, voix et effets…", force=True)
    pipeline.sync_library()
    manifest = pipeline.prepare_assets(ep, sb["content"], lambda: ctx.check(get_settings()["render_timeout_s"]))
    for w in manifest["warnings"][:3]:
        log("assets.warning", w, level="warning", series_id=ep["series_id"], episode_id=ep["id"])
    log("assets.ready", f"Assets prêts — {manifest['voice_status']}", series_id=ep["series_id"], episode_id=ep["id"])
    if ctx.params.get("then") == "preview":
        engine.set_stage(ep["id"], "preview", "in_progress")
        db.execute("INSERT INTO jobs(episode_id, series_id, kind, heavy, status, params, created_at)"
                   " VALUES(?,?,?,?,?,?,?)", (ep["id"], ep["series_id"], "preview", 1, "queued", "{}", db.now()))


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
                for k in ("camera", "duration", "characters", "caption", "sfx"):
                    sh[k] = p[k]
    return script


def _render(ctx: JobContext, kind: str) -> None:
    ep = _ep(ctx)
    sb = engine.latest_storyboard(ep["id"])
    engine.require_gate(ep, "storyboard", sb["id"])
    if kind == "final":
        engine.require_gate(ep, "preview")
    engine.set_stage(ep["id"], kind, "in_progress")
    timeout = get_settings()["render_timeout_s"]
    res = pipeline.render_video(ep, _script_from_storyboard(ep, sb), kind,
                                lambda p, m: ctx.progress(p, m), lambda: ctx.check(timeout))
    rid = db.execute("INSERT INTO renders(episode_id, kind, storyboard_id, path, width, height, fps, duration_s,"
                     " size_bytes, meta, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (ep["id"], kind, sb["id"], res["path"], res["width"], res["height"], res["fps"],
                      res["duration_s"], res["size_bytes"], db.jdumps(res["meta"]), db.now()))
    ctx.progress(1.0, f"Rendu {kind} terminé ({res['width']}×{res['height']}, {res['duration_s']} s)", force=True)
    engine._open_gate(ep, kind, rid)


@handler("preview")
def job_preview(ctx: JobContext) -> None:
    _render(ctx, "preview")


@handler("final")
def job_final(ctx: JobContext) -> None:
    _render(ctx, "final")


@handler("publish")
def job_publish(ctx: JobContext) -> None:
    ep = _ep(ctx)
    r = engine.latest_render(ep["id"], "final")
    if not r:
        raise StudioError("Rendu final manquant.")
    engine.require_gate(ep, "final", r["id"])
    sb = db.row("SELECT * FROM storyboards WHERE id=?", (r["storyboard_id"],))
    sb["content"] = db.jloads(sb["content"], {})
    ctx.progress(None, "Préparation du pack de publication…", force=True)
    pack = publish.build_pack(ep, _script_from_storyboard(ep, sb), r)
    publish.save_pack(ep, r["id"], pack)
    engine.set_stage(ep["id"], "ready", "ready_to_publish")
    log("publish.ready", f"Pack prêt dans {pack['folder']} — publication manuelle depuis votre téléphone.",
        series_id=ep["series_id"], episode_id=ep["id"])


@handler("library_seed")
def job_library(ctx: JobContext) -> None:
    from .. import library

    ctx.progress(None, "Génération des ressources procédurales de la Bibliothèque…", force=True)
    n = library.generate_procedural(lambda: ctx.check())
    ctx.progress(None, f"{n} éléments vérifiés", force=True)
