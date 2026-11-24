#!/usr/bin/env python3
"""Rebuild the comment table from the run files, without guessing.

`ingest.py` has heuristics that were written for a news-post feed and they were
silently discarding real replies:

  * TikTok names the commenter `user`, not `author`
  * `_comment_belongs` dropped emoji/sticker-only replies ("🥰🥰🥰")
  * replies whose `posted_iso` the harvester could not read were dropped whole

Rather than keep widening those heuristics until the numbers move, this script
does the one thing the dashboard needs: every comment that exists in a run file
with a non-empty body lands in `post_comments`, keyed by post+author+words so a
re-run cannot double up. Posts themselves stay `ingest.py`'s job.

Usage:  python3 scripts/sync_comments.py [--run satun] [--dry] [--purge]
        --purge  delete this run's comment rows first (clean rebuild)
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from api import db  # noqa: E402

JUNK = re.compile(r'^(?:ชอบ|ถูกใจ|Like|Reply|ตอบกลับ|·|ผู้เขียน|Author|ดูคำแปล|See translation)$')


def body(c):
    """The words a person actually typed, from whichever field the platform used."""
    for k in ('text', 'text_raw', 'body', 'message'):
        t = (c.get(k) or '').strip()
        if t:
            return t
    return ''


def who(c):
    return (c.get('author') or c.get('user') or c.get('nickname')
            or c.get('username') or '').strip()


def liked(c):
    v = c.get('likes')
    if v is None:
        v = (c.get('metrics') or {}).get('likes')
    try:
        return int(str(v).replace(',', '')) if v not in (None, 'None', '') else 0
    except ValueError:
        return 0


def when(c):
    return (c.get('posted_iso') or c.get('posted_at') or '').strip()[:32]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', default='satun', help='only files whose name contains this')
    ap.add_argument('--purge', action='store_true', help='delete these posts\' comments first')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()

    conn = sqlite3.connect(db.path())
    conn.row_factory = sqlite3.Row
    files = [f for f in glob.glob(os.path.join(ROOT, '*.jsonl')) if a.run in os.path.basename(f)]
    if not files:
        print(f'no run files matching {a.run!r}')
        return 1

    seen_posts, rows = 0, []
    for f in sorted(files):
        for line in open(f, encoding='utf-8'):
            if not line.strip():
                continue
            p = json.loads(line)
            url = (p.get('url') or '').strip()
            if not url:
                continue
            seen_posts += 1
            for c in (p.get('comments') or []):
                t = body(c)
                if not t or JUNK.match(t):
                    continue
                rows.append({'url': url, 'author': who(c), 'text': t,
                             'iso': when(c), 'likes': liked(c),
                             'is_author': 1 if c.get('is_author') in (True, 1, 'True', 'true') else 0})
    print(f'files {len(files)} · posts {seen_posts} · comments in files {len(rows)}')

    known = {r[0] for r in conn.execute('select url from posts')}
    orphan = [r for r in rows if r['url'] not in known]
    if orphan:
        print(f'  {len(orphan)} comments belong to posts that are not in the db yet -- run /api/ingest first')
    rows = [r for r in rows if r['url'] in known]

    if a.purge and rows:
        urls = sorted({r['url'] for r in rows})
        n = conn.execute(f'delete from post_comments where url in ({",".join("?" * len(urls))})',
                         urls).rowcount
        print(f'  purged {n} existing comment rows for these {len(urls)} posts')

    inserted = updated = 0
    for r in rows:
        cid = hashlib.sha1(f"{r['url']}|{r['author']}|{r['text']}".encode()).hexdigest()[:20]
        cur = conn.execute(
            """INSERT INTO post_comments (id, url, author, text_raw, text_th, posted_iso, likes, is_author)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET likes=excluded.likes, posted_iso=excluded.posted_iso
               WHERE excluded.likes <> post_comments.likes OR excluded.posted_iso <> post_comments.posted_iso""",
            (cid, r['url'], r['author'], r['text'], r['text'], r['iso'], r['likes'], r['is_author']))
        if cur.rowcount:
            inserted += 1
        else:
            updated += 1
    if a.dry:
        conn.rollback()
        print(f'  dry run: would write {inserted} new / {updated} unchanged')
        return 0
    conn.commit()
    print(f'  written {inserted} new comment rows, {updated} already current')

    per = conn.execute("""select p.platform, count(*) from post_comments m
                          join posts p on p.url = m.url group by 1 order by 1""").fetchall()
    print('  db comments by platform:', {r[0]: r[1] for r in per})
    print('  total rows:', conn.execute('select count(*) from post_comments').fetchone()[0])
    return 0


if __name__ == '__main__':
    sys.exit(main())
