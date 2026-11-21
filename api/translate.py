"""Translate non-Thai posts and comments into Thai, in-process, then refresh the DB.

The old version shelled out to ~/.hermes/cache/scratch/beam_translate.py. Scratch
is pruned after 24h idle, so one morning the script was simply gone: the worker
logged `translated: 0` forever with an empty log and nobody noticed. Everything
the translator needs now lives in this file plus api/llm.py, and a failure is
returned as `error` so the worker log shows it.
"""
import json
import os
import re
import time

from . import db, ingest as ingest_mod, llm

TRANSLATIONS = os.path.expanduser('~/Projects/harken/site/translations.json')
THAI = re.compile('[\u0E00-\u0E7F]')
CHUNK = 8

PROMPT = (
    'แปลข้อความ social media ต่อไปนี้เป็น**ภาษาไทย** (ทุกชิ้น ไม่ว่าจะเป็นภาษาอังกฤษ จีน '
    'ญี่ปุ่น เกาหลี สเปน ฝรั่งเศส หรือภาษาอื่น)\n'
    '- แปลเอาความหมาย คงชื่อเฉพาะ ชื่อบริษัท ticker ตัวเลข และแฮชแท็กไว้\n'
    '- ถ้าเป็นโพสต์สั้น/แสลง ให้คงน้ำเสียงเดิม (เช่น TMI = เล่าเรื่องส่วนตัวมากไป)\n'
    '- ถ้าข้อความยาว ให้สรุปเป็นไทยไม่เกิน 3 ประโยค\n'
    '- ตอบเป็น JSON array ของสตริง จำนวนเท่ากับข้อความที่ส่งมา ตามลำดับ ห้ามมีข้อความอื่น\n\n'
)


def _ratio(t):
    letters = [c for c in (t or '') if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if THAI.match(c)) / len(letters)


def is_thai(t, thr=0.3):
    """Thai enough to read as-is. Emoji/number-only text counts as Thai (nothing to translate)."""
    letters = [c for c in (t or '') if c.isalpha()]
    return not letters or _ratio(t) >= thr


def _load():
    try:
        return json.load(open(TRANSLATIONS, encoding='utf-8'))
    except Exception:
        return {}


def _save(trans):
    os.makedirs(os.path.dirname(TRANSLATIONS), exist_ok=True)
    tmp = TRANSLATIONS + '.tmp'
    json.dump(trans, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(tmp, TRANSLATIONS)


def apply_cache():
    """Copy cached translations into posts.text_th and post_comments.text_th."""
    trans = _load()
    if not trans:
        return 0
    n = 0
    with db.db() as conn:
        for table in ('posts', 'post_comments'):
            key = 'url' if table == 'posts' else 'id'
            rows = conn.execute(
                'SELECT %s, text_raw FROM %s WHERE COALESCE(text_raw,\'\') <> \'\' '
                'AND (COALESCE(text_th,\'\') = \'\' OR text_th = text_raw)' % (key, table)).fetchall()
            for k, raw in rows:
                v = trans.get(ingest_mod._text_key(raw or ''))
                th = v.get('th') if isinstance(v, dict) else v
                if isinstance(th, str) and th.strip() and th.strip() != (raw or '').strip():
                    conn.execute('UPDATE %s SET text_th = ? WHERE %s = ?' % (table, key), (th.strip(), k))
                    n += 1
    return n


def pending(limit=200):
    """Distinct non-Thai texts (posts + comments) that have no cached translation yet."""
    cached = _load()
    with db.db() as conn:
        texts = [r[0] for r in conn.execute(
            "SELECT text_raw FROM posts WHERE COALESCE(kind,'social') = 'social' "
            "AND COALESCE(text_raw,'') <> '' AND (COALESCE(text_th,'') = '' OR text_th = text_raw) "
            "ORDER BY COALESCE(noise,0), posted_iso DESC")]
        texts += [r[0] for r in conn.execute(
            "SELECT text_raw FROM post_comments WHERE COALESCE(text_raw,'') <> '' "
            "AND (COALESCE(text_th,'') = '' OR text_th = text_raw)")]
    out, seen = [], set()
    for t in texts:
        k = ingest_mod._text_key(t)
        if k in seen or k in cached or is_thai(t):
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def translate_pending(limit=200, timeout=240):
    """Translate what is pending, cache it, write it into the DB. Never raises."""
    todo = pending(limit)
    if not todo:
        return {'pending': 0, 'translated': 0, 'applied': apply_cache()}
    t0 = time.time()
    trans = _load()
    done, error, skipped = 0, '', 0
    for i in range(0, len(todo), CHUNK):
        part = todo[i:i + CHUNK]
        arr = None
        for attempt in range(2):
            try:
                sid = llm.new_session('harken-translate')
                reply = llm.generate(sid, PROMPT + json.dumps([p[:700] for p in part], ensure_ascii=False),
                                     timeout=timeout)
            except Exception as e:
                error = '%s: %s' % (type(e).__name__, e)
                break   # service down — stop now, the next cycle retries
            try:
                arr = llm.json_array(reply)
                break
            except Exception as e:
                error = '%s: %s' % (type(e).__name__, e)   # bad reply: retry once, then skip chunk
        if arr is None:
            if error.startswith(('RuntimeError', 'URLError', 'ConnectionError', 'TimeoutError', 'OSError')):
                break
            skipped += len(part)
            continue
        error = ''
        for src, dst in zip(part, arr):
            if isinstance(dst, str) and dst.strip():
                trans[ingest_mod._text_key(src)] = {'th': dst.strip(), 'src': 'auto', 'engine': 'beam-free'}
                done += 1
        _save(trans)
    out = {'pending': len(todo), 'translated': done, 'applied': apply_cache(),
           'seconds': round(time.time() - t0)}
    if skipped:
        out['skipped'] = skipped
    if error:
        out['error'] = error
    return out
