/* Preset search page: one keyword, six recipes, real runs behind them. */
const $ = (s, r = document) => r.querySelector(s);
const PLAT_TH = {x: 'X', tiktok: 'TikTok', threads: 'Threads', facebook: 'Facebook'};
let META = {presets: [], platforms: [], windows: {}, busy: []};
let chosen = new Set();

function say(msg, bad = false) {
  $('#bannerMsg').textContent = msg;
  $('#banner').classList.toggle('show', true);
  $('#banner').style.background = bad ? '#FEE2E2' : '';
  $('#banner').style.color = bad ? '#991B1B' : '';
}

async function loadMeta() {
  const r = await fetch('/api/presets', {cache: 'no-store'});
  META = await r.json();
  chosen = new Set(META.platforms);

  $('#win').innerHTML = Object.entries(META.windows)
    .map(([k, v]) => `<option value="${k}">${v}</option>`).join('');
  $('#plats').innerHTML = META.platforms.map(p =>
    `<label><input type="checkbox" value="${p}" checked> ${PLAT_TH[p] || p}</label>`).join('');
  $('#plats').addEventListener('change', e => {
    const v = e.target.value;
    e.target.checked ? chosen.add(v) : chosen.delete(v);
  });
  render();
}

function render() {
  const kw = $('#kw').value.trim();
  $('#cards').innerHTML = META.presets.map(p => {
    const busy = p.platforms.filter(x => META.busy.includes(x));
    return `<div class="card pcard" data-id="${p.id}">
      <div class="card-head"><h3>${p.title}</h3></div>
      <div class="card-body pcard">
        <p>${p.desc}</p>
        <p style="font-size:13px">แพลตฟอร์ม: ${p.platforms.map(x => PLAT_TH[x] || x).join(' · ')}</p>
        <div class="trap">⚠ ${p.trap}</div>
        ${p.extra ? `<input class="extra" type="text" placeholder="${p.extra_label || p.extra}" data-extra="${p.id}">` : ''}
        <div class="row">
          <button class="btn" data-run="${p.id}" ${busy.length ? 'disabled' : ''}>เริ่มค้น</button>
          <button class="btn-quiet" data-cmd="${p.id}" type="button">คัดลอกคำสั่ง</button>
          ${busy.length ? `<span class="busy">กำลังรัน: ${busy.join(', ')}</span>` : ''}
        </div>
      </div>
    </div>`;
  }).join('');
  $('#cardCount') && ($('#cardCount').textContent = META.presets.length);
  $('#kw').placeholder = kw ? kw : 'พิมพ์คำค้นก่อน แล้วกดเริ่มค้น';
}

async function run(presetId) {
  const keyword = $('#kw').value.trim();
  if (!keyword) { say('พิมพ์คำค้นก่อนครับ', true); $('#kw').focus(); return; }
  const extraEl = document.querySelector(`[data-extra="${presetId}"]`);
  const params = new URLSearchParams({
    preset: presetId, keyword, platforms: [...chosen].join(','),
    window: $('#win').value, extra: extraEl ? extraEl.value.trim() : ''
  });
  const r = await fetch('/api/presets/run?' + params, {method: 'POST'});
  const body = await r.json().catch(() => ({}));
  if (!r.ok) { say(body.detail || 'เริ่มไม่สำเร็จ', true); return; }
  say(`เริ่มแล้ว ${body.started.length} งาน — ผลจะเข้าแดชบอร์ดเองเมื่อค้นเสร็จ`);
  loadMeta(); poll();
}

async function poll() {
  const r = await fetch('/api/presets/jobs', {cache: 'no-store'});
  const {jobs} = await r.json();
  $('#stamp').textContent = new Date().toLocaleTimeString('th-TH');
  $('#liveDot').classList.add('on');
  META.busy = jobs.filter(j => j.state === 'running').map(j => j.platform);
  $('#busyNote').textContent = META.busy.length
    ? 'กำลังค้น: ' + META.busy.join(', ') + ' (ปุ่มของแพลตฟอร์มนั้นจะถูกล็อกจนจบ)' : '';
  if (!jobs.length) { $('#jobs').innerHTML = '<div class="empty">ยังไม่มีงาน</div>'; return; }
  $('#jobs').innerHTML = jobs.map(j => `<div class="job">
      <span class="st ${j.state === 'running' ? 'run' : 'done'}">${j.state === 'running' ? 'กำลังค้น' : 'จบแล้ว'}</span>
      <div class="meta">
        <div class="t">${j.title} · ${PLAT_TH[j.platform] || j.platform} · “${esc(j.keyword)}”</div>
        <div class="s">${j.result ? esc(j.result) : esc(j.tail.slice(-1)[0] || '—')}</div>
        <pre>${esc(j.tail.join('\n'))}</pre>
      </div>
    </div>`).join('');
}

const esc = s => String(s ?? '').replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));

document.addEventListener('click', e => {
  const runId = e.target?.dataset?.run;
  if (runId) return run(runId);
  const cmdId = e.target?.dataset?.cmd;
  if (cmdId) {
    const p = META.presets.find(x => x.id === cmdId);
    const kw = $('#kw').value.trim() || '<KEYWORD>';
    const text = `# ${p.title}\ncurl -X POST "localhost:8000/api/presets/run?preset=${cmdId}&keyword=${encodeURIComponent(kw)}&platforms=${p.platforms.join(',')}&window=${p.window}"`;
    navigator.clipboard?.writeText(text);
    say('คัดลอกคำสั่งแล้ว');
  }
  const chip = e.target?.closest?.('.chip');
  if (chip) { $('#kw').value = chip.dataset.kw; render(); }
});

$('#kw').addEventListener('input', render);
$('#runAll').addEventListener('click', () => META.presets.forEach(p => run(p.id)));
$('#kw').addEventListener('keydown', e => { if (e.key === 'Enter') run(META.presets[0].id); });

document.addEventListener('DOMContentLoaded', function () {
  var keyword = new URLSearchParams(location.search).get('kw');
  var input = document.getElementById('kw');
  if (input && keyword && keyword.trim()) {
    input.value = keyword.trim();
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }
});

loadMeta().then(poll);
setInterval(poll, 2000);
