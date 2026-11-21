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
    base_name = os.path.basename(name).lower()
    if base_name.startswith('news_'):      # web news search feed, not social
        return 'news'
    try:
        if SKILL_SCRIPTS not in sys.path:
            sys.path.insert(0, SKILL_SCRIPTS)
        import platforms
        pid = platforms.id_of(name, url)
        return 'facebook' if pid == 'fbfeed' else pid
    except Exception:
        base = base_name
        for p in ('threads', 'facebook', 'fbfeed', 'tiktok'):
            if base.startswith(p):
                return 'facebook' if p == 'fbfeed' else p
        return 'other'


_RE = __import__('re')


def _summary(p, plat):
    """A description that only repeats the outlet is not a summary."""
    if plat != 'news':
        return ''
    sm = (p.get('summary') or '').strip()[:400]
    src = (p.get('source') or p.get('author') or '').strip()
    if sm and src and sm.casefold() == src.casefold():
        return ''
    return sm


def _news_key(text):
    """Same story, different tracking URL — dedupe on the headline itself.

    Never split on '.': Thai abbreviations (รฟท., ซี.พี., บมจ.) would cut the
    headline to nothing and let every re-fetch through as a new row.
    """
    return _RE.sub(r'[^0-9a-z\u0e00-\u0e7f]+', '', (text or '').lower())[:50]
UI_TAIL = _RE.compile(r'\s*(?:ดูเพิ่มเติม|See more|see more)\s*$')

MAX_COMMENTS_PER_POST = 100   # analysis cap: beyond this the signal stops improving

CHROME_RE = _RE.compile(
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


THAI_RE = _RE.compile(r'[\u0E00-\u0E7F]')


def _thai_ratio(text):
    letters = [ch for ch in (text or '') if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if THAI_RE.match(ch)) / len(letters)


def _comment_belongs(ctext, post_text):
    """A Thai news post attracts Thai replies; the reel comment panel also shows
    unrelated recommended threads (Vietnamese/English), so drop those."""
    r = _thai_ratio(ctext)
    if r >= 0.2:
        return True
    if not post_text:
        return True
    # non-Thai comment is kept only when it shares a real word with the post
    words = {w.lower() for w in _RE.findall(r'[A-Za-z]{4,}|[\u0E00-\u0E7F]{3,}', post_text)}
    return any(w in ctext.lower() for w in words)


RUN_STABLE_SECONDS = 60      # a file untouched this long is treated as finished


def fingerprint():
    """Cheap stat-only signature of the feed directory (no file reads).

    Includes the .keep.json / .meta.json sidecars: an analyst's --keep decision
    written after the feed must still trigger a re-ingest.
    """
    parts = []
    files = (glob.glob(os.path.join(PROJECT, '*.jsonl'))
             + glob.glob(os.path.join(PROJECT, '*.jsonl.keep.json'))
             + glob.glob(os.path.join(PROJECT, '*.jsonl.meta.json')))
    for f in sorted(files):
        if f.endswith('-cand.jsonl'):
            continue
        try:
            st = os.stat(f)
        except OSError:
            continue
        parts.append('%s:%s:%s' % (os.path.basename(f), st.st_size, int(st.st_mtime)))
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:16]


def _update_run_status(conn, run_key, platform, path, posts_seen, comments_stored,
                       comments_reported, now):
    age = time.time() - os.path.getmtime(path)
    size = os.path.getsize(path)
    if size == 0:
        status, note = 'empty', 'ไฟล์ว่าง — scraper อาจถูกบล็อกหรือไม่พบผล'
    elif age < RUN_STABLE_SECONDS:
        status, note = 'partial', 'สแครปперอาจยังเขียนไฟล์อยู่'
    else:
        status, note = 'complete', ''
    row = conn.execute('SELECT first_iso FROM run_status WHERE run = ?', (run_key,)).fetchone()
    first = row['first_iso'] if row and row['first_iso'] else now
    conn.execute(
        '''INSERT INTO run_status (run, platform, file, status, posts_seen, comments_stored,
                                  comments_reported, note, first_iso, last_iso, ready_iso)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(run) DO UPDATE SET
             platform=excluded.platform, file=excluded.file, status=excluded.status,
             posts_seen=excluded.posts_seen, comments_stored=excluded.comments_stored,
             comments_reported=excluded.comments_reported, note=excluded.note,
             last_iso=excluded.last_iso,
             ready_iso=CASE WHEN excluded.status = 'complete' THEN excluded.last_iso
                            ELSE run_status.ready_iso END''',
        (run_key, platform, os.path.basename(path), status, posts_seen, comments_stored,
         comments_reported, note, first, now, now if status == 'complete' else None))


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


def _sidecar(path, suffix):
    try:
        return json.load(open(path + suffix, encoding='utf-8'))
    except Exception:
        return None


def _apply_judgement(conn, path, run_urls):
    """Make the DB show what was decided about this run, not the raw search output.

    Two sources, both optional, both written next to the feed file:
      <feed>.keep.json  the analyst's --keep list; every other post in the file is off-topic
      <feed>.meta.json  the run's since/until window; posts outside it are not "today"
    A person's review (review_state confirmed/rejected) always wins over both.
    Judged rows are marked noise_checked=1 so the LLM relevance pass never re-opens them.
    """
    keep = _sidecar(path, '.keep.json')
    meta = _sidecar(path, '.meta.json') or {}
    since, until = (meta.get('since') or '')[:10], (meta.get('until') or '')[:10]
    kept = set(keep.get('keep') or []) if isinstance(keep, dict) else None
    why = (keep.get('why') or {}) if isinstance(keep, dict) else {}
    human = "COALESCE(review_state,'auto') = 'auto'"
    for url, iso in run_urls:
        day = (iso or '')[:10]
        if day and ((since and day < since) or (until and day > until)):
            conn.execute(
                "UPDATE posts SET noise = 1, noise_checked = 1, noise_state = 'window', "
                "noise_why = ? WHERE url = ? AND " + human,
                ('นอกช่วงเวลาที่ค้น (%s ถึง %s)' % (since or '-', until or '-'), url))
        elif kept is None:
            continue
        elif url in kept:
            conn.execute(
                "UPDATE posts SET noise = 0, noise_checked = 1, noise_state = 'ok', "
                "noise_why = ? WHERE url = ? AND " + human,
                ('ผู้วิเคราะห์คัดไว้: ' + str(why.get(url) or 'ตรงหัวข้อ'), url))
        else:
            conn.execute(
                "UPDATE posts SET noise = 1, noise_checked = 1, noise_state = 'agent', "
                "noise_why = ? WHERE url = ? AND " + human,
                ('ผู้วิเคราะห์ตัดออก: ไม่ตรงความหมายของคำค้น', url))


def fingerprint_sidecars(project=PROJECT):
    return [(f, os.path.getmtime(f)) for f in sorted(glob.glob(os.path.join(project, '*.keep.json')))]


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
            run_posts = run_comments = run_reported = 0
            run_urls = []
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
                plat = _platform(path, url)
                row = (
                    plat,
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
                    now,   # fetched_at
                    now,   # updated_at
                    now,   # observed_at
                    now,   # first_seen
                    url,
                    'news' if plat == 'news' else 'social',
                    _news_key(text) if plat == 'news' else '',
                    _summary(p, plat),
                )
                cur = conn.execute('SELECT 1 FROM posts WHERE url = ?', (url,)).fetchone()
                if plat == 'news' and not cur:
                    dk = _news_key(text)
                    if dk and conn.execute(
                            "SELECT 1 FROM posts WHERE kind='news' AND dedupe_key = ? LIMIT 1",
                            (dk,)).fetchone():
                        continue
                conn.execute(
                    """INSERT INTO posts
                       (platform, author, text_raw, text_th, posted_at, posted_iso, likes, replies,
                        reposts, shares, is_reply, query, relevance, sentiment, run, fetched_at, updated_at,
                        observed_at, first_seen, url, kind, dedupe_key, summary)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(url) DO UPDATE SET
                         platform=excluded.platform, author=excluded.author, text_raw=excluded.text_raw,
                         text_th=CASE WHEN excluded.text_th <> '' AND excluded.text_th <> excluded.text_raw
                                      THEN excluded.text_th ELSE posts.text_th END,
                         posted_at=excluded.posted_at, posted_iso=excluded.posted_iso,
                         likes=CASE WHEN excluded.likes > 0 THEN excluded.likes ELSE posts.likes END,
                         replies=CASE WHEN excluded.replies > 0 THEN excluded.replies ELSE posts.replies END,
                         reposts=CASE WHEN excluded.reposts > 0 THEN excluded.reposts ELSE posts.reposts END,
                         shares=CASE WHEN excluded.shares > 0 THEN excluded.shares ELSE posts.shares END,
                         is_reply=excluded.is_reply, query=excluded.query,
                         relevance=excluded.relevance,
                         sentiment=CASE WHEN excluded.sentiment <> '' THEN excluded.sentiment
                                        ELSE posts.sentiment END,
                         run=CASE WHEN COALESCE(posts.run,'') = '' THEN excluded.run ELSE posts.run END,
                         updated_at=excluded.updated_at,
                         observed_at=excluded.observed_at,
                         first_seen=COALESCE(posts.first_seen, excluded.first_seen),
                         kind=excluded.kind,
                         dedupe_key=excluded.dedupe_key,
                         summary=CASE WHEN excluded.kind = 'news' THEN excluded.summary
                                      ELSE COALESCE(NULLIF(excluded.summary,''), posts.summary) END""",
                    row,
                )
                if cur:
                    updated += 1
                else:
                    added += 1
                run_urls.append((url, p.get('posted_iso') or ''))
                run_posts += 1
                run_reported += replies or 0

                for i, c in enumerate((p.get('comments') or [])[:MAX_COMMENTS_PER_POST]):
                    curl = c.get('url') or f'{url}#c{i}'
                    ctext = UI_TAIL.sub('', (c.get('text') or '').strip())
                    if _looks_like_profile_card(ctext):
                        continue
                    # every real reply carries a time; feed-side "recommended" blocks do not
                    if not (c.get('posted_iso') or '').strip():
                        continue
                    if not _comment_belongs(ctext, p.get('text') or ''):
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
                    run_comments += 1

            _apply_judgement(conn, path, run_urls)
            _update_run_status(conn, run_key, platform, path, run_posts,
                               run_comments, run_reported, now)
        conn.execute('INSERT INTO ingest_log (files, added, updated, at) VALUES (?,?,?,?)',
                     (files, added, updated, now))

    if verbose:
        print(f'INGEST files={files} added={added} updated={updated} comments={comments}')
    return {'files': files, 'added': added, 'updated': updated, 'comments': comments}
