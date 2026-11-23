/* One-shot overview motion. Load BEFORE charts.js/sl-charts.js/ov.js so this
 * observer removes the donut library's replay marker before its observer runs.
 * Public surface is deliberately limited to teardown and test diagnostics. */
(function () {
  'use strict';
  if (window.__microData) return;
  var media = matchMedia('(prefers-reduced-motion: reduce)');
  var values = new Map(), shots = new Set(), timers = new Set();
  var dead = false, observer;
  var stats = { counts: 0, changes: 0, pulses: 0, entrances: 0 };
  var selector = '#kPosts,#kComments,#kEng,#kAuthors,#kZones';
  function number(text) {
    var s = text.trim().replace(/[๐-๙]/g, function (c) { return String(c.charCodeAt(0) - 3664); })
      .replace(/[,\s\u00a0\u202f]/g, '');
    return /^[+-]?\d+(?:\.\d+)?$/.test(s) && Number.isFinite(Number(s)) ? Number(s) : null;
  }
  function duration() {
    var s = getComputedStyle(document.documentElement).getPropertyValue('--micro-data-enter').trim();
    var ms = parseFloat(s) * (/ms$/.test(s) ? 1 : 1000);
    return Math.max(500, Math.min(700, ms || 600));
  }
  function observeValue(el, state) { state.observer.observe(el, { childList: true, characterData: true, subtree: true }); }
  function write(el, state, text) {
    state.observer.disconnect();
    el.textContent = text;
    observeValue(el, state);
  }
  function stop(el, state, restore) {
    cancelAnimationFrame(state.raf);
    state.raf = 0;
    if (restore) write(el, state, state.final);
  }
  function flash(el, delta) {
    if (media.matches || !delta) return;
    stats.pulses++;
    el.dataset.microDelta = (delta > 0 ? '+' : '−') + Math.abs(delta).toLocaleString('th-TH');
    el.dataset.microSign = delta > 0 ? 'pos' : 'neg';
    el.classList.remove('micro-data-pulse');
    void el.offsetWidth;
    el.classList.add('micro-data-pulse');
  }
  function update(el, state) {
    var final = el.textContent, n = number(final);
    if (n === null) return;
    if (state.value !== null) {
      if (state.raf) stop(el, state, false);
      var delta = n - state.value;
      state.final = final;
      state.value = n;
      if (delta) { stats.changes++; flash(el, delta); }
      return;
    }
    state.value = n;
    state.final = final;
    if (media.matches || !n) return;
    stats.counts++;
    var start = performance.now(), ms = duration();
    var thai = /[๐-๙]/.test(final);
    var decimals = (final.trim().split('.')[1] || '').length;
    var formatter = new Intl.NumberFormat(thai ? 'th-TH-u-nu-thai' : 'th-TH', {
      useGrouping: /[,\s\u00a0\u202f]/.test(final.trim()),
      minimumFractionDigits: decimals, maximumFractionDigits: decimals
    });
    write(el, state, formatter.format(0));
    function frame(now) {
      if (dead) return;
      if (media.matches) { stop(el, state, true); return; }
      var t = Math.min(1, (now - start) / ms);
      var v = n * (1 - Math.pow(1 - t, 3));
      write(el, state, t === 1 ? state.final : formatter.format(decimals ? v : Math.trunc(v)));
      state.raf = t < 1 ? requestAnimationFrame(frame) : 0;
    }
    state.raf = requestAnimationFrame(frame);
  }
  function enter(host, cls) {
    if (shots.has(host)) return;
    shots.add(host);
    if (media.matches) return;
    stats.entrances++;
    host.classList.add(cls);
    var timer = setTimeout(function () { host.classList.remove(cls); timers.delete(timer); }, duration());
    timers.add(timer);
  }
  function scan() {
    if (dead) return;
    document.querySelectorAll(selector).forEach(function (el) {
      if (!el.matches('.kpi .v') || values.has(el)) return;
      var state = { value: null, final: '', raf: 0 };
      state.observer = new MutationObserver(function () { update(el, state); });
      values.set(el, state);
      el.classList.add('micro-data-value');
      observeValue(el, state);
      update(el, state);
    });
    var bars = document.querySelector('#sentBars');
    if (bars && bars.querySelector('.fill')) enter(bars, 'micro-data-bars');
    var donut = document.querySelector('#chartDonut');
    if (donut) {
      /* Suppress the library's repeated arc sweep, not its renderer or geometry. */
      donut.querySelectorAll('[data-sl-motion="donut"]').forEach(function (svg) { svg.removeAttribute('data-sl-motion'); });
      if (donut.querySelector('svg path,svg circle,canvas')) enter(donut, 'micro-data-donut');
    }
    document.querySelectorAll('.spark').forEach(function (host) {
      if (shots.has(host) || !host.firstChild) return;
      var path = host.querySelector('path[stroke]');
      if (path) {
        shots.add(host);
        enter(path, 'micro-data-spark-path');
      } else enter(host, 'micro-data-spark-fallback');
    });
  }
  function reduced() {
    if (!media.matches) return;
    values.forEach(function (state, el) { if (state.raf) stop(el, state, true); });
  }
  function destroy() {
    dead = true;
    observer.disconnect();
    document.removeEventListener('DOMContentLoaded', scan);
    media.removeEventListener('change', reduced);
    values.forEach(function (state, el) {
      if (state.raf) stop(el, state, true);
      state.observer.disconnect();
      el.classList.remove('micro-data-value', 'micro-data-pulse');
      delete el.dataset.microDelta; delete el.dataset.microSign;
    });
    timers.forEach(clearTimeout);
    document.querySelectorAll('.micro-data-bars,.micro-data-donut,.micro-data-spark-path,.micro-data-spark-fallback')
      .forEach(function (el) { el.classList.remove('micro-data-bars','micro-data-donut','micro-data-spark-path','micro-data-spark-fallback'); });
    delete window.__microData;
  }
  window.__microData = { destroy: destroy, stats: stats };
  observer = new MutationObserver(function (records) {
    /* Counter text writes are already handled locally, never rescan for them. */
    if (records.some(function (r) { return r.target.nodeType === 1 && !r.target.matches(selector) && r.addedNodes.length; })) scan();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  media.addEventListener('change', reduced);
  document.addEventListener('DOMContentLoaded', scan, { once: true });
  scan();
})();
