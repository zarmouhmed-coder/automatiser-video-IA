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
    pack = d["packs"][0]["content"]
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
