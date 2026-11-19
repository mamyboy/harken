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
    facebook: '#1877F2', fbfeed: '#0A57C4', threads: '#111111', tiktok: '#00F2EA', x: '#0F1419',
    x: '#0F1419', twitter: '#0F1419', instagram: '#E1306C', ig: '#E1306C',
    youtube: '#FF0000', pantip: '#7B2D8E', lemon8: '#FFC300', news: '#6B7A99', other: '#8C99B4'
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

  /* ── 1. trend line with crosshair ───────────────────────────
   * d = {labels, cur, prev, iso}
   * opts.dayKey  -> data-act="day" payload attribute name (default 'day') */
  HC.register('slLine', {
    label: 'แนวโน้มการพูดถึง',
    render: function (d, opts) {
      if (!d || !d.labels || !d.labels.length) return empty('ยังไม่มีโพสต์ในช่วงนี้');
      var W = 900, H = 260, X0 = 44, XR = W - 16, Y0 = 24, Y1 = H - 36;
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
          '<text x="' + (X0 - 9) + '" y="' + (gy + 4).toFixed(1) + '" text-anchor="end" font-size="10.5" fill="' +
          C.muted2 + '">' + num(val) + '</text>';
      }
      var every = n > 12 ? Math.ceil(n / 8) : 1;
      var xl = d.labels.map(function (l, k) {
        return k % every ? '' : '<text x="' + xx(k).toFixed(1) + '" y="' + (Y1 + 19) + '" text-anchor="middle" ' +
          'font-size="10.5" fill="' + C.muted2 + '">' + esc(l) + '</text>';
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
      return wrap(W, H, inner, 'แนวโน้มการพูดถึง ' + n + ' ช่วง');
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
        '<text x="' + cx + '" y="' + (cy + 16) + '" text-anchor="middle" font-size="11" fill="' +
        C.muted2 + '">โพสต์</text>';
      /* one platform = one full ring; a single 360° arc collapses to nothing */
      if (items.length === 1) {
        var only = items[0];
        var col0 = only.color || PLATCOL[only.platform] || C.violet;
        return '<div class="sl-donut"><div class="sl-donut-svg">' + wrap(S, S,
          '<circle cx="' + cx + '" cy="' + cy + '" r="' + ((R + r) / 2) + '" fill="none" stroke="' +
          col0 + '" stroke-width="' + (R - r) + '" data-act="platform" data-platform="' +
          esc(only.platform || '') + '"' + tip([only.label || only.platform,
            num(only.n) + ' โพสต์', '100%']) + '/>' + centre, 'สัดส่วนแพลตฟอร์ม') +
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
          'data-act="platform" data-platform="' + esc(it.platform || '') + '" data-hover-group="donut" ' +
          tip([it.label || it.platform, num(it.n) + ' โพสต์', Math.round(frac * 100) + '%']) + '/>';
        legend += '<button type="button" class="rankrow" data-act="platform" data-platform="' +
          esc(it.platform || '') + '"><span class="no"><i style="display:inline-block;width:9px;height:9px;' +
          'border-radius:3px;background:' + col + '"></i></span><span class="rt">' +
          esc(it.label || it.platform) + '</span><span class="rv">' + num(it.n) + ' · ' +
          Math.round(frac * 100) + '%</span></button>';
        a0 = a1;
      });
      var svg = wrap(S, S, out + centre, 'สัดส่วนแพลตฟอร์ม');
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
          'font-size="10" fill="' + C.muted2 + '">' + num(Math.round(max * (1 - gi / stepN))) + '</text>';
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
            'font-size="9.5" fill="' + C.muted2 + '">' + esc(r.label) + '</text>';
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
            'font-size="9.5" fill="' + C.muted2 + '">' + esc(hours[i]) + '</text>';
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
