/* Tools page — data operations only. Analysis lives on / and /search, so this
 * page never repeats a chart or a KPI: coverage, review queue, clearing, export. */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var PLAT = { threads: 'Threads', facebook: 'Facebook', fbfeed: 'Facebook (ฟีด)', tiktok: 'TikTok',
    news: 'ข่าวเว็บ', other: 'อื่น ๆ' };
  var STL = { complete: 'ครบ', partial: 'กำลังเก็บ', empty: 'ว่าง/ถูกบล็อก',
    missing: 'ไม่มีไฟล์', unknown: '—' };

  var num = function (v) {
    return (v === null || v === undefined || v === '') ? '0' : Number(v).toLocaleString('th-TH');
  };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  function getJSON(url, opts) {
    return fetch(url, opts || { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error(url + ' → ' + r.status);
      return r.json();
    });
  }

  var runs = [];

  /* ── coverage table ───────────────────────────────────── */
  function covRow(r) {
    var plats = (r.platforms || []).map(function (p) { return PLAT[p] || p; }).join(' + ');
    var stored = r.comments_stored || 0, reported = r.comments_reported || 0;
    var cov = r.comments_coverage;
    var covTxt = reported
      ? (num(stored) + ' / ' + num(reported) + (cov != null ? ' (' + cov + '%)' : ''))
      : (num(stored) + ' / –');
    var caveat = r.note || (reported ? '' : 'โพสต์ไม่รายงานจำนวนคอมเมนต์');
    var st = r.status || 'unknown';
    var tone = st === 'complete' ? 'pos' : (st === 'missing' || st === 'empty') ? 'neg' : 'neu';
    return '<tr class="row" data-zone="' + esc(r.run) + '">' +
      '<td data-l="โซน"><div class="who" title="' + esc(r.label) + '">' + esc(r.label || r.run) +
      '</div><div class="chint">' + esc(r.run) + '</div></td>' +
      '<td data-l="แพลตฟอร์ม"><span class="pilltag plat">' + esc(plats || '—') + '</span></td>' +
      '<td data-l="โพสต์" style="text-align:right"><b class="num">' + num(r.posts) + '</b></td>' +
      '<td data-l="คอมเมนต์" style="text-align:right" class="num">' + covTxt +
      (caveat ? '<div class="chint">' + esc(caveat) + '</div>' : '') + '</td>' +
      '<td data-l="สถานะ"><span class="pilltag ' + tone + '">' + esc(STL[st] || st) + '</span></td>' +
      '<td data-l="จัดการ">' + ((r.kind || 'social') === 'news'
        ? '<a href="/#news">ดูในหน้าข่าว ↗</a>'
        : '<a href="/search?run=' + encodeURIComponent(r.run) + '">เปิดโซน ↗</a>') + '</td></tr>';
  }

  function paintCoverage() {
    $('#covRows').innerHTML = runs.length ? runs.map(covRow).join('')
      : '<tr><td colspan="6"><div class="empty">ยังไม่มีชุดข้อมูล</div></td></tr>';
    var social = runs.filter(function (r) { return (r.kind || 'social') === 'social'; });
    $('#covHint').textContent = num(social.length) + ' โซนโซเชียล · ' +
      num(runs.length) + ' ชุดข้อมูลทั้งหมด';
  }

  function paintZonePicker() {
    var social = runs.filter(function (r) { return (r.kind || 'social') === 'social'; });
    $('#zoneSel').innerHTML = '<option value="">— เลือกโซน —</option>' + social.map(function (r) {
      return '<option value="' + esc(r.run) + '">' + esc(r.label || r.run) +
        ' (' + num(r.posts) + ')</option>';
    }).join('');
  }

  /* ── review queue ─────────────────────────────────────── */
  function revItem(p) {
    var th = p.text || p.text_th || p.text_raw || '';
    return '<div class="revitem" data-url="' + esc(p.url) + '" style="border:1px solid var(--line);' +
      'border-radius:14px;padding:12px 14px;margin-bottom:10px;background:#fff">' +
      '<div class="tags" style="margin:0 0 6px"><span class="pilltag plat">' +
      esc(PLAT[p.platform] || p.platform) + '</span>' +
      '<span class="pilltag none">' + esc(p.run || '') + '</span>' +
      (p.noise_state ? '<span class="pilltag neu">' + esc(p.noise_state) + '</span>' : '') + '</div>' +
      '<div class="snip">' + esc(th.slice(0, 200)) + '</div>' +
      '<div class="chint" style="margin-top:6px">@' + esc(p.author || '—') +
      (p.noise_why ? ' · ' + esc(p.noise_why) : '') + '</div>' +
      '<div style="display:flex;gap:8px;margin-top:10px;flex-wrap:wrap">' +
      '<button class="btn" type="button" data-decide="confirmed">เก็บไว้</button>' +
      '<button class="btn" type="button" data-decide="rejected">ตัดออก</button>' +
      '<a class="btn" href="' + esc(p.url) + '" target="_blank" rel="noopener">เปิดโพสต์ ↗</a></div></div>';
  }

  function paintReview(d) {
    var items = d.items || [];
    $('#revMeta').textContent = num(d.pending || 0) + ' รายการรอทบทวน';
    $('#revSay').textContent = items.length
      ? 'แสดง ' + num(items.length) + ' จาก ' + num(d.pending || items.length) + ' รายการ'
      : 'ไม่มีโพสต์ที่ระบบไม่แน่ใจ';
    $('#revList').innerHTML = items.length ? items.map(revItem).join('')
      : '<div class="empty"><b>ไม่มีรายการรอทบทวน</b>ระบบจำแนกโพสต์ทั้งหมดแล้ว</div>';
  }

  /* ── load ─────────────────────────────────────────────── */
  function load() {
    return Promise.all([
      getJSON('/api/runs'), getJSON('/api/review?state=pending&limit=30'), getJSON('/api/stats')
    ]).then(function (r) {
      runs = r[0].runs || [];
      paintCoverage();
      paintZonePicker();
      paintReview(r[1]);
      var st = r[2];
      $('#newsCount').textContent = num(st.news_total || 0);
      $('#clearNews').disabled = !(st.news_total > 0);
      $('#allSummary').textContent = 'โซเชียล ' + num(st.total) + ' โพสต์ · ' +
        num(st.comments) + ' คอมเมนต์ · ข่าวเว็บ ' + num(st.news_total) + ' รายการ';
      $('#stamp').textContent = new Date().toLocaleTimeString('th-TH', { timeZone: 'Asia/Bangkok' });
      $('#liveDot').style.background = 'var(--pos)';
      $('#banner').classList.remove('on');
    }).catch(function (e) {
      $('#banner').classList.add('on');
      $('#bannerMsg').textContent = 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ — ' + e.message;
      $('#liveDot').style.background = 'var(--neg)';
    });
  }

  /* ── destructive actions ──────────────────────────────── */
  function busy(on) {
    ['#clearRun', '#clearAll', '#clearNews'].forEach(function (s) {
      var b = $(s);
      if (b) b.disabled = on;
    });
  }

  $('#clearRun').addEventListener('click', function () {
    var run = $('#zoneSel').value;
    var msg = $('#clearMsg');
    if (!run) { msg.textContent = 'เลือกโซนก่อน'; return; }
    var row = runs.filter(function (r) { return r.run === run; })[0] || {};
    if (!window.confirm('ลบชุด “' + (row.label || run) + '” ?\n\n' +
      '• ' + num(row.posts || 0) + ' โพสต์จะถูกลบออกจากแดชบอร์ด\n' +
      '• ไฟล์ฟีดจะถูกย้ายไป feeds_archive/ (ไม่ถูกลบ)')) return;
    busy(true);
    msg.textContent = 'กำลังลบ…';
    getJSON('/api/runs/clear?run=' + encodeURIComponent(run), { method: 'POST' })
      .then(function (d) {
        msg.textContent = 'ลบแล้ว ' + num(d.posts_deleted) + ' โพสต์';
        return load();
      }).catch(function (e) { msg.textContent = 'ลบไม่สำเร็จ: ' + e.message; })
      .then(function () { busy(false); });
  });

  $('#clearAll').addEventListener('click', function () {
    var msg = $('#clearMsg2');
    if (!window.confirm('ลบข้อมูลทั้งหมด?\n\n• โพสต์โซเชียลและข่าวเว็บทั้งหมดจะถูกลบ\n' +
      '• ไฟล์ฟีดจะถูกย้ายไป feeds_archive/ (ไม่ถูกลบ)')) return;
    busy(true);
    msg.textContent = 'กำลังลบ…';
    getJSON('/api/runs/clear?all=1', { method: 'POST' })
      .then(function (d) {
        msg.textContent = 'ลบแล้ว ' + num(d.posts_deleted) + ' โพสต์';
        return load();
      }).catch(function (e) { msg.textContent = 'ลบไม่สำเร็จ: ' + e.message; })
      .then(function () { busy(false); });
  });

  $('#clearNews').addEventListener('click', function () {
    var msg = $('#clearMsg2');
    if (!window.confirm('ลบเฉพาะข่าวเว็บ? โซเชียลจะไม่ถูกแตะต้อง')) return;
    busy(true);
    msg.textContent = 'กำลังลบข่าว…';
    getJSON('/api/news/clear', { method: 'POST' })
      .then(function (d) {
        msg.textContent = 'ลบข่าวแล้ว ' + num(d.news_deleted || 0) + ' รายการ';
        return load();
      }).catch(function (e) { msg.textContent = 'ลบไม่สำเร็จ: ' + e.message; })
      .then(function () { busy(false); });
  });

  $('#export').addEventListener('click', function () {
    window.location = '/api/export.csv';
  });
  $('#retry').addEventListener('click', load);

  document.addEventListener('click', function (e) {
    var decide = e.target.closest('[data-decide]');
    if (!decide) return;
    var box = decide.closest('.revitem');
    var url = box.dataset.url, state = decide.dataset.decide;
    decide.disabled = true;
    getJSON('/api/review?url=' + encodeURIComponent(url) + '&state=' + state, { method: 'POST' })
      .then(function () { return load(); })
      .catch(function () { decide.disabled = false; });
  });

  load();
  setInterval(function () {
    getJSON('/api/review?state=pending&limit=30').then(paintReview).catch(function () {});
  }, 15000);
})();
