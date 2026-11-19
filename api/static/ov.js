/* Overview page (/) — the whole listener in one readable screen.
 * Every number here closes over ALL search runs. Single-zone numbers live at
 * /search?run=…, which this page only ever links to. */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var HC = window.HarkenCharts;

  var PLAT = { threads: 'Threads', facebook: 'Facebook', fbfeed: 'Facebook (ฟีด)', tiktok: 'TikTok', x: 'X (Twitter)',
    news: 'ข่าวเว็บ', other: 'อื่น ๆ' };
  var SENT = { pos: { n: 'บวก', e: '😊' }, neu: { n: 'กลาง', e: '😐' },
    neg: { n: 'ลบ', e: '😠' }, none: { n: 'ไม่ระบุ', e: '·' } };
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
  var fmt = new Intl.DateTimeFormat('th-TH', { timeZone: 'Asia/Bangkok', day: '2-digit',
    month: 'short', hour: '2-digit', minute: '2-digit' });
  var clock = function (iso) {
    var d = new Date(iso);
    return isNaN(d) ? String(iso || '—').slice(0, 16).replace('T', ' ') : fmt.format(d);
  };
  var day = function (iso) {
    var d = new Date(iso);
    return isNaN(d) ? String(iso || '').slice(0, 10) : d.toISOString().slice(0, 10);
  };
  function getJSON(url) {
    return fetch(url, { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error(url + ' → ' + r.status);
      return r.json();
    });
  }

  var V = { runs: [], stats: null, trend: null, dims: null, gran: 'day',
    zq: '', zplat: '', zsort: 'recent' };

  /* ── KPI ──────────────────────────────────────────────── */
  var prevSpark = {};
  function spark(slot, values, color) {
    var host = $(slot);
    if (!host) return;
    var sig = values.join(',');
    if (prevSpark[slot] === sig) return;
    prevSpark[slot] = sig;
    if (HC) HC.render('slSpark', host, values.slice(-14), { color: color });
  }

  function paintKpis(st) {
    var eng = st.engagement || { likes: 0, replies: 0, reposts: 0 };
    var total = st.total || 0;
    $('#kPosts').textContent = num(total);
    $('#kComments').textContent = num(st.comments || 0);
    $('#kEng').textContent = num((eng.likes || 0) + (eng.replies || 0) + (eng.reposts || 0));
    $('#kAuthors').textContent = num((st.authors_total || (st.top_authors || []).length || 0));
    $('#kZones').textContent = num((V.runs || []).filter(function (r) {
      return (r.kind || 'social') === 'social';
    }).length);

    var done = (st.translated || 0) + (st.native_th || 0);
    var pct = total ? Math.round(done / total * 100) : 0;
    $('#kPostsF').textContent = 'อ่านได้ ' + num(done) + ' · ' + pct + '%';
    $('#kCommentsF').textContent = 'จาก ' + num(st.posts_with_comments || 0) + ' โพสต์';
    $('#kEngF').textContent = 'ไลก์ ' + num(eng.likes) + ' · ตอบ ' + num(eng.replies) +
      ' · รี ' + num(eng.reposts);
    $('#kAuthorsF').textContent = 'ผู้โพสต์ในภาพรวม';

    var days = (st.by_day || []).slice().sort(function (a, b) { return String(a.d).localeCompare(String(b.d)); });
    var series = days.map(function (d) { return d.n; });
    // only the post KPI has a real per-day series; the others would show a lie
    spark('#sPosts', series, 'var(--violet)');
  }

  /* ── trend ────────────────────────────────────────────── */
  function paintTrend(d) {
    V.trend = d;
    if (!HC) return;
    if (d && d.labels && d.labels.length) {
      HC.render('slLine', $('#chartTrend'), d);
    } else {
      $('#chartTrend').innerHTML =
        '<div class="empty"><b>ยังไม่มีข้อมูลตามเวลา</b>โพสต์ยังไม่มีวันที่อ่านได้</div>';
    }
    var sum = (d.cur || []).reduce(function (a, b) { return a + b; }, 0);
    var prev = (d.prev || []).reduce(function (a, b) { return a + b; }, 0);
    $('#trendSay').textContent = d.labels.length
      ? 'ทุกโซนรวมกัน · ' + num(sum) + ' โพสต์ในช่วงนี้ (ก่อนหน้า ' + num(prev) + ')'
      : 'ยังไม่มีข้อมูล';
    $('#trendNote').textContent = 'เส้นทึบ = ' + (d.gran === 'hour' ? 'ชั่วโมง' : 'วัน') +
      'ล่าสุด · เส้นประ = ช่วงก่อนหน้า · แตะจุดเพื่อดูโพสต์ของช่วงนั้น';
  }

  /* ── sentiment ────────────────────────────────────────── */
  function paintSent(st) {
    var rows = (st.by_sentiment || []).filter(function (r) { return r.n > 0; });
    var mix = {}; rows.forEach(function (r) { mix[r.s] = r.n; });
    var tot = Math.max(1, rows.reduce(function (a, b) { return a + b.n; }, 0));
    if (!rows.length) {
      $('#sentBars').innerHTML = '<div class="chint">ยังไม่จำแนกอารมณ์ — ' +
        'ระบบจะจำแนกให้อัตโนมัติหลังแปลข้อความเสร็จ</div>';
      $('#sentHint').textContent = 'ยังไม่จำแนก';
      return;
    }
    $('#sentBars').innerHTML = ['pos', 'neu', 'neg'].map(function (k) {
      var n = mix[k] || 0, pct = Math.round(n / tot * 100);
      return '<div class="bar ' + k + '"><span class="lab">' + SENT[k].e + ' ' + SENT[k].n + '</span>' +
        '<span class="track"><span class="fill" style="width:' + pct + '%"></span></span>' +
        '<span class="val num">' + num(n) + ' · ' + pct + '%</span></div>';
    }).join('');
    var top = rows.slice().sort(function (a, b) { return b.n - a.n; })[0];
    // percentages are of the classified subset — say so, or 5%+8%+2% looks broken
    var classified = rows.reduce(function (a, b) { return a + b.n; }, 0);
    $('#sentHint').textContent = classified
      ? ('จำแนกแล้ว ' + num(classified) + ' จาก ' + num(st.total) + ' โพสต์' +
         (top ? ' · ส่วนใหญ่' + (SENT[top.s] || {}).n : ''))
      : 'ยังไม่จำแนก';
  }

  /* ── platform donut ───────────────────────────────────── */
  function paintPlat(st) {
    var items = (st.by_platform || []).map(function (p) {
      return { platform: p.platform, label: PLAT[p.platform] || p.platform, n: p.n };
    });
    if (HC) HC.render('slDonut', $('#chartDonut'), items);
  }

  /* ── zones table ──────────────────────────────────────── */
  function zoneRow(r) {
    var plats = (r.platforms || []).map(function (p) { return PLAT[p] || p; }).join(' + ');
    var from = (r.first_iso || '').slice(0, 10), to = (r.last_iso || '').slice(0, 10);
    var cov = r.comments_coverage;
    return '<tr class="row" data-zone="' + esc(r.run) + '">' +
      '<td data-l="โซน"><div class="who" title="' + esc(r.label) + '">' + esc(r.label || r.run) + '</div>' +
      '<div class="chint">' + esc(r.run) + '</div></td>' +
      '<td data-l="แพลตฟอร์ม"><span class="pilltag plat">' + esc(plats || '—') + '</span></td>' +
      '<td data-l="โพสต์" style="text-align:right" class="num"><b>' + num(r.posts) + '</b></td>' +
      '<td data-l="คอมเมนต์" style="text-align:right" class="num">' + num(r.comments_stored) +
      (cov != null ? '<div class="chint">' + cov + '% ของที่แพลตฟอร์มรายงาน</div>' : '') + '</td>' +
      '<td data-l="ช่วง"><span class="when">' + esc(from || '—') + ' → ' + esc(to || '—') + '</span></td>' +
      '<td data-l="สถานะ"><span class="pilltag ' + (r.status === 'complete' ? 'pos' :
        r.status === 'missing' || r.status === 'empty' ? 'neg' : 'neu') + '">' +
      esc(STL[r.status] || r.status || '—') + '</span></td>' +
      '<td data-l="เปิด"><a href="/search?run=' + encodeURIComponent(r.run) + '">เปิดโซน ↗</a></td></tr>';
  }

  function paintZones() {
    var all = (V.runs || []).filter(function (r) { return (r.kind || 'social') === 'social'; });
    $('#zoneCount').textContent = num(all.length) + ' โซน';
    var q = V.zq.trim().toLowerCase();
    var rows = all.filter(function (r) {
      if (V.zplat && (r.platforms || []).indexOf(V.zplat) < 0) return false;
      if (!q) return true;
      var hay = (r.label + ' ' + r.run + ' ' + (r.queries || []).join(' ') + ' ' +
        (r.platforms || []).join(' ')).toLowerCase();
      return hay.indexOf(q) >= 0;
    });
    var sorters = {
      recent: function (a, b) { return String(b.last_iso || '').localeCompare(String(a.last_iso || '')); },
      posts: function (a, b) { return (b.posts || 0) - (a.posts || 0); },
      comments: function (a, b) { return (b.comments_stored || 0) - (a.comments_stored || 0); },
      name: function (a, b) { return String(a.label || '').localeCompare(String(b.label || ''), 'th'); }
    };
    rows.sort(sorters[V.zsort] || sorters.recent);
    $('#zoneShown').textContent = rows.length === all.length ? '' : 'แสดง ' + num(rows.length) + ' จาก ' + num(all.length);
    $('#zoneRows').innerHTML = rows.length ? rows.map(zoneRow).join('')
      : '<tr><td colspan="7"><div class="empty"><b>ไม่พบโซนที่ตรงกับคำค้น</b>ลองล้างตัวกรอง</div></td></tr>';
  }

  /* ── issues & terms ───────────────────────────────────── */
  function paintIssues(d) {
    var rows = d.issues || [];
    var top = Math.max(1, Math.max.apply(null, rows.map(function (r) { return r.n_posts || 0; }).concat([1])));
    $('#issues').innerHTML = rows.length ? rows.map(function (t, i) {
      var bits = [num(t.n_posts) + ' โพสต์', 'ก่อนหน้า ' + num(t.prev_posts)];
      if (t.top_author) bits.push('@' + t.top_author);
      return '<div class="issue" style="cursor:default;grid-template-columns:22px minmax(0,1fr) 54px">' +
        '<span class="rank">' + String(i + 1).padStart(2, '0') + '</span>' +
        '<span><span class="nm">' + esc(t.label) + '</span>' +
        '<span class="meta">' + esc(bits.join(' · ')) + '</span>' +
        '<span class="prog"><i style="width:' + Math.round((t.n_posts || 0) / top * 100) + '%"></i></span></span>' +
        '<span class="chg' + (t.chg === 0 ? ' flat' : '') + '">' + (t.chg > 0 ? '+' : '') + num(t.chg) + '</span></div>';
    }).join('') : '<div class="empty"><b>ยังไม่มีประเด็นซ้ำ</b>ต้องมีคำที่พูดถึงอย่างน้อย 2 โพสต์</div>';
    $('#issuesSay').textContent = rows.length
      ? num(rows.length) + ' ประเด็นจาก ' + num(d.window_days || 7) + ' วันล่าสุด' : 'ยังไม่มีข้อมูล';
  }

  function paintTerms(st) {
    var rows = (st.top_terms || []).slice(0, 18);
    $('#terms').innerHTML = rows.length ? rows.map(function (t) {
      return '<button type="button" class="term" data-term="' + esc(t.term) + '">' + esc(t.term) +
        ' <span class="n num">' + num(t.n) + '</span></button>';
    }).join('') : '<span class="chint">ยังไม่มีคำที่ถูกพูดถึงซ้ำ</span>';
  }

  /* ── top posts ────────────────────────────────────────── */
  function paintTopPosts(d) {
    var posts = (d.posts || []).slice().sort(function (a, b) {
      return ((b.likes || 0) + (b.replies || 0) + (b.reposts || 0)) -
        ((a.likes || 0) + (a.replies || 0) + (a.reposts || 0));
    }).slice(0, 5);
    $('#topPostsHint').textContent = num(d.total || 0) + ' โพสต์ในภาพรวม';
    $('#topRows').innerHTML = posts.length ? posts.map(function (p) {
      var th = p.text_th || p.text_raw || '';
      var eng = (p.likes || 0) + (p.replies || 0) + (p.reposts || 0);
      return '<tr class="row" data-url="' + esc(p.url) + '">' +
        '<td data-l="เวลา"><span class="when">' + esc(clock(p.posted_iso)) + '</span></td>' +
        '<td data-l="ผู้โพสต์"><div class="who">@' + esc(p.author) + '</div><div class="tags">' +
        '<span class="pilltag plat">' + esc(PLAT[p.platform] || p.platform) + '</span></div></td>' +
        '<td data-l="ข้อความ"><div class="snip">' + esc(th.slice(0, 150)) + (th.length > 150 ? '…' : '') + '</div></td>' +
        '<td data-l="การมีส่วนร่วม" style="text-align:right"><b class="num">' + num(eng) + '</b>' +
        '<div class="chint">❤ ' + num(p.likes) + ' · 💬 ' + num(p.replies) + ' · 🔁 ' + num(p.reposts) + '</div></td>' +
        '<td data-l="เปิด"><a href="' + esc(p.url) + '" target="_blank" rel="noopener">เปิด ↗</a></td></tr>';
    }).join('') : '<tr><td colspan="5"><div class="empty">ยังไม่มีโพสต์</div></td></tr>';
  }

  /* ── news (separate dataset) ──────────────────────────── */
  function paintNews(d) {
    var rows = d.news || [];
    $('#newsHint').textContent = num(d.total || 0) + ' ข่าว · แยกจากโซเชียลโดยสิ้นเชิง';
    $('#newsSay').textContent = 'ไม่ถูกนับรวมกับตัวเลขโซเชียลด้านบน';
    $('#newsRows').innerHTML = rows.length ? rows.map(function (n) {
      return '<tr class="row" data-url="' + esc(n.url) + '">' +
        '<td data-l="เวลา"><span class="when">' + esc(clock(n.posted_iso)) + '</span></td>' +
        '<td data-l="แหล่งข่าว"><span class="pilltag none">' + esc(n.source || '—') + '</span></td>' +
        '<td data-l="พาดหัว"><div class="snip">' + esc((n.headline || '').slice(0, 140)) + '</div></td>' +
        '<td data-l="เปิด"><a href="' + esc(n.url) + '" target="_blank" rel="noopener">เปิด ↗</a></td></tr>';
    }).join('') : '<tr><td colspan="4"><div class="empty">ยังไม่มีข่าวในคลัง</div></td></tr>';
  }

  /* ── day card ─────────────────────────────────────────── */
  function showDay(iso, idx) {
    if (!iso || !V.trend) return;
    var card = $('#dayCard');
    var label = (V.trend.labels || [])[idx] || iso;
    var n = (V.trend.cur || [])[idx] || 0;
    card.style.display = '';
    card.classList.add('on');
    card.innerHTML = '<b>' + esc(label) + '</b>\n' + num(n) + ' โพสต์ · เปิดโซนคำค้นเพื่อดูรายละเอียด';
    card.style.left = '50%';
    card.style.top = '120px';
    getJSON('/api/posts?date_from=' + encodeURIComponent(iso) + '&date_to=' +
      encodeURIComponent(iso) + '&limit=3').then(function (d) {
      var names = (d.posts || []).slice(0, 3).map(function (p) {
        return '@' + p.author;
      });
      if (names.length) card.innerHTML += '\n' + esc(names.join(' · '));
    }).catch(function () {});
    clearTimeout(showDay._t);
    showDay._t = setTimeout(function () { card.classList.remove('on'); card.style.display = 'none'; }, 4200);
  }

  /* ── load ─────────────────────────────────────────────── */
  function load() {
    var trendUrl = '/api/trend?gran=' + V.gran + '&days=7';
    return Promise.all([
      getJSON('/api/stats'),
      getJSON(trendUrl),
      getJSON('/api/dims?days=7'),
      getJSON('/api/issues?days=7&limit=6'),
      getJSON('/api/runs'),
      getJSON('/api/posts?limit=60'),
      getJSON('/api/news?limit=5&days=365')
    ]).then(function (r) {
      V.stats = r[0];
      V.runs = (r[4].runs || []);
      paintKpis(r[0]);
      paintTrend(r[1]);
      paintSent(r[0]);
      paintPlat(r[0]);
      paintIssues(r[3]);
      paintTerms(r[0]);
      paintZones();
      paintTopPosts(r[5]);
      paintNews(r[6]);
      if (HC && r[2] && r[2].hour_profile) HC.render('slHours', $('#chartHours'), r[2].hour_profile);
      var hp = (r[2] && r[2].hour_profile) || { hours: [], counts: [] };
      var peak = hp.counts && hp.counts.length ? hp.counts.indexOf(Math.max.apply(null, hp.counts)) : -1;
      $('#hoursHint').textContent = peak >= 0 ? ('คึกคักสุด ' + hp.hours[peak] + ':00 น.') : '—';
      $('#stamp').textContent = new Date().toLocaleTimeString('th-TH', { timeZone: 'Asia/Bangkok' });
      $('#liveDot').style.background = 'var(--pos)';
      $('#banner').classList.remove('on');
    }).catch(function (e) {
      $('#banner').classList.add('on');
      $('#bannerMsg').textContent = 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ — ' + e.message;
      $('#liveDot').style.background = 'var(--neg)';
    });
  }

  /* ── wiring ───────────────────────────────────────────── */
  $('#retry').addEventListener('click', load);
  $('#segDay').addEventListener('click', function () {
    V.gran = 'day';
    this.setAttribute('aria-pressed', 'true');
    $('#segHour').setAttribute('aria-pressed', 'false');
    load();
  });
  $('#segHour').addEventListener('click', function () {
    V.gran = 'hour';
    this.setAttribute('aria-pressed', 'true');
    $('#segDay').setAttribute('aria-pressed', 'false');
    load();
  });
  var zt;
  $('#zq').addEventListener('input', function (e) {
    clearTimeout(zt);
    var v = e.target.value;
    zt = setTimeout(function () { V.zq = v; paintZones(); }, 200);
  });
  $('#zplat').addEventListener('change', function (e) { V.zplat = e.target.value; paintZones(); });
  $('#zsort').addEventListener('change', function (e) { V.zsort = e.target.value; paintZones(); });

  document.addEventListener('click', function (e) {
    var z = e.target.closest('tr[data-zone]');
    if (z && !e.target.closest('a')) { window.location = '/search?run=' + encodeURIComponent(z.dataset.zone); return; }
    var p = e.target.closest('tr[data-url]');
    if (p && !e.target.closest('a')) { window.open(p.dataset.url, '_blank', 'noopener'); return; }
    var term = e.target.closest('.term');
    if (term) {
      V.zq = term.getAttribute('data-term');
      $('#zq').value = V.zq;
      paintZones();
      $('#zones').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });

  window.addEventListener('sl:act', function (e) {
    var d = e.detail || {};
    if (d.act === 'day') { showDay(d.day, Number(d.idx)); return; }
    if (d.act === 'platform' && d.platform) {
      V.zplat = d.platform;
      $('#zplat').value = d.platform;
      paintZones();
      $('#zones').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });

  load();
  setInterval(load, 5000);
})();
