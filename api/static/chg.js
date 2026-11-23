/* Overview changes: include after sl.css with chg.css; no other module required. */
(function () {
  'use strict';

  function init() {
    var host = document.getElementById('chgBar');
    if (!host || host.dataset.chgInitialized) return;
    host.dataset.chgInitialized = 'true';
    host.hidden = true;
    host.setAttribute('role', 'group');
    host.setAttribute('aria-label', 'คำที่เปลี่ยนใน 7 วัน เทียบกับ 7 วันก่อนหน้า');

    fetch('/api/terms-changes?days=7&limit=5', { cache: 'no-store' })
      .then(function (response) {
        if (!response.ok) throw new Error('ดึงข้อมูลการเปลี่ยนแปลงไม่สำเร็จ');
        return response.json();
      })
      .then(function (data) {
        var terms = data && Array.isArray(data.terms) ? data.terms : [];
        terms = terms.filter(function (row) {
          return row && typeof row.term === 'string' && row.term.trim() &&
            Number.isFinite(row.n) && row.n >= 0 &&
            Number.isFinite(row.prev) && row.prev >= 0 && Number.isFinite(row.chg);
        }).slice(0, 5);
        if (!terms.length) return;

        var content = document.createDocumentFragment();
        var lead = document.createElement('span');
        lead.className = 'chgbar__lead';
        lead.textContent = 'เปลี่ยนจากสัปดาห์ก่อน';
        content.appendChild(lead);

        terms.forEach(function (row) {
          var direction = row.chg > 0 ? 'pos' : row.chg < 0 ? 'neg' : 'neu';
          var percent = Math.min(999, Math.round(Math.abs(row.chg) / Math.max(row.prev, 1) * 100));
          var change = row.prev === 0
            ? '+' + row.n.toLocaleString('th-TH') + ' ใหม่'
            : row.chg === 0 ? 'ไม่เปลี่ยน' : (row.chg > 0 ? '▲ ' : '▼ ') + percent + '%';
          var button = document.createElement('button');
          button.type = 'button';
          button.className = 'chgbar__chip chgbar__chip--' + direction;
          button.title = 'กรองคำว่า ' + row.term + ' · ' + row.n.toLocaleString('th-TH') +
            ' โพสต์ · ก่อนหน้า ' + row.prev.toLocaleString('th-TH') + ' โพสต์';
          button.setAttribute('aria-label', 'กรองคำว่า ' + row.term + ' · ' +
            (row.prev === 0 ? change : row.chg === 0 ? change :
              (row.chg > 0 ? 'เพิ่มขึ้น ' : 'ลดลง ') + percent + '%') +
            ' · ' + row.n.toLocaleString('th-TH') + ' โพสต์');

          var term = document.createElement('span');
          term.className = 'chgbar__term';
          term.textContent = row.term;
          var delta = document.createElement('span');
          delta.className = 'chgbar__delta';
          delta.textContent = change;
          button.appendChild(term);
          button.appendChild(delta);
          button.addEventListener('click', function () {
            document.dispatchEvent(new CustomEvent('harken:filter', { detail: { term: row.term } }));
          });
          content.appendChild(button);
        });

        host.replaceChildren(content);
        host.classList.add('chgbar--ready');
        host.hidden = false;
      })
      .catch(function () {
        // A failed request must not invent zero growth or leave an empty shell.
        host.hidden = true;
        host.classList.remove('chgbar--ready');
        host.replaceChildren();
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
}());
