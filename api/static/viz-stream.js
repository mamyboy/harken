/* Mount: <div id="vizStream"></div> (or [data-viz-stream]). Load after sl.css.
 * Public API: window.__vizStream.mount(element); repeated mounts share one fetch.
 * Dates use Bangkok calendar days, not the viewer's timezone. SVG units = CSS px,
 * so text remains >=12px at every DPR; vectors need no bitmap backing-store scale.
 */
(function () {
  'use strict';
  if (window.__vizStream) return;
  document.documentElement.classList.add('viz-stream');
  const instances = new WeakMap();
  let request, serial = 0;
  const names = {x:'เอ็กซ์', twitter:'เอ็กซ์', facebook:'เฟซบุ๊ก', fbfeed:'เฟซบุ๊กฟีด', threads:'เธรดส์', tiktok:'ติ๊กต็อก', instagram:'อินสตาแกรม', youtube:'ยูทูบ', pantip:'พันทิป', other:'อื่น ๆ'};
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dayFmt = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit'});
  const labelFmt = new Intl.DateTimeFormat('th-TH', {timeZone:'Asia/Bangkok',day:'numeric',month:'short',year:'numeric'});
  const dayKey = d => dayFmt.format(d);
  const label = k => labelFmt.format(new Date(k+'T12:00:00+07:00'));
  const num = n => n.toLocaleString('th-TH');
  async function load() {
    const end = dayKey(new Date()), base = new Date(end+'T12:00:00+07:00');
    const days = Array.from({length:30}, (_,i) => dayKey(new Date(base.getTime()-(29-i)*86400000)));
    let posts = [], total = 0;
    do {
      const limit = Math.min(200,500-posts.length);
      const q = new URLSearchParams({limit,offset:posts.length,comments:0,sort:'newest',date_from:days[0],date_to:end});
      const res = await fetch('/api/posts?'+q, {cache:'no-store'});
      if (!res.ok) throw new Error('posts');
      const data = await res.json();
      total = Number(data.total)||0;
      if (!Array.isArray(data.posts)) throw new Error('shape');
      if (!data.posts.length) break;
      posts = posts.concat(data.posts.slice(0,limit));
    } while (posts.length < Math.min(total,500));
    const rows = days.map(date => ({date,counts:{},total:0}));
    const index = new Map(rows.map(r => [r.date,r]));
    const platforms = new Set();
    let invalid = 0;
    posts.forEach(p => {
      const date = new Date(p.posted_iso);
      if (!p.posted_iso || !Number.isFinite(date.getTime())) { invalid++; return; }
      const row = index.get(dayKey(date));
      if (!row) return;
      const platform = String(p.platform || 'other');
      platforms.add(platform); row.counts[platform] = (row.counts[platform]||0)+1; row.total++;
    });
    return {rows, platforms:[...platforms].sort(), capped:total>500, invalid};
  }
  function mount(host) {
    if (typeof host === 'string') host = document.querySelector(host);
    if (!host || instances.has(host)) return host && instances.get(host);
    const state = {cursor:-1, off:new Set(), animated:false};
    instances.set(host,state);
    const id = 'vs'+(++serial);
    host.classList.add('vs-card');
    host.innerHTML = '<h2 id="'+id+'Title">แพลตฟอร์มตามเวลา</h2><p class="vs-note" role="status">กำลังโหลดข้อมูล</p>';
    host.setAttribute('aria-labelledby',id+'Title');
    (request || (request=load())).then(data => {
      state.data = data;
      if (data.rows.filter(r=>r.total>0).length<3) {
        host.querySelector('.vs-note').textContent = 'ข้อมูลยังน้อยเกินกว่าจะดูแนวโน้ม';
        return;
      }
      host.innerHTML = '<h2 id="'+id+'Title">แพลตฟอร์มตามเวลา</h2><p class="vs-note">'+esc(label(data.rows[0].date))+' – '+esc(label(data.rows[29].date))+' · จำนวนโพสต์รายวัน'+(data.capped?' · แสดงเฉพาะ 500 โพสต์ล่าสุด':'')+(data.invalid?' · ไม่นับโพสต์ที่อ่านวันที่ไม่ได้':'')+'</p><div class="vs-legend" aria-label="แสดงหรือซ่อนแพลตฟอร์ม"></div><p class="vs-help" id="'+id+'Help">ชี้หรือแตะวันที่เพื่อดูจำนวน · ใช้ลูกศรซ้ายขวา ปุ่มเริ่มต้นหรือสิ้นสุดเพื่อเลือกวัน และปุ่มยกเลิกเพื่อปิด</p><div class="vs-plot" tabindex="0" role="group" aria-label="กราฟจำนวนโพสต์รายวัน" aria-describedby="'+id+'Help '+id+'Tip"><div class="vs-svg"></div><div class="vs-tip" id="'+id+'Tip" role="status" aria-live="polite" hidden></div></div><details class="vs-summary"><summary>ตารางจำนวนโพสต์รายวัน</summary><div class="vs-tablewrap" tabindex="0" role="region" aria-label="ตารางเลื่อนแนวนอนได้"><table><caption>จำนวนโพสต์ทุกแพลตฟอร์ม รวมแพลตฟอร์มที่ซ่อนจากกราฟ</caption><thead></thead><tbody></tbody></table></div></details>';
      const legend = host.querySelector('.vs-legend'), plot=host.querySelector('.vs-plot'), slot=host.querySelector('.vs-svg'), tip=host.querySelector('.vs-tip');
      data.platforms.forEach((p,i) => {
        const b=document.createElement('button'); b.type='button'; b.dataset.platform=p; b.style.setProperty('--vs-series','var(--vs-c'+(i%4)+')'); b.setAttribute('aria-pressed','true'); b.innerHTML='<span class="vs-swatch" aria-hidden="true"></span>'+esc(names[p]||'แพลตฟอร์มอื่น');
        b.onclick=()=>{state.off.has(p)?state.off.delete(p):state.off.add(p);b.setAttribute('aria-pressed',String(!state.off.has(p)));draw();}; legend.append(b);
      });
      host.querySelector('thead').innerHTML='<tr><th scope="col">วันที่</th>'+data.platforms.map(p=>'<th scope="col">'+esc(names[p]||'แพลตฟอร์มอื่น')+'</th>').join('')+'<th scope="col">รวมทั้งหมด</th></tr>';
      host.querySelector('tbody').innerHTML=data.rows.map((r,i)=>'<tr data-day="'+i+'"><th scope="row">'+esc(label(r.date))+'</th>'+data.platforms.map(p=>'<td data-platform="'+esc(p)+'">'+num(r.counts[p]||0)+'</td>').join('')+'<td data-total>'+num(r.total)+'</td></tr>').join('');
      function cursor(i) {
        state.cursor=i;
        const cross=slot.querySelector('.vs-cross');
        if (i<0) {tip.hidden=true; if(cross) cross.setAttribute('visibility','hidden'); return;}
        const r=data.rows[i], x=state.x(i);
        cross.setAttribute('x1',x);cross.setAttribute('x2',x);cross.setAttribute('visibility','visible');
        // Tooltip always includes every platform and full total, exactly like the table.
        tip.innerHTML='<strong>'+esc(label(r.date))+'</strong>'+data.platforms.map(p=>'<div>'+esc(names[p]||'แพลตฟอร์มอื่น')+' <b>'+num(r.counts[p]||0)+'</b></div>').join('')+'<div class="vs-tiptotal">รวมทั้งหมด <b>'+num(r.total)+'</b></div>';
        tip.hidden=false;
        tip.style.left=Math.max(0,Math.min(x-tip.offsetWidth/2,plot.clientWidth-tip.offsetWidth))+'px';
      }
      function draw() {
        const w=slot.clientWidth; if(w<100)return;
        state.width=w;
        const h=250,L=40,R=w-16,T=14,B=214,dx=(R-L)/30;
        state.x=i=>L+dx*(i+.5);
        const active=data.platforms.filter(p=>!state.off.has(p));
        const totals=data.rows.map(r=>active.reduce((s,p)=>s+(r.counts[p]||0),0));
        const step=Math.max(1,Math.ceil(Math.max(...totals)/4)),max=step*4,y=n=>B-(B-T)*n/max;
        let grid='';
        for(let n=0;n<=4;n++)grid+='<line class="vs-grid" x1="'+L+'" x2="'+R+'" y1="'+y(n*step)+'" y2="'+y(n*step)+'"/><text class="vs-axis" x="'+(L-8)+'" y="'+(y(n*step)+4)+'" text-anchor="end">'+num(n*step)+'</text>';
        [0,Math.round(29/2),29].forEach(i=>{grid+='<text class="vs-axis" x="'+state.x(i)+'" y="242" text-anchor="'+(i===0?'start':i===29?'end':'middle')+'">'+esc(labelFmt.format(new Date(data.rows[i].date+'T12:00:00+07:00')).replace(/\s+\d{4}$/, ''))+'</text>';});
        let shapes='',bottom=Array(30).fill(0);
        // Fewer than six occupied days: stacked bars avoid interpolating a continuous
        // trend across missing days. Six or more: stacked linear areas, no smoothing.
        const bars=data.rows.filter(r=>r.total>0).length<6;
        active.forEach(p=>{
          const top=bottom.map((n,i)=>n+(data.rows[i].counts[p]||0)),color='var(--vs-c'+(data.platforms.indexOf(p)%4)+')';
          let shape='';
          if(bars)shape=top.map((n,i)=>'<rect x="'+(state.x(i)-dx*.36)+'" y="'+y(n)+'" width="'+dx*.72+'" height="'+(y(bottom[i])-y(n))+'"/>').join('');
          else shape='<path d="M'+top.map((n,i)=>state.x(i)+','+y(n)).join(' L')+' L'+bottom.map((n,i)=>state.x(i)+','+y(n)).reverse().join(' L')+' Z"/>';
          shapes+='<g data-series="'+esc(p)+'" fill="'+color+'">'+shape+'</g>';bottom=top;
        });
        // Only the clip rectangle transforms; the data geometry never scales.
        const animate=!state.animated&&!matchMedia('(prefers-reduced-motion: reduce)').matches;
        state.animated=true;
        slot.innerHTML='<svg xmlns="http://www.w3.org/2000/svg" width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" aria-hidden="true"><defs><clipPath id="'+id+'Clip"><rect class="'+(animate?'vs-wipe':'')+'" x="0" y="0" width="'+w+'" height="'+h+'"/></clipPath></defs>'+grid+'<g clip-path="url(#'+id+'Clip)">'+shapes+'</g><line class="vs-cross" x1="0" x2="0" y1="'+T+'" y2="'+B+'" visibility="hidden"/></svg>';
        cursor(state.cursor);
      }
      const point=e=>{const r=plot.getBoundingClientRect();cursor(Math.max(0,Math.min(29,Math.floor((e.clientX-r.left-40)/(plot.clientWidth-56)*30))));};
      plot.addEventListener('pointermove',point);
      plot.addEventListener('pointerdown',e=>{plot.focus();point(e);});
      plot.addEventListener('pointerleave',()=>{if(document.activeElement!==plot)cursor(-1);});
      plot.addEventListener('focus',()=>{if(state.cursor<0)cursor(data.rows.findIndex(r=>r.total));});
      plot.addEventListener('blur',()=>cursor(-1));
      plot.addEventListener('keydown',e=>{
        let i=state.cursor;
        if(e.key==='ArrowRight')i=Math.min(29,i+1);
        else if(e.key==='ArrowLeft')i=Math.max(0,i-1);
        else if(e.key==='Home')i=0; else if(e.key==='End')i=29;
        else if(e.key==='Escape')i=-1; else return;
        e.preventDefault();cursor(i);
      });
      state.observer=new ResizeObserver(()=>{if(slot.clientWidth!==state.width)draw();});state.observer.observe(slot);draw();
    }).catch(()=>{host.querySelector('.vs-note').textContent='โหลดข้อมูลไม่สำเร็จ กรุณาลองใหม่เมื่อรีเฟรชหน้า';});
    return state;
  }
  window.__vizStream = Object.freeze({mount});
  function boot(){document.querySelectorAll('#vizStream,[data-viz-stream]').forEach(mount);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
