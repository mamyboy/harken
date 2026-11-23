#!/usr/bin/python3
"""Motion contracts on an isolated CDP :9333 tab; starts no processes.

The integrator owns tags. Missing tags are injected into this tab only, matching
verify_v6_states.py. HARKEN_MOTION_CDP may isolate parallel local self-tests.
"""
import json
import os
import sys
import time
import urllib.request

import websocket

BASE = 'http://localhost:8000'
CDP = os.environ.get('HARKEN_MOTION_CDP', 'http://127.0.0.1:9333')
RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append(bool(ok))
    print(('PASS' if ok else 'FAIL') + '  ' + name + '  ' + str(detail).replace('\n', ' '), flush=True)


def http(path, method='GET'):
    with urllib.request.urlopen(urllib.request.Request(CDP + path, method=method), timeout=15) as r:
        text = r.read().decode()
        return json.loads(text) if text[:1] in ('{', '[') else text


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
        r = self.call('Runtime.evaluate', dict(expression='(async()=>{' + body + '})()', awaitPromise=True, returnByValue=True))
        if 'exceptionDetails' in r:
            raise RuntimeError(r['exceptionDetails'])
        return r['result'].get('value')


def load(b, reduced=False):
    b.call('Emulation.setEmulatedMedia', {'features': [{'name': 'prefers-reduced-motion', 'value': 'reduce' if reduced else 'no-preference'}]})
    b.call('Page.navigate', {'url': BASE + '/'})
    end = time.monotonic() + 20
    while time.monotonic() < end:
        if b.js('return document.readyState === "complete" && !!document.querySelector("#topRows");'):
            break
        time.sleep(.05)
    else:
        raise TimeoutError('overview did not load')
    # Fonts and initial API repaint must settle before comparing geometry.
    time.sleep(1.5)
    return b.js('''await document.fonts.ready;
if (!document.querySelector('link[href*="micro-motion.css"]')) await new Promise((ok,no)=>{
const l=document.createElement('link');l.rel='stylesheet';l.href='/static/micro-motion.css';l.onload=ok;l.onerror=no;document.head.append(l);});
if (!window.__microMotion) await new Promise((ok,no)=>{const s=document.createElement('script');
s.src='/static/micro-motion.js';s.onload=ok;s.onerror=no;document.head.append(s);});
return !!window.__microMotion?.ready && document.documentElement.classList.contains('micro-motion');''')


def exercise(b):
    b.call('Page.enable')
    b.call('Page.addScriptToEvaluateOnNewDocument', {'source': 'window.setInterval=()=>0; window.__motionErrors=[]; addEventListener("error",e=>window.__motionErrors.push(e.message));'})
    b.call('Network.setCacheDisabled', {'cacheDisabled': True})
    b.call('Emulation.setDeviceMetricsOverride', dict(width=1440, height=900, deviceScaleFactor=1, mobile=False))
    check('assets load and API exists', load(b))
    time.sleep(.35)
    d = b.js('''const e=[...document.querySelectorAll('.card[data-mm-reveal="pending"]')].find(e=>!e.querySelector('.tablewrap'));
if(!e)return {found:false};e.id=e.id||'mm-test-card';window.__motionCard=e;
const r=e.getBoundingClientRect();window.__motionBox={width:r.width,height:r.height,offsetWidth:e.offsetWidth,offsetHeight:e.offsetHeight};
return {found:true,opacity:getComputedStyle(e).opacity,transform:getComputedStyle(e).transform,box:window.__motionBox};''')
    check('offscreen card hidden before reveal', d.get('found') and float(d.get('opacity', 1)) == 0, d)
    if d.get('found'):
        d = b.js('''const e=window.__motionCard,start=performance.now();e.scrollIntoView({block:'center',behavior:'instant'});
await new Promise(ok=>{function tick(){if(getComputedStyle(e).opacity==='1' && e.dataset.mmReveal==='done')ok();
else if(performance.now()-start>400)ok();else requestAnimationFrame(tick);}tick();});
const r=e.getBoundingClientRect(),s=getComputedStyle(e),old=window.__motionBox;
return {elapsed:performance.now()-start,done:e.dataset.mmReveal,opacity:s.opacity,transform:s.transform,willChange:s.willChange,
same:Math.abs(r.width-old.width)<.1 && Math.abs(r.height-old.height)<.1 && e.offsetWidth===old.offsetWidth && e.offsetHeight===old.offsetHeight};''')
        check('reveal completes within 400ms', d['elapsed'] <= 400 and d['done'] == 'done' and d['opacity'] == '1' and d['transform'] == 'none', d)
        check('identical reveal box and will-change released', d['same'] and d['willChange'] == 'auto', d)
    d = b.js('''const groups={};document.querySelectorAll('[data-mm-stagger]').forEach(e=>{groups[e.dataset.mmGroup]=(groups[e.dataset.mmGroup]||0)+1;});
return {groups,budget:[...document.querySelectorAll('[data-mm-stagger]')].every(e=>parseFloat(e.style.getPropertyValue('--mm-duration'))+parseFloat(e.style.getPropertyValue('--mm-delay'))<=300)};''')
    check('at most six staggered items per group', bool(d['groups']) and max(d['groups'].values()) <= 6, d)
    check('entrance total duration at most 300ms', d['budget'])
    d = b.js('''const host=document.createElement('div');host.id='mm-state-test';host.dataset.state='loading';
host.innerHTML='<div class="hstate" data-state="loading">กำลังโหลดข้อมูล</div>';document.body.append(host);
const ui=host.firstChild,loading=getComputedStyle(ui).animationName,duration=getComputedStyle(ui).animationDuration;
host.dataset.state='empty';const empty=getComputedStyle(ui).animationName;
host.dataset.state='error';const error=getComputedStyle(ui).animationName;
host.dataset.state='no-source';const noSource=getComputedStyle(ui).animationName;
return {loading,duration,empty,error,noSource};''')
    check('loading shimmer only and stops instantly on state change', d == dict(loading='mm-shimmer', duration='1.4s', empty='none', error='none', noSource='none'), d)
    time.sleep(1)
    d = b.js('''const host=document.querySelector('#topRows');host.dataset.state='ready';host.innerHTML='<tr><td>motion probe</td></tr>';
await new Promise(ok=>setTimeout(ok,600));const before=window.__microMotion.sweepCount;
host.innerHTML=host.innerHTML;await new Promise(ok=>setTimeout(ok,600));
return {before,after:window.__microMotion.sweepCount};''')
    check('identical DOM repaint skips sweep', d['before'] == d['after'], d)
    d = b.js('''const before=window.__microMotion.sweepCount;document.querySelector('#topRows td').firstChild.data='new data';
const deadline=performance.now()+700;while(window.__microMotion.sweepCount===before&&performance.now()<deadline)await new Promise(ok=>setTimeout(ok,20));const after=window.__microMotion.sweepCount;
const sweep=document.querySelector('#appbar .mm-refresh');const duration=getComputedStyle(sweep).animationDuration;
await new Promise(ok=>setTimeout(ok,950));return {before,after,duration,stopped:!sweep.classList.contains('mm-sweeping'),count:document.querySelectorAll('.mm-refresh').length};''')
    check('changed text cues one 900ms hairline then stops', d['after'] == d['before'] + 1 and d['duration'] == '0.9s' and d['stopped'] and d['count'] == 1, d)
    check('reduced-motion assets load', load(b, True))
    d = b.js('''const bad=[...document.querySelectorAll('[data-mm-reveal]')].filter(e=>{const s=getComputedStyle(e);return +s.opacity<1||!['none','matrix(1, 0, 0, 1, 0, 0)'].includes(s.transform);});
return {bad:bad.length,pending:document.querySelectorAll('[data-mm-reveal="pending"]').length};''')
    check('reduced motion final opacity and identity transform at load', d['bad'] == 0 and d['pending'] == 0, d)
    d = b.js('''const host=document.createElement('div');host.dataset.state='loading';host.innerHTML='<div class="hstate" data-state="loading">loading</div>';document.body.append(host);
const before=window.__microMotion.sweepCount;document.querySelector('#topRows').textContent='reduced change';
await new Promise(ok=>setTimeout(ok,100));return {shimmer:getComputedStyle(host.firstChild).animationName,sweep:window.__microMotion.sweepCount-before};''')
    check('reduced motion disables shimmer and repaint cue', d == {'shimmer': 'none', 'sweep': 0}, d)
    d = b.js('''const old=window.__microMotion;await new Promise((ok,no)=>{const s=document.createElement('script');s.src='/static/micro-motion.js';s.onload=ok;s.onerror=no;document.head.append(s);});
return old===window.__microMotion&&document.querySelectorAll('.mm-refresh').length===1;''')
    check('idempotent initialization', d)
    errors = b.js('return window.__motionErrors;')
    check('no browser errors', errors == [], errors)


def main():
    tab = b = None
    try:
        tab = http('/json/new?about:blank', 'PUT')
        b = Browser(tab)
        exercise(b)
    except Exception as exc:
        check('browser execution', False, repr(exc))
    finally:
        if b:
            b.ws.close()
        if tab:
            try:
                http('/json/close/' + tab['id'])
            except Exception as exc:
                check('close temporary tab', False, repr(exc))
    failed = RESULTS.count(False)
    print('\n{} passed, {} failed'.format(len(RESULTS) - failed, failed))
    return int(bool(failed))


if __name__ == '__main__':
    sys.exit(main())
