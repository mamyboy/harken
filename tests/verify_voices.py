#!/usr/bin/env python3
"""The public number must be voices, not message count.

Fixture: one post, 9 near-identical comments from a single account plus 2 real
comments from 2 other people. A message-count dashboard reports 11 comments and
a sentiment mix dominated by the spammer; a voice-count dashboard reports 3
people and names the burst as an anomaly instead.

Checks the JSON contract of /api/comments/insights, not the paint code.
"""
import json
import sqlite3
import sys
import urllib.request

BASE = 'http://localhost:8000'
DB = '/Users/mamyboy/Projects/harken/harken.db'
RUN = 'facebook_voices-test'
POST = 'http://localhost:8000/t/voices'   # a row id only: the suite guard forbids non-local hosts

passed = failed = 0


def check(name, ok, detail=''):
    global passed, failed
    if ok:
        passed += 1
        print(f'  PASS  {name}')
    else:
        failed += 1
        print(f'  FAIL  {name}  {detail}')


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=25) as f:
        return json.loads(f.read())


def seed():
    c = sqlite3.connect(DB)
    c.execute("delete from post_comments where url=?", (POST,))
    c.execute("delete from posts where url=?", (POST,))
    c.execute("""insert into posts (url, platform, author, text_raw, posted_at, posted_iso,
                 fetched_at, kind, run) values (?,?,?,?,?,?,?,?,?)""",
              (POST, 'facebook', 'เพจทดสอบ', 'งานลอยกระทงจังหวัดสตูล', '2026-11-24',
               '2026-11-24T09:00:00+07:00', '2026-11-24T09:00:00+07:00', 'social', RUN))
    rows = []
    for i in range(9):
        rows.append((f'{POST}#spam{i}', POST, 'อเนก อสัมภินวัฒน์', 'เเเเค้น ทรมาน',
                     'neg', 0.85, '2026-11-24T10:0%d:00+07:00' % i))
    rows.append((f'{POST}#a', POST, 'สมชาย', 'สวยมากครับ', 'pos', 0.9,
                 '2026-11-24T11:00:00+07:00'))
    rows.append((f'{POST}#b', POST, 'สมหญิง', 'ปีนี้จัดใหญ่จริง', 'pos', 0.8,
                 '2026-11-24T12:00:00+07:00'))
    c.executemany("""insert into post_comments (id, url, author, text_raw, text_th,
                    sentiment, sentiment_conf, posted_iso) values (?,?,?,?,?,?,?,?)""",
                  [(r[0], r[1], r[2], r[3], r[3], r[4], r[5], r[6]) for r in rows])
    c.commit()
    c.close()


def cleanup():
    c = sqlite3.connect(DB)
    c.execute('delete from post_comments where url=?', (POST,))
    c.execute('delete from posts where url=?', (POST,))
    c.commit()
    c.close()


def main():
    try:
        seed()
        d = get(f'/api/comments/insights?run={RUN}&days=30')

        check('raw total counts every message', d.get('total') == 11, f"total={d.get('total')}")
        check('voices count people-per-post', d.get('voices') == 3, f"voices={d.get('voices')}")
        check('weight is declared as voice', d.get('weight') == 'voice', str(d.get('weight')))

        mix = {r['s']: r['n'] for r in d.get('sentiment', [])}
        check('sentiment mix is per voice (pos 2 / neg 1)', mix.get('pos') == 2 and mix.get('neg') == 1,
              str(mix))

        flood = d.get('flood') or []
        check('burst reported separately', len(flood) == 1 and flood[0]['n'] == 9, str(flood[:1]))
        check('burst names the account', flood and flood[0]['author'] == 'อเนก อสัมภินวัฒน์',
              str(flood[:1]))

        per = {p['url']: p for p in d.get('per_post', [])}
        check('per_post carries both numbers', per.get(POST, {}).get('n') == 3
              and per.get(POST, {}).get('comments') == 11, str(per.get(POST)))

        plat = {p['platform']: p for p in d.get('by_platform', [])}
        check('platform carries both numbers', plat.get('facebook', {}).get('n') == 3
              and plat.get('facebook', {}).get('comments') == 11, str(plat.get('facebook')))

        top = {t['author']: t for t in d.get('top_commenters', [])}
        spammer = top.get('อเนก อสัมภินวัฒน์', {})
        check('spammer is 1 voice but 9 messages',
              spammer.get('n') == 1 and spammer.get('comments') == 9, str(spammer))

        d2 = get(f'/api/comments/insights?run={RUN}&days=30&flood_min=10')
        check('flood_min raises the bar', (d2.get('flood') or []) == [], str(d2.get('flood')))
    finally:
        cleanup()

    print(f'\n{passed} passed, {failed} failed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
