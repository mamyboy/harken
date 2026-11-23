/* Additive chart access: reads the exact data-tip values emitted by sl-charts.js.
 * No fetch interception, renderer hooks, timers polling the API, or chart redraws.
 * Load after ov.js (defer is supported). Public entry point: __vizA11y.refresh(). */
(function () {
  'use strict';
  if (window.__vizA11y) { window.__vizA11y.refresh(); return; }
  var states = [], timer;
  var names = {x:'เอ็กซ์', twitter:'ทวิตเตอร์', threads:'เธรดส์', facebook:'เฟซบุ๊ก',
    fbfeed:'เฟซบุ๊กฟีด', tiktok:'ติ๊กต็อก', instagram:'อินสตาแกรม', ig:'อินสตาแกรม',
    youtube:'ยูทูบ', pantip:'พันทิป', lemon8:'เลมอนเอท', news:'ข่าวเว็บ', other:'อื่น ๆ'};
  function number(s) {
    var match = String(s || '').replace(/[๐-๙]/g, function (c) { return '๐๑๒๓๔๕๖๗๘๙'.indexOf(c); }).replace(/,/g, '').match(/\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : 0;
  }
  function n(v) { return Number(v).toLocaleString('th-TH'); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function tips(host, selector) {
    return Array.from(host.querySelectorAll(selector)).map(function (node) {
      var parts = node.getAttribute('data-tip').split('\n');
      return {node:node, label:parts[0], value:number(parts[1]), previous:number(parts[2])};
    });
  }
  function read(s) {
    var rows, range, title, headers;
    if (s.id === 'chartTrend') {
      rows = tips(s.host, 'rect[data-act="day"][data-tip]');
      rows.forEach(function (r) { r.key = r.node.getAttribute('data-day'); });
      range = rows.length ? rows[0].label + ' ถึง ' + rows[rows.length-1].label : 'ช่วงที่เลือก';
      title = 'กราฟเส้นแนวโน้ม'; headers = ['ช่วงเวลา', 'โพสต์', 'ช่วงก่อนหน้า'];
    } else if (s.id === 'chartHours') {
      rows = tips(s.host, 'rect[data-hover-group="hours"][data-tip]');
      range = '7 วันล่าสุด · 00–23 น.';
      title = 'กราฟแท่งรายชั่วโมง'; headers = ['ชั่วโมง', 'โพสต์'];
    } else {
      rows = tips(s.host, 'svg [data-act="platform"][data-tip]');
      rows.forEach(function (r) {
        r.key = r.node.getAttribute('data-platform');
        r.label = names[r.key] || 'แพลตฟอร์มอื่น';
      });
      range = 'ข้อมูลทั้งหมด'; title = 'กราฟโดนัทแพลตฟอร์ม'; headers = ['แพลตฟอร์ม', 'โพสต์', 'สัดส่วน'];
    }
    if (!rows.length && s.host.querySelector('canvas') && s.canvasRows) rows = s.canvasRows;
    var total = rows.reduce(function (a, r) { return a + r.value; }, 0);
    var peak = rows.reduce(function (a, r) { return !a || r.value > a.value ? r : a; }, null);
    var fact = peak && total ? (s.id === 'chartDonut' ? 'มากสุด ' : 'สูงสุด ') + peak.label + ' ' + n(peak.value) + ' โพสต์' : 'ยังไม่มีข้อมูล';
    return {rows:rows, total:total, peak:peak, title:title, headers:headers, range:range,
      label:(title + ' · ' + range + ' · รวม ' + n(total) + ' โพสต์ · ' + fact).slice(0,179)};
  }
  function table(s, d) {
    var signature = JSON.stringify([d.headers,d.range,d.rows.map(function (r) { return [r.label,r.value,r.previous]; })]);
    if (s.signature === signature) return;
    s.signature = signature;
    var t = el('table', 'viz-table');
    t.tabIndex = 0;
    t.appendChild(el('caption', '', d.title + ' · ' + d.range));
    var head = t.createTHead().insertRow();
    d.headers.forEach(function (h) { var th = el('th', '', h); th.scope = 'col'; head.appendChild(th); });
    var body = t.createTBody();
    d.rows.forEach(function (r) {
      var tr = body.insertRow(), th = el('th', '', r.label); th.scope = 'row'; tr.appendChild(th);
      tr.appendChild(el('td', '', n(r.value)));
      if (s.id === 'chartTrend') tr.appendChild(el('td', '', n(r.previous)));
      if (s.id === 'chartDonut') tr.appendChild(el('td', '', n(d.total ? Math.round(r.value / d.total * 100) : 0) + '%'));
    });
    if (!d.rows.length) { var cell = body.insertRow().insertCell(); cell.colSpan = d.headers.length; cell.textContent = 'ยังไม่มีข้อมูล'; }
    var foot = t.createTFoot().insertRow();
    var label = el('th', '', 'รวม'); label.scope = 'row'; foot.appendChild(label);
    foot.appendChild(el('td', '', n(d.total)));
    if (s.id === 'chartTrend') foot.appendChild(el('td', '', n(d.rows.reduce(function (a,r) { return a+r.previous; },0))));
    if (s.id === 'chartDonut') foot.appendChild(el('td', '', d.total ? '100%' : '0%'));
    // Preserve the focused table across refreshes when the data is unchanged.
    s.panel.replaceChildren(t);
  }
  function annotations(s, d) {
    if (s.id !== 'chartTrend') return;
    if (!s.overlay || !s.overlay.isConnected) {
      s.overlay = el('div','viz-annotations'); s.overlay.setAttribute('aria-hidden','true'); s.host.appendChild(s.overlay);
    }
    s.overlay.replaceChildren();
    if (!d.total || !d.rows.length) return;
    var last = d.rows[d.rows.length-1];
    var picks = d.peak === last ? [{r:last, text:'สูงสุด · ล่าสุด'}] : [{r:d.peak,text:'สูงสุด'},{r:last,text:'ล่าสุด'}];
    var box = s.host.getBoundingClientRect();
    var points = s.host.querySelectorAll('circle[r="3.4"]');
    var previousRect;
    picks.forEach(function (p) {
      var idx = d.rows.indexOf(p.r), point = points[idx];
      if (!point || !box.width || !box.height) return;
      var rect = point.getBoundingClientRect(), label = el('span','viz-annotation',p.text + ' ' + n(p.r.value));
      s.overlay.appendChild(label);
      var w = label.offsetWidth, h = label.offsetHeight;
      var x = Math.max(2,Math.min(box.width-w-2, rect.x+rect.width/2-box.x-w/2));
      var y = rect.y-box.y-h-7;
      if (y < 2) y = rect.bottom-box.y+7;
      y = Math.max(2,Math.min(box.height-h-2,y));
      if (previousRect && x < previousRect.x+previousRect.w+3 && x+w > previousRect.x && Math.abs(y-previousRect.y) < h+3) {
        y = Math.max(2,Math.min(box.height-h-2,previousRect.y+h+4));
      }
      label.style.left = x+'px'; label.style.top = y+'px';
      previousRect = {x:x,y:y,w:w};
    });
  }
  function rgb(value) {
    var probe = el('span'); probe.style.color = value; probe.style.display = 'none';
    document.body.appendChild(probe);
    var result = getComputedStyle(probe).color.match(/[\d.]+/g); probe.remove();
    return result ? result.map(Number) : [0,0,0,1];
  }
  function composite(fg,bg) { var a = fg.length > 3 ? fg[3] : 1; return fg.slice(0,3).map(function(v,i) { return v*a+bg[i]*(1-a); }); }
  function lum(c) { return c.slice(0,3).reduce(function (v,c,i) { c/=255; return v+[.2126,.7152,.0722][i]*(c<=.04045 ? c/12.92 : Math.pow((c+.055)/1.055,2.4)); },0); }
  function contrast(a,b) { var x=lum(a),y=lum(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); }
  function safety(s,d) {
    if (s.id !== 'chartDonut') return;
    if (s.host.querySelector('canvas')) {
      if (!s.legend || !s.legend.isConnected) {
        s.legend=el('ul','viz-canvas-legend'); s.host.appendChild(s.legend);
      }
      s.legend.replaceChildren();
      d.rows.forEach(function (r) { s.legend.appendChild(el('li','',r.label+' '+n(r.value)+' โพสต์ · '+n(d.total ? Math.round(r.value/d.total*100) : 0)+'%')); });
      return;
    }
    var ground = [255,255,255], chain=[], node=s.card;
    while (node && node.nodeType===1) { chain.unshift(node); node=node.parentElement; }
    chain.forEach(function (e) { ground=composite(rgb(getComputedStyle(e).backgroundColor),ground); });
    var colours = d.rows.map(function (r) { var style=getComputedStyle(r.node); return composite(rgb(r.node.tagName.toLowerCase()==='circle' ? style.stroke : style.fill),ground); });
    s.contrasts = colours.map(function (c) { return contrast(c,ground); });
    var low = colours.length>1 && colours.some(function (c,i) { return contrast(c,colours[(i+1)%colours.length])<1.3; });
    // Add separator overlays; never change a slice's geometry, fill or existing stroke.
    var svg=s.host.querySelector('svg');
    if (!svg) return;
    var old=svg.querySelector('[data-viz-separators]'); if(old) old.remove();
    if (!low) return;
    var ns='http://www.w3.org/2000/svg', group=document.createElementNS(ns,'g');
    group.setAttribute('data-viz-separators',''); group.setAttribute('aria-hidden','true');
    group.setAttribute('pointer-events','none');
    d.rows.forEach(function (r) {
      if (r.node.tagName.toLowerCase()!=='path') return;
      var path=document.createElementNS(ns,'path'); path.setAttribute('d',r.node.getAttribute('d'));
      path.setAttribute('fill','none'); path.setAttribute('stroke','var(--card)'); path.setAttribute('stroke-width','1');
      path.setAttribute('vector-effect','non-scaling-stroke'); group.appendChild(path);
    });
    svg.appendChild(group);
  }
  function update(s) {
    // The shipped renderer is SVG. Only a canvas fallback needs the same API;
    // SVG values come straight from the rendered source, avoiding polling races.
    var canvas=s.id==='chartDonut' && s.host.querySelector('canvas');
    if (canvas && s.canvasSource!==canvas && !s.pending) {
      s.pending=true;
      fetch('/api/stats',{cache:'no-store'}).then(function(r) { if(!r.ok) throw new Error(); return r.json(); }).then(function(data) {
        s.canvasRows=(data.by_platform || []).filter(function(p) { return p.n>0; }).map(function(p) { return {label:names[p.platform] || 'แพลตฟอร์มอื่น',key:p.platform,value:p.n}; });
        s.canvasSource=canvas;
      }).catch(function() {}).finally(function() { s.pending=false; if(s.canvasSource===canvas) update(s); });
    }
    var d=read(s); s.data=d;
    // The graphic is the image, the wrapper is a box. Announcing the same label
    // on both makes a screen reader read every chart twice, so the label lives
    // on the innermost drawable and the host only gets it when there is no svg.
    var svg = s.host.querySelector('svg');
    if (svg) {
      svg.setAttribute('role', 'img');
      svg.setAttribute('aria-label', d.label);
      s.host.removeAttribute('role');
      s.host.removeAttribute('aria-label');
    } else {
      s.host.setAttribute('role', 'img');
      s.host.setAttribute('aria-label', d.label);
    }
    table(s,d); annotations(s,d); safety(s,d);
  }
  function refresh() { states.forEach(update); }
  function schedule() { clearTimeout(timer); timer=setTimeout(refresh,300); }
  function owned(node) { return node.nodeType===1 && (node.matches('.viz-disclosure,.viz-annotations,.viz-canvas-legend,[data-viz-separators]') || node.closest('.viz-disclosure,.viz-annotations,.viz-canvas-legend,[data-viz-separators]')); }
  function mount() {
    document.documentElement.classList.add('viz-a11y');
    ['chartTrend','chartDonut','chartHours'].forEach(function (id) {
      var host=document.getElementById(id); if(!host) return;
      var card=host.closest('.card') || host.parentElement;
      var details=el('details','viz-disclosure'); details.dataset.vizFor=id;
      var summary=el('summary','','ดูข้อมูลเป็นตาราง');
      var panel=el('div','viz-table-scroll'); panel.tabIndex=0; panel.setAttribute('role','region');
      panel.setAttribute('aria-label','ตาราง'+({chartTrend:'แนวโน้ม',chartDonut:'แพลตฟอร์ม',chartHours:'รายชั่วโมง'}[id]));
      details.append(summary,panel);
      (host.closest('.card-body') || card).appendChild(details);
      host.classList.add('viz-chart-host');
      var s={id:id,host:host,card:card,panel:panel}; states.push(s);
      var observer=new MutationObserver(function (records) {
        if(records.some(function (r) {
          if(owned(r.target)) return false;
          if(r.type==='characterData') return !owned(r.target.parentElement);
          return Array.from(r.addedNodes).concat(Array.from(r.removedNodes)).some(function (node) { return !owned(node); });
        })) schedule();
      });
      observer.observe(card,{childList:true,subtree:true,characterData:true});
      s.observer=observer;
      if(window.ResizeObserver) { s.resize=new ResizeObserver(schedule); s.resize.observe(host); }
    });
    new MutationObserver(schedule).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
    window.addEventListener('resize',schedule,{passive:true});
    refresh();
  }
  window.__vizA11y={refresh:refresh};
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',mount,{once:true}); else mount();
})();
