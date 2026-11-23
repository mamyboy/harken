/* Optional, idempotent pointer layer. Load with defer, after its stylesheet. */
(function () {
  document.documentElement.classList.add('micro-pointer');
  'use strict';
  if (window.__microPointer) return;
  var root = document.documentElement;
  var media = window.matchMedia('(pointer: fine) and (hover: hover) and (prefers-reduced-motion: no-preference)');
  var pending = new Map();
  var touched = new Set();
  var frame = 0, railFrame = 0, observer, resizeObserver, host, pill;
  var destroyed = false;

  function flush() {
    frame = 0;
    if (!media.matches) { pending.clear(); return; }
    pending.forEach(function (values, el) {
      if (!el.isConnected) return;
      Object.keys(values).forEach(function (key) { el.style.setProperty(key, values[key]); });
      touched.add(el);
    });
    pending.clear();
  }
  function queue(el, values) {
    pending.set(el, Object.assign(pending.get(el) || {}, values));
    if (!frame) frame = requestAnimationFrame(flush);
  }
  function move(event) {
    if (!media.matches || event.pointerType === 'touch' || !(event.target instanceof Element)) return;
    var surface = event.target.closest('.card, .kpi');
    if (surface) {
      var r = surface.getBoundingClientRect();
      queue(surface, { '--mx': (event.clientX - r.left) + 'px', '--my': (event.clientY - r.top) + 'px' });
    }
    var cta = event.target.closest('.qs-go');
    if (cta) {
      /* Subtract the current translation so the magnetic target never chases itself. */
      var box = cta.getBoundingClientRect();
      var dx = parseFloat(cta.style.getPropertyValue('--mag-x')) || 0;
      var dy = parseFloat(cta.style.getPropertyValue('--mag-y')) || 0;
      var x = (event.clientX - box.left + dx) / box.width - .5;
      var y = (event.clientY - box.top + dy) / box.height - .5;
      var length = Math.hypot(x, y) || 1;
      var amount = Math.min(3, length * 4);
      queue(cta, { '--mag-x': (x / length * amount) + 'px', '--mag-y': (y / length * amount) + 'px' });
    }
  }
  function leave(event) {
    if (!(event.target instanceof Element)) return;
    var cta = event.target.closest('.qs-go');
    if (cta && (!event.relatedTarget || !cta.contains(event.relatedTarget))) {
      queue(cta, { '--mag-x': '0px', '--mag-y': '0px' });
    }
  }
  function activeLink() {
    if (!host) return null;
    /* In overview.html .nl is the label INSIDE .navlink, not the anchor itself. */
    var active = host.querySelector('[aria-current="page"], [aria-current="true"], .navlink.active, .nl.active, .navlink.is-active, .nl.is-active');
    return active && (active.closest('.navlink') || active.closest('a.nl') || active);
  }
  function placeRail() {
    railFrame = 0;
    if (!pill || !media.matches) return;
    var link = activeLink();
    if (!link) { pill.removeAttribute('data-ready'); return; }
    var r = link.getBoundingClientRect(), p = host.getBoundingClientRect();
    if (!r.width || !r.height) { pill.removeAttribute('data-ready'); return; }
    /* Dimensions are measured, assigned without a transition; only translation animates. */
    pill.style.width = r.width + 'px';
    pill.style.height = r.height + 'px';
    pill.style.transform = 'translate(' + (r.left - p.left + host.scrollLeft - host.clientLeft) + 'px,' +
      (r.top - p.top + host.scrollTop - host.clientTop) + 'px)';
    pill.setAttribute('data-ready', '');
  }
  function requestRail() {
    if (!railFrame && media.matches) railFrame = requestAnimationFrame(placeRail);
  }
  function reset() {
    pending.clear();
    touched.forEach(function (el) {
      ['--mx', '--my', '--mag-x', '--mag-y'].forEach(function (key) { el.style.removeProperty(key); });
    });
    touched.clear();
    if (pill) pill.removeAttribute('data-ready');
  }
  function change() { if (media.matches) requestRail(); else reset(); }
  function start() {
    if (destroyed) return;
    host = document.querySelector('.topnav .navlinks');
    if (host && !pill) {
      pill = document.createElement('span');
      pill.className = 'micro-rail-pill';
      pill.setAttribute('aria-hidden', 'true');
      host.prepend(pill);
      observer = new MutationObserver(requestRail);
      observer.observe(host, { subtree:true, childList:true, attributes:true, attributeFilter:['aria-current','class'] });
      if (window.ResizeObserver) {
        resizeObserver = new ResizeObserver(requestRail);
        resizeObserver.observe(host);
      }
      host.addEventListener('scroll', requestRail, { passive:true });
    }
    requestRail();
    if (document.fonts) document.fonts.ready.then(requestRail);
  }
  document.addEventListener('pointermove', move, { passive:true });
  document.addEventListener('pointerout', leave, { passive:true });
  window.addEventListener('resize', requestRail, { passive:true });
  media.addEventListener('change', change);
  window.__microPointer = {
    refresh:requestRail,
    destroy:function () {
      destroyed = true;
      document.removeEventListener('DOMContentLoaded', start);
      document.removeEventListener('pointermove', move);
      document.removeEventListener('pointerout', leave);
      window.removeEventListener('resize', requestRail);
      media.removeEventListener('change', change);
      if (observer) observer.disconnect();
      if (resizeObserver) resizeObserver.disconnect();
      if (host) host.removeEventListener('scroll', requestRail);
      cancelAnimationFrame(frame); cancelAnimationFrame(railFrame);
      reset();
      if (pill) pill.remove();
      root.classList.remove('micro-pointer');
      delete window.__microPointer;
    }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once:true });
  else start();
})();
