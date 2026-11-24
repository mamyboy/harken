#!/usr/bin/env python3
"""Route hygiene: every address in the nav must show its own data.

Two failure modes this guards against:

1. A legacy address that stopped redirecting and now renders a copy of another
   page -- the nav then offers two doors to one room, and a reader has no way to
   tell which is current.
2. Two live surfaces that drift into showing the same blocks. The overview, the
   zone page and the operations page are allowed to share a shell (nav, app bar)
   but not their payload.

Redirects are checked without following them, because a followed redirect is
indistinguishable from a page that duplicates its target.
"""
import http.client
import itertools
import json
import sys
import time
import urllib.request

import websocket

BASE = '127.0.0.1:8000'
LEGACY = {'/vibrant': '/', '/workspace': '/search', '/ops': '/tools'}
LIVE = ['/', '/search', '/tools']
MAX_OVERLAP = 0.60        # shell + nav is ~13%; anything near 100% is a copy

FAILS = []
CHECKS = [0]


def check(name, ok, detail=None):
    CHECKS[0] += 1
    print(('PASS  ' if ok else 'FAIL  ') + name +
          ('  ' + json.dumps(detail, ensure_ascii=False) if detail is not None else ''))
    if not ok:
        FAILS.append((name, detail))


class Tab:
    def __init__(self):
        self.t = json.load(urllib.request.urlopen(
            urllib.request.Request('http://127.0.0.1:9333/json/new?about:blank', method='PUT')))
        self.ws = websocket.create_connection(self.t['webSocketDebuggerUrl'], timeout=40)
        self.i = 0

    def call(self, m, **p):
        self.i += 1
        n = self.i
        self.ws.send(json.dumps({'id': n, 'method': m, 'params': p}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get('id') == n:
                return r.get('result', {})

    def js(self, expr):
        r = self.call('Runtime.evaluate', expression=expr, returnByValue=True)['result']
        if r.get('subtype') == 'error':
            raise RuntimeError(r.get('description'))
        return r.get('value')

    def blocks(self, path):
        self.call('Emulation.setDeviceMetricsOverride', width=1440, height=1200,
                  deviceScaleFactor=1, mobile=False)
        self.call('Page.navigate', url='http://localhost:8000' + path)
        time.sleep(5)
        self.call('Runtime.evaluate', expression="window.scrollTo(0,document.body.scrollHeight)")
        time.sleep(1.5)
        raw = self.js(r"""
        (() => {
          const norm = s => (s||'').replace(/\s+/g,' ').trim();
          const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
                             return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
          const out = new Set();
          const walk = e => {
            if (!vis(e)) return;
            const kids = [...e.children];
            if (!kids.length) { const t = norm(e.textContent); if (t.length > 1) out.add(t); return; }
            kids.forEach(walk);
          };
          walk(document.body);
          return JSON.stringify([...out]);
        })()
        """)
        return set(json.loads(raw)), self.js('location.pathname')

    def close(self):
        try:
            urllib.request.urlopen('http://127.0.0.1:9333/json/close/' + self.t['id'])
        except Exception:
            pass


def head(path):
    conn = http.client.HTTPConnection(BASE.split(':')[0], int(BASE.split(':')[1]), timeout=10)
    conn.request('GET', path)
    r = conn.getresponse()
    loc = r.getheader('Location') or ''
    conn.close()
    return r.status, loc


def main():
    # 1. legacy addresses are permanent redirects to the surface that owns the data
    for old, new in LEGACY.items():
        status, loc = head(old)
        check(f'{old} redirects permanently to {new}',
              status == 308 and loc.rstrip('/').endswith(new.rstrip('/')),
              {'status': status, 'location': loc})

    # 2. no live surface repeats another one's payload
    tab = Tab()
    seen = {}
    try:
        for path in LIVE:
            blocks, landed = tab.blocks(path)
            check(f'{path} lands on {path}', landed == path, {'landed': landed})
            seen[path] = blocks
        for a, b in itertools.combinations(LIVE, 2):
            inter = len(seen[a] & seen[b])
            union = max(1, len(seen[a] | seen[b]))
            ratio = inter / union
            check(f'{a} and {b} do not share their payload',
                  ratio < MAX_OVERLAP,
                  {'shared': inter, 'union': union, 'ratio': round(ratio, 3),
                   'limit': MAX_OVERLAP})
    finally:
        tab.close()

    print(f'{CHECKS[0] - len(FAILS)} passed, {len(FAILS)} failed')
    return 0 if not FAILS else 1


if __name__ == '__main__':
    sys.exit(main())
