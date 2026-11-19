"""Classify post sentiment (pos/neu/neg) with beam-free; store in posts.sentiment."""
import time

from . import db, llm

CHUNK = 20
LABELS = ('pos', 'neu', 'neg')


def pending(limit=400):
    with db.db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT url, text_th, text_raw FROM posts "
            "WHERE COALESCE(sentiment,'') = '' AND COALESCE(kind,'social') = 'social' AND COALESCE(text_raw,'') <> '' LIMIT ?", (limit,))]


def pending_comments(limit=400):
    """Comment rows still missing a sentiment label."""
    with db.db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT c.id, c.text_th, c.text_raw FROM post_comments c "
            "LEFT JOIN posts p ON p.url = c.url "
            "WHERE COALESCE(c.sentiment,'') = '' "
            "AND COALESCE(p.kind,'social') = 'social' "
            "AND COALESCE(c.text_raw,'') <> '' LIMIT ?", (limit,))]


def _classify(session_id, items, key='url'):
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
    return [(items[i][key], s) for i, s in got.items() if i < len(items)]


def _score(rows, key, update_sql, timeout_chunks=40):
    """Classify rows in chunks, halving on failure; returns (scored, failed)."""
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
            got = _classify(session, chunk, key)
            if got:
                with db.db() as conn:
                    conn.executemany(update_sql, [(s, k) for k, s in got])
                scored += len(got)
        except Exception as e:
            if len(chunk) > 1:
                half = len(chunk) // 2
                queue[:0] = [chunk[:half], chunk[half:]]
                session = None
            else:
                failed += 1
                print('[sentiment] fail %s' % e, flush=True)
    return scored, failed, round(time.time() - t0)


def run(timeout_chunks=40):
    """Score pending posts. Returns {pending, scored, failed}."""
    rows = pending()
    if not rows:
        return {'pending': 0, 'scored': 0, 'failed': 0}
    scored, failed, secs = _score(
        rows, 'url', 'UPDATE posts SET sentiment = ? WHERE url = ?', timeout_chunks)
    return {'pending': len(rows), 'scored': scored, 'failed': failed, 'seconds': secs}


def run_comments(timeout_chunks=40):
    """Score pending comments so the table can show comment sentiment direction."""
    rows = pending_comments()
    if not rows:
        return {'pending': 0, 'scored': 0, 'failed': 0}
    scored, failed, secs = _score(
        rows, 'id', 'UPDATE post_comments SET sentiment = ? WHERE id = ?', timeout_chunks)
    return {'pending': len(rows), 'scored': scored, 'failed': failed, 'seconds': secs}
