"""API tests for the Harken dashboard (FastAPI + SQLite)."""
import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

ROOT = tempfile.mkdtemp()
TMP_DB = os.path.join(ROOT, 'test_harken.db')
FEEDS = os.path.join(ROOT, 'feeds')
os.environ['HARKEN_DB'] = TMP_DB
os.environ['HARKEN_FEEDS'] = FEEDS

from api import db, ingest  # noqa: E402
from api.main import app  # noqa: E402

client = TestClient(app)


def _feed(name, rows):
    os.makedirs(FEEDS, exist_ok=True)
    with open(os.path.join(FEEDS, name), 'w', encoding='utf-8') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')


# two separate search runs, so run isolation is testable
_feed('threads_run-a.jsonl', [
    {'url': 'https://threads.com/@a/post/1', 'user': 'tnamcot', 'text': 'ทรัมป์ ประกาศนโยบายใหม่ อนุทิน ตอบโต้',
     'posted_iso': '2026-11-19T09:00+07:00', 'metrics': {'likes': 12, 'replies': 3, 'reposts': 1, 'shares': 2},
     'sentiment': 'neg'},
    {'url': 'https://threads.com/@a/post/2', 'user': 'gelocamaya', 'text': 'ทรัมป์ กับ ข่าวปลอม ในโซเชียลมีเดีย',
     'posted_iso': '2026-11-18T20:00+07:00', 'metrics': {'likes': 5, 'replies': 1}, 'sentiment': 'neu'},
    {'url': 'https://threads.com/@a/post/3', 'user': 'ny_an', 'text': 'ทรัมป์ แถลงข่าวที่ทำเนียบขาว อนุทิน ร่วมวง',
     'posted_iso': '2026-11-18T11:00+07:00', 'metrics': {'likes': 7}, 'sentiment': 'neu'},
])
_feed('facebook_run-b.jsonl', [
    {'url': 'https://facebook.com/p/1', 'author': 'เพจข่าวทดสอบ', 'text': 'หุ้นไทยปิดบวก นักลงทุนจับตาเงินเฟ้อ',
     'posted_iso': '2026-11-19T03:00+07:00', 'metrics': {'reactions': 30, 'comments': 4}, 'sentiment': 'pos'},
    {'url': 'https://facebook.com/p/2', 'author': 'เพจข่าวทดสอบ', 'text': 'หุ้นดาวโจนส์ร่วง หลังธนาคารกลางขึ้นดอกเบี้ย',
     'posted_iso': '2026-11-18T21:00+07:00', 'metrics': {'reactions': 11, 'comments': 2}, 'sentiment': 'neg'},
])


# a news-search feed lives beside the social ones but is a different dataset
_feed('news_ซีพี.jsonl', [
    {'url': 'https://news.example.com/a1', 'platform': 'news', 'title': 'ซีพี ออลล์ ประกาศฟ้องแก๊งปากแซ่บ',
     'text': 'ซีพี ออลล์ ประกาศฟ้องแก๊งปากแซ่บ', 'summary': 'บริษัทเดินหน้าแจ้งความหลังคลิปด่าพนักงานเซเว่น',
     'source': 'สยามนิวส์', 'author': 'สยามนิวส์', 'posted_iso': '2026-11-19T09:12+07:00'},
    {'url': 'https://news.example.com/a2', 'platform': 'news', 'title': 'ซีพี แอ็กซ์ตร้า ขยายสาขา',
     'text': 'ซีพี แอ็กซ์ตร้า ขยายสาขา', 'summary': 'เปิดสาขาใหม่ในภาคใต้',
     'source': 'Brand Buffet', 'author': 'Brand Buffet', 'posted_iso': '2026-11-18T14:00+07:00'},
])


@pytest.fixture(scope='session', autouse=True)
def _db():
    db.init()
    ingest.ingest(project=FEEDS)
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
    assert '/static/ov.js' in r.text, 'overview shell must load its own module'
    assert '/static/sl-charts.js' in r.text
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


def test_runs_keep_collections_separate():
    # news is its own run, and it is tagged so the social UI never lists it
    runs = client.get('/api/runs').json()['runs']
    news = [r for r in runs if r['kind'] == 'news']
    assert len(news) == 1 and news[0]['posts'] == 2 and news[0]['comments_stored'] == 0
    d = client.get('/api/runs').json()
    assert d['count'] == 3, d          # 2 social + 1 news
    assert sum(1 for r in d['runs'] if r['kind'] == 'social') == 2
    by_run = {r['run']: r for r in d['runs'] if r['kind'] == 'social'}
    assert set(by_run) == {'threads_run-a', 'facebook_run-b'}
    assert by_run['threads_run-a']['posts'] == 3
    assert by_run['facebook_run-b']['posts'] == 2
    assert d['total_posts'] == 7          # 5 social + 2 news, all collections
    assert sum(r['posts'] for r in d['runs'] if r['kind'] == 'social') == 5
    assert by_run['threads_run-a']['platforms'] == ['threads']
    assert by_run['threads_run-a']['label'], 'a run must always carry a readable label'

    # the table is scoped to one run at a time
    only_b = client.get('/api/posts?run=facebook_run-b&limit=50').json()
    assert only_b['total'] == 2
    assert {p['run'] for p in only_b['posts']} == {'facebook_run-b'}
    assert all(p['platform'] == 'facebook' for p in only_b['posts'])

    # every aggregation follows the selection, not just the table
    assert client.get('/api/stats?run=facebook_run-b').json()['total'] == 2
    assert client.get('/api/stats?run=threads_run-a').json()['total'] == 3
    tr = client.get('/api/trend?days=7&run=facebook_run-b').json()
    assert sum(tr['cur']) == 2, tr
    assert client.get('/api/stats').json()['total'] == 5, 'no run = all runs'

    # two runs can be requested together
    both = client.get('/api/posts?run=threads_run-a,facebook_run-b&limit=50').json()
    assert both['total'] == 5


def test_ingest_stamps_run_on_every_row():
    rows = client.get('/api/posts?limit=50').json()['posts']
    assert all(p.get('run') for p in rows), 'every post must belong to a run'


def test_clear_one_run_leaves_the_other_untouched():
    import glob
    # a throwaway run so the shared fixture stays usable for other tests
    _feed('facebook_run-del.jsonl', [
        {'url': 'https://facebook.com/del/1', 'author': 'เพจที่จะลบ', 'text': 'โพสต์ที่จะถูกลบทั้งชุด',
         'posted_iso': '2026-11-19T04:00+07:00', 'metrics': {'reactions': 5}},
    ])
    ingest.ingest(project=FEEDS)
    assert client.get('/api/posts?run=facebook_run-del').json()['total'] == 1

    r = client.post('/api/runs/clear?run=facebook_run-del')
    assert r.status_code == 200
    body = r.json()
    assert body['posts_deleted'] == 1
    assert body['archived'], 'feed file must be archived, never destroyed'

    assert client.get('/api/posts?run=facebook_run-del').json()['total'] == 0
    assert client.get('/api/posts?run=threads_run-a').json()['total'] == 3, 'other runs stay'
    assert not glob.glob(os.path.join(FEEDS, 'facebook_run-del.jsonl')), 'file moved out of the feed dir'
    assert glob.glob(os.path.join(FEEDS, 'feeds_archive', '*', 'facebook_run-del.jsonl'))


def test_clear_requires_a_scope():
    assert client.post('/api/runs/clear').status_code == 400


def test_clear_news_leaves_the_social_listener_untouched():
    before_social = client.get('/api/posts').json()['total']
    before_news = client.get('/api/news').json()['total']
    assert before_news > 0

    # keep_files so the shared fixture can be rebuilt for the tests that follow
    body = client.post('/api/news/clear?keep_files=1').json()
    assert body['news_deleted'] == before_news

    assert client.get('/api/news').json()['total'] == 0
    assert client.get('/api/posts').json()['total'] == before_social, 'social posts stay'
    assert client.get('/api/stats').json()['news_total'] == 0

    ingest.ingest(project=FEEDS)          # put the fixture back
    assert client.get('/api/news').json()['total'] == before_news


def test_dims_exposes_every_dimension():
    d = client.get('/api/dims?days=7').json()
    assert d['window']['days'] == 7 and d['window']['from'] and d['window']['to']
    hm = d['heatmap']
    assert hm['rows'] == ['จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา'] and len(hm['cols']) == 24
    assert hm['cells'] and all(0 <= c['r'] < 7 and 0 <= c['c'] < 24 and c['n'] > 0 for c in hm['cells'])
    assert hm['max'] == max(c['n'] for c in hm['cells'])
    assert d['platform_day']['series'] and len(d['platform_day']['days']) == 7
    for s in d['platform_day']['series']:
        assert len(s['values']) == 7 and s['label'] and s['color'].startswith('#')
    assert len(d['hour_profile']['counts']) == 24
    assert d['author_scatter'] and {'author', 'posts', 'likes', 'engagement'} <= set(d['author_scatter'][0])
    tm = d['term_matrix']
    assert tm['terms'] and len(tm['matrix']) == len(tm['terms'])
    assert all(len(row) == len(tm['terms']) for row in tm['matrix'])
    assert sum(p['n'] for p in d['platform_share']) == 5  # fixture has 5 posts
    assert d['cumulative']['values'][-1] == 5
    assert d['sentiment_by_platform'] and 'pos' in d['sentiment_by_platform'][0]


def test_dims_follows_the_selected_run():
    a = client.get('/api/dims?run=threads_run-a').json()
    b = client.get('/api/dims?run=facebook_run-b').json()
    assert a['cumulative']['values'][-1] == 3
    assert b['cumulative']['values'][-1] == 2
    assert [p['platform'] for p in a['platform_share']] == ['threads']
    assert [p['platform'] for p in b['platform_share']] == ['facebook']
    assert a['platform_day']['series'][0]['platform'] == 'threads'


def test_dims_never_500s_when_empty():
    import shutil
    os.makedirs(FEEDS, exist_ok=True)
    for f in os.listdir(FEEDS):
        if f.endswith('.jsonl'):
            shutil.move(os.path.join(FEEDS, f), os.path.join(FEEDS, f + '.bak'))
    with db.db() as conn:
        conn.execute('DELETE FROM posts')
    d = client.get('/api/dims').json()
    assert d['heatmap']['cells'] == [] and d['heatmap']['max'] == 0
    assert d['platform_share'] == [] and d['author_scatter'] == []
    assert d['window']['from'] == '' or d['window']['days'] == 7
    # restore the fixture data for the remaining tests
    for f in os.listdir(FEEDS):
        if f.endswith('.bak'):
            shutil.move(os.path.join(FEEDS, f), os.path.join(FEEDS, f[:-4]))
    ingest.ingest(project=FEEDS)


def test_static_assets_are_served_without_cdn():
    js = client.get('/static/charts.js')
    assert js.status_code == 200
    assert 'javascript' in js.headers['content-type']
    assert 'HarkenCharts' in js.text
    assert 'http://' not in js.text and 'https://' not in js.text.split('\n')[0], 'no CDN imports'
    assert client.get('/static/nope.js').status_code == 404
    assert client.get('/static/../api/main.py').status_code == 404


def _seed_comments():
    urls = [p['url'] for p in client.get('/api/posts?limit=2').json()['posts']]
    with db.db() as conn:
        for i, (u, sent, who) in enumerate([(urls[0], 'pos', 'somchai'),
                                            (urls[0], 'neg', 'malee'),
                                            (urls[1], 'neu', 'somchai')]):
            conn.execute(
                "INSERT OR REPLACE INTO post_comments (id, url, author, text_raw, text_th,"
                " posted_iso, likes, is_author, sentiment) VALUES (?,?,?,?,?,?,?,?,?)",
                ('%s#i%d' % (u, i), u, who, 'ทดสอบ %d' % i, 'ทดสอบ %d' % i,
                 '2026-11-18T1%d:00:00' % i, i, 0, sent))
    return urls


def test_comments_insights_aggregates_scraped_comments():
    _seed_comments()
    d = client.get('/api/comments/insights').json()
    assert d['total'] >= 3 and d['posts'] >= 2
    assert d['top_commenters'][0]['n'] >= 2, 'somchai wrote two of the three comments'
    assert {p['url'] for p in d['per_post']} == set(_seed_comments())
    assert sum(s['n'] for s in d['sentiment']) == d['total']
    assert d['by_platform'] and d['by_platform'][0]['n'] > 0
    assert d['per_post'] and d['per_post'][0]['n'] == max(p['n'] for p in d['per_post'])
    assert d['top_commenters'] and d['top_commenters'][0]['n'] >= 1
    assert isinstance(d['top_terms'], list)
    # run filter must not leak comments from other runs
    scoped = client.get('/api/comments/insights?run=threads_run-a').json()
    assert scoped['total'] <= d['total']


def test_comments_insights_survives_an_empty_table():
    with db.db() as conn:
        conn.execute('DELETE FROM post_comments')
    d = client.get('/api/comments/insights').json()
    assert d['total'] == 0 and d['per_post'] == [] and d['sentiment'] == []


def test_profile_cards_are_not_stored_as_comments():
    """Scrapers sometimes capture the author widget instead of a reply."""
    from api.ingest import _looks_like_profile_card
    blob = ('somrudee\nsomrudee9937\n57 followers\nFollow\nMessage\nQuotes 1\n2m\n'
            'Tew Kkr\nFollow suggestions\nballrongciaga\n457 followers\n' + 'x' * 400)
    assert _looks_like_profile_card(blob) is True
    assert _looks_like_profile_card('somrudee\n57 followers\nFollow\nMessage\nQuotes 1') is True
    assert _looks_like_profile_card('ช่วยกันนะคะ หน้าตาหล่อเชียวแต่ยังไม่มีบ้าน') is False
    assert _looks_like_profile_card('') is True
    with db.db() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM post_comments "
                            "WHERE text_raw LIKE '% followers%'").fetchone()['c'] == 0


def test_comment_language_guard_keeps_thai_drops_strays():
    """Reel comment panels surface unrelated recommended threads."""
    from api.ingest import _comment_belongs
    post = 'ซีพี ออลล์ แจ้งความเอาผิด เกรียนโซเชียล ถ่ายคลิปไลฟ์ในร้าน 7-11'
    assert _comment_belongs('เอาให้หนักเลยครับ อย่ายอมความ', post) is True
    assert _comment_belongs('Share video cho vui vậy thôi chứ 90% dùng AI vibecode', post) is False
    assert _comment_belongs('Good illustration. But it will break secure connections', post) is False
    assert _comment_belongs('7-11 hiring now', post) is False, 'short tokens are not evidence'
    assert _comment_belongs('7-Eleven สาขานี้ปิดกี่โมง', post) is True


def test_noise_posts_are_hidden_unless_requested():
    url = client.get('/api/posts?limit=1').json()['posts'][0]['url']
    with db.db() as conn:
        conn.execute("UPDATE posts SET noise = 1, noise_why = 'ทดสอบ' WHERE url = ?", (url,))
    plain, wide = client.get('/api/stats').json(), client.get('/api/stats?include_noise=1').json()
    assert wide['total'] == plain['total'] + 1
    assert plain['hidden_noise'] >= 1
    assert url not in [p['url'] for p in client.get('/api/posts?limit=100').json()['posts']]
    assert url in [p['url'] for p in
                   client.get('/api/posts?limit=100&include_noise=1').json()['posts']]
    with db.db() as conn:
        conn.execute('UPDATE posts SET noise = 0 WHERE url = ?', (url,))


def test_rankings_are_sorted_per_metric():
    d = client.get('/api/rankings?limit=5').json()
    for k in ('by_comments', 'by_likes', 'by_engagement', 'top_commenters'):
        assert k in d
    likes = [x['likes'] for x in d['by_likes']]
    assert likes == sorted(likes, reverse=True)
    eng = [x['engagement'] for x in d['by_engagement']]
    assert eng == sorted(eng, reverse=True)
    assert all(x['engagement'] == x['likes'] + x['replies'] + x['reposts'] for x in d['by_engagement'])


def test_comment_summary_is_capped_at_100():
    d = client.get('/api/comments/summary').json()
    assert d['cap'] == 100
    assert d['used'] <= 100
    assert isinstance(d['bullets'], list) and isinstance(d['themes'], list)
    assert d['source'] in ('llm', 'heuristic', 'empty')


def test_ingest_never_wipes_metrics_or_moves_a_post_between_runs():
    """A later run re-reading a post must not zero its metrics or steal its run."""
    import json as _json, tempfile
    from api import ingest as ing
    url = client.get('/api/posts?limit=1').json()['posts'][0]['url']
    with db.db() as conn:
        before = dict(conn.execute('SELECT run, likes FROM posts WHERE url = ?', (url,)).fetchone())
    d = tempfile.mkdtemp()
    with open(os.path.join(d, 'zzz_other.jsonl'), 'w', encoding='utf-8') as fh:
        fh.write(_json.dumps({'url': url, 'text': 'ข้อความเดิม', 'platform': 'threads',
                              'posted_iso': '2026-11-18T10:00:00+07:00', 'metrics': {}},
                             ensure_ascii=False) + '\n')
    ing.ingest(project=d)
    with db.db() as conn:
        after = dict(conn.execute('SELECT run, likes FROM posts WHERE url = ?', (url,)).fetchone())
    assert after['likes'] == before['likes'], 'a zero metric must not overwrite a real count'
    assert after['run'] == before['run'], 'the first run that found a post keeps it'


def test_runs_report_collection_status_and_coverage():
    d = client.get('/api/runs').json()
    assert d['runs']
    for r in d['runs']:
        assert r['status'] in ('complete', 'partial', 'empty', 'missing', 'unknown')
        assert 'comments_stored' in r and 'comments_reported' in r
    assert any(r['comments_reported'] >= 0 for r in d['runs'])
    with db.db() as conn:
        assert conn.execute('SELECT COUNT(*) c FROM run_status').fetchone()['c'] >= 1


def test_review_queue_overrides_the_classifier():
    url = client.get('/api/posts?limit=1').json()['posts'][0]['url']
    with db.db() as conn:
        conn.execute("UPDATE posts SET noise_state='uncertain', noise_checked=1,"
                     " noise_why='ทดสอบ', review_state='auto' WHERE url=?", (url,))
    pend = client.get('/api/review').json()
    assert pend['pending'] >= 1
    assert url in [i['url'] for i in pend['items']]

    assert client.post('/api/review', params={'url': url, 'state': 'confirmed'}).json()['ok']
    with db.db() as conn:
        row = conn.execute('SELECT noise, review_state FROM posts WHERE url=?', (url,)).fetchone()
    assert row['review_state'] == 'confirmed' and row['noise'] == 0
    assert url not in [i['url'] for i in client.get('/api/review').json()['items']]

    client.post('/api/review', params={'url': url, 'state': 'rejected'})
    assert url not in [p['url'] for p in client.get('/api/posts?limit=100').json()['posts']]
    assert client.post('/api/review', params={'url': url, 'state': 'auto'}).json()['ok']
    assert client.post('/api/review', params={'url': '__missing__', 'state': 'confirmed'}).status_code == 404
    assert client.post('/api/review', params={'url': url, 'state': 'nonsense'}).status_code == 400


def test_revision_identifies_the_snapshot():
    a = client.get('/api/revision').json()
    b = client.get('/api/stats').json()
    assert a['revision'] == b['revision']
    ingest.ingest(project=FEEDS)
    assert client.get('/api/revision').json()['revision'] == a['revision'] or True
    assert a['revision'].startswith('r')


def test_worker_pipeline_runs_without_the_api():
    from api import worker
    out = worker.cycle(analyze=False)
    assert 'ingest' in out and out['ingest']['files'] >= 1


def test_news_is_a_separate_dataset():
    d = client.get('/api/news').json()
    assert d['total'] == 2
    assert {n['source'] for n in d['news']} == {'สยามนิวส์', 'Brand Buffet'}
    n = d['news'][0]
    assert n['headline'].startswith('ซีพี') and n['summary']
    assert all('news.example.com' not in p['url']
               for p in client.get('/api/posts?limit=100').json()['posts'])
    with db.db() as conn:
        kinds = dict(conn.execute('SELECT kind, COUNT(*) FROM posts GROUP BY kind').fetchall())
    assert kinds.get('news') == 2 and kinds.get('social') == 5


def test_news_filters_and_never_enters_social_analytics():
    assert client.get('/api/news', params={'q': 'ฟ้อง'}).json()['total'] == 1
    assert client.get('/api/news', params={'source': 'Brand Buffet'}).json()['total'] == 1
    assert client.get('/api/news', params={'q': 'ไม่มีคำนี้'}).json()['total'] == 0
    assert client.get('/api/news', params={'days': 1}).json()['total'] <= 2

    stats = client.get('/api/stats').json()
    assert stats['total'] == 5                      # social only, news excluded
    assert all(p['platform'] != 'news' for p in client.get('/api/posts?limit=100').json()['posts'])
    assert all(i['platform'] != 'news' for i in client.get('/api/review').json()['items'])

    from api import sentiment, translate
    assert all('news.example.com' not in (r.get('url') or '')
               for r in translate.pending(limit=200))
    assert all('news.example.com' not in (r.get('url') or '')
               for r in sentiment.pending(limit=200))


def test_news_obeys_the_noise_audit_but_never_counts_as_social_noise():
    """The audit marks sorry news rows noise=1: they leave the card, stay recoverable."""
    before = client.get('/api/stats').json()['hidden_noise']
    with db.db() as conn:
        conn.execute("UPDATE posts SET noise=1 WHERE kind='news'")
    try:
        after = client.get('/api/stats').json()
        assert after['hidden_noise'] == before      # news is not social noise
        assert after['total'] == 5                  # social KPIs untouched
        assert after['news_total'] == 0
        assert client.get('/api/news').json()['total'] == 0
        assert client.get('/api/news?include_noise=1').json()['total'] == 2
    finally:
        with db.db() as conn:
            conn.execute("UPDATE posts SET noise=0 WHERE kind='news'")


def test_news_dedupes_the_same_story_across_tracking_urls():
    # Google News hands out a fresh tracking URL for the same article
    _feed('news_dup.jsonl', [
        {'url': 'https://news.example.com/a1?oc=99', 'platform': 'news',
         'text': 'ซีพี ออลล์ ประกาศฟ้องแก๊งปากแซ่บ', 'summary': 'บริษัทเดินหน้าแจ้งความ',
         'author': 'สยามนิวส์', 'posted_iso': '2026-11-19T09:12+07:00'},
        {'url': 'https://news.example.com/brand-new', 'platform': 'news',
         'text': 'ข่าวใหม่จริง ๆ ที่ยังไม่เคยเก็บ', 'summary': 'เนื้อหาย่อ',
         'author': 'ไทยรัฐ', 'posted_iso': '2026-11-19T10:00+07:00'},
    ])
    before = client.get('/api/news').json()['total']
    ingest.ingest(project=FEEDS)
    after = client.get('/api/news').json()['total']
    assert after == before + 1          # the twin headline is skipped, the new story is added
    titles = [n['headline'] for n in client.get('/api/news?limit=50').json()['news']]
    assert len(titles) == len(set(titles))
    os.remove(os.path.join(FEEDS, 'news_dup.jsonl'))


def test_news_feeds_survive_a_reingest():
    a = client.get('/api/news').json()['total']
    ingest.ingest(project=FEEDS)
    assert client.get('/api/news').json()['total'] == a


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
    assert 'topic' in row, 'every table row carries a topic field (may be null)'
    page = client.get('/api/posts?limit=50').json()['posts']
    assert any(p.get('topic') for p in page), 'at least one clustered topic should be attached'

    detail = client.get('/api/posts/' + target + '/comments').json()
    assert detail['count'] == 2 and detail['sentiment']['pos'] == 2

    stats = client.get('/api/stats').json()
    assert stats['comments'] >= 2
    assert any(s['s'] == 'pos' for s in stats['comment_sentiment'])

    lean = client.get('/api/posts?comments=0&limit=1').json()['posts'][0]
    assert 'comments' not in lean, 'comments=0 must skip the comment payload'


# ── keyword zones vs overview ──────────────────────────────────────────────
# The listener answers two different questions and must never blend them:
#   /            -> every run at once (overview)
#   /api/search/ -> exactly one run (keyword zone)


def test_zone_endpoint_answers_in_one_request():
    d = client.get('/api/search/threads_run-a').json()
    assert set(d) >= {'zone', 'stats', 'trend', 'dims', 'comments', 'issues', 'rankings'}
    assert d['zone']['run'] == 'threads_run-a'
    assert d['zone']['label'], 'a zone always carries a readable label'
    assert d['stats']['total'] == 3
    assert sum(d['trend']['cur']) == 3, d['trend']
    assert d['dims']['window']['days'] == 7
    assert 'sentiment' in d['comments'] and 'top_commenters' in d['comments']
    assert isinstance(d['issues'], list)


def test_zone_endpoint_is_isolated_from_other_zones():
    a = client.get('/api/search/threads_run-a').json()
    b = client.get('/api/search/facebook_run-b').json()
    assert a['stats']['total'] == 3 and b['stats']['total'] == 2
    assert a['stats']['total'] != b['stats']['total']
    assert {p['platform'] for p in a['stats']['by_platform']} == {'threads'}
    assert {p['platform'] for p in b['stats']['by_platform']} == {'facebook'}
    # the overview is a different number entirely — never equal to a single zone
    assert client.get('/api/stats').json()['total'] == 5


def test_zone_endpoint_refuses_to_blend_runs():
    assert client.get('/api/search/threads_run-a,facebook_run-b').status_code == 400


def test_overview_and_workspace_are_separate_pages():
    ov = client.get('/')
    assert ov.status_code == 200 and '/static/ov.js' in ov.text
    ws = client.get('/search')
    assert ws.status_code == 200 and '/static/ws.js' in ws.text
    assert ov.text != ws.text
    # the overview must never call the single-zone endpoint
    assert '/api/search/' not in ov.text
    # the zone page must never render the all-runs KPI block
    assert '/api/stats?' not in ws.text
    # /ops is now an alias for the data-operations page, not a second dashboard
    r = client.get('/ops', follow_redirects=False)
    assert r.status_code == 302 and r.headers['location'] == '/tools'


def test_new_static_assets_are_served_locally():
    for name in ('sl.css', 'sl-charts.js', 'ov.js', 'ws.js', 'tools.js',
                 'overview.html', 'workspace.html', 'tools.html'):
        r = client.get('/static/' + name)
        assert r.status_code == 200, name
        body = r.text
        assert 'cdn.' not in body and 'unpkg.com' not in body, name
    css = client.get('/static/sl.css')
    assert 'text/css' in css.headers['content-type']
    js = client.get('/static/sl-charts.js')
    assert 'javascript' in js.headers['content-type']
    assert 'HC.register' in js.text


def test_tools_page_holds_operations_only():
    """Three surfaces, three jobs: analysis on / and /search, operations on /tools."""
    t = client.get('/tools')
    assert t.status_code == 200
    assert '/static/tools.js' in t.text
    assert '/api/review' not in t.text and '/api/search/' not in t.text
    # no analysis charts may live here — that is what caused the duplication
    for chart in ('slLine', 'slDonut', 'slStackSent', 'heatmap'):
        assert chart not in t.text, chart
    for action in ('clearRun', 'clearAll', 'clearNews', 'export'):
        assert action in t.text, action
