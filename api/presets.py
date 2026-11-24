"""Search presets: one card per recurring search, one keyword to change.

Each preset knows which platforms it runs on, which window it needs and which
flag combinations actually work (a preset is the accumulated fix for a search
that used to return nothing — the `trap` field says which).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

SKILLS = os.path.expanduser('~/.hermes/skills/productivity')
PROJECT = os.path.expanduser('~/Projects/harken')
LOGDIR = os.path.join(PROJECT, 'logs', 'presets')
JOBS = os.path.join(PROJECT, 'logs', 'presets', 'jobs.json')


def _search_python():
    """Pick an interpreter that can `import websocket` — the runners need it.

    The web venv usually lacks websocket-client, and /opt/homebrew/bin/python3 on
    this Mac does too, so guessing from sys.executable is not enough: probe each
    candidate once (this runs at import, five 40ms subprocesses at worst).
    """
    cands = [os.environ.get('HARKEN_SEARCH_PY'), sys.executable,
             shutil.which('python3'), '/usr/bin/python3',
             shutil.which('python3.11'), shutil.which('python3.12'),
             '/opt/homebrew/bin/python3']
    for c in cands:
        if not c or not os.path.exists(c):
            continue
        try:
            r = subprocess.run([c, '-c', 'import websocket'], capture_output=True, timeout=15)
        except Exception:
            continue
        if r.returncode == 0:
            return c
    return sys.executable


PY = _search_python()

PLATFORMS = ('x', 'tiktok', 'threads', 'facebook')
ALL = list(PLATFORMS)

PRESETS = [
    {
        'id': 'hot-today',
        'title': 'ข่าวร้อนวันนี้',
        'desc': 'ค้นทุกแพลตฟอร์ม เฉพาะวันนี้ แล้วให้ agent คัดเฉพาะที่ตรงความหมาย',
        'platforms': ALL,
        'window': 'today',
        'extra': '',
        'trap': 'คำค้นต้องสั้น (1–2 คำ) ถ้าได้ 0 ให้สลับหน้าต่างเป็น "ทุกช่วงเวลา"',
    },
    {
        'id': 'brand-exists',
        'title': 'มีคนพูดถึงแบรนด์ไหม',
        'desc': 'ตรวจการมีอยู่ของแบรนด์/เว็บ ไม่จำกัดเวลา',
        'platforms': ALL,
        'window': 'any',
        'extra': 'domain',
        'extra_label': 'โดเมน (ไม่บังคับ)',
        'trap': 'Threads ใช้ --keep-fuzzy เพราะผลค้นเป็น semantic ไม่มีคำตรงตัว',
    },
    {
        'id': 'brand-facebook',
        'title': 'แบรนด์บน Facebook (เพจ)',
        'desc': 'ดึงโพสต์จากเพจของแบรนด์โดยตรง ไม่พึ่ง keyword',
        'platforms': ['facebook'],
        'window': 'any',
        'extra': 'page',
        'extra_label': 'URL เพจ facebook.com/…',
        'trap': 'ต้อง --days 0 ไม่งั้นเพจที่เงียบจะได้ from_page: 0',
    },
    {
        'id': 'service-feedback',
        'title': 'ฟีดแบ็กบริการ/สถานที่',
        'desc': 'เสียงประชาชนเรื่องบริการของหน่วยงาน/ร้าน/อำเภอ',
        'platforms': ALL,
        'window': '7d',
        'extra': 'place',
        'extra_label': 'พื้นที่ (เช่น สตูล, ละงู)',
        'trap': 'สรุป sentiment ได้เมื่อมี ≥3 โพสต์ น้อยกว่านั้นรายงานทีละโพสต์',
    },
    {
        'id': 'slang',
        'title': 'คำสแลง / คำสั้นกำกวม',
        'desc': 'คำ ≤4 ตัวอักษรที่ชนความหมายอื่น (TMI, HAIT, ANT)',
        'platforms': ALL,
        'window': 'today',
        'extra': '',
        'trap': 'ต้องให้ agent บอกว่าคำนี้หมายถึงอะไร ไม่ใช่สรุปว่าเป็นข่าว',
    },
    {
        'id': 'compare',
        'title': 'เทียบสองแบรนด์',
        'desc': 'ใครถูกพูดถึงมากกว่า และประเด็นคืออะไร',
        'platforms': ALL,
        'window': '7d',
        'extra': 'second',
        'extra_label': 'แบรนด์ที่สอง',
        'trap': 'แยกคำค้นด้วย comma ห้ามให้เป็น AND (จะได้ 0)',
    },
]

WINDOWS = {'today': 'วันนี้', '7d': '7 วัน', '30d': '30 วัน', 'any': 'ทุกช่วงเวลา'}


def by_id(pid):
    return next((p for p in PRESETS if p['id'] == pid), None)


def slug(text, limit=18):
    s = re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')
    return (s or 'kw')[:limit]


def _window_args(platform, window):
    """X/TikTok/Threads take --date/--days; Facebook has no --date, only --days."""
    if window == 'today':
        return ['--days', '1'] if platform == 'facebook' else ['--date', 'today']
    if window == 'any':
        return ['--days', '0'] if platform == 'facebook' else ['--date', 'any']
    days = {'7d': '7', '30d': '30'}.get(window, '30')
    return ['--days', days]


def build(preset, keyword, platforms=None, window=None, extra=''):
    """Return [(platform, argv, log_path), ...] — one process per platform."""
    keyword = (keyword or '').strip()
    if not keyword:
        raise ValueError('keyword is required')
    window = window or preset['window']
    plats = [p for p in (platforms or preset['platforms']) if p in PLATFORMS]
    if not plats:
        raise ValueError('pick at least one platform')

    # --must is one short token: the keyword itself, never the whole sentence
    must = keyword.split(',')[0].strip()
    queries = keyword if preset['id'] != 'compare' or not extra else '%s,%s' % (keyword, extra.strip())
    intent = '%s: %s' % (preset['title'], keyword)
    name = '%s-%s' % (slug(keyword), preset['id'])
    out = []

    for p in plats:
        win = _window_args(p, window)
        if p == 'x':
            cmd = [PY, '-u', f'{SKILLS}/x-cdp-search/scripts/x_run.py',
                   '--intent', intent, '--name', name, '--direct', queries,
                   '--must', must] + win + ['--target', '15', '--comments', '15']
        elif p == 'tiktok':
            cmd = [PY, '-u', f'{SKILLS}/tiktok-cdp-search/scripts/tt_run.py',
                   '--intent', intent, '--name', name, '--direct', queries,
                   '--must', must] + win + ['--target', '15', '--comments', '25']
        elif p == 'threads':
            cmd = [PY, '-u', f'{SKILLS}/threads-cdp-search/scripts/th_run.py',
                   '--intent', intent, '--name', name, '--direct', queries,
                   '--must', must] + win + ['--target', '15', '--comments', '20',
                                            '--keep-fuzzy']
        else:
            cmd = [PY, '-u', f'{SKILLS}/facebook-cdp-search/scripts/fb_search.py',
                   must]
            if extra.strip().startswith('http') and preset['id'] == 'brand-facebook':
                cmd += ['--page', extra.strip(), '--days', '0']
            else:
                cmd += ['--strict'] + win
            cmd += ['--target', '15', '--comments', '25', '--name', name]
        log = os.path.join(LOGDIR, '%s-%s-%s.log' % (name, p, time.strftime('%H%M%S')))
        out.append((p, cmd, log))
    return out


def _load_jobs():
    try:
        return json.load(open(JOBS, encoding='utf-8'))
    except Exception:
        return []


def _save_jobs(jobs):
    os.makedirs(LOGDIR, exist_ok=True)
    tmp = JOBS + '.tmp'
    json.dump(jobs[-60:], open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(tmp, JOBS)


def running(jobs=None):
    """Platforms with a live process — one Chrome tab per platform, never two."""
    jobs = jobs if jobs is not None else _load_jobs()
    live = set()
    for j in jobs:
        if j.get('pid') and _alive(j['pid']):
            live.add(j['platform'])
    return live


def _alive(pid):
    """A live process, not a corpse.

    A finished child that nobody waited on stays in the table as a zombie, and
    os.kill(pid, 0) happily succeeds on it -- which left the platform marked
    busy forever and refused every later search. Reap it and say no.
    """
    try:
        pid = int(pid)
    except Exception:
        return False
    try:
        os.kill(pid, 0)
    except Exception:
        return False
    try:
        with open('/proc/%d/stat' % pid, 'rb') as fh:              # linux
            return fh.read().split(b') ')[-1][:1] != b'Z'
    except OSError:
        pass
    try:
        out = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        if out.startswith('Z'):
            try:
                os.waitpid(pid, os.WNOHANG)                        # reap the corpse
            except Exception:
                pass
            return False
        return bool(out)
    except Exception:
        return True


def start(pid, keyword, platforms=None, window=None, extra=''):
    preset = by_id(pid)
    if not preset:
        raise ValueError('unknown preset: %s' % pid)
    cmds = build(preset, keyword, platforms, window, extra)
    busy = running()
    clash = [p for p, _, _ in cmds if p in busy]
    if clash:
        raise RuntimeError('กำลังค้นอยู่แล้วบน: %s' % ', '.join(clash))

    os.makedirs(LOGDIR, exist_ok=True)
    jobs = _load_jobs()
    started = []
    for platform, cmd, log in cmds:
        fh = open(log, 'w', encoding='utf-8')
        # the dashboard runs inside a venv with PYTHONPATH set; the search scripts
        # must start clean or they import the wrong site-packages (websocket vanishes)
        env = {k: v for k, v in os.environ.items()
               if k not in ('PYTHONPATH', 'VIRTUAL_ENV', 'PYTHONHOME')}
        proc = subprocess.Popen(cmd, cwd=PROJECT, stdout=fh, stderr=subprocess.STDOUT,
                                env=env, start_new_session=True)
        jobs.append({'id': '%s-%s' % (platform, int(time.time() * 1000)),
                     'preset': pid, 'preset_title': preset['title'], 'keyword': keyword,
                     'platform': platform, 'pid': proc.pid, 'log': log,
                     'started': time.strftime('%Y-%m-%dT%H:%M:%S'),
                     'cmd': ' '.join(cmd)})
        started.append({'platform': platform, 'pid': proc.pid, 'log': log})
    _save_jobs(jobs)
    return started


def jobs_view(limit=12, tail=6):
    jobs = _load_jobs()
    out = []
    for j in reversed(jobs[-limit:]):
        alive = bool(j.get('pid')) and _alive(j['pid'])
        try:
            lines = open(j['log'], encoding='utf-8', errors='replace').read().splitlines()
        except Exception:
            lines = []
        out.append({'id': j['id'], 'preset': j['preset'], 'title': j.get('preset_title', ''),
                    'keyword': j.get('keyword', ''), 'platform': j['platform'],
                    'state': 'running' if alive else 'done',
                    'started': j.get('started', ''), 'tail': lines[-tail:],
                    'result': next((l for l in reversed(lines)
                                    if l.startswith(('DONE', 'STOP', 'posts collected'))), '')})
    return out
