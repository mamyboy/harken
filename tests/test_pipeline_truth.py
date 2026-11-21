"""The dashboard must show what the analyst decided — not raw search output.

Covers the three defects found in the 2026-11-20 audit:
  1. an agent's --keep judgement never reached the DB (HAIT: 25 dropped, 11 hidden)
  2. posts outside the run's date window counted as "today"
  3. translation silently did nothing, and foreign text was counted as native Thai
"""
import json
import os
import tempfile

os.environ.setdefault('HARKEN_DB', os.path.join(tempfile.mkdtemp(), 'truth.db'))

from fastapi.testclient import TestClient  # noqa: E402

from api import db, ingest, translate  # noqa: E402
from api.main import app  # noqa: E402

client = TestClient(app)


def _write(d, name, rows, keep=None, meta=None):
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    with open(p, 'w', encoding='utf-8') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    if keep is not None:
        json.dump(keep, open(p + '.keep.json', 'w', encoding='utf-8'), ensure_ascii=False)
    if meta is not None:
        json.dump(meta, open(p + '.meta.json', 'w', encoding='utf-8'), ensure_ascii=False)
    return p


def _row(url):
    with db.db() as conn:
        r = conn.execute('SELECT noise, noise_state, noise_why, noise_checked, review_state '
                         'FROM posts WHERE url = ?', (url,)).fetchone()
        return dict(r) if r else None


def _post(u, text, iso='2026-11-20T10:00+07:00'):
    return {'url': u, 'user': 'a', 'text': text, 'posted_iso': iso}


def test_agent_keep_decision_is_what_the_db_shows():
    d = tempfile.mkdtemp()
    _write(d, 'x_keeptest.jsonl',
           [_post('https://x.com/a/status/1', 'ดีลการค้าไทย-สหรัฐ เซ็นแล้ว'),
            _post('https://x.com/a/status/2', 'Haiti news today'),
            _post('https://x.com/a/status/3', 'HAIT boots sale')],
           keep={'intent': 'ดีลการค้า', 'keep': ['https://x.com/a/status/1'],
                 'why': {'https://x.com/a/status/1': 'ตรงหัวข้อ'}})
    db.init()
    ingest.ingest(project=d)
    assert _row('https://x.com/a/status/1')['noise'] == 0
    for u in ('https://x.com/a/status/2', 'https://x.com/a/status/3'):
        r = _row(u)
        assert r['noise'] == 1, u
        assert r['noise_state'] == 'agent'
        assert r['noise_checked'] == 1, 'the LLM relevance pass must not re-judge it'
        assert 'ไม่ตรง' in (r['noise_why'] or '')


def test_keep_none_hides_the_whole_run():
    d = tempfile.mkdtemp()
    _write(d, 'threads_nonetest.jsonl',
           [_post('https://threads.com/@b/post/1', 'tmi'), _post('https://threads.com/@b/post/2', 'x')],
           keep={'intent': 'HAIT', 'keep': []})
    ingest.ingest(project=d)
    assert _row('https://threads.com/@b/post/1')['noise'] == 1
    assert _row('https://threads.com/@b/post/2')['noise'] == 1


def test_human_review_beats_the_agent():
    d = tempfile.mkdtemp()
    u = 'https://x.com/c/status/9'
    _write(d, 'x_humantest.jsonl', [_post(u, 'ข่าวจริง')], keep={'keep': []})
    ingest.ingest(project=d)
    assert client.post('/api/review', params={'url': u, 'state': 'confirmed'}).status_code == 200
    ingest.ingest(project=d)
    assert _row(u)['noise'] == 0, 'a person confirmed it — re-ingest must not hide it again'


def test_posts_outside_the_run_window_are_hidden():
    d = tempfile.mkdtemp()
    _write(d, 'tiktok_wintest.jsonl',
           [_post('https://tiktok.com/@d/video/1', 'วันนี้', '2026-11-20T09:00+07:00'),
            _post('https://tiktok.com/@d/video/2', 'เก่า', '2026-10-25T09:00+07:00')],
           meta={'since': '2026-11-20', 'until': '2026-11-20'})
    ingest.ingest(project=d)
    assert _row('https://tiktok.com/@d/video/1')['noise'] == 0
    old = _row('https://tiktok.com/@d/video/2')
    assert old['noise'] == 1 and 'นอกช่วงเวลา' in old['noise_why']


def test_translation_runs_in_process_and_fills_text_th(monkeypatch, tmp_path):
    d = tempfile.mkdtemp()
    _write(d, 'x_trtest.jsonl', [_post('https://x.com/e/status/1', 'I got caught in the rain today')])
    ingest.ingest(project=d)
    monkeypatch.setattr(translate, 'TRANSLATIONS', str(tmp_path / 'translations.json'))
    monkeypatch.setattr(translate.llm, 'new_session', lambda title='': 'sid')
    monkeypatch.setattr(translate.llm, 'generate', lambda sid, prompt, timeout=0: '["วันนี้ฉันติดฝน"]')
    res = translate.translate_pending()
    assert res['translated'] >= 1, res
    with db.db() as conn:
        th = conn.execute("SELECT text_th FROM posts WHERE url='https://x.com/e/status/1'").fetchone()[0]
    assert th == 'วันนี้ฉันติดฝน'


def test_translation_failure_is_loud_not_silent(monkeypatch, tmp_path):
    d = tempfile.mkdtemp()
    _write(d, 'x_trfail.jsonl', [_post('https://x.com/f/status/1', 'completely english sentence here')])
    ingest.ingest(project=d)
    monkeypatch.setattr(translate, 'TRANSLATIONS', str(tmp_path / 't.json'))

    def boom(title=''):
        raise RuntimeError('service down')
    monkeypatch.setattr(translate.llm, 'new_session', boom)
    res = translate.translate_pending()
    assert res['translated'] == 0
    assert 'service down' in res.get('error', ''), res


def test_foreign_text_is_not_counted_as_native_thai():
    d = tempfile.mkdtemp()
    _write(d, 'x_natest.jsonl', [_post('https://x.com/g/status/1', '私利私欲の話をするかコムチズTMIを聞く'),
                                 _post('https://x.com/g/status/2', 'ภาษาไทยล้วน ๆ ครับ')])
    ingest.ingest(project=d)
    b = client.get('/api/stats', params={'run': 'x_natest', 'include_noise': 1}).json()
    assert b['native_th'] == 1, b
    assert b.get('untranslated') == 1, b


def test_one_bad_reply_does_not_stop_the_rest(monkeypatch, tmp_path):
    d = tempfile.mkdtemp()
    rows = [_post('https://x.com/h/status/%d' % i, 'english sentence number %d here' % i) for i in range(10)]
    _write(d, 'x_trbad.jsonl', rows)
    ingest.ingest(project=d)
    monkeypatch.setattr(translate, 'TRANSLATIONS', str(tmp_path / 'b.json'))
    monkeypatch.setattr(translate.llm, 'new_session', lambda title='': 'sid')
    calls = {'n': 0}

    def gen(sid, prompt, timeout=0):
        calls['n'] += 1
        if calls['n'] <= 2:
            return 'sorry, not json'          # first chunk: bad twice -> skipped
        n = json.loads(prompt[prompt.index('['):])
        return json.dumps(['ไทย %d' % i for i in range(len(n))], ensure_ascii=False)
    monkeypatch.setattr(translate.llm, 'generate', gen)
    res = translate.translate_pending()
    assert res['translated'] >= 1 and res.get('skipped', 0) >= 1, res
    assert 'error' not in res, 'a later good chunk clears a parse error'
