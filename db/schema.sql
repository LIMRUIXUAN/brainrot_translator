CREATE TABLE IF NOT EXISTS slang_terms (
    id              SERIAL PRIMARY KEY,
    term            TEXT NOT NULL,
    source          TEXT NOT NULL,
    definition      TEXT,
    example         TEXT,
    raw_text        TEXT NOT NULL,
    raw_text_hash   TEXT UNIQUE,
    upvotes         INTEGER DEFAULT 0,
    downvotes       INTEGER DEFAULT 0,
    subreddit       TEXT,
    channel         TEXT,
    author          TEXT,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    embedding_id    TEXT UNIQUE,
    is_embedded     BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_term ON slang_terms(term);
CREATE INDEX IF NOT EXISTS idx_source ON slang_terms(source);
CREATE INDEX IF NOT EXISTS idx_scraped_at ON slang_terms(scraped_at);
CREATE INDEX IF NOT EXISTS idx_is_embedded ON slang_terms(is_embedded);
CREATE INDEX IF NOT EXISTS idx_raw_text_hash ON slang_terms(raw_text_hash);
