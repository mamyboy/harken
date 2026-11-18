"""Harken dashboard API — feeds get ingested into SQLite, the page polls it every 2 s.

Run:  .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
import asyncio
import glob
import hashlib
import json
import os
import re
import time

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from . import db, ingest as ingest_mod, translate as translate_mod, sentiment as sentiment_mod

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, 'static')
PROJECT = os.path.expanduser('~/Projects/harken')
INGEST_EVERY = float(os.environ.get('HARKEN_INGEST_SECONDS', '15'))

app = FastAPI(title='Harken Dashboard API', version='1.0.0')


def _fingerprint():
    parts = []
    for f in sorted(glob.glob(os.path.join(PROJECT, '*.jsonl'))):
        if f.endswith('-cand.jsonl'):
            continue
        try:
            st = os.stat(f)
        except OSError:
            continue
        parts.append('%s:%s:%s' % (os.path.basename(f), st.st_size, int(st.st_mtime)))
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:16]


async def _watch_feeds():
    last = None
    while True:
        try:
            fp = _fingerprint()
            if fp != last:
                res = await asyncio.to_thread(ingest_mod.ingest)
                last = fp
                print('[ingest] %s -> %s' % (fp, res), flush=True)
                tr = await asyncio.to_thread(translate_mod.translate_pending)
                if tr.get('pending'):
                    print('[translate] %s' % (tr,), flush=True)
                se = await asyncio.to_thread(sentiment_mod.run)
                if se.get('pending'):
                    print('[sentiment] %s' % (se,), flush=True)
        except Exception as e:
            print('[watch] error %s: %s' % (type(e).__name__, e), flush=True)
        await asyncio.sleep(INGEST_EVERY)


@app.on_event('startup')
async def _startup():
    db.init()
    await asyncio.to_thread(ingest_mod.ingest)
    asyncio.create_task(_watch_feeds())


@app.get('/api/health')
def health():
    with db.db() as conn:
        posts = conn.execute('SELECT COUNT(*) c FROM posts').fetchone()['c']
        last = conn.execute('SELECT * FROM ingest_log ORDER BY id DESC LIMIT 1').fetchone()
    return {
        'ok': True,
        'db': db.DB_PATH,
        'posts': posts,
        'last_ingest': dict(last) if last else None,
        'server_time': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    }


@app.post('/api/ingest')
async def do_ingest():
    return await asyncio.to_thread(ingest_mod.ingest)


@app.get('/health')
def health_alias():
    """Same as /api/health, for uptime checks."""
    return health()


@app.post('/api/translate')
async def do_translate():
    return await asyncio.to_thread(translate_mod.translate_pending)


@app.post('/api/sentiment')
async def do_sentiment():
    return await asyncio.to_thread(sentiment_mod.run)


@app.get('/api/stats')
def stats():
    with db.db() as conn:
        total = conn.execute('SELECT COUNT(*) c FROM posts').fetchone()['c']
        by_platform = [dict(r) for r in conn.execute(
            'SELECT platform, COUNT(*) n FROM posts GROUP BY platform ORDER BY n DESC')]
        by_day = [dict(r) for r in conn.execute(
            "SELECT substr(posted_iso,1,10) d, COUNT(*) n FROM posts "
            "WHERE posted_iso <> '' GROUP BY d ORDER BY d DESC LIMIT 45")]
        translated = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE text_th <> '' AND text_th <> text_raw").fetchone()['c']
        comments = conn.execute('SELECT COUNT(*) c FROM post_comments').fetchone()['c']
        by_sentiment = [dict(r) for r in conn.execute(
            "SELECT COALESCE(NULLIF(sentiment,''),'none') s, COUNT(*) n FROM posts "
            "GROUP BY s ORDER BY n DESC")]
        top_authors = [dict(r) for r in conn.execute(
            'SELECT author, COUNT(*) n, SUM(likes + replies + reposts) eng FROM posts '
            'WHERE author <> \'\' GROUP BY author ORDER BY eng DESC, n DESC LIMIT 8')]
        score = conn.execute(
            'SELECT COALESCE(SUM(likes),0) l, COALESCE(SUM(replies),0) r, '
            'COALESCE(SUM(reposts),0) rp FROM posts').fetchone()
        texts = [r['text_th'] or r['text_raw'] or '' for r in conn.execute(
            'SELECT text_th, text_raw FROM posts LIMIT 800')]

    return {'total': total, 'translated': translated, 'comments': comments,
            'by_platform': by_platform, 'by_day': by_day, 'by_sentiment': by_sentiment,
            'top_authors': top_authors, 'top_terms': top_terms(texts),
            'engagement': {'likes': score['l'], 'replies': score['r'], 'reposts': score['rp']}}


STOPWORDS = set("""
the and for with that this from have has are was were you your our their his her its not but
ได้ ที่ จะ และ ของ ใน การ ให้ ไม่ มี เป็น ว่า ก็ แต่ จาก ไป มา นี้ นั้น เรา เขา คุณ ผม ฉัน
หรือ ถึง ยัง อยู่ แล้ว คือ ต้อง อาจ มาก น้อย คน วัน เรื่อง อย่าง ระหว่าง หลัง ก่อน
ทั้งหมด ทุกคน รวม อื่น เป็นต้น เช่น นี่ และก็ ส่วน ทาง ด้าน ซึ่ง ผู้ คนนั้น ด้วย ถ้า เพราะ
""".split())


def top_terms(texts, limit=20):
    """Frequency of meaningful Thai/Latin terms across post texts."""
    import collections
    cnt = collections.Counter()
    for t in texts:
        for tag in re.findall(r'#[^\s#]+', t or ''):
            cnt[tag] += 2
        for w in re.findall(r'[\u0E00-\u0E7F]{4,}|[A-Za-z][A-Za-z0-9.+_-]{3,}', t or ''):
            wl = w.lower()
            if wl in STOPWORDS or wl.isdigit():
                continue
            # drop URLs/domains/handles/paths — noise, not a talking point
            if re.search(r'[0-9./@:_\\]', w) or wl in ('http', 'https', 'www'):
                continue
            if len(w) > 24:
                continue
            cnt[w] += 1
    return [{'term': k, 'n': v} for k, v in cnt.most_common(limit)]


def _term_list(raw):
    """Split a comma separated term list, drop blanks/dupes, cap at 8."""
    out = []
    for t in (raw or '').split(','):
        t = t.strip().lstrip('#')
        if t and t not in out:
            out.append(t)
    return out[:8]


def _add_filters(where, params, q='', platform='', relevance='', date_from='', date_to='',
                 sentiment='', terms=''):
    """Single source of truth for post filters, shared by API + CSV export."""
    if q.strip():
        where.append('(text_raw LIKE ? OR text_th LIKE ? OR author LIKE ?)')
        like = '%' + q.strip() + '%'
        params += [like, like, like]
    if platform.strip():
        where.append('platform = ?')
        params.append(platform.strip())
    if relevance.strip():
        where.append('relevance = ?')
        params.append(relevance.strip())
    if sentiment.strip():
        where.append("COALESCE(NULLIF(sentiment,''),'none') = ?")
        params.append(sentiment.strip())
    for t in _term_list(terms):
        where.append('(text_raw LIKE ? OR text_th LIKE ?)')
        like = '%' + t + '%'
        params += [like, like]
    if date_from.strip():
        where.append('substr(posted_iso,1,10) >= ?')
        params.append(date_from.strip())
    if date_to.strip():
        where.append('substr(posted_iso,1,10) <= ?')
        params.append(date_to.strip())
    return where, params


@app.get('/api/export.csv')
def export_csv(q: str = '', platform: str = '', date_from: str = '', date_to: str = '',
               sentiment: str = '', terms: str = ''):
    """UTF-8 BOM CSV so Thai opens correctly in Excel."""
    import csv
    import io
    where, params = [], []
    _add_filters(where, params, q, platform, '', date_from, date_to, sentiment, terms)
    sql_where = ('WHERE ' + ' AND '.join(where)) if where else ''

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['วันที่', 'ผู้โพสต์', 'แพลตฟอร์ม', 'อารมณ์', 'ข้อความ(ไทย)', 'ข้อความต้นฉบับ', 'ไลก์', 'ตอบ', 'ลิงก์'])
    with db.db() as conn:
        for r in conn.execute('SELECT * FROM posts ' + sql_where + ' ORDER BY posted_iso DESC', params):
            w.writerow([(r['posted_iso'] or '')[:19].replace('T', ' '), r['author'], r['platform'],
                        r['sentiment'] or '', r['text_th'] or '', r['text_raw'] or '',
                        r['likes'], r['replies'], r['url']])
    body = '\ufeff' + buf.getvalue()
    return Response(content=body, media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="harken-posts.csv"'})


def _iso(s):
    """Parse the mixed posted_iso formats the feeds carry (with/without seconds/tz)."""
    import datetime as dt
    import re as _re
    s = _re.sub(r'[+-]\d{2}:?\d{2}$|Z$', '', (s or ''))[:19]
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return dt.datetime.strptime(s, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None


@app.get('/api/trend')
def trend(gran: str = 'day', days: int = Query(7, ge=1, le=30)):
    """Two comparison windows of real post counts, anchored to the newest post date."""
    import datetime as dt
    with db.db() as conn:
        rows = [r['posted_iso'] for r in conn.execute(
            "SELECT posted_iso FROM posts WHERE posted_iso <> ''") if r['posted_iso']]
    if not rows:
        return {'labels': [], 'cur': [], 'prev': [], 'gran': gran, 'source': 'posts'}

    stamps = [t for t in (_iso(s) for s in rows) if t]
    newest = max(stamps)

    def count(lo, hi):
        c = {}
        for t in stamps:
            if lo <= t < hi:
                k = t.strftime('%m-%d') if gran == 'day' else t.strftime('%H')
                c[k] = c.get(k, 0) + 1
        return c

    if gran == 'day':
        end = newest.replace(hour=23, minute=59, second=59) + dt.timedelta(seconds=1)
        cur_lo, prev_hi = end - dt.timedelta(days=days), end - dt.timedelta(days=days)
        prev_lo = prev_hi - dt.timedelta(days=days)
        cur = count(cur_lo, end)
        prev = count(prev_lo, prev_hi)
        dates = [(end - dt.timedelta(days=i + 1)).date() for i in range(days)][::-1]
        labels = [d.strftime('%m-%d') for d in dates]
        iso = [d.isoformat() for d in dates]
    else:
        hours = 24
        end = (newest + dt.timedelta(hours=1)).replace(minute=0, second=0)
        cur = count(end - dt.timedelta(hours=hours), end)
        prev = count(end - dt.timedelta(hours=2 * hours), end - dt.timedelta(hours=hours))
        hs = [(end - dt.timedelta(hours=i + 1)) for i in range(hours)][::-1]
        labels = [h.strftime('%H') for h in hs]
        iso = [h.strftime('%Y-%m-%dT%H') for h in hs]

    return {'labels': labels, 'iso': iso,
            'cur': [cur.get(l, 0) for l in labels],
            'prev': [prev.get(l, 0) for l in labels],
            'gran': gran, 'from': iso[0] if iso else '', 'to': iso[-1] if iso else ''}


@app.get('/api/terms-changes')
def terms_changes(days: int = Query(7, ge=1, le=60), limit: int = Query(8, ge=1, le=20)):
    """Top terms in the recent window with change vs the previous window (real texts)."""
    import datetime as dt
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT text_th, text_raw, posted_iso FROM posts WHERE posted_iso <> \'\'')]
    if not rows:
        return {'terms': [], 'window_days': days}
    stamps = [t for t in (_iso(r['posted_iso']) for r in rows) if t]
    if not stamps:
        return {'terms': [], 'window_days': days}
    end = max(stamps)
    cur_hi, cur_lo = end, end - dt.timedelta(days=days)
    prev_lo = cur_lo - dt.timedelta(days=days)

    def texts(a, b):
        return [r['text_th'] or r['text_raw'] or '' for r in rows
                if (_iso(r['posted_iso']) is not None and a <= _iso(r['posted_iso']) <= b)]

    cur = {t['term']: t['n'] for t in top_terms(texts(cur_lo, cur_hi), limit=60)}
    prev = {t['term']: t['n'] for t in top_terms(texts(prev_lo, cur_lo), limit=60)}
    terms = []
    for term, n in cur.items():
        p = prev.get(term, 0)
        terms.append({'term': term, 'n': n, 'prev': p, 'chg': n - p})
    terms.sort(key=lambda x: (x['chg'], x['n']), reverse=True)
    return {'terms': terms[:limit], 'window_days': days}


@app.get('/api/issues')
def issues(days: int = Query(7, ge=1, le=60), limit: int = Query(8, ge=1, le=20),
           q: str = '', platform: str = '', sentiment: str = ''):
    """Group posts into topics (issues) by term co-occurrence, not just top terms.

    Terms whose post sets overlap strongly (Jaccard >= 0.5) are treated as one
    talking point, so a story split across several keywords reads as one issue.
    """
    import datetime as dt
    where, params = [], []
    _add_filters(where, params, q, platform, '', '', '', sentiment, '')
    sql_where = ('WHERE ' + ' AND '.join(where)) if where else ''
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT url, author, text_th, text_raw, sentiment, posted_iso, likes FROM posts '
            + sql_where, params)]
    rows = [r for r in rows if _iso(r['posted_iso']) is not None]
    if not rows:
        return {'issues': [], 'window_days': days}

    def body(r):
        return (r['text_th'] or r['text_raw'] or '')

    stamps = [t for t in (_iso(r['posted_iso']) for r in rows) if t]
    end = max(stamps)
    cur_lo = end - dt.timedelta(days=days)
    prev_lo = cur_lo - dt.timedelta(days=days)
    cur = [r for r, t in zip(rows, stamps) if t >= cur_lo]
    prev = [r for r, t in zip(rows, stamps) if prev_lo <= t < cur_lo]
    if not cur:
        return {'issues': [], 'window_days': days}

    cand = top_terms([body(r) for r in cur], limit=40)
    docs = {}
    for t in cand:
        term = t['term']
        docs[term] = {r['url'] for r in cur if term.lower() in body(r).lower()}

    clusters = []  # [{'terms': [...], 'aliases': [...], 'docs': set}]
    for t in sorted(cand, key=lambda x: x['n'], reverse=True):
        term, nd = t['term'], docs[t['term']]
        if len(nd) < 2:
            continue
        best, best_j = None, 0.0
        for c in clusters:
            inter = len(nd & c['docs'])
            if not inter:
                continue
            j = inter / len(nd | c['docs'])
            if j > best_j:
                best, best_j = c, j
        # only merge when the post sets are essentially the same story
        # (#ทรัมป์ vs ทรัมป์); separate-but-overlapping topics stay distinct
        if best and best_j >= 0.85:
            best['aliases'].append(term)
            best['docs'] |= nd
        else:
            clusters.append({'terms': [term], 'aliases': [], 'docs': set(nd)})

    term_n = {t['term']: t['n'] for t in cand}
    out = []
    for c in clusters:
        terms = sorted(c['terms'], key=lambda x: term_n.get(x, 0), reverse=True)[:4]
        label = terms[0]
        members = [r for r in cur if r['url'] in c['docs']]
        prev_n = sum(1 for r in prev if any(t.lower() in body(r).lower() for t in terms))
        mix = {'pos': 0, 'neu': 0, 'neg': 0, 'none': 0}
        for r in members:
            mix[r['sentiment'] if r['sentiment'] in mix else 'none'] += 1
        authors = {}
        for r in members:
            authors[r['author']] = authors.get(r['author'], 0) + 1
        top_author = max(authors.items(), key=lambda kv: kv[1])[0] if authors else ''
        samples = sorted(members, key=lambda r: (_iso(r['posted_iso']), r['likes'] or 0),
                         reverse=True)[:3]
        out.append({
            'label': label,
            'terms': terms,
            'also': c['aliases'][:4],
            'n_posts': len(members),
            'prev_posts': prev_n,
            'chg': len(members) - prev_n,
            'sentiment': mix,
            'top_author': top_author,
            'samples': [{'url': r['url'], 'author': r['author'],
                         'text': body(r)[:180], 'likes': r['likes']} for r in samples],
        })

    out.sort(key=lambda x: (x['chg'], x['n_posts']), reverse=True)
    return {'issues': out[:limit], 'window_days': days, 'candidates': len(cand)}


@app.get('/api/posts')
def posts(
    q: str = '',
    platform: str = '',
    relevance: str = '',
    date_from: str = '',
    date_to: str = '',
    sentiment: str = '',
    terms: str = '',
    sort: str = 'newest',
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    comments: int = Query(0, ge=0, le=1),
):
    where, params = [], []
    _add_filters(where, params, q, platform, relevance, date_from, date_to, sentiment, terms)
    sql_where = ('WHERE ' + ' AND '.join(where)) if where else ''
    order = {'oldest': 'posted_iso ASC',
             'likes': 'likes DESC, posted_iso DESC',
             'engagement': '(likes + replies + reposts) DESC, posted_iso DESC'}.get(sort, 'posted_iso DESC')

    with db.db() as conn:
        total = conn.execute('SELECT COUNT(*) c FROM posts ' + sql_where, params).fetchone()['c']
        rows = [dict(r) for r in conn.execute(
            'SELECT * FROM posts ' + sql_where + ' ORDER BY ' + order + ' LIMIT ? OFFSET ?',
            params + [limit, offset])]
        facets = {
            'platform': {r['platform']: r['n'] for r in conn.execute(
                'SELECT platform, COUNT(*) n FROM posts ' + sql_where + ' GROUP BY platform', params)},
            'sentiment': {r['s']: r['n'] for r in conn.execute(
                "SELECT COALESCE(NULLIF(sentiment,''),'none') s, COUNT(*) n FROM posts "
                + sql_where + ' GROUP BY s', params)},
        }
        if comments and rows:
            urls = [r['url'] for r in rows]
            marks = ','.join('?' * len(urls))
            cs = [dict(r) for r in conn.execute(
                'SELECT * FROM post_comments WHERE url IN (%s) ORDER BY posted_iso DESC' % marks, urls)]
            bucket = {}
            for c in cs:
                bucket.setdefault(c['url'], []).append(c)
            for r in rows:
                r['comments'] = bucket.get(r['url'], [])

    return {'total': total, 'limit': limit, 'offset': offset, 'sort': sort,
            'facets': facets, 'terms_active': _term_list(terms), 'posts': rows}


@app.get('/api/posts/{post_id:path}/comments')
def post_comments(post_id: str):
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT * FROM post_comments WHERE url = ? ORDER BY posted_iso DESC', (post_id,))]
    return {'url': post_id, 'count': len(rows), 'comments': rows}


@app.get('/')
def index():
    """Serve the current dashboard shell — no-store so a stale cache can't show a blank page."""
    return FileResponse(os.path.join(STATIC, 'app.html'),
                        headers={'Cache-Control': 'no-store, must-revalidate'})


@app.get('/vibrant')
def vibrant():
    """Design shell now runs on real data — the prototype route redirects to it."""
    return RedirectResponse('/', status_code=302)


@app.get('/favicon.ico')
def favicon():
    return JSONResponse({}, status_code=204)
