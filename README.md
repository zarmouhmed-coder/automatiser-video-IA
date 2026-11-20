# MULTIVERSE STUDIO

Application locale de production de **trois séries vidéo verticales interactives** :

| Série | Titre | Genre |
|---|---|---|
| A | LES HEURES CREUSES | Horreur — enquête paranormale |
| B | LIGUE ÉCLIPSE | Football fantasy — anime sportif tactique |
| C | L'ARCHIVE D'ALDHRA | Isekai fantasy (avec Observateurs/sponsors) |

De l'intention du réalisateur au **MP4 1080×1920 H.264/AAC** et au **pack de publication manuelle**, avec une validation humaine obligatoire à chaque étape clé.

---

## Démarrer

**Windows** : double-cliquez sur `start.bat` (ou lancez-le dans un terminal).
**Linux / macOS** :

```bash
./start.sh
```

Puis ouvrez **http://127.0.0.1:8765** (le navigateur s'ouvre normalement tout seul).

Prérequis : **Python 3.10+** et **Node.js 18+** (uniquement pour compiler l'interface la première fois).
FFmpeg est fourni automatiquement par le paquet `imageio-ffmpeg` si vous ne l'avez pas installé.
Aucun GPU n'est nécessaire.

Le premier lancement crée `.venv/`, installe les dépendances, compile l'interface, crée la base `data/studio.db`
avec les trois bibles, puis génère la bibliothèque de ressources procédurales (quelques dizaines de secondes).

Arrêt : `Ctrl+C` dans le terminal. Au redémarrage, tout reprend : file d'attente, validations, historique.

---

## Parcours d'un épisode (par défaut : UNE seule validation)

```
Intention (+ inspiration TikTok/vidéo facultative)
  ─▶ Scénario ─▶ Critique ─▶ Traduction EN ─▶ Storyboard ─▶ Voix FR + EN ─▶ Rendus FR + EN 1080×1920
  ─▶ ✋ UNE VALIDATION : vidéos FR/EN + explication scène par scène (pourquoi ce lieu, cette musique,
       cette caméra), avis du directeur, fin/vote, voix, traduction, propositions de canon à cocher
  ─▶ Packs de publication FR et EN (manuelle)
```

Le mode « détaillé » (4 validations : scénario, storyboard, prévisualisation, rendu) reste disponible dans Paramètres.

**Voix** : par défaut, voix neuronales **Piper** (gratuites, hors ligne) — une voix stable par personnage selon son
genre et sa hauteur (réglables dans la bible), 3 voix françaises et 4 anglaises. Elles sont téléchargées
automatiquement au premier épisode (~500 Mo, une seule fois, dans `data/models`). Si elles sont indisponibles,
le rapport de validation l'indique clairement (repli espeak-ng ou « aucune voix »).

**Traduction anglaise** : gabarits démo traduits à la main ; sinon l'IA configurée ; sinon un modèle de traduction
local hors ligne (~80 Mo, téléchargé automatiquement). Les textes non traduits sont signalés dans le rapport.

**Inspirations** (page dédiée, ou champ dans Création) : un lien TikTok donne titre/auteur/couleurs de la miniature
(API officielle oEmbed ; TikTok n'autorise pas le téléchargement de la vidéo). Pour copier le **rythme** et le
**mouvement**, importez la vidéo de référence : le studio mesure plans, coupes/min, mouvement, luminosité, contraste,
saturation et palette, puis applique durée des plans, énergie caméra, étalonnage et couleur d'accent. Aucun
contenu de la référence n'est copié.

- **Corrections ciblées** : réécrire une seule scène, éditer le script à la main (nouvelle version),
  modifier un seul plan du storyboard (caméra, durée, expression, texte) — sans tout régénérer.
- **Aucune étape ne peut sauter une validation** : chaque tâche revérifie en base que la validation
  humaine de l'étape précédente existe et porte sur la version courante.
- **Votes (règle absolue)** : si un épisode se termine sur un vote, l'épisode suivant de la même série est
  **bloqué** jusqu'à ce que vous saisissiez le résultat officiel (plateforme, date/heure, décision gagnante)
  **puis** le validiez. Contrôle fait à la création ET avant chaque étape narrative. Les autres séries continuent.
  Le vote n'est pas imposé : par épisode, choisissez « si dilemme », « obligatoire » ou « non ».
- **Rien ne devient canon sans vous** : propositions de faits, nouveaux personnages, dons d'Observateurs.

## Les 10 pages

1. **Dashboard** — progression réelle des séries, file d'attente (3 workflows max, 1 rendu lourd), activité.
2. **Création / Mode Directeur** — intention, série, durée, style, politique de vote.
3. **Scénarios** — scripts versionnés, critique (scores + problèmes), validation, réécriture par scène.
4. **Production** — storyboard, édition de plan, lecteur prévisu/final, voix, journal, tâches.
5. **Bibliothèque** — ressources versionnées à clés stables ; import (licence obligatoire).
6. **Communauté** — votes, commentaires saisis à la main, Observateurs (isekai), historique des choix.
7. **Validations** — tout ce qui attend votre décision.
8. **Archives** — épisodes, versions, MP4, sauvegardes.
9. **Publication** — MP4, miniature, titre/description/hashtags par plateforme, commentaire épinglé, sondage court.
10. **Paramètres** — fournisseur IA, clés, budgets/quotas, voix, qualité vidéo, sauvegardes.

Plus une page **Bibles des séries** (monde, personnages, canon, codex, chronologie, agent, import).

## IA : modes et coûts

| Mode | Coût | Ce qu'il fait |
|---|---|---|
| **Démo** (par défaut) | gratuit | Scénarios assemblés à partir de gabarits écrits à la main + critique par analyse locale. **Ce n'est pas de l'IA**, c'est clairement affiché. Sert à tester toute la chaîne. |
| **API Claude** | facturé à l'usage | Agents scénaristes et critique via l'API Anthropic (`claude-opus-5-5` par défaut, sortie JSON structurée). Nécessite une clé de la console Anthropic : **un abonnement claude.ai ne donne pas accès à l'API.** |
| **Ollama** | gratuit (local) | Modèle installé par vous sur votre PC (`ollama serve`). |

Budget mensuel, budget par épisode, nombre max d'appels par épisode et délais sont réglables.
Une génération qui échoue ne se relance jamais toute seule (bouton « Relancer l'étape »).

L'analyse locale du critique (rythme, accroche, plans vides, répétitions, longueur des sous-titres,
personnages inconnus, techniques sans coût ni porteur, révélations multiples…) fonctionne dans tous les modes.

## Voix

`Aucune` (par défaut : sous-titres karaoké, bouches animées, sound design), `espeak-ng` (local, gratuit,
voix robotique — à installer) ou `ElevenLabs` (payant ; clé + `voice_id` par personnage dans la bible).
Les durées des plans s'allongent automatiquement si une voix est plus longue que prévu ;
la synchronisation labiale suit alors l'enveloppe réelle de la voix.

## Rendu vidéo

Moteur 2D/2.5D en Python (Pillow + NumPy) piloté par FFmpeg :
personnages vectoriels expressifs (8 expressions, face / trois-quarts), clignements, respiration,
bouches animées, décors en 3 couches avec parallaxe, caméra virtuelle (travelling, panoramique, secousse),
effets par série (grain/vignettage/aberration en horreur, lignes de vitesse en football, particules et
fenêtres du Système en isekai), sous-titres mobiles, carton de fin (vote / à suivre),
musiques et effets sonores **synthétisés** (créations originales, sans droits tiers), mixage avec ducking.

Les PNG importés dans la Bibliothèque remplacent le rendu procédural :
`char.<id>.<expression>` (ex. `char.hor.lea.scared`) pour un personnage, `bg.<lieu>` (ex. `bg.corridor`) pour un décor.
C'est la voie pour monter en qualité graphique avec vos propres illustrations.

> **Pourquoi pas Remotion ?** Remotion nécessite un Chrome headless téléchargé et une licence
> payante pour les entreprises de plus de 3 personnes. Le moteur Python + FFmpeg n'a aucune dépendance
> lourde, fonctionne sans GPU et tourne de la même façon sous Windows et Linux.

Prévisualisation : demi-résolution, 24 i/s (réglable ; « extrait test max » pour ne rendre que les N premières secondes).
Ordre de grandeur mesuré sur 4 cœurs : ~0,3–0,7 s par image 1080×1920.

## Stockage

Tout est local, dans `data/` :

```
data/studio.db        base SQLite (état, files, validations, bibles, journaux, chemins des médias)
data/media/ep<N>/     vignettes de storyboard, voix, prévisualisations, rendus finaux
data/exports/<série>/ packs de publication (MP4, miniature.jpg, pack.json, pack.txt)
data/library/<clé>/vN bibliothèque versionnée
data/bibles/          instantanés JSON des bibles
data/backups/         sauvegardes de la base (quotidienne + avant chaque migration)
```

Les migrations (`backend/app/migrations/*.sql`) sont appliquées au démarrage après une sauvegarde automatique.
Les clés API sont dans `.env` (ignoré par Git) et ne sont jamais renvoyées à l'interface.

## Développement

```bash
source .venv/bin/activate
cd backend && python -m pytest -q        # tests (parcours complet + règles absolues)
cd frontend && npm run dev                 # interface en mode développement (proxy vers :8765)
```

Architecture :

```
backend/app/
  main.py              FastAPI (API + fichiers + interface compilée)
  db.py, migrations/   SQLite, migrations versionnées, sauvegardes
  bible.py, seed.py    bibles persistantes, mémoire des agents, import sans écrasement
  agents/              configs des 3 scénaristes + critique, schéma des scripts, mode démo
  llm/providers.py     Anthropic / Ollama / démo, budgets et quotas
  workflow/            moteur d'étapes, validations, verrou des votes, file persistante
  render/              personnages, décors, compositeur, audio, chaîne vidéo
  publish.py           packs de publication manuelle
  library.py           bibliothèque versionnée
frontend/src/          React + TypeScript (Vite)
```

## Droits et limites

- Musiques et effets fournis : synthétisés par le projet. Tout import exige une licence renseignée.
- Les packs incluent une mention « fiction / contenu de synthèse » et rappellent d'activer l'étiquette IA des plateformes.
- Aucune publication, aucun achat, aucun abonnement n'est effectué par l'application.
- Le rendu procédural est volontairement simple (style « motion design 2D ») ; la qualité « anime » passe par
  l'import de vos sprites/décors dans la Bibliothèque ou par un futur fournisseur d'images configuré par vous.
