/* Shared app bar: native search, live totals and restrained KPI motion. */
(function () {
  'use strict';
  var pollTimer = null;
  var inFlight = null;

  function liveState(state) {
    var live = document.getElementById('abLive');
    if (!live) { return; }
    live.classList.remove('is-live', 'is-idle', 'is-err');
    live.classList.add(state);
  }

  function refreshStats() {
    var meta = document.getElementById('abMeta');
    if (!meta || typeof window.fetch !== 'function') { return; }
    if (inFlight) { return inFlight; }
    inFlight = window.fetch('/api/stats', { cache: 'no-store' })
      .then(function (response) {
        if (!response.ok) { throw new Error('Stats request failed'); }
        return response.json();
      })
      .then(function (stats) {
        if (!stats || typeof stats.total !== 'number' ||
            !isFinite(stats.total) || stats.total < 0) {
          throw new Error('Invalid post total');
        }
        var now = new Date();
        var hh = ('0' + now.getHours()).slice(-2);
        var mm = ('0' + now.getMinutes()).slice(-2);
        meta.textContent = 'อัปเดต ' + hh + ':' + mm + ' · ' +
          stats.total.toLocaleString('th-TH') + ' โพสต์';
        liveState(document.hidden ? 'is-idle' : 'is-live');
      })
      .catch(function () { liveState('is-err'); })
      .then(function () { inFlight = null; });
    return inFlight;
  }

  function countUp(element) {
    var original = element.textContent;
    var ascii = original.replace(/[๐-๙]/g, function (digit) {
      return String(digit.charCodeAt(0) - 3664);
    });
    var match = /[+-]?[0-9][0-9,]*(?:\.[0-9]+)?/.exec(ascii);
    if (!match || typeof window.requestAnimationFrame !== 'function') { return; }
    var value = Number(match[0].replace(/,/g, ''));
    if (!isFinite(value)) { return; }
    var decimals = (match[0].split('.')[1] || '').length;
    if (decimals > 20) { return; }
    var prefix = original.slice(0, match.index);
    var suffix = original.slice(match.index + match[0].length);
    var thaiDigits = /[๐-๙]/.test(original.slice(match.index, match.index + match[0].length));
    var start = null;
    function frame(time) {
      if (start === null) { start = time; }
      var progress = Math.min((time - start) / 700, 1);
      if (progress >= 1) { element.textContent = original; return; }
      var eased = 1 - Math.pow(1 - progress, 3);
      var number = (value * eased).toLocaleString('th-TH', {
        useGrouping: match[0].indexOf(',') !== -1,
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
      });
      if (thaiDigits) {
        number = number.replace(/[0-9]/g, function (digit) {
          return String.fromCharCode(3664 + Number(digit));
        });
      }
      if (match[0].charAt(0) === '+' && value >= 0) { number = '+' + number; }
      element.textContent = prefix + number + suffix;
      window.requestAnimationFrame(frame);
    }
    window.requestAnimationFrame(frame);
  }

  function initCountUp() {
    if ((window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) ||
        !window.IntersectionObserver || !window.requestAnimationFrame) { return; }
    var observer = new window.IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        observer.unobserve(entry.target);
        if (entry.isIntersecting && entry.intersectionRatio >= 0.3) { countUp(entry.target); }
      });
    }, { threshold: 0.3 });
    var values = document.querySelectorAll('.kpi .v');
    for (var i = 0; i < values.length; i += 1) { observer.observe(values[i]); }
  }

  function isField(target) {
    if (!target) { return false; }
    var tag = (target.tagName || '').toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable;
  }

  function init() {
    var bar = document.getElementById('appbar') || document.querySelector('.appbar');
    var input = document.getElementById('qkw');
    var form = document.getElementById('quicksearch');
    var scrollPending = false;
    function updateSticky() {
      scrollPending = false;
      if (bar) { bar.classList.toggle('is-stuck', (window.scrollY || window.pageYOffset || 0) > 4); }
    }
    updateSticky();
    if (bar && window.requestAnimationFrame) {
      window.addEventListener('scroll', function () {
        if (!scrollPending) {
          scrollPending = true;
          window.requestAnimationFrame(updateSticky);
        }
      }, { passive: true });
    }
    if (input) {
      document.addEventListener('keydown', function (event) {
        var shortcut = (event.metaKey || event.ctrlKey) && !event.altKey &&
          String(event.key).toLowerCase() === 'k';
        var slash = event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey;
        if (!shortcut && !slash) { return; }
        if (isField(event.target) && event.target !== input) { return; }
        if (slash && (isField(event.target) || isField(document.activeElement))) { return; }
        event.preventDefault();
        input.focus();
        input.select();
      });
      input.addEventListener('input', function () {
        input.removeAttribute('aria-invalid');
        if (input.getAttribute('title') === 'กรุณาพิมพ์คำค้น') { input.removeAttribute('title'); }
      });
      if (form) {
        form.addEventListener('submit', function (event) {
          input.value = input.value.trim();
          if (!input.value) {
            event.preventDefault();
            input.setAttribute('aria-invalid', 'true');
            input.setAttribute('title', 'กรุณาพิมพ์คำค้น');
            input.focus();
          }
        });
      }
    }
    function resumePolling() {
      if (pollTimer !== null) { window.clearInterval(pollTimer); pollTimer = null; }
      if (document.hidden) { liveState('is-idle'); return; }
      refreshStats();
      if (document.getElementById('abMeta')) {
        pollTimer = window.setInterval(refreshStats, 60000);
      }
    }
    document.addEventListener('visibilitychange', resumePolling);
    resumePolling();
    initCountUp();
  }

  window.HarkenAppbar = { refresh: refreshStats };
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', init); }
  else { init(); }
}());
