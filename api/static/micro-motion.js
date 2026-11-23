/* Optional overview motion. Include after micro-motion.css, preferably deferred. */
(function () {
  'use strict';
  if (window.__microMotion) return;
  var root = document.documentElement;
  var media = matchMedia('(prefers-reduced-motion: reduce)');
  var pending = new Set();
  var observer;
  var sweep;
  var sweepTimer;
  var api = { ready: false, sweepCount: 0 };
  window.__microMotion = api;
  root.classList.add('micro-motion');

  function finish(el) {
    el.dataset.mmReveal = 'done';
    el.style.removeProperty('will-change');
    pending.delete(el);
    if (observer) observer.unobserve(el);
  }
  function reveal(el) {
    if (!pending.has(el)) return;
    if (observer) observer.unobserve(el);
    if (media.matches) { finish(el); return; }
    el.style.willChange = 'transform, opacity';
    el.dataset.mmReveal = 'revealing';
    el.addEventListener('animationend', function ended(event) {
      if (event.target !== el || event.animationName !== 'mm-reveal') return;
      el.removeEventListener('animationend', ended);
      finish(el);
    });
    // Cleanup is bounded even when the tab is backgrounded or CSS is unavailable.
    setTimeout(function () { finish(el); }, 300);
  }
  function stopSweep() {
    clearTimeout(sweepTimer);
    if (sweep) sweep.classList.remove('mm-sweeping');
  }

  // Safety net: a reveal that never fires would leave real content invisible.
  // Whatever the observer did, nothing may stay hidden — printing, a missed
  // intersection, or a backgrounded tab all fall back to the final state.
  window.addEventListener('beforeprint', function () { pending.forEach(finish); });
  window.addEventListener('afterprint', function () { pending.forEach(finish); });
  setTimeout(function () { pending.forEach(finish); }, 4000);
  function cue() {
    if (media.matches || !sweep) return;
    stopSweep();
    // Two frames restart the single decorative element without a layout read.
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        if (media.matches) return;
        sweep.classList.add('mm-sweeping');
        api.sweepCount++;
        sweepTimer = setTimeout(stopSweep, 900);
      });
    });
  }
  function init() {
    var nodes = Array.from(document.querySelectorAll('.section, .card, .kpis > .kpi'));
    var groups = new Map();
    if ('IntersectionObserver' in window) observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting && entry.intersectionRatio >= 0.15) reveal(entry.target);
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -8% 0px' });
    nodes.forEach(function (el) {
      var parent = el.parentElement;
      if (!groups.has(parent)) groups.set(parent, []);
      groups.get(parent).push(el);
    });
    var groupId = 0;
    groups.forEach(function (items) {
      // Six-item groups reset the cadence; extra items have no stagger at all.
      var id = String(++groupId);
      items.forEach(function (el, index) {
        el.dataset.mmGroup = id;
        var delay = index < 6 ? index * 40 : 0;
        if (index < 6) el.dataset.mmStagger = String(index);
        el.style.setProperty('--mm-delay', delay + 'ms');
        // 260ms travel, shortened only where needed to keep delay+travel <=300ms.
        el.style.setProperty('--mm-duration', Math.min(260, 300 - delay) + 'ms');
        var box = el.getBoundingClientRect();
        // Above-fold content is immediate: the existing route/body owns its fade.
        // This also covers html.vt and active same/cross-document View Transitions.
        if (media.matches || !observer || (box.top < innerHeight && box.bottom > 0)) {
          finish(el);
        } else {
          el.dataset.mmReveal = 'pending';
          pending.add(el);
          observer.observe(el);
        }
      });
    });
    var bar = document.querySelector('#appbar');
    if (bar) {
      sweep = document.createElement('span');
      sweep.className = 'mm-refresh';
      sweep.setAttribute('aria-hidden', 'true');
      bar.appendChild(sweep);
    }
    var hosts = Array.from(document.querySelectorAll('#topRows, #zoneRows'));
    var signatures = new WeakMap();
    hosts.forEach(function (host) { signatures.set(host, host.innerHTML); });
    var queued = false;
    var repaintObserver = new MutationObserver(function () {
      if (queued) return;
      queued = true;
      requestAnimationFrame(function () {
        queued = false;
        var changed = false;
        hosts.forEach(function (host) {
          // Loading/error/empty/no-source are honest status, not arriving data.
          // Retain last ready snapshot through loading so identical polls stay silent.
          var state = host.getAttribute('data-state');
          if (state && state !== 'ready') return;
          var next = host.innerHTML;
          if (next !== signatures.get(host)) changed = true;
          signatures.set(host, next);
        });
        if (changed) cue();
      });
    });
    hosts.forEach(function (host) {
      repaintObserver.observe(host, { childList: true, characterData: true, subtree: true });
    });
    media.addEventListener('change', function () {
      if (!media.matches) return;
      pending.forEach(finish);
      stopSweep();
    });
    api.ready = true;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();
