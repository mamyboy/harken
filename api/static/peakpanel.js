/* Integration: document.dispatchEvent(new CustomEvent('harken:day-select',
 *   { detail: { date: 'YYYY-MM-DD' } }));
 * Window-dispatched events are supported too. No chart/global dependencies.
 */
(function () {
  'use strict';

  function init() {
    var panel = document.createElement('aside');
    panel.id = 'peakPanel';
    panel.className = 'peak-panel';
    panel.hidden = true;
    panel.setAttribute('role', 'complementary');
    panel.setAttribute('aria-labelledby', 'peakPanelDate');
    panel.innerHTML = '<header class="peak-panel__head">' +
      '<div><p class="peak-panel__eyebrow">โพสต์ประจำวัน</p>' +
      '<h2 id="peakPanelDate"></h2></div>' +
      '<button class="peak-panel__close" type="button" aria-label="ปิด">' +
      '<span aria-hidden="true">×</span></button></header>' +
      '<div class="peak-panel__body" aria-live="polite" aria-atomic="true"></div>';
    document.body.appendChild(panel);

    var heading = panel.querySelector('h2');
    var closeButton = panel.querySelector('button');
    var body = panel.querySelector('.peak-panel__body');
    var isOpen = false;
    var activeDate = '';
    var controller = null;
    var sequence = 0;
    var hideTimer;
    var outsideTimer;
    var motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    var number = new Intl.NumberFormat('th-TH');
    var relative = new Intl.RelativeTimeFormat('th-TH', { numeric: 'auto' });
    var platforms = { x: 'เอ็กซ์', twitter: 'เอ็กซ์', facebook: 'เฟซบุ๊ก',
      threads: 'เธรดส์', tiktok: 'ติ๊กต็อก', youtube: 'ยูทูบ', instagram: 'อินสตาแกรม' };

    function element(tag, className, text) {
      var node = document.createElement(tag);
      node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    }

    function platformName(key) {
      return platforms[String(key || '').toLowerCase()] || 'แพลตฟอร์มอื่น';
    }

    function position() {
      var bar = document.querySelector('.appbar');
      var top = bar ? Math.max(16, bar.getBoundingClientRect().bottom + 12) : 82;
      panel.style.setProperty('--peak-panel-top', top + 'px');
    }

    function hideTooltip() {
      var tooltip = document.getElementById('dayCard');
      if (tooltip) {
        tooltip.classList.remove('on');
        tooltip.style.display = 'none';
      }
    }

    function close() {
      if (!isOpen) return;
      isOpen = false;
      activeDate = '';
      sequence += 1;
      if (controller) controller.abort();
      panel.classList.remove('is-open');
      panel.setAttribute('aria-hidden', 'true');
      panel.inert = true;
      document.documentElement.classList.remove('peak-panel-open');
      // The body normally cannot receive focus; restore its original tabindex.
      var tabindex = document.body.getAttribute('tabindex');
      document.body.setAttribute('tabindex', '-1');
      document.body.focus({ preventScroll: true });
      if (tabindex === null) document.body.removeAttribute('tabindex');
      else document.body.setAttribute('tabindex', tabindex);
      hideTimer = window.setTimeout(function () { panel.hidden = true; }, motion.matches ? 0 : 140);
    }

    function message(text, error) {
      body.replaceChildren(element('p', 'peak-panel__state' + (error ? ' peak-panel__state--error' : ''), text));
    }

    function timeNode(iso) {
      var time = element('time', 'peak-panel__time');
      var stamp = new Date(iso);
      if (!iso || !Number.isFinite(stamp.getTime())) {
        time.textContent = 'ไม่ระบุเวลา';
        return time;
      }
      var seconds = (stamp.getTime() - Date.now()) / 1000;
      var magnitude = Math.abs(seconds);
      var unit = magnitude < 60 ? 'second' : magnitude < 3600 ? 'minute' : magnitude < 86400 ? 'hour' : 'day';
      var divisor = unit === 'second' ? 1 : unit === 'minute' ? 60 : unit === 'hour' ? 3600 : 86400;
      time.dateTime = iso;
      time.title = stamp.toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' });
      time.textContent = relative.format(Math.round(seconds / divisor), unit);
      return time;
    }

    function render(data) {
      if (!Array.isArray(data.posts)) throw new Error('Invalid posts response');
      var posts = data.posts.slice(0, 8);
      var total = Number.isFinite(data.total) ? data.total : posts.length;
      var summary = element('div', 'peak-panel__summary');
      summary.appendChild(element('p', 'peak-panel__count', number.format(total) + ' โพสต์'));
      var chips = element('div', 'peak-panel__chips');
      chips.setAttribute('aria-label', 'จำนวนโพสต์แยกตามแพลตฟอร์ม');
      var counts = data.facets && data.facets.platform;
      if (!counts || typeof counts !== 'object') {
        counts = Object.create(null);
        posts.forEach(function (post) { var key = post.platform || ''; counts[key] = (counts[key] || 0) + 1; });
      }
      Object.keys(counts).forEach(function (key) {
        chips.appendChild(element('span', 'peak-panel__chip', platformName(key) + ' · ' + number.format(counts[key])));
      });
      summary.appendChild(chips);
      body.replaceChildren(summary);
      if (!posts.length) {
        body.appendChild(element('p', 'peak-panel__state', 'ไม่พบโพสต์ในวันนี้'));
        return;
      }
      body.appendChild(element('p', 'peak-panel__caption', 'แสดง ' + number.format(posts.length) + ' โพสต์ล่าสุด'));
      var list = element('ul', 'peak-panel__posts');
      posts.forEach(function (post) {
        var item = element('li', 'peak-panel__item');
        var link = element('a', 'peak-panel__post');
        // Treat remote fields as text and reject executable URL schemes.
        try {
          var url = new URL(post.url);
          if (url.protocol !== 'https:' && url.protocol !== 'http:') throw new Error('Unsafe URL');
          link.href = url.href;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.setAttribute('aria-label', 'เปิดโพสต์ของ ' + (post.author || 'ผู้ใช้ไม่ระบุชื่อ') + ' ในแท็บใหม่');
        } catch (_) {
          link = element('div', 'peak-panel__post');
        }
        var meta = element('div', 'peak-panel__meta');
        meta.appendChild(element('strong', 'peak-panel__author', post.author ? '@' + String(post.author).replace(/^@/, '') : 'ผู้ใช้ไม่ระบุชื่อ'));
        meta.appendChild(element('span', 'peak-panel__platform', platformName(post.platform)));
        link.appendChild(meta);
        link.appendChild(element('p', 'peak-panel__excerpt', post.text_th || post.text_raw || 'ไม่มีข้อความ'));
        link.appendChild(timeNode(post.posted_iso));
        item.appendChild(link);
        list.appendChild(item);
      });
      body.appendChild(list);
    }

    function open(event) {
      var detail = event.detail || {};
      var date = detail.date;
      if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return;
      var stamp = new Date(date + 'T00:00:00Z');
      if (!Number.isFinite(stamp.getTime()) || stamp.toISOString().slice(0, 10) !== date) return;
      clearTimeout(outsideTimer);
      hideTooltip();
      // Repeated clicks on the selected day reuse the pending/loaded request.
      if (isOpen && activeDate === date) { closeButton.focus({ preventScroll: true }); return; }
      clearTimeout(hideTimer);
      if (controller) controller.abort();
      controller = new AbortController();
      var request = ++sequence;
      activeDate = date;
      isOpen = true;
      heading.textContent = stamp.toLocaleDateString('th-TH', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'Asia/Bangkok' });
      body.setAttribute('aria-busy', 'true');
      message('กำลังโหลด…');
      panel.hidden = false;
      panel.inert = false;
      panel.removeAttribute('aria-hidden');
      document.documentElement.classList.add('peak-panel-open');
      position();
      // Flush the closed pose before applying the opening transition.
      void panel.offsetWidth;
      panel.classList.add('is-open');
      closeButton.focus({ preventScroll: true });
      fetch('/api/posts?date_from=' + encodeURIComponent(date) + '&date_to=' + encodeURIComponent(date) + '&limit=8', {
        signal: controller.signal, headers: { Accept: 'application/json' }
      }).then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      }).then(function (data) {
        if (request === sequence && isOpen) render(data);
      }).catch(function (error) {
        if (request !== sequence || !isOpen || error.name === 'AbortError') return;
        activeDate = ''; // Allow clicking this day again to retry.
        message('โหลดโพสต์ไม่ได้ กรุณาเลือกวันนี้บนกราฟอีกครั้ง', true);
      }).finally(function () {
        if (request === sequence) body.setAttribute('aria-busy', 'false');
      });
    }

    closeButton.addEventListener('click', close);
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && isOpen) { event.preventDefault(); close(); }
    });
    // Defer outside dismissal until chart handlers have dispatched a selection.
    // This preserves a pending request when the same day is clicked twice.
    document.addEventListener('click', function (event) {
      if (isOpen && !panel.contains(event.target)) {
        clearTimeout(outsideTimer);
        outsideTimer = window.setTimeout(close, 0);
      }
    }, true);
    window.addEventListener('resize', position);
    window.addEventListener('scroll', function () { if (isOpen) position(); }, { passive: true });
    window.addEventListener('harken:day-select', open);
    // Non-bubbling CustomEvents dispatched on document also work.
    document.addEventListener('harken:day-select', function (event) {
      if (!event.bubbles) open(event);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
}());
