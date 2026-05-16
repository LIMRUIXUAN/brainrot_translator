CREATE TABLE slang_terms (
    id INT AUTO_INCREMENT PRIMARY KEY,
    term VARCHAR(255),
    meaning TEXT,
    example TEXT,
    source VARCHAR(255),
    source_url TEXT,
    category VARCHAR(100),
    collected_at DATETIME
);
