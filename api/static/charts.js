/* Harken chart components — hand-rolled SVG, no dependencies, no CDN.
 *
 * Every chart is a pure function (data, opts) -> SVG string, registered in a
 * small registry so a new dimension can be added with one call:
 *
 *   HarkenCharts.register('myChart', {render(data, opts){ return '<svg…'; }});
 *   HarkenCharts.render('myChart', '#slot', data);
 *
 * Themes come from the page's CSS variables (var(--violet), var(--pos) …), so
 * the charts follow the design system instead of hard-coding colours.
 */
(function (global) {
  'use strict';

  var registry = {};
  var V = {
    ink: 'var(--ink)', ink2: 'var(--ink-2)', muted: 'var(--muted)', muted2: 'var(--muted-2)',
    line: 'var(--line)', violet: 'var(--violet)', violetD: 'var(--violet-d)',
    cyan: 'var(--cyan)', pos: 'var(--pos)', neu: 'var(--neu)', neg: 'var(--neg)',
    card: 'var(--card)'
  };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function num(v) {
    var n = Number(v || 0);
    if (!isFinite(n)) return '0';
    return n.toLocaleString('th-TH');
  }
  function svgWrap(w, h, inner, label) {
    return '<svg viewBox="0 0 ' + w + ' ' + h + '" width="100%" height="' + h + '" ' +
      'preserveAspectRatio="xMidYMid meet" role="img" aria-label="' + esc(label) + '" ' +
      'style="display:block;overflow:visible">' + inner + '</svg>';
  }
  function empty(msg, w, h) {
    w = w || 320; h = h || 120;
    return svgWrap(w, h,
      '<text x="' + (w / 2) + '" y="' + (h / 2) + '" text-anchor="middle" ' +
      'font-size="12" fill="' + V.muted2 + '">' + esc(msg || 'ยังไม่มีข้อมูล') + '</text>',
      msg || 'ยังไม่มีข้อมูล');
  }
  /* accent ramp for intensity: violet at increasing opacity */
  function ramp(t) {
    t = Math.max(0, Math.min(1, t));
    return 'rgba(109,40,217,' + (0.08 + 0.82 * t).toFixed(3) + ')';
  }

  /* ── 1. heatmap: weekday x hour ───────────────────────────── */
  registry.heatmap = {
    label: 'ความหนาแน่นโพสต์ตามวันและชั่วโมง',
    render: function (d) {
      if (!d || !d.rows || !d.cols) return empty();
      var cells = d.cells || [], max = d.max || 0;
      if (!cells.length) return empty('ยังไม่มีโพสต์ในช่วงนี้');
      var cw = 18, ch = 25, gap = 3.5, left = 34, top = 16;
      var w = left + d.cols.length * (cw + gap), h = top + d.rows.length * (ch + gap) + 46;
      var map = {};
      cells.forEach(function (c) { map[c.r + ':' + c.c] = c.n; });
      var out = '';
      // hour ticks
      d.cols.forEach(function (col, i) {
        if (i % 3) return;
        out += '<text x="' + (left + i * (cw + gap) + cw / 2) + '" y="' + (top - 5) +
          '" font-size="9" text-anchor="middle" fill="' + V.muted2 + '">' + esc(col) + '</text>';
      });
      d.rows.forEach(function (row, r) {
        out += '<text x="' + (left - 7) + '" y="' + (top + r * (ch + gap) + ch / 2 + 3.5) +
          '" font-size="10" text-anchor="end" fill="' + V.muted + '">' + esc(row) + '.</text>';
        d.cols.forEach(function (col, c) {
          var n = map[r + ':' + c] || 0;
          var fill = n ? ramp(max ? n / max : 0) : 'var(--line)';
          out += '<rect x="' + (left + c * (cw + gap)) + '" y="' + (top + r * (ch + gap)) +
            '" width="' + cw + '" height="' + ch + '" rx="3" fill="' + fill + '">' +
            '<title>' + esc(row + ' ' + col + ':00 — ' + n + ' โพสต์') + '</title></rect>';
        });
      });
      // legend
      var ly = top + d.rows.length * (ch + gap) + 14;
      out += '<text x="' + left + '" y="' + ly + '" font-size="9.5" fill="' + V.muted2 + '">น้อย</text>';
      for (var i = 0; i < 5; i++) {
        out += '<rect x="' + (left + 26 + i * 14) + '" y="' + (ly - 8) + '" width="11" height="11" rx="2" ' +
          'fill="' + ramp((i + 1) / 5) + '"></rect>';
      }
      out += '<text x="' + (left + 26 + 5 * 14 + 3) + '" y="' + ly + '" font-size="9.5" fill="' +
        V.muted2 + '">มาก (' + num(max) + ')</text>';
      return svgWrap(w, h, out, 'ฮีตแมปโพสต์ตามวันและชั่วโมง สูงสุด ' + max + ' โพสต์');
    }
  };

  /* ── 2. stacked bars: posts per day per platform ──────────── */
  registry.stackedBars = {
    label: 'โพสต์รายวันแยกแพลตฟอร์ม',
    render: function (d) {
      if (!d || !d.days || !d.days.length) return empty();
      var series = (d.series || []).filter(function (s) { return s.values && s.values.length; });
      if (!series.length) return empty('ยังไม่มีโพสต์ในช่วงนี้');
      var sums = d.days.map(function (_, i) {
        return series.reduce(function (a, s) { return a + (s.values[i] || 0); }, 0);
      });
      var max = Math.max.apply(null, sums.concat([1]));
      var w = 420, h = 190, left = 26, bottom = 34, top = 8;
      var plotW = w - left - 6, plotH = h - bottom - top;
      var bw = Math.max(6, Math.min(26, plotW / d.days.length - 8));
      var out = '';
      [0, 0.5, 1].forEach(function (f) {
        var y = top + plotH * (1 - f);
        out += '<line x1="' + left + '" y1="' + y + '" x2="' + (w - 6) + '" y2="' + y +
          '" stroke="' + V.line + '" stroke-dasharray="' + (f ? '2 3' : '0') + '"></line>';
        out += '<text x="' + (left - 5) + '" y="' + (y + 3.5) + '" font-size="9" text-anchor="end" fill="' +
          V.muted2 + '">' + Math.round(max * f) + '</text>';
      });
      d.days.forEach(function (day, i) {
        var x = left + (plotW / d.days.length) * i + (plotW / d.days.length - bw) / 2;
        var acc = 0;
        series.forEach(function (s) {
          var v = s.values[i] || 0;
          if (!v) return;
          var hh = plotH * (v / max);
          acc += hh;
          out += '<rect x="' + x + '" y="' + (top + plotH - acc) + '" width="' + bw +
            '" height="' + hh + '" fill="' + (s.color || V.violet) + '" rx="2">' +
            '<title>' + esc(day + ' · ' + (s.label || s.platform) + ': ' + v) + '</title></rect>';
        });
        if (d.days.length <= 10 || i % 2 === 0) {
          out += '<text x="' + (x + bw / 2) + '" y="' + (h - bottom + 14) +
            '" font-size="9" text-anchor="middle" fill="' + V.muted2 + '">' + esc(day) + '</text>';
        }
      });
      // legend
      var lx = left;
      series.forEach(function (s) {
        out += '<rect x="' + lx + '" y="' + (h - 12) + '" width="8" height="8" rx="2" fill="' +
          (s.color || V.violet) + '"></rect>';
        out += '<text x="' + (lx + 12) + '" y="' + (h - 5) + '" font-size="9.5" fill="' + V.muted + '">' +
          esc(s.label || s.platform) + '</text>';
        lx += 18 + (String(s.label || s.platform).length * 5.2);
      });
      return svgWrap(w, h, out, 'จำนวนโพสต์รายวันแยกตามแพลตฟอร์ม');
    }
  };

  /* ── 3. donut: platform share ─────────────────────────────── */
  registry.donut = {
    label: 'สัดส่วนโพสต์ตามแพลตฟอร์ม',
    render: function (d, opts) {
      var items = (d || []).filter(function (x) { return x.n > 0; });
      if (!items.length) return empty();
      var total = items.reduce(function (a, x) { return a + x.n; }, 0);
      var w = 330, h = 176, cx = 82, cy = 88, r = 63, ir = 40;
      var colors = ['var(--violet)', 'var(--cyan)', 'var(--pos)', 'var(--neu)', 'var(--neg)', '#8C99B4'];
      var ang = -Math.PI / 2, out = '';
      items.forEach(function (it, i) {
        var a2 = ang + (it.n / total) * Math.PI * 2;
        var large = (a2 - ang) > Math.PI ? 1 : 0;
        var x1 = cx + r * Math.cos(ang), y1 = cy + r * Math.sin(ang);
        var x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
        var x3 = cx + ir * Math.cos(a2), y3 = cy + ir * Math.sin(a2);
        var x4 = cx + ir * Math.cos(ang), y4 = cy + ir * Math.sin(ang);
        var col = (opts && opts.colors && opts.colors[i]) || colors[i % colors.length];
        out += '<path d="M' + x1 + ' ' + y1 + 'A' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x2 + ' ' + y2 +
          'L' + x3 + ' ' + y3 + 'A' + ir + ' ' + ir + ' 0 ' + large + ' 0 ' + x4 + ' ' + y4 + 'Z" ' +
          'fill="' + col + '"><title>' + esc((it.label || it.platform) + ': ' + it.n + ' (' +
          Math.round(it.n / total * 100) + '%)') + '</title></path>';
        ang = a2;
      });
      out += '<text x="' + cx + '" y="' + (cy - 1) + '" font-size="19" font-weight="700" ' +
        'text-anchor="middle" fill="' + V.ink + '">' + num(total) + '</text>';
      out += '<text x="' + cx + '" y="' + (cy + 13) + '" font-size="9.5" text-anchor="middle" fill="' +
        V.muted2 + '">โพสต์</text>';
      var ly = 40;
      items.forEach(function (it, i) {
        var col = (opts && opts.colors && opts.colors[i]) || colors[i % colors.length];
        out += '<rect x="162" y="' + (ly - 7) + '" width="8" height="8" rx="2" fill="' + col + '"></rect>';
        out += '<text x="175" y="' + ly + '" font-size="10.5" fill="' + V.ink2 + '">' +
          esc(String(it.label || it.platform).slice(0, 14)) + '</text>';
        out += '<text x="' + (w - 4) + '" y="' + ly + '" font-size="10" text-anchor="end" fill="' +
          V.muted + '">' + Math.round(it.n / total * 100) + '%</text>';
        ly += 20;
      });
      return svgWrap(w, h, out, 'สัดส่วนโพสต์ตามแพลตฟอร์ม รวม ' + total + ' โพสต์');
    }
  };

  /* ── 4. scatter: authors, posts vs likes ──────────────────── */
  registry.scatter = {
    label: 'ผู้โพสต์: จำนวนโพสต์กับไลก์',
    render: function (d) {
      var items = (d || []).filter(function (a) { return a.posts > 0; });
      if (!items.length) return empty();
      var w = 430, h = 218, left = 48, bottom = 34, top = 18, right = 12;
      var pw = w - left - right, ph = h - bottom - top;
      var maxX = Math.max.apply(null, items.map(function (a) { return a.posts; })) || 1;
      var maxY = Math.max.apply(null, items.map(function (a) { return a.likes; })) || 1;
      var maxE = Math.max.apply(null, items.map(function (a) { return a.engagement || 1; })) || 1;
      var out = '';
      for (var g = 0; g <= 2; g++) {
        var y = top + ph * (1 - g / 2);
        out += '<line x1="' + left + '" y1="' + y + '" x2="' + (w - right) + '" y2="' + y +
          '" stroke="' + V.line + '" stroke-dasharray="' + (g ? '2 3' : '0') + '"></line>';
        out += '<text x="' + (left - 5) + '" y="' + (y + 3.5) + '" font-size="9" text-anchor="end" fill="' +
          V.muted2 + '">' + num(Math.round(maxY * g / 2)) + '</text>';
      }
      out += '<text x="' + (left - 5) + '" y="' + (top - 3) + '" font-size="8.5" text-anchor="end" fill="' +
        V.muted2 + '">ไลก์</text>';
      ['pos', 'neu', 'neg', 'none'].forEach(function () {});
      var sentColor = { pos: 'var(--pos)', neu: 'var(--neu)', neg: 'var(--neg)' };
      var seen = {};
      items.forEach(function (a, idx) {
        var kx = a.posts + ':' + a.likes;
        seen[kx] = (seen[kx] || 0) + 1;
        var j = (seen[kx] - 1);
        var cx = left + pw * (a.posts / maxX) + (j ? (j % 2 ? 4 : -4) * Math.ceil(j / 2) : 0);
        var cy = top + ph * (1 - (a.likes / maxY)) + (j ? (j % 2 ? -3 : 3) : 0);
        var rr = 3.5 + 9 * Math.sqrt((a.engagement || 1) / maxE);
        out += '<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="' + rr.toFixed(1) +
          '" fill="' + (sentColor[a.sentiment] || '#B7C0D4') + '" fill-opacity=".72" stroke="' +
          (sentColor[a.sentiment] || '#8C99B4') + '">' +
          '<title>' + esc(a.author + ' — ' + a.posts + ' โพสต์ · ' + a.likes + ' ไลก์ · ' +
                          a.engagement + ' engagement') + '</title></circle>';
      });
      items.slice(0, 3).forEach(function (a, i) {
        var cx = left + pw * (a.posts / maxX);
        var cy = top + ph * (1 - (a.likes / maxY));
        // alternate the label side so neighbouring bubbles don't stack their text
        var dx = i % 2 ? -12 : 12, anchor = i % 2 ? 'end' : 'start';
        out += '<text x="' + (cx + dx) + '" y="' + (cy - (i % 2 ? 9 : 5)) + '" font-size="9" ' +
          'text-anchor="' + anchor + '" fill="' + V.muted + '">' +
          esc(String(a.author).slice(0, 14)) + '</text>';
      });
      // x axis labels
      out += '<text x="' + left + '" y="' + (h - bottom + 14) + '" font-size="9" fill="' + V.muted2 +
        '">1 โพสต์</text>';
      out += '<text x="' + (w - right) + '" y="' + (h - bottom + 14) + '" font-size="9" text-anchor="end" ' +
        'fill="' + V.muted2 + '">' + num(maxX) + ' โพสต์</text>';
      out += '<circle cx="' + left + '" cy="' + (h - 8) + '" r="3.5" fill="#9AA5BC"></circle>';
      out += '<circle cx="' + (left + 13) + '" cy="' + (h - 8) + '" r="7" fill="#9AA5BC" fill-opacity=".6" stroke="#9AA5BC"></circle>';
      out += '<text x="' + (left + 24) + '" y="' + (h - 5) + '" font-size="8.5" fill="' + V.muted2 +
        '">ขนาดฟอง = engagement · สี = อารมณ์เด่น</text>';
      return svgWrap(w, h, out, 'กระจายตัวผู้โพสต์ตามจำนวนโพสต์และไลก์');
    }
  };

  /* ── 5. area: cumulative posts ────────────────────────────── */
  registry.area = {
    label: 'โพสต์สะสม',
    render: function (d) {
      if (!d || !d.values || !d.values.length) return empty();
      var vals = d.values, labels = d.labels || [];
      var w = 380, h = 130, left = 24, bottom = 22, top = 10, right = 8;
      var pw = w - left - right, ph = h - bottom - top;
      var max = Math.max.apply(null, vals.concat([1]));
      var pts = vals.map(function (v, i) {
        var x = left + (pw * i) / Math.max(1, vals.length - 1);
        var y = top + ph * (1 - v / max);
        return [x, y];
      });
      var line = pts.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
      var area = line + ' L' + pts[pts.length - 1][0].toFixed(1) + ' ' + (top + ph) + ' L' + pts[0][0].toFixed(1) + ' ' + (top + ph) + ' Z';
      var gid = 'ag' + Math.random().toString(36).slice(2, 7);
      var out = '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">' +
        '<stop offset="0%" stop-color="var(--violet)" stop-opacity=".32"/>' +
        '<stop offset="100%" stop-color="var(--violet)" stop-opacity="0"/></linearGradient></defs>';
      out += '<line x1="' + left + '" y1="' + (top + ph) + '" x2="' + (w - right) + '" y2="' + (top + ph) +
        '" stroke="' + V.line + '"></line>';
      out += '<path d="' + area + '" fill="url(#' + gid + ')"></path>';
      out += '<path d="' + line + '" fill="none" stroke="var(--violet)" stroke-width="2.2" ' +
        'stroke-linejoin="round"></path>';
      pts.forEach(function (p, i) {
        out += '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="2.4" fill="var(--violet)">' +
          '<title>' + esc((labels[i] || '') + ': ' + vals[i]) + '</title></circle>';
      });
      if (labels.length) {
        out += '<text x="' + left + '" y="' + (h - 6) + '" font-size="9" fill="' + V.muted2 + '">' +
          esc(labels[0]) + '</text>';
        out += '<text x="' + (w - right) + '" y="' + (h - 6) + '" font-size="9" text-anchor="end" fill="' +
          V.muted2 + '">' + esc(labels[labels.length - 1]) + '</text>';
      }
      return svgWrap(w, h, out, 'โพสต์สะสมตามวัน สูงสุด ' + max);
    }
  };

  /* ── 6. horizontal bars (ranked) ──────────────────────────── */
  registry.hbars = {
    label: 'อันดับ',
    render: function (items, opts) {
      items = (items || []).filter(function (x) { return x.value > 0; });
      if (!items.length) return empty();
      opts = opts || {};
      var w = 340, rowH = 22, h = items.length * rowH + 8;
      var max = Math.max.apply(null, items.map(function (x) { return x.value; })) || 1;
      var labelW = opts.labelW || 108, out = '';
      items.forEach(function (it, i) {
        var y = i * rowH + 4;
        var bw = Math.max(2, (w - labelW - 44) * (it.value / max));
        out += '<text x="0" y="' + (y + 11) + '" font-size="10" fill="' + V.ink2 + '">' +
          esc(String(it.label).slice(0, opts.labelChars || 18)) + '</text>';
        out += '<rect x="' + labelW + '" y="' + (y + 4) + '" width="' + bw + '" height="10" rx="5" fill="' +
          (it.color || 'var(--violet)') + '"></rect>';
        out += '<text x="' + (labelW + bw + 6) + '" y="' + (y + 12) + '" font-size="9.5" fill="' +
          V.muted + '">' + num(it.value) + '</text>';
      });
      return svgWrap(w, h, out, 'อันดับ ' + items.length + ' รายการ');
    }
  };

  /* ── 7. sparkline ─────────────────────────────────────────── */
  registry.sparkline = {
    label: 'แนวโน้มย่อ',
    render: function (values, opts) {
      var vals = (values || []).map(Number).filter(function (v) { return isFinite(v); });
      if (!vals.length) return '<span style="color:var(--muted-2);font-size:11px">—</span>';
      opts = opts || {};
      var w = opts.w || 90, h = opts.h || 24, pad = 2;
      var max = Math.max.apply(null, vals), min = Math.min.apply(null, vals);
      var span = (max - min) || 1;
      var pts = vals.map(function (v, i) {
        var x = pad + ((w - 2 * pad) * i) / Math.max(1, vals.length - 1);
        var y = pad + (h - 2 * pad) * (1 - (v - min) / span);
        return x.toFixed(1) + ' ' + y.toFixed(1);
      });
      var d = 'M' + pts.join(' L');
      return '<svg viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h +
        '" role="img" aria-label="แนวโน้ม" style="display:inline-block;vertical-align:middle">' +
        '<path d="' + d + '" fill="none" stroke="' + (opts.color || 'var(--violet)') +
        '" stroke-width="1.8" stroke-linejoin="round"></path></svg>';
    }
  };

  var HarkenCharts = {
    version: '1.0.0',
    register: function (name, def) {
      if (!name || !def || typeof def.render !== 'function') {
        throw new Error('HarkenCharts.register(name, {render}) required');
      }
      registry[name] = def;
      return def;
    },
    get: function (name) { return registry[name]; },
    list: function () {
      return Object.keys(registry).map(function (k) { return { name: k, label: registry[k].label || k }; });
    },
    render: function (name, target, data, opts) {
      var el = typeof target === 'string' ? document.querySelector(target) : target;
      if (!el) return null;
      var def = registry[name];
      if (!def) {
        el.innerHTML = empty('ไม่พบกราฟ: ' + name);
        return null;
      }
      try {
        el.innerHTML = def.render(data, opts || {});
      } catch (err) {
        el.innerHTML = empty('วาดกราฟไม่สำเร็จ');
        if (window.console) console.warn('[charts]', name, err);
      }
      return el;
    },
    empty: empty
  };

  global.HarkenCharts = HarkenCharts;
})(window);
