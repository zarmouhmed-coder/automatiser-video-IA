"""Schéma JSON des scripts d'épisode (contrat entre agents, interface et moteur de rendu)."""
from __future__ import annotations

from copy import deepcopy

EXPRESSIONS = ["neutral", "happy", "sad", "angry", "scared", "surprised", "determined", "smirk"]
FACINGS = ["front", "left", "right"]
POSITIONS = ["left", "center", "right"]
CAMERAS = ["static", "push_in", "pull_out", "pan_left", "pan_right", "shake", "tilt_up"]
SHOT_KINDS = ["establishing", "dialogue", "action", "reveal", "pause", "technique", "system", "title"]
MUSIC = ["tension", "mystery", "calm", "epic", "action", "sad", "silence"]
SFX = ["whoosh", "impact", "stinger", "heartbeat", "creak", "footsteps", "whistle", "kick", "crowd_roar",
       "chime", "system_ping", "glitch", "wind", "door_slam", "breath", "magic_cast", "sword"]
ENDINGS = ["cliffhanger", "vote", "resolution", "reveal"]

LOCATIONS = {
    "horror": ["exterior_sanatorium", "corridor", "archive_room", "bedroom", "forest_night"],
    "football": ["stadium_night", "training_field", "locker_room"],
    "isekai": ["plains", "magic_forest", "dungeon", "town"],
}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


def shot_schema() -> dict:
    return _obj({
        "id": {"type": "string"},
        "kind": {"type": "string", "enum": SHOT_KINDS},
        "duration": {"type": "number"},
        "camera": {"type": "string", "enum": CAMERAS},
        "characters": {"type": "array", "items": _obj({
            "id": {"type": "string"},
            "expression": {"type": "string", "enum": EXPRESSIONS},
            "facing": {"type": "string", "enum": FACINGS},
            "position": {"type": "string", "enum": POSITIONS},
        })},
        "speaker": {"type": "string", "description": "id du personnage qui parle, ou chaîne vide"},
        "text": {"type": "string", "description": "réplique (max 90 caractères) ou chaîne vide"},
        "narration": {"type": "string", "description": "voix off ou chaîne vide"},
        "caption": {"type": "string", "description": "texte à l'écran (titre, technique, fenêtre Système) ou vide"},
        "sfx": {"type": "array", "items": {"type": "string", "enum": SFX}},
    })


def scene_schema(series_id: str) -> dict:
    return _obj({
        "id": {"type": "string"},
        "location": {"type": "string", "enum": LOCATIONS[series_id]},
        "mood": {"type": "string"},
        "music": {"type": "string", "enum": MUSIC},
        "summary": {"type": "string"},
        "shots": {"type": "array", "items": shot_schema()},
    })


def script_schema(series_id: str) -> dict:
    return _obj({
        "title": {"type": "string"},
        "logline": {"type": "string"},
        "hook": {"type": "string"},
        "scenes": {"type": "array", "items": scene_schema(series_id)},
        "ending": _obj({
            "type": {"type": "string", "enum": ENDINGS},
            "vote_question": {"type": "string"},
            "vote_options": {"type": "array", "items": {"type": "string"}},
        }),
        "canon_proposals": {"type": "array", "items": _obj({"category": {"type": "string"}, "text": {"type": "string"}})},
        "new_characters": {"type": "array", "items": _obj({
            "name": {"type": "string"}, "role": {"type": "string"}, "description": {"type": "string"}})},
    })


def critique_schema() -> dict:
    return _obj({
        "summary": {"type": "string"},
        "scores": _obj({k: {"type": "integer"} for k in
                        ["dialogues", "coherence", "rythme", "repetitions", "tension", "lisibilite_mobile"]}),
        "issues": {"type": "array", "items": _obj({
            "scene": {"type": "string"}, "shot": {"type": "string"},
            "type": {"type": "string", "enum": ["dialogue_plat", "incoherence", "rythme", "repetition", "tension",
                                                 "lisibilite", "canon"]},
            "severity": {"type": "string", "enum": ["faible", "moyenne", "forte"]},
            "message": {"type": "string"}, "suggestion": {"type": "string"},
        })},
    })


def observer_schema() -> dict:
    return _obj({
        "verdict": {"type": "string", "enum": ["compatible", "a_adapter", "incompatible"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "adaptation": {"type": "string"},
    })


def normalize_script(script: dict, series_id: str) -> dict:
    """Valide et corrige un script (valeurs inconnues → valeurs sûres, durées bornées, ids stables)."""
    s = deepcopy(script)
    s.setdefault("title", "Sans titre")
    s.setdefault("logline", "")
    s.setdefault("hook", "")
    s.setdefault("canon_proposals", [])
    s.setdefault("new_characters", [])
    end = s.setdefault("ending", {"type": "cliffhanger", "vote_question": "", "vote_options": []})
    if end.get("type") not in ENDINGS:
        end["type"] = "cliffhanger"
    end["vote_options"] = [o.strip()[:40] for o in end.get("vote_options", []) if o and o.strip()][:4]
    if end["type"] == "vote" and (len(end["vote_options"]) < 2 or not end.get("vote_question")):
        end["type"] = "cliffhanger"
    locs = LOCATIONS[series_id]
    for i, sc in enumerate(s.get("scenes", []), 1):
        sc["id"] = f"s{i}"
        if sc.get("location") not in locs:
            sc["location"] = locs[0]
        if sc.get("music") not in MUSIC:
            sc["music"] = "tension"
        sc.setdefault("mood", "")
        sc.setdefault("summary", "")
        for j, sh in enumerate(sc.get("shots", []), 1):
            sh["id"] = f"s{i}p{j}"
            if sh.get("kind") not in SHOT_KINDS:
                sh["kind"] = "dialogue"
            if sh.get("camera") not in CAMERAS:
                sh["camera"] = "static"
            try:
                sh["duration"] = float(sh.get("duration", 3.5))
            except (TypeError, ValueError):
                sh["duration"] = 3.5
            sh["duration"] = max(1.0, min(12.0, sh["duration"]))
            for key in ("speaker", "text", "narration", "caption"):
                sh[key] = (sh.get(key) or "").strip()
            sh["sfx"] = [x for x in sh.get("sfx", []) if x in SFX][:3]
            chars = []
            for c in sh.get("characters", [])[:3]:
                chars.append({
                    "id": c.get("id", ""),
                    "expression": c.get("expression") if c.get("expression") in EXPRESSIONS else "neutral",
                    "facing": c.get("facing") if c.get("facing") in FACINGS else "front",
                    "position": c.get("position") if c.get("position") in POSITIONS else "center",
                })
            sh["characters"] = chars
    return s


def script_duration(script: dict) -> float:
    return sum(sh["duration"] for sc in script.get("scenes", []) for sh in sc.get("shots", []))
