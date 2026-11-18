"""SQLite layer for the Harken dashboard API."""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get('HARKEN_DB', os.path.expanduser('~/Projects/harken/harken.db'))

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    url         TEXT PRIMARY KEY,
    platform    TEXT,
    author      TEXT,
    text_raw    TEXT,
    text_th     TEXT,
    posted_at   TEXT,
    posted_iso  TEXT,
    likes       INTEGER DEFAULT 0,
    replies     INTEGER DEFAULT 0,
    reposts     INTEGER DEFAULT 0,
    shares      INTEGER DEFAULT 0,
    is_reply    INTEGER DEFAULT 0,
    query       TEXT,
    relevance   TEXT,
    sentiment   TEXT,
    fetched_at  TEXT,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts_iso ON posts(posted_iso DESC);
CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform);

CREATE TABLE IF NOT EXISTS post_comments (
    id          TEXT PRIMARY KEY,
    url         TEXT,
    author      TEXT,
    text_raw    TEXT,
    text_th     TEXT,
    posted_iso  TEXT,
    likes       INTEGER DEFAULT 0,
    is_author   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_comments_url ON post_comments(url);

CREATE TABLE IF NOT EXISTS ingest_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    files   INTEGER,
    added   INTEGER,
    updated INTEGER,
    at      TEXT
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    with db() as conn:
        conn.executescript(SCHEMA)
    return DB_PATH
