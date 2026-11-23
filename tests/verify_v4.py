#!/usr/bin/python3
"""Harken appbar acceptance checks. Temporary tabs/storage are restored in finally."""
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from pathlib import Path
import websocket

BASE, CDP = 'http://localhost:8000', 'http://127.0.0.1:9333'
RESULTS = []
ROUTES = ('/', '/presets', '/tools', '/search')


def check(name, ok, detail):
    detail = str(detail).replace('\n', ' ')
    RESULTS.append((name, bool(ok), detail))
    print(('PASS' if ok else 'FAIL') + '  ' + name + '  ' + detail, flush=True)


def http(path, method='GET'):
    with urllib.request.urlopen(urllib.request.Request(CDP + path, method=method), timeout=15) as r:
        return r.read().decode()


class Browser:
    def __init__(self, tab):
        self.ws = websocket.create_connection(tab['webSocketDebuggerUrl'], timeout=20, suppress_origin=True)
        self.seq, self.events = 0, []
        for domain in ('Page', 'Runtime', 'Network'):
            self.call(domain + '.enable')
        self.call('Network.setCacheDisabled', {'cacheDisabled': True})

    def call(self, method, params=None):
        self.seq += 1
        self.ws.send(json.dumps(dict(id=self.seq, method=method, params=params or {})))
        while True:
            msg = json.loads(self.ws.recv())
            if 'method' in msg:
                self.events.append(msg)
            if msg.get('id') == self.seq:
                if 'error' in msg:
                    raise RuntimeError(msg['error'])
                return msg.get('result', {})

    def js(self, body, await_promise=False):
        r = self.call('Runtime.evaluate', dict(expression='(' + ('async ' if await_promise else '') +
                      '() => {' + body + '})()', returnByValue=True, awaitPromise=await_promise))
        if 'exceptionDetails' in r:
            raise RuntimeError(r['exceptionDetails'])
        return r['result'].get('value')

    def wait(self, condition, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                if self.js('return ' + condition + ';'):
                    return
            except RuntimeError:
                pass  # A navigation can replace the execution context between evaluations.
            time.sleep(.1)
        raise TimeoutError(condition)

    def navigate(self, route):
        result = self.call('Page.navigate', {'url': BASE + route})
        if result.get('errorText'):
            raise RuntimeError(result['errorText'])
        self.wait('location.pathname === ' + json.dumps(route) + ' && document.readyState === "complete"')
        time.sleep(1)

    def size(self, w, h):
        self.call('Emulation.setDeviceMetricsOverride', dict(width=w, height=h, deviceScaleFactor=1, mobile=w < 500))


def guarded(name, fn):
    try:
        fn()
    except Exception as exc:
        check(name, False, repr(exc))


def rgb(text):
    v = [float(n) for n in re.findall(r'[\d.]+', text)]
    if not text.startswith('rgb') or len(v) not in (3, 4):
        raise ValueError('Unsupported color: ' + text)
    return v[:3] + [v[3] if len(v) == 4 else 1]


def luminance(c):
    v = [x / 255 for x in c[:3]]
    return sum((x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4) * w
               for x, w in zip(v, (.2126, .7152, .0722)))


def contrast(pair):
    grounds = [(255., 255., 255.)]
    for solid, image in reversed(pair['layers']):
        paints = [[solid]] + [re.findall(r'rgba?\([^)]*\)', g) for g in
                  reversed(re.split(r'(?<=\)),\s*(?=[\w-]+gradient\()', image)) if g != 'none']
        for colors in paints:
            if not colors:
                raise ValueError('Unsupported background: ' + image)
            grounds = list({tuple(c[i]*c[3]+bg[i]*(1-c[3]) for i in range(3))
                            for bg in grounds for c in map(rgb, colors)})
    c, ratios = rgb(pair['fg']), []
    for bg in grounds:
        fg = [c[i]*c[3]+bg[i]*(1-c[3]) for i in range(3)]
        lo, hi = sorted((luminance(fg), luminance(bg)))
        ratios.append((hi + .05) / (lo + .05))
    return min(ratios)


def present(b, route):
    b.navigate(route)
    d = b.js('''const a=document.querySelector('#appbar');return {exists:!!a,
first:!!a&&document.querySelector('.shell')?.firstElementChild===a,
missing:['.crumbs a.cr','#qkw','.qs-go','#abMeta'].filter(s=>!a?.querySelector(s)),
position:a&&getComputedStyle(a).position};''')
    check('A appbar ' + route, d['exists'] and d['first'] and not d['missing'] and d['position'] == 'sticky', d)


def sticky(b):
    b.navigate('/')
    before = b.js("scrollTo(0,0);return document.querySelector('#appbar').getBoundingClientRect().top;")
    b.js('scrollTo(0,600);')
    time.sleep(.25)
    d = b.js('''const a=document.querySelector('#appbar');return {top:a.getBoundingClientRect().top,
offset:parseFloat(getComputedStyle(a).top),stuck:a.classList.contains('is-stuck'),scroll:scrollY};''')
    check('B sticky pinned', d['scroll'] > 0 and abs(d['top']-d['offset']) <= 2 and d['stuck'], {'before': before, 'after': d})
    b.js('''window.__cls=0;window.__shifts=[];window.__po=new PerformanceObserver(list=>{
for(const e of list.getEntries()){window.__cls+=e.value;window.__shifts.push({value:e.value,recentInput:e.hadRecentInput});}});
window.__po.observe({type:'layout-shift',buffered:false});scrollTo(0,0);''')
    time.sleep(.4)
    d = b.js('window.__po.disconnect();return {cls:window.__cls,shifts:window.__shifts};')
    check('B scroll CLS', d['cls'] < .05, d)


def shortcut(b):
    b.js('document.activeElement?.blur();')
    for kind in ('keyDown', 'keyUp'):
        b.call('Input.dispatchKeyEvent', dict(type=kind, modifiers=4, metaKey=True,
                                            key='k', code='KeyK', windowsVirtualKeyCode=75))
    d = b.js('return document.activeElement.id;')
    check('C real Command-K focus', d == 'qkw', 'activeElement.id=' + str(d))


def search(b):
    b.js('''const q=document.querySelector('#qkw');q.value='สตูล';const f=q.form;
if(f.requestSubmit)f.requestSubmit();else f.submit();''')
    b.wait('location.pathname === "/presets" && document.readyState === "complete"')
    time.sleep(.5)
    d = b.js('return {path:location.pathname,search:location.search,kw:document.querySelector("#kw")?.value};')
    encoded = urllib.parse.quote('สตูล')
    check('D quick search round trip', d['path'] == '/presets' and encoded.lower() in d['search'].lower()
          and d.get('kw') == 'สตูล', d)
    b.js('history.back();')
    b.wait('location.pathname === "/" && document.readyState === "complete"')
    time.sleep(.5)


def meta(b):
    try:
        b.wait('/อัปเดต \\d{1,2}:\\d{2}/.test(document.querySelector("#abMeta")?.textContent || "")', 8)
    except TimeoutError:
        check('E live meta ready', False, b.js('return {text:document.querySelector("#abMeta")?.textContent,refresh:typeof window.HarkenAppbar?.refresh};'))
    read = '''return {text:document.querySelector('#abMeta')?.textContent,
live:document.querySelector('#abLive')?.classList.contains('is-live')};'''
    for label in ('initial', 'refresh'):
        if label == 'refresh':
            b.js('await window.HarkenAppbar.refresh();return true;', True)
        d = b.js(read)
        check('E live meta ' + label, bool(re.search(r'อัปเดต \d{1,2}:\d{2}', d.get('text') or ''))
              and '0 โพสต์' not in (d.get('text') or '') and d.get('live'), d)


def motion(b):
    for reduced in (True, False):
        b.call('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce'}] if reduced else []})
        b.navigate('/')
        d = b.js('''const style=s=>getComputedStyle(document.querySelector(s));return {
kpi:style('.kpis .kpi').animationName,card:style('.card').animationName,
lead:style('.kpi.lead').transitionDuration};''')
        ok = d['kpi'] == 'none' and d['card'] == 'none' and d['lead'] == '0s' if reduced else d['kpi'] != 'none' and d['card'] != 'none'
        check('F motion ' + ('reduced' if reduced else 'normal'), ok, d)


def themed(b, theme):
    b.size(1280, 800)
    b.js('localStorage.setItem("harken-theme",' + json.dumps(theme) + ');')
    b.navigate('/')
    pairs = b.js('''return ['.crumbs a.cr','#abMeta','#qkw'].map(selector=>{
const e=document.querySelector(selector),layers=[];let s=getComputedStyle(e),fallback=false;
if(selector==='#qkw'){const p=getComputedStyle(e,'::placeholder');if(p?.color&&p.color!=='')s=p;else fallback=true;}
for(let n=e;n;n=n.parentElement){const c=getComputedStyle(n);layers.push([c.backgroundColor,c.backgroundImage]);}
return {selector,fg:s.color,layers,fallback};});''')
    for p in pairs:
        check('G contrast ' + theme + ' ' + p['selector'], contrast(p) >= 4.5,
              '{:.4f}:1 {}; placeholder fallback={}'.format(contrast(p), p, p['fallback']))
    b.size(390, 844)
    for route in ROUTES:
        b.navigate(route)
        d = b.js('''const a=document.querySelector('#appbar');const boxes=[...document.querySelectorAll('.navlink,.qs-go,#themeBtn')]
.map(e=>{const r=e.getBoundingClientRect();return {name:e.id||e.className,w:r.width,h:r.height};});return {
theme:document.documentElement.dataset.theme,width:document.documentElement.scrollWidth,inner:innerWidth,
height:a?.getBoundingClientRect().height,boxes,bad:boxes.filter(r=>r.w<28||r.h<28)};''')
        prefix = 'H mobile ' + theme + ' ' + route
        check(prefix + ' overflow', d.get('theme') == theme and d['width'] <= d['inner'] + 1, d)
        check(prefix + ' appbar height', d.get('height') is not None and 44 <= d['height'] <= 60, d)
        check(prefix + ' hit targets', bool(d['boxes']) and not d['bad'], d)


def regressions():
    for name in ('verify_v3.py', 'verify_ui.py'):
        r = subprocess.run(['/usr/bin/python3', str(Path(__file__).with_name(name))], capture_output=True, text=True, timeout=240)
        summaries = re.findall(r'\d+ passed, \d+ failed', r.stdout)
        failures = [s for s in r.stdout.splitlines() if s.startswith('FAIL')]
        check('H regression ' + name, r.returncode == 0 and bool(summaries) and summaries[-1].endswith(', 0 failed'),
              {'summary': summaries[-1] if summaries else 'missing', 'exit': r.returncode, 'failures': failures, 'stderr': r.stderr[-1000:]})


def main():
    tab = b = saved = None
    try:
        tab = json.loads(http('/json/new?about:blank', 'PUT'))
        b = Browser(tab)
        b.navigate('/')
        saved = b.js('return Object.fromEntries(Object.keys(localStorage).map(k=>[k,localStorage.getItem(k)]));')
        b.size(1280, 800)
        for route in ROUTES:
            guarded('A appbar ' + route, lambda route=route: present(b, route))
        for name, fn in [('B sticky', sticky), ('C shortcut', shortcut), ('D search', search), ('E meta', meta), ('F motion', motion)]:
            guarded(name, lambda fn=fn: fn(b))
        for theme in ('light', 'dark'):
            guarded('G/H ' + theme, lambda theme=theme: themed(b, theme))
        b.js('return true;')  # Drain queued Runtime events.
        errors = [e['params'] for e in b.events if e['method'] == 'Runtime.consoleAPICalled'
                  and e['params'].get('type') == 'error' and 'appbar.js' in json.dumps(e['params'])]
        check('E appbar console errors', not errors, errors)
        guarded('H regression subprocesses', regressions)
    except Exception as exc:
        check('browser execution', False, repr(exc))
    finally:
        if b:
            try:
                if saved is not None:
                    b.navigate('/')
                    b.js('const s=' + json.dumps(saved) + ';localStorage.clear();for(const [k,v] of Object.entries(s))localStorage.setItem(k,v);')
            except Exception as exc:
                check('restore localStorage', False, repr(exc))
            b.ws.close()
        if tab:
            guarded('close temporary tab', lambda: http('/json/close/' + tab['id']))
    failures = [(n, d) for n, ok, d in RESULTS if not ok]
    print('\nFAILURE TABLE\nCheck | Detail')
    for n, d in failures:
        print(n + ' | ' + d)
    if not failures:
        print('(none)')
    print('\n{} passed, {} failed'.format(len(RESULTS)-len(failures), len(failures)))
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main())
