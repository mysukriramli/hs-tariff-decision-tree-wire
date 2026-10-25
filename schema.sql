CREATE SEQUENCE IF NOT EXISTS seq_commit_id START 1;

CREATE TABLE IF NOT EXISTS decision_trees (
    chapter VARCHAR PRIMARY KEY,
    title VARCHAR,
    total_nodes INTEGER,
    total_endpoints INTEGER,
    tree_depth INTEGER,
    tree_json VARCHAR,
    content_hash VARCHAR,
    last_updated_utc VARCHAR
);

CREATE TABLE IF NOT EXISTS ledger (
    commit_id BIGINT PRIMARY KEY,
    timestamp_utc VARCHAR,
    operation VARCHAR,
    chapter VARCHAR,
    nodes_count INTEGER,
    detail VARCHAR
);
