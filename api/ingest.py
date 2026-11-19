"""Ingest Threads/Facebook/TikTok jsonl feeds into SQLite (idempotent, upsert by url)."""
import glob
import hashlib
import json
import os
import sys
import time

from . import db

PROJECT = os.path.expanduser('~/Projects/harken')
SITE = os.path.join(PROJECT, 'site')
TRANSLATIONS = os.path.join(SITE, 'translations.json')
SKILL_SCRIPTS = os.path.expanduser('~/.hermes/skills/productivity/social-listening-merge/scripts')


def _text_key(text):
    """Same key the build/translate pipeline uses, so translations line up."""
    try:
        if SKILL_SCRIPTS not in sys.path:
            sys.path.insert(0, SKILL_SCRIPTS)
        from build_site import text_key  # noqa: WPS433
        return text_key(text)
    except Exception:
        return hashlib.sha1((text or '').strip().encode('utf-8')).hexdigest()[:16]


def _translations():
    if not os.path.exists(TRANSLATIONS):
        return {}
    try:
        return json.load(open(TRANSLATIONS, encoding='utf-8'))
    except Exception:
        return {}


def _platform(name, url=''):
    """Platform id from the shared registry (skill scripts), so every scraper counts."""
    try:
        if SKILL_SCRIPTS not in sys.path:
            sys.path.insert(0, SKILL_SCRIPTS)
        import platforms
        pid = platforms.id_of(name, url)
        return 'facebook' if pid == 'fbfeed' else pid
    except Exception:
        base = os.path.basename(name).lower()
        for p in ('threads', 'facebook', 'fbfeed', 'tiktok'):
            if base.startswith(p):
                return 'facebook' if p == 'fbfeed' else p
        return 'other'


CHROME_RE = __import__('re').compile(
    r'(?is)\b\d+\s*followers?\b.*\bfollow\b|\bquotes?\s+\d+\b.*\bmessage\b')


def _looks_like_profile_card(text):
    """True when a 'comment' is really the author widget ('name / N followers / Follow')."""
    t = (text or '').strip()
    if not t:
        return True
    if CHROME_RE.search(t) or 'Follow suggestions' in t:
        return True
    if len(t) > 400:
        return False
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    return bool(len(lines) >= 4 and any('follower' in ln.lower() for ln in lines))


def _metrics(p):
    """likes / replies / reposts / shares from any scraper's metric names."""
    m = p.get('metrics') if isinstance(p.get('metrics'), dict) else {}

    def pick(*keys):
        for k in keys:
            v = m.get(k)
            if v in (None, ''):
                v = p.get(k)
            if v not in (None, ''):
                return _num(v)
        return 0

    return (pick('likes', 'like_count', 'reactions', 'diggCount', 'favorite_count'),
            pick('replies', 'comments', 'comment_count', 'commentCount', 'reply_count'),
            pick('reposts', 'retweets', 'retweet_count'),
            pick('shares', 'share_count', 'shareCount'))


def _author(p):
    return (p.get('user') or p.get('author') or p.get('nickname')
            or p.get('username') or p.get('page') or '')


def _run_key(path):
    """One search run = one feed file. Keeps each collection separate forever."""
    return os.path.splitext(os.path.basename(path))[0]


def _num(v):
    try:
        return int(v)
    except Exception:
        return 0


def ingest(project=PROJECT, verbose=False):
    """Read every feed file and upsert posts. Returns {files, added, updated, comments}."""
    trans = _translations()
    now = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    added = updated = comments = files = 0

    paths = sorted(f for f in glob.glob(os.path.join(project, '*.jsonl'))
                   if not f.endswith('-cand.jsonl'))

    with db.db() as conn:
        for path in paths:
            files += 1
            platform = _platform(path)
            run_key = _run_key(path)
            for line in open(path, encoding='utf-8'):
                line = line.strip()
                if not line:
                    continue
                try:
                    p = json.loads(line)
                except Exception:
                    continue
                url = p.get('url')
                if not url:
                    continue
                text = (p.get('text') or '').strip()
                th = (trans.get(_text_key(text)) or {}).get('th') or text
                likes, replies, reposts, shares = _metrics(p)
                row = (
                    _platform(path, url),
                    _author(p),
                    text,
                    th,
                    p.get('posted_at') or '',
                    p.get('posted_iso') or '',
                    likes,
                    replies,
                    reposts,
                    shares,
                    1 if p.get('is_reply') else 0,
                    ','.join(p.get('queries') or []) if isinstance(p.get('queries'), list) else str(p.get('queries') or ''),
                    p.get('match') or '',
                    p.get('sentiment') or '',
                    run_key,
                    now,
                    now,
                    url,
                )
                cur = conn.execute('SELECT 1 FROM posts WHERE url = ?', (url,)).fetchone()
                conn.execute(
                    """INSERT INTO posts
                       (platform, author, text_raw, text_th, posted_at, posted_iso, likes, replies,
                        reposts, shares, is_reply, query, relevance, sentiment, run, fetched_at, updated_at, url)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(url) DO UPDATE SET
                         platform=excluded.platform, author=excluded.author, text_raw=excluded.text_raw,
                         text_th=CASE WHEN excluded.text_th <> '' AND excluded.text_th <> excluded.text_raw
                                      THEN excluded.text_th ELSE posts.text_th END,
                         posted_at=excluded.posted_at, posted_iso=excluded.posted_iso,
                         likes=excluded.likes, replies=excluded.replies, reposts=excluded.reposts,
                         shares=excluded.shares, is_reply=excluded.is_reply, query=excluded.query,
                         relevance=excluded.relevance,
                         sentiment=CASE WHEN excluded.sentiment <> '' THEN excluded.sentiment
                                        ELSE posts.sentiment END,
                         run=excluded.run,
                         updated_at=excluded.updated_at""",
                    row,
                )
                if cur:
                    updated += 1
                else:
                    added += 1

                for i, c in enumerate(p.get('comments') or []):
                    curl = c.get('url') or f'{url}#c{i}'
                    ctext = (c.get('text') or '').strip()
                    if _looks_like_profile_card(ctext):
                        continue
                    cth = (trans.get(_text_key(ctext)) or {}).get('th') or ctext
                    conn.execute(
                        """INSERT INTO post_comments (id, url, author, text_raw, text_th, posted_iso, likes, is_author)
                           VALUES (?,?,?,?,?,?,?,?)
                           ON CONFLICT(id) DO UPDATE SET text_raw=excluded.text_raw, text_th=excluded.text_th,
                             likes=excluded.likes""",
                        (curl, url, _author(c), ctext, cth, c.get('posted_iso') or '',
                         _num((c.get('metrics') or {}).get('likes', c.get('likes'))),
                         1 if c.get('is_author') else 0),
                    )
                    comments += 1

        conn.execute('INSERT INTO ingest_log (files, added, updated, at) VALUES (?,?,?,?)',
                     (files, added, updated, now))

    if verbose:
        print(f'INGEST files={files} added={added} updated={updated} comments={comments}')
    return {'files': files, 'added': added, 'updated': updated, 'comments': comments}
