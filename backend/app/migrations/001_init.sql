-- MULTIVERSE STUDIO — schéma initial

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE series (
    id TEXT PRIMARY KEY,               -- horror | football | isekai
    code TEXT NOT NULL,                -- A | B | C
    name TEXT NOT NULL,
    genre TEXT NOT NULL,
    accent TEXT NOT NULL,
    bible TEXT NOT NULL,               -- JSON : ton, règles du monde, direction artistique
    features TEXT NOT NULL DEFAULT '{}', -- JSON : { "observers": true } ...
    created_at TEXT NOT NULL
);

-- Personnages : identifiants stables (ex. hor.lea)
CREATE TABLE characters (
    id TEXT PRIMARY KEY,
    series_id TEXT NOT NULL REFERENCES series(id),
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    personality TEXT NOT NULL DEFAULT '',
    appearance TEXT NOT NULL DEFAULT '{}',  -- JSON pour le moteur de rendu
    stats TEXT NOT NULL DEFAULT '{}',       -- JSON (niveau, classe, poste, techniques...)
    voice TEXT NOT NULL DEFAULT '{}',       -- JSON (fournisseur, voice_id, hauteur)
    status TEXT NOT NULL DEFAULT 'canon',   -- canon | proposed | rejected
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL REFERENCES series(id),
    a_id TEXT NOT NULL,
    b_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

-- Entrées de bible : règles, techniques, lieux, races, classes, magie, objets, entités...
CREATE TABLE bible_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL REFERENCES series(id),
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    name TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'seed',    -- seed | import | user | vote | observer | episode
    created_at TEXT NOT NULL,
    UNIQUE(series_id, kind, key)
);

-- Faits canoniques et propositions (rien ne devient canon sans accord humain)
CREATE TABLE canon_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL REFERENCES series(id),
    text TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'fait',
    status TEXT NOT NULL DEFAULT 'proposed', -- proposed | canon | rejected
    source TEXT NOT NULL DEFAULT 'user',
    episode_id INTEGER,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

CREATE TABLE timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL REFERENCES series(id),
    episode_id INTEGER,
    label TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL REFERENCES series(id),
    number INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    intent TEXT NOT NULL,
    duration_s INTEGER NOT NULL DEFAULT 45,
    style TEXT NOT NULL DEFAULT '',
    allow_vote INTEGER NOT NULL DEFAULT 1,
    stage TEXT NOT NULL DEFAULT 'script',
    status TEXT NOT NULL DEFAULT 'in_progress', -- in_progress | waiting_validation | ready_to_publish | published | rejected
    ends_with_vote INTEGER NOT NULL DEFAULT 0,
    provider TEXT NOT NULL DEFAULT 'demo',
    published_at TEXT,
    published_info TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(series_id, number)
);

CREATE TABLE script_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    version INTEGER NOT NULL,
    content TEXT NOT NULL,          -- JSON du script
    origin TEXT NOT NULL,           -- generated | scene_regen | manual_edit
    note TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT 'demo',
    created_at TEXT NOT NULL
);

CREATE TABLE critiques (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    script_version_id INTEGER NOT NULL REFERENCES script_versions(id),
    content TEXT NOT NULL,          -- JSON
    provider TEXT NOT NULL DEFAULT 'demo',
    created_at TEXT NOT NULL
);

CREATE TABLE storyboards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    version INTEGER NOT NULL,
    script_version_id INTEGER NOT NULL,
    content TEXT NOT NULL,          -- JSON : plans résolus, timings, fichiers vignettes
    created_at TEXT NOT NULL
);

CREATE TABLE renders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    kind TEXT NOT NULL,             -- preview | final
    storyboard_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    fps INTEGER NOT NULL,
    duration_s REAL NOT NULL,
    size_bytes INTEGER NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

-- Points de validation humaine
CREATE TABLE gates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    stage TEXT NOT NULL,            -- script | storyboard | preview | final
    ref_id INTEGER,                 -- version concernée
    status TEXT NOT NULL DEFAULT 'pending', -- pending | approved | changes_requested | rejected | superseded
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    decided_at TEXT
);

-- File d'attente persistante
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER,
    series_id TEXT,
    kind TEXT NOT NULL,
    heavy INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'queued', -- queued | running | done | failed | cancelled
    params TEXT NOT NULL DEFAULT '{}',
    progress REAL,                  -- uniquement si mesurable (images rendues / total)
    message TEXT NOT NULL DEFAULT '',
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'info',
    series_id TEXT,
    episode_id INTEGER,
    job_id INTEGER,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}'
);

-- Votes du public (saisie manuelle uniquement)
CREATE TABLE votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL REFERENCES series(id),
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    question TEXT NOT NULL,
    options TEXT NOT NULL,          -- JSON liste
    status TEXT NOT NULL DEFAULT 'open', -- open | result_entered | validated
    platform TEXT,
    result_at TEXT,
    counts TEXT NOT NULL DEFAULT '{}',
    winner TEXT,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    validated_at TEXT
);

-- Historique de tous les choix
CREATE TABLE choices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL,
    episode_id INTEGER,
    kind TEXT NOT NULL,             -- vote | gate | canon | observer | import
    summary TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL REFERENCES series(id),
    episode_id INTEGER,
    author TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    use_as_inspiration INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Observateurs / sponsors (série isekai uniquement)
CREATE TABLE observer_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL REFERENCES series(id),
    pseudo TEXT NOT NULL,
    pseudo_kind TEXT NOT NULL,      -- fictif | consenti
    kind TEXT NOT NULL,             -- capacite | cadeau | commentaire
    content TEXT NOT NULL,
    target_character TEXT,
    status TEXT NOT NULL DEFAULT 'pending', -- pending | analyzed | accepted | adapted | rejected
    analysis TEXT NOT NULL DEFAULT '{}',
    final_text TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);

-- Bibliothèque versionnée
CREATE TABLE assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    series_id TEXT,
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    path TEXT NOT NULL,
    license TEXT NOT NULL,
    source TEXT NOT NULL,           -- procedural | import | render
    meta TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(asset_key, version)
);

CREATE TABLE publication_packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    render_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    folder TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE cost_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    episode_id INTEGER,
    purpose TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_events_ts ON events(ts);
CREATE INDEX idx_episodes_series ON episodes(series_id, number);
