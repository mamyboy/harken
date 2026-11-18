"""API tests for the Harken dashboard (FastAPI + SQLite)."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

TMP_DB = os.path.join(tempfile.mkdtemp(), 'test_harken.db')
os.environ['HARKEN_DB'] = TMP_DB

from api import db, ingest  # noqa: E402
from api.main import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(scope='session', autouse=True)
def _db():
    db.init()
    ingest.ingest()
    yield


def test_health_ok_and_posts_present():
    r = client.get('/api/health')
    assert r.status_code == 200
    body = r.json()
    assert body['ok'] is True
    assert body['posts'] >= 1, 'ingest should have loaded feed posts'


def test_stats_shape():
    r = client.get('/api/stats')
    assert r.status_code == 200
    b = r.json()
    assert b['total'] >= 1
    assert isinstance(b['by_platform'], list) and b['by_platform']
    assert 'by_day' in b and 'translated' in b and 'comments' in b


def test_stats_has_terms_authors_engagement():
    b = client.get('/api/stats').json()
    assert isinstance(b['top_terms'], list) and b['top_terms']
    assert set(b['top_terms'][0]) == {'term', 'n'}
    assert isinstance(b['top_authors'], list) and b['top_authors']
    assert {'author', 'n', 'eng'} <= set(b['top_authors'][0])
    assert {'likes', 'replies', 'reposts'} == set(b['engagement'])


def test_top_terms_drops_url_noise():
    """Terms must be talking points, not domains/handles/paths."""
    for t in client.get('/api/stats').json()['top_terms']:
        assert not any(c in t['term'] for c in './@:0123456789'), t['term']


def test_export_csv_bom_and_header():
    r = client.get('/api/export.csv')
    assert r.status_code == 200
    assert r.text.startswith('\ufeff'), 'BOM required so Excel opens Thai correctly'
    head = r.text.lstrip('\ufeff').splitlines()[0]
    assert 'ผู้โพสต์' in head and 'ข้อความ(ไทย)' in head


def test_posts_offset_pages():
    a = client.get('/api/posts?limit=2&offset=0').json()
    b = client.get('/api/posts?limit=2&offset=2').json()
    assert a['total'] == b['total']
    assert len(b['posts']) == 2
    assert [p['url'] for p in a['posts']] != [p['url'] for p in b['posts']]


def test_posts_newest_first_and_limit():
    r = client.get('/api/posts?limit=5')
    assert r.status_code == 200
    b = r.json()
    assert b['limit'] == 5
    assert len(b['posts']) <= 5
    iso = [p['posted_iso'] for p in b['posts'] if p['posted_iso']]
    assert iso == sorted(iso, reverse=True), 'posts must be newest first'


def test_search_matches_thai_text():
    r = client.get('/api/posts', params={'q': 'ทรัมป์', 'limit': 50})
    assert r.status_code == 200
    b = r.json()
    assert b['total'] >= 1
    for p in b['posts']:
        hay = f"{p['text_raw']} {p['text_th']} {p['author']}"
        assert 'ทรัมป์' in hay


def test_platform_filter():
    r = client.get('/api/posts', params={'platform': 'threads'})
    assert r.status_code == 200
    for p in r.json()['posts']:
        assert p['platform'] == 'threads'


def test_ingest_is_idempotent():
    first = client.post('/api/ingest').json()
    second = client.post('/api/ingest').json()
    assert second['added'] == 0, 're-ingesting must not duplicate rows'
    assert second['updated'] >= first['added']


def test_index_page_served():
    r = client.get('/')
    assert r.status_code == 200
    assert 'Harken' in r.text
    assert '/api/posts' in r.text
    assert 'no-store' in r.headers.get('cache-control', ''), 'shell must not be cached'


def test_issues_group_posts_into_topics():
    d = client.get('/api/issues?days=7&limit=6').json()
    assert 'issues' in d
    for it in d['issues']:
        assert it['label'] and it['n_posts'] > 0
        assert isinstance(it['terms'], list) and it['label'] in it['terms']
        assert set(it['sentiment']) == {'pos', 'neu', 'neg', 'none'}
        assert it['n_posts'] - it['prev_posts'] == it['chg']
    counts = [i['n_posts'] for i in d['issues']]
    assert counts == sorted(counts, reverse=True) or len(counts) <= 1


def test_posts_filter_by_terms_and_sentiment():
    d = client.get('/api/posts?terms=ทรัมป์&limit=100').json()
    assert d['terms_active'] == ['ทรัมป์']
    assert d['total'] >= 1
    for p in d['posts']:
        assert 'ทรัมป์' in (p['text_th'] or '') + (p['text_raw'] or '')

    # facets must describe the filtered set, whatever sentiments exist in the test DB
    assert sum(d['facets']['sentiment'].values()) == d['total']
    assert sum(d['facets']['platform'].values()) == d['total']

    any_sent = next((k for k, v in d['facets']['sentiment'].items() if v), None)
    if any_sent:
        f = client.get('/api/posts?sentiment=' + any_sent + '&limit=1').json()
        assert f['facets']['sentiment'][any_sent] == f['total']
        for p in f['posts']:
            assert (p['sentiment'] or 'none') == any_sent


def test_posts_terms_are_anded():
    one = client.get('/api/posts?terms=ทรัมป์&limit=1').json()['total']
    two = client.get('/api/posts?terms=ทรัมป์,อนุทิน&limit=1').json()['total']
    assert two <= one, 'adding a term must narrow the result set'


def test_comments_carry_sentiment_direction():
    target = client.get('/api/posts?limit=1').json()['posts'][0]['url']
    with db.db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO post_comments (id, url, author, text_raw, text_th, posted_iso, likes, is_author, sentiment)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (target + '#c1', target, 'tester', 'เห็นด้วยมาก', 'เห็นด้วยมาก', '2026-11-18T10:00:00', 3, 0, 'pos'))
        conn.execute(
            "INSERT OR REPLACE INTO post_comments (id, url, author, text_raw, text_th, posted_iso, likes, is_author, sentiment)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (target + '#c2', target, 'tester2', 'ไม่เห็นด้วย', 'ไม่เห็นด้วย', '2026-11-18T11:00:00', 1, 0, 'pos'))

    row = next(p for p in client.get('/api/posts?limit=50').json()['posts'] if p['url'] == target)
    assert row['comment_count'] == 2
    assert row['comment_sentiment']['pos'] == 2
    assert row['comment_direction'] == 'pos'
    assert all(c['sentiment'] for c in row['comments'])
    assert row['topic'], 'every table row should carry a topic link'

    detail = client.get('/api/posts/' + target + '/comments').json()
    assert detail['count'] == 2 and detail['sentiment']['pos'] == 2

    stats = client.get('/api/stats').json()
    assert stats['comments'] >= 2
    assert any(s['s'] == 'pos' for s in stats['comment_sentiment'])

    lean = client.get('/api/posts?comments=0&limit=1').json()['posts'][0]
    assert 'comments' not in lean, 'comments=0 must skip the comment payload'
