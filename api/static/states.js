/* Honest region states. No fetching or data inference: callers own the lifecycle.
 * set(target, 'ready') BEFORE painting fresh data so cached nodes are restored
 * before a renderer looks up their IDs. Then set an empty/error state if needed.
 * Loading -> empty -> error retains the same original nodes, including listeners.
 */
(function () {
  'use strict';
  var saved = new WeakMap();
  var messages = {
    loading: ['กำลังโหลดข้อมูล', 'โปรดรอสักครู่'],
    empty: ['ยังไม่มีข้อมูลในช่วงนี้', 'ลองเปลี่ยนช่วงเวลาหรือล้างตัวกรอง'],
    'no-source': ['ยังไม่มีแหล่งข้อมูล', 'ตรวจสอบแหล่งข้อมูลและเริ่มเก็บข้อมูลก่อน'],
    error: ['โหลดข้อมูลไม่สำเร็จ', 'ตรวจสอบการเชื่อมต่อ แล้วลองโหลดหน้าใหม่']
  };

  function text(value, fallback) {
    // Missing data is never a measured zero, including caller-supplied labels.
    return typeof value === 'string' && value.trim() && !/^[0๐]+$/.test(value.trim())
      ? value : fallback;
  }

  function set(target, state, opts) {
    if (state !== 'ready' && !Object.prototype.hasOwnProperty.call(messages, state)) {
      throw new TypeError('Unknown Harken state: ' + state);
    }
    var host = typeof target === 'string' ? document.querySelector(target) : target;
    if (!host || host.nodeType !== 1) return;
    opts = opts || {};
    var prior = saved.get(host);
    if (state === 'ready') {
      if (prior) {
        host.replaceChildren(prior.nodes);
        if (prior.busy === null) host.removeAttribute('aria-busy');
        else host.setAttribute('aria-busy', prior.busy);
        saved.delete(host);
      }
      host.setAttribute('data-state', 'ready');
      return;
    }
    if (!prior) {
      prior = { nodes: document.createDocumentFragment(), busy: host.getAttribute('aria-busy') };
      while (host.firstChild) prior.nodes.appendChild(host.firstChild);
      saved.set(host, prior);
    }
    var ui = document.createElement('div');
    ui.className = 'hstate hstate-' + state;
    ui.setAttribute('role', 'status');
    ui.setAttribute('aria-live', 'polite');
    ui.setAttribute('aria-atomic', 'true');
    ui.setAttribute('data-state', state);
    var message = document.createElement('strong');
    message.className = 'hstate-message';
    message.textContent = text(opts.message, messages[state][0]);
    ui.appendChild(message);
    var detail = opts.detail === '' ? '' : text(opts.detail, messages[state][1]);
    if (detail) {
      var hint = document.createElement('span');
      hint.className = 'hstate-detail';
      hint.textContent = detail;
      ui.appendChild(hint);
    }
    var root = ui;
    // Keep valid table structure; exactly one state div inside a spanning cell.
    if (/^(TBODY|THEAD|TFOOT|TABLE)$/.test(host.tagName)) {
      var row = document.createElement('tr');
      row.className = 'hstate-row';
      var cell = document.createElement('td');
      var table = host.closest('table');
      var headings = table && table.querySelector('thead tr');
      cell.colSpan = headings ? Math.max(1, Array.prototype.reduce.call(headings.cells,
        function (n, c) { return n + c.colSpan; }, 0)) : 1;
      cell.appendChild(ui);
      row.appendChild(cell);
      root = row;
    } else if (host.tagName === 'TR') {
      root = document.createElement('td');
      root.colSpan = Math.max(1, prior.nodes.children.length);
      root.appendChild(ui);
    }
    host.replaceChildren(root);
    host.setAttribute('data-state', state);
    host.setAttribute('aria-busy', state === 'loading' ? 'true' : 'false');
  }

  function stamp(value) {
    var host = document.querySelector('#stamp');
    if (!host) return;
    var date = value instanceof Date ? value : new Date(value);
    if (value == null || value === '' || isNaN(date.getTime())) {
      host.textContent = 'ยังไม่ทราบเวลาอัปเดต';
      host.removeAttribute('datetime');
      host.removeAttribute('title');
      return;
    }
    host.textContent = new Intl.DateTimeFormat('th-TH', {
      timeZone: 'Asia/Bangkok', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
    }).format(date);
    host.setAttribute('datetime', date.toISOString());
    host.title = 'อัปเดตล่าสุด · ' + new Intl.DateTimeFormat('th-TH', {
      timeZone: 'Asia/Bangkok', dateStyle: 'medium', timeStyle: 'medium'
    }).format(date) + ' (เวลาประเทศไทย)';
  }

  window.HarkenStates = { set: set, stamp: stamp };
})();
