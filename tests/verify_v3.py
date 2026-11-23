#!/usr/bin/python3
"""Rendered Harken v3 checks; no app writes, temporary theme state restored."""
import json
import re
import sys
import time
import urllib.parse
import urllib.request

from html.parser import HTMLParser
from pathlib import Path
import websocket

ROOT = Path('/Users/mamyboy/Projects/harken/api/static')
BASE, CDP = 'http://localhost:8000', 'http://127.0.0.1:9333'
RESULTS = []
ROUTES = [('overview.html', '/'), ('presets.html', '/presets'),
          ('tools.html', '/tools'), ('workspace.html', '/search')]


def check(name, ok, detail):
    detail = str(detail).replace('\n', ' ')
    RESULTS.append((name, bool(ok), detail))
    print(('PASS' if ok else 'FAIL') + '  ' + name + '  ' + detail, flush=True)


class NavParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.current = [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and 'navlink' in a.get('class', '').split():
            self.current = {'href': a.get('href'), 'svg': False, 'span': False}
            self.links.append(self.current)
        if self.current is not None:
            if tag == 'svg' and 'ni' in a.get('class', '').split():
                self.current['svg'] = True
            if tag == 'span' and 'nl' in a.get('class', '').split():
                self.current['span'] = True

    def handle_endtag(self, tag):
        if tag == 'a':
            self.current = None


def http(path, method='GET'):
    with urllib.request.urlopen(urllib.request.Request(CDP + path, method=method), timeout=15) as r:
        return r.read().decode()


class Browser:
    def __init__(self, tab):
        self.ws = websocket.create_connection(tab['webSocketDebuggerUrl'], timeout=20, suppress_origin=True)
        self.seq = 0

    def call(self, method, params=None):
        self.seq += 1
        self.ws.send(json.dumps(dict(id=self.seq, method=method, params=params or {})))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == self.seq:
                if 'error' in msg:
                    raise RuntimeError(msg['error'])
                return msg.get('result', {})

    def js(self, body):
        r = self.call('Runtime.evaluate', dict(expression='(() => {' + body + '})()', returnByValue=True))
        if 'exceptionDetails' in r:
            raise RuntimeError(r['exceptionDetails'])
        return r['result'].get('value')

    def size(self, w, h):
        self.call('Emulation.setDeviceMetricsOverride', dict(width=w, height=h, deviceScaleFactor=1, mobile=w < 500))

    def navigate(self, route):
        self.call('Page.navigate', {'url': BASE + route})
        end = time.monotonic() + 20
        while time.monotonic() < end:
            if self.js('return location.pathname === ' + json.dumps(urllib.parse.urlparse(route).path) + ' && document.readyState === "complete";'):
                time.sleep(1.5)
                return
            time.sleep(.1)
        raise TimeoutError('page load: ' + route)


VISIBLE = '''const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);
return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.visibility!=='collapse';};'''
STATE = '''const b=document.querySelector('#themeBtn');return {theme:document.documentElement.dataset.theme,
tag:b&&b.tagName,pressed:b&&b.getAttribute('aria-pressed'),stored:localStorage.getItem('harken-theme')};'''
COLOR = '''const row=[...document.querySelectorAll('.sl-donut-legend [data-platform]')].find(
e=>['x','twitter'].includes(e.dataset.platform.toLowerCase()));
const sw=row&&row.querySelector('i,.sl-swatch');
const arc=[...document.querySelectorAll('.sl-donut-svg [data-platform]')].find(
e=>['x','twitter'].includes(e.dataset.platform.toLowerCase()));
return {legend:sw?getComputedStyle(sw).backgroundColor:null,
slice:arc?getComputedStyle(arc)[arc.tagName.toLowerCase()==='circle'?'stroke':'fill']:null};'''


def rgb(s):
    values = [float(n) for n in re.findall(r'[\d.]+', s)]
    if not s.startswith('rgb') or len(values) not in (3, 4):
        raise ValueError('Expected computed RGB(A), got ' + repr(s))
    return values[:3] + [values[3] if len(values) == 4 else 1]


def luminance(channels):
    v = [x / 255 for x in channels[:3]]
    return sum((x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4) * w
               for x, w in zip(v, (.2126, .7152, .0722)))


def contrast(pair):
    backgrounds = [(255., 255., 255.)]
    for solid, image in reversed(pair['layers']):
        # Composite every computed gradient stop; use the worst endpoint, never white by assumption.
        paints = [[solid]] + [re.findall(r'rgba?\([^)]*\)', g) for g in
                  reversed(re.split(r'(?<=\)),\s*(?=[\w-]+gradient\()', image)) if g != 'none']
        for choices in paints:
            if not choices:
                raise ValueError('Unsupported computed background: ' + image)
            backgrounds = list({tuple(c[i]*c[3]+bg[i]*(1-c[3]) for i in range(3))
                                for bg in backgrounds for c in map(rgb, choices)})
    c, ratios = rgb(pair['fg']), []
    for bg in backgrounds:
        fg = [c[i]*c[3]+bg[i]*(1-c[3]) for i in range(3)]
        lo, hi = sorted([luminance(fg), luminance(bg)])
        ratios.append((hi+.05)/(lo+.05))
    return min(ratios)


def exercise(b):
    b.size(1280, 800)
    for filename, route in ROUTES:
        b.navigate(route)
        d = b.js(VISIBLE + '''const links=[...document.querySelectorAll('.navlink')].filter(visible);
return {count:links.length,bad:links.filter(e=>{const s=e.querySelector('svg');
return !s||!visible(s);}).map(e=>e.outerHTML)};''')
        check('A rendered ' + route, d['count'] > 0 and not d['bad'], d)
    b.navigate('/')
    original = b.js(STATE)
    check('B button', original['tag'] == 'BUTTON' and original['pressed'] in ('true', 'false'), original)
    check('B initial theme', original.get('theme') in ('light', 'dark'), original)
    b.js("document.querySelector('#themeBtn')?.click();")
    time.sleep(.4)
    flipped = b.js(STATE)
    expected = 'dark' if original.get('theme') == 'light' else 'light'
    check('B click flips theme/aria/storage', flipped.get('theme') == expected and
          flipped['pressed'] in ('true', 'false') and flipped['pressed'] != original['pressed'] and
          flipped['stored'] == expected, {'before': original, 'after': flipped})
    b.navigate('/')
    persisted = b.js(STATE)
    check('B full navigation persistence', persisted.get('theme') == expected and
          persisted['pressed'] == flipped['pressed'] and persisted['stored'] == expected, persisted)
    b.js("document.querySelector('#themeBtn')?.click();")
    returned = b.js(STATE)
    check('B second click restores', returned.get('theme') == original.get('theme') and
          returned['pressed'] == original['pressed'] and returned['stored'] == original.get('theme'), returned)
    colors = {}
    for theme in ('light', 'dark'):
        # Persist the requested mode then navigate: exercises chart startup with real theme state.
        b.js('localStorage.setItem("harken-theme",' + json.dumps(theme) + ');')
        b.navigate('/')
        check('theme setup ' + theme, b.js(STATE).get('theme') == theme, b.js(STATE))
        colors[theme] = b.js(COLOR)
        if theme == 'dark':
            b.js("document.documentElement.dataset.theme='dark';")
            time.sleep(.3)
            pairs = b.js('''const layers=e=>{const a=[];for(;e;e=e.parentElement)
a.push([getComputedStyle(e).backgroundColor,getComputedStyle(e).backgroundImage]);return a;};
return [['body',document.body],...Array.from(document.querySelectorAll('.kpi .k,.navlink'))
.map((e,i)=>[e.matches('.navlink')?'nav '+i:'kpi '+i,e])].map(([name,e])=>
({name,fg:getComputedStyle(e).color,layers:layers(e)}));''')
            check('C required samples', any(p['name'].startswith('nav') for p in pairs) and
                  any(p['name'].startswith('kpi') for p in pairs), 'samples=' + str(len(pairs)))
            for p in pairs:
                ratio = contrast(p)
                check('C dark ' + p['name'], ratio >= 4.5, '{:.4f}:1 {}'.format(ratio, p))
        b.size(390, 844)
        for _, route in ROUTES:
            b.navigate(route)
            d = b.js(VISIBLE + '''const a=[...document.querySelectorAll('.btn,.navlink,#themeBtn')].filter(visible);
return {theme:document.documentElement.dataset.theme,w:document.documentElement.scrollWidth,inner:innerWidth,
object:document.body.innerText.includes('[object'),count:a.length,short:a.filter(e=>e.getBoundingClientRect().height<34)
.map(e=>({text:e.innerText.slice(0,50),id:e.id,height:e.getBoundingClientRect().height}))};''')
            label = 'D ' + theme + ' ' + route
            check(label + ' theme', d['theme'] == theme, 'rendered=' + str(d['theme']))
            check(label + ' overflow', d['theme'] == theme and d['w'] <= d['inner'] + 1, d)
            check(label + ' object text', not d['object'], 'contains [object=' + str(d['object']))
            check(label + ' controls', d['count'] > 0 and not d['short'], d)
        b.size(1280, 800)
    check('F X chart changes', all(colors[t]['legend'] or colors[t]['slice'] for t in colors) and
          colors['light'] != colors['dark'], colors)
    dark = colors['dark']['legend'] or colors['dark']['slice']
    check('F X dark not near-black', bool(dark) and luminance(rgb(dark)) >= .1,
          {'color': dark, 'minimum_relative_luminance': .1})
    b.navigate('/presets')
    d = b.js('''const h=document.querySelector('header.pagehero'),s=document.querySelector('.shell');
const c=s&&getComputedStyle(s);return {exists:!!h,width:h&&h.getBoundingClientRect().width,
column:s&&s.clientWidth-parseFloat(c.paddingLeft)-parseFloat(c.paddingRight),
background:h&&getComputedStyle(h).backgroundImage};''')
    check('E hero exists', d['exists'], d)
    check('E hero full column', d['exists'] and abs(d['width']-d['column']) <= 2, d)
    check('E hero gradient', d['exists'] and 'gradient(' in d['background'], d)


def main():
    for filename, _ in ROUTES:
        try:
            p = NavParser()
            p.feed((ROOT / filename).read_text())
            bad = [a for a in p.links if not a['svg'] or not a['span']]
            check('A source ' + filename, bool(p.links) and not bad, {'count': len(p.links), 'bad': bad})
        except Exception as e:
            check('A source ' + filename, False, repr(e))
    tab = b = saved = None
    try:
        tab = json.loads(http('/json/new?about:blank', 'PUT'))
        b = Browser(tab)
        b.call('Network.setCacheDisabled', {'cacheDisabled': True})
        b.navigate('/')
        saved = b.js('return {stored:localStorage.getItem("harken-theme"),theme:document.documentElement.dataset.theme};')
        exercise(b)
    except Exception as e:
        check('browser execution', False, repr(e))
    finally:
        if b:
            try:
                if saved is not None:
                    b.js('const s=' + json.dumps(saved) + ';if(s.stored===null)localStorage.removeItem("harken-theme");else localStorage.setItem("harken-theme",s.stored);')
            except Exception as e:
                check('restore theme storage', False, repr(e))
            b.ws.close()
        if tab:
            try:
                http('/json/close/' + tab['id'])
            except Exception as e:
                check('close temporary tab', False, repr(e))
    failures = [(n, d) for n, ok, d in RESULTS if not ok]
    if failures:
        print('\nFAILURE TABLE\nCheck | Detail')
        for n, d in failures:
            print(n + ' | ' + d)
    print('\n{} passed, {} failed'.format(len(RESULTS)-len(failures), len(failures)))
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
