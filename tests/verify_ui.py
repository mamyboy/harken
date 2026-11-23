#!/usr/bin/python3
"""Read-only Harken UI verification; only temporary Chrome tabs are created."""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import sys as _sys; _sys.path.insert(0, "/Users/mamyboy/.hermes/cache/scratch")
from pathlib import Path

import websocket

ROOT = Path('/Users/mamyboy/Projects/harken/api/static')
CDP = 'http://127.0.0.1:9333'
results = []


def check(name, ok, detail):
    results.append(bool(ok))
    detail = str(detail).replace('\n', ' ')
    print('{}  {}  {}'.format('PASS' if ok else 'FAIL', name, detail), flush=True)


def luminance(color):
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))


def contrast(fg, bg):
    lo, hi = sorted((luminance(fg), luminance(bg)))
    return (hi + .05) / (lo + .05)


def source_checks():
    css = (ROOT / 'sl.css').read_text()
    count = css.count('prefers-reduced-motion')
    check('source reduced-motion', count == 1, 'count={} expected=1'.format(count))
    check('source CSS small font', 'font-size:10.5px' not in css,
          'font-size:10.5px count={}'.format(css.count('font-size:10.5px')))
    count = css.count('var(--brand)')
    check('source brand references', count >= 2, 'count={} expected>=2'.format(count))
    for name, value in [('muted', '#5F6B85'), ('muted-2', '#5C6884'),
                        ('pos', '#12692F'), ('neu', '#8A5A00'), ('neg', '#C22A2E')]:
        token = '--{}:{}'.format(name, value)
        check('source token ' + name, token in css, token)
    balance = css.count('{') - css.count('}')
    check('source CSS brace balance', balance == 0, 'balance={}'.format(balance))
    presets = (ROOT / 'presets.html').read_text()
    count = presets.count('@keyframes pulse')
    check('source presets pulse', count == 0, 'count={}'.format(count))
    charts = (ROOT / 'sl-charts.js').read_text()
    # Inspect SVG text opening tags, not unrelated numeric geometry or swatches.
    tags = re.findall(r'<text\b[^>]*>', charts, re.S)
    small = [t for t in tags if re.search(r'font-size\s*[=:]\s*[\\\'\"]*10\.5\b', t)]
    pale = [t for t in tags if re.search(r'fill\s*[=:][^>]*#8C99B4', t, re.I)]
    check('source chart axis font', not small, '10.5 text font tags={}'.format(len(small)))
    check('source chart text fill', not pale, '#8C99B4 text fill tags={}'.format(len(pale)))


def http(path, method='GET'):
    request = urllib.request.Request(CDP + path, method=method)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode()


class Protocol:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=15, suppress_origin=True)
        self.seq = 0

    def call(self, method, params=None):
        self.seq += 1
        ident = self.seq
        self.ws.send(json.dumps({'id': ident, 'method': method, 'params': params or {}}))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get('id') == ident:
                if 'error' in reply:
                    raise RuntimeError(reply['error'])
                return reply.get('result', {})

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True})
        if 'exceptionDetails' in result:
            raise RuntimeError(result['exceptionDetails'])
        return result['result'].get('value')


EXTRACT = r'''(() => {
 const visible = el => {
   const r = el.getBoundingClientRect(), s = getComputedStyle(el);
   return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' &&
     s.visibility !== 'collapse' && el.getClientRects().length > 0;
 };
 const buttons = [...document.querySelectorAll('.btn,.navlink')].filter(visible);
 return {
   width: document.documentElement.scrollWidth, inner: window.innerWidth,
   objectText: document.body.innerText.includes('[object'),
   count: buttons.length,
   short: buttons.filter(el => el.getBoundingClientRect().height < 36).map(el => ({
     text: el.innerText.trim().slice(0,70), height: el.getBoundingClientRect().height
   })),
   axes: [...document.querySelectorAll('svg text')].slice(0,3).map(el => ({
     text: el.textContent, fill: getComputedStyle(el).fill,
     fontSize: getComputedStyle(el).fontSize
   }))
 };
})()'''


def rendered(route, width, height, mobile):
    label = '{} {}x{}'.format(route, width, height)
    tab = None
    protocol = None
    try:
        tab = json.loads(http('/json/new?' + urllib.parse.quote('about:blank', safe=''), 'PUT'))
        protocol = Protocol(tab['webSocketDebuggerUrl'])
        protocol.call('Emulation.setDeviceMetricsOverride', {
            'width': width, 'height': height, 'mobile': mobile,
            'deviceScaleFactor': 3 if mobile else 1})
        protocol.call('Network.setCacheDisabled', {'cacheDisabled': True})
        protocol.call('Page.navigate', {'url': 'http://localhost:8000' + route})
        deadline = time.monotonic() + 20
        while protocol.evaluate('(() => document.readyState)()') != 'complete':
            if time.monotonic() > deadline:
                raise TimeoutError('document did not finish loading')
            time.sleep(.2)
        time.sleep(3)
        data = protocol.evaluate(EXTRACT)
        check(label + ' overflow', data['width'] <= data['inner'] + 1,
              'scrollWidth={} innerWidth={}'.format(data['width'], data['inner']))
        check(label + ' object text', not data['objectText'], '[object found={}'.format(data['objectText']))
        check(label + ' controls', data['count'] > 0 and not data['short'],
              'visible={} heights<36={}'.format(data['count'], json.dumps(data['short'], ensure_ascii=False)))
        if route == '/':
            check(label + ' SVG text report', len(data['axes']) == 3,
                  json.dumps(data['axes'], ensure_ascii=False))
    except Exception as exc:
        check(label + ' CDP', False, '{}: {}'.format(type(exc).__name__, exc))
    finally:
        if protocol:
            protocol.ws.close()
        if tab:
            try:
                http('/json/close/' + tab['id'])
            except Exception as exc:
                check(label + ' close tab', False, str(exc))


def main():
    pairs = [('#5F6B85', bg) for bg in ('#E4ECFF', '#FFFFFF', '#F2EBFF')]
    pairs += [('#5C6884', bg) for bg in ('#E4ECFF', '#FFFFFF')]
    pairs += [('#12692F', '#E9F8EF'), ('#8A5A00', '#FFF4E2'), ('#C22A2E', '#FFECEC')]
    for fg, bg in pairs:
        ratio = contrast(fg, bg)
        check('contrast {} on {}'.format(fg, bg), ratio >= 4.5, '{:.4f}:1 expected>=4.5:1'.format(ratio))
    for fg, bg in [('#6B7A99', '#E4ECFF'), ('#8C99B4', '#E4ECFF'),
                   ('#16A34A', '#E9F8EF'), ('#D98A18', '#FFF4E2'), ('#E5484D', '#FFECEC')]:
        check('before {} on {}'.format(fg, bg), True,
              '{:.4f}:1 (informational baseline, not a new-token assertion)'.format(contrast(fg, bg)))
    try:
        source_checks()
    except Exception as exc:
        check('source read', False, str(exc))
    for route in ('/', '/presets'):
        for width, height, mobile in ((1280, 800, False), (390, 844, True)):
            rendered(route, width, height, mobile)
    passed = sum(results)
    failed = len(results) - passed
    print('{} passed, {} failed'.format(passed, failed))
    return int(failed > 0)


if __name__ == '__main__':
    sys.exit(main())
