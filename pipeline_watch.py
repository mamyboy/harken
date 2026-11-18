#!/usr/bin/env python3
"""Harken auto-pipeline: feeds (*.jsonl) -> translate (beam-free) -> rebuild dashboard.

Watches ~/Projects/harken/*.jsonl for new/changed data every POLL seconds.
On change:  extract untranslated non-Thai posts -> beam_translate.py -> build_site.py

Run:  nohup python3 -u ~/Projects/harken/pipeline_watch.py > ~/Projects/harken/pipeline.log 2>&1 &
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HOME = os.path.expanduser('~')
PROJ = os.path.join(HOME, 'Projects/harken')
SITE = os.path.join(PROJ, 'site')
TRANSLATIONS = os.path.join(SITE, 'translations.json')
SKILL = os.path.join(HOME, '.hermes/skills/productivity/social-listening-merge')
SCRATCH = os.path.join(HOME, '.hermes/cache/scratch')
BEAM = os.path.join(SCRATCH, 'beam_translate.py')
TRANS_IN = os.path.join(SCRATCH, 'trans_in')
STATE = os.path.join(SITE, '.pipeline_state.json')
LOG = os.path.join(PROJ, 'pipeline.log')
POLL = int(os.environ.get('POLL', '10'))
THAI = re.compile('[\u0E00-\u0E7F]')


def log(msg):
    line = '[%s] %s' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg)
    print(line, flush=True)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def feeds():
    return sorted(f for f in glob.glob(os.path.join(PROJ, '*.jsonl')) if not f.endswith('-cand.jsonl'))


def fingerprint():
    parts = []
    for f in feeds():
        try:
            st = os.stat(f)
        except OSError:
            continue
        parts.append('%s:%s:%s' % (os.path.basename(f), st.st_size, int(st.st_mtime)))
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:16]


def thai_ratio(t):
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if THAI.match(c)) / len(letters)


def build_batches():
    """Write untranslated non-Thai posts to trans_in/batch_*.json and return the count."""
    sys.path.insert(0, os.path.join(SKILL, 'scripts'))
    from build_site import text_key

    cache = {}
    if os.path.exists(TRANSLATIONS):
        try:
            cache = json.load(open(TRANSLATIONS, encoding='utf-8'))
        except Exception:
            cache = {}

    todo, seen = [], set()
    for f in feeds():
        for line in open(f, encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            try:
                p = json.loads(line)
            except Exception:
                continue
            t = (p.get('text') or '').strip()
            if not t or len(t) < 8 or thai_ratio(t) >= 0.3:
                continue
            k = text_key(t)
            if k in cache or k in seen:
                continue
            seen.add(k)
            todo.append({'k': k, 't': t[:700]})

    os.makedirs(TRANS_IN, exist_ok=True)
    for old in glob.glob(os.path.join(TRANS_IN, 'batch_*.json')):
        os.remove(old)
    if todo:
        json.dump(todo, open(os.path.join(TRANS_IN, 'batch_0.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
    return len(todo)


def run(cmd, cwd=None, timeout=3600):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    out = ((r.stdout or '') + (r.stderr or '')).strip()
    return r.returncode, out


def pipeline(reason):
    t0 = time.time()
    log('PIPELINE start (%s)' % reason)
    try:
        n = build_batches()
        log('  batches: %d posts need translation' % n)
        if n:
            rc, out = run([sys.executable, '-u', BEAM], cwd=SCRATCH,
                          timeout=1800)
            tail = [l for l in out.splitlines() if l.startswith(('DONE', 'FAIL', '  FAIL'))][-3:]
            log('  translate rc=%s %s' % (rc, ' | '.join(tail) or '(no summary)'))
        rc, out = run([sys.executable, os.path.join(SKILL, 'scripts', 'build_site.py')], cwd=SKILL)
        site_line = [l for l in out.splitlines() if l.startswith('SITE')]
        log('  build rc=%s %s' % (rc, site_line[-1] if site_line else out[-200:]))
    except Exception as e:
        log('  ERROR %s: %s' % (type(e).__name__, e))
    log('PIPELINE done in %.0fs' % (time.time() - t0))


def main():
    os.makedirs(SITE, exist_ok=True)
    last = None
    if os.path.exists(STATE):
        try:
            last = json.load(open(STATE, encoding='utf-8')).get('fp')
        except Exception:
            pass
    log('WATCH start · poll=%ss · %d feed files' % (POLL, len(feeds())))
    while True:
        fp = fingerprint()
        if fp != last:
            pipeline('feeds changed %s' % fp)
            last = fp
            try:
                json.dump({'fp': fp, 'at': time.strftime('%Y-%m-%d %H:%M:%S')},
                          open(STATE, 'w', encoding='utf-8'))
            except Exception:
                pass
        time.sleep(POLL)


if __name__ == '__main__':
    main()
