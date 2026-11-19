/* Keyword-zone workspace (/search?run=…).
 * Everything on this page belongs to ONE run. The overview numbers are never
 * fetched here — that separation is the whole point of the page. */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var HC = window.HarkenCharts;

  var PLAT = { threads: 'Threads', facebook: 'Facebook', fbfeed: 'Facebook (ฟีด)', tiktok: 'TikTok',
    news: 'ข่าวเว็บ', other: 'อื่น ๆ' };
  // arrow is part of the label: the row prints dir.arrow, and a missing key
  // rendered the literal string "undefined" next to the count
  var SENT = { pos: { n: 'บวก', e: '😊', arrow: '↗' }, neu: { n: 'กลาง', e: '😐', arrow: '→' },
    neg: { n: 'ลบ', e: '😠', arrow: '↘' }, none: { n: 'ไม่ระบุ', e: '·', arrow: '–' } };

  var num = function (v) {
    return (v === null || v === undefined || v === '') ? '0' : Number(v).toLocaleString('th-TH');
  };
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var escRx = function (s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); };
  var fmt = new Intl.DateTimeFormat('th-TH', { timeZone: 'Asia/Bangkok', day: '2-digit',
    month: 'short', hour: '2-digit', minute: '2-digit' });
  var clock = function (iso) {
    var d = new Date(iso);
    return isNaN(d) ? String(iso || '—').slice(0, 16).replace('T', ' ') : fmt.format(d);
  };
  function getJSON(url) {
    return fetch(url, { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error(url + ' → ' + r.status);
      return r.json();
    });
  }

  var S = { run: '', q: '', platform: '', sentiment: '', from: '', to: '', sort: 'date',
    page: 1, per: 25, total: 0, open: new Set(), noise: false };
  var Z = null;
  var cache = {};

  function paint(slot, name, data, opts) {
    var host = $(slot);
    if (!host || !HC) return;
    var sig = slot + '|' + JSON.stringify(data || null).slice(0, 900) + '|' + (opts ? JSON.stringify(opts) : '');
    if (cache[slot] === sig) return;
    cache[slot] = sig;
    HC.render(name, host, data, opts);
  }

  /* ── filters → query string ───────────────────────────── */
  function qs() {
    var p = new URLSearchParams();
    if (S.q) p.set('q', S.q);
    if (S.platform) p.set('platform', S.platform);
    if (S.sentiment) p.set('sentiment', S.sentiment);
    if (S.from) p.set('date_from', S.from);
    if (S.to) p.set('date_to', S.to);
    if (S.run) p.set('run', S.run);
    if (S.noise) p.set('include_noise', '1');
    if (S.sort === 'likes') p.set('sort', 'likes');
    p.set('limit', String(S.per));
    p.set('offset', String((S.page - 1) * S.per));
    return p.toString();
  }

  /* ── zone header ──────────────────────────────────────── */
  function paintZone(z, st) {
    var plats = (z.platforms || []).map(function (p) { return PLAT[p] || p; });
    $('#zhLabel').textContent = z.label || z.run;
    $('#footZone').textContent = z.label || z.run;
    document.title = (z.label || z.run) + ' · โซนคำค้น · SatunEcho';
    $('#zhPlats').innerHTML = plats.map(function (p) {
      return '<span>' + esc(p) + '</span>';
    }).join('') + ((z.queries || []).length
      ? '<span>คำค้น: ' + esc(z.queries.slice(0, 4).join(' · ')) + '</span>' : '');
    var from = (z.first_iso || '').slice(0, 10), to = (z.last_iso || '').slice(0, 10);
    $('#zhNote').textContent = (z.note || 'หน้านี้แสดงเฉพาะโซนนี้ · หน้าแรกแสดงภาพรวมทุกโซน') +
      ((from && to) ? ' · ช่วงข้อมูล ' + from + ' ถึง ' + to : '');
    var eng = st.engagement || { likes: 0, replies: 0, reposts: 0 };
    $('#zoneSel').value = z.run;
  }

  /* ── section 1 · KPIs + trend + sentiment + donut ─────── */
  var sparkSig = {};
  function spark(slot, values, color) {
    var sig = (values || []).join(',');
    if (sparkSig[slot] === sig) return;
    sparkSig[slot] = sig;
    paint(slot, 'slSpark', (values || []).slice(-14), { color: color });
  }

  function paintKpis(d) {
    var st = d.stats, eng = st.engagement || { likes: 0, replies: 0, reposts: 0 };
    var days = (st.by_day || []).slice().sort(function (a, b) {
      return String(a.d).localeCompare(String(b.d));
    }).map(function (x) { return x.n; });
    var done = (st.translated || 0) + (st.native_th || 0);
    var pct = st.total ? Math.round(done / st.total * 100) : 0;

    $('#kPosts').textContent = num(st.total || 0);
    $('#kPostsF').textContent = 'อ่านได้ ' + num(done) + ' · ' + pct + '%';
    $('#kComments').textContent = num(st.comments || 0);
    $('#kCommentsF').textContent = 'จาก ' + num(st.posts_with_comments || 0) + ' โพสต์';
    $('#kEng').textContent = num((eng.likes || 0) + (eng.replies || 0) + (eng.reposts || 0));
    $('#kEngF').textContent = '❤ ' + num(eng.likes) + ' · 💬 ' + num(eng.replies) + ' · 🔁 ' + num(eng.reposts);

    // one real series only — the other KPIs are not per-day counts
    spark('#sPosts', days, 'var(--violet)');

    var w = d.window || {};
    $('#winSay').textContent = (w.from && w.to)
      ? ('ช่วง ' + String(w.from).slice(5).replace('-', '/') + ' – ' +
         String(w.to).slice(5).replace('-', '/') + ' · ' + num(w.days || 7) + ' วัน')
      : 'ทุกช่วงเวลาที่เก็บได้';
  }

  function paintTrend(tr) {
    if (!tr || !tr.labels || !tr.labels.length) {
      $('#chartTrend').innerHTML = '<div class="empty"><b>ยังไม่มีข้อมูลตามเวลา</b>โพสต์ในโซนนี้ยังไม่มีวันที่อ่านได้</div>';
      $('#trendHint').textContent = '—';
      return;
    }
    paint('#chartTrend', 'slLine', tr);
    var sum = (tr.cur || []).reduce(function (a, b) { return a + b; }, 0);
    var prev = (tr.prev || []).reduce(function (a, b) { return a + b; }, 0);
    $('#trendHint').textContent = num(sum) + ' โพสต์ · ก่อนหน้า ' + num(prev);
  }

  function paintSent(st) {
    var mix = {};
    (st.by_sentiment || []).forEach(function (r) { mix[r.s] = r.n; });
    paint('#chartMix', 'slMix', mix);
    var classified = ['pos', 'neu', 'neg'].reduce(function (a, k) { return a + (mix[k] || 0); }, 0);
    var tot = Math.max(1, classified);
    var sh = $('#sentHint');
    if (sh) sh.textContent = classified
      ? ('จำแนกแล้ว ' + num(classified) + ' จาก ' + num(st.total) + ' โพสต์') : 'ยังไม่จำแนก';
    if (!classified) {
      $('#sentBars').innerHTML = '<div class="chint">ยังไม่จำแนกอารมณ์ของโพสต์ในโซนนี้ — ' +
        'ระบบจะจำแนกให้อัตโนมัติหลังแปลข้อความเสร็จ</div>';
      return;
    }
    $('#sentBars').innerHTML = ['pos', 'neu', 'neg'].map(function (k) {
      var n = mix[k] || 0, pct = Math.round(n / tot * 100);
      return '<button type="button" class="bar ' + k + '" data-sent="' + k + '" aria-pressed="' +
        (S.sentiment === k) + '"><span class="lab">' + SENT[k].e + ' ' + SENT[k].n + '</span>' +
        '<span class="track"><span class="fill" style="width:' + pct + '%"></span></span>' +
        '<span class="val num">' + num(n) + ' · ' + pct + '%</span></button>';
    }).join('');
  }

  function paintPlat(st) {
    var items = (st.by_platform || []).map(function (p) {
      return { platform: p.platform, label: PLAT[p.platform] || p.platform, n: p.n };
    });
    paint('#chartDonut', 'slDonut', items);
  }

  /* ── section 2 · posts table ──────────────────────────── */
  function highlight(text) {
    var safe = esc(text);
    var words = [].concat(S.q ? S.q.split(/\s+/) : [])
      .map(function (w) { return String(w || '').replace(/^#/, ''); })
      .filter(function (w) { return w.length > 1; });
    if (!words.length) return safe;
    return words.reduce(function (acc, w) {
      return acc.replace(new RegExp(escRx(esc(w)), 'gi'), function (m) { return '<mark>' + m + '</mark>'; });
    }, safe);
  }

  function rowHtml(p) {
    var open = S.open.has(p.url);
    var th = p.text_th || p.text_raw || '';
    var s = SENT[p.sentiment] || null;
    var cs = p.comment_sentiment || { pos: 0, neu: 0, neg: 0 };
    var dir = SENT[p.comment_direction] || SENT.none;
    var ccount = p.comment_count || 0;
    var emos = ['pos', 'neu', 'neg'].filter(function (k) { return cs[k] > 0; })
      .map(function (k) {
        return '<span class="emo ' + k + '">' + SENT[k].e + ' ' + num(cs[k]) + '</span>';
      }).join('');

    var thread = ccount ? '<div class="thread"><div class="th"><b>' + num(ccount) + ' คอมเมนต์</b>' +
      '<span class="emo ' + dir.c + '">' + dir.e + ' ทิศทาง ' + dir.n + '</span></div>' +
      (p.comments || []).map(function (c) {
        var s2 = SENT[c.sentiment] || SENT.none;
        return '<div class="c"><div class="cm"><b>@' + esc(c.author) + '</b>' +
          '<span class="emo ' + s2.c + '">' + s2.e + ' ' + s2.n + '</span>' +
          '<span>' + esc(clock(c.posted_iso)) + '</span>' +
          '<span class="cl">❤ ' + num(c.likes) + '</span></div>' +
          '<div class="ct">' + highlight(c.text_th || c.text_raw || '') + '</div></div>';
      }).join('') + '</div>'
      : (p.replies ? '<div class="chint">💬 ' + num(p.replies) +
        ' การตอบกลับตามตัวเลขของโพสต์ — ฟีดนี้ไม่ได้เก็บข้อความ</div>' : '');

    return '<tr class="row" data-url="' + esc(p.url) + '" aria-expanded="' + open + '" tabindex="0">' +
      '<td data-l="เวลา"><span class="when">' + esc(clock(p.posted_iso)) + '</span></td>' +
      '<td data-l="ผู้โพสต์"><div class="who">@' + esc(p.author) + '</div><div class="tags">' +
      '<span class="pilltag plat">' + esc(PLAT[p.platform] || p.platform) + '</span>' +
      (s ? '<span class="pilltag ' + s.c + '">' + s.e + ' ' + esc(s.n) + '</span>' : '') +
      '</div></td>' +
      '<td data-l="ข้อความ">' + (open
        ? '<div class="full">' + highlight(th) + '</div>' + thread
        : '<div class="snip">' + highlight(th.slice(0, 230)) + (th.length > 230 ? '…' : '') + '</div>' +
          (ccount ? '<div class="chint">' + dir.e + ' ' + num(ccount) + ' คอมเมนต์</div>' : '')) + '</td>' +
      '<td data-l="ตัวชี้วัด"><div class="metrics"><span>❤ <b>' + num(p.likes) + '</b></span>' +
      '<span>💬 <b>' + num(p.replies) + '</b></span><span>🔁 <b>' + num(p.reposts) + '</b></span></div></td>' +
      '<td data-l="คอมเมนต์">' + (ccount
        ? '<div class="num"><b>' + num(ccount) + '</b> คอมเมนต์</div><div class="tags">' + emos + '</div>' +
          '<div class="chint">' + dir.arrow + ' ' + dir.n + '</div>'
        : '<div class="chint">ไม่มีข้อความคอมเมนต์</div>') + '</td>' +
      '<td data-l="เปิด"><a href="' + esc(p.url) + '" target="_blank" rel="noopener">เปิด ↗</a></td></tr>';
  }

  function loadPosts() {
    return getJSON('/api/posts?' + qs()).then(function (d) {
      S.total = d.total || 0;
      var from = S.total ? (S.page - 1) * S.per + 1 : 0;
      var to = Math.min(S.total, from + (d.posts || []).length - 1);
      $('#countHint').textContent = S.total
        ? num(from) + '–' + num(to) + ' จาก ' + num(S.total) + ' โพสต์ในโซนนี้' : 'ไม่มีรายการ';
      $('#pageInfo').textContent = 'หน้า ' + S.page + ' · ' + num(S.total) + ' รายการ';
      $('#prev').disabled = S.page <= 1;
      $('#next').disabled = S.page * S.per >= S.total;
      $('#rows').innerHTML = (d.posts || []).length ? d.posts.map(rowHtml).join('')
        : '<tr><td colspan="6"><div class="empty"><b>ไม่พบโพสต์ที่ตรงกับเงื่อนไข</b>ลองล้างตัวกรอง</div></td></tr>';
    });
  }

  function renderChips() {
    var items = [];
    if (S.q) items.push(['ค้นหา: ' + S.q, function () { S.q = ''; $('#q').value = ''; }]);
    if (S.sentiment) items.push(['อารมณ์: ' + (SENT[S.sentiment] || {}).n, function () {
      S.sentiment = ''; $('#sentSel').value = '';
    }]);
    if (S.platform) items.push(['แพลตฟอร์ม: ' + (PLAT[S.platform] || S.platform), function () {
      S.platform = ''; $('#platSel').value = '';
    }]);
    if (S.from || S.to) items.push(['ช่วง: ' + (S.from || '…') + ' → ' + (S.to || '…'), function () {
      S.from = ''; S.to = ''; $('#dFrom').value = ''; $('#dTo').value = '';
    }]);
    $('#chips').innerHTML = items.length
      ? items.map(function (it, i) {
          return '<span class="chip">' + esc(it[0]) + '<button type="button" data-chip="' + i +
            '" aria-label="ลบตัวกรอง">×</button></span>';
        }).join('') + '<button class="btn btn-quiet" type="button" id="clearAll" style="padding:5px 10px">ล้างทั้งหมด</button>'
      : '<span class="chint" style="color:var(--muted-2)">แสดงทุกโพสต์ในโซนนี้ — ยังไม่มีการกรอง</span>';
    window.__chips = items;
  }

  function refreshPosts() {
    S.page = 1;
    renderChips();
    loadPosts().catch(function () {});
  }

  /* ── zone load ────────────────────────────────────────── */
  function loadZone() {
    return getJSON('/api/search/' + encodeURIComponent(S.run) +
      '?days=7' + (S.noise ? '&include_noise=1' : '')).then(function (d) {
      Z = d;
      paintZone(d.zone || {}, d.stats || {});
      paintKpis(d);
      paintTrend(d.trend);
      paintSent(d.stats || {});
      paintPlat(d.stats || {});
      paintComments(d.comments || {});
      paintIssues(d);
      paintTerms(d.stats || {});
      paintDims(d.dims || {});
      $('#noiseCount').textContent = num((d.stats || {}).hidden_noise || 0);
      $('#noiseToggle').setAttribute('aria-pressed', String(S.noise));
      $('#stamp').textContent = new Date().toLocaleTimeString('th-TH', { timeZone: 'Asia/Bangkok' });
      $('#liveDot').style.background = 'var(--pos)';
      $('#banner').classList.remove('on');
      loadSummary().catch(function () {});
    });
  }

  /* ── section 3 · comments & reactions ─────────────────── */
  function paintComments(ci) {
    var total = ci.total || 0;
    $('#cmTotal').textContent = num(total);
    $('#cmTotalF').textContent = ci.window && ci.window.days
      ? ('ในช่วง ' + num(ci.window.days) + ' วันล่าสุด') : 'ทุกช่วงที่เก็บได้';
    $('#cmPosts').textContent = num(ci.posts || 0);
    $('#cmPostsF').textContent = total ? ('เฉลี่ย ' +
      (Math.round(total / Math.max(1, ci.posts || 1) * 10) / 10) + ' ต่อโพสต์') : '—';

    var rows = (ci.sentiment || []).slice().sort(function (a, b) { return b.n - a.n; });
    var people = ci.top_commenters || [];

    var mix = {};
    rows.forEach(function (r) { mix[r.s] = r.n; });
    paint('#cmMixChart', 'slMix', mix);
    var tot = Math.max(1, ['pos', 'neu', 'neg', 'none'].reduce(function (a, k) { return a + (mix[k] || 0); }, 0));
    $('#cmBars').innerHTML = ['pos', 'neu', 'neg', 'none'].filter(function (k) { return (mix[k] || 0) > 0; })
      .map(function (k) {
        var n = mix[k] || 0, pct = Math.round(n / tot * 100);
        return '<div class="bar ' + k + '"><span class="lab">' + SENT[k].e + ' ' + SENT[k].n + '</span>' +
          '<span class="track"><span class="fill" style="width:' + pct + '%"></span></span>' +
          '<span class="val num">' + num(n) + ' · ' + pct + '%</span></div>';
      }).join('') || '<div class="chint">ยังไม่มีคอมเมนต์ที่จำแนกได้</div>';
    $('#cmMixHint').textContent = total ? (num(total) + ' ข้อความ') : '—';

    paint('#cmPeople', 'slBars', people.slice(0, 8).map(function (p) {
      return { key: p.author, label: '@' + (p.author || '—'), value: p.n, badge: '·',
        color: 'var(--cyan)' };
    }), { act: 'author', unit: ' ข้อความ', empty: 'ยังไม่มีคอมเมนต์' });

    var per = (ci.per_post || []).slice(0, 8);
    var maxN = Math.max(1, Math.max.apply(null, per.map(function (x) { return x.n; }).concat([1])));
    $('#cmPerPost').innerHTML = per.length ? per.map(function (x, i) {
      return '<button type="button" class="rankrow" data-url="' + esc(x.url) + '">' +
        '<span class="no num">' + String(i + 1).padStart(2, '0') + '</span>' +
        '<span class="rt">' + esc('@' + (x.post_author || '—') + ' · ' + (x.text || '').slice(0, 60)) + '</span>' +
        '<span class="rv">' + num(x.n) + '</span>' +
        '<span class="bar"><i style="width:' + Math.round(x.n / maxN * 100) + '%"></i></span></button>';
    }).join('') : '<div class="empty">ยังไม่มีโพสต์ที่มีคอมเมนต์</div>';

    $('#cmTerms').innerHTML = (ci.top_terms || []).slice(0, 14).map(function (t) {
      return '<button type="button" class="term" data-term="' + esc(t.term) + '">' + esc(t.term) +
        ' <span class="n num">' + num(t.n) + '</span></button>';
    }).join('') || '<span class="chint">ยังไม่มีคำที่พูดถึงซ้ำในคอมเมนต์</span>';
  }

  function loadSummary() {
    return getJSON('/api/comments/summary?' + (S.run ? 'run=' + encodeURIComponent(S.run) + '&' : '')).then(function (d) {
      var used = d.used || 0;
      $('#sumMeta').textContent = used
        ? ('อ่าน ' + num(used) + ' คอมเมนต์' + (d.source === 'llm' ? ' · สรุปด้วยโมเดล' : ' · สรุปจากคำซ้ำ'))
        : 'ยังไม่มีข้อมูล';
      if (!used) {
        $('#sumList').innerHTML = '<div class="empty"><b>ยังไม่มีคอมเมนต์ให้สรุป</b>เก็บคอมเมนต์จากโพสต์ในโซนนี้ก่อน</div>';
        $('#sumThemes').innerHTML = '';
        return;
      }
      $('#sumList').innerHTML = (d.bullets || []).length
        ? d.bullets.map(function (b) {
            return '<div class="sumitem"><span class="dot"></span><span>' + esc(b) + '</span></div>';
          }).join('')
        : (d.themes || []).map(function (t) {
            return '<div class="sumitem"><span class="dot"></span><span>คำที่พูดถึงบ่อย: <b>' +
              esc(t.label) + '</b> (' + num(t.n) + ')</span></div>';
          }).join('') || '<div class="empty">สรุปไม่ได้ในขณะนี้</div>';
      $('#sumThemes').innerHTML = (d.themes || []).map(function (t) {
        return '<span class="tchip">' + esc(t.label) + (t.n ? ' · ' + num(t.n) : '') + '</span>';
      }).join('');
    });
  }

  /* ── section 4 · issues & terms ───────────────────────── */
  function paintIssues(d) {
    var rows = d.issues || [];
    var top = Math.max(1, Math.max.apply(null, rows.map(function (r) { return r.n_posts || 0; }).concat([1])));
    $('#issues').innerHTML = rows.length ? rows.map(function (t, i) {
      var bits = [num(t.n_posts) + ' โพสต์', 'ก่อนหน้า ' + num(t.prev_posts)];
      if (t.top_author) bits.push('@' + t.top_author);
      if (t.sentiment) {
        bits.push('😊 ' + num(t.sentiment.pos) + ' · 😐 ' + num(t.sentiment.neu) +
          ' · 😠 ' + num(t.sentiment.neg));
      }
      return '<button type="button" class="issue" data-term="' + esc(t.label) + '" aria-pressed="' +
        (S.q === t.label) + '" title="กรองเฉพาะประเด็นนี้">' +
        '<span class="rank">' + String(i + 1).padStart(2, '0') + '</span>' +
        '<span><span class="nm">' + esc(t.label) + '</span>' +
        '<span class="meta">' + esc(bits.join(' · ')) + '</span>' +
        '<span class="prog"><i style="width:' + Math.round((t.n_posts || 0) / top * 100) + '%"></i></span></span>' +
        '<span class="chg' + (t.chg === 0 ? ' flat' : '') + '">' + (t.chg > 0 ? '+' : '') + num(t.chg) +
        '</span></button>';
    }).join('') : '<div class="empty"><b>ยังไม่มีประเด็นซ้ำ</b>ต้องมีคำที่พูดถึงอย่างน้อย 2 โพสต์ในโซนนี้</div>';
    $('#issuesSay').textContent = rows.length
      ? num(rows.length) + ' ประเด็น · ' + num(d.issues_window_days || 7) + ' วันล่าสุด'
      : 'ยังไม่มีข้อมูล';
  }

  function paintTerms(st) {
    $('#terms').innerHTML = (st.top_terms || []).slice(0, 16).map(function (t) {
      return '<button type="button" class="term" data-term="' + esc(t.term) + '" aria-pressed="' +
        (S.q === t.term) + '">' + esc(t.term) + ' <span class="n num">' + num(t.n) + '</span></button>';
    }).join('') || '<span class="chint">ยังไม่มีคำที่ถูกพูดถึงซ้ำ</span>';
  }

  /* ── section 5 · dimensions ───────────────────────────── */
  function paintDims(dm) {
    var win = dm.window || {};
    $('#dimsSay').textContent = (win.from && win.to)
      ? ('ช่วง ' + String(win.from).slice(5).replace('-', '/') + ' – ' +
         String(win.to).slice(5).replace('-', '/')) : '—';
    paint('#chartHeat', 'heatmap', dm.heatmap, { width: 520 });
    paint('#chartStack', 'stackedBars', dm.platform_day, { width: 520 });
    paint('#chartArea', 'area', dm.cumulative, { width: 640 });
    paint('#chartHours', 'slHours', dm.hour_profile, { width: 640 });

    var hp = dm.hour_profile || { hours: [], counts: [] };
    var peak = (hp.counts || []).length ? hp.counts.indexOf(Math.max.apply(null, hp.counts)) : -1;
    $('#hoursHint').textContent = peak >= 0 ? ('คึกคักสุด ' + hp.hours[peak] + ':00 น.') : '—';
    $('#heatSub').textContent = dm.heatmap && dm.heatmap.max ? ('สูงสุด ' + num(dm.heatmap.max)) : '';

    // sentiment per day comes from the posts themselves — dims carries no such axis
    getJSON('/api/posts?' + (S.run ? 'run=' + encodeURIComponent(S.run) + '&' : '') +
      (S.noise ? 'include_noise=1&' : '') + 'limit=300&comments=0').then(function (d) {
      var byDay = {};
      (d.posts || []).forEach(function (p) {
        var k = String(p.posted_iso || '').slice(5, 10);
        if (!k) return;
        var b = byDay[k] || (byDay[k] = { label: k, pos: 0, neu: 0, neg: 0 });
        if (b[p.sentiment] != null) b[p.sentiment]++;
      });
      var rows = Object.keys(byDay).sort().slice(-10).map(function (k) { return byDay[k]; });
      paint('#chartStackSent', 'slStackSent', rows, { width: 520 });
    }).catch(function () {});
  }

  /* ── zone switcher ────────────────────────────────────── */
  function loadRunList() {
    return getJSON('/api/runs').then(function (d) {
      var social = (d.runs || []).filter(function (r) { return (r.kind || 'social') === 'social'; });
      var sel = $('#zoneSel');
      sel.innerHTML = social.map(function (r) {
        return '<option value="' + esc(r.run) + '">' + esc(r.label || r.run) +
          ' (' + num(r.posts) + ')</option>';
      }).join('') || '<option value="">ยังไม่มีโซน</option>';
      if (!S.run && social.length) {
        S.run = social[0].run;
        history.replaceState(null, '', '/search?run=' + encodeURIComponent(S.run));
      }
      sel.value = S.run;
      return social;
    });
  }

  /* ── wiring ───────────────────────────────────────────── */
  $('#zoneSel').addEventListener('change', function (e) {
    if (!e.target.value) return;
    window.location = '/search?run=' + encodeURIComponent(e.target.value);
  });
  $('#retry').addEventListener('click', function () { location.reload(); });

  var typing;
  $('#q').addEventListener('input', function (e) {
    clearTimeout(typing);
    var v = e.target.value.trim();
    typing = setTimeout(function () { S.q = v; refreshPosts(); }, 260);
  });
  $('#platSel').addEventListener('change', function (e) { S.platform = e.target.value; refreshPosts(); });
  $('#sentSel').addEventListener('change', function (e) { S.sentiment = e.target.value; refreshPosts(); });
  $('#dFrom').addEventListener('change', function (e) { S.from = e.target.value; refreshPosts(); });
  $('#dTo').addEventListener('change', function (e) { S.to = e.target.value; refreshPosts(); });
  $('#sortSel').addEventListener('change', function (e) { S.sort = e.target.value; refreshPosts(); });
  $('#per').addEventListener('change', function (e) { S.per = Number(e.target.value); refreshPosts(); });
  $('#prev').addEventListener('click', function () {
    S.page = Math.max(1, S.page - 1); loadPosts().catch(function () {});
  });
  $('#next').addEventListener('click', function () {
    if (S.total && S.page * S.per < S.total) { S.page++; loadPosts().catch(function () {}); }
  });
  $('#export').addEventListener('click', function () { window.location = '/api/export.csv?' + qs(); });
  $('#noiseToggle').addEventListener('click', function () {
    S.noise = !S.noise;
    this.setAttribute('aria-pressed', String(S.noise));
    loadZone().then(loadPosts).catch(function () {});
  });

  document.addEventListener('click', function (e) {
    var sent = e.target.closest('[data-sent]');
    if (sent) {
      var v = sent.dataset.sent;
      S.sentiment = (S.sentiment === v) ? '' : v;
      $('#sentSel').value = S.sentiment;
      document.querySelectorAll('[data-sent]').forEach(function (x) {
        x.setAttribute('aria-pressed', String(x.dataset.sent === S.sentiment));
      });
      refreshPosts();
      return;
    }
    var term = e.target.closest('[data-term]');
    if (term) {
      var t = term.getAttribute('data-term');
      S.q = (S.q === t) ? '' : t;
      $('#q').value = S.q;
      refreshPosts();
      $('#postsSec').scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    var chipBtn = e.target.closest('[data-chip]');
    if (chipBtn) {
      var fn = (window.__chips || [])[Number(chipBtn.dataset.chip)];
      if (fn) { fn(); refreshPosts(); }
      return;
    }
    if (e.target.id === 'clearAll') {
      S.q = ''; S.platform = ''; S.sentiment = ''; S.from = ''; S.to = '';
      $('#q').value = ''; $('#platSel').value = ''; $('#sentSel').value = '';
      $('#dFrom').value = ''; $('#dTo').value = '';
      refreshPosts();
      return;
    }
    var post = e.target.closest('button[data-url]');
    if (post) { window.open(post.dataset.url, '_blank', 'noopener'); return; }
    if (e.target.closest('a, [data-stop]')) return;
    var row = e.target.closest('tr.row');
    if (row && row.dataset.url) {
      if (S.open.has(row.dataset.url)) S.open.delete(row.dataset.url);
      else S.open.add(row.dataset.url);
      loadPosts().catch(function () {});
    }
  });

  $('#rows').addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    if (e.target.closest('a, button')) return;
    var row = e.target.closest('tr.row');
    if (!row) return;
    e.preventDefault();
    row.click();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === '/' && document.activeElement !== $('#q')) {
      e.preventDefault();
      $('#q').focus();
    }
  });

  window.addEventListener('sl:act', function (e) {
    var d = e.detail || {};
    if (d.act === 'day' && d.day) {
      S.from = d.day; S.to = d.day;
      $('#dFrom').value = S.from; $('#dTo').value = S.to;
      refreshPosts();
      $('#postsSec').scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    if (d.act === 'author') {
      S.q = d.key || '';
      $('#q').value = S.q;
      refreshPosts();
      return;
    }
    if (d.act === 'platform' && d.platform) {
      S.platform = d.platform;
      $('#platSel').value = d.platform;
      refreshPosts();
    }
  });

  /* ── boot ─────────────────────────────────────────────── */
  var params = new URLSearchParams(location.search);
  S.run = (params.get('run') || '').trim();

  loadRunList().then(function () {
    if (!S.run) { $('#banner').classList.add('on'); $('#bannerMsg').textContent = 'ยังไม่มีโซนคำค้นให้แสดง'; return; }
    loadZone().then(loadPosts).catch(function (e) {
      $('#banner').classList.add('on');
      $('#bannerMsg').textContent = 'โหลดโซนไม่สำเร็จ — ' + e.message;
      $('#liveDot').style.background = 'var(--neg)';
    });
  }).catch(function (e) {
    $('#banner').classList.add('on');
    $('#bannerMsg').textContent = 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ — ' + e.message;
  });

  setInterval(function () { loadPosts().catch(function () {}); }, 10000);
  setInterval(function () { loadZone().catch(function () {}); }, 30000);
})();
