/* Shared theme controller; the head snippet handles the first paint. */
(function (window, document) {
  'use strict';
  var key = 'harken-theme';
  var choice = null;
  var theme;
  var button;
  var media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function valid(value) {
    return value === 'light' || value === 'dark';
  }
  try {
    choice = window.localStorage.getItem(key);
  } catch (ignore) {}
  if (!valid(choice)) choice = null;

  function apply(value) {
    theme = value;
    var root = document && document.documentElement;
    if (root && root.dataset) root.dataset.theme = theme;
    var meta = document && document.querySelector ? document.querySelector('meta[name="theme-color"]') : null;
    if (!meta && document && document.head && document.createElement) {
      meta = document.createElement('meta');
      meta.setAttribute('name', 'theme-color');
      document.head.appendChild(meta);
    }
    if (meta) meta.setAttribute('content', theme === 'dark' ? '#0F1B33' : '#EDF4FE');
    if (button) button.setAttribute('aria-pressed', String(theme === 'dark'));
  }

  function set(value) {
    if (!valid(value)) return theme;
    choice = value;
    try {
      window.localStorage.setItem(key, value);
    } catch (ignore) {}
    apply(value);
    window.dispatchEvent(new window.CustomEvent('harken:theme', { detail: { theme: theme } }));
    return theme;
  }
  function toggle() {
    return set(theme === 'dark' ? 'light' : 'dark');
  }
  window.HarkenTheme = {
    get: function () { return theme; },
    set: set,
    toggle: toggle
  };
  apply(choice || (media && media.matches ? 'dark' : 'light'));

  function wire() {
    button = document && document.getElementById ? document.getElementById('themeBtn') : null;
    if (!button) return;
    button.setAttribute('aria-pressed', String(theme === 'dark'));
    button.addEventListener('click', function () {
      toggle();
    });
  }
  if (document && document.addEventListener) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
    else wire();
  }

  function followSystem(event) {
    try {
      var stored = window.localStorage.getItem(key);
      choice = valid(stored) ? stored : null;
    } catch (ignore) {}
    if (!choice) apply(event.matches ? 'dark' : 'light');
  }
  if (media) {
    if (media.addEventListener) media.addEventListener('change', followSystem);
    else if (media.addListener) media.addListener(followSystem);
  }
}(window, document));
