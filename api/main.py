"""Harken dashboard API — feeds get ingested into SQLite, the page polls it every 2 s.

Run:  .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
"""
import asyncio
import glob
import hashlib
import json
import mimetypes
import os
import re
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from . import db, ingest as ingest_mod, insight, translate as translate_mod, sentiment as sentiment_mod

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, 'static')
PROJECT = os.environ.get('HARKEN_FEEDS', os.path.expanduser('~/Projects/harken'))
INGEST_EVERY = float(os.environ.get('HARKEN_INGEST_SECONDS', '3'))

mimetypes.add_type('image/svg+xml', '.svg')
app = FastAPI(title='Harken Dashboard API', version='1.0.0')


def _fingerprint():
    return ingest_mod.fingerprint()


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
                sc = await asyncio.to_thread(sentiment_mod.run_comments)
                if sc.get('pending'):
                    print('[sentiment:comments] %s' % (sc,), flush=True)
                rl = await asyncio.to_thread(insight.run_relevance)
                if rl.get('checked'):
                    print('[relevance] %s' % (rl,), flush=True)
        except Exception as e:
            print('[watch] error %s: %s' % (type(e).__name__, e), flush=True)
        await asyncio.sleep(INGEST_EVERY)


@app.on_event('startup')
async def _startup():
    db.init()
    await asyncio.to_thread(ingest_mod.ingest)
    if os.environ.get('HARKEN_EMBED_WORKER', '1') != '0':
        asyncio.create_task(_watch_feeds())
    else:
        print('[watch] embedded worker disabled — expects api.worker', flush=True)


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
    return await asyncio.to_thread(ingest_mod.ingest, PROJECT)


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


def _revision():
    """Cheap snapshot id so the UI can tell two cards apart when polls differ."""
    with db.db() as conn:
        row = conn.execute('SELECT COUNT(*) n FROM posts').fetchone()
        cr = conn.execute('SELECT COUNT(*) n FROM post_comments').fetchone()
        ing = conn.execute('SELECT COALESCE(MAX(id),0) i FROM ingest_log').fetchone()
    return 'r%s.p%s.c%s' % (ing['i'], row['n'], cr['n'])


def _split_headline(body):
    """'รฟท. เตรียม...' must not become the headline 'รฟท'."""
    idx = body.find('. ')
    while idx != -1 and idx < 25:
        idx = body.find('. ', idx + 1)
    if idx == -1:
        return body.strip(), ''
    return body[:idx].strip(), body[idx + 2:].strip()


@app.get('/api/news')
def news(q: str = '', source: str = '', days: int = Query(30, ge=1, le=365),
         limit: int = Query(50, ge=1, le=300), offset: int = Query(0, ge=0),
         sort: str = 'newest'):
    """Web news-search results — a separate dataset from the social listener."""
    import datetime as dt
    where, params = ["COALESCE(kind,'social') = 'news'"], []
    if q:
        where.append('(text_raw LIKE ? OR COALESCE(text_th,\'\') LIKE ? OR author LIKE ?)')
        params += ['%' + q + '%'] * 3
    if source:
        where.append('author = ?')
        params.append(source)
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT url, author AS source, text_raw AS headline, summary, posted_iso, fetched_at, run '
            'FROM posts WHERE ' + ' AND '.join(where), params)]
        sources = [dict(r) for r in conn.execute(
            "SELECT author AS source, COUNT(*) n FROM posts WHERE COALESCE(kind,'social')='news' "
            "AND COALESCE(author,'') <> '' GROUP BY author ORDER BY n DESC")]

    stamped = [(r, _iso(r['posted_iso'])) for r in rows]
    dated = [(r, t) for r, t in stamped if t]
    if dated and days:
        end = max(t for _, t in dated).date()
        start = end - dt.timedelta(days=days - 1)
        rows = [r for r, t in dated if start <= t.date() <= end]
    rows.sort(key=lambda r: (r['posted_iso'] or ''), reverse=(sort != 'oldest'))
    total = len(rows)
    page = rows[offset:offset + limit]
    for r in page:
        r['headline'] = (r.get('headline') or '')[:200]
        r['summary'] = (r.get('summary') or '')[:200]
    return {'news': page, 'total': total, 'sources': sources,
            'days': days, 'offset': offset, 'limit': limit}


@app.get('/api/review')
def review_list(state: str = 'pending', limit: int = Query(50, ge=1, le=200), run: str = ''):
    """Posts the model was unsure about (or that a human flagged) — decide by eye."""
    rw, rp = [], []
    _run_clause(rw, rp, run)
    where = ['COALESCE(review_state,\'auto\') = ?', "COALESCE(kind,'social') = 'social'"] + rw
    params = [state] + rp
    if state == 'pending':
        where = ["COALESCE(review_state,'auto') = 'auto'", "COALESCE(kind,'social') = 'social'",
                 "(COALESCE(noise_state,'') = 'uncertain' OR COALESCE(noise_checked,0) = 0)"] + rw
        params = rp
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT url, platform, author, text_th, text_raw, posted_iso, likes, run,'
            ' noise, noise_state, noise_why, review_state, review_note FROM posts WHERE '
            + ' AND '.join(where) + ' ORDER BY posted_iso DESC LIMIT ?', params + [limit])]
        pending = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE COALESCE(review_state,'auto') = 'auto' "
            "AND COALESCE(kind,'social') = 'social' AND "
            "(COALESCE(noise_state,'') = 'uncertain' OR COALESCE(noise_checked,0) = 0)").fetchone()['c']
    for r in rows:
        r['text'] = (r.get('text_th') or r.get('text_raw') or '')[:220]
    return {'items': rows, 'pending': pending, 'state': state}


@app.post('/api/review')
def review_set(url: str = '', state: str = 'confirmed', note: str = ''):
    """Human decision wins: 'confirmed' keeps the post, 'rejected' hides it, 'auto' re-opens."""
    if state not in ('confirmed', 'rejected', 'auto'):
        raise HTTPException(status_code=400, detail='state must be confirmed|rejected|auto')
    with db.db() as conn:
        cur = conn.execute(
            'UPDATE posts SET review_state = ?, review_note = ?, reviewed_iso = ?,'
            ' noise = CASE WHEN ? = \'rejected\' THEN 1 WHEN ? = \'confirmed\' THEN 0'
            '              WHEN COALESCE(noise_state,\'\') = \'noise\' THEN 1 ELSE 0 END'
            ' WHERE url = ?',
            (state, note, _now(), state, state, url))
        if not cur.rowcount:
            raise HTTPException(status_code=404, detail='post not found')
    return {'ok': True, 'url': url, 'state': state}


@app.get('/api/revision')
def revision():
    return {'revision': _revision(), 'server_time': _now()}


@app.get('/api/stats')
def stats(run: str = '', include_noise: int = 0):
    rw, rp = [], []
    _run_clause(rw, rp, run)
    noise_scope, noise_params = list(rw), list(rp)
    _kind_clause(rw)
    _noise_clause(rw, include_noise)
    W = ('WHERE ' + ' AND '.join(rw)) if rw else ''
    with db.db() as conn:
        total = conn.execute('SELECT COUNT(*) c FROM posts ' + W, rp).fetchone()['c']
        by_platform = [dict(r) for r in conn.execute(
            'SELECT platform, COUNT(*) n FROM posts ' + W + ' GROUP BY platform ORDER BY n DESC', rp)]
        by_day = [dict(r) for r in conn.execute(
            "SELECT substr(posted_iso,1,10) d, COUNT(*) n FROM posts "
            "WHERE posted_iso <> ''" + (' AND ' + ' AND '.join(rw) if rw else '') +
            ' GROUP BY d ORDER BY d DESC LIMIT 45', rp)]
        translated = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE text_th <> '' AND text_th <> text_raw"
            + (' AND ' + ' AND '.join(rw) if rw else ''), rp).fetchone()['c']
        native_th = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE COALESCE(text_th,'') = '' OR text_th = text_raw"
            + (' AND ' + ' AND '.join(rw) if rw else ''), rp).fetchone()['c']
        comments = conn.execute('SELECT COUNT(*) c FROM post_comments').fetchone()['c']
        comment_sentiment = [dict(r) for r in conn.execute(
            "SELECT COALESCE(NULLIF(sentiment,''),'none') s, COUNT(*) n FROM post_comments "
            "GROUP BY s ORDER BY n DESC")]
        posts_with_comments = conn.execute(
            'SELECT COUNT(DISTINCT url) c FROM post_comments').fetchone()['c']
        by_sentiment = [dict(r) for r in conn.execute(
            "SELECT COALESCE(NULLIF(sentiment,''),'none') s, COUNT(*) n FROM posts " + W +
            " GROUP BY s ORDER BY n DESC", rp)]
        top_authors = [dict(r) for r in conn.execute(
            'SELECT author, COUNT(*) n, SUM(likes + replies + reposts) eng FROM posts '
            'WHERE author <> \'\'' + (' AND ' + ' AND '.join(rw) if rw else '') +
            ' GROUP BY author ORDER BY eng DESC, n DESC LIMIT 8', rp)]
        score = conn.execute(
            'SELECT COALESCE(SUM(likes),0) l, COALESCE(SUM(replies),0) r, '
            'COALESCE(SUM(reposts),0) rp FROM posts ' + W, rp).fetchone()
        texts = [r['text_th'] or r['text_raw'] or '' for r in conn.execute(
            'SELECT text_th, text_raw FROM posts ' + W + ' LIMIT 800', rp)]
        hidden_noise = conn.execute(
            "SELECT COUNT(*) c FROM posts WHERE COALESCE(noise,0) = 1 "
            "AND COALESCE(kind,'social') = 'social'"
            + (' AND ' + ' AND '.join(noise_scope) if noise_scope else ''),
            noise_params).fetchone()['c']

    return {'revision': _revision(), 'total': total, 'translated': translated,
            'native_th': native_th,
            'hidden_noise': hidden_noise, 'comments': comments,
            'comment_sentiment': comment_sentiment, 'posts_with_comments': posts_with_comments,
            'by_platform': by_platform, 'by_day': by_day, 'by_sentiment': by_sentiment,
            'top_authors': top_authors, 'top_terms': top_terms(texts),
            'engagement': {'likes': score['l'], 'replies': score['r'], 'reposts': score['rp']}}


STOPWORDS = set("""
the and for with that this from have has are was were you your our their his her its not but
ได้ ที่ จะ และ ของ ใน การ ให้ ไม่ มี เป็น ว่า ก็ แต่ จาก ไป มา นี้ นั้น เรา เขา คุณ ผม ฉัน
หรือ ถึง ยัง อยู่ แล้ว คือ ต้อง อาจ มาก น้อย คน วัน เรื่อง อย่าง ระหว่าง หลัง ก่อน
ทั้งหมด ทุกคน รวม อื่น เป็นต้น เช่น นี่ และก็ ส่วน ทาง ด้าน ซึ่ง ผู้ คนนั้น ด้วย ถ้า เพราะ
ดูเพิ่มเติม See more สมัครเป็นสมาชิก video connections Policy followers Follow
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


def _run_clause(where, params, run='', prefix=''):
    """Restrict any query to one or more search runs (feed files). '' = all runs."""
    runs = [r.strip() for r in (run or '').split(',') if r.strip()]
    if runs:
        where.append(prefix + 'run IN (' + ','.join('?' * len(runs)) + ')')
        params += runs


def _noise_clause(where, include_noise=0):
    """Hide posts the relevance pass flagged as ads / off-topic (default on)."""
    if not include_noise:
        where.append('COALESCE(noise,0) = 0')


def _kind_clause(where, kind='social'):
    """Social rows and news-search rows are separate datasets — never mixed."""
    where.append("COALESCE(kind,'social') = ?") if False else where.append(
        "COALESCE(kind,'social') = '%s'" % ('news' if kind == 'news' else 'social'))


def _add_filters(where, params, q='', platform='', relevance='', date_from='', date_to='',
                 sentiment='', terms='', run=''):
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
    _run_clause(where, params, run)
    return where, params


@app.get('/api/export.csv')
def export_csv(q: str = '', platform: str = '', date_from: str = '', date_to: str = '',
               sentiment: str = '', terms: str = '', run: str = ''):
    """UTF-8 BOM CSV so Thai opens correctly in Excel."""
    import csv
    import io
    where, params = [], []
    _add_filters(where, params, q, platform, '', date_from, date_to, sentiment, terms, run)
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


def _now():
    import datetime as dt
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).strftime('%Y-%m-%dT%H:%M+07:00')


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
def trend(gran: str = 'day', days: int = Query(7, ge=1, le=30), run: str = '',
          include_noise: int = 0):
    """Two comparison windows of real post counts, anchored to the newest post date."""
    import datetime as dt
    rw, rp = [], []
    _run_clause(rw, rp, run)
    _noise_clause(rw, include_noise)
    with db.db() as conn:
        rows = [r['posted_iso'] for r in conn.execute(
            "SELECT posted_iso FROM posts WHERE posted_iso <> ''"
            + (' AND ' + ' AND '.join(rw) if rw else ''), rp) if r['posted_iso']]
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
def terms_changes(days: int = Query(7, ge=1, le=60), limit: int = Query(8, ge=1, le=20),
                  run: str = '', include_noise: int = 0):
    """Top terms in the recent window with change vs the previous window (real texts)."""
    import datetime as dt
    rw, rp = [], []
    _run_clause(rw, rp, run)
    _noise_clause(rw, include_noise)
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT text_th, text_raw, posted_iso FROM posts WHERE posted_iso <> \'\''
            + (' AND ' + ' AND '.join(rw) if rw else ''), rp)]
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
           q: str = '', platform: str = '', sentiment: str = '', run: str = '',
           include_noise: int = 0):
    """Group posts into topics (issues) by term co-occurrence, not just top terms.

    Terms whose post sets overlap strongly (Jaccard >= 0.5) are treated as one
    talking point, so a story split across several keywords reads as one issue.
    """
    import datetime as dt
    where, params = [], []
    _add_filters(where, params, q, platform, '', '', '', sentiment, '', run)
    _kind_clause(where)
    _noise_clause(where, include_noise)
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

    LEGAL = {'บริษัท', 'จำกัด', 'มหาชน', 'จำกัดมหาชน', 'บจก', 'บมจ', 'ออลล์', 'company', 'co'}
    cand = [t for t in top_terms([body(r) for r in cur], limit=40)
            if t['term'] not in LEGAL and len(t['term']) >= 3]
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


def _post_topics(conn, limit=8):
    """Cheap topic map for the table: top terms -> post urls containing them."""
    rows = [dict(r) for r in conn.execute(
        'SELECT url, text_th, text_raw FROM posts')]
    texts = [(r['text_th'] or r['text_raw'] or '') for r in rows]
    topics = []
    for t in top_terms(texts, limit=limit):
        term = t['term']
        urls = [r['url'] for r, txt in zip(rows, texts) if term.lower() in txt.lower()]
        if len(urls) >= 2:
            topics.append({'term': term, 'urls': urls})
    return topics


def _attach_comments(conn, rows, topics):
    """Add comment list, comment sentiment mix, topic and related posts to each row."""
    if not rows:
        return rows
    urls = [r['url'] for r in rows]
    marks = ','.join('?' * len(urls))
    cs = [dict(r) for r in conn.execute(
        'SELECT * FROM post_comments WHERE url IN (%s) ORDER BY posted_iso DESC' % marks, urls)]
    bucket = {}
    for c in cs:
        bucket.setdefault(c['url'], []).append(c)

    for r in rows:
        mine = bucket.get(r['url'], [])
        mix = {'pos': 0, 'neu': 0, 'neg': 0, 'none': 0}
        for c in mine:
            s = c.get('sentiment') or ''
            mix[s if s in mix else 'none'] += 1
        # direction = whichever label carries the most comments (ties -> neu)
        ranked = sorted((('pos', mix['pos']), ('neg', mix['neg']), ('neu', mix['neu'])),
                        key=lambda kv: kv[1], reverse=True)
        direction = ranked[0][0] if ranked[0][1] else 'none'
        if ranked[0][1] and len(ranked) > 1 and ranked[1][1] == ranked[0][1]:
            direction = 'neu'
        r['comments'] = mine
        r['comment_count'] = len(mine)
        r['comment_sentiment'] = mix
        r['comment_direction'] = direction

        body = (r.get('text_th') or r.get('text_raw') or '').lower()
        topic = next((t for t in topics if t['term'].lower() in body), None)
        if topic:
            r['topic'] = topic['term']
            r['topic_posts'] = len(topic['urls'])
            r['related'] = [u for u in topic['urls'] if u != r['url']][:3]
        else:
            r['topic'] = ''
            r['topic_posts'] = 0
            r['related'] = []
    return rows


@app.get('/api/posts')
def posts(
    q: str = '',
    platform: str = '',
    relevance: str = '',
    date_from: str = '',
    date_to: str = '',
    sentiment: str = '',
    terms: str = '',
    run: str = '',
    sort: str = 'newest',
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    comments: int = Query(1, ge=0, le=1),
    include_noise: int = 0,
    include_news: int = 0,
):
    where, params = [], []
    _add_filters(where, params, q, platform, relevance, date_from, date_to, sentiment, terms, run)
    if not include_news:
        _kind_clause(where)
    _noise_clause(where, include_noise)
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
            _attach_comments(conn, rows, _post_topics(conn))

    return {'total': total, 'limit': limit, 'offset': offset, 'sort': sort,
            'facets': facets, 'terms_active': _term_list(terms), 'posts': rows}


@app.get('/api/runs')
def runs():
    """One row per search run (feed file): label, platform, size and date span.

    This is what keeps collections apart — the dashboard shows a run at a time.
    """
    import glob
    import os
    import urllib.parse

    def label_for(key):
        """Friendly label: the query the run searched, else the cleaned file name."""
        path = os.path.join(PROJECT, key + '.jsonl')
        meta = path + '.meta.json'
        if os.path.exists(meta):
            try:
                m = json.load(open(meta, encoding='utf-8'))
                for k in ('keyword', 'intent', 'name', 'topic'):
                    if isinstance(m.get(k), str) and m[k].strip():
                        return m[k].strip(), m.get('queries') or []
            except Exception:
                pass
        base = urllib.parse.unquote(key or '')
        for pre in ('fbfeed_', 'facebook_', 'fb_', 'threads_', 'th_', 'tiktok_', 'tt_',
                    'twitter_', 'tw_', 'x_', 'instagram_', 'ig_', 'youtube_', 'yt_',
                    'pantip_', 'pt_', 'lemon8_', 'l8_'):
            if base.lower().startswith(pre):
                base = base[len(pre):]
                break
        return base or key, []

    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT run, platform, COUNT(*) n, MIN(posted_iso) first_iso, MAX(posted_iso) last_iso, '
            "MIN(fetched_at) loaded_at, SUM(likes + replies + reposts) eng FROM posts "
            "GROUP BY run, platform ORDER BY MAX(posted_iso) DESC")]

    merged = {}
    for r in rows:
        key = r['run'] or ''
        cur = merged.setdefault(key, {'run': key, 'posts': 0, 'platforms': [],
                                      'first_iso': r['first_iso'], 'last_iso': r['last_iso'],
                                      'loaded_at': r['loaded_at'], 'engagement': 0})
        cur['posts'] += r['n']
        cur['engagement'] += r['eng'] or 0
        if r['platform'] and r['platform'] not in cur['platforms']:
            cur['platforms'].append(r['platform'])
        if r['first_iso'] and (not cur['first_iso'] or r['first_iso'] < cur['first_iso']):
            cur['first_iso'] = r['first_iso']
        if r['last_iso'] and (not cur['last_iso'] or r['last_iso'] > cur['last_iso']):
            cur['last_iso'] = r['last_iso']

    with db.db() as conn:
        status_rows = {r['run']: dict(r) for r in conn.execute('SELECT * FROM run_status')}

    out = []
    for key, cur in merged.items():
        label, queries = label_for(key)
        exists = os.path.exists(os.path.join(PROJECT, (key or '') + '.jsonl'))
        st = status_rows.pop(key, {})
        stored = st.get('comments_stored') or 0
        reported = st.get('comments_reported') or 0
        kind = 'news' if str(key).startswith('news_') else 'social'
        out.append(dict(cur, kind=kind, label=label, queries=queries[:6], file_exists=exists,
                        status=st.get('status') or ('missing' if not exists else 'unknown'),
                        note=st.get('note') or '',
                        comments_stored=stored, comments_reported=reported,
                        comments_coverage=(round(stored / reported * 100) if reported and stored <= reported else None),
                        ready_iso=st.get('ready_iso') or ''))
    out.sort(key=lambda x: (x['last_iso'] or '', x['label']), reverse=True)
    return {'runs': out, 'count': len(out), 'total_posts': sum(r['posts'] for r in out)}


@app.post('/api/runs/clear')
def clear_runs(run: str = '', all: int = 0, keep_files: int = 0):
    """Delete one search run, or everything — rows now and the feed file so it can't return.

    Feed files are never destroyed: they are moved to feeds_archive/<timestamp>/.
    """
    import datetime as dt
    import glob
    import os
    import shutil

    runs = [r.strip() for r in (run or '').split(',') if r.strip()]
    if not runs and not all:
        raise HTTPException(status_code=400, detail='ต้องระบุ run หรือ all=1')

    with db.db() as conn:
        if all:
            posts = conn.execute('DELETE FROM posts').rowcount
            comments = conn.execute('DELETE FROM post_comments').rowcount
        else:
            marks = ','.join('?' * len(runs))
            cur = conn.execute('DELETE FROM post_comments WHERE url IN '
                               '(SELECT url FROM posts WHERE run IN (' + marks + '))', runs)
            comments = cur.rowcount
            posts = conn.execute('DELETE FROM posts WHERE run IN (' + marks + ')', runs).rowcount

    archived = []
    if not keep_files:
        stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        dest = os.path.join(PROJECT, 'feeds_archive', stamp)
        targets = (glob.glob(os.path.join(PROJECT, '*.jsonl')) if all else
                   [os.path.join(PROJECT, r + '.jsonl') for r in runs])
        for path in targets:
            if not os.path.exists(path) or path.endswith('-cand.jsonl'):
                continue
            os.makedirs(dest, exist_ok=True)
            base = os.path.basename(path)
            shutil.move(path, os.path.join(dest, base))
            meta = path + '.meta.json'
            if os.path.exists(meta):
                shutil.move(meta, os.path.join(dest, base + '.meta.json'))
            archived.append(os.path.join(dest, base))

    return {'ok': True, 'runs': runs, 'all': bool(all), 'posts_deleted': posts,
            'comments_deleted': comments, 'archived': archived}


@app.get('/api/dims')
def dims(days: int = Query(7, ge=1, le=60), run: str = '', include_noise: int = 0):
    """Every cross-dimension the dashboard can chart, in one request.

    heatmap (weekday x hour), per-day per-platform counts, hour profile, author
    scatter, term co-occurrence, sentiment/engagement per platform, cumulative
    and platform share. Window is anchored on the newest post, like /api/trend.
    """
    import datetime as dt

    def skeleton(days_):
        return {'window': {'days': days_, 'from': '', 'to': ''},
                'heatmap': {'rows': ['จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา'],
                            'cols': ['%02d' % h for h in range(24)], 'cells': [], 'max': 0},
                'platform_day': {'days': [], 'series': []},
                'hour_profile': {'hours': ['%02d' % h for h in range(24)], 'counts': [0] * 24},
                'author_scatter': [], 'term_matrix': {'terms': [], 'matrix': []},
                'sentiment_by_platform': [], 'engagement_by_platform': [],
                'cumulative': {'labels': [], 'values': []}, 'platform_share': []}

    rw, rp = [], []
    _run_clause(rw, rp, run)
    _kind_clause(rw)
    _noise_clause(rw, include_noise)
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT platform, author, text_th, text_raw, sentiment, posted_iso, '
            'likes, replies, reposts FROM posts '
            + ('WHERE ' + ' AND '.join(rw) if rw else ''), rp)]

    stamped = [(r, _iso(r['posted_iso'])) for r in rows]
    stamped = [(r, t) for r, t in stamped if t]
    if not stamped:
        return skeleton(days)

    end = max(t for _, t in stamped).date()
    start = end - dt.timedelta(days=days - 1)
    win = [(r, t) for r, t in stamped if start <= t.date() <= end]
    out = skeleton(days)
    out['window'] = {'days': days, 'from': start.isoformat(), 'to': end.isoformat()}

    # ── heatmap: weekday (จ..อา) x hour ──────────────────────
    cells, grid = [], {}
    for r, t in win:
        k = (t.weekday(), t.hour)
        grid[k] = grid.get(k, 0) + 1
    for (wd, hh), n in sorted(grid.items()):
        cells.append({'r': wd, 'c': hh, 'n': n})
    out['heatmap']['cells'] = cells
    out['heatmap']['max'] = max(grid.values()) if grid else 0

    # ── day axis ─────────────────────────────────────────────
    dates = [start + dt.timedelta(days=i) for i in range(days)]
    day_keys = [d.strftime('%m-%d') for d in dates]
    out['platform_day']['days'] = day_keys

    per_day = {}
    for r, t in win:
        per_day.setdefault((r['platform'] or 'other', t.date()), 0)
        per_day[(r['platform'] or 'other', t.date())] += 1

    plat_label, plat_color = {}, {}
    try:
        import sys as _sys
        scripts = os.path.expanduser('~/.hermes/skills/productivity/social-listening-merge/scripts')
        if scripts not in _sys.path:
            _sys.path.insert(0, scripts)
        import platforms as _platforms
        plat_label = {p['id']: p['label'] for p in _platforms.PLATFORMS}
        plat_color = {p['id']: p['color'] for p in _platforms.PLATFORMS}
    except Exception:
        pass

    platforms_in = sorted({r['platform'] or 'other' for r, _ in win})
    out['platform_day']['series'] = [
        {'platform': p, 'label': plat_label.get(p, p), 'color': plat_color.get(p, '#8C99B4'),
         'values': [per_day.get((p, d), 0) for d in dates]}
        for p in platforms_in]

    # ── hour profile ─────────────────────────────────────────
    hours = [0] * 24
    for r, t in win:
        hours[t.hour] += 1
    out['hour_profile']['counts'] = hours

    # ── authors ──────────────────────────────────────────────
    authors = {}
    for r, t in win:
        a = (r['author'] or '').strip() or '(ไม่ระบุ)'
        cur = authors.setdefault(a, {'author': a, 'posts': 0, 'likes': 0, 'replies': 0,
                                     'engagement': 0, 'mix': {'pos': 0, 'neu': 0, 'neg': 0, 'none': 0}})
        cur['posts'] += 1
        cur['likes'] += r['likes'] or 0
        cur['replies'] += r['replies'] or 0
        cur['engagement'] += (r['likes'] or 0) + (r['replies'] or 0) + (r['reposts'] or 0)
        s = r['sentiment'] or ''
        cur['mix'][s if s in cur['mix'] else 'none'] += 1
    author_rows = []
    for cur in authors.values():
        mix = cur.pop('mix')
        cur['sentiment'] = max(mix, key=lambda k: mix[k]) if any(mix.values()) else 'none'
        author_rows.append(cur)
    author_rows.sort(key=lambda x: (x['engagement'], x['posts']), reverse=True)
    out['author_scatter'] = author_rows[:20]

    # ── term co-occurrence ───────────────────────────────────
    texts = [r['text_th'] or r['text_raw'] or '' for r, _ in win]
    terms = [t['term'] for t in top_terms(texts, limit=8)]
    matrix = []
    for a in terms:
        row = []
        for b in terms:
            n = sum(1 for txt in texts if a.lower() in txt.lower() and b.lower() in txt.lower())
            row.append(n)
        matrix.append(row)
    out['term_matrix'] = {'terms': terms, 'matrix': matrix}

    # ── per-platform sentiment / engagement / share ──────────
    by_plat = {}
    for r, t in win:
        p = r['platform'] or 'other'
        cur = by_plat.setdefault(p, {'platform': p, 'label': plat_label.get(p, p),
                                     'pos': 0, 'neu': 0, 'neg': 0, 'none': 0, 'n': 0,
                                     'likes': 0, 'replies': 0, 'reposts': 0})
        cur['n'] += 1
        s = r['sentiment'] or ''
        cur[s if s in ('pos', 'neu', 'neg') else 'none'] += 1
        cur['likes'] += r['likes'] or 0
        cur['replies'] += r['replies'] or 0
        cur['reposts'] += r['reposts'] or 0
    plats = sorted(by_plat.values(), key=lambda x: x['n'], reverse=True)
    out['sentiment_by_platform'] = [
        {k: v for k, v in p.items() if k in ('platform', 'label', 'pos', 'neu', 'neg', 'none')}
        for p in plats]
    out['engagement_by_platform'] = [
        {k: v for k, v in p.items() if k in ('platform', 'label', 'likes', 'replies', 'reposts')}
        for p in plats]
    out['platform_share'] = [{'platform': p['platform'], 'label': p['label'], 'n': p['n']}
                             for p in plats]

    # ── cumulative ───────────────────────────────────────────
    running, total = [], 0
    for d in dates:
        total += sum(1 for _, t in win if t.date() == d)
        running.append(total)
    out['cumulative'] = {'labels': day_keys, 'values': running}
    return out


@app.get('/api/rankings')
def rankings(days: int = Query(7, ge=1, le=180), limit: int = Query(6, ge=1, le=20),
             run: str = '', include_noise: int = 0):
    """Leaderboards: which posts and which people carry the conversation."""
    import datetime as dt
    rw, rp = [], []
    _run_clause(rw, rp, run)
    _kind_clause(rw)
    _noise_clause(rw, include_noise)
    where = ['1=1'] + rw
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT p.url, p.platform, p.author, p.text_th, p.text_raw, p.likes, p.replies,'
            ' p.reposts, p.sentiment, p.posted_iso,'
            ' (SELECT COUNT(*) FROM post_comments c WHERE c.url = p.url) AS scraped_comments'
            ' FROM posts p WHERE ' + ' AND '.join(where), rp)]
        commenters = [dict(r) for r in conn.execute(
            'SELECT c.author, COUNT(*) n, SUM(c.likes) likes,'
            " SUM(CASE WHEN c.sentiment = 'pos' THEN 1 ELSE 0 END) pos,"
            " SUM(CASE WHEN c.sentiment = 'neg' THEN 1 ELSE 0 END) neg"
            ' FROM post_comments c JOIN posts p ON p.url = c.url'
            ' WHERE ' + ' AND '.join(where) +
            " AND COALESCE(c.author,'') <> '' GROUP BY c.author"
            ' ORDER BY n DESC, likes DESC LIMIT ?', rp + [limit])]

    for r in rows:
        r['engagement'] = (r.get('likes') or 0) + (r.get('replies') or 0) + (r.get('reposts') or 0)
        r['text'] = (r.get('text_th') or r.get('text_raw') or '')[:160]
        r.pop('text_th', None); r.pop('text_raw', None)

    def top(key):
        return sorted(rows, key=lambda x: (x.get(key) or 0), reverse=True)[:limit]

    return {'by_comments': top('scraped_comments'), 'by_likes': top('likes'),
            'by_engagement': top('engagement'), 'by_replies': top('replies'),
            'top_commenters': commenters, 'scanned': len(rows)}


@app.get('/api/comments/summary')
def comments_summary(days: int = Query(30, ge=1, le=180), run: str = '',
                     include_noise: int = 0, refresh: int = 0):
    """อ่านคอมเมนต์แล้วสรุปเป็นสาระ (LLM, cached) — capped at 100 comments."""
    rw, rp = [], []
    _run_clause(rw, rp, run, prefix='p.')
    where = ['1=1'] + rw + ["COALESCE(p.kind,'social') = 'social'"]
    if not include_noise:
        where.append('COALESCE(p.noise,0) = 0')
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT c.id, c.author, c.text_th, c.text_raw, c.likes, c.sentiment, c.posted_iso,'
            ' p.platform, p.author AS post_author FROM post_comments c'
            ' JOIN posts p ON p.url = c.url WHERE ' + ' AND '.join(where) +
            ' ORDER BY c.likes DESC, c.posted_iso DESC', rp)]
    if refresh:
        with db.db() as conn:
            conn.execute("DELETE FROM analysis_cache WHERE key LIKE 'summary:%'")
    out = insight.summarize_comments(rows, run)
    out['comments_available'] = len(rows)
    out['cap'] = insight.MAX_SUMMARY_COMMENTS
    return out


@app.get('/api/comments/insights')
def comments_insights(days: int = Query(30, ge=1, le=180), run: str = ''):
    """Aggregate the scraped comments: volume, sentiment mix, who talks, what about."""
    import datetime as dt
    rw, rp = [], []
    _run_clause(rw, rp, run, prefix='p.')
    where = ['1=1'] + rw
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT c.url, c.author, c.text_raw, c.text_th, c.sentiment, c.posted_iso, '
            'c.likes, p.platform, p.author AS post_author, p.text_raw AS post_text '
            'FROM post_comments c JOIN posts p ON p.url = c.url '
            'WHERE ' + ' AND '.join(where), rp)]
    if not rows:
        return {'total': 0, 'posts': 0, 'sentiment': [], 'by_platform': [],
                'top_commenters': [], 'top_terms': [], 'per_post': [],
                'window': {'days': days, 'from': '', 'to': ''}}

    stamped = []
    for r in rows:
        t = _iso(r['posted_iso'])
        if t:
            stamped.append((r, t))
    end = max((t for _, t in stamped), default=None)
    end_d = end.date() if end else None
    start = (end_d - dt.timedelta(days=days - 1)) if end_d else None
    dated = [r for r, _ in stamped]
    undated = [r for r in rows if not _iso(r['posted_iso'])]
    # comments without a parseable timestamp still count — never silently drop rows
    win = [(r, _iso(r['posted_iso'])) for r in rows
           if not _iso(r['posted_iso'])
           or not start or start <= _iso(r['posted_iso']).date() <= end_d]

    mix = {'pos': 0, 'neu': 0, 'neg': 0, 'none': 0}
    plat, talkers, posts_map = {}, {}, {}
    for r, t in win:
        s_ = r['sentiment'] or ''
        mix[s_ if s_ in mix else 'none'] += 1
        p = r['platform'] or 'other'
        cur = plat.setdefault(p, {'platform': p, 'n': 0, 'pos': 0, 'neg': 0, 'neu': 0})
        cur['n'] += 1
        if s_ in ('pos', 'neg', 'neu'):
            cur[s_] += 1
        a = (r['author'] or '').strip() or '(ไม่ระบุ)'
        talker = talkers.setdefault(a, {'author': a, 'n': 0, 'likes': 0})
        talker['n'] += 1
        talker['likes'] += r['likes'] or 0
        pm = posts_map.setdefault(r['url'], {'url': r['url'], 'platform': p,
                                             'post_author': r['post_author'],
                                             'text': (r['post_text'] or '')[:120],
                                             'n': 0, 'pos': 0, 'neg': 0, 'neu': 0})
        pm['n'] += 1
        if s_ in ('pos', 'neg', 'neu'):
            pm[s_] += 1

    texts = [r['text_th'] or r['text_raw'] or '' for r, _ in win]
    per_post = sorted(posts_map.values(), key=lambda x: x['n'], reverse=True)
    return {
        'total': len(win), 'posts': len(posts_map),
        'sentiment': [{'s': k, 'n': v} for k, v in mix.items() if v],
        'by_platform': sorted(plat.values(), key=lambda x: x['n'], reverse=True),
        'top_commenters': sorted(talkers.values(), key=lambda x: (x['n'], x['likes']),
                                 reverse=True)[:10],
        'top_terms': top_terms(texts, limit=10),
        'per_post': per_post[:20],
        'window': {'days': days,
                   'from': start.isoformat() if start else '',
                   'to': end_d.isoformat() if end_d else ''}}


@app.get('/api/posts/{post_id:path}/comments')
def post_comments(post_id: str):
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            'SELECT * FROM post_comments WHERE url = ? ORDER BY posted_iso DESC', (post_id,))]
    mix = {'pos': 0, 'neu': 0, 'neg': 0, 'none': 0}
    for r in rows:
        s = r.get('sentiment') or ''
        mix[s if s in mix else 'none'] += 1
    return {'url': post_id, 'count': len(rows), 'sentiment': mix, 'comments': rows}


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
    # browsers that ignore the SVG icon still get the brand mark
    return FileResponse(os.path.join(STATIC, 'logo.svg'), media_type='image/svg+xml')


@app.get('/static/{name}')
def static_file(name: str):
    """Serve hand-written assets (charts.js) — no CDN, no build step."""
    path = os.path.normpath(os.path.join(STATIC, name))
    if not path.startswith(STATIC) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail='not found')
    ctype = ('application/javascript' if name.endswith('.js')
             else 'text/css' if name.endswith('.css')
             else 'image/svg+xml' if name.endswith('.svg')
             else 'application/octet-stream')
    return FileResponse(path, media_type=ctype,
                        headers={'Cache-Control': 'no-store, must-revalidate'})
