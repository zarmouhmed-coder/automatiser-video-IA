"""Générateur local du MODE DÉMO.

Il n'utilise aucune IA : il assemble des gabarits écrits à la main, propres à chaque série,
avec des variantes tirées au sort de façon reproductible. Il sert à tester toute la chaîne
(scénario → critique → storyboard → rendu → publication) sans rien facturer.
"""
from __future__ import annotations

import random
from typing import Any


def _c(cid: str, expr: str = "neutral", facing: str = "front", pos: str = "center") -> dict:
    return {"id": cid, "expression": expr, "facing": facing, "position": pos}


def _shot(kind: str, dur: float, camera: str, chars: list, speaker: str = "", text: str = "",
          narration: str = "", caption: str = "", sfx: list | None = None) -> dict:
    return {"id": "", "kind": kind, "duration": dur, "camera": camera, "characters": chars, "speaker": speaker,
            "text": text, "narration": narration, "caption": caption, "sfx": sfx or []}


def _pick(rng: random.Random, *options: str) -> str:
    return rng.choice(options)


def _want_vote(ep: dict, rng: random.Random) -> bool:
    policy = int(ep.get("allow_vote", 1))
    if policy == 0:
        return False
    if policy == 2:
        return True
    return ep["number"] % 2 == 1  # « auto » : un épisode sur deux, jamais systématique


# --------------------------------------------------------------------------- HORREUR

def _horror(ep: dict, mem: dict, rng: random.Random) -> dict:
    last_vote = (mem.get("validated_votes") or [None])[-1]
    recap = f"Après le choix du public : « {last_vote['winner']} »." if last_vote else ""
    s1 = {"location": _pick(rng, "exterior_sanatorium", "corridor"), "mood": "malaise", "music": "mystery",
          "summary": "Accroche : un son impossible dans l'aile B.", "shots": [
              _shot("title", 2.5, "push_in", [], caption=_pick(rng, "03:33 — AILE B", "NUIT 4 — AILE B"),
                    sfx=["stinger", "wind"]),
              _shot("dialogue", 4.0, "push_in", [_c("hor.lea", "scared", "front", "center")], "hor.lea",
                    _pick(rng, "Sur la bande… c'était la voix de Clara.", "Quelqu'un a dit mon nom. Avec sa voix à elle."),
                    sfx=["breath"]),
              _shot("dialogue", 3.5, "static", [_c("hor.samir", "determined", "left", "right"),
                                                 _c("hor.lea", "scared", "right", "left")], "hor.samir",
                    _pick(rng, "Une interférence. Une radio de camionneur, rien d'autre.",
                          "Les vieux câbles captent n'importe quoi, Léa."), sfx=[]),
              _shot("pause", 3.0, "push_in", [], narration="" if not recap else recap, sfx=["footsteps", "creak"]),
          ]}
    s2 = {"location": "archive_room", "mood": "révélation dosée", "music": "tension",
          "summary": "Odile montre un registre qui n'aurait pas dû exister.", "shots": [
              _shot("establishing", 2.5, "pan_right", [], sfx=["creak"]),
              _shot("dialogue", 4.0, "push_in", [_c("hor.odile", "neutral", "front", "center")], "hor.odile",
                    _pick(rng, "Chambre 13. Personne n'y a jamais été admis. Et pourtant, regardez.",
                          "Ce registre liste un patient de trop. Chaque année.")),
              _shot("dialogue", 3.5, "static", [_c("hor.lea", "surprised", "right", "left"),
                                                 _c("hor.odile", "neutral", "left", "right")], "hor.lea",
                    "Le dernier nom… c'est l'écriture de ma sœur."),
              _shot("pause", 2.5, "push_in", [_c("hor.odile", "sad", "front", "center")], sfx=["heartbeat"]),
          ]}
    ending_vote = _want_vote(ep, rng)
    s3 = {"location": "corridor", "mood": "terreur sourde", "music": "tension",
          "summary": "La réécoute révèle une présence dans le reflet.", "shots": [
              _shot("dialogue", 3.5, "static", [_c("hor.samir", "neutral", "front", "center")], "hor.samir",
                    "Je repasse l'enregistrement. Ralenti à 50 %."),
              _shot("reveal", 3.5, "shake", [_c("hor.locataire", "neutral", "front", "right"),
                                              _c("hor.samir", "scared", "right", "left")],
                    caption="RÉÉCOUTE — 00:47", sfx=["glitch", "stinger"]),
              _shot("dialogue", 3.5, "push_in", [_c("hor.samir", "scared", "front", "center")], "hor.samir",
                    "Il était derrière toi. Pendant tout l'enregistrement."),
          ]}
    if ending_vote:
        s3["shots"].append(_shot("pause", 3.5, "push_in", [_c("hor.lea", "determined", "front", "center")],
                                 narration="La porte 13 est entrouverte. À vous de décider.", sfx=["door_slam"]))
        ending = {"type": "vote", "vote_question": "Léa doit-elle ouvrir la porte 13 ?",
                  "vote_options": ["Ouvrir la porte", "Fuir avec Samir"]}
    else:
        s3["shots"].append(_shot("pause", 3.0, "pull_out", [], caption="À SUIVRE", sfx=["heartbeat"]))
        ending = {"type": "cliffhanger", "vote_question": "", "vote_options": []}
    return {"title": _pick(rng, "La chambre 13", "Le patient de trop", "La voix des absents"),
            "logline": ep["intent"], "hook": "Une voix disparue sur un enregistrement.", "scenes": [s1, s2, s3],
            "ending": ending,
            "canon_proposals": [{"category": "lieu", "text": "La chambre 13 de l'aile B figure dans un registre secret."}],
            "new_characters": []}


# --------------------------------------------------------------------------- FOOTBALL

def _football(ep: dict, mem: dict, rng: random.Random) -> dict:
    minute = rng.choice([71, 74, 78, 82])
    s1 = {"location": "stadium_night", "mood": "pression", "music": "tension",
          "summary": "Le FC Aube est mené, le maintien s'éloigne.", "shots": [
              _shot("title", 2.5, "pull_out", [], caption=f"{minute}' — FC AUBE 0-1 CORBEAUX", sfx=["crowd_roar", "whistle"]),
              _shot("dialogue", 3.5, "push_in", [_c("fb.brandt", "angry", "front", "center")], "fb.brandt",
                    _pick(rng, "Pressing haut ! Coupez Kaito de ses milieux !", "Marco, remonte la ligne. Maintenant !")),
              _shot("dialogue", 3.5, "static", [_c("fb.marco", "determined", "right", "left"),
                                                 _c("fb.noa", "neutral", "left", "right")], "fb.marco",
                    "Noa, il te faut deux secondes. Je te les donne."),
              _shot("action", 3.0, "pan_right", [_c("fb.kaito", "smirk", "left", "right")], "fb.kaito",
                    "Deux secondes ? Je n'en laisse jamais une.", sfx=["kick"]),
          ]}
    s2 = {"location": "stadium_night", "mood": "explosion", "music": "action",
          "summary": "Marco gagne le duel, Noa déclenche sa technique.", "shots": [
              _shot("action", 2.5, "shake", [_c("fb.marco", "angry", "front", "center")], caption="DUEL GAGNÉ",
                    sfx=["impact", "crowd_roar"]),
              _shot("technique", 3.5, "push_in", [_c("fb.noa", "determined", "front", "center")],
                    caption="LIGNE D'HORIZON — ÉLAN -30", sfx=["whoosh"]),
              _shot("dialogue", 3.0, "static", [_c("fb.yuna", "happy", "right", "center")], "fb.yuna",
                    "Je l'ai ! Deuxième Pas Fantôme, tant pis pour les crampes !"),
              _shot("technique", 3.0, "pan_left", [_c("fb.yuna", "determined", "left", "center")],
                    caption="PAS FANTÔME — 2/2", sfx=["whoosh", "kick"]),
          ]}
    vote = _want_vote(ep, rng)
    s3 = {"location": "stadium_night", "mood": "suspendu", "music": "epic",
          "summary": "La frappe touche le poteau ; Yuna s'effondre.", "shots": [
              _shot("reveal", 2.5, "shake", [], caption="POTEAU !", sfx=["impact", "crowd_roar"]),
              _shot("dialogue", 3.0, "push_in", [_c("fb.yuna", "sad", "front", "center")], "fb.yuna",
                    "Ma jambe… elle ne répond plus."),
              _shot("dialogue", 3.0, "static", [_c("fb.brandt", "determined", "front", "center")], "fb.brandt",
                    _pick(rng, "Il reste dix minutes. Et une seule décision.", "On change tout. Ou on tient.")),
          ]}
    if vote:
        ending = {"type": "vote", "vote_question": "Quel plan pour les 10 dernières minutes ?",
                  "vote_options": ["Tout pour l'attaque", "Bloc bas et contre"]}
        s3["shots"].append(_shot("pause", 3.0, "push_in", [_c("fb.noa", "determined", "front", "center")],
                                 narration="Le coach attend votre choix.", sfx=["heartbeat"]))
    else:
        ending = {"type": "cliffhanger", "vote_question": "", "vote_options": []}
        s3["shots"].append(_shot("pause", 2.5, "pull_out", [], caption="À SUIVRE", sfx=["crowd_roar"]))
    return {"title": _pick(rng, "Deux secondes", "Le prix de l'Élan", "Poteau rentrant"),
            "logline": ep["intent"], "hook": f"{minute}e minute, mené 1-0, maintien en jeu.", "scenes": [s1, s2, s3],
            "ending": ending,
            "canon_proposals": [{"category": "condition", "text": "Yuna souffre de crampes après son 2e Pas Fantôme du match."}],
            "new_characters": []}


# --------------------------------------------------------------------------- ISEKAI

def _isekai(ep: dict, mem: dict, rng: random.Random) -> dict:
    gifts = mem.get("accepted_observer_gifts") or []
    s1 = {"location": _pick(rng, "plains", "magic_forest"), "mood": "émerveillement inquiet", "music": "calm",
          "summary": "Le Système livre un indice ambigu.", "shots": [
              _shot("system", 3.0, "push_in", [], caption="[SYSTÈME] Indice du jour : la carte ment.",
                    sfx=["system_ping"]),
              _shot("dialogue", 3.5, "static", [_c("isk.elio", "surprised", "front", "center")], "isk.elio",
                    _pick(rng, "Ma propre carte… me ment ?", "Un indice par jour, et il choisit celui-là.")),
              _shot("dialogue", 3.5, "static", [_c("isk.sylwen", "neutral", "left", "right"),
                                                 _c("isk.elio", "neutral", "right", "left")], "isk.sylwen",
                    "Les réincarnés font trop confiance à leurs fenêtres bleues."),
          ]}
    s2_shots = [
        _shot("establishing", 2.5, "tilt_up", [], sfx=["wind"]),
        _shot("dialogue", 3.5, "push_in", [_c("isk.heraut", "neutral", "front", "center")], "isk.heraut",
              "Chaque carte que tu traces, je l'efface. C'est mon travail."),
        _shot("technique", 3.0, "shake", [_c("isk.elio", "determined", "front", "center")],
              caption="CARTE VIVANTE — MANA -20", sfx=["magic_cast"]),
        _shot("action", 3.0, "pan_right", [_c("isk.grukk", "angry", "right", "center")], "isk.grukk",
              "Recule, Elio. Ma lame a faim.", sfx=["sword", "impact"]),
    ]
    if gifts:
        s2_shots.insert(3, _shot("system", 3.0, "static", [], caption=f"[OBSERVATEUR] {gifts[-1][:60]}",
                                 sfx=["chime"]))
    s2 = {"location": "dungeon", "mood": "danger", "music": "epic",
          "summary": "Le Héraut Gris efface une salle entière.", "shots": s2_shots}
    vote = _want_vote(ep, rng)
    s3 = {"location": "town", "mood": "conséquence", "music": "sad",
          "summary": "Personne au village ne se souvient de la salle effacée.", "shots": [
              _shot("dialogue", 3.5, "static", [_c("isk.mira", "sad", "front", "center")], "isk.mira",
                    "L'auberge du Pont… tu es sûr qu'elle existait ?"),
              _shot("system", 3.0, "push_in", [], caption="[SYSTÈME] Niveau 8 atteint. Évolution au niveau 10.",
                    sfx=["system_ping"]),
          ]}
    if vote:
        ending = {"type": "vote", "vote_question": "Où Elio doit-il aller ?",
                  "vote_options": ["Ruines d'Ost", "Cité de Verre"]}
        s3["shots"].append(_shot("pause", 3.0, "pull_out", [_c("isk.elio", "determined", "front", "center")],
                                 narration="Deux routes. Une seule carte fiable.", sfx=["wind"]))
    else:
        ending = {"type": "reveal", "vote_question": "", "vote_options": []}
        s3["shots"].append(_shot("reveal", 3.0, "push_in", [_c("isk.elio", "scared", "front", "center")],
                                 caption="Le nom d'Elio s'efface de sa propre carte.", sfx=["glitch"]))
    return {"title": _pick(rng, "La carte qui ment", "Le Héraut Gris", "Ce que le monde oublie"),
            "logline": ep["intent"], "hook": "Le Système affirme que la carte d'Elio ment.", "scenes": [s1, s2, s3],
            "ending": ending,
            "canon_proposals": [{"category": "progression", "text": "Elio atteint le niveau 8."},
                                {"category": "monde", "text": "L'auberge du Pont a été effacée par le Héraut Gris."}],
            "new_characters": []}


GENERATORS = {"horror": _horror, "football": _football, "isekai": _isekai}


def _fit_duration(script: dict, target: float) -> dict:
    """Ajuste proportionnellement les durées des plans à la durée demandée (bornes 1,5–8 s)."""
    total = sum(sh["duration"] for sc in script["scenes"] for sh in sc["shots"])
    if total <= 0:
        return script
    k = target / total
    for sc in script["scenes"]:
        for sh in sc["shots"]:
            sh["duration"] = round(max(1.5, min(8.0, sh["duration"] * k)), 2)
    return script


def generate(ep: dict, mem: dict, seed: int = 0) -> dict:
    rng = random.Random(f"{ep['series_id']}-{ep['number']}-{seed}")
    script = GENERATORS[ep["series_id"]](ep, mem, rng)
    return _fit_duration(script, float(ep.get("duration_s", 45)))


def regenerate_scene(ep: dict, mem: dict, script: dict, scene_index: int, seed: int) -> dict[str, Any]:
    """Variante d'une seule scène (les autres restent intactes)."""
    alt = generate(ep, mem, seed=seed)
    scenes = alt["scenes"]
    idx = min(scene_index, len(scenes) - 1)
    return scenes[idx]
