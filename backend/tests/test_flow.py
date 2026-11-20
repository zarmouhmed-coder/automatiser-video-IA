"""Parcours complet d'un épisode démo + règles absolues (votes, validations)."""
from pathlib import Path

from conftest import wait_idle


def _pending_gate(client, eid):
    d = client.get(f"/api/episodes/{eid}").json()
    g = [g for g in d["gates"] if g["status"] == "pending"]
    return g[0] if g else None, d


def test_status_and_seed(client):
    s = client.get("/api/status").json()
    assert s["demo_mode"] is True
    assert s["ffmpeg"]
    series = client.get("/api/series").json()
    assert {x["id"] for x in series} == {"horror", "football", "isekai"}
    wait_idle()
    lib = client.get("/api/library").json()
    assert any(a["asset_key"] == "char.hor.lea.sheet" for a in lib)
    assert any(a["kind"] == "sfx" for a in lib)


def test_full_demo_episode_until_publication(client):
    r = client.post("/api/episodes", json={"series_id": "horror", "intent": "Léa trouve un registre interdit",
                                           "duration_s": 20, "allow_vote": 2})
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    wait_idle()
    gate, d = _pending_gate(client, eid)
    assert gate and gate["stage"] == "script"
    assert d["critiques"] and "scores" in d["critiques"][0]["content"]
    assert d["scripts"][0]["content"]["ending"]["type"] == "vote"

    # Le prochain épisode est bloqué tant que le scénario n'est pas validé
    r2 = client.post("/api/episodes", json={"series_id": "horror", "intent": "Suite", "duration_s": 20})
    assert r2.status_code == 423

    # Réécriture d'une seule scène : les autres restent identiques
    before = d["scripts"][0]["content"]["scenes"]
    assert client.post(f"/api/episodes/{eid}/scenes/1/regenerate", json={"note": "plus de tension"}).status_code == 200
    wait_idle()
    gate, d = _pending_gate(client, eid)
    after = d["scripts"][0]["content"]["scenes"]
    assert d["scripts"][0]["origin"] == "scene_regen"
    assert before[0] == after[0] and before[2] == after[2]

    # Impossible de valider une version obsolète / de sauter une étape
    assert client.post(f"/api/gates/{gate['id']}/decide", json={"action": "approve"}).status_code == 200
    wait_idle()
    gate, d = _pending_gate(client, eid)
    assert gate["stage"] == "storyboard"
    sb = d["storyboards"][0]["content"]
    assert all("thumb" in s for s in sb["shots"])

    # Modification d'un seul plan du storyboard
    shot_id = sb["shots"][0]["shot_id"]
    assert client.patch(f"/api/episodes/{eid}/storyboard/shots/{shot_id}", json={"camera": "pull_out"}).status_code == 200
    wait_idle()
    gate, d = _pending_gate(client, eid)
    assert gate["stage"] == "storyboard" and d["storyboards"][0]["version"] == 2
    assert d["storyboards"][0]["content"]["shots"][0]["camera"] == "pull_out"

    client.post(f"/api/gates/{gate['id']}/decide", json={"action": "approve"})
    wait_idle()
    gate, d = _pending_gate(client, eid)
    assert gate["stage"] == "preview", d["jobs"][:3]
    prev = d["renders"][0]
    assert prev["kind"] == "preview" and prev["size_bytes"] > 10_000

    client.post(f"/api/gates/{gate['id']}/decide", json={"action": "approve"})
    wait_idle()
    gate, d = _pending_gate(client, eid)
    assert gate["stage"] == "final"
    final = d["renders"][0]
    from app import config
    mp4 = config.DATA_DIR / final["path"]
    assert mp4.exists()
    import subprocess
    probe = subprocess.run([config.ffmpeg_exe(), "-i", str(mp4)], capture_output=True, text=True).stderr
    assert "h264" in probe and "aac" in probe

    client.post(f"/api/gates/{gate['id']}/decide", json={"action": "approve"})
    wait_idle()
    d = client.get(f"/api/episodes/{eid}").json()
    assert d["episode"]["status"] == "ready_to_publish"
    assert set(d["packs"][0]["content"]["langs"]) == {"fr", "en"}
    pack = d["packs"][0]["content"]["langs"]["fr"]
    assert set(pack["platforms"]) == {"tiktok", "youtube_shorts", "instagram_reels"}
    assert all(len(o) <= 25 for o in pack["platforms"]["tiktok"]["poll"]["options"])
    assert (config.DATA_DIR / pack["files"]["thumbnail"]).exists()

    # Vote : l'épisode suivant reste bloqué jusqu'au résultat officiel validé
    assert client.post("/api/episodes", json={"series_id": "horror", "intent": "Suite", "duration_s": 20}).status_code == 423
    client.post(f"/api/episodes/{eid}/published", json={"platform": "TikTok"})
    vote = client.get("/api/votes?series_id=horror").json()[0]
    assert vote["status"] == "open"
    assert client.post("/api/episodes", json={"series_id": "horror", "intent": "Suite", "duration_s": 20}).status_code == 423
    bad = client.post(f"/api/votes/{vote['id']}/result", json={"platform": "TikTok", "result_at": "2026-11-18 20:00",
                                                                "winner": "Option inventée"})
    assert bad.status_code == 400
    client.post(f"/api/votes/{vote['id']}/result", json={"platform": "TikTok", "result_at": "2026-11-18 20:00",
                                                          "winner": vote["options"][0], "counts": {vote["options"][0]: 812}})
    # résultat saisi mais pas encore validé : toujours bloqué
    assert client.post("/api/episodes", json={"series_id": "horror", "intent": "Suite", "duration_s": 20}).status_code == 423
    assert client.post(f"/api/votes/{vote['id']}/validate").status_code == 200
    r3 = client.post("/api/episodes", json={"series_id": "horror", "intent": "Suite après le vote", "duration_s": 20,
                                            "allow_vote": 0})
    assert r3.status_code == 200
    wait_idle()
    mem_votes = client.get("/api/series/horror/bible").json()["facts"]
    assert any(f["source"] == "vote" and f["status"] == "canon" for f in mem_votes)


def test_other_series_not_blocked(client):
    # la série football avance indépendamment de l'horreur
    r = client.post("/api/episodes", json={"series_id": "football", "intent": "Match décisif contre les Corbeaux",
                                           "duration_s": 20})
    assert r.status_code == 200
    wait_idle()


def test_job_cannot_bypass_gate(client):
    from app.workflow import engine
    eps = client.get("/api/episodes?series_id=football").json()
    ep = engine.get_episode(eps[0]["id"])
    # Forcer un storyboard sans validation du scénario échoue proprement
    engine.enqueue("storyboard", ep)
    wait_idle()
    j = client.get("/api/jobs").json()[0]
    assert j["kind"] == "storyboard" and j["status"] == "failed" and "Validation humaine" in j["error"]


def test_observers_isekai(client):
    ok = client.post("/api/observers", json={"pseudo": "Veilleur_42", "content": "Une boussole qui pointe vers le mana",
                                             "kind": "cadeau", "target_character": "isk.elio"}).json()
    bad = client.post("/api/observers", json={"pseudo": "Dieu", "content": "Elio devient immortel et omniscient",
                                              "kind": "capacite"}).json()
    a1 = client.post(f"/api/observers/{ok['id']}/analyze").json()["analysis"]
    a2 = client.post(f"/api/observers/{bad['id']}/analyze").json()["analysis"]
    assert a1["verdict"] == "compatible" and a2["verdict"] == "incompatible"
    assert client.post(f"/api/observers/{bad['id']}/decide", json={"action": "accept"}).status_code == 400
    assert client.post(f"/api/observers/{ok['id']}/decide", json={"action": "accept"}).status_code == 200
    facts = client.get("/api/series/isekai/bible").json()["facts"]
    assert any(f["source"] == "observer" for f in facts)
    imp = client.post("/api/observers/import", json={"text": "Lune | capacite | Vision nocturne\nmauvaise ligne"}).json()
    assert len(imp["added"]) == 1 and len(imp["errors"]) == 1


def test_bible_import_never_overwrites(client):
    before = [c for c in client.get("/api/series/football/bible").json()["characters"] if c["id"] == "fb.noa"][0]
    rep = client.post("/api/series/football/import", json={
        "characters": [{"id": "fb.noa", "name": "ÉCRASÉ"}, {"name": "Bastien Roux", "role": "Latéral gauche"}],
        "entries": [{"kind": "technique", "key": "tech.ligne_horizon", "name": "ÉCRASÉ"}],
        "rules": ["Règle importée"]}).json()
    assert "personnage:fb.noa" in rep["skipped_existing"] and "personnage:fb.bastien_roux" in rep["added"]
    after = [c for c in client.get("/api/series/football/bible").json()["characters"] if c["id"] == "fb.noa"][0]
    assert after["name"] == before["name"] == "Noa Diallo"


def test_settings_and_secret_not_leaked(client):
    r = client.put("/api/settings", json={"budget_monthly_usd": 5})
    assert r.json()["settings"]["budget_monthly_usd"] == 5.0
    assert client.put("/api/settings", json={"inconnu": 1}).status_code == 400
    st = client.get("/api/settings").json()
    assert "ANTHROPIC_API_KEY" in st["secrets"] and isinstance(st["secrets"]["ANTHROPIC_API_KEY"], bool)


def test_anthropic_without_key_requires_configuration(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.llm import providers
    from app.core import ConfigRequired, update_settings
    update_settings({"llm_provider": "anthropic"})
    try:
        import pytest
        with pytest.raises(ConfigRequired):
            providers.generate_json("s", "p", {"type": "object"}, purpose="test")
    finally:
        update_settings({"llm_provider": "demo"})


def test_migrations_idempotent_and_backup(client):
    from app import db
    assert db.migrate() == []
    assert client.post("/api/backups").json()["path"]


# ---------------------------------------------------------------- v2 : une validation, FR + EN, voix, inspiration

def test_episode_mode_single_validation_bilingual_with_voices(client):
    from app import config
    from app.core import update_settings
    update_settings({"validation_mode": "episode", "tts_provider": "piper", "languages": "fr,en"})
    try:
        r = client.post("/api/episodes", json={"series_id": "isekai", "intent": "Elio découvre que la carte ment",
                                               "duration_s": 20, "allow_vote": 2})
        assert r.status_code == 200, r.text
        eid = r.json()["id"]
        wait_idle(900)
        d = client.get(f"/api/episodes/{eid}").json()
        pending = [g for g in d["gates"] if g["status"] == "pending"]
        # une seule validation, ouverte seulement à la fin, avec le rapport complet
        assert len(pending) == 1 and pending[0]["stage"] == "episode", [j["error"] for j in d["jobs"]]
        assert len([g for g in d["gates"] if g["stage"] != "episode"]) == 0
        rep = pending[0]["report"]
        assert rep["scenes"] and all(s["why"] for s in rep["scenes"])
        assert rep["title"]["en"] and rep["title"]["en"] != rep["title"]["fr"]
        assert rep["ending"]["type"] == "vote" and rep["ending"]["options"]["en"]
        assert rep["voices"]["provider"] == "piper", rep["voices"]
        langs = {r_["lang"] for r_ in d["renders"] if r_["kind"] == "final"}
        assert langs == {"fr", "en"}
        man = d["assets_manifest"]["langs"]
        assert man["fr"]["voices"] and man["en"]["voices"]
        # la piste audio contient bien des voix : le fichier de voix existe et n'est pas silencieux
        import numpy as np
        from app.render import audio
        v = next(iter(man["en"]["voices"].values()))
        x = audio.read_wav(config.DATA_DIR / v["rel"])
        assert len(x) > audio.SR * 0.5 and np.abs(x).max() > 0.3
        # approbation avec une seule proposition de canon cochée
        n_props = len(rep["canon_proposals"])
        g = pending[0]
        r = client.post(f"/api/gates/{g['id']}/decide", json={"action": "approve", "accept_canon": [0]})
        assert r.status_code == 200, r.text
        wait_idle()
        d = client.get(f"/api/episodes/{eid}").json()
        assert d["episode"]["status"] == "ready_to_publish"
        pack = d["packs"][0]["content"]
        assert set(pack["langs"]) == {"fr", "en"}
        en = pack["langs"]["en"]["platforms"]["tiktok"]
        assert "#isekai" in en["hashtags"] and en["poll"]["options"]
        facts = [f for f in client.get("/api/series/isekai/bible").json()["facts"] if f["episode_id"] == eid]
        assert sum(f["status"] == "canon" for f in facts) == 1
        assert sum(f["status"] == "rejected" for f in facts) == n_props - 1
        # le verrou de vote s'applique aussi en mode épisode
        assert client.post("/api/episodes", json={"series_id": "isekai", "intent": "La suite", "duration_s": 20}).status_code == 423
    finally:
        update_settings({"validation_mode": "detailed"})


def test_episode_mode_scene_change_reruns_to_single_gate(client):
    from app.core import update_settings
    update_settings({"validation_mode": "episode", "languages": "fr"})
    try:
        # l'épisode football précédent attend sa validation : on le rejette (sinon la série reste bloquée)
        for e in client.get("/api/episodes?series_id=football").json():
            for g in client.get(f"/api/episodes/{e['id']}").json()["gates"]:
                if g["status"] == "pending":
                    client.post(f"/api/gates/{g['id']}/decide", json={"action": "reject"})
        eid = client.post("/api/episodes", json={"series_id": "football", "intent": "Entraînement avant le derby",
                                                 "duration_s": 15, "allow_vote": 0}).json()["id"]
        wait_idle(600)
        g = [g for g in client.get(f"/api/episodes/{eid}").json()["gates"] if g["status"] == "pending"][0]
        r = client.post(f"/api/gates/{g['id']}/decide", json={"action": "changes", "note": "Plus d'intensité",
                                                              "target": "scene", "scene_index": 1})
        assert r.status_code == 200
        wait_idle(600)
        d = client.get(f"/api/episodes/{eid}").json()
        assert d["scripts"][0]["origin"] == "scene_regen"
        assert [g["stage"] for g in d["gates"] if g["status"] == "pending"] == ["episode"]
    finally:
        update_settings({"validation_mode": "detailed", "languages": "fr,en"})


def test_inspiration_video_analysis(client):
    import subprocess
    import tempfile
    from pathlib import Path
    from app import config
    td = Path(tempfile.mkdtemp())
    clip = td / "ref.mp4"
    # 3 plans de couleurs différentes de 1 s chacun → 3 coupes attendues
    subprocess.run([config.ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=180x320:d=1",
                    "-f", "lavfi", "-i", "color=c=blue:s=180x320:d=1", "-f", "lavfi", "-i", "testsrc2=s=180x320:d=1",
                    "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0", "-r", "25", str(clip)], check=True)
    with open(clip, "rb") as f:
        r = client.post("/api/inspirations/upload", files={"file": ("ref.mp4", f, "video/mp4")},
                        data={"series_id": "football"})
    assert r.status_code == 200, r.text
    p = r.json()["profile"]
    assert r.json()["status"] == "ready"
    assert 2 <= p["shots"] <= 4 and 0.5 <= p["avg_shot_s"] <= 1.6, p
    assert p["palette"] and p["description"]
    bad = client.post("/api/inspirations/link", json={"url": "https://example.com/video"})
    assert bad.status_code == 400
