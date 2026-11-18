"""Classify post sentiment (pos/neu/neg) with beam-free; store in posts.sentiment."""
import time

from . import db, llm

CHUNK = 20
LABELS = ('pos', 'neu', 'neg')


def pending(limit=400):
    with db.db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT url, text_th, text_raw FROM posts "
            "WHERE COALESCE(sentiment,'') = '' AND COALESCE(text_raw,'') <> '' LIMIT ?", (limit,))]


def _classify(session_id, items):
    payload = [{'i': i, 't': (it.get('text_th') or it.get('text_raw') or '')[:500]}
               for i, it in enumerate(items)]
    prompt = (
        'จัดประเภทอารมณ์ของข้อความต่อไปนี้เป็น pos (บวก/ชื่นชม), neu (กลาง/รายงานข่าว) '
        'หรือ neg (ลบ/ตำหนิ/กังวล)\n'
        'ตอบเป็น JSON array เท่านั้น รูปแบบ [{"i":0,"s":"neu"}] ห้ามมีข้อความอื่น\n\n'
        + llm.json.dumps(payload, ensure_ascii=False)
    )
    out = llm.json_array(llm.generate(session_id, prompt))
    got = {}
    for o in out:
        try:
            i = int(o['i'])
            s = str(o['s']).strip().lower()
        except Exception:
            continue
        if s in LABELS:
            got[i] = s
    return [(items[i]['url'], s) for i, s in got.items() if i < len(items)]


def run(timeout_chunks=40):
    """Score pending posts. Returns {pending, scored, failed}."""
    rows = pending()
    if not rows:
        return {'pending': 0, 'scored': 0, 'failed': 0}

    t0 = time.time()
    scored = failed = 0
    session = None
    queue = [rows[i:i + CHUNK] for i in range(0, len(rows), CHUNK)]
    while queue and timeout_chunks > 0:
        chunk = queue.pop(0)
        timeout_chunks -= 1
        try:
            if session is None:
                session = llm.new_session('harken-sentiment')
            got = _classify(session, chunk)
            if got:
                with db.db() as conn:
                    conn.executemany('UPDATE posts SET sentiment = ? WHERE url = ?',
                                     [(s, u) for u, s in got])
                scored += len(got)
        except Exception as e:
            if len(chunk) > 1:
                half = len(chunk) // 2
                queue[:0] = [chunk[:half], chunk[half:]]
                session = None
            else:
                failed += 1
                print('[sentiment] fail %s' % e, flush=True)
    return {'pending': len(rows), 'scored': scored, 'failed': failed,
            'seconds': round(time.time() - t0)}
