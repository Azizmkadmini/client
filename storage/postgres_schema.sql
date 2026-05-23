-- Schéma PostgreSQL (Phase 3) — optionnel, STORAGE_BACKEND=postgres + DATABASE_URL

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY,
    fingerprint TEXT UNIQUE,
    name TEXT NOT NULL,
    company TEXT,
    email TEXT,
    phone TEXT,
    link TEXT,
    linkedin TEXT,
    instagram TEXT,
    tag TEXT NOT NULL,
    status TEXT NOT NULL,
    channel TEXT NOT NULL,
    follow_up_stage INTEGER NOT NULL DEFAULT 1,
    last_contacted_at TIMESTAMPTZ,
    next_follow_up_at TIMESTAMPTZ,
    notes TEXT,
    consent BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scraper_jobs (
    id UUID PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads (email);
