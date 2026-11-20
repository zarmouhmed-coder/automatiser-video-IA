-- Version 2 : épisodes bilingues, inspirations de style, validation unique par épisode.

ALTER TABLE renders ADD COLUMN lang TEXT NOT NULL DEFAULT 'fr';
ALTER TABLE episodes ADD COLUMN validation_mode TEXT NOT NULL DEFAULT 'detailed';
ALTER TABLE episodes ADD COLUMN inspiration_id INTEGER;
ALTER TABLE gates ADD COLUMN report TEXT NOT NULL DEFAULT '{}';

CREATE TABLE inspirations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT,                 -- NULL = toutes séries
    kind TEXT NOT NULL,             -- tiktok | video | image
    url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    file_path TEXT,
    thumbnail_path TEXT,
    profile TEXT NOT NULL DEFAULT '{}',
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ready', -- ready | partial | error
    error TEXT,
    created_at TEXT NOT NULL
);

-- Voix activées par défaut (les anciennes installations avaient « none »).
UPDATE settings SET value = '"piper"' WHERE key = 'tts_provider' AND value = '"none"';
