#!/usr/bin/env python3
"""Clear-all must wipe the charts too, not just the table."""
import base64, json, time, urllib.request
import websocket

t = json.load(urllib.request.urlopen(urllib.request.Request(
    'http://127.0.0.1:9333/json/new?http://localhost:8000/', method='PUT'), timeout=10))
ws = websocket.create_connection(t['webSocketDebuggerUrl'], timeout=90)
mid, errors = 0, []


def send(m, p=None):
    global mid
    mid += 1
    ws.send(json.dumps({'id': mid, 'method': m, 'params': p or {}}))
    while True:
        r = json.loads(ws.recv())
        if r.get('method') == 'Runtime.exceptionThrown':
            errors.append(str(r['params']['exceptionDetails'].get('exception', {}))[:200])
        if r.get('id') == mid:
            return r.get('result', {})


def ev(e):
    return send('Runtime.evaluate', {'expression': e, 'returnByValue': True,
                                     'awaitPromise': True}).get('result', {}).get('value')


STATE = """(() => ({
  hero: document.querySelector('.hero .stats .v').textContent,
  rows: document.querySelectorAll('#rows tr.row').length,
  heatCells: document.querySelectorAll('#chartHeat rect').length,
  stackBars: document.querySelectorAll('#chartStack rect').length,
  donutArcs: document.querySelectorAll('#chartDonut path').length,
  scatterDots: document.querySelectorAll('#chartScatter circle').length,
  areaPath: !!document.querySelector('#chartArea path'),
  hours: document.querySelectorAll('#chartHours rect').length,
  sentBars: document.querySelectorAll('#chartSentPlat rect').length,
  trendPath: (document.querySelector('#chart path')||{}).getAttribute ? 
             (document.querySelector('#chart path')||{}).getAttribute('d') : null,
  issues: document.querySelectorAll('#issues .issue').length,
  terms: document.querySelectorAll('#termlist .chip').length,
  authors: document.querySelectorAll('#authors .au, #authors .row').length
}))()"""

send('Runtime.enable')
send('Emulation.setDeviceMetricsOverride', {'width': 1440, 'height': 1100, 'deviceScaleFactor': 2, 'mobile': False})
time.sleep(6)
ev("window.confirm = () => true")
print('BEFORE:', ev(STATE))

ev("document.querySelector('#clearAll').click()")
time.sleep(5)
print('AFTER :', ev(STATE))

shot = send('Page.captureScreenshot', {'format': 'png'})
open('/Users/mamyboy/.hermes/cache/scratch/cleared_charts.png', 'wb').write(
    base64.b64decode(shot['data']))
print('SHOT: /Users/mamyboy/.hermes/cache/scratch/cleared_charts.png')
print('JS ERRORS:', errors or 'none')
