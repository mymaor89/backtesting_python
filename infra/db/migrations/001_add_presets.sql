-- Migration: Add presets table for user-saved strategy presets
-- Run this manually if the database was already initialized before this feature

CREATE TABLE IF NOT EXISTS presets (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    tag         TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT 'Custom',
    description TEXT NOT NULL DEFAULT '',
    state       JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS presets_name_idx ON presets (name);
