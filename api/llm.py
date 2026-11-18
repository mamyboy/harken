"""Thin client for the local OpenCode server (beam-free)."""
import base64
import json
import os
import time
import urllib.error
import urllib.request

SERVICE = os.path.expanduser('~/.local/state/opencode/service.json')
MODEL = {'id': 'beam-free', 'providerID': 'opencode-go'}


def _service():
    with open(SERVICE, encoding='utf-8') as f:
        svc = json.load(f)
    return svc['url'], 'Basic ' + base64.b64encode(('opencode:' + svc['password']).encode()).decode()


def _call(method, path, payload=None, timeout=240, tries=4):
    last = None
    for attempt in range(tries):
        url, auth = _service()
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json', 'Authorization': auth})
        try:
            return 200, json.load(urllib.request.urlopen(req, timeout=timeout))
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:300]
        except Exception as e:
            last = '%s: %s' % (type(e).__name__, e)
            if attempt < tries - 1:
                time.sleep(4 + 4 * attempt)
    return -1, last


def new_session(title='harken-api'):
    st, r = _call('POST', '/api/session', {'title': title, 'model': MODEL})
    if st != 200:
        raise RuntimeError('session create failed: %s %s' % (st, r))
    return r['data']['id']


def generate(session_id, prompt, timeout=300):
    st, r = _call('POST', '/api/session/%s/generate' % session_id, {'prompt': prompt}, timeout=timeout)
    if st != 200:
        raise RuntimeError('generate failed: %s %s' % (st, r))
    return r['data']['text']


def json_array(text):
    """Pull the first JSON array out of a model reply (tolerates ``` fences)."""
    t = (text or '').strip()
    if t.startswith('```'):
        t = t.split('\n', 1)[-1]
        if t.rstrip().endswith('```'):
            t = t.rstrip()[:-3]
    start, end = t.find('['), t.rfind(']')
    if start < 0 or end < 0:
        raise ValueError('no JSON array in reply')
    return json.loads(t[start:end + 1])
