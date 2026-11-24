"""Score sentiment and emotion per post / per comment.

Three poles are not emotions: 'โกรธ', 'กลัว' and 'ผิดหวัง' all collapse into neg,
which answers nothing when the question is *what people feel*. So every row now
carries, next to the legacy pos/neu/neg that the charts already draw:

  emotion   one of EMOTIONS (or neutral)
  polarity  -2 (โกรธ/รุนแรง) .. +2 (ชื่นชมมาก), for ordering rather than buckets
  sarcasm   1 when the literal words mean the opposite of the intent
  aspects   which subject the feeling is about (comma list from ASPECTS)
  conf      how sure the model was -- under REVIEW_BELOW the UI shows 'ควรตรวจ'

The legacy label stays authoritative for existing charts; emotion is the richer
read. polarity must not contradict it, because a chart that draws 'neg' beside a
positive number is a bug, not a nuance.
"""
import time

from . import db, llm

CHUNK = 20
LABELS = ('pos', 'neu', 'neg')
EMOTIONS = ('anger', 'fear', 'disappointment', 'mockery', 'praise', 'neutral')
ASPECTS = ('stock', 'politics', 'person', 'product', 'service', 'other')
MODEL = 'local-llm'
REVIEW_BELOW = 0.70        # under this the row is presented as "ควรตรวจ", not as a label

_POLARITY_HINT = {'pos': 1, 'neu': 0, 'neg': -1}


def pending(limit=400):
    with db.db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT url, text_th, text_raw FROM posts "
            "WHERE (COALESCE(sentiment,'') = '' OR sentiment_conf IS NULL OR emotion IS NULL) "
            "AND COALESCE(kind,'social') = 'social' AND COALESCE(text_raw,'') <> '' LIMIT ?", (limit,))]


def pending_comments(limit=400):
    """Comment rows still missing a sentiment label."""
    with db.db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT c.id, c.text_th, c.text_raw FROM post_comments c "
            "LEFT JOIN posts p ON p.url = c.url "
            "WHERE (COALESCE(c.sentiment,'') = '' OR c.sentiment_conf IS NULL OR c.emotion IS NULL) "
            "AND COALESCE(p.kind,'social') = 'social' "
            "AND COALESCE(c.text_raw,'') <> '' LIMIT ?", (limit,))]


def _clamp_conf(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except Exception:
        return 0.5           # a label with no number is a guess; record it as one


def _polarity(v, label):
    try:
        p = int(round(float(v)))
    except Exception:
        return _POLARITY_HINT.get(label, 0)
    p = max(-2, min(2, p))
    hint = _POLARITY_HINT.get(label, 0)
    if hint and (p > 0) != (hint > 0):
        return hint
    return p


def _aspects(v):
    if isinstance(v, str):
        parts = v.replace(';', ',').split(',')
    elif isinstance(v, (list, tuple)):
        parts = list(v)
    else:
        parts = []
    out = []
    for a in parts:
        a = str(a).strip().lower()
        if a in ASPECTS and a not in out:
            out.append(a)
    return ','.join(out[:3])


def _classify(session_id, items, key='url'):
    payload = [{'i': i, 't': (it.get('text_th') or it.get('text_raw') or '')[:500]}
               for i, it in enumerate(items)]
    prompt = (
        'ให้คะแนนข้อความต่อไปนี้ทีละรายการ\n'
        '- s: pos | neu | neg  (ขั้วรวม ใช้กับกราฟเดิม)\n'
        '- e: อารมณ์หลัก เลือกหนึ่งจาก anger (โกรธ), fear (กลัว/กังวล), '
        'disappointment (ผิดหวัง/เสียดาย), mockery (ล้อเลียน/ประชด), '
        'praise (ชื่นชม/ยินดี), neutral (กลาง/รายงานข่าว)\n'
        '- p: ความเข้ม -2..+2 (-2 โกรธรุนแรง, 0 กลาง, +2 ชื่นชมมาก)\n'
        '- k: 1 ถ้าเป็นคำประชด/แดกดันที่เจตนาตรงข้ามกับคำที่พิมพ์, ไม่งั้น 0\n'
        '- a: หัวข้อที่อารมณ์นั้นพุ่งไป เลือกจาก stock (หุ้น/ตลาด), '
        'politics (การเมือง/นโยบาย), person (ตัวบุคคล), product (สินค้า/เทคโนโลยี), '
        'service (บริการ), other — สูงสุด 3\n'
        '- c: ความมั่นใจ 0-1 (ต่ำกว่า 0.7 เมื่อกำกวม ประชด หรือข้อความสั้นมาก)\n'
        '- w: เหตุผลสั้นไม่เกิน 12 คำ อ้างคำที่อยู่ในข้อความ\n'
        'ตอบเป็น JSON array เท่านั้น รูปแบบ '
        '[{"i":0,"s":"neg","e":"mockery","p":-1,"k":1,"a":["person","stock"],"c":0.78,"w":"..."}] '
        'ห้ามมีข้อความอื่น\n\n'
        + llm.json.dumps(payload, ensure_ascii=False)
    )
    out = llm.json_array(llm.generate(session_id, prompt))
    got = []
    for o in out:
        try:
            i = int(o['i'])
            s = str(o['s']).strip().lower()
        except Exception:
            continue
        if s not in LABELS or i >= len(items):
            continue
        e = str(o.get('e') or '').strip().lower()
        if e not in EMOTIONS:
            e = 'neutral'
        try:
            k = 1 if int(o.get('k')) else 0
        except Exception:
            k = 0
        got.append((items[i][key], s, _clamp_conf(o.get('c')), str(o.get('w') or '')[:200],
                    e, _polarity(o.get('p'), s), k, _aspects(o.get('a'))))
    return got


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
                    # tuple order: (label, conf, why, emotion, polarity, sarcasm, aspects, model, key)
                    conn.executemany(update_sql, [g[1:] + (MODEL, g[0]) for g in got])
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


POST_SQL = ('UPDATE posts SET sentiment=?, sentiment_conf=?, sentiment_why=?, emotion=?, '
            'polarity=?, sarcasm=?, aspects=?, sentiment_model=? WHERE url=?')
COMMENT_SQL = ('UPDATE post_comments SET sentiment=?, sentiment_conf=?, sentiment_why=?, emotion=?, '
               'polarity=?, sarcasm=?, aspects=?, sentiment_model=? WHERE id=?')


def run(timeout_chunks=40):
    """Score pending posts. Returns {pending, scored, failed}."""
    rows = pending()
    if not rows:
        return {'pending': 0, 'scored': 0, 'failed': 0}
    scored, failed, secs = _score(rows, 'url', POST_SQL, timeout_chunks)
    return {'pending': len(rows), 'scored': scored, 'failed': failed, 'seconds': secs}


def run_comments(timeout_chunks=40):
    """Score pending comments so the table can show comment sentiment direction."""
    rows = pending_comments()
    if not rows:
        return {'pending': 0, 'scored': 0, 'failed': 0}
    scored, failed, secs = _score(rows, 'id', COMMENT_SQL, timeout_chunks)
    return {'pending': len(rows), 'scored': scored, 'failed': failed, 'seconds': secs}


def state(row):
    """'ok' | 'review' | 'none' -- how a stored label should be presented."""
    label = (row.get('sentiment') or '').strip()
    if not label:
        return 'none'
    conf = row.get('sentiment_conf')
    if conf is None:
        return 'review'       # a label from before confidences were recorded
    return 'ok' if float(conf) >= REVIEW_BELOW else 'review'
