/* Mount: <div id="vizHeat"></div>, load after sl.css + viz-heat.css.
 * Auto-mounts once at DOM ready. Manual: __vizHeat.mount(elementOrSelector).
 * refresh() re-fetches; snapshot() returns the exact buckets used to paint.
 * Seven Bangkok calendar days ending today; at most 200 API rows, never extrapolated.
 */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var WEEK = ['วันอาทิตย์', 'วันจันทร์', 'วันอังคาร', 'วันพุธ', 'วันพฤหัสบดี', 'วันศุกร์', 'วันเสาร์'];
  var PLAT = {x:'เอ็กซ์', twitter:'เอ็กซ์', facebook:'เฟซบุ๊ก', fbfeed:'เฟซบุ๊ก (ฟีด)', threads:'เธรดส์', tiktok:'ติ๊กต็อก', instagram:'อินสตาแกรม', youtube:'ยูทูบ', news:'ข่าวเว็บ', other:'อื่น ๆ'};
  var instances = new WeakMap(), current = null, serial = 0;
  function node(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text != null) el.textContent = text;
    return el;
  }
  function clock(h) { return String(h).padStart(2, '0') + ':00'; }
  function range(h) { return clock(h) + '-' + clock(h + 1); }
  function dayLabel(key) {
    var d = new Date(key + 'T12:00:00+07:00');
    return WEEK[d.getUTCDay()] + ' ' + key.slice(8) + '/' + key.slice(5,7);
  }
  // Reject timezone-less timestamps rather than letting the viewer's locale move cells.
  function stamp(iso) {
    if (typeof iso !== 'string' || !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso)) return null;
    var ms = Date.parse(iso);
    if (!Number.isFinite(ms)) return null;
    var local = new Date(ms + 7 * 3600000).toISOString();
    return {day:local.slice(0,10), hour:Number(local.slice(11,13))};
  }
  function bucket(posts, now) {
    var today = new Date((now == null ? Date.now() : Number(now)) + 7 * 3600000).toISOString().slice(0,10);
    var days = Array.from({length:7}, function (_, i) {
      return new Date(Date.parse(today + 'T00:00:00Z') - i * 86400000).toISOString().slice(0,10);
    });
    var daily = days.map(function () { return Array(24).fill(0); });
    var platforms = Object.create(null), valid = [], invalid = 0, outside = 0;
    posts.forEach(function (p) {
      var s = stamp(p.posted_iso);
      if (!s) { invalid++; return; }
      var r = days.indexOf(s.day);
      if (r < 0) { outside++; return; }
      var platform = String(p.platform || 'other');
      if (!platforms[platform]) platforms[platform] = Array(24).fill(0);
      daily[r][s.hour]++; platforms[platform][s.hour]++;
      valid.push({day:s.day, hour:s.hour, platform:platform});
    });
    var hours = Array.from({length:24}, function (_, h) {
      return daily.reduce(function (sum, row) { return sum + row[h]; }, 0);
    });
    var peakHour = hours.indexOf(Math.max.apply(null, hours));
    return {days:days, daily:daily, platforms:platforms, hours:hours, peakHour:peakHour,
      total:valid.length, fetched:posts.length, invalid:invalid, outside:outside, valid:valid};
  }
  function render(state) {
    var data = state.data, host = state.host;
    state.tip.hidden = true;
    state.plot.replaceChildren();
    state.caption.textContent = data.total < 5 ? 'ข้อมูลยังน้อยเกินกว่าจะอ่านรูปแบบเวลา · ตัวอย่าง ' + data.total + ' โพสต์' :
      'คึกคักสุด ' + range(data.peakHour) + ' · ' + data.hours[data.peakHour] + ' โพสต์ · ตัวอย่าง ' + data.total + ' โพสต์';
    state.note.textContent = 'เวลาไทย · 7 วันล่าสุด (' + data.days[6] + ' ถึง ' + data.days[0] + ') · ใช้ ' + data.total +
      ' จากตัวอย่างที่ดึงมา ' + data.fetched + ' โพสต์ (สูงสุด 200)' +
      (data.invalid ? ' · ไม่ทราบเวลา ' + data.invalid + ' โพสต์' : '') +
      (data.outside ? ' · นอกช่วง ' + data.outside + ' โพสต์' : '');
    state.buttons.forEach(function (b) { b.disabled = data.total < 5; b.setAttribute('aria-pressed', String(b.dataset.mode === state.mode)); });
    host.dataset.mode = state.mode;
    if (data.total < 5) return;
    var keys = state.mode === 'day' ? data.days : Object.keys(data.platforms).sort();
    var values = state.mode === 'day' ? data.daily : keys.map(function (key) { return data.platforms[key]; });
    var flat = values.flat(), max = Math.max.apply(null, flat), hottest = flat.indexOf(max);
    state.hottest = {row:Math.floor(hottest/24), hour:hottest%24, count:max};
    var scroller = node('div', 'vh-scroll');
    var grid = node('div', 'vh-grid');
    grid.setAttribute('role','grid'); grid.setAttribute('aria-label','จำนวนโพสต์ตามวันและชั่วโมง เวลาไทย');
    grid.setAttribute('aria-rowcount', String(keys.length + 1)); grid.setAttribute('aria-colcount','25');
    var axis = node('div','vh-row vh-axis'); axis.setAttribute('role','row');
    var corner = node('div','vh-label',state.mode === 'day' ? 'วัน / ชั่วโมง' : 'แพลตฟอร์ม');
    corner.setAttribute('role','columnheader'); axis.append(corner);
    var ticks = node('div','vh-ticks'); ticks.setAttribute('aria-hidden','true');
    for (var h = 0; h < 24; h++) ticks.append(node('span','',h % 3 === 0 ? String(h) : ''));
    axis.append(ticks); grid.append(axis);
    var cells = [];
    keys.forEach(function (key, r) {
      var row = node('div','vh-row'); row.setAttribute('role','row');
      var label = state.mode === 'day' ? dayLabel(key) : (PLAT[key] || 'อื่น ๆ');
      var lab = node('div','vh-label',label); lab.setAttribute('role','rowheader'); row.append(lab);
      var svg = document.createElementNS(NS,'svg');
      svg.setAttribute('viewBox','0 0 720 32'); svg.setAttribute('preserveAspectRatio','none');
      svg.setAttribute('role','presentation'); svg.classList.add('vh-cells');
      values[r].forEach(function (count, hour) {
        var rect = document.createElementNS(NS,'rect'), index = r * 24 + hour;
        rect.setAttribute('x',String(hour * 30 + 2)); rect.setAttribute('y','3');
        rect.setAttribute('width','26'); rect.setAttribute('height','26'); rect.setAttribute('rx','5');
        rect.setAttribute('role','gridcell'); rect.setAttribute('aria-colindex',String(hour+2));
        rect.setAttribute('tabindex', index === 0 ? '0' : '-1');
        rect.dataset.row = r; rect.dataset.hour = hour; rect.dataset.count = count;
        var level = count ? Math.max(1, Math.ceil(count / max * 5)) : 0;
        rect.dataset.level = level;
        if (index === hottest) rect.dataset.hottest = 'true';
        var weekday = state.mode === 'platform' ? data.days.filter(function (day) {
          return data.valid.some(function (p) { return p.day === day && p.hour === hour && p.platform === key; });
        }).map(dayLabel).join(' / ') : '';
        var text = label + (weekday ? ' · ' + weekday : '') + ' · ' + range(hour) + ' · ' + count +
          ' โพสต์ · ' + (count / data.total * 100).toFixed(1) + '% ของตัวอย่าง ' + data.total + ' โพสต์';
        if (index === hottest) text += ' · ช่องที่คึกคักสุด';
        rect.setAttribute('aria-label',text);
        function show() {
          state.tip.textContent = text; state.tip.hidden = false;
          rect.setAttribute('aria-describedby',state.tip.id);
          var box = rect.getBoundingClientRect(), tip = state.tip.getBoundingClientRect();
          state.tip.style.left = Math.max(8, Math.min(box.left, window.innerWidth - tip.width - 8)) + 'px';
          state.tip.style.top = Math.max(8, (box.bottom + tip.height + 12 < window.innerHeight ? box.bottom + 8 : box.top - tip.height - 8)) + 'px';
        }
        function hide() { state.tip.hidden = true; rect.removeAttribute('aria-describedby'); }
        rect.addEventListener('pointerenter',show); rect.addEventListener('pointerleave',hide);
        rect.addEventListener('focus',function () {
          cells.forEach(function (cell) { cell.setAttribute('tabindex',cell === rect ? '0' : '-1'); }); show();
        });
        rect.addEventListener('blur',hide);
        rect.addEventListener('keydown',function (event) {
          if (event.key === 'Escape') { hide(); event.preventDefault(); return; }
          var nr = r, nh = hour;
          if (event.key === 'ArrowRight') nh = Math.min(23,hour+1);
          else if (event.key === 'ArrowLeft') nh = Math.max(0,hour-1);
          else if (event.key === 'ArrowDown') nr = Math.min(keys.length-1,r+1);
          else if (event.key === 'ArrowUp') nr = Math.max(0,r-1);
          else if (event.key === 'Home') nh = 0;
          else if (event.key === 'End') nh = 23;
          else return;
          event.preventDefault();
          var next = cells[nr*24+nh]; next.focus({preventScroll:true});
          var b = next.getBoundingClientRect(), s = scroller.getBoundingClientRect();
          if (b.left < s.left + 116) scroller.scrollLeft -= s.left + 116 - b.left;
          if (b.right > s.right) scroller.scrollLeft += b.right - s.right + 4;
          next.dispatchEvent(new Event('pointerenter'));
        });
        svg.append(rect); cells.push(rect);
      });
      row.append(svg); grid.append(row);
    });
    scroller.append(grid); state.plot.append(scroller);
    scroller.addEventListener('scroll',function () {
      var focused = document.activeElement;
      if (grid.contains(focused) && focused.matches('rect')) focused.dispatchEvent(new Event('pointerenter'));
      else state.tip.hidden = true;
    }, {passive:true});
    if (!state.entered) { state.plot.classList.add('vh-enter'); state.entered = true; }
  }
  function mount(target, options) {
    var host = typeof target === 'string' ? document.querySelector(target) : target;
    if (!host) return null;
    if (instances.has(host)) return instances.get(host).api;
    options = options || {};
    document.documentElement.classList.add('viz-heat');
    host.classList.add('vh-card');
    var state = {host:host, mode:'day', options:options, buttons:[], entered:false};
    var head = node('div','vh-head'); head.append(node('h2','','คนโพสต์กันช่วงไหน'));
    var modes = node('div','vh-modes'); modes.setAttribute('role','group'); modes.setAttribute('aria-label','แยกแถวตาม');
    ['day','platform'].forEach(function (mode, i) {
      var button = node('button','',i ? 'แพลตฟอร์ม' : 'รายวัน');
      button.type = 'button'; button.dataset.mode = mode; button.setAttribute('aria-pressed', String(!i));
      button.addEventListener('click',function () { state.mode = mode; if (state.data) render(state); });
      state.buttons.push(button); modes.append(button);
    });
    head.append(modes); state.caption = node('p','vh-caption','กำลังอ่านช่วงเวลาโพสต์');
    state.caption.setAttribute('role','status');
    state.note = node('p','vh-note','ตัวอย่างสูงสุด 200 โพสต์ · เวลาไทย');
    state.plot = node('div','vh-plot');
    state.tip = node('div','vh-tip'); state.tip.id = 'vh-tip-' + (++serial); state.tip.setAttribute('role','tooltip'); state.tip.hidden = true;
    var help = node('p','vh-help','สีเข้มขึ้น = โพสต์มากขึ้น · สีเน้น = ช่องที่คึกคักสุด · ช่องว่าง = 0 โพสต์ · ใช้ปุ่มลูกศรเพื่อสำรวจ กดเอสเคปเพื่อปิดคำอธิบาย');
    host.replaceChildren(head,state.caption,state.note,state.plot,help,state.tip);
    async function refresh() {
      state.buttons.forEach(function (b) { b.disabled = true; });
      host.setAttribute('aria-busy','true');
      try {
        var payload;
        if (options.posts) payload = {posts:options.posts};
        else {
          var response = await fetch('/api/posts?limit=200', {cache:'no-store'});
          if (!response.ok) throw new Error('posts');
          payload = await response.json();
        }
        if (!Array.isArray(payload.posts)) throw new Error('posts');
        state.data = bucket(payload.posts,options.now);
        render(state);
      } catch (_) {
        state.plot.replaceChildren(); state.tip.hidden = true;
        state.caption.textContent = 'อ่านเวลาโพสต์ไม่ได้ กรุณาลองใหม่';
        state.note.textContent = 'ยังไม่มีตัวอย่างที่ตรวจสอบได้';
      } finally { host.setAttribute('aria-busy','false'); }
    }
    state.api = {refresh:refresh, snapshot:function () { return state.data ? JSON.parse(JSON.stringify({data:state.data, mode:state.mode, hottest:state.hottest})) : null; }};
    instances.set(host,state); current = state.api; refresh(); return state.api;
  }
  window.__vizHeat = {mount:mount, bucket:bucket, refresh:function () { return current && current.refresh(); }, snapshot:function () { return current && current.snapshot(); }};
  function boot() { mount(document.querySelector('#vizHeat')); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',boot,{once:true}); else boot();
})();
