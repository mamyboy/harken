#!/usr/bin/env python3
"""Typography audit: the real font must be the one the CSS names, Thai must never
drop below 12px, Thai must carry no tracking, and the scale must be monotonic."""
import json

import sys, time, urllib.request, websocket

FAILS = []

def check(name, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + name + ('  ' + json.dumps(detail, ensure_ascii=False) if detail != '' else ''))
    if not ok:
        FAILS.append((name, detail))

class Tab:
    def __init__(self):
        self.t = json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:9333/json/new?about:blank', method='PUT')))
        self.ws = websocket.create_connection(self.t['webSocketDebuggerUrl'], timeout=40)
        self.i = 0
    def call(self, m, **p):
        self.i += 1; n = self.i
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
    def go(self, url, w, h, dsf=1):
        self.call('Emulation.setDeviceMetricsOverride', width=w, height=h, deviceScaleFactor=dsf, mobile=w < 500)
        self.call('Page.navigate', url=url); time.sleep(1)
        self.call('Runtime.evaluate', expression="document.readyState")
        time.sleep(6)
    def close(self):
        try: urllib.request.urlopen('http://127.0.0.1:9333/json/close/' + self.t['id'])
        except Exception: pass

AUDIT = r"""(() => {
 const c=document.createElement('canvas').getContext('2d');
 const s='สวัสดีครับ Harken ๑๒๓ 0123';
 const w=f=>{c.font='40px '+f; return Math.round(c.measureText(s).width*100)/100;};
 const thai=/[\u0E00-\u0E7F]/;
 const small=[...document.querySelectorAll('body *')].filter(e=>{
   const own=[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
   if(!own||!thai.test(own)) return false;
   const r=e.getBoundingClientRect(); if(r.width<1) return false;
   const cs=getComputedStyle(e); if(cs.visibility==='hidden'||cs.display==='none') return false;
   return parseFloat(cs.fontSize)<12;
 }).map(e=>({cls:String(e.className||e.tagName).slice(0,28),fs:getComputedStyle(e).fontSize,txt:e.textContent.trim().slice(0,18)}));
 const tracked=[...document.querySelectorAll('h1,h2,h3,.tag,.k,.sub,.crumbs a,.navlink .nl,.kpi .k,.section h2,.card-head h2')]
   .filter(e=>thai.test(e.textContent||''))
   .map(e=>{const cs=getComputedStyle(e);return {cls:String(e.className||e.tagName).slice(0,24),ls:cs.letterSpacing,fs:cs.fontSize};})
   .filter(x=>x.ls!=='normal'&&parseFloat(x.ls)!==0);
 const fs=s=>{const e=document.querySelector(s); return e?parseFloat(getComputedStyle(e).fontSize):null;};
 return JSON.stringify({
   plex:w('"IBM Plex Sans Thai"'), serif:w('serif'), noto:w('"Noto Sans Thai"'),
   faces:[...document.fonts].filter(f=>/IBM Plex/.test(f.family)).map(f=>f.weight+':'+f.status),
   small, tracked,
   scale:{h2:fs('.section h2'), title:fs('.card-head h2'), body:fs('body'), label:fs('.kpi .k'),
          lead:fs('.kpi.lead .v'), kpi:fs('.kpis .kpi:not(.lead) .v')},
   synth:getComputedStyle(document.body).fontSynthesis,
   root:getComputedStyle(document.documentElement).getPropertyValue('--fs-body').trim()
 });})()"""


# --- dark-theme leak guard: no light ground may survive a dark page ----------
LEAK = r"""(() => {
 const parse=c=>{const m=c.match(/[\d.]+/g).map(Number);return {r:m[0],g:m[1],b:m[2],a:m.length>3?m[3]:1};};
 const f=v=>{v/=255;return v<=.04045?v/12.92:Math.pow((v+.055)/1.055,2.4)};
 const lum=p=>.2126*f(p.r)+.7152*f(p.g)+.0722*f(p.b);
 const GROUND={r:21,g:38,b:74};           // the dark page stop
 const over=(c,g)=>({r:c.r*c.a+g.r*(1-c.a), g:c.g*c.a+g.g*(1-c.a), b:c.b*c.a+g.b*(1-c.a)});
 const bad=[];
 for (const e of document.querySelectorAll('body *')) {
   if (/^chrome_/.test(e.className || '')) continue;          // browser-injected UI, not ours
   const t=[...e.childNodes].filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim();
   if(!t) continue;
   const r=e.getBoundingClientRect(); if(r.width<8||r.height<8) continue;
   const bg=getComputedStyle(e).backgroundColor;
   if(bg==='rgba(0, 0, 0, 0)'||bg==='transparent') continue;
   const eff=over(parse(bg), GROUND);
   if(lum(eff)>0.30) bad.push({cls:String(e.className||e.tagName).slice(0,26),bg,effLum:+lum(eff).toFixed(3),txt:t.slice(0,14)});
 }
 return JSON.stringify(bad.slice(0,10));})()"""

def dark_leak():
    tab.js("localStorage.setItem('harken-theme','dark')")
    for route in ('/presets', '/'):
        tab.call('Page.navigate', url='http://localhost:8000' + route); time.sleep(6)
        found = json.loads(tab.js(LEAK))
        check('dark has no light ground ' + route, not found, found)
    tab.js("localStorage.setItem('harken-theme','light')")

tab = Tab()
try:
    tab.go('http://localhost:8000/', 1440, 1000)
    a = json.loads(tab.js(AUDIT))

    check('font files parse (8 faces)', len([f for f in a['faces'] if f.endswith('loaded')]) == 8, a['faces'])
    check('IBM Plex Sans Thai actually renders', abs(a['plex'] - a['serif']) > 1 and abs(a['plex'] - a['noto']) > 1,
          {'plex': a['plex'], 'serif': a['serif'], 'noto': a['noto']})
    check('no Thai text below 12px', not a['small'], a['small'])
    check('no tracking on Thai text', not a['tracked'], a['tracked'])
    check('no synthetic bold', a['synth'] == 'none', a['synth'])

    sc = a['scale']
    check('scale is monotonic', sc['h2'] > sc['title'] > sc['body'] > sc['label'],
          sc)
    check('lead KPI outranks the rest', sc['lead'] > sc['kpi'] == 30, {'lead': sc['lead'], 'kpi': sc['kpi']})
    check('section heading >= 18px', sc['h2'] >= 18, sc['h2'])
    check('body sits at 14.5px', sc['body'] == 14.5, sc['body'])
    check('labels sit at 12px', sc['label'] == 12, sc['label'])
    check('scale tokens exist', a['root'] == '14.5px', a['root'])

    dark_leak()
    tab.go('http://localhost:8000/', 390, 844, 2)
    m = json.loads(tab.js(AUDIT))
    check('mobile: no Thai below 12px', not m['small'], m['small'])
    check('mobile: lead KPI still outranks', m['scale']['lead'] > m['scale']['kpi'],
          {'lead': m['scale']['lead'], 'kpi': m['scale']['kpi']})
    check('mobile: no horizontal overflow', tab.js('document.documentElement.scrollWidth - innerWidth') <= 1)
finally:
    tab.close()

print('\n%d passed, %d failed' % (len(FAILS) and 0 or 0, 0) if False else '')
total = 15
print('%d passed, %d failed' % (total - len(FAILS), len(FAILS)))
sys.exit(1 if FAILS else 0)
