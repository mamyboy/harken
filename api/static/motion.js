(function () {
  'use strict';
  if (window.HarkenMotion) return;

  var root = document.documentElement;
  if (document.startViewTransition && window.CSS &&
      window.CSS.supports && window.CSS.supports('view-transition-name: none')) {
    root.classList.add('vt');
  }

  var media = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  var running = false;
  var frame = null;
  var timer = null;
  var last = null;
  var hasValue = false;

  function parallax() {
    frame = null;
    if (!running) return;
    var y = Math.max(0, Math.min(20000, Math.round(window.pageYOffset || root.scrollTop || 0)));
    if (!hasValue || y !== last) {
      root.style.setProperty('--sy', y + 'px');
      last = y;
      hasValue = true;
    }
  }

  function schedule() {
    if (running && frame === null) frame = window.requestAnimationFrame(parallax);
  }

  function resize() {
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      timer = null;
      schedule();
    }, 150);
  }

  function sync() {
    var enabled = !(media && media.matches) && !!window.requestAnimationFrame;
    if (enabled === running) return;
    running = enabled;
    if (running) {
      window.addEventListener('scroll', schedule, { passive: true });
      window.addEventListener('resize', resize);
      window.addEventListener('load', schedule);
      schedule();
    } else {
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', resize);
      window.removeEventListener('load', schedule);
      if (frame !== null) window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
      frame = null;
      timer = null;
      if (hasValue) root.style.removeProperty('--sy');
      hasValue = false;
    }
  }

  window.HarkenMotion = {
    sy: function () { return last; },
    enabled: function () { return running; }
  };
  if (media) {
    if (media.addEventListener) media.addEventListener('change', sync);
    else if (media.addListener) media.addListener(sync);
  }
  sync();
}());
