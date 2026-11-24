#!/usr/bin/python3
"""Harken v5: real-CDP motion and regression acceptance; no app edits."""
import json
import re
import subprocess
import sys
import time
import urllib.parse

sys.path.insert(0, __import__('os').path.dirname(__file__))
import dataset
import urllib.request

from pathlib import Path
import websocket

BASE, CDP = 'http://localhost:8000', 'http://127.0.0.1:9333'
RESULTS = []


def check(name, ok, detail):
    detail = str(detail).replace('\n', ' ')
    RESULTS.append((name, bool(ok), detail))
    print(('PASS' if ok else 'FAIL') + '  ' + name + '  ' + detail, flush=True)


def http(path, method='GET'):
    with urllib.request.urlopen(urllib.request.Request(CDP + path, method=method), timeout=15) as r:
        return json.loads(r.read()) if path.startswith('/json/new?') else r.read().decode()


# Observe chart insertion before application scripts execute. Sampling relative to
# series insertion avoids missing the animation while APIs load asynchronously.
PROBE = r'''(() => {
const selector='#chartTrend path[class*="series"], #chartTrend path[fill="none"][stroke-width="2.6"]';
window.__v5arm=()=>{
 const p=document.querySelector(selector);
 window.__v5probe={old:p,samples:[],started:false};
};
window.__v5arm();
new MutationObserver(()=>{
 const s=window.__v5probe,p=document.querySelector(selector);
 if(!p||s.started||p===s.old)return;
 s.started=true;s.start=performance.now();
 const sample=()=>{s.samples.push({ms:performance.now()-s.start,
 offset:getComputedStyle(p).strokeDashoffset,inline:p.style.strokeDasharray,
 attr:p.getAttribute('stroke-dasharray'),class:p.getAttribute('class'),
 length:p.getTotalLength(),connected:p.isConnected});};
 setTimeout(sample,60);setTimeout(sample,900);
}).observe(document,{childList:true,subtree:true});
})();'''

LAYERS = r'''const choices=['body','.shell'].map(selector=>{
 const e=document.querySelector(selector);
 return {selector,layers:e?['::before','::after'].map(pseudo=>{
  const s=getComputedStyle(e,pseudo);let x=0,y=0,z=0;
  try{const m=new DOMMatrixReadOnly(s.transform);x=m.m41;y=m.m42;z=m.m43;}catch(e){}
  const t=s.translate;
  const individual=t&&t!=='none'&&t.split(/\s+/).some(v=>parseFloat(v)!==0);
  return {pseudo,content:s.content,display:s.display,background:s.backgroundImage,
   transform:s.transform,translate:t,translated:Math.abs(x)+Math.abs(y)+Math.abs(z)>.001||!!individual,
   exists:s.content!=='none'&&s.content!=='normal'&&s.display!=='none'};
 }):[]};});
const chosen=choices.find(c=>c.layers.length===2&&c.layers.every(l=>l.exists));
return {chosen:chosen||null,choices};'''


class Browser:
    def __init__(self, tab):
        self.ws = websocket.create_connection(tab['webSocketDebuggerUrl'], timeout=20, suppress_origin=True)
        self.seq = 0
        self.call('Page.enable')
        self.call('Network.enable')
        self.call('Network.setCacheDisabled', {'cacheDisabled': True})
        self.call('Page.addScriptToEvaluateOnNewDocument', {'source': PROBE})

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
        r = self.call('Runtime.evaluate', {'expression': '(() => {' + body + '})()', 'returnByValue': True})
        if 'exceptionDetails' in r:
            raise RuntimeError(r['exceptionDetails'])
        return r['result'].get('value')

    def wait(self, condition, timeout=20):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                if self.js('return Boolean(' + condition + ');'):
                    return
            except RuntimeError:
                pass
            time.sleep(.025)
        raise TimeoutError(condition)

    def navigate(self, route):
        r = self.call('Page.navigate', {'url': BASE + route})
        if r.get('errorText'):
            raise RuntimeError(r['errorText'])
        self.wait('location.pathname===' + json.dumps(route) + '&&document.readyState==="complete"')

    def size(self, w, h):
        self.call('Emulation.setDeviceMetricsOverride', dict(width=w, height=h, deviceScaleFactor=1, mobile=w < 500))

    def media(self, reduced):
        self.call('Emulation.setEmulatedMedia', {'features': [
            {'name': 'prefers-reduced-motion', 'value': 'reduce' if reduced else 'no-preference'}]})


def guarded(name, fn):
    try:
        fn()
    except Exception as exc:
        check(name, False, repr(exc))


def parallax(b, reduced=False):
    b.media(reduced)
    b.size(1280, 800)
    b.navigate('/')
    time.sleep(1.2)
    b.js('''scrollTo(0,0);window.__v5cls=0;window.__v5shifts=[];
window.__v5po=new PerformanceObserver(list=>{for(const e of list.getEntries()){
window.__v5cls+=e.value;window.__v5shifts.push({value:e.value,recentInput:e.hadRecentInput});}});
window.__v5po.observe({type:'layout-shift',buffered:false});''')
    time.sleep(.1)
    b.js('scrollTo(0,700);')
    time.sleep(.3)
    d = b.js('''return {sy:getComputedStyle(document.documentElement).getPropertyValue('--sy').trim(),
scroll:scrollY,enabled:window.HarkenMotion?.enabled?.(),cls:(window.__v5cls===undefined?null:window.__v5cls),shifts:window.__v5shifts||[]};''')
    b.js('try{window.__v5po&&window.__v5po.disconnect();}catch(e){}')
    layers = b.js(LAYERS)
    chosen = layers['chosen']
    if reduced:
        check('B reduced --sy', d['sy'] in ('', '0px'), d)
        check('B motion disabled', d.get('enabled') is False, d)
        check('B blooms stationary', bool(chosen) and all(not x['translated'] for x in chosen['layers']), layers)
    else:
        valid = bool(re.fullmatch(r'-?\d+(?:\.\d+)?px', d['sy']))
        check('A scroll --sy px', valid and d['scroll'] > 0 and float(d['sy'][:-2]) == int(d['scroll']), d)
        check('A two translated blooms', bool(chosen) and all(x['translated'] for x in chosen['layers']), layers)
        check('A scrolling CLS < 0.05', d['cls'] < .05, d)


def line_draw(b):
    if dataset.empty():
        dataset.skip('C line draw 60ms -> 900ms')
        return
    b.media(False)
    b.size(1280, 800)
    b.navigate('/')
    try:
        b.wait('window.__v5probe?.samples.length===2', 12)
    except TimeoutError:
        check('C initial line draw', False, b.js('''return {probe:window.__v5probe,
paths:[...document.querySelectorAll('#chartTrend path')].map(p=>({class:p.getAttribute('class'),style:p.getAttribute('style')}))};'''))
        return
    samples = b.js('return window.__v5probe.samples;')
    a, z = samples
    num = lambda s: float(re.match(r'^(-?[\d.]+)', s).group(1))
    check('C line draw 60ms -> 900ms', a['connected'] and z['connected'] and
          num(a['offset']) > num(z['offset']) + 10 and abs(num(z['offset'])) < .01 and
          40 <= a['ms'] <= 180 and 850 <= z['ms'] <= 1100, samples)
    b.js('window.__v5arm();document.querySelector("#segHour").click();')
    b.wait('window.__v5probe?.samples.length>=1', 12)
    replay = b.js('return {sample:window.__v5probe.samples[0],pressed:document.querySelector("#segHour").getAttribute("aria-pressed")};')
    check('C hourly replay 60ms', replay['pressed'] == 'true' and num(replay['sample']['offset']) > 10, replay)


def reduced_line(b):
    if dataset.empty():
        dataset.skip('C reduced no inline dasharray')
        return
    b.media(True)
    b.navigate('/')
    b.wait('document.querySelector(\'#chartTrend path[class*="series"], #chartTrend path[fill="none"][stroke-width="2.6"]\')', 12)
    d = b.js('''const p=document.querySelector('#chartTrend path[class*="series"], #chartTrend path[fill="none"][stroke-width="2.6"]');
return {inline:p.style.strokeDasharray,attr:p.getAttribute('stroke-dasharray'),offset:getComputedStyle(p).strokeDashoffset};''')
    check('C reduced no inline dasharray', d['inline'] == '' and d['attr'] is None, d)


def transitions(b):
    b.media(False)
    b.navigate('/')
    d = b.js('''let texts=[],blocked=[];function walk(rules){for(const r of rules){texts.push(r.cssText);if(r.cssRules)walk(r.cssRules);}}
for(const s of document.styleSheets){try{walk(s.cssRules);}catch(e){blocked.push(e.name);}}
return {supported:CSS.supports('view-transition-name: none'),vt:document.documentElement.classList.contains('vt'),
rule:texts.some(t=>/@view-transition\s*\{/.test(t)),blocked,
rail:getComputedStyle(document.querySelector('.topnav')).viewTransitionName};''')
    for key, expected in (('supported', True), ('vt', True), ('rule', True), ('rail', 'rail')):
        check('D transition ' + key, d[key] == expected, d)
    for route in ('/tools', '/'):
        b.navigate(route)
        d = b.js('return {path:location.pathname,ready:document.readyState,title:document.title,vt:document.documentElement.classList.contains("vt"),shell:!!document.querySelector(".shell")};')
        check('D arrival ' + route, d['path'] == route and d['ready'] == 'complete' and d['shell'] and d['vt'], d)


def mobile(b):
    b.media(False)
    b.size(390, 844)
    for theme in ('light', 'dark'):
        b.js('localStorage.setItem("harken-theme",' + json.dumps(theme) + ');')
        b.navigate('/')
        time.sleep(1)
        for y in (0, 700):
            b.js('scrollTo(0,' + str(y) + ');')
            time.sleep(.3)
            d = b.js('''const a=document.querySelector('#appbar'),s=getComputedStyle(a);
return {width:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,inner:innerWidth,
theme:document.documentElement.dataset.theme,position:s.position,top:a.getBoundingClientRect().top,
offset:parseFloat(s.top),scroll:scrollY};''')
            check('E mobile ' + theme + ' overflow @' + str(y), d['theme'] == theme and
                  max(d['width'], d['bodyWidth']) <= d['inner'] + 1, d)
            check('E mobile ' + theme + ' sticky @' + str(y), d['position'] == 'sticky' and
                  (y == 0 or (d['scroll'] > 0 and abs(d['top'] - d['offset']) <= 2)), d)


def regressions():
    for name in ('verify_ui.py', 'verify_v3.py', 'verify_v4.py'):
        try:
            r = subprocess.run(['/usr/bin/python3', str(Path(__file__).with_name(name))],
                               capture_output=True, text=True, timeout=600)
            summaries = re.findall(r'\d+ passed, \d+ failed', r.stdout)
            fails = [s for s in r.stdout.splitlines() if s.startswith('FAIL')]
            check('E regression ' + name, r.returncode == 0 and bool(summaries) and
                  all(s.endswith(', 0 failed') for s in summaries),
                  {'summaries': summaries, 'exit': r.returncode, 'failures': fails, 'stderr': r.stderr[-1500:]})
        except Exception as exc:
            check('E regression ' + name, False, repr(exc))


def main():
    tab, b, saved = None, None, None
    try:
        tab = http('/json/new?' + urllib.parse.quote(BASE + '/', safe=':/'), 'PUT')
        b = Browser(tab)
        b.wait('location.origin===' + json.dumps(BASE) + '&&document.readyState==="complete"')
        saved = b.js('return {theme:localStorage.getItem("harken-theme")};')
        for name, fn in [('A parallax', lambda: parallax(b)), ('B reduced parallax', lambda: parallax(b, True)),
                         ('C line draw', lambda: line_draw(b)), ('C reduced line', lambda: reduced_line(b)),
                         ('D transitions', lambda: transitions(b)), ('E mobile', lambda: mobile(b))]:
            guarded(name, fn)
    except Exception as exc:
        check('browser setup', False, repr(exc))
    finally:
        if b:
            for name, fn in [('media', lambda: b.call('Emulation.setEmulatedMedia', {'features': []})),
                             ('viewport', lambda: b.call('Emulation.clearDeviceMetricsOverride')),
                             ('storage', lambda: b.js('const t=' + json.dumps(saved) + ';if(t){if(t.theme===null)localStorage.removeItem("harken-theme");else localStorage.setItem("harken-theme",t.theme);}'))]:
                try:
                    fn()
                except Exception as exc:
                    check('cleanup ' + name, False, repr(exc))
            b.ws.close()
        if tab:
            guarded('close tab', lambda: http('/json/close/' + tab['id']))
    regressions()
    failures = [(n, d) for n, ok, d in RESULTS if not ok]
    print('\nFailure table:')
    print('Check | Detail')
    for n, d in failures:
        print(n + ' | ' + d)
    if not failures:
        print('(none)')
    print('{} passed, {} failed'.format(len(RESULTS) - len(failures), len(failures)))
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
