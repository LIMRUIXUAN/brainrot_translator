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
