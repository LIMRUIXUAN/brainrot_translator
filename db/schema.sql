CREATE TABLE IF NOT EXISTS verified_image_brainrot (
    id SERIAL PRIMARY KEY,
    source_url VARCHAR(2048) NOT NULL DEFAULT '',
    media_type VARCHAR(64) NOT NULL,
    agent_meaning VARCHAR(1024) NOT NULL DEFAULT '',
    confidence DOUBLE PRECISION NOT NULL,
    human_verified BOOLEAN NOT NULL DEFAULT FALSE,
    correct_meaning VARCHAR(1024),
    "timestamp" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS verified_text_brainrot (
    id SERIAL PRIMARY KEY,
    source_text VARCHAR(2048) NOT NULL,
    page_url VARCHAR(2048) NOT NULL DEFAULT '',
    agent_equivalent_text VARCHAR(2048) NOT NULL DEFAULT '',
    confidence DOUBLE PRECISION NOT NULL,
    human_verified BOOLEAN NOT NULL DEFAULT FALSE,
    correct_meaning VARCHAR(2048),
    "timestamp" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cached_text_translations (
    id SERIAL PRIMARY KEY,
    lookup_key VARCHAR(2048) NOT NULL UNIQUE,
    is_brainrot BOOLEAN NOT NULL,
    brainrot_text VARCHAR(2048),
    equivalent_text VARCHAR(2048),
    formal_explanation TEXT,
    sentiment_label VARCHAR(32) NOT NULL DEFAULT 'unclear',
    sentiment_rationale TEXT,
    confidence_score DOUBLE PRECISION NOT NULL,
    model_used VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_cached_text_translations_lookup_key
    ON cached_text_translations (lookup_key);

CREATE TABLE IF NOT EXISTS cached_image_analyses (
    id SERIAL PRIMARY KEY,
    image_hash VARCHAR(64) NOT NULL UNIQUE,
    is_brainrot BOOLEAN NOT NULL,
    brainrot_meaning VARCHAR(2048),
    equivalent_text VARCHAR(2048),
    formal_explanation TEXT,
    confidence_score DOUBLE PRECISION NOT NULL,
    model_used VARCHAR(128),
    used_frame_fallback BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_cached_image_analyses_image_hash
    ON cached_image_analyses (image_hash);

CREATE TABLE IF NOT EXISTS brainrot_word_frequency (
    id SERIAL PRIMARY KEY,
    normalized_term VARCHAR(256) NOT NULL UNIQUE,
    display_label VARCHAR(256) NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_page_url VARCHAR(2048)
);

CREATE INDEX IF NOT EXISTS ix_brainrot_word_frequency_normalized_term
    ON brainrot_word_frequency (normalized_term);
