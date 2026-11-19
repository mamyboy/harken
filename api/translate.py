"""Translate untranslated non-Thai posts with beam-free, then refresh the DB."""
import glob
import json
import os
import re
import subprocess
import sys
import time

from . import db, ingest as ingest_mod

SCRATCH = os.path.expanduser('~/.hermes/cache/scratch')
BEAM = os.path.join(SCRATCH, 'beam_translate.py')
TRANS_IN = os.path.join(SCRATCH, 'trans_in')
TRANSLATIONS = os.path.expanduser('~/Projects/harken/site/translations.json')
THAI = re.compile('[\u0E00-\u0E7F]')


def _ratio(t):
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if THAI.match(c)) / len(letters)


def pending(limit=400):
    """Rows that still need a Thai translation."""
    with db.db() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT url, text_raw, text_th FROM posts "
            "WHERE COALESCE(kind,'social') = 'social' AND COALESCE(text_raw,'') <> '' "
            "AND (text_th IS NULL OR text_th = '' OR text_th = text_raw)")]
    out = []
    for r in rows:
        if _ratio(r['text_raw']) >= 0.3:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def translate_pending(timeout=1800):
    """Build batches from the DB, run beam-free, write translations.json, re-ingest."""
    rows = pending()
    if not rows:
        return {'pending': 0, 'translated': 0}

    os.makedirs(TRANS_IN, exist_ok=True)
    for old in glob.glob(os.path.join(TRANS_IN, 'batch_*.json')):
        os.remove(old)

    seen, batch = set(), []
    for r in rows:
        key = ingest_mod._text_key(r['text_raw'])
        if key in seen:
            continue
        seen.add(key)
        batch.append({'k': key, 't': (r['text_raw'] or '')[:700]})
    json.dump(batch, open(os.path.join(TRANS_IN, 'batch_0.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)

    before = 0
    if os.path.exists(TRANSLATIONS):
        try:
            before = len(json.load(open(TRANSLATIONS, encoding='utf-8')))
        except Exception:
            before = 0

    t0 = time.time()
    env = dict(os.environ, NSHARDS='1')
    proc = subprocess.run([sys.executable, '-u', BEAM], cwd=SCRATCH, capture_output=True,
                          text=True, timeout=timeout, env=env)
    after = before
    if os.path.exists(TRANSLATIONS):
        try:
            after = len(json.load(open(TRANSLATIONS, encoding='utf-8')))
        except Exception:
            after = before

    if after > before:
        ingest_mod.ingest()

    tail = [l for l in ((proc.stdout or '') + (proc.stderr or '')).splitlines()
            if l.startswith(('DONE', 'FAIL'))][-2:]
    return {'pending': len(batch), 'translated': max(0, after - before),
            'seconds': round(time.time() - t0), 'log': tail}
