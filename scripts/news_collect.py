#!/usr/bin/env python3
"""Collect news-search results (Google News + Bing News RSS) into a feed file.

No API key: both endpoints are public RSS. The output uses the same jsonl shape
as the social scrapers, so the worker ingests it unchanged, and `platform` is
"news" so the dashboard can keep it in its own table.

  python3 scripts/news_collect.py "ซีพี" --days 30 --limit 40
  -> ~/Projects/harken/news_<quoted keyword>.jsonl
"""
import argparse
import email.utils
import html as html_mod
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
PROJECT = os.path.expanduser('~/Projects/harken')


def fetch(url, timeout=25, tries=3):
    """Google News intermittently answers with an empty feed; retry before believing it."""
    import time
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            body = urllib.request.urlopen(req, timeout=timeout).read()
            if body and len(body) > 400:
                return body
            last = RuntimeError('empty feed (%d bytes)' % len(body or b''))
        except Exception as e:
            last = e
        time.sleep(1.5 * (i + 1))
    raise last


def iso(pub):
    try:
        return email.utils.parsedate_to_datetime(pub).astimezone().isoformat(timespec='minutes')
    except Exception:
        return ''


def clean(html):
    txt = re.sub(r'<[^>]+>', ' ', html or '')
    txt = html_mod.unescape(html_mod.unescape(txt))     # feeds double-encode &nbsp;
    txt = txt.replace('\xa0', ' ')
    txt = unicodedata.normalize('NFC', txt)
    return re.sub(r'\s+', ' ', txt).strip()


def key(title):
    return re.sub(r'[^0-9a-z\u0e00-\u0e7f]+', '', (title or '').lower())[:60]


def google_news(q, days):
    url = ('https://news.google.com/rss/search?q=' + urllib.parse.quote(q) +
           '&hl=th&gl=TH&ceid=TH:th')
    # an empty-but-valid RSS document is a normal Google throttle answer: back off, then
    # try the date-scoped variant of the same query before admitting defeat.
    import time
    variants = [url, url + '&q=' + urllib.parse.quote(q + ' when:' + str(days) + 'd')]
    root, items = None, []
    for attempt in range(4):
        for v in variants:
            try:
                root = ET.fromstring(fetch(v))
            except Exception:
                root = None
                continue
            items = root.findall('.//item') if root is not None else []
            if items:
                break
        if items:
            break
        time.sleep(3 + 4 * attempt)
    if not items:
        raise RuntimeError('Google News returned no items for %r after 4 tries' % q)
    root = ET.fromstring('<rss><channel>' + ''.join(
        ET.tostring(i, encoding='unicode') for i in items) + '</channel></rss>')
    out = []
    for it in root.findall('.//item'):
        title = clean(it.findtext('title') or '')
        src = clean(it.findtext('source') or '')
        title = re.sub(r'\s*-\s*' + re.escape(src) + r'$', '', title) if src else title
        out.append({
            'url': it.findtext('link') or '',
            'title': title,
            'summary': clean(it.findtext('description') or ''),
            'source': src or 'Google News',
            'posted_iso': iso(it.findtext('pubDate')),
            'collector': 'google-news',
        })
    return out


def bing_news(q):
    url = ('https://www.bing.com/news/search?q=' + urllib.parse.quote(q) +
           '&format=RSS&setlang=th-TH')
    try:
        root = ET.fromstring(fetch(url))
    except Exception:
        return []
    out = []
    for it in root.findall('.//item'):
        out.append({
            'url': it.findtext('link') or '',
            'title': clean(it.findtext('title') or ''),
            'summary': clean(it.findtext('description') or ''),
            'source': clean(it.findtext('source') or 'Bing News'),
            'posted_iso': iso(it.findtext('pubDate')),
            'collector': 'bing-news',
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('keyword')
    ap.add_argument('--days', type=int, default=30)
    ap.add_argument('--limit', type=int, default=40)
    ap.add_argument('--no-bing', action='store_true')
    ap.add_argument('--loose', action='store_true',
                    help='keep fuzzy matches (default: the keyword must appear verbatim)')
    ap.add_argument('--out', default='')
    ap.add_argument('--block-source', default='Vietnam.vn',
                    help='comma separated outlets to drop (default: Vietnam.vn — its Thai-language '
                         'edition shows up for Thai keywords but is not Thai public news)')
    ap.add_argument('--allow-blocked', action='store_true', help='ignore --block-source')
    a = ap.parse_args()

    rows = google_news(a.keyword, a.days)
    if not a.no_bing:
        rows += bing_news(a.keyword)

    cutoff = None
    stamps = [r['posted_iso'] for r in rows if r['posted_iso']]
    if stamps and a.days:
        import datetime as dt
        newest = max(stamps)
        try:
            cutoff = (dt.datetime.fromisoformat(newest.replace('Z', '+00:00'))
                      - dt.timedelta(days=a.days)).isoformat(timespec='minutes')
        except Exception:
            cutoff = None

    # Google/Bing match Thai fuzzily ("ปะหวาจัดให้" -> บางหว้า, บางปะกอก). A news item
    # is only kept when the phrase itself appears in its title or summary.
    blocked = set() if a.allow_blocked else {
        b.strip().lower() for b in (a.block_source or '').split(',') if b.strip()}
    if blocked:
        before = len(rows)
        rows = [r for r in rows if (r.get('source') or '').strip().lower() not in blocked]
        if before != len(rows):
            print('INFO | blocked %d rows from %s' % (before - len(rows), ', '.join(sorted(blocked))),
                  file=sys.stderr)
    want = re.sub(r'\s+', '', a.keyword).lower()
    off_topic = 0
    if not a.loose:
        filtered = []
        for r in rows:
            hay = re.sub(r'\s+', '', (r['title'] + ' ' + r['summary'])).lower()
            if want in hay:
                filtered.append(r)
            else:
                off_topic += 1
        rows = filtered

    seen, kept = set(), []
    for r in rows:
        if not r['url'] or not r['title']:
            continue
        k = key(r['title'])
        if not k or k in seen:
            continue
        if cutoff and r['posted_iso'] and r['posted_iso'] < cutoff:
            continue
        seen.add(k)
        kept.append(r)
    kept.sort(key=lambda r: r['posted_iso'] or '', reverse=True)
    kept = kept[:a.limit]

    # feeds repeat the headline inside the description and append " - Source"
    for r in kept:
        t = r['title'].strip()
        sm = r['summary']
        for sep in (' - ', ' | ', ' — '):
            if sm.endswith(sep + r['source']):
                sm = sm[:-(len(sep) + len(r['source']))].strip()
        if sm.lower().startswith(t.lower()):
            sm = sm[len(t):].lstrip(' .-–—:')
        # a description that is only the outlet name is not a summary
        if not sm or sm.strip().lower() == (r['source'] or '').strip().lower() \
                or sm.strip() in ('Google News', 'Bing News'):
            sm = ''
        r['summary'] = sm.strip()

    out = a.out or os.path.join(PROJECT, 'news_' + urllib.parse.quote(a.keyword) + '.jsonl')
    with open(out, 'w', encoding='utf-8') as fh:
        for r in kept:
            fh.write(json.dumps({
                'url': r['url'],
                'platform': 'news',
                'title': r['title'],
                'text': r['title'][:400],
                'summary': r['summary'][:400],
                'source': r['source'],
                'author': r['source'],
                'posted_iso': r['posted_iso'],
                'collector': r['collector'],
            }, ensure_ascii=False) + '\n')
    print(json.dumps({'keyword': a.keyword, 'news': len(kept), 'dropped_offtopic': off_topic,
                      'file': out, 'sources': sorted({r['source'] for r in kept})[:8]},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
