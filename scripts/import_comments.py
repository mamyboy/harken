#!/usr/bin/env python3
"""Import comment bodies into post_comments, then let the pipeline score them.

Feed scrapers often capture engagement counts but not comment text. This makes
comment data land in one place whether it arrives as JSON or JSONL.

Usage:
    .venv/bin/python scripts/import_comments.py comments.json
    echo '[{"url": "...", "user": "...", "text": "..."}]' | \\
        .venv/bin/python scripts/import_comments.py -

Accepted shapes:
  [{url, user|author, text, posted_iso, metrics:{likes}, is_author}, ...]
  {"comments": [ ... ]}            # single post wrapper
  {"<post url>": [comment, ...]}   # grouped by post
"""
import json
import os
import sys

sys.path.insert(0, os.path.expanduser('~/Projects/harken'))

from api import db, sentiment  # noqa: E402


def _rows(payload):
    if isinstance(payload, dict):
        if isinstance(payload.get('comments'), list):
            payload = payload['comments']
        else:
            out = []
            for url, items in payload.items():
                for c in items:
                    out.append(dict(c, url=c.get('url') or url))
            return out
    if not isinstance(payload, list):
        return []
    return payload


def import_payload(payload):
    rows = _rows(payload)
    added = 0
    with db.db() as conn:
        for i, c in enumerate(rows):
            url = c.get('url') or c.get('post_url')
            text = (c.get('text') or c.get('text_raw') or '').strip()
            if not url or not text:
                continue
            cid = c.get('id') or c.get('comment_url') or f"{url}#c{i}"
            m = c.get('metrics') or {}
            likes = c.get('likes', m.get('likes', 0)) or 0
            conn.execute(
                """INSERT INTO post_comments
                   (id, url, author, text_raw, text_th, posted_iso, likes, is_author, sentiment)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     text_raw=excluded.text_raw, text_th=excluded.text_th,
                     likes=excluded.likes, author=excluded.author,
                     posted_iso=excluded.posted_iso,
                     sentiment=CASE WHEN excluded.sentiment <> '' THEN excluded.sentiment
                                    ELSE post_comments.sentiment END""",
                (cid, url, c.get('user') or c.get('author') or '', text, text,
                 c.get('posted_iso') or '', int(likes), 1 if c.get('is_author') else 0,
                 c.get('sentiment') or ''),
            )
            added += 1
    return added


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    raw = sys.stdin.read() if src == '-' else open(src, encoding='utf-8').read()
    payload = [json.loads(line) for line in raw.splitlines() if line.strip()] \
        if src.endswith('.jsonl') else json.loads(raw)
    added = import_payload(payload)
    print(f'imported comments: {added}')
    res = sentiment.run_comments()
    print('sentiment:', res)
    return 0


if __name__ == '__main__':
    sys.exit(main())
