-- Analysis store, store version 1 (specs/005-storage-http-api/data-model.md).
-- Applied on every Store.open(); every statement is idempotent. No timestamps, sequences or random values.

CREATE TABLE IF NOT EXISTS store_meta (
    key   text PRIMARY KEY,
    value text NOT NULL
);

CREATE TABLE IF NOT EXISTS analyses (
    repository     text  NOT NULL CHECK (char_length(repository) BETWEEN 1 AND 300),
    snapshot       text  NOT NULL CHECK (snapshot ~ '^([0-9a-f]{40}(\+dirty:[0-9a-f]{16})?|content:[0-9a-f]{16})$'),
    schema_version int   NOT NULL,
    extractors     text  NOT NULL,  -- canonical JSON object, sorted keys
    warnings       text  NOT NULL,  -- canonical JSON array, sorted
    graph          bytea NOT NULL,  -- the serialized graph document, byte for byte
    graph_sha256   text  NOT NULL,
    PRIMARY KEY (repository, snapshot)
);

CREATE TABLE IF NOT EXISTS blobs (
    sha256  text  PRIMARY KEY,      -- hex of content
    content bytea NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    repository text    NOT NULL,
    snapshot   text    NOT NULL,
    path       text    NOT NULL,
    has_text   boolean NOT NULL,
    line_count int     NOT NULL,
    size       bigint  NULL,                    -- NULL when unreadable
    sha256     text    NULL REFERENCES blobs,   -- NULL when unreadable or has_text = false
    PRIMARY KEY (repository, snapshot, path),
    FOREIGN KEY (repository, snapshot) REFERENCES analyses ON DELETE CASCADE
);

INSERT INTO store_meta VALUES ('store_version', '1') ON CONFLICT DO NOTHING;
