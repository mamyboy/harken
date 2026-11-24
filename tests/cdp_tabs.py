"""One CDP tab for the whole run.

Every check used to spawn its own tab via /json/new: a five-suite pass plus
screenshots meant dozens of tabs, and Chrome eventually answered with
"Connection reset by peer". Reuse one localhost:8000 tab instead, and position
the cursor inside it rather than opening a new one.
"""
import json, urllib.parse, urllib.request

BASE = 'http://127.0.0.1:9222'
LOCAL = 'http://localhost:8000'


def _req(path, method='GET'):
    r = urllib.request.Request(BASE + path, method=method)
    with urllib.request.urlopen(r, timeout=15) as f:
        raw = f.read()
    return json.loads(raw) if raw else {}


def _pages():
    return [t for t in _req('/json/list') if t.get('type') == 'page']


def reusable(prefix=LOCAL):
    """Attach to an existing tab on the app, or create the only one we need."""
    for t in _pages():
        if t.get('url', '').startswith(prefix):
            return t
    return _req('/json/new?' + urllib.parse.quote(LOCAL + '/', safe=''), 'PUT')


def sweep(keep=('localhost:8000',)):
    """Close our own leftovers; never touch the operator's real tabs."""
    closed = 0
    for t in _pages():
        u = t.get('url', '')
        if any(k in u for k in keep) and not u.startswith(LOCAL):
            try:
                _req('/json/close/' + t['id']); closed += 1
            except Exception:
                pass
    return closed


def extras():
    """Tabs that are ours but idle — the inverse of what the operator browses."""
    return [t for t in _pages() if t.get('url', '').startswith('about:')]
