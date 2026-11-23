/* SatunEcho · interactive SVG charts for the social-listening workspace.
 *
 * Loads after charts.js and registers extra renderers into the same registry, so
 * a page can mix the original components with these. No dependencies, no CDN.
 *
 * Interactivity is markup-driven, never per-element listeners:
 *   data-tip="line1\nline2"  -> shared floating tooltip follows the pointer
 *   data-act="day|term|..."  -> click dispatches a `sl:act` CustomEvent on window
 *   data-hover-group="g"     -> hovering one element dims its siblings in the group
 * The page owns behaviour (filters, drawers), the chart owns pixels.
 */
(function (global) {
  'use strict';
  if (!global.HarkenCharts) return;

  var HC = global.HarkenCharts;
  var C = {
    violet: 'var(--violet)', violetD: 'var(--violet-d)', cyan: 'var(--cyan)',
    ink: 'var(--ink)', ink2: 'var(--ink-2)', muted: 'var(--muted)', muted2: 'var(--muted-2)',
    line: 'var(--line)', line2: 'var(--line-2)',
    pos: 'var(--pos)', neu: 'var(--neu)', neg: 'var(--neg)'
  };
  var PLATCOL = {
    facebook: '#1877F2', fbfeed: '#0A57C4', threads: 'var(--ink)', tiktok: '#00F2EA', x: 'var(--ink)',
    x: 'var(--ink)', twitter: 'var(--ink)', instagram: '#E1306C', ig: '#E1306C',
    youtube: '#FF0000', pantip: '#7B2D8E', lemon8: '#FFC300', news: 'var(--muted)', other: 'var(--muted-2)'
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(v) {
    var n = Number(v || 0);
    return isFinite(n) ? n.toLocaleString('th-TH') : '0';
  }
  function wrap(w, h, inner, label) {
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" width="100%" height="' + h + '" ' +
      'preserveAspectRatio="xMidYMid meet" role="img" aria-label="' + esc(label) + '" ' +
      'style="display:block;overflow:visible">' + inner + '</svg>';
  }
  function empty(msg, w, h) {
    w = w || 320; h = h || 120;
    return wrap(w, h, '<text x="' + (w / 2) + '" y="' + (h / 2) + '" text-anchor="middle" ' +
      'font-size="12" fill="' + C.muted2 + '">' + esc(msg || 'ยังไม่มีข้อมูล') + '</text>', msg || '');
  }
  function tip(lines) {
    var t = lines.filter(Boolean).join('\n');
    return t ? ' data-tip="' + esc(t) + '"' : '';
  }

  /* Renderers return strings; observe newly mounted SVGs before the next paint.
   * A fresh SVG on every render also means daily/hourly toggles replay motion. */
  function motionWrap(w, h, inner, label, kind) {
    return wrap(w, h, inner, label).replace('<svg ', '<svg data-sl-motion="' + kind + '" ');
  }
  function motionAllowed(svg) {
    return !(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches) &&
      svg.getBoundingClientRect().width > 0;
  }
  function draw(path, host, delay, area, sweep, done) {
    var svg = path.ownerSVGElement;
    if (!svg || !motionAllowed(svg) || typeof path.getTotalLength !== 'function') return;
    var len = path.getTotalLength();
    if (!isFinite(len) || len <= 0) return;
    var original = path.getAttribute('stroke-dasharray');
    var opacity = area && area.getAttribute('opacity');
    var natural = opacity === null || !area ? 1 : Number(opacity);
    var start = global.performance.now() + delay;
    var duration = sweep ? 600 : 800;
    function restore() {
      if (sweep) {
        if (original === null) path.removeAttribute('stroke-dasharray');
        else path.setAttribute('stroke-dasharray', original);
      } else {
        path.style.strokeDashoffset = 0;
        path.style.removeProperty('stroke-dasharray');
        path.style.removeProperty('stroke-dashoffset');
      }
      if (area) {
        area.style.removeProperty('opacity');
        if (opacity === null) area.removeAttribute('opacity');
        else area.setAttribute('opacity', opacity);
      }
      if (done) done();
    }
    var visible = sweep && original ? parseFloat(original) : len;
    if (sweep) path.setAttribute('stroke-dasharray', '0 ' + len);
    else {
      path.style.strokeDasharray = len;
      path.style.strokeDashoffset = len;
    }
    if (area) area.style.opacity = 0;
    function frame(now) {
      if (!document.body.contains(host) || !host.contains(path) || !motionAllowed(svg)) {
        restore();
        return;
      }
      var t = Math.max(0, Math.min(1, (now - start) / duration));
      var eased = 1 - Math.pow(1 - t, 3);
      if (sweep) path.setAttribute('stroke-dasharray', (visible * eased) + ' ' + (len - visible * eased));
      else path.style.strokeDashoffset = len * (1 - eased);
      if (area) area.style.opacity = natural * eased;
      if (t < 1) global.requestAnimationFrame(frame);
      else restore();
    }
    global.requestAnimationFrame(frame);
  }
  var sweepId = 0;
  /* These slices are filled wedges, not stroked arcs. Sweep a temporary ring
   * mask so their original geometry, colours and white borders stay intact. */
  function sweepArc(arc, host) {
    if (typeof arc.getTotalLength !== 'function') return;
    var svg = arc.ownerSVGElement, ns = 'http://www.w3.org/2000/svg';
    var mask = document.createElementNS(ns, 'mask');
    var circle = document.createElementNS(ns, 'circle');
    var id = 'slSweep' + (++sweepId);
    var len = 2 * Math.PI * 70.5;
    mask.setAttribute('id', id);
    mask.setAttribute('maskUnits', 'userSpaceOnUse');
    mask.setAttribute('x', '0'); mask.setAttribute('y', '0');
    mask.setAttribute('width', '220'); mask.setAttribute('height', '220');
    circle.setAttribute('cx', '110'); circle.setAttribute('cy', '110');
    circle.setAttribute('r', '70.5');
    circle.setAttribute('fill', 'none'); circle.setAttribute('stroke', '#fff');
    circle.setAttribute('stroke-width', '35');
    circle.setAttribute('transform', 'rotate(' + arc.getAttribute('data-sl-start') + ' 110 110)');
    var visible = len * Number(arc.getAttribute('data-sl-frac'));
    circle.setAttribute('stroke-dasharray', visible + ' ' + (len - visible));
    if (typeof circle.getTotalLength !== 'function') return;
    mask.appendChild(circle); svg.appendChild(mask);
    arc.setAttribute('mask', 'url(#' + id + ')');
    draw(circle, host, 0, null, true, function () {
      arc.removeAttribute('mask');
      if (mask.parentNode) mask.parentNode.removeChild(mask);
    });
  }
  function animateChart(svg) {
    if (!motionAllowed(svg)) return;
    var host = svg.parentNode;
    if (svg.getAttribute('data-sl-motion') === 'line') {
      var paths = svg.querySelectorAll('path[fill="none"]');
      var area = svg.querySelector('path[fill="url(#slFill)"]');
      for (var i = 0; i < paths.length; i++) {
        draw(paths[i], host, i * 90, i === paths.length - 1 ? area : null, false);
      }
    } else {
      var arcs = svg.querySelectorAll('[data-sl-frac]');
      for (var j = 0; j < arcs.length; j++) sweepArc(arcs[j], host);
    }
  }
  if (global.MutationObserver && global.requestAnimationFrame) {
    new global.MutationObserver(function (records) {
      records.forEach(function (record) {
        for (var i = 0; i < record.addedNodes.length; i++) {
          var node = record.addedNodes[i];
          if (node.nodeType !== 1) continue;
          if (node.matches('svg[data-sl-motion]')) animateChart(node);
          var charts = node.querySelectorAll('svg[data-sl-motion]');
          for (var j = 0; j < charts.length; j++) animateChart(charts[j]);
        }
      });
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  /* ── 1. trend line with crosshair ───────────────────────────
   * d = {labels, cur, prev, iso}
   * opts.dayKey  -> data-act="day" payload attribute name (default 'day') */
  HC.register('slLine', {
    label: 'แนวโน้มการพูดถึง',
    render: function (d, opts) {
      if (!d || !d.labels || !d.labels.length) return empty('ยังไม่มีโพสต์ในช่วงนี้');
      // draw at the container width so 1 SVG unit = 1 CSS px; otherwise a 900-unit
      // viewBox scales the axis text down to ~5px on a phone and kills its contrast
      var W = Math.max(320, (opts && opts.width) || 900), H = 260, X0 = 44, XR = W - 16, Y0 = 24, Y1 = H - 36;
      var cur = d.cur || [], prev = d.prev || [], iso = d.iso || [];
      var rawMax = Math.max(1, Math.max.apply(null, cur.concat(prev)));
      var stepN = rawMax <= 6 ? rawMax : 4;
      var tick = Math.ceil(rawMax / stepN), max = tick * stepN;
      var n = d.labels.length;
      var xx = function (i) { return n === 1 ? (X0 + XR) / 2 : X0 + i * ((XR - X0) / (n - 1)); };
      var yy = function (v) { return Y1 - (v / max) * (Y1 - Y0); };
      var line = function (a) {
        return a.map(function (v, i) { return (i ? 'L' : 'M') + xx(i).toFixed(1) + ' ' + yy(v).toFixed(1); }).join(' ');
      };
      var area = line(cur) + ' L' + xx(n - 1).toFixed(1) + ' ' + Y1 + ' L' + xx(0).toFixed(1) + ' ' + Y1 + ' Z';
      var g = '', i, gy, val;
      for (i = 0; i <= stepN; i++) {
        gy = Y0 + (Y1 - Y0) * i / stepN;
        val = Math.round(max * (1 - i / stepN));
        g += '<line x1="' + X0 + '" y1="' + gy.toFixed(1) + '" x2="' + XR + '" y2="' + gy.toFixed(1) +
          '" stroke="' + C.line + '" stroke-width="1"/>' +
          '<text x="' + (X0 - 9) + '" y="' + (gy + 4).toFixed(1) + '" text-anchor="end" font-size="12" fill="' +
          'var(--ink-2)' + '">' + num(val) + '</text>';
      }
      var every = n > 12 ? Math.ceil(n / 8) : 1;
      var xl = d.labels.map(function (l, k) {
        return k % every ? '' : '<text x="' + xx(k).toFixed(1) + '" y="' + (Y1 + 19) + '" text-anchor="middle" ' +
          'font-size="12" fill="var(--ink-2)">' + esc(l) + '</text>';
      }).join('');
      var cols = '';
      var pts = cur.map(function (v, k) {
        cols += '<rect x="' + (xx(k) - (n > 1 ? (XR - X0) / (n - 1) / 2 : 40)).toFixed(1) + '" y="' + Y0 +
          '" width="' + (n > 1 ? (XR - X0) / (n - 1) : 80).toFixed(1) + '" height="' + (Y1 - Y0) +
          '" fill="transparent" data-act="day" data-day="' + esc(iso[k] || '') + '" data-idx="' + k + '" ' +
          'data-hover-group="trend" data-hover-idx="' + k + '"' +
          tip([d.labels[k], num(v) + ' โพสต์', 'ช่วงก่อนหน้า ' + num(prev[k] || 0)]) + '/>' +
          '<circle cx="' + xx(k).toFixed(1) + '" cy="' + yy(v).toFixed(1) + '" r="3.4" fill="' + C.violet +
          '" stroke="#fff" stroke-width="1.4" opacity="' + (n > 30 ? '.55' : '1') + '"/>';
        return '';
      }).join('');
      var peakIdx = cur.indexOf(Math.max.apply(null, cur));
      var peak = Math.max.apply(null, cur) > 0
        ? '<circle cx="' + xx(peakIdx).toFixed(1) + '" cy="' + yy(cur[peakIdx]).toFixed(1) +
          '" r="10" fill="rgba(255,107,107,.14)" stroke="var(--coral)" stroke-width="1.3"/>' : '';
      var inner = '<defs><linearGradient id="slFill" x1="0" y1="0" x2="0" y2="1">' +
        '<stop offset="0" stop-color="#6D28D9" stop-opacity=".24"/>' +
        '<stop offset="1" stop-color="#6D28D9" stop-opacity="0"/></linearGradient></defs>' +
        g + xl +
        '<path d="' + area + '" fill="url(#slFill)"/>' +
        (prev.some(function (v) { return v > 0; })
          ? '<path d="' + line(prev) + '" fill="none" stroke="' + C.cyan + '" stroke-width="1.8" ' +
            'stroke-dasharray="5 4" stroke-linecap="round"/>' : '') +
        '<path d="' + line(cur) + '" fill="none" stroke="' + C.violet + '" stroke-width="2.6" ' +
        'stroke-linecap="round" stroke-linejoin="round"/>' +
        peak + cols + pts;
      return motionWrap(W, H, inner, 'แนวโน้มการพูดถึง ' + n + ' ช่วง', 'line');
    }
  });

  /* ── 2. donut with hover-expand and live centre ─────────── */
  HC.register('slDonut', {
    label: 'สัดส่วนแพลตฟอร์ม',
    render: function (items, opts) {
      items = (items || []).filter(function (x) { return (x.n || 0) > 0; });
      if (!items.length) return empty('ยังไม่มีข้อมูลแพลตฟอร์ม');
      var total = items.reduce(function (a, b) { return a + (b.n || 0); }, 0);
      var S = 220, R = 86, r = 55, cx = S / 2, cy = S / 2;
      var centre = '<text x="' + cx + '" y="' + (cy - 2) + '" text-anchor="middle" font-size="22" ' +
        'font-weight="700" fill="' + C.ink + '">' + num(total) + '</text>' +
        '<text x="' + cx + '" y="' + (cy + 16) + '" text-anchor="middle" font-size="12" fill="' +
        'var(--ink-2)' + '">โพสต์</text>';
      /* one platform = one full ring; a single 360° arc collapses to nothing */
      if (items.length === 1) {
        var only = items[0];
        var col0 = only.color || PLATCOL[only.platform] || C.violet;
        return '<div class="sl-donut"><div class="sl-donut-svg">' + motionWrap(S, S,
          '<circle data-sl-start="-90" data-sl-frac="1" cx="' + cx + '" cy="' + cy + '" r="' + ((R + r) / 2) + '" fill="none" stroke="' +
          col0 + '" stroke-width="' + (R - r) + '" data-act="platform" data-platform="' +
          esc(only.platform || '') + '"' + tip([only.label || only.platform,
            num(only.n) + ' โพสต์', '100%']) + '/>' + centre, 'สัดส่วนแพลตฟอร์ม', 'donut') +
          '</div><div class="sl-donut-legend"><button type="button" class="rankrow" data-act="platform" ' +
          'data-platform="' + esc(only.platform || '') + '"><span class="no">' +
          '<i class="sl-swatch" style="background:' + col0 + '"></i></span>' +
          '<span class="rt">' + esc(only.label || only.platform) + '</span>' +
          '<span class="rv">' + num(only.n) + ' · 100%</span></button></div></div>';
      }
      var a0 = -Math.PI / 2, out = '', legend = '';
      items.forEach(function (it, k) {
        var frac = (it.n || 0) / total, a1 = a0 + frac * Math.PI * 2;
        var big = (a1 - a0) > Math.PI ? 1 : 0;
        var p = function (ang, rad) {
          return (cx + Math.cos(ang) * rad).toFixed(2) + ' ' + (cy + Math.sin(ang) * rad).toFixed(2);
        };
        var col = it.color || PLATCOL[it.platform] || C.violet;
        out += '<path d="M' + p(a0, R) + ' A' + R + ' ' + R + ' 0 ' + big + ' 1 ' + p(a1, R) +
          ' L' + p(a1, r) + ' A' + r + ' ' + r + ' 0 ' + big + ' 0 ' + p(a0, r) + ' Z" ' +
          'fill="' + col + '" stroke="#fff" stroke-width="1.6" class="sl-arc" ' +
          'data-sl-start="' + (a0 * 180 / Math.PI) + '" data-sl-frac="' + frac + '" ' +
          'data-act="platform" data-platform="' + esc(it.platform || '') + '" data-hover-group="donut" ' +
          tip([it.label || it.platform, num(it.n) + ' โพสต์', Math.round(frac * 100) + '%']) + '/>';
        legend += '<button type="button" class="rankrow" data-act="platform" data-platform="' +
          esc(it.platform || '') + '"><span class="no"><i style="display:inline-block;width:9px;height:9px;' +
          'border-radius:3px;background:' + col + '"></i></span><span class="rt">' +
          esc(it.label || it.platform) + '</span><span class="rv">' + num(it.n) + ' · ' +
          Math.round(frac * 100) + '%</span></button>';
        a0 = a1;
      });
      var svg = motionWrap(S, S, out + centre, 'สัดส่วนแพลตฟอร์ม', 'donut');
      return '<div class="sl-donut"><div class="sl-donut-svg">' + svg +
        '</div><div class="sl-donut-legend">' + legend + '</div></div>';
    }
  });

  /* ── 3. stacked sentiment per day ───────────────────────── */
  HC.register('slStackSent', {
    label: 'อารมณ์รายวัน',
    render: function (rows, opts) {
      rows = rows || [];
      if (!rows.length) return empty('ยังไม่มีข้อมูลอารมณ์');
      var W = 900, H = 200, X0 = 34, XR = W - 12, Y0 = 16, Y1 = H - 30;
      var rawMax = Math.max(1, Math.max.apply(null, rows.map(function (r) { return r.pos + r.neu + r.neg; })));
      // integer ticks: rounding 0/0.5/1 to labels printed "1" twice on small zones
      var stepN = rawMax <= 5 ? rawMax : 4;
      var tick = Math.ceil(rawMax / stepN);
      var max = tick * stepN;
      var bw = Math.max(4, Math.min(30, (XR - X0) / rows.length - 5));
      var gap = ((XR - X0) - bw * rows.length) / Math.max(1, rows.length - 1);
      var out = '';
      for (var gi = 0; gi <= stepN; gi++) {
        var y = Y1 - (gi / stepN) * (Y1 - Y0);
        out += '<line x1="' + X0 + '" y1="' + y.toFixed(1) + '" x2="' + XR + '" y2="' + y.toFixed(1) +
          '" stroke="' + C.line + '"/>' +
          '<text x="' + (X0 - 7) + '" y="' + (y + 3.5).toFixed(1) + '" text-anchor="end" ' +
          'font-size="12" fill="var(--ink-2)">' + num(Math.round(max * (1 - gi / stepN))) + '</text>';
      }
      rows.forEach(function (r, i) {
        var x = X0 + i * (bw + gap), y = Y1, h, tot = r.pos + r.neu + r.neg;
        [['neg', C.neg], ['neu', C.neu], ['pos', C.pos]].forEach(function (k) {
          h = (r[k[0]] / max) * (Y1 - Y0);
          if (h <= 0) return;
          y -= h;
          out += '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) +
            '" height="' + h.toFixed(1) + '" rx="2.5" fill="' + k[1] + '" data-hover-group="stack" ' +
            tip([r.label, 'บวก ' + num(r.pos) + ' · กลาง ' + num(r.neu) + ' · ลบ ' + num(r.neg),
                 'รวม ' + num(tot) + ' โพสต์']) + '/>';
        });
        if (i % (rows.length > 16 ? 3 : 1) === 0) {
          out += '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (Y1 + 15) + '" text-anchor="middle" ' +
            'font-size="12" fill="var(--ink-2)">' + esc(r.label) + '</text>';
        }
      });
      return wrap(W, H, out, 'อารมณ์รายวัน');
    }
  });

  /* ── 4. interactive horizontal bars ─────────────────────── */
  HC.register('slBars', {
    label: 'อันดับ',
    render: function (items, opts) {
      opts = opts || {};
      items = (items || []).filter(function (x) { return (x.value || 0) > 0; }).slice(0, opts.limit || 8);
      if (!items.length) return empty(opts.empty || 'ยังไม่มีข้อมูล');
      var max = Math.max.apply(null, items.map(function (x) { return x.value; }));
      return '<div style="display:flex;flex-direction:column;gap:2px">' + items.map(function (x) {
        return '<button type="button" class="rankrow" data-act="' + esc(opts.act || '') + '" ' +
          'data-key="' + esc(x.key || '') + '"' + tip([x.label, num(x.value) + (opts.unit || '')]) + '>' +
          '<span class="no">' + esc(x.badge || '') + '</span>' +
          '<span class="rt">' + esc(x.label) + '</span>' +
          '<span class="rv">' + num(x.value) + '</span>' +
          '<span class="bar"><i style="width:' + Math.round(x.value / max * 100) + '%;' +
          (x.color ? 'background:' + x.color : '') + '"></i></span></button>';
      }).join('') + '</div>';
    }
  });

  /* ── 5. sparkline for KPI cards ─────────────────────────── */
  HC.register('slSpark', {
    label: 'แนวโน้มขนาดย่อ',
    render: function (values, opts) {
      values = (values || []).map(Number);
      opts = opts || {};
      if (values.length < 2) return '';
      var W = 160, H = opts.height || 26, max = Math.max.apply(null, values) || 1;
      var min = Math.min.apply(null, values);
      var span = Math.max(1, max - min);
      var xx = function (i) { return (i / (values.length - 1)) * W; };
      var yy = function (v) { return H - 2 - ((v - min) / span) * (H - 5); };
      var d = values.map(function (v, i) { return (i ? 'L' : 'M') + xx(i).toFixed(1) + ' ' + yy(v).toFixed(1); }).join(' ');
      var col = opts.color || C.violet;
      return wrap(W, H, '<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.8" ' +
        'stroke-linecap="round" stroke-linejoin="round"/>' +
        '<circle cx="' + xx(values.length - 1).toFixed(1) + '" cy="' + yy(values[values.length - 1]).toFixed(1) +
        '" r="2.4" fill="' + col + '"/>', 'sparkline');
    }
  });

  /* ── 6. one-row sentiment mix ───────────────────────────── */
  HC.register('slMix', {
    label: 'องค์ประกอบอารมณ์',
    render: function (mix, opts) {
      mix = mix || {};
      var parts = [['pos', C.pos], ['neu', C.neu], ['neg', C.neg]].map(function (k) {
        return { key: k[0], n: mix[k[0]] || 0, color: k[1] };
      });
      var tot = parts.reduce(function (a, b) { return a + b.n; }, 0);
      if (!tot) return empty('ยังไม่มีการจำแนกอารมณ์');
      var w = 100, x = 0, out = '';
      parts.forEach(function (p) {
        var frac = p.n / tot * 100;
        if (frac > 0) {
          out += '<rect x="' + x + '%" y="0" width="' + frac + '%" height="14" fill="' + p.color +
            '" data-hover-group="mix"' + tip([p.key === 'pos' ? 'บวก' : p.key === 'neu' ? 'กลาง' : 'ลบ',
              num(p.n) + ' · ' + Math.round(frac) + '%']) + '/>';
        }
        x += frac;
      });
      return '<div style="display:flex;flex-direction:column;gap:7px">' +
        '<svg viewBox="0 0 ' + w + ' 14" width="100%" height="14" preserveAspectRatio="none" ' +
        'style="display:block;border-radius:99px;overflow:hidden">' + out + '</svg>' +
        '<div style="display:flex;gap:12px;font-size:11.5px;color:var(--muted)">' +
        parts.map(function (p) {
          return '<span style="display:inline-flex;align-items:center;gap:5px">' +
            '<i style="width:8px;height:8px;border-radius:2px;background:' + p.color + '"></i>' +
            (p.key === 'pos' ? 'บวก' : p.key === 'neu' ? 'กลาง' : 'ลบ') +
            ' <b class="num">' + num(p.n) + '</b></span>';
        }).join('') + '</div></div>';
    }
  });

  /* ── 7. hour profile column chart ───────────────────────── */
  HC.register('slHours', {
    label: 'ชั่วโมงที่คึกคัก',
    render: function (profile, opts) {
      var hours = (profile && profile.hours) || [], counts = (profile && profile.counts) || [];
      if (!counts.length) return empty('ยังไม่มีข้อมูลเวลา');
      var W = 900, H = 170, X0 = 26, XR = W - 10, Y0 = 12, Y1 = H - 26;
      var max = Math.max(1, Math.max.apply(null, counts));
      var bw = (XR - X0) / counts.length - 2.5;
      var peak = counts.indexOf(max);
      var out = '';
      counts.forEach(function (v, i) {
        var h = (v / max) * (Y1 - Y0);
        var x = X0 + i * ((XR - X0) / counts.length);
        out += '<rect x="' + x.toFixed(1) + '" y="' + (Y1 - h).toFixed(1) + '" width="' + bw.toFixed(1) +
          '" height="' + Math.max(v > 0 ? 2 : 0.5, h).toFixed(1) + '" rx="2.5" fill="' +
          (i === peak && v > 0 ? C.violet : 'rgba(109,40,217,.32)') + '" data-hover-group="hours" ' +
          tip([hours[i] + ':00', num(v) + ' โพสต์']) + '/>';
        if (i % 3 === 0) {
          out += '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (Y1 + 14) + '" text-anchor="middle" ' +
            'font-size="12" fill="var(--ink-2)">' + esc(hours[i]) + '</text>';
        }
      });
      return wrap(W, H, out, 'ชั่วโมงที่คึกคัก');
    }
  });

  /* ── shared tooltip + click routing ────────────────────── */
  var tipEl = null;
  function ensureTip() {
    if (tipEl && document.body.contains(tipEl)) return tipEl;
    tipEl = document.createElement('div');
    tipEl.className = 'sl-tip';
    document.body.appendChild(tipEl);
    return tipEl;
  }
  document.addEventListener('mousemove', function (e) {
    var t = e.target.closest && e.target.closest('[data-tip]');
    var box = ensureTip();
    if (!t) { box.classList.remove('on'); return; }
    box.textContent = t.getAttribute('data-tip');
    box.classList.add('on');
    box.style.left = e.clientX + 'px';
    box.style.top = e.clientY + 'px';
  }, { passive: true });
  document.addEventListener('mouseleave', function () {
    if (tipEl) tipEl.classList.remove('on');
  });
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-act]');
    if (!t) return;
    var act = t.getAttribute('data-act');
    if (!act) return;
    var detail = { act: act, el: t };
    ['day', 'platform', 'key', 'idx'].forEach(function (k) {
      if (t.dataset[k] != null) detail[k] = t.dataset[k];
    });
    window.dispatchEvent(new CustomEvent('sl:act', { detail: detail }));
  });
  document.addEventListener('mouseover', function (e) {
    var g = e.target.closest && e.target.closest('[data-hover-group]');
    var groups = document.querySelectorAll('[data-hover-group]');
    for (var i = 0; i < groups.length; i++) groups[i].style.opacity = '';
    if (!g) return;
    var name = g.getAttribute('data-hover-group');
    var same = document.querySelectorAll('[data-hover-group="' + name + '"]');
    for (var j = 0; j < same.length; j++) if (same[j] !== g) same[j].style.opacity = '.55';
    g.style.opacity = '1';
  }, { passive: true });

  global.SLCharts = { colors: PLATCOL };
})(window);
