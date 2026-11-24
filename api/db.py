"""SQLite layer for the Harken dashboard API."""
import os
import sqlite3
from contextlib import contextmanager

DEFAULT_DB = os.path.expanduser('~/Projects/harken/harken.db')


def path():
    """Resolve the DB on every call, not at import.

    Tests point HARKEN_DB at a temp file and other modules must still see the default;
    a module-level constant freezes whichever value happened to be set during import.
    """
    return os.environ.get('HARKEN_DB', DEFAULT_DB)


DB_PATH = path()   # snapshot for display only — use path() for anything that writes

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
    run         TEXT,
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
    is_author   INTEGER DEFAULT 0,
    sentiment   TEXT
);
CREATE INDEX IF NOT EXISTS idx_comments_url ON post_comments(url);

CREATE TABLE IF NOT EXISTS run_status (
    run                     TEXT PRIMARY KEY,
    platform                TEXT,
    file                    TEXT,
    status                  TEXT,      -- complete | partial | empty | missing
    posts_seen              INTEGER DEFAULT 0,
    comments_stored         INTEGER DEFAULT 0,
    comments_reported       INTEGER DEFAULT 0,
    note                    TEXT,
    first_iso               TEXT,
    last_iso                TEXT,
    ready_iso               TEXT
);

CREATE TABLE IF NOT EXISTS analysis_cache (
    key         TEXT PRIMARY KEY,
    payload     TEXT,
    updated_iso TEXT
);

CREATE TABLE IF NOT EXISTS ingest_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    files   INTEGER,
    added   INTEGER,
    updated INTEGER,
    at      TEXT
);
"""


def connect():
    conn = sqlite3.connect(path(), timeout=15)
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
        # migrate DBs created before comment sentiment existed
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(post_comments)')}
        if 'sentiment' not in cols:
            conn.execute('ALTER TABLE post_comments ADD COLUMN sentiment TEXT')
        # migrate DBs created before search runs were tracked
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(posts)')}
        if 'run' not in cols:
            conn.execute('ALTER TABLE posts ADD COLUMN run TEXT')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_posts_run ON posts(run)')
        # migrate DBs created before the relevance filter existed
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(posts)')}
        for col, ddl in (('noise', 'INTEGER DEFAULT 0'),
                         ('noise_why', "TEXT DEFAULT ''"),
                         ('noise_checked', 'INTEGER DEFAULT 0')):
            if col not in cols:
                conn.execute('ALTER TABLE posts ADD COLUMN %s %s' % (col, ddl))
        conn.execute('CREATE INDEX IF NOT EXISTS idx_posts_noise ON posts(noise)')
        # observed_at (when we first saw it) is not posted_at (when it was written)
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(posts)')}
        for col, ddl in (('observed_at', 'TEXT'), ('first_seen', 'TEXT'),
                         ('review_state', "TEXT DEFAULT 'auto'"), ('review_note', 'TEXT'),
                         ('reviewed_iso', 'TEXT'),
                         ('noise_state', "TEXT DEFAULT 'pending'"),
                         ('kind', "TEXT DEFAULT 'social'"),
                         ('dedupe_key', "TEXT DEFAULT ''"),
                         ('summary', "TEXT DEFAULT ''"),
                         # how many comments the platform says exist: without it
                         # "28 comments" and "28 of 61" look the same on screen
                         ('comments_declared', 'INTEGER DEFAULT 0')):
            if col not in cols:
                conn.execute('ALTER TABLE posts ADD COLUMN %s %s' % (col, ddl))
        conn.execute('CREATE INDEX IF NOT EXISTS idx_posts_review ON posts(review_state)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_posts_kind ON posts(kind)')
        conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_dedupe ON posts(kind, dedupe_key)")
        # A label with no stated confidence cannot be told apart from a guess:
        # store how sure the model was and why, so the UI can flag the weak ones
        # instead of printing them as fact.
        for table in ('posts', 'post_comments'):
            cols = {r['name'] for r in conn.execute('PRAGMA table_info(%s)' % table)}
            for col, ddl in (('sentiment_conf', 'REAL'),
                             ('sentiment_model', 'TEXT'),
                             ('sentiment_why', 'TEXT'),
                             # three poles cannot hold what people actually
                             # express: 'โกรธ' and 'ผิดหวัง' both collapse to neg
                             ('emotion', 'TEXT'),
                             ('polarity', 'INTEGER'),
                             ('sarcasm', 'INTEGER DEFAULT 0'),
                             ('aspects', 'TEXT')):
                if col not in cols:
                    conn.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table, col, ddl))
        conn.execute('CREATE INDEX IF NOT EXISTS idx_comments_url_sent ON post_comments(url, sentiment)')
    return path()
