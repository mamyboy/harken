#!/usr/bin/python3
"""States contract on the real overview, isolated CDP :9333 only.

Run: /usr/bin/python3 tests/verify_v6_states.py
The integrator owns HTML tags. Until wired, load the served assets into this
throwaway tab only; never patch application files or touch operator Chrome.
"""
import json
import sys
import time
import urllib.request

import websocket

BASE = 'http://localhost:8000'
CDP = 'http://127.0.0.1:9333'
RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append(bool(ok))
    print(('PASS' if ok else 'FAIL') + '  ' + name + '  ' +
          str(detail).replace('\n', ' '), flush=True)


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
        result = self.call('Runtime.evaluate', dict(expression='(async () => {' + body + '})()',
                                                  awaitPromise=True, returnByValue=True))
        if 'exceptionDetails' in result:
            raise RuntimeError(result['exceptionDetails'])
        return result['result'].get('value')


def exercise(b):
    # Stop periodic repaint racing contract assertions; initial fetch still runs.
    b.call('Page.addScriptToEvaluateOnNewDocument', {'source': 'window.setInterval = () => 0;'})
    b.call('Network.setCacheDisabled', {'cacheDisabled': True})
    b.call('Page.navigate', {'url': BASE + '/'})
    end = time.monotonic() + 20
    while time.monotonic() < end:
        if b.js('return document.readyState === "complete" && !!document.querySelector("#topRows");'):
            break
        time.sleep(.1)
    else:
        raise TimeoutError('overview did not load')
    time.sleep(1.5)
    loaded = b.js('''const wired=!!window.HarkenStates;
if(!document.querySelector('link[href*="states.css"]')) {
  await new Promise((resolve,reject)=>{const l=document.createElement('link');
  l.rel='stylesheet';l.href='/static/states.css';l.onload=resolve;l.onerror=()=>reject(Error('states.css load'));
  document.head.append(l);});
}
if(!wired) await new Promise((resolve,reject)=>{const s=document.createElement('script');
s.src='/static/states.js';s.onload=resolve;s.onerror=()=>reject(Error('states.js load'));document.head.append(s);});
return {exists:typeof window.HarkenStates?.set==='function' && typeof window.HarkenStates?.stamp==='function',wired};''')
    check('API exists after asset load', loaded['exists'], loaded)
    if not loaded['exists']:
        return
    d = b.js('''const el=document.querySelector('#topRows');
window.__stateNodes=[...el.childNodes];window.__stateCount=el.children.length;
HarkenStates.set('#topRows','empty');const states=el.querySelectorAll('.hstate');
return {count:states.length,role:states[0]?.getAttribute('role'),text:states[0]?.textContent,
validTable:!!el.querySelector(':scope > tr > td > .hstate')};''')
    check('empty single accessible honest state', d['count'] == 1 and d['role'] == 'status'
          and bool(d['text']) and d['text'].strip() not in ('0', '๐') and d['validTable'], d)
    d = b.js('''HarkenStates.set('#topRows','ready');const el=document.querySelector('#topRows');
return {count:el.children.length,expected:window.__stateCount,
identity:[...el.childNodes].every((n,i)=>n===window.__stateNodes[i]),states:el.querySelectorAll('.hstate').length};''')
    check('ready restores original count and node identity', d['count'] == d['expected']
          and d['identity'] and d['states'] == 0, d)
    d = b.js('''const el=document.querySelector('#topRows');
const rows=['loading','empty','no-source','error'].map(state=>{
HarkenStates.set(el,state);const ui=el.querySelector('.hstate');
return {state,attribute:ui?.dataset.state,host:el.dataset.state,role:ui?.getAttribute('role'),
count:el.querySelectorAll('.hstate').length,busy:el.getAttribute('aria-busy'),
fonts:[ui,...ui.querySelectorAll('*')].filter(n=>/[\u0e00-\u0e7f]/.test(n.textContent))
.map(n=>parseFloat(getComputedStyle(n).fontSize))};});HarkenStates.set(el,'ready');return rows;''')
    check('four distinct state attributes', len({r['attribute'] for r in d}) == 4 and
          all(r['attribute'] == r['state'] == r['host'] and r['count'] == 1 and r['role'] == 'status' for r in d), d)
    check('Thai text at least 12px', all(r['fonts'] and min(r['fonts']) >= 12 for r in d), d)
    check('loading alone is busy', all(r['busy'] == ('true' if r['state'] == 'loading' else 'false') for r in d), d)
    d = b.js('''return ['#topRows','#zoneRows','#issues','#newsRows','#terms','#kpis'].map(selector=>{
const el=document.querySelector(selector);if(!el)return {selector,ok:false};
const original=[...el.childNodes];for(const state of ['loading','empty','no-source','error'])HarkenStates.set(el,state);
HarkenStates.set(el,'ready');return {selector,ok:original.length===el.childNodes.length && original.every((n,i)=>n===el.childNodes[i])};});''')
    check('all overview regions restore through repeated states', all(r['ok'] for r in d), d)
    d = b.js('''const el=document.createElement('div');el.setAttribute('aria-busy','mixed');
const button=document.createElement('button');let clicks=0;button.onclick=()=>clicks++;el.append('text',button);
HarkenStates.set(el,'error',{message:'<img src=x onerror=alert(1)>',detail:'ลองใหม่'});
const safe=!el.querySelector('img')&&el.textContent.includes('<img');HarkenStates.set(el,'ready');button.click();
HarkenStates.set(el,'ready');return {safe,clicks,text:el.firstChild.textContent,busy:el.getAttribute('aria-busy')};''')
    check('safe custom text and preserved listeners attributes', d == {'safe': True, 'clicks': 1, 'text': 'text', 'busy': 'mixed'}, d)
    d = b.js('''const el=document.querySelector('#stamp');const old=el.textContent;
HarkenStates.stamp('2026-01-02T03:04:05Z');const iso=el.textContent;
HarkenStates.stamp(new Date('2026-01-02T03:04:05Z'));const date=el.textContent;
HarkenStates.stamp('invalid');const invalid=el.textContent;el.textContent=old;
return {iso,date,invalid};''')
    check('stamp Bangkok time accepts ISO and Date', d['iso'] == d['date'] and '10:04' in d['iso'] and 'NaN' not in d['invalid'], d)
    d = b.js('''HarkenStates.set('#not-present','error');HarkenStates.stamp(null);
const el=document.createElement('div');HarkenStates.set(el,'empty',{message:'0',detail:'0'});
return {text:el.textContent,hasZero:[...el.querySelectorAll('*')].some(n=>/^\s*[0๐]\s*$/.test(n.textContent))};''')
    check('absent targets safe and zero-only overrides rejected', bool(d['text']) and not d['hasZero'], d)


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
