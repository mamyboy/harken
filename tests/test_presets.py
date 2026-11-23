"""Preset search page + runner: the flags each preset must emit."""
import os
import tempfile

os.environ.setdefault('HARKEN_DB', os.path.join(tempfile.mkdtemp(), 'presets.db'))

from fastapi.testclient import TestClient  # noqa: E402

from api import presets  # noqa: E402
from api.main import app  # noqa: E402

client = TestClient(app)


def _cmds(pid, keyword='astracode', **kw):
    return {p: c for p, c, _ in presets.build(presets.by_id(pid), keyword, **kw)}


def test_meta_lists_every_preset():
    b = client.get('/api/presets').json()
    ids = {p['id'] for p in b['presets']}
    assert {'hot-today', 'brand-exists', 'brand-facebook', 'service-feedback',
            'slang', 'compare'} <= ids
    assert set(b['platforms']) == {'x', 'tiktok', 'threads', 'facebook'}


def test_brand_exists_runs_all_time():
    c = _cmds('brand-exists')
    assert 'any' in c['x'] and '--date' in c['x']
    assert c['facebook'][c['facebook'].index('--days') + 1] == '0', 'FB needs --days 0'
    assert '--keep-fuzzy' in c['threads'], 'Threads drops semantic matches without it'


def test_today_preset_uses_today_window():
    c = _cmds('hot-today')
    assert 'today' in c['x'] and 'today' in c['tiktok']
    assert c['facebook'][c['facebook'].index('--days') + 1] == '1'


def test_brand_facebook_harvests_the_page():
    _p, cmd, _log = presets.build(presets.by_id('brand-facebook'), 'astracode',
                                  extra='https://www.facebook.com/astracodeAi')[0]
    assert '--page' in cmd and 'https://www.facebook.com/astracodeAi' in cmd
    assert '--days' in cmd and '0' in cmd


def test_compare_sends_both_brands():
    c = _cmds('compare', keyword='AstraCode', extra='Cursor')
    assert 'AstraCode,Cursor' in c['x'], 'compare must pass both, never as an AND must'


def test_empty_keyword_is_rejected():
    r = client.post('/api/presets/run', params={'preset': 'hot-today', 'keyword': '  '})
    assert r.status_code == 400


def test_unknown_preset_is_rejected():
    r = client.post('/api/presets/run', params={'preset': 'nope', 'keyword': 'x'})
    assert r.status_code == 400


def test_platform_already_running_is_409(monkeypatch):
    monkeypatch.setattr(presets, 'running', lambda jobs=None: {'x'})
    r = client.post('/api/presets/run',
                    params={'preset': 'hot-today', 'keyword': 'TMI', 'platforms': 'x'})
    assert r.status_code == 409
    assert 'x' in r.json()['detail']


def test_page_and_jobs_respond():
    assert client.get('/presets').status_code == 200
    assert 'Preset' in client.get('/presets').text
    assert isinstance(client.get('/api/presets/jobs').json()['jobs'], list)
