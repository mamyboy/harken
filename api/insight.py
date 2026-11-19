"""Relevance filter for scraped posts + human-readable summary of comments.

Both use the local LLM (same beam-free session pattern as sentiment.py) and
cache their output in SQLite, so a dashboard refresh never re-runs a model.
A heuristic fallback keeps the dashboard usable when the model is down.
"""
import re
import time

from . import db, llm

NOISE_LABELS = ('noise', 'ok')
MAX_SUMMARY_COMMENTS = 100      # analysis cap the user asked for
AD_RE = re.compile(
    r'(โปรโมชั่น|สั่งซื้อ|สนใจ|ทักแชท|โทร|ราคา|ผ่อน|ส่งฟรี|ขายส่ง|รับสมัคร|'
    r'shopee|lazada|line\s*@|@[a-z0-9_]{4,})', re.I)


def _text(row):
    return (row.get('text_th') or row.get('text_raw') or '').strip()


def heuristic_noise(text, keyword=''):
    """Cheap first pass: obvious ads and empty shells never need the model."""
    t = (text or '').strip()
    kws = [k.strip() for k in (keyword or '').replace('|', ',').split(',') if k.strip()]
    hits_keyword = any(k in t for k in kws)
    if len(t) < 15 and not hits_keyword:
        return True, 'สั้นเกินไป'
    if AD_RE.search(t) and not any(k and k in t for k in keyword.split(',')):
        return True, 'โฆษณา/ขายของ'
    return False, ''


def pending_relevance(limit=200):
    with db.db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT url, run, text_th, text_raw FROM posts "
            "WHERE COALESCE(noise_checked,0) = 0 LIMIT ?", (limit,))]


def _ask(session, rows):
    payload = [{'i': i, 'kw': r.get('run') or '', 't': _text(r)[:400]}
               for i, r in enumerate(rows)]
    prompt = (
        'คุณเป็นผู้คัดกรองข้อมูล social listening ให้ตอบว่าโพสต์ต่อไปนี้ "เกี่ยวกับหัวข้อที่ค้นหา" หรือไม่\n'
        '- ok   = เนื้อหาเกี่ยวข้องกับหัวข้อ/แบรนด์/เหตุการณ์ที่ค้น (kw)\n'
        '- noise= โฆษณา ขายของ โปรโมชั่น เรื่องอื่นโดยบังเอิญมีคำค้น หรือข้อความไร้สาระ\n'
        'ตอบเป็น JSON array เท่านั้น: [{"i":0,"s":"ok","why":"สั้นๆ"}] ห้ามมีข้อความอื่น\n\n'
        + llm.json.dumps(payload, ensure_ascii=False)
    )
    return llm.json_array(llm.generate(session, prompt))


def run_relevance(chunks=8):
    """Label posts ok/noise. Returns {'checked', 'noise', 'failed'}."""
    rows = pending_relevance()
    if not rows:
        return {'checked': 0, 'noise': 0, 'failed': 0}

    checked = noise = failed = 0
    quick, rest = [], []
    for r in rows:
        bad, why = heuristic_noise(_text(r), r.get('run') or '')
        (quick if bad else rest).append((r, why))

    with db.db() as conn:
        for r, why in quick:
            conn.execute('UPDATE posts SET noise = 1, noise_why = ?, noise_checked = 1 WHERE url = ?',
                         (why, r['url']))
        checked += len(quick)
        noise += len(quick)

    session = None
    queue = [rest[i:i + 12] for i in range(0, len(rest), 12)]
    while queue and chunks > 0:
        chunk = queue.pop(0)
        chunks -= 1
        batch = [r for r, _ in chunk]
        try:
            if session is None:
                session = llm.new_session('harken-relevance')
            out = _ask(session, batch)
            got = {}
            for o in out:
                try:
                    i = int(o['i'])
                except Exception:
                    continue
                s = str(o.get('s', '')).strip().lower()
                if s in NOISE_LABELS:
                    got[i] = (s, str(o.get('why', ''))[:80])
            with db.db() as conn:
                for i, (s, why) in got.items():
                    if i >= len(batch):
                        continue
                    conn.execute(
                        'UPDATE posts SET noise = ?, noise_why = ?, noise_checked = 1 WHERE url = ?',
                        (1 if s == 'noise' else 0, why, batch[i]['url']))
            checked += len(got)
            noise += sum(1 for s, _ in got.values() if s == 'noise')
        except Exception:
            failed += len(chunk)
        time.sleep(0.2)
    return {'checked': checked, 'noise': noise, 'failed': failed}


# ── comment summary ──────────────────────────────────────────
def _cache_get(key):
    with db.db() as conn:
        row = conn.execute('SELECT payload, updated_iso FROM analysis_cache WHERE key = ?',
                           (key,)).fetchone()
    return dict(row) if row else None


def _cache_put(key, payload):
    import json
    with db.db() as conn:
        conn.execute(
            'INSERT INTO analysis_cache (key, payload, updated_iso) VALUES (?,?,datetime("now")) '
            'ON CONFLICT(key) DO UPDATE SET payload = excluded.payload, updated_iso = excluded.updated_iso',
            (key, json.dumps(payload, ensure_ascii=False)))


def pick_comments(rows, cap=MAX_SUMMARY_COMMENTS):
    """Most-informative comments first: longest + most liked, capped."""
    scored = sorted(rows, key=lambda r: ((r.get('likes') or 0), len(_text(r))), reverse=True)
    return scored[:cap]


def _extract_json(raw):
    """Model answers sometimes wrap JSON in ```json fences or prose."""
    t = (raw or '').strip()
    if '```' in t:
        t = re.sub(r'^.*?```(?:json)?\s*', '', t, flags=re.S)
        t = t.split('```')[0]
    i, j = t.find('{'), t.rfind('}')
    return t[i:j + 1] if i >= 0 and j > i else t


def summarize_comments(rows, run='') -> dict:
    """Return {'bullets': [...], 'themes': [...], 'source': 'llm'|'heuristic'}."""
    import json
    rows = pick_comments(rows)
    if not rows:
        return {'bullets': [], 'themes': [], 'source': 'empty', 'used': 0}

    key = 'summary:%s:%d:%s' % (run or 'all', len(rows),
                                (rows[0].get('id') or '')[:12])
    cached = _cache_get(key)
    if cached:
        try:
            payload = json.loads(cached['payload'])
            payload['cached_iso'] = cached['updated_iso']
            return payload
        except Exception:
            pass

    payload = [{'i': i, 't': _text(r)[:280]} for i, r in enumerate(rows)]
    prompt = (
        'สรุปสิ่งที่คนพูดในคอมเมนต์ต่อไปนี้เป็นภาษาไทย\n'
        'ตอบเป็น JSON object เท่านั้น: {"bullets":["สรุป 1","สรุป 2","สรุป 3"],'
        '"themes":[{"label":"ประเด็น","n":จำนวนคอมเมนต์โดยประมาณ}]}\n'
        'กติกา: bullets 3-4 ข้อ สั้น กระชับ อ้างจากเนื้อหาจริงเท่านั้น ห้ามแต่งเติม; '
        'themes 2-4 ประเด็น พร้อมจำนวน\n\n'
        + json.dumps(payload, ensure_ascii=False)
    )
    try:
        session = llm.new_session('harken-summary')
        raw = llm.generate(session, prompt)
        data = json.loads(_extract_json(raw))
        bullets = [str(b)[:160] for b in (data.get('bullets') or [])][:4]
        themes = []
        for t in (data.get('themes') or [])[:4]:
            if isinstance(t, dict) and t.get('label'):
                try:
                    n = int(t.get('n') or 0)
                except Exception:
                    n = 0
                themes.append({'label': str(t['label'])[:40], 'n': n})
        if bullets:
            out = {'bullets': bullets, 'themes': themes, 'source': 'llm', 'used': len(rows)}
            _cache_put(key, out)
            return out
    except Exception:
        pass

    # fallback: frequency-based, still grounded in the real text
    from .main import top_terms  # reuse the term extractor
    themes = [{'label': t['term'], 'n': t['n']} for t in
              top_terms([_text(r) for r in rows], limit=4)] if rows else []
    out = {'bullets': [], 'themes': themes, 'source': 'heuristic', 'used': len(rows)}
    _cache_put(key, out)
    return out
