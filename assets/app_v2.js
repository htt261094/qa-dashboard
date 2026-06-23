/* ===== QA Suite UI v2 — JS shell (dashboard QA + roadmap). Inline qua _document_v2. ===== */
/* Phần shared chạy mọi trang; dashboard guard #rows; roadmap guard #rmList2. Endpoint thật. */
(function(){
'use strict';

// ---------- helpers ----------
function esc(s){ return (s==null?'':String(s))
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function $(id){ return document.getElementById(id); }
function readJSON(id){ var el=$(id); if(!el) return null; try{ return JSON.parse(el.textContent); }catch(e){ return null; } }
// Write cần Jira -> chặn khi đang xem snapshot OFFLINE (window.__stale). /set-custom-status
// ghi Cloudflare KV nên VẪN cho (sống offline); /dismiss cũng KV -> không chặn.
var JIRA_WRITE = { '/do-transition':1, '/create-subtask':1 };
function postJSON(url, body, ms){
  if (window.__stale && JIRA_WRITE[url]) {
    try { toast('Đang xem offline (mất kết nối Jira) — không đổi được task. Bật VPN rồi thử lại.'); } catch(e){}
    return Promise.reject(new Error('offline'));
  }
  var ctrl = new AbortController();
  var to = setTimeout(function(){ ctrl.abort(); }, ms||20000);
  return fetch(url, { method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body||{}), signal: ctrl.signal })
    .then(function(r){ clearTimeout(to); return r.json(); })
    .catch(function(e){ clearTimeout(to); throw e; });
}
function getJSON(url, ms){
  var ctrl = new AbortController();
  var to = setTimeout(function(){ ctrl.abort(); }, ms||20000);
  return fetch(url, { signal: ctrl.signal })
    .then(function(r){ clearTimeout(to); return r.json(); })
    .catch(function(e){ clearTimeout(to); throw e; });
}
var AV = ['av-a','av-b','av-c','av-d','av-e','av-f'];
function avById(name){ var s=0,n=name||'?'; for(var i=0;i<n.length;i++) s+=n.charCodeAt(i); return AV[s%AV.length]; }
function initOf(name){ return ((name||'?').trim()[0]||'?').toUpperCase(); }

// ---------- bug đã link tới task (drawer detail) ----------
var BUG_ST = { 'New':['st-open','Mới'], 'Fixing':['st-fixing','Đang fix'],
  'Fixed':['st-fixed','Đã fix (chờ retest)'], 'Reopen':['st-reopen','Reopen'],
  'Rejected':['st-rejected','Bị từ chối'], 'Closed':['st-closed','Đã đóng'] };
function bugSectionHtml(d){
  var bugs=(d&&d.bugs)||[];
  if(!bugs.length) return '';
  var rows=bugs.map(function(b){
    var m=BUG_ST[b.status]||['st-default', b.status||'—'];
    var sev=(b.severity||'').trim();
    return '<div class="dt-bug">'
      +'<span class="dt-bug-id">'+esc(b.id||'')+'</span>'
      +'<span class="dt-bug-sum">'+esc(b.summary||'')+(b.module?' <span class="dt-bug-mod">· '+esc(b.module)+'</span>':'')+'</span>'
      +(sev?'<span class="dt-bug-sev">'+esc(sev)+'</span>':'')
      +'<span class="st-badge '+m[0]+'">'+esc(m[1])+'</span>'
      +'</div>';
  }).join('');
  return '<div class="dt-sec-title">Bug liên quan ('+bugs.length+')</div><div class="dt-bugs">'+rows+'</div>';
}

// ---------- bộ test case đã link tới task (drawer detail, #155) ----------
function testcaseSectionHtml(d){
  var tcs=(d&&d.testcases)||[];
  if(!tcs.length) return '';
  var rows=tcs.map(function(t){
    var meta=[];
    if(t.pass) meta.push('<span class="dt-tc-pass">'+t.pass+' pass</span>');
    if(t.fail) meta.push('<span class="dt-tc-fail">'+t.fail+' fail</span>');
    var href='/test-cases?folder='+encodeURIComponent(t.id||'');
    return '<a class="dt-tc" href="'+href+'" target="_blank">'
      +'<span class="material-symbols-rounded mi-sm">folder</span>'
      +'<span class="dt-tc-name">'+esc(t.name||'')+'</span>'
      +'<span class="dt-tc-count">'+(t.count||0)+' TC</span>'
      +(meta.length?'<span class="dt-tc-meta">'+meta.join(' · ')+'</span>':'')
      +'</a>';
  }).join('');
  return '<div class="dt-sec-title">Bộ test case liên quan ('+tcs.length+')</div><div class="dt-tcs">'+rows+'</div>';
}

// ---------- toast ----------
var toastT;
function toast(msg, ok){ var el=$('toast'); if(!el) return; el.textContent=msg;
  el.className = 'toast show' + (ok===false?' err':'');
  clearTimeout(toastT); toastT=setTimeout(function(){ el.className='toast'; }, 2200); }

// ---------- chatbot (float góc dưới-phải, Decision #32) ----------
// Stream từ POST /chat (text/plain, đọc dần qua ReadableStream). Lịch sử lưu localStorage.
(function(){
  var fab=$('chatFab'), panel=$('chatPanel'), body=$('chatBody'), inp=$('chatInp'),
      sendBtn=$('chatSend'), closeBtn=$('chatClose'), clearBtn=$('chatClear'), fabIc=$('chatFabIc');
  if(!fab || !panel) return;   // CHAT_ENABLED=false -> widget không render
  var KEY='qa-chat-history';
  var history=[], busy=false;

  function save(){ try{ localStorage.setItem(KEY, JSON.stringify(history.slice(-40))); }catch(e){} }
  function load(){ try{ var s=localStorage.getItem(KEY); if(s) history=JSON.parse(s)||[]; }catch(e){ history=[]; } }

  // markdown nhẹ: escape TRƯỚC (an toàn XSS) rồi mới format. bold/code/link/bullet/xuống dòng.
  function md(t){
    var h=esc(t);
    h=h.replace(/`([^`]+)`/g,'<code>$1</code>');
    h=h.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
    h=h.replace(/(https?:\/\/[^\s<]+)/g,'<a href="$1" target="_blank" rel="noopener">$1</a>');
    var lines=h.split('\n'), out=[], inList=false, m;
    for(var i=0;i<lines.length;i++){
      m=lines[i].match(/^\s*[-*]\s+(.*)$/);
      if(m){ if(!inList){ out.push('<ul>'); inList=true; } out.push('<li>'+m[1]+'</li>'); }
      else { if(inList){ out.push('</ul>'); inList=false; } out.push(lines[i]); }
    }
    if(inList) out.push('</ul>');
    return out.join('\n');
  }
  function bubble(role, text){
    var d=document.createElement('div');
    d.className='chat-msg '+(role==='user'?'user':'bot');
    if(role==='user') d.textContent=text; else d.innerHTML=md(text);
    body.appendChild(d); body.scrollTop=body.scrollHeight; return d;
  }
  function typing(){
    var d=document.createElement('div'); d.className='chat-typing';
    d.innerHTML='<span></span><span></span><span></span>';
    body.appendChild(d); body.scrollTop=body.scrollHeight; return d;
  }
  function renderAll(){
    body.innerHTML='';
    if(!history.length){
      body.innerHTML='<div class="chat-empty"><span class="material-symbols-rounded">smart_toy</span>'
        +'Chào! Mình là trợ lý QA. Hỏi mình về bug log, test case, tài liệu hay bất cứ gì nhé.</div>';
      return;
    }
    history.forEach(function(m){ bubble(m.role, m.content); });
  }
  function open(){ panel.classList.add('open'); fab.classList.add('open'); fabIc.textContent='close';
    body.scrollTop=body.scrollHeight; setTimeout(function(){ inp.focus(); },60); }
  function close(){ panel.classList.remove('open'); fab.classList.remove('open'); fabIc.textContent='smart_toy'; }
  function autoGrow(){ inp.style.height='auto'; inp.style.height=Math.min(120, inp.scrollHeight)+'px'; }

  // Scrape nội dung tab đang mở: text hiển thị của khối `.content` (+ tiêu đề tab) gửi
  // kèm câu hỏi làm context -> hỏi "trang này", "bảng trên màn hình" model đọc được.
  function scrapePage(){
    try{
      var el=document.querySelector('.content'); if(!el) return '';
      var t=(el.innerText||el.textContent||'').replace(/[ \t]+\n/g,'\n').replace(/\n{3,}/g,'\n\n').trim();
      if(!t) return '';
      if(t.length>6000) t=t.slice(0,6000)+'\n…(đã cắt bớt)';
      var nav=document.querySelector('.sidebar a.active'), tab='';
      if(nav){ var c=nav.cloneNode(true), ic=c.querySelector('.material-symbols-rounded');
        if(ic) ic.remove(); tab=(c.innerText||c.textContent||'').trim(); }
      if(!tab) tab=(document.title||'').trim();
      return (tab? 'Tab: '+tab+'\n\n':'')+t;
    }catch(e){ return ''; }
  }

  function send(){
    var text=(inp.value||'').trim();
    if(!text || busy) return;
    history.push({role:'user', content:text}); save();
    var emp=body.querySelector('.chat-empty'); if(emp) emp.remove();
    bubble('user', text);
    inp.value=''; autoGrow();
    busy=true; sendBtn.disabled=true;
    var tp=typing(), botDiv=null, acc='';
    fetch('/chat', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({messages: history.slice(-16), page: scrapePage()})})
    .then(function(r){
      if(!r.ok || !r.body) throw new Error('http '+r.status);
      var reader=r.body.getReader(), dec=new TextDecoder();
      function pump(){
        return reader.read().then(function(res){
          if(res.done) return;
          var chunk=dec.decode(res.value, {stream:true});
          if(chunk){
            if(!botDiv){ if(tp.parentNode) tp.remove(); botDiv=bubble('bot',''); }
            acc+=chunk; botDiv.innerHTML=md(acc); body.scrollTop=body.scrollHeight;
          }
          return pump();
        });
      }
      return pump();
    })
    .then(function(){
      if(tp.parentNode) tp.remove();
      if(acc){ history.push({role:'assistant', content:acc}); save(); }
      else bubble('bot','⚠️ Không nhận được phản hồi từ trợ lý.');
    })
    .catch(function(){
      if(tp.parentNode) tp.remove();
      if(!botDiv) bubble('bot','⚠️ Lỗi kết nối tới trợ lý. Thử lại nhé.');
    })
    .then(function(){ busy=false; sendBtn.disabled=false; inp.focus(); });
  }

  fab.addEventListener('click', function(){ panel.classList.contains('open')?close():open(); });
  closeBtn.addEventListener('click', close);
  clearBtn.addEventListener('click', function(){ history=[]; save(); renderAll(); });
  sendBtn.addEventListener('click', send);
  inp.addEventListener('input', autoGrow);
  inp.addEventListener('keydown', function(e){ if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); send(); } });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape' && panel.classList.contains('open')) close(); });

  load(); renderAll();
})();

// ---------- theme ----------
function applyTheme(t){ document.documentElement.setAttribute('data-theme', t);
  try{ localStorage.setItem('qa-theme', t); }catch(e){}
  var ic=$('themeIc'); if(ic) ic.textContent = t==='dark'?'light_mode':'dark_mode'; }
(function(){ var t='light'; try{ t=localStorage.getItem('qa-theme')||'light'; }catch(e){} applyTheme(t); })();
(function(){ var b=$('themeBtn'); if(b) b.addEventListener('click', function(){
  applyTheme(document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark'); }); })();

// ---------- profile menu ----------
(function(){
  var btn=$('profileBtn'), menu=$('pmenu'); if(!btn||!menu) return;
  btn.addEventListener('click', function(e){ e.stopPropagation(); menu.classList.toggle('open');
    var n=$('notif'); if(n) n.classList.remove('open'); });
  document.addEventListener('click', function(e){
    if(!e.target.closest('#pmenu') && !e.target.closest('#profileBtn')) menu.classList.remove('open'); });
})();

// ---------- global search topbar (quick-search toàn Jira) ----------
// Gõ key / số (5125 -> DA61H26-5125) / text summary -> dropdown -> click mở drawer tại chỗ.
// Chạy mọi trang v2. KHÔNG đụng filter bảng local (vẫn bind input riêng ở từng closure).
(function(){
  var inp=$('searchInp'); if(!inp) return;
  var box=inp.closest('.search') || inp.parentNode;
  if(box && getComputedStyle(box).position==='static') box.style.position='relative';
  var dd=document.createElement('div'); dd.className='gsearch-dd'; dd.style.display='none';
  box.appendChild(dd);
  var ST={ 'TO DO':'st-open','In Progress':'st-fixing','PENDING':'st-default',
           'DONE':'st-fixed','CANCELLED':'st-closed' };
  var seq=0, lastQ='', curRows=[], active=-1;

  function hide(){ dd.style.display='none'; active=-1; }
  function open(){ if(dd.firstChild) dd.style.display='block'; }
  function rowHtml(r, i){
    var cls=ST[r.status]||'st-default';
    return '<div class="gs-item'+(i===active?' active':'')+'" data-key="'+esc(r.key)+'" data-i="'+i+'">'
      +'<span class="gs-key">'+esc(r.key)+'</span>'
      +'<span class="gs-sum">'+esc(r.summary||'')+'</span>'
      +(r.status?'<span class="st-badge '+cls+'">'+esc(r.status)+'</span>':'')
      +'</div>';
  }
  function render(){
    if(!curRows.length){ dd.innerHTML='<div class="gs-empty">Không tìm thấy task</div>'; open(); return; }
    dd.innerHTML=curRows.map(rowHtml).join('');
    open();
  }
  function pick(key){ hide(); inp.blur();
    if(window.__openDetail){ window.__openDetail(key); }
    else { window.open((window.__jiraBase||'')+'/browse/'+encodeURIComponent(key), '_blank'); }
  }
  function run(q){
    var my=++seq; lastQ=q;
    dd.innerHTML='<div class="gs-empty">Đang tìm…</div>'; open();
    getJSON('/global-search?q='+encodeURIComponent(q), 15000).then(function(j){
      if(my!==seq) return;                 // kết quả cũ -> bỏ
      curRows=(j&&j.ok&&j.results)||[]; active=-1; render();
    }).catch(function(){ if(my!==seq) return; curRows=[]; dd.innerHTML='<div class="gs-empty">Lỗi tìm kiếm</div>'; open(); });
  }
  var deb;
  inp.addEventListener('input', function(){
    var q=(inp.value||'').trim();
    clearTimeout(deb);
    if(q.length<2){ seq++; hide(); return; }
    deb=setTimeout(function(){ run(q); }, 300);
  });
  inp.addEventListener('keydown', function(e){
    if(dd.style.display==='none') return;
    if(e.key==='ArrowDown'){ e.preventDefault(); active=Math.min(active+1, curRows.length-1); render(); }
    else if(e.key==='ArrowUp'){ e.preventDefault(); active=Math.max(active-1, -1); render(); }
    else if(e.key==='Enter'){ if(active>=0&&curRows[active]){ e.preventDefault(); pick(curRows[active].key); } }
    else if(e.key==='Escape'){ hide(); }
  });
  inp.addEventListener('focus', function(){ if(curRows.length && (inp.value||'').trim().length>=2) open(); });
  dd.addEventListener('mousedown', function(e){    // mousedown để chạy trước blur
    var it=e.target.closest('.gs-item'); if(it){ e.preventDefault(); pick(it.getAttribute('data-key')); } });
  document.addEventListener('click', function(e){
    if(!e.target.closest('.search')) hide(); });
})();

// ---------- settings PAT modal ----------
(function(){
  var ov=$('setOverlay'); if(!ov) return;
  function loadDrive(){
    var sect=$('setDriveSect'); if(!sect) return;   // chỉ admin có section này
    var st=$('setDriveState'), conn=$('setDriveConnect'), dc=$('setDriveDisconnect');
    fetch('/has-drive').then(function(r){ return r.json(); }).then(function(j){
      if(!j || !j.ok){ st.textContent='Không kiểm tra được trạng thái Drive.'; st.className='set-drive-state'; return; }
      if(!j.authEnabled){ st.textContent='⚠ Chưa bật Google OAuth (local dev) — không kết nối được.';
        st.className='set-drive-state warn'; if(conn) conn.style.display='none'; if(dc) dc.style.display='none'; return; }
      if(j.hasDrive){ st.textContent='✓ Đã kết nối Drive (chỉ đọc).'; st.className='set-drive-state ok';
        if(conn){ conn.textContent='Kết nối lại'; conn.style.display=''; } if(dc) dc.style.display=''; }
      else { st.textContent='⚠ Chưa kết nối Drive.'; st.className='set-drive-state warn';
        if(conn){ conn.textContent='Kết nối Drive'; conn.style.display=''; } if(dc) dc.style.display='none'; }
    }).catch(function(){ st.textContent='Lỗi mạng khi kiểm tra Drive.'; st.className='set-drive-state'; });
  }
  function open(){ ov.classList.add('open'); var m=$('pmenu'); if(m) m.classList.remove('open'); loadDrive(); }
  function close(){ ov.classList.remove('open'); }
  var s=$('pmSettings'); if(s) s.addEventListener('click', open);
  var ddc=$('setDriveDisconnect');
  if(ddc) ddc.addEventListener('click', function(){
    if(!confirm('Ngắt kết nối Drive? Background sync bug log sẽ ngừng đọc file cho tới khi kết nối lại.')) return;
    fetch('/disconnect-drive', { method:'POST' }).then(function(r){ return r.json(); })
      .then(function(j){ toast(j.ok?'Đã ngắt kết nối Drive':'Lỗi ngắt kết nối', j.ok); if(j.ok) loadDrive(); })
      .catch(function(){ toast('Lỗi mạng', false); }); });
  var c=$('setClose'); if(c) c.addEventListener('click', close);
  var cc=$('setCancel'); if(cc) cc.addEventListener('click', close);
  ov.addEventListener('click', function(e){ if(e.target===ov) close(); });
  var show=$('patShowBtn'), inp=$('patInp');
  if(show&&inp) show.addEventListener('click', function(){
    if(inp.type==='password'){ inp.type='text'; show.textContent='visibility_off'; }
    else { inp.type='password'; show.textContent='visibility'; } });
  var save=$('patSaveBtn');
  if(save) save.addEventListener('click', function(){
    var v=(inp.value||'').trim(); if(!v){ toast('Chưa nhập PAT', false); return; }
    save.disabled=true;
    postJSON('/save-pat', { pat:v }, 20000).then(function(j){
      save.disabled=false; toast(j.msg || (j.ok?'Đã lưu PAT':'Lỗi lưu PAT'), j.ok);
      if(j.ok){ inp.value=''; close(); }
    }).catch(function(){ save.disabled=false; toast('Lỗi mạng khi lưu PAT', false); }); });
  var del=$('patDelBtn');
  if(del) del.addEventListener('click', function(){
    if(!confirm('Xoá PAT đã lưu? Thao tác Jira sẽ không còn ghi tên bạn.')) return;
    fetch('/delete-pat', { method:'POST' }).then(function(r){ return r.json(); })
      .then(function(j){ toast(j.ok?'Đã xoá PAT':'Lỗi xoá', j.ok); if(j.ok) close(); })
      .catch(function(){ toast('Lỗi mạng', false); }); });
})();
// popup nhắc PAT khi server trả no_pat
function patToast(j){ if(j && j.code==='no_pat'){ var ov=$('setOverlay'); if(ov) ov.classList.add('open');
  toast(j.msg || 'Cần PAT để thao tác Jira', false); return true; } return false; }

// ---------- trang /settings ĐẦY ĐỦ (render_settings_page) — khác modal ở trên (IDs riêng) ----------
(function(){
  var input=$('patInput'); if(!input) return;   // chỉ chạy trên trang /settings
  var saveBtn=$('patSave'), showBtn=$('patShow'), delBtn=$('patDelete');
  if(saveBtn) saveBtn.addEventListener('click', function(){
    var pat=(input.value||'').trim(); if(!pat){ toast('Chưa nhập PAT', false); return; }
    saveBtn.disabled=true;
    postJSON('/save-pat', { pat:pat }, 20000).then(function(j){
      saveBtn.disabled=false; toast(j.msg || (j.ok?'Đã lưu PAT':'Lỗi lưu PAT'), j.ok);
      if(j.ok){ input.value=''; setTimeout(function(){ location.reload(); }, 1500); }
    }).catch(function(){ saveBtn.disabled=false; toast('Lỗi mạng khi lưu PAT', false); }); });
  if(showBtn) showBtn.addEventListener('click', function(){
    input.type = input.type==='password' ? 'text' : 'password'; });
  if(delBtn) delBtn.addEventListener('click', function(){
    if(!confirm('Xoá PAT đã lưu? Sau đó thao tác Jira sẽ không còn ghi tên bạn.')) return;
    fetch('/delete-pat', { method:'POST' }).then(function(r){ return r.json(); })
      .then(function(j){ toast(j.ok?'Đã xoá PAT':'Lỗi xoá', j.ok);
        if(j.ok) setTimeout(function(){ location.reload(); }, 1200); })
      .catch(function(){ toast('Lỗi mạng', false); }); });
  var driveDc=$('driveDisconnect');
  if(driveDc) driveDc.addEventListener('click', function(){
    if(!confirm('Ngắt kết nối Drive? Background sync bug log sẽ ngừng đọc file cho tới khi kết nối lại.')) return;
    fetch('/disconnect-drive', { method:'POST' }).then(function(r){ return r.json(); })
      .then(function(j){ toast(j.ok?'Đã ngắt kết nối Drive':'Lỗi ngắt kết nối', j.ok);
        if(j.ok) setTimeout(function(){ location.reload(); }, 1200); })
      .catch(function(){ toast('Lỗi mạng', false); }); });
})();

// ---------- notifications bell ----------
(function(){
  var NOTIFS = (readJSON('qaNotif') || []).slice();
  var notif=$('notif'), bell=$('bellBtn'), list=$('notifList'), dot=$('bellDot');
  if(!notif||!bell||!list) return;
  var BASE_TITLE=(document.title||'').replace(/^\(\d+\)\s*/, '');   // tên tab gốc, bỏ prefix cũ nếu có
  var filter='all';
  var localRead={};   // id đã dismiss tại máy này phiên này -> giữ "đã đọc" kể cả khi poll trả về trước lúc Jira property kịp sync
  var seenIds={};     // mọi id từng thấy -> phát hiện mục MỚI giữa 2 lần poll để toast
  var KIND_IC={created:'fiber_new', comment:'chat_bubble', status:'swap_horiz', assignee:'person_add',
               duedate:'event', priority:'bolt', summary:'edit', custom_status:'sell'};
  function kindCls(n){ if(n.mention) return 'k-mention'; if(n.kind==='status') return 'k-status';
    if(n.kind==='duedate') return 'k-due'; return ''; }
  function minsAgo(when){ if(!when) return 9e9; var t=Date.parse(when); if(isNaN(t)) return 9e9;
    return Math.max(0, Math.round((Date.now()-t)/60000)); }
  function timeAgo(m){ if(m<1) return 'vừa xong'; if(m<60) return m+' phút';
    var h=Math.floor(m/60); if(h<24) return h+' giờ'; return Math.floor(h/24)+' ngày'; }
  function ntext(n){ var k='<b>'+esc(n.key)+'</b>', w='<b>'+esc(n.author||'—')+'</b>';
    switch(n.kind){
      case 'created':  return w+' tạo mới '+k;
      case 'comment':  return n.mention ? (w+' nhắc đến bạn ở '+k) : (w+' bình luận ở '+k);
      case 'status':   return w+' đổi trạng thái '+k+' → <b>'+esc(n.new||'')+'</b>';
      case 'assignee': return w+' reassign '+k+': '+esc(n.old||'')+' → '+esc(n.new||'');
      case 'duedate':  return w+' đổi hạn '+k+': '+esc(n.old||'')+' → '+esc(n.new||'');
      case 'priority': return w+' đổi ưu tiên '+k;
      case 'summary':  return w+' đổi tiêu đề '+k;
      case 'custom_status': { var nv=n.new||'';
        if(nv.indexOf('✕')===0) return w+' gỡ nhãn '+k+': '+esc(nv.replace(/^✕\s*/,''));
        if(nv.indexOf('—')===0) return w+' gỡ nhãn '+k;
        return w+' gắn nhãn '+k+': '+esc(nv); }
      default: return w+' cập nhật '+k;
    } }
  function visible(){
    var l=NOTIFS.slice().sort(function(a,b){ return minsAgo(a.when)-minsAgo(b.when); });
    return filter==='unread' ? l.filter(function(n){ return n.is_unread; }) : l;
  }
  function render(){
    var l=visible();
    list.innerHTML = l.length ? l.map(function(n){
      var ic=KIND_IC[n.kind]||'notifications';
      var av=avById(n.author||'?');
      var rsn = n.mention ? '<span class="nrsn mention">Được nhắc</span>'
                          : '<span class="nrsn watch">Đang theo dõi</span>';
      var snip = n.body ? '<div class="nsnip">"'+esc(n.body)+'"</div>' : '';
      var unreadCls = n.is_unread ? ' unread' : '';
      var dotHtml = n.is_unread ? '<span class="ndot"></span>' : '';
      return '<div class="notif-item'+unreadCls+'" data-actid="'+esc(n.id)+'" data-key="'+esc(n.key)+'">'
        +'<span class="nav-wrap"><span class="av '+av+'">'+esc(initOf(n.author))+'</span>'
        +'<span class="nkind '+kindCls(n)+' material-symbols-rounded">'+ic+'</span></span>'
        +'<div class="ncontent"><div class="nt">'+ntext(n)+'</div>'+snip
        +'<div class="nmeta">'+rsn+'<span class="ntime">'+timeAgo(minsAgo(n.when))+'</span></div></div>'
        +dotHtml+'</div>';
    }).join('') : '<div class="notif-empty">Không có thông báo mới 🎉</div>';
    var unreadCount = NOTIFS.filter(function(n){ return n.is_unread; }).length;
    if(dot){ if(unreadCount){ dot.style.display='flex'; dot.textContent=unreadCount>99?'99+':unreadCount; }
             else dot.style.display='none'; }
    // Số noti chưa đọc lên title tab browser: "(3) QA Workspace — ..."
    document.title = unreadCount ? '('+(unreadCount>99?'99+':unreadCount)+') '+BASE_TITLE : BASE_TITLE;
  }
  function markRead(ids){ var set={}; ids.forEach(function(i){ set[i]=1; localRead[i]=1; });
    NOTIFS.forEach(function(n){ if(set[n.id]) n.is_unread=false; }); render(); }
  bell.addEventListener('click', function(e){ e.stopPropagation(); notif.classList.toggle('open');
    var m=$('pmenu'); if(m) m.classList.remove('open'); });
  document.addEventListener('click', function(e){
    if(!e.target.closest('#notif') && !e.target.closest('#bellBtn')) notif.classList.remove('open'); });
  document.querySelectorAll('.nf-tab').forEach(function(b){ b.addEventListener('click', function(){
    filter=b.getAttribute('data-nf'); document.querySelectorAll('.nf-tab').forEach(function(x){
      x.classList.toggle('active', x===b); }); render(); }); });
  var all=$('notifReadAll');
  if(all) all.addEventListener('click', function(){
    var unreads = NOTIFS.filter(function(n){ return n.is_unread; });
    if(!unreads.length) return;
    var ids=unreads.map(function(n){ return n.id; });
    postJSON('/dismiss', { ids: ids }, 20000).catch(function(){});
    markRead(ids); toast('Đã đánh dấu tất cả đã đọc', true); });
  list.addEventListener('click', function(e){
    var it=e.target.closest('.notif-item'); if(!it) return;
    var id=it.getAttribute('data-actid'), key=it.getAttribute('data-key');
    var isUnread = it.classList.contains('unread');
    if(isUnread){
      postJSON('/dismiss', { ids: [id] }, 20000).catch(function(){});
      markRead([id]);
    }
    notif.classList.remove('open');
    if(window.__openDetail) window.__openDetail(key);   // dashboard -> drawer
    else if(window.__jiraBase) window.open(window.__jiraBase+'/browse/'+key, '_blank');
    else toast('Đã đọc thông báo '+key, true); });

  // --------- poll real-time (Decision #24): cập nhật chuông + toast, KHÔNG reload trang ---------
  var POLL_MS=60000;
  NOTIFS.forEach(function(n){ seenIds[n.id]=1; });   // baseline embed lúc load -> không toast giả lần poll đầu
  function applyFeed(acts){
    if(!Array.isArray(acts)) return;
    var freshUnread=0;
    acts.forEach(function(n){
      if(localRead[n.id]) n.is_unread=false;          // dismiss local thắng (Jira property có thể chưa kịp sync)
      if(!seenIds[n.id]){ seenIds[n.id]=1; if(n.is_unread) freshUnread++; }
    });
    NOTIFS = acts;
    render();
    if(freshUnread>0) toast('🔔 '+freshUnread+' thông báo mới', true);
  }
  function poll(){
    if(document.hidden) return;                        // tab ẩn -> bỏ qua, đỡ tải Jira
    getJSON('/activity-feed', 20000).then(function(j){
      if(j && j.ok){ applyFeed(j.activities);
        // Vá status Jira + nhãn nội bộ vào bảng/drawer (Decision #24), KHÔNG reload trang.
        if(window.__applyTaskPatch && j.tasks) window.__applyTaskPatch(j.tasks);
      }
    }).catch(function(){});                             // lỗi mạng/timeout -> im lặng, thử lại lần sau
  }
  setInterval(poll, POLL_MS);
  document.addEventListener('visibilitychange', function(){ if(!document.hidden) poll(); });

  render();
  // Poll NGAY sau khi render (không chờ 60s): chuông embed lúc load có thể là data SWR cũ
  // (server không block trên feed nặng) -> poll async kéo về bản mới, KHÔNG chặn điều hướng.
  setTimeout(poll, 300);
})();

// ================= DASHBOARD (guard #rows) =================
(function(){
  var tbody=$('rows'); if(!tbody) return;
  var DATA = readJSON('qaData') || { tasks:[], meta:{} };
  var TASKS = DATA.tasks || [];
  window.__jiraBase = (TASKS[0] && TASKS[0].jiraUrl ? TASKS[0].jiraUrl.replace(/\/browse\/.*$/, '') : (window.__jiraBase||''));

  // --------- ADMIN DASHBOARD v2 (pills + member filter + 5-col table + KPI) ---------
  if(DATA.meta && DATA.meta.isAdmin){
    var custMap={}; (window.QA_CUSTOM_STATUSES||[]).forEach(function(p){ custMap[p[0]]=p[1]; });
    var curPill='todo', curMember='all', curPage=1, PER_PAGE=5;
    var COMMENTS={}, DETAIL={}, inflight={};

    function badgeCls(v){ v=(v||'').toUpperCase();
      if(v==='DONE') return 'b-done'; if(v==='IN PROGRESS') return 'b-checking';
      if(v==='PENDING') return 'b-blocked'; if(v==='TO DO') return 'b-todo';
      if(v==='CANCELLED') return 'b-critical'; return 'b-todo'; }

    function pillMatch(t){
      if(curPill==='todo') return t.active && t.jira==='TO DO' && !t.isNew && !t.overdue;
      // In Progress = MỌI task active không phải TO DO (gồm status active mới) → không status nào lọt (issue #39)
      if(curPill==='progress') return t.active && t.jira!=='TO DO' && !t.stuck && !t.overdue;
      if(curPill==='new') return t.isNew;
      if(curPill==='stuck') return t.stuck;
      if(curPill==='overdue') return t.overdue;
      if(curPill==='done') return t.jira.toUpperCase()==='DONE';
      return true;
    }
    function memberMatch(t){ return curMember==='all' || t.assignee.name===curMember; }
    function searchMatch(t){
      var q=(($('searchInp')||{}).value||'').toLowerCase();
      return !q || (t.key+' '+t.summary).toLowerCase().indexOf(q)>=0;
    }
    function filtered(){
      return TASKS.filter(function(t){ return pillMatch(t)&&memberMatch(t)&&searchMatch(t); })
        .sort(function(a,b){ return (b.updated||'')<(a.updated||'')?-1:((b.updated||'')>(a.updated||'')?1:0); });
    }

    function chipHTML(t){
      if(!t.customs||!t.customs.length) return '';
      return '<div class="cust-chips">'+t.customs.map(function(v){
        return '<span class="cust-chip"><span class="material-symbols-rounded">circle</span>'
          +esc(custMap[v]||v)+'<span class="rm material-symbols-rounded" data-key="'+esc(t.key)
          +'" data-val="'+esc(v)+'">close</span></span>'; }).join('')+'</div>';
    }

    function renderRows(){
      var all=filtered(), total=all.length;
      var pages=Math.max(1,Math.ceil(total/PER_PAGE));
      if(curPage>pages) curPage=pages; if(curPage<1) curPage=1;
      var start=(curPage-1)*PER_PAGE, slice=all.slice(start, start+PER_PAGE);

      var label={todo:'To Do Tasks',progress:'In Progress Tasks',new:'New Tasks',
                 stuck:'Stuck Tasks',overdue:'Overdue Tasks',done:'Done Tasks'};
      $('tableTitleText').innerHTML='<span class="material-symbols-rounded">assignment</span><span>'+(label[curPill]||'Tasks')+'</span>';

      if(!total){
        tbody.innerHTML='<tr><td colspan="6"><div class="empty-state"><span class="material-symbols-rounded">folder_off</span>Không tìm thấy task nào.</div></td></tr>';
        $('pager').innerHTML=''; return;
      }

      var html=slice.map(function(t){
        return '<tr data-key="'+esc(t.key)+'">'
          +'<td><a class="cell-key" href="'+esc(t.jiraUrl)+'" target="_blank" onclick="event.stopPropagation()">'+esc(t.key)+'</a></td>'
          +'<td><span class="cell-title">'+esc(t.summary)+'</span></td>'
          +'<td><div class="cell-member"><span class="m-av '+esc(t.assignee.cls)+'">'+esc(t.assignee.init)+'</span>'
          +'<span>'+esc(t.assignee.name)+'</span></div></td>'
          +'<td class="status-cell"><div class="stat-wrap"><span class="badge '+badgeCls(t.jira)+'">'+esc(t.jira)+'</span>'
          +'<button class="caret material-symbols-rounded mi-sm" data-act="smenu" data-key="'+esc(t.key)+'">expand_more</button></div>'+chipHTML(t)+'</td>'
          +'<td class="cell-date"><span class="due '+esc(t.dueCls)+'">'+esc(t.dueDisp)+'</span></td>'
          +'<td class="cell-date">'+esc(t.createdDisp)+'</td>'
          +'<td class="cell-date">'+esc(t.updatedDisp)+'</td></tr>';
      }).join('');
      for(var k=slice.length;k<PER_PAGE;k++){
        html+='<tr class="pager-filler"><td>&nbsp;</td><td><span class="cell-title">&nbsp;</span></td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>';
      }
      tbody.innerHTML=html;

      var ph='<span class="pager-summary">'+(start+1)+'–'+(start+slice.length)+' / '+total+' task · trang '+curPage+'/'+pages+'</span>'
        +'<div class="pager-nav"><button class="pager-btn"'+(curPage<=1?' disabled':'')+' data-pg="'+(curPage-1)+'"><span class="material-symbols-rounded mi-xs">chevron_left</span></button>';
      for(var i=1;i<=pages;i++) ph+='<button class="pager-page'+(i===curPage?' active':'')+'" data-pg="'+i+'">'+i+'</button>';
      ph+='<button class="pager-btn"'+(curPage>=pages?' disabled':'')+' data-pg="'+(curPage+1)+'"><span class="material-symbols-rounded mi-xs">chevron_right</span></button></div>';
      $('pager').innerHTML=ph;
      // Giữ smenu mở bám đúng caret sau khi rebuild bảng.
      if(adCurCaret && adSmenu && adSmenu.classList.contains('open')){
        var sk=adCurCaret.getAttribute('data-key');
        var nc=document.querySelector('[data-act="smenu"][data-key="'+sk+'"]');
        if(nc) adCurCaret=nc;
      }
    }

    function updateCounts(){
      var counts={todo:0,progress:0,'new':0,stuck:0,overdue:0,done:0};
      TASKS.forEach(function(t){
        if(!memberMatch(t)||!searchMatch(t)) return;
        if(t.isNew) counts['new']++;
        if(t.overdue) counts.overdue++;
        if(t.stuck) counts.stuck++;
        if(t.active && t.jira==='TO DO' && !t.isNew && !t.overdue) counts.todo++;
        if(t.active && t.jira!=='TO DO' && !t.stuck && !t.overdue) counts.progress++;
        if(t.jira.toUpperCase()==='DONE') counts.done++;
      });
      ['todo','progress','new','stuck','overdue','done'].forEach(function(k){
        var el=$('count-'+k); if(el) el.textContent=counts[k];
      });
    }

    function updateKPIs(){
      var active=TASKS.filter(function(t){ return memberMatch(t)&&t.jira.toUpperCase()!=='DONE'; });
      var done=TASKS.filter(function(t){ return memberMatch(t)&&t.jira.toUpperCase()==='DONE'; });
      var vel=(done.length/7+0.1).toFixed(1);
      var ov=active.filter(function(t){ return t.overdue; }).length;
      var v=$('kpiVelocity'); if(v) v.textContent=vel+' Tasks/Day';
      var tt=$('kpiTotalTasks'); if(tt) tt.textContent=active.length+' Tasks';
      var b=$('kpiBugs'); if(b) b.textContent=ov+' Open';
    }

    // Pill clicks
    document.querySelectorAll('.pill-btn').forEach(function(btn){
      btn.addEventListener('click', function(){
        document.querySelectorAll('.pill-btn').forEach(function(b){ b.classList.remove('active'); });
        btn.classList.add('active');
        curPill=btn.getAttribute('data-pill'); curPage=1;
        renderRows();
      });
    });

    // Member dropdown
    var mBtn=$('memberFilterBtn'), mDrop=$('memberDropdown');
    if(mBtn&&mDrop){
      mBtn.addEventListener('click', function(e){ e.stopPropagation(); mDrop.classList.toggle('open');
        var n=$('notif'); if(n) n.classList.remove('open');
        var p=$('pmenu'); if(p) p.classList.remove('open'); });
      document.querySelectorAll('.member-opt').forEach(function(opt){
        opt.addEventListener('click', function(){
          document.querySelectorAll('.member-opt').forEach(function(o){ o.classList.remove('active'); });
          opt.classList.add('active');
          curMember=opt.getAttribute('data-member');
          $('selectedMemberLabel').textContent=opt.textContent;
          curPage=1; mDrop.classList.remove('open');
          updateCounts(); renderRows(); updateKPIs();
        });
      });
      document.addEventListener('click', function(e){
        if(!e.target.closest('.member-filter-wrap')) mDrop.classList.remove('open');
      });
    }

    // Search
    var si=$('searchInp'); if(si) si.addEventListener('input', function(){ curPage=1; updateCounts(); renderRows(); updateKPIs(); });

    // Pager clicks
    $('pager').addEventListener('click', function(e){
      var b=e.target.closest('[data-pg]'); if(!b) return;
      curPage=parseInt(b.getAttribute('data-pg'),10);
      renderRows();
    });

    // Row clicks -> drawer
    tbody.addEventListener('click', function(e){
      if(e.target.closest('.pager-filler')) return;
      var rm=e.target.closest('.rm[data-val]');
      if(rm){ e.stopPropagation(); adRmCust(rm.getAttribute('data-key'), rm.getAttribute('data-val')); return; }
      var caret=e.target.closest('[data-act="smenu"]');
      if(caret){ e.stopPropagation(); adOpenStatusMenu(caret); return; }
      var tr=e.target.closest('tr[data-key]'); if(!tr) return;
      var key=tr.getAttribute('data-key');
      openDetail(key);
    });

    // Detail drawer
    var EXTRA={};   // task không nằm trong bucket (vd CANCELLED) -> dựng từ /issue-comments
    function taskByKey(k){ return TASKS.filter(function(x){ return x.key===k; })[0] || EXTRA[k]; }
    function synthTask(key, d){
      return { key:key, summary:d.summary||key, jira:d.status||'',
        customs:[], canCustom:false,
        assignee:{ name:d.assignee||'—', init:initOf(d.assignee||'?'), cls:avById(d.assignee||'?') },
        due:d.duedate||'', dueDisp:d.duedate||'Chưa đặt hạn', dueCls:'',
        created:d.created||'', createdDisp:d.created||'—',
        overdue:false, stuck:false, isNew:false,
        jiraUrl:(window.__jiraBase||'')+'/browse/'+key };
    }
    function openDetail(key){
      var t=taskByKey(key);
      $('drawerOv').classList.add('open'); $('drawer').classList.add('open');
      if(t) renderDrawer(t);
      else $('drawer').innerHTML='<div class="drawer-body"><div class="cmt-empty">Đang tải…</div></div>';
      if(COMMENTS[key]===undefined){
        COMMENTS[key]=null;
        getJSON('/issue-comments?key='+encodeURIComponent(key), 20000)
          .then(function(j){ if(j&&j.ok&&j.detail){ COMMENTS[key]=j.detail.comments||[]; DETAIL[key]=j.detail;
              if(!taskByKey(key)) EXTRA[key]=synthTask(key, j.detail); }
            else COMMENTS[key]=COMMENTS[key]||[];
            var tt=taskByKey(key);
            if(tt && $('drawer').classList.contains('open')) renderDrawer(tt);
          }).catch(function(){ COMMENTS[key]=COMMENTS[key]||[]; });
      }
    }
    window.__openDetail = openDetail;
    function closeDetail(){ $('drawerOv').classList.remove('open'); $('drawer').classList.remove('open'); }
    function renderDrawer(t){
      var chips=(t.customs&&t.customs.length)?t.customs.map(function(v){
        return '<span class="cust-chip"><span class="material-symbols-rounded">circle</span>'+esc(custMap[v]||v)+'</span>';}).join('')
        :'<span style="color:var(--on-surface-variant)">—</span>';
      var flags='';
      if(t.overdue) flags+='<span class="dt-flag od"><span class="material-symbols-rounded mi-xs">event_busy</span>Quá hạn</span>';
      if(t.stuck) flags+='<span class="dt-flag st"><span class="material-symbols-rounded mi-xs">hourglass_bottom</span>Kẹt</span>';
      if(!flags) flags='<span style="color:var(--on-surface-variant)">—</span>';
      var list=COMMENTS[t.key]; var hist;
      if(list===null||list===undefined) hist='<div class="cmt-empty">Đang tải…</div>';
      else if(!list.length) hist='<div class="cmt-empty">Chưa có bình luận nào</div>';
      else hist=list.map(function(c){ return '<div class="cmt-item"><span class="av '+avById(c.author)+'">'+esc(initOf(c.author))+'</span>'
        +'<div class="cmt-main"><div class="cmt-meta"><b>'+esc(c.author)+'</b><span>'+esc((c.when||'').slice(0,16).replace('T',' '))+'</span></div>'
        +'<div class="cmt-text">'+esc(c.body)+'</div></div></div>'; }).join('');
      var desc=(DETAIL[t.key]&&DETAIL[t.key].description)?esc(DETAIL[t.key].description):esc(t.summary);
      $('drawer').innerHTML='<div class="drawer-head"><a class="key" href="'+esc(t.jiraUrl)+'" target="_blank">'+esc(t.key)+'</a>'
        +'<span class="badge '+badgeCls(t.jira)+'">'+esc(t.jira)+'</span>'
        +'<button class="x material-symbols-rounded" data-act="drawer-close">close</button></div>'
        +'<div class="drawer-body"><h2>'+esc(t.summary)+'</h2>'
        +'<div class="dt-grid"><div class="lbl">Người xử lý</div><div class="val"><span class="assignee"><span class="av '+esc(t.assignee.cls)+'">'+esc(t.assignee.init)+'</span> '+esc(t.assignee.name)+'</span></div>'
        +'<div class="lbl">Ngày tạo</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].created)?esc(DETAIL[t.key].created):esc(t.createdDisp||'—'))+'</div>'
        +'<div class="lbl">Hạn chót</div><div class="val"><span class="due '+esc(t.dueCls)+'">'+esc(t.dueDisp)+'</span></div>'
        +'<div class="lbl">Cập nhật</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].updated)?esc(DETAIL[t.key].updated):'—')+'</div>'
        +'<div class="lbl">Dev phụ trách</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].devs&&DETAIL[t.key].devs.length)?DETAIL[t.key].devs.map(esc).join(', '):'—')+'</div>'
        +'<div class="lbl">Nhãn nội bộ</div><div class="val">'+chips+'</div>'
        +'<div class="lbl">Cảnh báo</div><div class="val">'+flags+'</div></div>'
        +'<div class="dt-sec-title">Mô tả</div><div class="dt-desc">'+desc+'</div>'
        +bugSectionHtml(DETAIL[t.key])
        +testcaseSectionHtml(DETAIL[t.key])
        +'<div class="dt-cmts"><div class="dt-sec-title">Bình luận ('+(list&&list.length||0)+')</div>'
        +'<div class="cmt-panel"><div class="cmt-history">'+hist+'</div>'
        +'<div class="cmt-box"><textarea id="dtTa-'+esc(t.key)+'" placeholder="Viết bình luận..."></textarea>'
        +'<div class="cmt-foot"><button class="lbtn primary" data-act="dt-send" data-key="'+esc(t.key)+'">Gửi</button></div></div></div></div></div>';
    }
    document.addEventListener('click', function(e){
      var a=e.target.closest('[data-act]'); if(!a) return;
      if(a.getAttribute('data-act')==='drawer-close') closeDetail();
      else if(a.getAttribute('data-act')==='dt-send'){
        var key=a.getAttribute('data-key');
        var ta=$('dtTa-'+key); var v=(ta&&ta.value||'').trim();
        if(!v){ toast('Chưa nhập bình luận', false); return; }
        postJSON('/add-comment', {key:key,body:v}, 20000).then(function(j){
          if(patToast(j)) return;
          if(j.ok){ (COMMENTS[key]=COMMENTS[key]||[]).push({author:'Bạn',when:new Date().toISOString(),body:v});
            renderDrawer(taskByKey(key)); toast('Đã gửi comment ✓', true); }
          else toast(j.msg||'Lỗi gửi comment', false);
        }).catch(function(){ toast('Lỗi mạng', false); });
      }
    });
    var dov=$('drawerOv'); if(dov) dov.addEventListener('click', closeDetail);
    document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeDetail(); });

    // Vá real-time từ poll (Decision #24): cập nhật status Jira + nhãn nội bộ vào TASKS rồi
    // re-render bảng/KPI/drawer, KHÔNG reload. Chỉ render lại khi có gì THỰC SỰ đổi (tránh
    // flicker + nuốt comment đang gõ mỗi 60s).
    window.__applyTaskPatch=function(map){
      var changed=false;
      TASKS.forEach(function(t){ var p=map[t.key]; if(!p) return;
        if(p.status && p.status!==t.jira){ t.jira=p.status; changed=true; }
        if(p.customs){ var a=(t.customs||[]).join(','), b=p.customs.join(',');
          if(a!==b){ t.customs=p.customs; changed=true; } }
      });
      if(!changed) return;
      updateCounts(); renderRows(); updateKPIs();
      var dEl=$('drawer');
      if(dEl && dEl.classList.contains('open')){
        var ka=dEl.querySelector('.key'); var ok=ka&&ka.textContent;
        if(ok && map[ok]){ var tt=taskByKey(ok); if(tt) renderDrawer(tt); }
      }
    };

    // ----- status menu (.smenu) — đổi status Jira + gắn nhãn nội bộ (parity với QA member) -----
    var adSmenu=$('smenu'), adCurCaret=null, adCurJira=null;
    function adCloseSmenu(){ if(adSmenu){ adSmenu.classList.remove('open'); adSmenu.innerHTML=''; } adCurCaret=null; adCurJira=null; }
    function adRenderSmenu(t, jiraState){
      adCurJira=jiraState;
      var cur={}; (t.customs||[]).forEach(function(v){ cur[v]=1; });
      var h='<div class="smenu-grp">Status Jira</div>';
      if(jiraState===null) h+='<div class="smenu-note muted"><span class="material-symbols-rounded mi-sm">hourglass_empty</span>Đang tải status…</div>';
      else if(jiraState.code==='no_pat') h+='<div class="smenu-note" data-sm="nopat"><span class="material-symbols-rounded mi-sm">lock</span>Cần PAT để đổi status Jira — bấm để thêm</div>';
      else if(!jiraState.ok) h+='<div class="smenu-note muted"><span class="material-symbols-rounded mi-sm">error</span>'+esc(jiraState.msg||'Lỗi tải status')+'</div>';
      else if(!jiraState.transitions.length) h+='<div class="smenu-note muted"><span class="material-symbols-rounded mi-sm">info</span>Không có bước chuyển khả dụng</div>';
      else jiraState.transitions.forEach(function(tr){
        h+='<div class="smenu-opt" data-sm="jira" data-id="'+esc(tr.id)+'" data-to="'+esc(tr.to)+'">'
          +'<span class="dot" style="background:#0052cc"></span>'+esc(tr.to)+'<span class="chk material-symbols-rounded">check</span></div>'; });
      var allowed=t.canCustom;
      h+='<div class="smenu-grp brd">Nhãn nội bộ — chọn nhiều</div>';
      if(!allowed) h+='<div class="smenu-note muted"><span class="material-symbols-rounded mi-sm">info</span>Chỉ gắn khi <b>TO DO</b> / <b>In Progress</b></div>';
      (window.QA_CUSTOM_STATUSES||[]).forEach(function(p){
        var on=cur[p[0]]?' on':'';
        h+='<div class="smenu-opt'+on+(allowed?'':' disabled')+'"'+(allowed?' data-sm="cust" data-val="'+esc(p[0])+'"':'')+'>'
          +'<span class="dot" style="background:#6554c0"></span>'+esc(p[1])+'<span class="chk material-symbols-rounded">check</span></div>'; });
      h+='<div class="smenu-foot"><small>'+((t.customs||[]).length?(t.customs.length+' nhãn'):'Chưa gắn nhãn')+'</small>'
        +'<button type="button" data-sm="close">Xong</button></div>';
      adSmenu.innerHTML=h;
    }
    function adPositionSmenu(caret){
      adSmenu.classList.add('open'); adSmenu.style.maxHeight='none';
      var r=caret.getBoundingClientRect(), gap=6, pad=8;
      var below=window.innerHeight-r.bottom-gap-pad, above=r.top-gap-pad;
      var avail=Math.max(below,above); adSmenu.style.maxHeight=avail+'px';
      var mh=Math.min(adSmenu.offsetHeight, avail);
      var top=(below>=above)?r.bottom+gap:r.top-gap-mh;
      adSmenu.style.top=Math.max(pad, top)+'px';
      adSmenu.style.left=Math.min(r.left, window.innerWidth-292)+'px';
    }
    function adOpenStatusMenu(caret){
      var key=caret.getAttribute('data-key');
      if(adCurCaret && adCurCaret.getAttribute('data-key')===key && adSmenu.classList.contains('open')){ adCloseSmenu(); return; }
      adCurCaret=caret; var t=taskByKey(key); if(!t) return;
      adRenderSmenu(t, null); adPositionSmenu(caret);
      postJSON('/jira-transitions', { key:key }, 20000)
        .then(function(j){ if(adCurCaret && adCurCaret.getAttribute('data-key')===key && adSmenu.classList.contains('open')){ adRenderSmenu(t, j); adPositionSmenu(adCurCaret); } })
        .catch(function(){ if(adCurCaret && adCurCaret.getAttribute('data-key')===key && adSmenu.classList.contains('open')){ adRenderSmenu(t, { ok:false, msg:'Lỗi mạng khi tải status' }); adPositionSmenu(adCurCaret); } });
    }
    if(adSmenu) adSmenu.addEventListener('click', function(e){
      var o=e.target.closest('[data-sm]'); if(!o) return;
      var kind=o.getAttribute('data-sm'); if(!adCurCaret) return;
      var key=adCurCaret.getAttribute('data-key'), t=taskByKey(key);
      if(kind==='close'){ adCloseSmenu(); }
      else if(kind==='nopat'){ adCloseSmenu(); var ov=$('setOverlay'); if(ov) ov.classList.add('open'); }
      else if(kind==='jira'){ adCloseSmenu(); adDoTransition(key, o.getAttribute('data-id'), o.getAttribute('data-to')); }
      else if(kind==='cust'){ adSetCustom(t, key, o.getAttribute('data-val')); }
    });
    function adDoTransition(key, id, toName){
      if(inflight['t'+key]) return; inflight['t'+key]=true;
      toast(key+': đang đổi status…', true);
      postJSON('/do-transition', { key:key, id:id }, 20000).then(function(j){
        inflight['t'+key]=false; if(patToast(j)) return;
        if(j.ok){ var t=taskByKey(key); if(t){ t.jira=toName; if(!(toName==='TO DO'||toName==='In Progress')) t.customs=[]; }
          updateCounts(); renderRows(); updateKPIs(); toast(key+' → '+toName+' ✓', true); }
        else toast(j.msg||('Lỗi đổi status '+key), false);
      }).catch(function(){ inflight['t'+key]=false; toast('Lỗi mạng khi đổi status', false); });
    }
    function adSetCustom(t, key, val){
      if(!t) return;
      var fk=key+'#'+val; if(inflight[fk]) return; inflight[fk]=true;
      postJSON('/set-custom-status', { key:key, status:val, summary:t.summary||'' }, 20000).then(function(j){
        inflight[fk]=false;
        if(!j.ok){ toast('Lỗi lưu nhãn '+key, false); return; }
        t.customs = Array.isArray(j.values) ? j.values : (t.customs||[]);
        renderRows();
        if(adCurCaret && adSmenu.classList.contains('open')){ adRenderSmenu(t, adCurJira); adPositionSmenu(adCurCaret); }
      }).catch(function(){ inflight[fk]=false; toast('Lỗi mạng khi lưu nhãn', false); });
    }
    function adRmCust(key, val){ var t=taskByKey(key); if(t) adSetCustom(t, key, val); }
    document.addEventListener('click', function(e){
      if(adSmenu && adSmenu.classList.contains('open') && !e.target.closest('#smenu') && !e.target.closest('[data-act="smenu"]')) adCloseSmenu(); });
    window.addEventListener('scroll', function(e){
      if(!(adSmenu && adSmenu.classList.contains('open'))) return;
      if(e.target && e.target.nodeType===1 && (e.target===adSmenu || e.target.closest && e.target.closest('#smenu'))) return;
      adCloseSmenu();
    }, true);
    document.addEventListener('keydown', function(e){ if(e.key==='Escape') adCloseSmenu(); });

    // Initial render
    updateCounts(); renderRows(); updateKPIs();
    return; // <-- skip QA member code below
  }
  // --------- END ADMIN DASHBOARD ---------

  var custMap={}; (window.QA_CUSTOM_STATUSES||[]).forEach(function(p){ custMap[p[0]]=p[1]; });
  var COMMENTS={};        // key -> [{author,when,body}] (lazy)
  var DETAIL={};          // key -> {description}
  var openCmt={};         // key -> panel mở
  var curFilter='all', curPage=1, PER_PAGE=8;
  var inflight={};

  function jiraCls(v){ v=(v||'').toUpperCase();
    if(v==='DONE') return 'b-done'; if(v==='CANCELLED') return 'b-critical';
    if(v==='IN PROGRESS') return 'b-checking'; if(v==='PENDING') return 'b-blocked';
    if(v==='TO DO') return 'b-todo'; return 'b-todo'; }
  var EXTRA={};   // task ngoài bucket (vd CANCELLED) -> dựng từ /issue-comments
  function taskByKey(k){ return TASKS.filter(function(t){ return t.key===k; })[0] || EXTRA[k]; }
  function synthTask(key, d){
    return { key:key, summary:d.summary||key, jira:d.status||'',
      customs:[], canCustom:false,
      assignee:{ name:d.assignee||'—', init:initOf(d.assignee||'?'), cls:avById(d.assignee||'?') },
      due:d.duedate||'', dueDisp:d.duedate||'Chưa đặt hạn', dueCls:'',
      created:d.created||'', createdDisp:d.created||'—',
      overdue:false, stuck:false, isNew:false,
      jiraUrl:(window.__jiraBase||'')+'/browse/'+key };
  }
  function matchFilter(t,f){ if(f==='overdue') return t.overdue; if(f==='stuck') return t.stuck;
    if(f==='dueweek') return !!t.dueWeek; return true; }
  function visibleTasks(){
    var q=(($('searchInp')||{}).value||'').toLowerCase();
    return TASKS.filter(function(t){ return matchFilter(t,curFilter) &&
      (!q || (t.key+' '+t.summary).toLowerCase().indexOf(q)>=0); });
  }

  function chipHTML(t){
    if(!t.customs || !t.customs.length) return '';
    return '<div class="cust-chips">'+t.customs.map(function(v){
      return '<span class="cust-chip"><span class="material-symbols-rounded">circle</span>'
        +esc(custMap[v]||v)+'<span class="rm material-symbols-rounded" data-key="'+esc(t.key)
        +'" data-val="'+esc(v)+'">close</span></span>'; }).join('')+'</div>';
  }
  function rowHTML(t){
    var nc=(COMMENTS[t.key]||[]).length;
    var cnt = nc ? '<span class="cmt-count">'+nc+'</span>' : '';
    return '<tr'+(t.overdue?' class="overdue-row"':'')+' data-key="'+esc(t.key)+'">'
      +'<td><a class="key" href="'+esc(t.jiraUrl)+'" target="_blank">'+esc(t.key)+'</a></td>'
      +'<td class="title clickable" data-act="detail" data-key="'+esc(t.key)+'">'+esc(t.summary)+'</td>'
      +'<td class="status-cell"><div class="stat-wrap"><span class="badge '+jiraCls(t.jira)+'">'+esc(t.jira)+'</span>'
      +'<button class="caret material-symbols-rounded mi-sm" data-act="smenu" data-key="'+esc(t.key)+'">expand_more</button></div>'+chipHTML(t)+'</td>'
      +'<td><span class="assignee"><span class="av '+esc(t.assignee.cls)+'">'+esc(t.assignee.init)+'</span> '+esc(t.assignee.name)+'</span></td>'
      +'<td class="cell-date">'+esc(t.createdDisp)+'</td>'
      +'<td><span class="due '+esc(t.dueCls)+'">'+esc(t.dueDisp)+'</span></td>'
      +'<td><button class="act-btn'+(openCmt[t.key]?' on':'')+'" data-act="cmt" data-key="'+esc(t.key)+'" title="Bình luận">'
      +'<span class="material-symbols-rounded mi-sm">chat_bubble_outline</span>'+cnt+'</button></td>'
      +'</tr>' + (openCmt[t.key] ? cmtRow(t.key) : '');
  }
  function cmtRow(key){
    var list=COMMENTS[key]||null;
    var hist;
    if(list===null) hist='<div class="cmt-empty">Đang tải bình luận…</div>';
    else if(!list.length) hist='<div class="cmt-empty">Chưa có bình luận nào</div>';
    else hist=list.map(function(c){ return '<div class="cmt-item"><span class="av '+avById(c.author)+'">'+esc(initOf(c.author))+'</span>'
      +'<div class="cmt-main"><div class="cmt-meta"><b>'+esc(c.author)+'</b><span>'+esc((c.when||'').slice(0,16).replace('T',' '))+'</span></div>'
      +'<div class="cmt-text">'+esc(c.body)+'</div></div></div>'; }).join('');
    return '<tr class="cmt-row"><td colspan="7"><div class="cmt-panel">'
      +'<div class="cmt-history">'+hist+'</div>'
      +'<div class="cmt-box"><textarea id="cmtTa-'+esc(key)+'" placeholder="Viết bình luận của bạn..."></textarea>'
      +'<div class="cmt-foot">'
      +'<button class="lbtn close" data-act="cmt-close" data-key="'+esc(key)+'"><span class="material-symbols-rounded mi-xs">expand_less</span>Đóng</button>'
      +'<button class="lbtn primary" data-act="cmt-send" data-key="'+esc(key)+'">Gửi</button>'
      +'</div></div></div></td></tr>';
  }
  function renderRows(){
    var all=visibleTasks();
    if(!all.length){ tbody.innerHTML='<tr><td colspan="7"><div class="empty">Không có task nào 🎉</div></td></tr>';
      $('pager').innerHTML=''; return; }
    var pages=Math.max(1, Math.ceil(all.length/PER_PAGE));
    if(curPage>pages) curPage=pages; if(curPage<1) curPage=1;
    var start=(curPage-1)*PER_PAGE, slice=all.slice(start, start+PER_PAGE);
    tbody.innerHTML=slice.map(rowHTML).join('');
    $('pager').innerHTML='<span class="pinfo">'+(start+1)+'–'+(start+slice.length)+' / '+all.length+' task · trang '+curPage+'/'+pages+'</span>'
      +'<button '+(curPage<=1?'disabled':'')+' data-pg="-1"><span class="material-symbols-rounded mi-sm">chevron_left</span>Trước</button>'
      +'<button '+(curPage>=pages?'disabled':'')+' data-pg="1">Sau<span class="material-symbols-rounded mi-sm">chevron_right</span></button>';

    if(curCaret && smenu && smenu.classList.contains('open')){
      var key=curCaret.getAttribute('data-key');
      var newCaret=document.querySelector('[data-act="smenu"][data-key="'+key+'"]');
      if(newCaret) curCaret=newCaret;
    }
  }
  function setFilter(f){ curFilter=f; curPage=1;
    document.querySelectorAll('#tabs button').forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-f')===f); });
    document.querySelectorAll('#kpis .kpi').forEach(function(k){ k.classList.toggle('sel', k.getAttribute('data-f')===f); });
    renderRows(); }

  // dueWeek flag (cho filter) — tính nhanh client từ dueCls? dueweek đã đếm server; ở đây
  // filter dueweek dùng cờ: task không overdue và dueCls!=overdue và due trong tuần.
  // Đơn giản: đánh dấu dueWeek nếu meta cần — ở đây bỏ filter dueweek trên bảng (KPI chỉ là số).

  // event delegation
  document.addEventListener('click', function(e){
    var pg=e.target.closest('[data-pg]'); if(pg && pg.closest('#pager')){ curPage+=parseInt(pg.getAttribute('data-pg'),10); renderRows(); return; }
    var rm=e.target.closest('.rm[data-val]'); if(rm){ rmCust(rm.getAttribute('data-key'), rm.getAttribute('data-val')); return; }
    var a=e.target.closest('[data-act]'); if(!a) return;
    var act=a.getAttribute('data-act'), key=a.getAttribute('data-key');
    if(act==='smenu'){ e.stopPropagation(); openStatusMenu(a); }
    else if(act==='detail'){ openDetail(key); }
    else if(act==='cmt'){ toggleCmt(key); }
    else if(act==='cmt-close'){ toggleCmt(key); }
    else if(act==='cmt-send'){ sendComment(key); }
  });
  document.querySelectorAll('#tabs button').forEach(function(b){ b.addEventListener('click', function(){ setFilter(b.getAttribute('data-f')); }); });
  document.querySelectorAll('#kpis .kpi').forEach(function(k){ k.addEventListener('click', function(){
    var f=k.getAttribute('data-f'); setFilter(f==='done'?'all':f); }); });
  var si=$('searchInp'); if(si) si.addEventListener('input', function(){ curPage=1; renderRows(); });

  // ----- comment panel -----
  function fetchComments(key){ return getJSON('/issue-comments?key='+encodeURIComponent(key), 20000)
    .then(function(j){ if(j&&j.ok&&j.detail){ COMMENTS[key]=j.detail.comments||[]; DETAIL[key]=j.detail;
        if(!taskByKey(key)) EXTRA[key]=synthTask(key, j.detail); }
      else COMMENTS[key]=COMMENTS[key]||[]; })
    .catch(function(){ COMMENTS[key]=COMMENTS[key]||[]; }); }
  function toggleCmt(key){
    if(openCmt[key]){ delete openCmt[key]; renderRows(); return; }
    openCmt[key]=true;
    if(COMMENTS[key]===undefined){ COMMENTS[key]=null; renderRows();
      fetchComments(key).then(function(){ if(openCmt[key]) renderRows(); }); }
    else renderRows();
    var ta=$('cmtTa-'+key); if(ta) ta.focus();
  }
  function sendComment(key){
    var ta=$('cmtTa-'+key); var v=(ta&&ta.value||'').trim();
    if(!v){ toast('Chưa nhập bình luận', false); return; }
    if(inflight['c'+key]) return; inflight['c'+key]=true; if(ta) ta.disabled=true;
    postJSON('/add-comment', { key:key, body:v }, 20000).then(function(j){
      inflight['c'+key]=false; if(ta) ta.disabled=false;
      if(patToast(j)) return;
      if(j.ok){ (COMMENTS[key]=COMMENTS[key]||[]).push({author:'Bạn', when:new Date().toISOString(), body:v});
        renderRows(); toast(key+': đã gửi comment ✓', true);
        var h=document.querySelector('.cmt-row .cmt-history'); if(h) h.scrollTop=h.scrollHeight; }
      else toast(j.msg||('Lỗi gửi comment '+key), false);
    }).catch(function(){ inflight['c'+key]=false; if(ta) ta.disabled=false; toast('Lỗi mạng khi gửi comment', false); });
  }

  // ----- detail drawer -----
  function openDetail(key){ var t=taskByKey(key);
    $('drawerOv').classList.add('open'); $('drawer').classList.add('open');
    if(t) renderDrawer(t);
    else $('drawer').innerHTML='<div class="drawer-body"><div class="cmt-empty">Đang tải…</div></div>';
    if(COMMENTS[key]===undefined){ COMMENTS[key]=null; fetchComments(key).then(function(){
      var tt=taskByKey(key);
      if(tt && $('drawer').classList.contains('open')) renderDrawer(tt); }); } }
  window.__openDetail = openDetail;
  function closeDetail(){ $('drawerOv').classList.remove('open'); $('drawer').classList.remove('open'); }
  function renderDrawer(t){
    var chips = (t.customs&&t.customs.length) ? t.customs.map(function(v){
      return '<span class="cust-chip"><span class="material-symbols-rounded">circle</span>'+esc(custMap[v]||v)+'</span>'; }).join('')
      : '<span style="color:var(--on-surface-variant)">—</span>';
    var flags=''; if(t.overdue) flags+='<span class="dt-flag od"><span class="material-symbols-rounded mi-xs">event_busy</span>Quá hạn</span>';
    if(t.stuck) flags+='<span class="dt-flag st"><span class="material-symbols-rounded mi-xs">hourglass_bottom</span>Kẹt</span>';
    if(!flags) flags='<span style="color:var(--on-surface-variant)">—</span>';
    var list=COMMENTS[t.key];
    var hist;
    if(list===null||list===undefined) hist='<div class="cmt-empty">Đang tải…</div>';
    else if(!list.length) hist='<div class="cmt-empty">Chưa có bình luận nào</div>';
    else hist=list.map(function(c){ return '<div class="cmt-item"><span class="av '+avById(c.author)+'">'+esc(initOf(c.author))+'</span>'
      +'<div class="cmt-main"><div class="cmt-meta"><b>'+esc(c.author)+'</b><span>'+esc((c.when||'').slice(0,16).replace('T',' '))+'</span></div>'
      +'<div class="cmt-text">'+esc(c.body)+'</div></div></div>'; }).join('');
    var desc=(DETAIL[t.key]&&DETAIL[t.key].description) ? esc(DETAIL[t.key].description) : esc(t.summary);
    $('drawer').innerHTML='<div class="drawer-head"><a class="key" href="'+esc(t.jiraUrl)+'" target="_blank">'+esc(t.key)+'</a>'
      +'<span class="badge '+jiraCls(t.jira)+'">'+esc(t.jira)+'</span>'
      +'<button class="x material-symbols-rounded" data-act="drawer-close">close</button></div>'
      +'<div class="drawer-body"><h2>'+esc(t.summary)+'</h2>'
      +'<div class="dt-grid"><div class="lbl">Người xử lý</div><div class="val"><span class="assignee"><span class="av '+esc(t.assignee.cls)+'">'+esc(t.assignee.init)+'</span> '+esc(t.assignee.name)+'</span></div>'
      +'<div class="lbl">Ngày tạo</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].created)?esc(DETAIL[t.key].created):esc(t.createdDisp||'—'))+'</div>'
      +'<div class="lbl">Hạn chót</div><div class="val"><span class="due '+esc(t.dueCls)+'">'+esc(t.dueDisp)+'</span></div>'
      +'<div class="lbl">Cập nhật</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].updated)?esc(DETAIL[t.key].updated):'—')+'</div>'
      +'<div class="lbl">Dev phụ trách</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].devs&&DETAIL[t.key].devs.length)?DETAIL[t.key].devs.map(esc).join(', '):'—')+'</div>'
      +'<div class="lbl">Nhãn nội bộ</div><div class="val">'+chips+'</div>'
      +'<div class="lbl">Cảnh báo</div><div class="val">'+flags+'</div></div>'
      +'<div class="dt-sec-title">Mô tả</div><div class="dt-desc">'+desc+'</div>'
      +bugSectionHtml(DETAIL[t.key])
      +testcaseSectionHtml(DETAIL[t.key])
      +'<div class="dt-cmts"><div class="dt-sec-title">Bình luận ('+(list&&list.length||0)+')</div>'
      +'<div class="cmt-panel"><div class="cmt-history">'+hist+'</div>'
      +'<div class="cmt-box"><textarea id="dtTa-'+esc(t.key)+'" placeholder="Viết bình luận..."></textarea>'
      +'<div class="cmt-foot"><button class="lbtn primary" data-act="dt-send" data-key="'+esc(t.key)+'">Gửi</button></div></div></div></div></div>';
  }
  document.addEventListener('click', function(e){
    var a=e.target.closest('[data-act]'); if(!a) return;
    if(a.getAttribute('data-act')==='drawer-close') closeDetail();
    else if(a.getAttribute('data-act')==='dt-send'){ var key=a.getAttribute('data-key');
      var ta=$('dtTa-'+key); var v=(ta&&ta.value||'').trim(); if(!v){ toast('Chưa nhập bình luận', false); return; }
      postJSON('/add-comment', { key:key, body:v }, 20000).then(function(j){ if(patToast(j)) return;
        if(j.ok){ (COMMENTS[key]=COMMENTS[key]||[]).push({author:'Bạn', when:new Date().toISOString(), body:v});
          renderDrawer(taskByKey(key)); renderRows(); toast('Đã gửi comment ✓', true); }
        else toast(j.msg||'Lỗi gửi comment', false); }).catch(function(){ toast('Lỗi mạng', false); }); }
  });
  var dov=$('drawerOv'); if(dov) dov.addEventListener('click', closeDetail);

  // ----- status menu (.smenu) -----
  var smenu=$('smenu'), curCaret=null, curJira=null;
  function closeSmenu(){ if(smenu){ smenu.classList.remove('open'); smenu.innerHTML=''; } curCaret=null; curJira=null; }
  function renderSmenu(t, jiraState){
    curJira=jiraState;
    var cur={}; (t.customs||[]).forEach(function(v){ cur[v]=1; });
    var h='<div class="smenu-grp">Status Jira</div>';
    if(jiraState===null) h+='<div class="smenu-note muted"><span class="material-symbols-rounded mi-sm">hourglass_empty</span>Đang tải status…</div>';
    else if(jiraState.code==='no_pat') h+='<div class="smenu-note" data-sm="nopat"><span class="material-symbols-rounded mi-sm">lock</span>Cần PAT để đổi status Jira — bấm để thêm</div>';
    else if(!jiraState.ok) h+='<div class="smenu-note muted"><span class="material-symbols-rounded mi-sm">error</span>'+esc(jiraState.msg||'Lỗi tải status')+'</div>';
    else if(!jiraState.transitions.length) h+='<div class="smenu-note muted"><span class="material-symbols-rounded mi-sm">info</span>Không có bước chuyển khả dụng</div>';
    else jiraState.transitions.forEach(function(tr){
      h+='<div class="smenu-opt" data-sm="jira" data-id="'+esc(tr.id)+'" data-to="'+esc(tr.to)+'">'
        +'<span class="dot" style="background:#0052cc"></span>'+esc(tr.to)+'<span class="chk material-symbols-rounded">check</span></div>'; });
    var allowed=t.canCustom;
    h+='<div class="smenu-grp brd">Nhãn nội bộ — chọn nhiều</div>';
    if(!allowed) h+='<div class="smenu-note muted"><span class="material-symbols-rounded mi-sm">info</span>Chỉ gắn khi <b>TO DO</b> / <b>In Progress</b></div>';
    (window.QA_CUSTOM_STATUSES||[]).forEach(function(p){
      var on=cur[p[0]]?' on':'';
      h+='<div class="smenu-opt'+on+(allowed?'':' disabled')+'"'+(allowed?' data-sm="cust" data-val="'+esc(p[0])+'"':'')+'>'
        +'<span class="dot" style="background:#6554c0"></span>'+esc(p[1])+'<span class="chk material-symbols-rounded">check</span></div>'; });
    h+='<div class="smenu-foot"><small>'+((t.customs||[]).length?(t.customs.length+' nhãn'):'Chưa gắn nhãn')+'</small>'
      +'<button type="button" data-sm="close">Xong</button></div>';
    smenu.innerHTML=h;
  }
  function positionSmenu(caret){
    smenu.classList.add('open'); smenu.style.maxHeight='none';
    var r=caret.getBoundingClientRect(), gap=6, pad=8;
    var below=window.innerHeight-r.bottom-gap-pad, above=r.top-gap-pad;
    var avail=Math.max(below,above); smenu.style.maxHeight=avail+'px';
    var mh=Math.min(smenu.offsetHeight, avail);
    var top=(below>=above)?r.bottom+gap:r.top-gap-mh;
    smenu.style.top=Math.max(pad, top)+'px';
    smenu.style.left=Math.min(r.left, window.innerWidth-292)+'px';
  }
  window.openStatusMenu=function(caret){
    var key=caret.getAttribute('data-key');
    if(curCaret && curCaret.getAttribute('data-key') === key && smenu.classList.contains('open')){ closeSmenu(); return; }
    curCaret=caret; var t=taskByKey(key);
    renderSmenu(t, null); positionSmenu(caret);
    postJSON('/jira-transitions', { key:key }, 20000)
      .then(function(j){
        if(curCaret && curCaret.getAttribute('data-key') === key && smenu.classList.contains('open')){
          renderSmenu(t, j); positionSmenu(curCaret);
        }
      })
      .catch(function(){
        if(curCaret && curCaret.getAttribute('data-key') === key && smenu.classList.contains('open')){
          renderSmenu(t, { ok:false, msg:'Lỗi mạng khi tải status' }); positionSmenu(curCaret);
        }
      });
  };
  if(smenu) smenu.addEventListener('click', function(e){
    var o=e.target.closest('[data-sm]'); if(!o) return;
    var kind=o.getAttribute('data-sm'); if(!curCaret) return;
    var key=curCaret.getAttribute('data-key'), t=taskByKey(key);
    if(kind==='close'){ closeSmenu(); }
    else if(kind==='nopat'){ closeSmenu(); var ov=$('setOverlay'); if(ov) ov.classList.add('open'); }
    else if(kind==='jira'){ closeSmenu(); doTransition(key, o.getAttribute('data-id'), o.getAttribute('data-to')); }
    else if(kind==='cust'){ setCustom(t, key, o.getAttribute('data-val')); }
  });
  function doTransition(key, id, toName){
    if(inflight['t'+key]) return; inflight['t'+key]=true;
    toast(key+': đang đổi status…', true);
    postJSON('/do-transition', { key:key, id:id }, 20000).then(function(j){
      inflight['t'+key]=false; if(patToast(j)) return;
      if(j.ok){ var t=taskByKey(key); if(t){ t.jira=toName; if(!(toName==='TO DO'||toName==='In Progress')) t.customs=[]; } renderRows();
        toast(key+' → '+toName+' ✓', true); }
      else toast(j.msg||('Lỗi đổi status '+key), false);
    }).catch(function(){ inflight['t'+key]=false; toast('Lỗi mạng khi đổi status', false); });
  }
  function setCustom(t, key, val){
    var fk=key+'#'+val; if(inflight[fk]) return; inflight[fk]=true;
    postJSON('/set-custom-status', { key:key, status:val, summary:t.summary||'' }, 20000).then(function(j){
      inflight[fk]=false;
      if(!j.ok){ toast('Lỗi lưu nhãn '+key, false); return; }
      t.customs = Array.isArray(j.values) ? j.values : (t.customs||[]);
      renderRows();
      if(curCaret && smenu.classList.contains('open')){ renderSmenu(t, curJira); positionSmenu(curCaret); }
    }).catch(function(){ inflight[fk]=false; toast('Lỗi mạng khi lưu nhãn', false); });
  }
  function rmCust(key, val){ var t=taskByKey(key); if(t) setCustom(t, key, val); }
  document.addEventListener('click', function(e){
    if(smenu && smenu.classList.contains('open') && !e.target.closest('#smenu') && !e.target.closest('[data-act="smenu"]')) closeSmenu(); });
  window.addEventListener('scroll', function(e){
    if(!(smenu && smenu.classList.contains('open'))) return;
    if(e.target && e.target.nodeType===1 && (e.target===smenu || e.target.closest && e.target.closest('#smenu'))) return; // cuộn trong menu → giữ nguyên
    closeSmenu();
  }, true);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape'){ closeSmenu(); closeDetail(); } });

  // Vá real-time từ poll (Decision #24): cập nhật status Jira + nhãn nội bộ vào bảng/drawer,
  // KHÔNG reload. Chỉ render lại khi THỰC SỰ đổi (tránh flicker + nuốt comment đang gõ).
  window.__applyTaskPatch=function(map){
    var changed=false;
    TASKS.forEach(function(t){ var p=map[t.key]; if(!p) return;
      if(p.status && p.status!==t.jira){ t.jira=p.status; changed=true; }
      if(p.customs){ var a=(t.customs||[]).join(','), b=p.customs.join(',');
        if(a!==b){ t.customs=p.customs; changed=true; } }
    });
    if(!changed) return;
    renderRows();
    var dEl=$('drawer');
    if(dEl && dEl.classList.contains('open')){
      var ka=dEl.querySelector('.key'); var ok=ka&&ka.textContent;
      if(ok && map[ok]){ var tt=taskByKey(ok); if(tt) renderDrawer(tt); }
    }
  };

  setFilter('all');
})();

// ============== SHARED DRAWER (trang KHÔNG có bảng task: roadmap, docs) ==============
// Dashboard / Việc của tôi tự lo drawer trong closure #rows (có nhãn nội bộ + cờ Overdue/Kẹt).
// Module này chỉ kích hoạt khi trang có #drawer nhưng CHƯA có __openDetail -> bấm noti mở
// detail ngay tại chỗ (fetch từ /issue-comments), thay vì nhảy sang Jira.
(function(){
  var drawer=$('drawer'); if(!drawer) return;
  if(window.__openDetail) return;          // trang task đã có drawer "đầy đủ" riêng
  var ov=$('drawerOv');
  var COMMENTS={}, DETAIL={}, CUR={};       // key -> comments / detail / task obj
  var custMap={}; (window.QA_CUSTOM_STATUSES||[]).forEach(function(p){ custMap[p[0]]=p[1]; });
  function badgeCls(v){ v=(v||'').toUpperCase();
    if(v==='DONE') return 'b-done'; if(v==='CANCELLED') return 'b-critical';
    if(v==='IN PROGRESS') return 'b-checking'; if(v==='PENDING') return 'b-blocked';
    if(v==='TO DO') return 'b-todo'; return 'b-todo'; }
  function synth(key, d){
    return { key:key, summary:d.summary||key, jira:d.status||'',
      customs:[], canCustom:false,
      assignee:{ name:d.assignee||'—', init:initOf(d.assignee||'?'), cls:avById(d.assignee||'?') },
      due:d.duedate||'', dueDisp:d.duedate||'Chưa đặt hạn', dueCls:'',
      created:d.created||'', createdDisp:d.created||'—',
      overdue:false, stuck:false, isNew:false,
      jiraUrl:(window.__jiraBase||'')+'/browse/'+key };
  }
  function renderDrawer(t){
    var chips=(t.customs&&t.customs.length)?t.customs.map(function(v){
      return '<span class="cust-chip"><span class="material-symbols-rounded">circle</span>'+esc(custMap[v]||v)+'</span>';}).join('')
      :'<span style="color:var(--on-surface-variant)">—</span>';
    var flags='';
    if(t.overdue) flags+='<span class="dt-flag od"><span class="material-symbols-rounded mi-xs">event_busy</span>Quá hạn</span>';
    if(t.stuck) flags+='<span class="dt-flag st"><span class="material-symbols-rounded mi-xs">hourglass_bottom</span>Kẹt</span>';
    if(!flags) flags='<span style="color:var(--on-surface-variant)">—</span>';
    var list=COMMENTS[t.key], hist;
    if(list==null) hist='<div class="cmt-empty">Đang tải…</div>';
    else if(!list.length) hist='<div class="cmt-empty">Chưa có bình luận nào</div>';
    else hist=list.map(function(c){ return '<div class="cmt-item"><span class="av '+avById(c.author)+'">'+esc(initOf(c.author))+'</span>'
      +'<div class="cmt-main"><div class="cmt-meta"><b>'+esc(c.author)+'</b><span>'+esc((c.when||'').slice(0,16).replace('T',' '))+'</span></div>'
      +'<div class="cmt-text">'+esc(c.body)+'</div></div></div>'; }).join('');
    var desc=(DETAIL[t.key]&&DETAIL[t.key].description)?esc(DETAIL[t.key].description):esc(t.summary);
    drawer.innerHTML='<div class="drawer-head"><a class="key" href="'+esc(t.jiraUrl)+'" target="_blank">'+esc(t.key)+'</a>'
      +'<span class="badge '+badgeCls(t.jira)+'">'+esc(t.jira)+'</span>'
      +'<button class="x material-symbols-rounded" data-act="drawer-close">close</button></div>'
      +'<div class="drawer-body"><h2>'+esc(t.summary)+'</h2>'
      +'<div class="dt-grid"><div class="lbl">Người xử lý</div><div class="val"><span class="assignee"><span class="av '+esc(t.assignee.cls)+'">'+esc(t.assignee.init)+'</span> '+esc(t.assignee.name)+'</span></div>'
      +'<div class="lbl">Ngày tạo</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].created)?esc(DETAIL[t.key].created):esc(t.createdDisp||'—'))+'</div>'
      +'<div class="lbl">Hạn chót</div><div class="val"><span class="due '+esc(t.dueCls)+'">'+esc(t.dueDisp)+'</span></div>'
      +'<div class="lbl">Cập nhật</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].updated)?esc(DETAIL[t.key].updated):'—')+'</div>'
      +'<div class="lbl">Dev phụ trách</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].devs&&DETAIL[t.key].devs.length)?DETAIL[t.key].devs.map(esc).join(', '):'—')+'</div>'
      +'<div class="lbl">Nhãn nội bộ</div><div class="val">'+chips+'</div>'
      +'<div class="lbl">Cảnh báo</div><div class="val">'+flags+'</div></div>'
      +'<div class="dt-sec-title">Mô tả</div><div class="dt-desc">'+desc+'</div>'
      +bugSectionHtml(DETAIL[t.key])
      +testcaseSectionHtml(DETAIL[t.key])
      +'<div class="dt-cmts"><div class="dt-sec-title">Bình luận ('+(list&&list.length||0)+')</div>'
      +'<div class="cmt-panel"><div class="cmt-history">'+hist+'</div>'
      +'<div class="cmt-box"><textarea id="dtTa-'+esc(t.key)+'" placeholder="Viết bình luận..."></textarea>'
      +'<div class="cmt-foot"><button class="lbtn primary" data-act="dt-send" data-key="'+esc(t.key)+'">Gửi</button></div></div></div></div></div>';
  }
  function openDetail(key){
    ov.classList.add('open'); drawer.classList.add('open');
    if(CUR[key]) renderDrawer(CUR[key]);
    else drawer.innerHTML='<div class="drawer-body"><div class="cmt-empty">Đang tải…</div></div>';
    if(COMMENTS[key]===undefined){ COMMENTS[key]=null;
      getJSON('/issue-comments?key='+encodeURIComponent(key), 20000).then(function(j){
        if(j&&j.ok&&j.detail){ COMMENTS[key]=j.detail.comments||[]; DETAIL[key]=j.detail; CUR[key]=synth(key,j.detail); }
        else COMMENTS[key]=COMMENTS[key]||[];
        if(CUR[key] && drawer.classList.contains('open')) renderDrawer(CUR[key]);
      }).catch(function(){ COMMENTS[key]=COMMENTS[key]||[]; });
    }
  }
  window.__openDetail=openDetail;
  function closeDetail(){ ov.classList.remove('open'); drawer.classList.remove('open'); }
  if(ov) ov.addEventListener('click', closeDetail);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeDetail(); });
  document.addEventListener('click', function(e){
    var a=e.target.closest('[data-act]'); if(!a) return;
    var act=a.getAttribute('data-act');
    if(act==='drawer-close') closeDetail();
    else if(act==='dt-send'){ var key=a.getAttribute('data-key');
      var ta=$('dtTa-'+key), v=(ta&&ta.value||'').trim(); if(!v){ toast('Chưa nhập bình luận', false); return; }
      postJSON('/add-comment', { key:key, body:v }, 20000).then(function(j){ if(patToast(j)) return;
        if(j.ok){ (COMMENTS[key]=COMMENTS[key]||[]).push({author:'Bạn', when:new Date().toISOString(), body:v});
          if(CUR[key]) renderDrawer(CUR[key]); toast('Đã gửi comment ✓', true); }
        else toast(j.msg||'Lỗi gửi comment', false); }).catch(function(){ toast('Lỗi mạng', false); }); }
  });
})();

// ================= ROADMAP (guard #rmList2) =================
(function(){
  var box=$('rmList2'); if(!box) return;
  var PLANS = readJSON('rmData') || [];
  var META = readJSON('rmMeta') || { editable:false, statuses:[], people:[] };
  var HAS_PERM = !!META.editable;
  var EDIT = false;
  var STATUS_OPTS = META.statuses || [['planned','Planned'],['in_progress','In Progress'],['done','Done'],['blocked','Blocked']];
  var PEOPLE = META.people || [];
  var STLABEL={}; STATUS_OPTS.forEach(function(s){ STLABEL[s[0]]=s[1]; });
  var STCLS={done:'s-done', in_progress:'s-prog', planned:'s-plan', blocked:'s-block'};
  var curFilter='all', saveT=null;

  function uid(p){ return p+Date.now().toString(36)+Math.floor(Math.random()*1e4); }
  function planById(id){ return PLANS.filter(function(p){ return p.id===id; })[0]; }
  function taskById(p,tid){ return (p.tasks||[]).filter(function(t){ return t.id===tid; })[0]; }
  function subById(t,sid){ return (t.subs||[]).filter(function(s){ return s.id===sid; })[0]; }
  function leafById(s,lid){ return (s.leaves||[]).filter(function(l){ return l.id===lid; })[0]; }
  
  function subDone(s){ return (s.leaves&&s.leaves.length)?s.leaves.every(function(l){return l.done;}):!!s.done; }
  function subStarted(s){ return (s.leaves&&s.leaves.length)?s.leaves.some(function(l){return l.done;}):!!s.done; }
  function taskDone(t){ return (t.subs&&t.subs.length)?t.subs.every(subDone):!!t.done; }
  function taskStarted(t){ return (t.subs&&t.subs.length)?t.subs.some(function(s){return subStarted(s)||subDone(s);}):!!t.done; }

  function planStatus(p){ if(!p.tasks||!p.tasks.length) return p.status||'planned';
    if(p.tasks.every(taskDone)) return 'done';
    if(p.tasks.some(function(t){ return taskStarted(t)||taskDone(t); })) return 'in_progress'; return 'planned'; }
  function planFrac(p){ if(!p.tasks||!p.tasks.length) return null;
    var d=p.tasks.filter(taskDone).length; return {done:d, total:p.tasks.length, pct:Math.round(d/p.tasks.length*100)}; }
  function taskFrac(t){ if(!t.subs||!t.subs.length) return null;
    var d=t.subs.filter(subDone).length; return {done:d, total:t.subs.length, pct:Math.round(d/t.subs.length*100)}; }
  function subFrac(s){ if(!s.leaves||!s.leaves.length) return null;
    var d=s.leaves.filter(function(l){return l.done;}).length; return {done:d, total:s.leaves.length, pct:Math.round(d/s.leaves.length*100)}; }

  function dParts(due){ if(!due) return {m:'--', d:'--', disp:'Chưa đặt hạn', over:false};
    var dt=new Date(due+'T00:00:00'); if(isNaN(dt.getTime())) return {m:'--', d:'--', disp:esc(due), over:false};
    var dd=('0'+dt.getDate()).slice(-2), mm=('0'+(dt.getMonth()+1)).slice(-2);
    var today=new Date(); today.setHours(0,0,0,0);
    return {m:'Thg '+(dt.getMonth()+1), d:dd, disp:dd+'/'+mm+'/'+dt.getFullYear(), over: dt<today}; }

  function save(force){ if(!EDIT && !force) return; clearTimeout(saveT); var st=$('rmStatus');
    saveT=setTimeout(function(){
      postJSON('/save-roadmap', PLANS, 20000).then(function(j){
        toast(j.ok?'Đã lưu roadmap ✓':'Lỗi lưu roadmap', j.ok);
      }).catch(function(){ toast('Lỗi mạng khi lưu roadmap', false); });
    }, 600); }

  function visiblePlans(){
    var q=(($('searchInp')||{}).value||'').toLowerCase();
    return PLANS.slice().sort(function(a,b){ return (a.due||'9999')<(b.due||'9999')?-1:1; }).filter(function(p){
      var st=planStatus(p); var okF=curFilter==='all'||st===curFilter;
      var okQ=!q||((p.title||'')+' '+(p.desc||'')).toLowerCase().indexOf(q)>=0; return okF&&okQ; });
  }
  function render(){
    var list=visiblePlans();
    box.innerHTML = list.length ? list.map(planHTML).join('')
      : '<div class="rm-empty">Không có kế hoạch nào khớp 🎉</div>';
  }
  function planHTML(p){
    var st=planStatus(p), scls=STCLS[st]||'s-plan', dp=dParts(p.due), fr=planFrac(p);
    var caret=p.open?'keyboard_arrow_down':'keyboard_arrow_right';
    var sum = fr ? '<div class="rm-headsum"><span class="rm-pcount">'+fr.done+'/'+fr.total+' task</span>'
        +'<div class="rm-pbar"><i class="'+(fr.pct>=100?'full':'')+'" style="width:'+fr.pct+'%"></i></div></div>' : '';
    var acts = EDIT ? '<div class="rm-actions">'
        +'<button data-rm="edit-plan" data-p="'+esc(p.id)+'" title="Sửa"><span class="material-symbols-rounded mi-sm">edit</span></button>'
        +'<button class="del" data-rm="del-plan" data-p="'+esc(p.id)+'" title="Xoá"><span class="material-symbols-rounded mi-sm">delete</span></button></div>' : '';
    var over = (!plan_isDone(p) && dp.over) ? '<span class="od"><span class="material-symbols-rounded">warning</span>Quá hạn</span>' : '';
    return '<div class="rm-plan'+(p.open?' open':'')+'" data-id="'+esc(p.id)+'">'
      +'<div class="rm-plan-head" data-rm="toggle" data-p="'+esc(p.id)+'">'
        +'<div class="rm-date '+scls+'"><span class="m">'+esc(dp.m)+'</span><span class="d">'+esc(dp.d)+'</span></div>'
        +'<div class="rm-main"><div class="rm-titlerow"><span class="rm-caret material-symbols-rounded">'+caret+'</span>'
          +'<span class="rm-title">'+esc(p.title)+'</span><span class="rm-badge '+scls+'">'+esc(STLABEL[st]||st)+'</span></div>'
          +(p.desc?'<div class="rm-desc">'+esc(p.desc)+'</div>':'')
          +'<div class="rm-meta"><span><span class="material-symbols-rounded">person</span>'+esc(p.pic||'Chưa giao')+'</span>'
          +'<span><span class="material-symbols-rounded">event</span>'+esc(dp.disp)+'</span>'+over+'</div></div>'
        +'<div class="rm-headright">'+sum+acts+'</div>'
      +'</div>' + (p.open?bodyHTML(p):'') + '</div>';
  }
  function plan_isDone(p){ return planStatus(p)==='done'; }
  function bodyHTML(p){
    var tasks=(p.tasks||[]).map(function(t){ return taskHTML(p,t); }).join('');
    if(!tasks) tasks='<div class="rm-empty-task">Chưa có task nào.'+(EDIT?' Bấm "Thêm Task".':'')+'</div>';
    var add= EDIT?'<button class="rm-addbtn" data-rm="add-task" data-p="'+esc(p.id)+'"><span class="material-symbols-rounded mi-sm">add</span> Thêm Task</button>':'';
    return '<div class="rm-body"><div class="rm-body-head"><span class="ttl">Công việc trong kế hoạch</span>'+add+'</div>'
      +'<div class="rm-tasks">'+tasks+'</div></div>';
  }
  function taskHTML(p,t){
    var done=taskDone(t), partial=!done&&taskStarted(t);
    var ic=done?'check_box':(partial?'indeterminate_check_box':'check_box_outline_blank');
    var ccls=done?'on':(partial?'partial':'off');
    var fr=taskFrac(t), right='';
    if(fr) right+='<span class="rm-frac">'+fr.done+'/'+fr.total+' sub</span><div class="rm-tbar"><i class="'+(fr.pct>=100?'full':'')+'" style="width:'+fr.pct+'%"></i></div>';
    if(t.pic) right+='<span class="rm-av '+avById(t.pic)+'" title="'+esc(t.pic)+'">'+esc(initOf(t.pic))+'</span>';
    var mini= EDIT?'<div class="rm-tmini"><button data-rm="edit-task" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'"><span class="material-symbols-rounded mi-sm">edit</span></button>'
      +'<button class="del" data-rm="del-task" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'"><span class="material-symbols-rounded mi-sm">delete</span></button></div>':'';
    var subs=(t.subs&&t.subs.length)?t.subs.map(function(s){ return subHTML(p,t,s); }).join(''):'';
    var subadd= EDIT?'<button class="rm-subadd" data-rm="add-sub" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'"><span class="material-symbols-rounded mi-xs">add</span> Thêm Sub-task</button>':'';
    return '<div class="rm-task'+(done?' done':'')+'"><div class="rm-task-row">'
      +'<span class="rm-chk '+ccls+'" data-rm="toggle-task" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'"><span class="material-symbols-rounded">'+ic+'</span></span>'
      +'<span class="rm-task-name">'+esc(t.title)+'</span><div class="rm-task-right">'+right+mini+'</div></div>'
      +(t.desc?'<div class="rm-desc" style="font-size:13px; margin:4px 0 0 32px; color:var(--on-surface-variant)">'+esc(t.desc)+'</div>':'')
      +'<div class="rm-subs">'+subs+subadd+'</div></div>';
  }
  function leafHTML(p,t,s,l){
    var ic=l.done?'check_box':'check_box_outline_blank';
    var mini= EDIT?'<div class="rm-tmini"><button data-rm="edit-leaf" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'" data-s="'+esc(s.id)+'" data-l="'+esc(l.id)+'"><span class="material-symbols-rounded mi-xs">edit</span></button>'
      +'<button class="del" data-rm="del-leaf" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'" data-s="'+esc(s.id)+'" data-l="'+esc(l.id)+'"><span class="material-symbols-rounded mi-xs">close</span></button></div>':'';
    return '<div class="rm-leaf'+(l.done?' done':'')+'"><div class="rm-leaf-left">'
      +'<span class="rm-chk '+(l.done?'on':'off')+'" data-rm="toggle-leaf" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'" data-s="'+esc(s.id)+'" data-l="'+esc(l.id)+'"><span class="material-symbols-rounded mi-sm">'+ic+'</span></span>'
      +'<span class="rm-leaf-name">'+esc(l.title)+'</span></div>'+mini+'</div>'
      +(l.desc?'<div class="rm-desc" style="font-size:13px; margin:4px 0 0 32px; color:var(--on-surface-variant)">'+esc(l.desc)+'</div>':'');
  }

  function subHTML(p,t,s){
    var done=subDone(s), partial=!done&&subStarted(s);
    var ic=done?'check_box':(partial?'indeterminate_check_box':'check_box_outline_blank');
    var ccls=done?'on':(partial?'partial':'off');
    var fr=subFrac(s), right='';
    if(fr) right+='<span class="rm-frac" style="font-size:11px;color:var(--on-surface-variant);margin-right:8px;">'+fr.done+'/'+fr.total+' micro</span>';
    var mini= EDIT?'<div class="rm-tmini"><button data-rm="edit-sub" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'" data-s="'+esc(s.id)+'"><span class="material-symbols-rounded mi-xs">edit</span></button>'
      +'<button class="del" data-rm="del-sub" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'" data-s="'+esc(s.id)+'"><span class="material-symbols-rounded mi-xs">close</span></button></div>':'';
    var leaves=(s.leaves&&s.leaves.length)?s.leaves.map(function(l){ return leafHTML(p,t,s,l); }).join(''):'';
    var leafadd= EDIT?'<button class="rm-leafadd" data-rm="add-leaf" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'" data-s="'+esc(s.id)+'"><span class="material-symbols-rounded mi-xs">add</span> Thêm Micro-task</button>':'';
    return '<div class="rm-sub-wrap'+(done?' done':'')+'"><div class="rm-sub"><div class="rm-sub-left">'
      +'<span class="rm-chk '+ccls+'" data-rm="toggle-sub" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'" data-s="'+esc(s.id)+'"><span class="material-symbols-rounded mi-sm">'+ic+'</span></span>'
      +'<span class="rm-sub-name">'+esc(s.title)+'</span></div><div style="display:flex;align-items:center;">'+right+mini+'</div></div>'
      +(s.desc?'<div class="rm-desc" style="font-size:13px; margin:4px 0 0 32px; color:var(--on-surface-variant)">'+esc(s.desc)+'</div>':'')
      +'<div class="rm-leaves">'+leaves+leafadd+'</div></div>';
  }

  // ----- modal framework -----
  var modalState=null;
  function fieldHTML(f){ var inner;
    if(f.type==='textarea') inner='<textarea id="mf-'+f.key+'" placeholder="'+esc(f.placeholder||'')+'">'+esc(f.value||'')+'</textarea>';
    else if(f.type==='select') inner='<select id="mf-'+f.key+'">'+f.options.map(function(o){
      return '<option value="'+esc(o.value)+'"'+(String(o.value)===String(f.value)?' selected':'')+'>'+esc(o.label)+'</option>'; }).join('')+'</select>';
    else if(f.type==='date') inner='<input type="date" id="mf-'+f.key+'" value="'+esc(f.value||'')+'">';
    else inner='<input type="text" id="mf-'+f.key+'" value="'+esc(f.value||'')+'" placeholder="'+esc(f.placeholder||'')+'">';
    return '<div class="mfield"><label>'+esc(f.label)+'</label>'+inner+(f.hint?'<span class="hint">'+esc(f.hint)+'</span>':'')+'</div>';
  }
  function openModal(o){ modalState=o; $('modalIcon').textContent=o.icon||'edit'; $('modalTitle').textContent=o.title;
    $('modalSave').textContent=o.saveLabel||'Lưu'; $('modalBody').innerHTML=o.fields.map(fieldHTML).join('');
    $('modalOverlay').classList.add('open'); var fst=document.querySelector('#modalBody input,#modalBody textarea,#modalBody select'); if(fst) fst.focus(); }
  function closeModal(){ $('modalOverlay').classList.remove('open'); modalState=null; }
  function saveModal(){ if(!modalState) return; var vals={};
    modalState.fields.forEach(function(f){ var el=$('mf-'+f.key); vals[f.key]=el?(el.value||'').trim():''; });
    var err=modalState.onSave(vals); if(err){ toast(err, false); return; } closeModal(); }
  $('modalClose').addEventListener('click', closeModal); $('modalCancel').addEventListener('click', closeModal);
  $('modalSave').addEventListener('click', saveModal);
  $('modalOverlay').addEventListener('click', function(e){ if(e.target===$('modalOverlay')) closeModal(); });
  var peopleOpts = PEOPLE.map(function(n){ return {value:n, label:n}; });
  var statusOpts = STATUS_OPTS.map(function(s){ return {value:s[0], label:s[1]}; });

  // ----- CRUD -----
  function addPlan(){ openModal({ icon:'add_circle', title:'Thêm kế hoạch', saveLabel:'Tạo',
    fields:[ {key:'title',label:'Tên kế hoạch',type:'text',placeholder:'VD: Tự động hoá smoke test'},
      {key:'desc',label:'Mô tả',type:'textarea',placeholder:'Mục tiêu, phạm vi...'},
      {key:'due',label:'Hạn chót',type:'date'},
      {key:'pic',label:'Người phụ trách',type:'select',value:PEOPLE[0]||'',options:peopleOpts},
      {key:'status',label:'Trạng thái',type:'select',value:'planned',options:statusOpts} ],
    onSave:function(v){ if(!v.title) return 'Cần nhập tên kế hoạch';
      PLANS.push({id:uid('p'), title:v.title, desc:v.desc||'', due:v.due||'', pic:v.pic||'', status:v.status||'planned', open:true, tasks:[]});
      render(); save(); toast('Đã thêm kế hoạch', true); } }); }
  function editPlan(id){ var p=planById(id); if(!p) return; var has=p.tasks&&p.tasks.length;
    var fields=[ {key:'title',label:'Tên kế hoạch',type:'text',value:p.title},
      {key:'desc',label:'Mô tả',type:'textarea',value:p.desc},
      {key:'due',label:'Hạn chót',type:'date',value:p.due},
      {key:'pic',label:'Người phụ trách',type:'select',value:p.pic,options:peopleOpts},
      {key:'status',label:'Trạng thái',type:'select',value:has?planStatus(p):(p.status||'planned'),options:statusOpts,
        hint: has?'Tự suy theo task con — sửa task để đổi.':''} ];
    openModal({ icon:'edit', title:'Sửa kế hoạch', fields:fields, onSave:function(v){
      if(!v.title) return 'Cần nhập tên kế hoạch';
      p.title=v.title; p.desc=v.desc; p.due=v.due; p.pic=v.pic; if(!has) p.status=v.status;
      render(); save(); toast('Đã cập nhật', true); } }); }
  function delPlan(id){ var p=planById(id); if(!p) return;
    if(!confirm('Xoá kế hoạch "'+p.title+'"'+((p.tasks&&p.tasks.length)?' và toàn bộ task':'')+'?')) return;
    PLANS=PLANS.filter(function(x){ return x.id!==id; }); render(); save(); toast('Đã xoá', true); }
  function addTask(pid){ var p=planById(pid); if(!p) return;
    openModal({ icon:'add', title:'Thêm Task', saveLabel:'Tạo', fields:[
      {key:'title',label:'Tên task',type:'text',placeholder:'VD: Cập nhật Playwright'},
      {key:'desc',label:'Mô tả',type:'textarea',placeholder:'Note issue...'},
      {key:'pic',label:'Người xử lý',type:'select',value:PEOPLE[0]||'',options:peopleOpts} ],
      onSave:function(v){ if(!v.title) return 'Cần nhập tên task';
        p.tasks=p.tasks||[]; p.tasks.push({id:uid('t'), title:v.title, desc:v.desc||'', pic:v.pic||'', done:false, subs:[]});
        p.open=true; render(); save(); toast('Đã thêm task', true); } }); }
  function editTask(pid,tid){ var p=planById(pid), t=taskById(p,tid); if(!t) return;
    openModal({ icon:'edit', title:'Sửa Task', fields:[
      {key:'title',label:'Tên task',type:'text',value:t.title},
      {key:'desc',label:'Mô tả',type:'textarea',value:t.desc},
      {key:'pic',label:'Người xử lý',type:'select',value:t.pic,options:peopleOpts} ],
      onSave:function(v){ if(!v.title) return 'Cần nhập tên task';
        t.title=v.title; t.desc=v.desc; t.pic=v.pic; render(); save(); toast('Đã cập nhật', true); } }); }
  function delTask(pid,tid){ var p=planById(pid), t=taskById(p,tid); if(!t) return;
    if(!confirm('Xoá task "'+t.title+'"?')) return;
    p.tasks=p.tasks.filter(function(x){ return x.id!==tid; }); render(); save(); toast('Đã xoá', true); }
  function addSub(pid,tid){ var p=planById(pid), t=taskById(p,tid); if(!t) return;
    openModal({ icon:'add', title:'Thêm Sub-task', saveLabel:'Tạo', fields:[
      {key:'title',label:'Tên sub-task',type:'text',placeholder:'VD: Cập nhật config'},
      {key:'desc',label:'Mô tả',type:'textarea',placeholder:'Note issue...'} ],
      onSave:function(v){ if(!v.title) return 'Cần nhập tên sub-task';
        t.subs=t.subs||[]; t.subs.push({id:uid('s'), title:v.title, desc:v.desc||'', done:false}); render(); save(); toast('Đã thêm sub-task', true); } }); }
  function editSub(pid,tid,sid){ var p=planById(pid), t=taskById(p,tid), s=subById(t,sid); if(!s) return;
    openModal({ icon:'edit', title:'Sửa Sub-task', fields:[ {key:'title',label:'Tên sub-task',type:'text',value:s.title}, {key:'desc',label:'Mô tả',type:'textarea',value:s.desc} ],
      onSave:function(v){ if(!v.title) return 'Cần nhập tên sub-task'; s.title=v.title; s.desc=v.desc; render(); save(); toast('Đã cập nhật', true); } }); }
  function delSub(pid,tid,sid){ var p=planById(pid), t=taskById(p,tid);
    t.subs=t.subs.filter(function(x){ return x.id!==sid; }); render(); save(); toast('Đã xoá', true); }
  function addLeaf(pid,tid,sid){ var p=planById(pid), t=taskById(p,tid), s=subById(t,sid); if(!s) return;
    openModal({ icon:'add', title:'Thêm Micro-task', saveLabel:'Tạo', fields:[
      {key:'title',label:'Tên micro-task',type:'text',placeholder:'VD: Sửa hàm validate'},
      {key:'desc',label:'Mô tả',type:'textarea',placeholder:'Note issue...'} ],
      onSave:function(v){ if(!v.title) return 'Cần nhập tên micro-task';
        s.leaves=s.leaves||[]; s.leaves.push({id:uid('l'), title:v.title, desc:v.desc||'', done:false}); render(); save(); toast('Đã thêm micro-task', true); } }); }
  function editLeaf(pid,tid,sid,lid){ var p=planById(pid), t=taskById(p,tid), s=subById(t,sid), l=leafById(s,lid); if(!l) return;
    openModal({ icon:'edit', title:'Sửa Micro-task', fields:[ {key:'title',label:'Tên micro-task',type:'text',value:l.title}, {key:'desc',label:'Mô tả',type:'textarea',value:l.desc} ],
      onSave:function(v){ if(!v.title) return 'Cần nhập tên micro-task'; l.title=v.title; l.desc=v.desc; render(); save(); toast('Đã cập nhật', true); } }); }
  function delLeaf(pid,tid,sid,lid){ var p=planById(pid), t=taskById(p,tid), s=subById(t,sid);
    s.leaves=s.leaves.filter(function(x){ return x.id!==lid; }); render(); save(); toast('Đã xoá', true); }

  box.addEventListener('click', function(e){
    var el=e.target.closest('[data-rm]'); if(!el) return;
    var a=el.getAttribute('data-rm'), pid=el.getAttribute('data-p'), tid=el.getAttribute('data-t'), sid=el.getAttribute('data-s'), lid=el.getAttribute('data-l');
    if(a==='toggle'){ var p=planById(pid); if(p){ p.open=!p.open; render(); } return; }

    // Đánh dấu hoàn thành: chỉ cần quyền quản lý (HAS_PERM), kể cả đang ở View Mode
    if(HAS_PERM){
      if(a==='toggle-task'){ var p=planById(pid), t=taskById(p,tid); if(t){
        if(t.subs&&t.subs.length){ var all=taskDone(t); t.subs.forEach(function(s){
          if(s.leaves&&s.leaves.length) s.leaves.forEach(function(l){l.done=!all;});
          else s.done=!all;
        }); } else t.done=!t.done;
        p.status=planStatus(p); render(); save(true); } return; }
      else if(a==='toggle-sub'){ var p=planById(pid), t=taskById(p,tid), s=subById(t,sid); if(s){ 
        if(s.leaves&&s.leaves.length){ var all=subDone(s); s.leaves.forEach(function(l){l.done=!all;}); } else s.done=!s.done; 
        p.status=planStatus(p); render(); save(true); } return; }
      else if(a==='toggle-leaf'){ var p=planById(pid), t=taskById(p,tid), s=subById(t,sid), l=leafById(s,lid); if(l){ l.done=!l.done; p.status=planStatus(p); render(); save(true); } return; }
    }

    if(!EDIT) return;          // các thao tác còn lại cần bật chế độ chỉnh sửa
    e.stopPropagation();
    if(a==='edit-plan') editPlan(pid);
    else if(a==='del-plan') delPlan(pid);
    else if(a==='add-task') addTask(pid);
    else if(a==='edit-task') editTask(pid,tid);
    else if(a==='del-task') delTask(pid,tid);
    else if(a==='add-sub') addSub(pid,tid);
    else if(a==='edit-sub') editSub(pid,tid,sid);
    else if(a==='del-sub') delSub(pid,tid,sid);
    else if(a==='add-leaf') addLeaf(pid,tid,sid);
    else if(a==='edit-leaf') editLeaf(pid,tid,sid,lid);
    else if(a==='del-leaf') delLeaf(pid,tid,sid,lid);
  });
  document.querySelectorAll('#rmSeg button').forEach(function(b){ b.addEventListener('click', function(){
    curFilter=b.getAttribute('data-f'); document.querySelectorAll('#rmSeg button').forEach(function(x){ x.classList.toggle('active', x===b); }); render(); }); });
  var add=$('rmAddPlan'); if(add) add.addEventListener('click', addPlan);
  var tgl=$('rmToggleMode'); if(tgl) tgl.addEventListener('click', function(){
    if(!HAS_PERM) return;
    EDIT = !EDIT;
    if(EDIT){
      tgl.innerHTML = '<span class="material-symbols-rounded mi-sm">visibility</span> Tắt chỉnh sửa';
      tgl.classList.add('active');
      if(add) add.style.display = 'inline-flex';
    }else{
      tgl.innerHTML = '<span class="material-symbols-rounded mi-sm">edit</span> Bật chỉnh sửa';
      tgl.classList.remove('active');
      if(add) add.style.display = 'none';
    }
    render();
  });
  var si=$('searchInp'); if(si) si.addEventListener('input', render);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeModal(); });
  render();
})();

// ================= DOCUMENTS (guard #folderGrid) =================
(function(){
  var grid = $('folderGrid'); if(!grid) return;
  var EDIT = !!window.QA_DOCS_EDITABLE;
  var DOC_TREE = readJSON('docsData') || [];
  var currentPath = []; // Mảng lưu trữ đường dẫn thư mục hiện tại từ root
  var contextMenuSelectedId = null;

  // Normalise DOC_TREE nodes (ensure they have ids and map title to name for backward compatibility)
  function normaliseNodes(nodes) {
    if (!nodes) return;
    nodes.forEach(function(node) {
      if (!node.id) {
        node.id = (node.type === 'folder' ? 'f_' : 'd_') + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
      }
      if (node.type === 'link') {
        if (!node.name && node.title) {
          node.name = node.title;
        }
        // Migration: cũ lưu `date` = chuỗi tĩnh ("Vừa xong") đóng băng lúc tạo → luôn sai.
        // Giờ dùng `ts` (epoch ms) là nguồn thật; node cũ không có ts → hiển thị '--'.
        if (typeof node.ts !== 'number') {
          node.ts = null;
        }
      }
      if (node.type === 'folder') {
        if (!node.color) {
          node.color = 'blue';
        }
        if (node.children) {
          normaliseNodes(node.children);
        } else {
          node.children = [];
        }
      }
    });
  }
  normaliseNodes(DOC_TREE);

  // Helper functions
  function getCurrentNode() {
    if (currentPath.length === 0) {
      return { children: DOC_TREE };
    }
    return currentPath[currentPath.length - 1];
  }

  function getAllFilesRecursive(node) {
    var files = [];
    if (!node.children) return files;
    node.children.forEach(function(child) {
      if (child.type === 'link') {
        files.push(child);
      } else if (child.type === 'folder') {
        files = files.concat(getAllFilesRecursive(child));
      }
    });
    return files;
  }

  function getFolderCount(folderNode) {
    return getAllFilesRecursive(folderNode).length;
  }

  function findFolderById(list, id) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id && list[i].type === 'folder') return list[i];
      if (list[i].children) {
        var found = findFolderById(list[i].children, id);
        if (found) return found;
      }
    }
    return null;
  }

  function findFileById(list, id) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id && list[i].type === 'link') return list[i];
      if (list[i].children) {
        var found = findFileById(list[i].children, id);
        if (found) return found;
      }
    }
    return null;
  }

  function findFileParentAndIndex(list, id) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) {
        return { parentList: list, index: i };
      }
      if (list[i].children) {
        var found = findFileParentAndIndex(list[i].children, id);
        if (found) return found;
      }
    }
    return null;
  }

  function buildPathToFolder(list, id, path) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id && list[i].type === 'folder') {
        path.push(list[i]);
        return true;
      }
      if (list[i].children) {
        path.push(list[i]);
        var found = buildPathToFolder(list[i].children, id, path);
        if (found) return true;
        path.pop(); // backtrack
      }
    }
    return false;
  }

  // Navigation
  window.navigateToFolder = function(folderId) {
    var folder = findFolderById(DOC_TREE, folderId);
    if (!folder) return;
    currentPath = [];
    buildPathToFolder(DOC_TREE, folderId, currentPath);
    updateBreadcrumbs();
    renderFolders();
    renderTable();
  };

  window.navigateBackToRoot = function() {
    currentPath = [];
    updateBreadcrumbs();
    renderFolders();
    renderTable();
  };

  function updateBreadcrumbs() {
    var breadcrumbs = $('breadcrumbs');
    var tableTitle = $('tableTitle');
    var viewAllDocs = $('viewAllDocs');
    
    if (currentPath.length === 0) {
      breadcrumbs.style.display = 'none';
      tableTitle.textContent = 'Tài liệu gần đây';
      if (viewAllDocs) viewAllDocs.style.display = 'block';
    } else {
      breadcrumbs.style.display = 'flex';
      if (viewAllDocs) viewAllDocs.style.display = 'none';
      
      var html = '<a onclick="navigateBackToRoot()">Tài liệu QA</a>';
      for (var i = 0; i < currentPath.length; i++) {
        html += ' <span class="separator">/</span> ';
        if (i === currentPath.length - 1) {
          html += '<span class="current">' + esc(currentPath[i].name) + '</span>';
          tableTitle.textContent = 'Danh sách tài liệu - ' + currentPath[i].name;
        } else {
          var folderId = currentPath[i].id;
          html += '<a onclick="navigateToFolder(\'' + esc(folderId) + '\')">' + esc(currentPath[i].name) + '</a>';
        }
      }
      breadcrumbs.innerHTML = html;
    }
  }

  function renderFolders() {
    var currentNode = getCurrentNode();
    var subfolders = (currentNode.children || []).filter(function(n) { return n.type === 'folder'; });
    var section = $('foldersSection');
    
    section.style.display = 'block';
    
    if (subfolders.length === 0) {
      if (currentPath.length > 0) {
        grid.innerHTML = '';
        section.style.display = 'none';
      } else {
        grid.innerHTML = '<div style="grid-column:1/-1; padding:20px; text-align:center; color:var(--on-surface-variant); font-style:italic">Chưa có thư mục nào</div>';
      }
      return;
    }
    
    grid.innerHTML = subfolders.map(function(f) {
      var count = getFolderCount(f);
      return '<div class="folder-card" onclick="navigateToFolder(\'' + esc(f.id) + '\')">' +
        '<div class="folder-icon-box folder-' + esc(f.color || 'blue') + '">' +
          '<span class="material-symbols-rounded">folder</span>' +
        '</div>' +
        '<div class="folder-info">' +
          '<div class="folder-name">' + esc(f.name) + '</div>' +
          '<div class="folder-count">' + count + ' tài liệu</div>' +
        '</div>' +
      '</div>';
    }).join('');
  }

  function getFileIconClass(name, type, url) {
    var ext = name.split('.').pop().toLowerCase();
    
    if (url) {
      if (url.indexOf('/spreadsheets/') >= 0) return { icon: 'table_chart', cls: 'file-excel' };
      if (url.indexOf('/document/') >= 0) return { icon: 'description', cls: 'file-sop' };
      if (url.indexOf('/presentation/') >= 0) return { icon: 'slideshow', cls: 'file-excel' };
    }
    
    var baseName = name.replace(/\.url$/i, '');
    var checkExt = baseName !== name ? baseName.split('.').pop().toLowerCase() : ext;

    if (checkExt === 'xlsx' || checkExt === 'xls') return { icon: 'table_chart', cls: 'file-excel' };
    if (checkExt === 'pdf') return { icon: 'picture_as_pdf', cls: 'file-pdf' };
    if (checkExt === 'docx' || checkExt === 'doc') return { icon: 'description', cls: 'file-sop' };
    if (checkExt === 'pptx' || checkExt === 'ppt') return { icon: 'slideshow', cls: 'file-excel' };
    
    if (type === 'link' || ext === 'url') return { icon: 'link', cls: 'file-link' };
    return { icon: 'article', cls: 'file-sop' };
  }

  // Hiển thị ngày sửa từ ts (epoch ms): gần đây = tương đối, cũ = ngày tuyệt đối.
  function fmtDocDate(ts) {
    if (typeof ts !== 'number' || !ts) return '--';
    var diff = Date.now() - ts;
    if (diff < 0) diff = 0;
    var m = Math.floor(diff / 60000);
    if (m < 1) return 'Vừa xong';
    if (m < 60) return m + ' phút trước';
    var h = Math.floor(m / 60);
    if (h < 24) return h + ' giờ trước';
    var d = Math.floor(h / 24);
    if (d < 7) return d + ' ngày trước';
    var dt = new Date(ts);
    var p = function(n) { return (n < 10 ? '0' : '') + n; };
    return p(dt.getDate()) + '/' + p(dt.getMonth() + 1) + '/' + dt.getFullYear();
  }

  function renderTable() {
    var tbody = $('docTableBody');
    if (!tbody) return;
    var query = (($('searchInp') || {}).value || '').toLowerCase().trim();
    var currentNode = getCurrentNode();
    
    var files = [];
    if (currentPath.length === 0) {
      files = getAllFilesRecursive(currentNode);
    } else {
      files = (currentNode.children || []).filter(function(n) { return n.type === 'link'; });
    }
    
    var filtered = files.filter(function(d) {
      return !query || d.name.toLowerCase().indexOf(query) >= 0;
    });
    
    if (filtered.length === 0) {
      var cols = EDIT ? 3 : 2;
      tbody.innerHTML = '<tr><td colspan="' + cols + '"><div style="padding:40px; text-align:center; color:var(--on-surface-variant)">Chưa có tài liệu nào</div></td></tr>';
      return;
    }
    
    tbody.innerHTML = filtered.map(function(d) {
      var fileData = getFileIconClass(d.name, d.type, d.url);
      var actCol = EDIT ? '<td class="action-col" onclick="event.stopPropagation()">' +
          '<button class="action-btn material-symbols-rounded" onclick="openContextMenu(event, \'' + esc(d.id) + '\')">more_vert</button>' +
        '</td>' : '';
      return '<tr class="doc-row" data-url="' + esc(d.url) + '">' +
        '<td>' +
          '<div class="file-name-cell">' +
            '<span class="file-icon-wrapper ' + esc(fileData.cls) + '">' +
              '<span class="material-symbols-rounded">' + esc(fileData.icon) + '</span>' +
            '</span>' +
            '<span class="file-name">' + esc(d.name.replace(/\.url$/i, '')) + '</span>' +
          '</div>' +
        '</td>' +
        '<td class="date-modified">' + esc(fmtDocDate(d.ts)) + '</td>' +
        actCol +
      '</tr>';
    }).join('');
  }

  // Chỉ mở link an toàn (chặn javascript:/data: kể cả khi lọt qua validate server)
  function safeDocUrl(u){ return /^(https?:\/\/|\/uploads\/)/i.test(u||'') ? u : null; }

  // Mở link tài liệu qua delegated listener (KHÔNG inline onclick -> không chèn JS qua url)
  var docTbody = $('docTableBody');
  if (docTbody) {
    docTbody.addEventListener('click', function(e) {
      var row = e.target.closest('.doc-row');
      if (!row) return;
      var u = safeDocUrl(row.getAttribute('data-url'));
      if (u) window.open(u, '_blank');
    });
  }

  // Search input binding
  var si = $('searchInp');
  if (si) {
    si.placeholder = "Tìm tài liệu...";
    si.addEventListener('input', renderTable);
  }

  // Bottom Toast helper
  function showBottomToast(msg) {
    var bt = $('bottomToast');
    var bText = $('bottomToastText');
    if (!bt || !bText) return;
    bText.textContent = msg;
    bt.classList.add('show');
    setTimeout(function() {
      bt.classList.remove('show');
    }, 4000);
  }

  // Save docs configuration
  var saveT;
  function saveDocs() {
    if (!EDIT) return;
    clearTimeout(saveT);
    saveT = setTimeout(function() {
      postJSON('/save-docs', DOC_TREE, 20000).then(function(j) {
        toast(j.ok ? 'Đã lưu cấu trúc tài liệu ✓' : 'Lỗi lưu cấu trúc tài liệu', j.ok);
      }).catch(function() {
        toast('Lỗi kết nối khi lưu tài liệu', false);
      });
    }, 600);
  }

  // Context Menu handlers
  window.openContextMenu = function(event, id) {
    contextMenuSelectedId = id;
    var menu = $('contextMenu');
    if (!menu) return;
    menu.style.top = (event.clientY + window.scrollY) + 'px';
    menu.style.left = (event.clientX - 160 + window.scrollX) + 'px';
    menu.classList.add('open');
    event.stopPropagation();
  };

  function findParentFolderOfFile(list, id, currentParentId) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) return currentParentId || 'root';
      if (list[i].children) {
        var res = findParentFolderOfFile(list[i].children, id, list[i].id);
        if (res) return res;
      }
    }
    return null;
  }

  window.editDoc = function() {
    var doc = findFileById(DOC_TREE, contextMenuSelectedId);
    if (!doc) return;
    openModal('linkModal');
    
    var titleInp = $('linkTitleInp');
    var urlInp = $('linkUrlInp');
    if (titleInp && urlInp) {
      titleInp.value = doc.name.replace(/\.url$/i, '');
      urlInp.value = doc.url;
    }
    
    var folderSel = $('linkFolderSel');
    if (folderSel) {
      folderSel.disabled = false;
      var pid = findParentFolderOfFile(DOC_TREE, doc.id, null);
      if (pid) {
        folderSel.value = pid;
      }
    }

    var saveBtn = document.querySelector('#linkModal .modal-foot .btn-primary');
    if (saveBtn) {
      saveBtn.textContent = 'Cập nhật';
      saveBtn.setAttribute('onclick', 'updateDocInfo(\'' + esc(doc.id) + '\')');
    }
  };

  window.updateDocInfo = function(id) {
    var doc = findFileById(DOC_TREE, id);
    if (!doc) return;
    var titleInp = $('linkTitleInp');
    var urlInp = $('linkUrlInp');
    if (titleInp && urlInp) {
      var name = titleInp.value.trim();
      var url = urlInp.value.trim();
      if (!name || !url) {
        toast('Vui lòng điền đầy đủ thông tin', false);
        return;
      }
      doc.name = name;
      doc.url = url;
      doc.ts = Date.now();

      var folderSel = $('linkFolderSel');
      if (folderSel && !folderSel.disabled) {
        var newParentId = folderSel.value;
        var oldParentId = findParentFolderOfFile(DOC_TREE, id, null);
        if (newParentId && oldParentId && newParentId !== oldParentId) {
          var indexInfo = findFileParentAndIndex(DOC_TREE, id);
          if (indexInfo) {
            indexInfo.parentList.splice(indexInfo.index, 1);
          }
          if (newParentId === 'root') {
            DOC_TREE.unshift(doc);
          } else {
            var targetFolder = findFolderById(DOC_TREE, newParentId);
            if (targetFolder) {
              if (!targetFolder.children) targetFolder.children = [];
              targetFolder.children.unshift(doc);
            } else {
              DOC_TREE.unshift(doc);
            }
          }
        }
      }

      closeModal('linkModal');
      renderFolders();
      renderTable();
      saveDocs();
      showBottomToast('Cập nhật tài liệu thành công ✔');
    }
  };

  window.openLink = function() {
    var doc = findFileById(DOC_TREE, contextMenuSelectedId);
    var u = doc && safeDocUrl(doc.url);
    if (u) window.open(u, '_blank');
  };

  window.copyDocLink = function() {
    var doc = findFileById(DOC_TREE, contextMenuSelectedId);
    if (doc) {
      navigator.clipboard.writeText(doc.url).then(function() {
        toast('Đã sao chép link tài liệu vào Clipboard', true);
      });
    }
  };

  window.deleteDoc = function() {
    var indexInfo = findFileParentAndIndex(DOC_TREE, contextMenuSelectedId);
    if (indexInfo) {
      if (confirm('Bạn có chắc chắn muốn xoá tài liệu này?')) {
        var docName = indexInfo.parentList[indexInfo.index].name;
        indexInfo.parentList.splice(indexInfo.index, 1);
        renderFolders();
        renderTable();
        saveDocs();
        showBottomToast('Đã xoá tài liệu: ' + docName);
      }
    }
  };

  // Collect flat folders for selects
  function collectFoldersFlat(list, result) {
    list.forEach(function(node) {
      if (node.type === 'folder') {
        result.push(node);
        if (node.children) {
          collectFoldersFlat(node.children, result);
        }
      }
    });
  }

  function updateModalDropdowns() {
    var linkFolderSel = $('linkFolderSel');
    var uploadFolderSel = $('uploadFolderSel');
    var folderParentSel = $('folderParentSel');
    
    var allFolders = [];
    collectFoldersFlat(DOC_TREE, allFolders);
    
    var opts = allFolders.map(function(f) {
      return '<option value="' + esc(f.id) + '">' + esc(f.name) + '</option>';
    }).join('');
    
    var fullOpts = '<option value="root">Thư mục gốc (Root)</option>' + opts;

    if (linkFolderSel) linkFolderSel.innerHTML = fullOpts;
    if (uploadFolderSel) uploadFolderSel.innerHTML = fullOpts;
    if (folderParentSel) folderParentSel.innerHTML = fullOpts;
    
    if (currentPath.length > 0) {
      var currentFolderId = currentPath[currentPath.length - 1].id;
      if (linkFolderSel) { linkFolderSel.value = currentFolderId; linkFolderSel.disabled = true; }
      if (uploadFolderSel) { uploadFolderSel.value = currentFolderId; uploadFolderSel.disabled = true; }
      if (folderParentSel) { folderParentSel.value = currentFolderId; folderParentSel.disabled = true; }
    } else {
      if (linkFolderSel) { linkFolderSel.disabled = false; linkFolderSel.value = 'root'; }
      if (uploadFolderSel) { uploadFolderSel.disabled = false; uploadFolderSel.value = 'root'; }
      if (folderParentSel) { folderParentSel.disabled = false; folderParentSel.value = 'root'; }
    }
  }

  // Modals management
  window.openModal = function(id) {
    var m = $(id);
    if (!m) return;
    m.classList.add('open');
    
    if (id === 'folderModal') {
      var inp = $('folderNameInp');
      if (inp) inp.value = '';
      updateModalDropdowns();
    } else if (id === 'linkModal') {
      var titleInp = $('linkTitleInp');
      var urlInp = $('linkUrlInp');
      if (titleInp && urlInp) {
        titleInp.value = '';
        urlInp.value = '';
      }
      updateModalDropdowns();
      var saveBtn = document.querySelector('#linkModal .modal-foot .btn-primary');
      if (saveBtn) {
        saveBtn.textContent = 'Lưu tài liệu';
        saveBtn.setAttribute('onclick', 'addDriveLink()');
      }
    } else if (id === 'uploadModal') {
      var fileInput = $('fileInput');
      var progressWrap = $('progressWrap');
      var uploadForm = $('uploadForm');
      var uploadBtn = $('uploadBtn');
      var dropzone = $('dropzone');
      var foot = $('uploadModalFoot');
      
      if (fileInput) fileInput.value = '';
      if (progressWrap) progressWrap.style.display = 'none';
      if (uploadForm) uploadForm.style.display = 'none';
      if (uploadBtn) { uploadBtn.disabled = true; uploadBtn.textContent = 'Bắt đầu tải lên'; }
      if (dropzone) dropzone.style.display = 'block';
      if (foot) foot.style.display = 'flex';
      updateModalDropdowns();
    }
  };

  window.closeModal = function(id) {
    var m = $(id);
    if (m) m.classList.remove('open');
  };

  window.selectColor = function(el) {
    document.querySelectorAll('.color-opt').forEach(function(opt) {
      opt.classList.remove('selected');
    });
    el.classList.add('selected');
  };

  window.createFolder = function() {
    var inp = $('folderNameInp');
    if (!inp) return;
    var name = inp.value.trim();
    if (!name) {
      toast('Vui lòng nhập tên thư mục', false);
      return;
    }
    
    var selectedColorEl = document.querySelector('.color-opt.selected');
    var color = selectedColorEl ? selectedColorEl.getAttribute('data-color') : 'blue';
    
    var newFolder = {
      id: "f_" + Date.now(),
      type: "folder",
      name: name,
      color: color,
      children: []
    };
    
    var parentFolderSel = $('folderParentSel');
    var parentFolderId = parentFolderSel ? parentFolderSel.value : 'root';
    
    if (parentFolderId === 'root') {
      DOC_TREE.push(newFolder);
    } else {
      var parentFolder = findFolderById(DOC_TREE, parentFolderId);
      if (parentFolder) {
        if (!parentFolder.children) parentFolder.children = [];
        parentFolder.children.push(newFolder);
      } else {
        DOC_TREE.push(newFolder);
      }
    }
    
    closeModal('folderModal');
    renderFolders();
    saveDocs();
    showBottomToast('Tạo thư mục "' + name + '" thành công ✔');
  };

  window.addDriveLink = function() {
    var titleInp = $('linkTitleInp');
    var urlInp = $('linkUrlInp');
    if (!titleInp || !urlInp) return;
    
    var title = titleInp.value.trim();
    var url = urlInp.value.trim();
    
    if (!title || !url) {
      toast('Vui lòng nhập đầy đủ Tên tài liệu và Link Drive', false);
      return;
    }
    
    if (url.indexOf('http://') !== 0 && url.indexOf('https://') !== 0) {
      toast('Đường dẫn phải bắt đầu bằng http:// hoặc https://', false);
      return;
    }
    
    var newDoc = {
      id: "d_" + Date.now(),
      type: "link",
      name: title,
      ts: Date.now(),
      url: url
    };
    
    var folderSel = $('linkFolderSel');
    var targetFolderId = folderSel ? folderSel.value : '';
    var targetFolder = targetFolderId ? findFolderById(DOC_TREE, targetFolderId) : null;
    
    if (targetFolder) {
      if (!targetFolder.children) targetFolder.children = [];
      targetFolder.children.unshift(newDoc);
    } else {
      DOC_TREE.unshift(newDoc);
    }
    
    closeModal('linkModal');
    renderFolders();
    renderTable();
    saveDocs();
    showBottomToast('Thêm link tài liệu thành công ✔');
  };

  // Drag and Drop & Upload
  var selectFileObj = null;

  window.handleFileSelect = function(event) {
    if (event.target.files && event.target.files.length) {
      handleFiles(event.target.files[0]);
    }
    event.target.value = '';
  };

  function handleFiles(file) {
    selectFileObj = file;
    var dropzone = $('dropzone');
    var uploadForm = $('uploadForm');
    var btn = $('uploadBtn');
    
    if (dropzone) dropzone.style.display = 'none';
    if (uploadForm) uploadForm.style.display = 'block';
    
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Bắt đầu tải lên (' + (file.size / (1024 * 1024)).toFixed(2) + ' MB)';
    }
  }

  // Setup drag drop events on load for dropzone
  var dropzone = $('dropzone');
  if (dropzone) {
    dropzone.addEventListener('dragover', function(e) {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
    dropzone.addEventListener('dragleave', function() {
      dropzone.classList.remove('dragover');
    });
    dropzone.addEventListener('drop', function(e) {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer && e.dataTransfer.files.length) {
        handleFiles(e.dataTransfer.files[0]);
      }
    });
  }

  // Real Upload logic via XMLHttpRequest
  window.performRealUpload = function() {
    if (!selectFileObj) return;
    
    var progressWrap = $('progressWrap');
    var progressPercent = $('progressPercent');
    var uploadFileName = $('uploadFileName');
    var uploadPercentage = $('uploadPercentage');
    var uploadForm = $('uploadForm');
    var foot = $('uploadModalFoot');
    
    if (uploadForm) uploadForm.style.display = 'none';
    if (foot) foot.style.display = 'none';
    if (progressWrap) progressWrap.style.display = 'flex';
    if (uploadFileName) uploadFileName.textContent = selectFileObj.name;
    
    var fd = new FormData();
    fd.append('file', selectFileObj);
    
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload-file', true);
    
    xhr.upload.onprogress = function(e) {
      if (e.lengthComputable) {
        var pct = Math.round((e.loaded / e.total) * 100);
        if (progressPercent) progressPercent.style.width = pct + '%';
        if (uploadPercentage) uploadPercentage.textContent = pct + '%';
      }
    };
    
    xhr.onload = function() {
      if (xhr.status === 200) {
        try {
          var res = JSON.parse(xhr.responseText);
          if (res.ok) {
            var folderSel = $('uploadFolderSel');
            var targetFolderId = folderSel ? folderSel.value : '';
            var targetFolder = targetFolderId ? findFolderById(DOC_TREE, targetFolderId) : null;
            
            var newDoc = {
              id: "d_" + Date.now(),
              type: "link",
              name: res.filename,
              ts: Date.now(),
              url: res.url
            };
            
            if (targetFolder) {
              if (!targetFolder.children) targetFolder.children = [];
              targetFolder.children.unshift(newDoc);
            } else {
              DOC_TREE.unshift(newDoc);
            }
            
            closeModal('uploadModal');
            renderFolders();
            renderTable();
            saveDocs();
            showBottomToast('Đã tải lên tệp: ' + res.filename + ' ✔');
          } else {
            toast('Lỗi tải lên: ' + (res.msg || 'Không rõ nguyên nhân'), false);
            closeModal('uploadModal');
          }
        } catch(ex) {
          toast('Lỗi phân tích phản hồi từ máy chủ', false);
          closeModal('uploadModal');
        }
      } else if (xhr.status === 403) {
        toast('Lỗi 403: Bạn không có quyền thực hiện thao tác này', false);
        closeModal('uploadModal');
      } else {
        toast('Lỗi máy chủ: ' + xhr.status, false);
        closeModal('uploadModal');
      }
      selectFileObj = null;
    };
    
    xhr.onerror = function() {
      toast('Lỗi kết nối mạng trong quá trình tải lên', false);
      closeModal('uploadModal');
      selectFileObj = null;
    };
    
    xhr.send(fd);
  };

  // Close context menu on click outside
  document.addEventListener('click', function(e) {
    var menu = $('contextMenu');
    if (menu && !e.target.closest('.action-btn')) {
      menu.classList.remove('open');
    }
  });

  // Initial renders
  renderFolders();
  renderTable();
})();

// ---------- Tạo Sub-task (modal type-ahead, dùng chung mọi trang v2) ----------
(function(){
  var ov = $('subOverlay'); if(!ov) return;
  var openBtn = $('createSubBtn');
  var parent = { key:'', summary:'' };   // Task-PTSP đã chọn
  var leader = { name:'', display:'' };  // user đã chọn (optional)

  function open(){ ov.classList.add('open');
    // Auto-fill Leader mặc định = Hiền (hiennt19) nếu chưa chọn
    if(!leader.name){ leaderTA.set({name:'hiennt19', display:'Hiền'}); }
    var p=$('subParentInp'); if(p) setTimeout(function(){ p.focus(); }, 60); }
  function close(){ ov.classList.remove('open'); }
  function debounce(fn, ms){ var t; return function(){ var a=arguments, self=this;
    clearTimeout(t); t=setTimeout(function(){ fn.apply(self, a); }, ms||260); }; }

  // --- generic type-ahead: gắn input -> results, gọi search(url), chọn 1 mục ---
  function wireTA(inpId, resId, chipId, url, fmt, onPick){
    var inp=$(inpId), res=$(resId), chip=$(chipId), opts=[], active=-1;
    function place(){ var r=inp.getBoundingClientRect();   // toạ độ viewport cho position:fixed
      res.style.top=(r.bottom+4)+'px'; res.style.left=r.left+'px'; res.style.width=r.width+'px'; }
    function hide(){ res.classList.remove('open'); res.innerHTML=''; opts=[]; active=-1; }
    function show(){ place(); res.classList.add('open'); }
    function showChip(label){ chip.innerHTML = label +
        '<button type="button" class="ta-x material-symbols-rounded mi-sm" title="Bỏ chọn">close</button>';
      chip.style.display='flex'; inp.style.display='none';
      chip.querySelector('.ta-x').addEventListener('click', function(){
        chip.style.display='none'; chip.innerHTML=''; inp.style.display=''; inp.value=''; onPick(null); inp.focus(); });
    }
    var run = debounce(function(){
      var q=(inp.value||'').trim();
      if(q.length<2){ hide(); return; }
      getJSON(url+encodeURIComponent(q)).then(function(j){
        opts=(j&&j.results)||[]; active=-1;
        if(!opts.length){ res.innerHTML='<div class="ta-empty">Không tìm thấy</div>'; show(); return; }
        res.innerHTML = opts.map(function(o,i){ return '<div class="ta-opt" data-i="'+i+'">'+fmt(o)+'</div>'; }).join('');
        show();
      }).catch(function(){ hide(); });
    }, 260);
    inp.addEventListener('input', run);
    // dropdown position:fixed -> bám lại input khi cuộn/đổi kích thước (lúc đang mở)
    window.addEventListener('scroll', function(){ if(res.classList.contains('open')) place(); }, true);
    window.addEventListener('resize', function(){ if(res.classList.contains('open')) place(); });
    inp.addEventListener('keydown', function(e){
      if(!res.classList.contains('open')) return;
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){ e.preventDefault();
        active += (e.key==='ArrowDown'?1:-1);
        if(active<0) active=opts.length-1; if(active>=opts.length) active=0;
        res.querySelectorAll('.ta-opt').forEach(function(el,i){ el.classList.toggle('act', i===active); });
      } else if(e.key==='Enter'){ e.preventDefault(); if(active>=0) pick(active); }
      else if(e.key==='Escape'){ hide(); }
    });
    res.addEventListener('mousedown', function(e){ var el=e.target.closest('.ta-opt'); if(el) pick(+el.getAttribute('data-i')); });
    inp.addEventListener('blur', function(){ setTimeout(hide, 150); });  // click ra ngoài -> đóng (mousedown pick chạy trước)
    function pick(i){ var o=opts[i]; if(!o) return; onPick(o); showChip(fmt(o)); hide(); }
    return {
      reset:function(){ chip.style.display='none'; chip.innerHTML=''; inp.style.display=''; inp.value=''; hide(); },
      // set giá trị bằng tay (auto-fill): hiện chip + chạy onPick như vừa chọn
      set:function(o){ if(!o){ onPick(null); return; } onPick(o); showChip(fmt(o)); }
    };
  }

  var parentTA = wireTA('subParentInp','subParentRes','subParentChip','/search-parents?q=',
    function(o){ return '<b>'+esc(o.key)+'</b>'+esc(o.summary||''); },
    function(o){ parent = o ? {key:o.key, summary:o.summary||''} : {key:'',summary:''};
      // Auto-fill tiêu đề: [QA] <title Task-PTSP> (tránh nhân đôi [QA] nếu cha đã có)
      var s=$('subSummary');
      if(s){ var t=(parent.summary||'').trim();
        s.value = !parent.key ? '' : (/^\[QA\]/i.test(t) ? t : ('[QA] '+t)); } });
  var leaderTA = wireTA('subLeaderInp','subLeaderRes','subLeaderChip','/search-people?q=',
    function(o){ return '<b>'+esc(o.display||o.name)+'</b><small>'+esc(o.name)+'</small>'; },
    function(o){ leader = o ? {name:o.name, display:o.display||o.name} : {name:'',display:''}; });

  function reset(){
    parent={key:'',summary:''}; leader={name:'',display:''};
    parentTA.reset(); leaderTA.reset();
    var s=$('subSummary'); if(s) s.value='';
    var d=$('subDue'); if(d) d.value='';
    var a=$('subAssignee'); if(a) a.value='';
  }

  // Chưa có PAT -> không mở form tạo, mở thẳng modal Cài đặt PAT (create cần PAT cá nhân).
  if(openBtn) openBtn.addEventListener('click', function(){
    getJSON('/has-pat').then(function(j){
      if(j && j.ok && !j.hasPat){
        var so=$('setOverlay'); if(so) so.classList.add('open');
        toast('Bạn cần cấu hình PAT trước khi tạo sub-task', false);
      } else { open(); }
    }).catch(function(){ open(); });   // lỗi check -> vẫn mở form, backend tự chặn
  });
  var c1=$('subClose'), c2=$('subCancel');
  if(c1) c1.addEventListener('click', close);
  if(c2) c2.addEventListener('click', close);
  ov.addEventListener('click', function(e){ if(e.target===ov) close(); });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape' && ov.classList.contains('open')) close(); });

  var createBtn=$('subCreate');
  if(createBtn) createBtn.addEventListener('click', function(){
    var summary=($('subSummary').value||'').trim();
    var start=($('subStart').value||'').trim();
    var due=($('subDue').value||'').trim();
    var assignee=($('subAssignee').value||'').trim();
    if(!parent.key){ toast('Chưa chọn Task-PTSP cha', false); return; }
    if(!summary){ toast('Chưa nhập tiêu đề', false); return; }
    if(!start){ toast('Chưa chọn ngày bắt đầu', false); return; }
    if(!due){ toast('Chưa chọn hạn chót', false); return; }
    createBtn.disabled=true;
    postJSON('/create-subtask', { parent:parent.key, summary:summary, startDate:start,
        duedate:due, assignee:assignee, leader:leader.name })
      .then(function(j){
        createBtn.disabled=false;
        if(j && j.ok){ toast(j.msg||'Đã tạo sub-task ✓', true); reset(); close();
          setTimeout(function(){ location.reload(); }, 1100); }
        else if(!patToast(j)){ toast((j&&j.msg)||'Lỗi tạo sub-task', false); }
      })
      .catch(function(){ createBtn.disabled=false; toast('Lỗi mạng khi tạo sub-task', false); });
  });
})();

// ================= BUG LOG (guard #bugLogData) =================
(function(){
  var DATA = readJSON('bugLogData'); if(!DATA) return;
  var BUGS = DATA.bugs||[], MONTHS = DATA.months||[], EDIT = !!DATA.editable;
  var SOURCES = DATA.sources||[];    // [{id,label}] file Drive nguồn đã cấu hình
  var REOPEN = DATA.reopen||{};      // {bugKey:{count,dev,project,month,last}} reopen tích luỹ
  var base = window.__jiraBase || '';
  // activeFid = file Drive đang xem riêng ('' = tất cả). Nhớ qua localStorage, validate còn tồn tại.
  var activeFid = '';
  try{ activeFid = localStorage.getItem('qa-buglog-file')||''; }catch(e){}
  if(activeFid && !SOURCES.some(function(s){ return s.id===activeFid; })) activeFid='';
  var curMonth = MONTHS.length ? MONTHS[0] : '';
  var page = 1, PER = 15;
  var sel = {};            // bugKey -> true (test case đang tick)
  var taskSel = [];        // các task key đã chọn ở ô tìm (multi-select chip)
  var testerFilter = '';   // lọc bảng theo tester (qa_pic); '' = tất cả
  var devFilter = '';      // lọc bảng theo dev in charge (dev_pic); '' = tất cả
  var linkFilter = '';     // lọc theo trạng thái liên kết task: ''=tất cả, 'linked', 'unlinked'
  var tabs=$('blTabs'), rows=$('blRows'), pager=$('blPager'), cnt=$('blCount');

  var FULL_MONTH_YEARS = [];
  (function(){
    var years = {};
    years[new Date().getFullYear()] = true;
    BUGS.forEach(function(b){
      if(b.created) { var p = b.created.split('-'); if(p.length >= 1 && p[0]) years[parseInt(p[0], 10)] = true; }
    });
    Object.keys(years).sort().reverse().forEach(function(y) {
      if(y && !isNaN(y)) {
        for(var i=1; i<=12; i++) {
          var mm = i<10 ? '0'+i : ''+i;
          FULL_MONTH_YEARS.push(mm+'/'+y);
        }
      }
    });
  })();
  var curMetricMonth = (function(){
    var d = new Date(); var m = d.getMonth()+1;
    return (m<10?'0'+m:m)+'/'+d.getFullYear();
  })();

  function formatCreated(iso) {
    if(!iso) return '—';
    var p = iso.split('-');
    if(p.length >= 3) return p[2]+'/'+p[1]+'/'+p[0];
    return iso;
  }
  function getCreatedMonthYear(iso) {
    if(!iso) return '';
    var p = iso.split('-');
    if(p.length >= 2) return p[1]+'/'+p[0];
    return '';
  }

  // ----- map mức độ / trạng thái -> class + nhãn -----
  function sevCls(s){ var t=(s||'').toLowerCase();
    if(/nghi[êe]m|critical|blocker/.test(t)) return 'sev-crit';
    if(/cao|high|major/.test(t)) return 'sev-high';
    if(/th[ấa]p|low|minor|trivial/.test(t)) return 'sev-low';
    return 'sev-med'; }
  var ST = { 'New':['st-open','Mới'], 'Fixing':['st-fixing','Đang fix'],
    'Fixed':['st-fixed','Đã fix (chờ retest)'], 'Reopen':['st-reopen','Reopen'],
    'Rejected':['st-rejected','Bị từ chối'], 'Closed':['st-closed','Đã đóng'] };
  function stCell(s){ var m=ST[s]||['st-default', s||'—'];
    return '<span class="st-badge '+m[0]+'">'+esc(m[1])+'</span>'; }

  function taskCell(b){
    var tasks = b.tasks || [];
    if(tasks.length){
      // 1 bug có thể link nhiều task -> mỗi task 1 chip, × gỡ riêng task đó.
      // × để NGOÀI <a> (nếu nằm trong sẽ đi theo href + bị bắt nhầm).
      return '<span class="bl-jira-wrap">' + tasks.map(function(t){
        var unlink = EDIT ? '<span class="unlink material-symbols-rounded mi-xs" data-unlink="'+esc(b.key)+'" data-task="'+esc(t)+'" title="Gỡ liên kết">close</span>' : '';
        return '<span class="bl-jira-chip"><a class="bl-jira" href="'+esc(base)+'/browse/'+esc(t)+'" target="_blank" rel="noopener">🔗 '+esc(t)+'</a>'+unlink+'</span>';
      }).join('') + '</span>';
    }
    return '<span class="bl-nolink">⛓️‍💥 Chưa liên kết</span>';
  }

  // file đang xem: '' = tất cả, else chỉ bug có fid===activeFid
  function fileBugs(){ return activeFid ? BUGS.filter(function(b){ return b.fid===activeFid; }) : BUGS; }
  // tháng có mặt trong file đang xem (giữ thứ tự MONTHS)
  function availMonths(){ var fb=fileBugs(); return MONTHS.filter(function(m){ return fb.some(function(b){ return b.month===m; }); }); }
  function monthBugs(){ return fileBugs().filter(function(b){
    if(b.month!==curMonth) return false;
    if(testerFilter && (b.qa||'')!==testerFilter) return false;
    if(devFilter){
      if(devFilter==='__none__'){ if((b.dev||'').trim()) return false; }
      else if((b.dev||'')!==devFilter) return false;
    }
    if(linkFilter){
      var linked = (b.tasks||[]).length>0;
      if(linkFilter==='linked' && !linked) return false;
      if(linkFilter==='unlinked' && linked) return false;
    }
    return true; }); }
  // danh sách tester (qa_pic) phân biệt trong file đang xem -> đổ vào dropdown lọc
  function populateTesters(){
    var sel0=$('blTesterFilter'); if(!sel0) return;
    var seen={}, list=[];
    fileBugs().forEach(function(b){ var q=(b.qa||'').trim();
      if(q && !seen[q]){ seen[q]=true; list.push(q); } });
    list.sort(function(a,b){ return a.localeCompare(b); });
    if(testerFilter && list.indexOf(testerFilter)<0) testerFilter='';   // tester biến mất khi đổi file
    sel0.innerHTML='<option value="">Tất cả tester</option>'+list.map(function(q){
      return '<option value="'+esc(q)+'"'+(q===testerFilter?' selected':'')+'>'+esc(q)+'</option>'; }).join('');
    populateDevs();
  }
  // danh sách dev (dev_pic) phân biệt trong file đang xem -> đổ vào dropdown lọc
  function populateDevs(){
    var sel0=$('blDevFilter'); if(!sel0) return;
    var seen={}, list=[], hasNone=false;
    fileBugs().forEach(function(b){ var d=(b.dev||'').trim();
      if(d){ if(!seen[d]){ seen[d]=true; list.push(d); } } else hasNone=true; });
    list.sort(function(a,b){ return a.localeCompare(b); });
    // dev đang chọn biến mất khi đổi file -> reset (giữ '__none__' nếu file vẫn có bug chưa gán)
    if(devFilter && devFilter!=='__none__' && list.indexOf(devFilter)<0) devFilter='';
    if(devFilter==='__none__' && !hasNone) devFilter='';
    var noneOpt = hasNone ? '<option value="__none__"'+(devFilter==='__none__'?' selected':'')+'>(Chưa gán dev)</option>' : '';
    sel0.innerHTML='<option value="">Tất cả dev</option>'+noneOpt+list.map(function(d){
      return '<option value="'+esc(d)+'"'+(d===devFilter?' selected':'')+'>'+esc(d)+'</option>'; }).join('');
  }

  function activeLabel(){
    if(!activeFid) return '';
    var s=SOURCES.filter(function(x){ return x.id===activeFid; })[0];
    return s ? (s.label||s.name||'File Drive') : '';
  }
  function setActiveFid(fid){
    if(fid===activeFid){ return; }
    activeFid = fid;
    try{ if(fid) localStorage.setItem('qa-buglog-file', fid); else localStorage.removeItem('qa-buglog-file'); }catch(e){}
    var av=availMonths();
    if(av.indexOf(curMonth)<0) curMonth = av.length ? av[0] : '';
    page=1; renderTabs(); render(); updateActiveChip(); updateSrcLine();
    toast(activeFid ? ('Đang xem: '+activeLabel()) : 'Đang xem: tất cả file', true);
  }
  function updateActiveChip(){ var c=$('blActiveFile'); if(!c) return;
    if(activeFid){ c.textContent='📄 '+activeLabel(); c.style.display=''; }
    else c.style.display='none';
  }
  // Dòng tên file nguồn: chọn 1 file -> CHỈ hiện tên file đó; '' -> hiện tất cả (HTML gốc render server-side).
  var ORIG_SRC_LINE = null;
  function updateSrcLine(){ var el=$('blSrcLine'); if(!el) return;
    if(ORIG_SRC_LINE===null) ORIG_SRC_LINE = el.innerHTML;
    if(activeFid){
      var s=SOURCES.filter(function(x){ return x.id===activeFid; })[0];
      var nm = s ? (s.name||s.label||'File Drive') : 'File Drive';
      var n = BUGS.filter(function(b){ return b.fid===activeFid; }).length;
      el.innerHTML = '<b>'+esc(nm)+'</b> — '+n+' bản ghi';
    } else el.innerHTML = ORIG_SRC_LINE;
  }

  function renderTabs(){
    populateTesters();
    var av = availMonths();
    if(!av.length){ tabs.innerHTML='<span class="bl-count">Chưa có dữ liệu cho file này.</span>'; return; }
    if(av.indexOf(curMonth)<0) curMonth=av[0];
    tabs.innerHTML = av.map(function(m){
      var n = fileBugs().filter(function(b){return b.month===m;}).length;
      return '<button class="bl-tab'+(m===curMonth?' active':'')+'" data-m="'+esc(m)+'">'
        +'<span class="material-symbols-rounded">calendar_month</span> '+esc(m)+' ('+n+')</button>';
    }).join('');
  }

  function render(){
    var list = monthBugs();
    var total = list.length, pages = Math.max(1, Math.ceil(total/PER));
    if(page>pages) page=pages;
    var start=(page-1)*PER, slice=list.slice(start, start+PER);
    var chkHead = EDIT;
    var html = slice.map(function(b){
      var chk = EDIT ? '<td><input type="checkbox" class="bl-check bl-row-chk" data-k="'+esc(b.key)+'"'+(sel[b.key]?' checked':'')+'></td>' : '';
      return '<tr>'+chk
        +'<td><span class="bl-id">'+esc(b.id)+'</span></td>'
        +'<td>'+esc(b.module)+'</td>'
        +'<td><b>'+esc(b.summary)+'</b></td>'
        +'<td style="white-space:nowrap">'+esc(formatCreated(b.created))+'</td>'
        +'<td>'+stCell(b.status)+'</td>'
        +'<td>'+esc(b.qa||'—')+'</td>'
        +'<td>'+esc(b.dev||'—')+'</td>'
        +'<td>'+taskCell(b)+'</td></tr>';
    }).join('');
    if(!total){
      var cols = EDIT?9:8;
      html = '<tr><td colspan="'+cols+'" style="text-align:center;color:var(--on-surface-variant);padding:30px">Không có bug nào trong tháng này.</td></tr>';
    }
    rows.innerHTML = html;
    cnt.textContent = 'Hiển thị '+slice.length+' / '+total+' bản ghi';
    // pager
    if(pages>1){
      var ph='<span class="pager-summary">trang '+page+'/'+pages+'</span><div class="pager-nav">'
        +'<button class="pager-btn" '+(page<=1?'disabled':'')+' data-pg="'+(page-1)+'"><span class="material-symbols-rounded mi-xs">chevron_left</span></button>';
      for(var i=1;i<=pages;i++) ph+='<button class="pager-page'+(i===page?' active':'')+'" data-pg="'+i+'">'+i+'</button>';
      ph+='<button class="pager-btn" '+(page>=pages?'disabled':'')+' data-pg="'+(page+1)+'"><span class="material-symbols-rounded mi-xs">chevron_right</span></button></div>';
      pager.innerHTML=ph;
    } else pager.innerHTML='';
    syncCheckAll();
    updateLinkBtn();
  }

  function syncCheckAll(){ var all=$('blCheckAll'); if(!all) return;
    var list=monthBugs(); all.checked = list.length>0 && list.every(function(b){return sel[b.key];}); }
  function selCount(){ return Object.keys(sel).filter(function(k){return sel[k];}).length; }
  function updateLinkBtn(){ var btn=$('blLinkBtn'); if(!btn) return;
    var n=selCount(); $('blSelCount').textContent = n?('('+n+')'):'';
    // cần: có test case tick (n>0) VÀ có ít nhất 1 task đã chọn
    btn.disabled = !(n>0 && taskSel.length>0); }

  // ----- events: tabs -----
  tabs.addEventListener('click', function(e){ var t=e.target.closest('.bl-tab'); if(!t) return;
    curMonth=t.getAttribute('data-m'); page=1; renderTabs(); render(); });
  // ----- events: pager -----
  pager.addEventListener('click', function(e){ var b=e.target.closest('[data-pg]'); if(!b||b.disabled) return;
    page=parseInt(b.getAttribute('data-pg'),10)||1; render(); });
  // ----- events: lọc theo tester -----
  (function(){ var tf=$('blTesterFilter'); if(!tf) return;
    tf.addEventListener('change', function(){ testerFilter=tf.value||''; page=1; render(); }); })();
  // ----- events: lọc theo dev in charge -----
  (function(){ var df=$('blDevFilter'); if(!df) return;
    df.addEventListener('change', function(){ devFilter=df.value||''; page=1; render(); }); })();
  // ----- events: lọc theo trạng thái liên kết task -----
  (function(){ var lf=$('blLinkFilter'); if(!lf) return;
    lf.addEventListener('change', function(){ linkFilter=lf.value||''; page=1; render(); }); })();
  // ----- events: tick + unlink (delegate trên tbody) -----
  rows.addEventListener('click', function(e){
    var u=e.target.closest('[data-unlink]');
    if(u){ e.preventDefault(); doLink([u.getAttribute('data-unlink')], u.getAttribute('data-task')||'', 'remove'); return; }
    var c=e.target.closest('.bl-row-chk');
    if(c){ var k=c.getAttribute('data-k'); if(c.checked) sel[k]=true; else delete sel[k]; syncCheckAll(); updateLinkBtn(); }
  });

  // ----- quản lý link Drive nguồn (admin): ✎ đổi link 1 file + modal CRUD list -----
  function driveLink(id){ return id ? ('https://drive.google.com/file/d/'+id+'/view') : ''; }
  function saveSources(list, btn){
    // list = [{link, label}]; server rút file id + scan ngay. Lưu xong reload để thấy data.
    if(btn) btn.disabled=true;
    toast('Đang lưu & đồng bộ từ Drive…', true);
    postJSON('/save-bug-log-sources', { sources:list }, 90000).then(function(j){
      if(btn) btn.disabled=false;
      if(j && j.ok){ toast('Đã lưu & đồng bộ ✓ — đang tải lại', true); setTimeout(function(){ location.reload(); }, 900); }
      else toast((j&&(j.err||(j.errors&&j.errors[0])))||'Lưu/đồng bộ lỗi', false);
    }).catch(function(){ if(btn) btn.disabled=false; toast('Lỗi mạng khi lưu', false); });
  }

  // "Đồng bộ ngay" — F5 chỉ render cache; nút này gọi scan() Drive ngay rồi reload (admin).
  // Khi đang sync: disable + đổi nhãn (spinner) để KHÔNG bấm nhiều lần. Dùng chung cho cả
  // auto-sync hết giờ (runBugSync) -> 1 đường đi duy nhất.
  // Nút GIỮ disabled suốt quá trình sync; chỉ "active" lại khi sync thành công -> reload
  // (trang load lại = nút mới tinh, enabled). Lỗi -> đổi nhãn báo lỗi + gợi ý F5 retry,
  // KHÔNG tự enable lại (tránh bấm dồn khi Drive đang chậm/timeout).
  function runBugSync(b){
    if(!b || b.disabled) return Promise.resolve(false);
    b.disabled=true;
    b.innerHTML='<span class="material-symbols-rounded mi-sm" style="animation:spin 1s linear infinite">progress_activity</span> Đang đồng bộ…';
    toast('Đang đọc lại data từ Drive…', true);
    return postJSON('/sync-bug-log', {}, 90000).then(function(j){
      if(j && j.ok){
        var changes=(j&&j.changes)||[];
        if(changes.length){ showBugChanges(changes, j.changed||changes.length); return true; }
        toast('Đã đồng bộ ✓ — không có thay đổi, đang tải lại', true);
        setTimeout(function(){ location.reload(); }, 900); return true;
      }
      b.innerHTML='<span class="material-symbols-rounded mi-sm">error</span> Đồng bộ lỗi — F5 để thử lại';
      toast((j&&(j.errors&&j.errors[0]))||'Đồng bộ lỗi', false); return false;
    }).catch(function(){
      b.innerHTML='<span class="material-symbols-rounded mi-sm">error</span> Đồng bộ lỗi — F5 để thử lại';
      toast('Lỗi mạng khi đồng bộ', false); return false;
    });
  }
  (function(){
    var b=$('blSyncBtn'); if(!b) return;
    b.addEventListener('click', function(){ runBugSync(b); });
  })();

  // Popup tổng kết thay đổi sau đồng bộ: nêu rõ file / sheet / nội dung đổi. Gom theo
  // (file, sheet) cho dễ đọc; bấm "Đóng & tải lại" mới reload (để user kịp đọc).
  function showBugChanges(changes, total){
    var ov=$('blChgOv'); if(!ov){ setTimeout(function(){ location.reload(); }, 900); return; }
    var ICON={ 'new':'add_circle', 'status':'sync_alt', 'del':'cancel' };
    var groups={}, order=[];
    changes.forEach(function(c){
      var f=c.file||'(không rõ file)', s=c.sheet||'(không rõ sheet)';
      var gk=f+' '+s;
      if(!groups[gk]){ groups[gk]={file:f, sheet:s, items:[]}; order.push(gk); }
      groups[gk].items.push(c);
    });
    var html='';
    order.forEach(function(gk){
      var g=groups[gk];
      html+='<div class="bl-chg-grp"><div class="bl-chg-grp-h">'
        +'<span class="material-symbols-rounded mi-sm">description</span> '+esc(g.file)
        +' <span class="bl-chg-sheet">› '+esc(g.sheet)+'</span></div>';
      g.items.forEach(function(c){
        var desc=c.desc||'', summ=c.summary?(' — '+c.summary):'', who=c.author?(' · '+c.author):'';
        html+='<div class="bl-chg-item bl-chg-'+esc(c.kind||'')+'">'
          +'<span class="material-symbols-rounded mi-sm">'+(ICON[c.kind]||'edit')+'</span>'
          +'<span class="bl-chg-txt">'+esc(desc)+esc(summ)+'<span class="bl-chg-who">'+esc(who)+'</span></span></div>';
      });
      html+='</div>';
    });
    var lst=$('blChgList'); if(lst) lst.innerHTML=html;
    var sm=$('blChgSummary');
    if(sm) sm.textContent='Đồng bộ xong: '+(total||changes.length)+' thay đổi'
      +(changes.length<(total||0)?(' (hiện '+changes.length+' dòng đầu)'):'')+'.';
    ov.classList.add('open');
  }
  // ackWatermark != null => popup đang hiện là "thay đổi tích luỹ" (admin chưa xem): khi đóng
  // phải BÁO server đã xem (đẩy watermark) RỒI mới reload, để reload không popup lại y hệt.
  // null => popup đồng bộ tay (server đã đánh dấu đã xem trong /sync-bug-log) -> reload thẳng.
  var ackWatermark = null;
  (function(){
    var ov=$('blChgOv'); if(!ov) return;
    function close(){
      if(ackWatermark !== null){
        var wm = ackWatermark; ackWatermark = null;
        postJSON('/seen-bug-log-changes', { watermark: wm }, 10000)
          .then(function(){ location.reload(); })
          .catch(function(){ location.reload(); });   // soft-fail: chưa đẩy được -> lần sau popup lại
        return;
      }
      location.reload();
    }
    var ok=$('blChgOk'), cl=$('blChgClose');
    if(ok) ok.addEventListener('click', close);
    if(cl) cl.addEventListener('click', close);
    ov.addEventListener('click', function(e){ if(e.target===ov) close(); });
  })();

  // Popup thay đổi TÍCH LUỸ từ các lần đồng bộ nền (admin chưa xem) — nêu mọi thay đổi
  // bug-log dồn lại từ lần admin vào màn này gần nhất. Hiện ngay khi vào màn; đóng = báo đã
  // xem + reload. Không vào màn -> giữ nguyên, không update nào bị tắt ngầm.
  (function(){
    var pending = DATA.pendingChanges || [];
    if(!pending.length) return;
    ackWatermark = DATA.pendingWatermark || '';
    showBugChanges(pending, DATA.pendingTotal || pending.length);
  })();

  // Đếm ngược "lần đồng bộ tự động kế tiếp" — next = synced_at + interval. Hết giờ thì
  // TỰ chạy sync (scan Drive) + reload để thấy data mới, thay vì chỉ đứng yên "sắp tới…".
  (function(){
    var el=$('blNextSync'); if(!el) return;
    var iso=el.getAttribute('data-synced')||'';
    var interval=parseInt(el.getAttribute('data-interval')||'0',10)||0;
    var mins=Math.max(1, Math.round(interval/60));
    var t0=iso?Date.parse(iso):NaN;
    if(!interval || isNaN(t0)) return;
    var fired=false;
    // Chống loop F5: nếu trang vừa load lại mà synced_at VẪN trùng mốc lần auto-sync trước
    // (scan chưa nhích vì lỗi/không phải admin) thì thôi tự đồng bộ — đợi F5 tay.
    var allow = (sessionStorage.getItem('bl-autosync-iso') !== iso);
    function tick(){
      var left=Math.round((t0+interval*1000-Date.now())/1000);
      var tail;
      if(left<=0){
        tail='lần tới: đang đồng bộ…';
        if(allow && !fired && !document.hidden){   // tab ẩn -> đợi quay lại mới chạy
          fired=true;
          sessionStorage.setItem('bl-autosync-iso', iso);
          var b=$('blSyncBtn');
          if(b) runBugSync(b);                      // admin: scan + reload (có nhãn spinner)
          else setTimeout(function(){ location.reload(); }, 800); // non-admin: reload đọc cache scheduler
        }
      } else {
        var m=Math.floor(left/60), s=left%60;
        tail='lần tới sau <span style="font-variant-numeric:tabular-nums;font-family:\'JetBrains Mono\',monospace;font-weight:500">'+(m<10?'0'+m:m)+':'+(s<10?'0'+s:s)+'</span>';
      }
      el.innerHTML='<span class="material-symbols-rounded mi-sm">autorenew</span> Tự đồng bộ lại toàn bộ file mỗi '+mins+' phút · '+tail;
    }
    tick(); setInterval(tick, 1000);
  })();

  // ✎ trên thẻ nguồn = PICKER: chọn 1 file Drive đã thêm để xem riêng data của file đó.
  // activeFid lưu localStorage (sống qua reload). '' = xem tất cả.
  (function(){
    var ov=$('blEditOv'), listEl=$('blPickList'); if(!ov) return;
    function rowHtml(fid, label, sub){
      var on = (activeFid===fid);
      return '<button type="button" class="bl-pick-row'+(on?' on':'')+'" data-fid="'+esc(fid)+'">'
        +'<span class="material-symbols-rounded bl-pick-ic">'+(fid?'description':'apps')+'</span>'
        +'<span class="bl-pick-meta"><span class="bl-pick-name">'+esc(label)+'</span>'
        +(sub?'<span class="bl-pick-sub">'+esc(sub)+'</span>':'')+'</span>'
        +'<span class="material-symbols-rounded bl-pick-chk">'+(on?'check_circle':'radio_button_unchecked')+'</span>'
        +'</button>';
    }
    function renderPick(){
      if(!SOURCES.length){ listEl.innerHTML='<div class="bl-src-empty">Chưa có file nào — thêm ở “Quản lý link drive”.</div>'; return; }
      var html = rowHtml('', 'Tất cả file', BUGS.length+' bản ghi');
      html += SOURCES.map(function(s){
        var n = BUGS.filter(function(b){ return b.fid===s.id; }).length;
        var name = s.label || s.name || 'File Drive';
        if (s.service) name += ' (' + s.service + ')';
        return rowHtml(s.id, name, n+' bản ghi');
      }).join('');
      listEl.innerHTML = html;
    }
    function open(){ renderPick(); ov.classList.add('open'); }
    function close(){ ov.classList.remove('open'); }
    listEl.addEventListener('click', function(e){
      var r=e.target.closest('.bl-pick-row'); if(!r) return;
      setActiveFid(r.getAttribute('data-fid')||'');
      close();
    });
    var b=$('blEditLinkBtn'); if(b) b.addEventListener('click', open);
    var c=$('blEditClose'); if(c) c.addEventListener('click', close);
    var cc=$('blEditCancel'); if(cc) cc.addEventListener('click', close);
    ov.addEventListener('click', function(e){ if(e.target===ov) close(); });
  })();

  // "Quản lý link drive" — modal CRUD list link
  (function(){
    var ov=$('blSrcOv'), listEl=$('blSrcList'); if(!ov) return;
    function rowHtml(label, link, service){
      return '<div class="bl-src-row">'
        +'<input type="text" class="bl-src-label" placeholder="Nhãn (tuỳ chọn)" value="'+esc(label||'')+'" style="width:140px;">'
        +'<input type="text" class="bl-src-service" placeholder="Hậu tố (VD: FE)" value="'+esc(service||'')+'" style="width:110px;">'
        +'<input type="text" class="bl-src-link" placeholder="Link Google Drive" value="'+esc(link||'')+'">'
        +'<button type="button" class="del material-symbols-rounded mi-sm" title="Xoá">delete</button></div>';
    }
    function renderList(){
      if(!SOURCES.length){ listEl.innerHTML='<div class="bl-src-empty">Chưa có link nào — bấm “Thêm link”.</div>'; return; }
      listEl.innerHTML = SOURCES.map(function(s){ return rowHtml(s.label, driveLink(s.id), s.service); }).join('');
    }
    function open(){ renderList(); ov.classList.add('open'); }
    function close(){ ov.classList.remove('open'); }
    var b=$('blManageBtn'); if(b) b.addEventListener('click', open);
    var c=$('blSrcClose'); if(c) c.addEventListener('click', close);
    var cc=$('blSrcCancel'); if(cc) cc.addEventListener('click', close);
    ov.addEventListener('click', function(e){ if(e.target===ov) close(); });
    var add=$('blSrcAdd'); if(add) add.addEventListener('click', function(){
      var empty=listEl.querySelector('.bl-src-empty'); if(empty) listEl.innerHTML='';
      listEl.insertAdjacentHTML('beforeend', rowHtml('', '', '')); });
    listEl.addEventListener('click', function(e){ var d=e.target.closest('.del'); if(!d) return;
      var row=d.closest('.bl-src-row'); if(row) row.remove();
      if(!listEl.querySelector('.bl-src-row')) listEl.innerHTML='<div class="bl-src-empty">Chưa có link nào — bấm “Thêm link”.</div>'; });
    var sv=$('blSrcSave'); if(sv) sv.addEventListener('click', function(){
      var list=[];
      listEl.querySelectorAll('.bl-src-row').forEach(function(row){
        var link=(row.querySelector('.bl-src-link').value||'').trim();
        var label=(row.querySelector('.bl-src-label').value||'').trim();
        var service=(row.querySelector('.bl-src-service').value||'').trim();
        if(link) list.push({ link:link, label:label, service:service });   // bỏ dòng trống
      });
      saveSources(list, sv);
    });
  })();

  // ----- editable: check-all + link bar typeahead -----
  if(EDIT){
    var all=$('blCheckAll');
    if(all) all.addEventListener('change', function(){
      monthBugs().forEach(function(b){ if(all.checked) sel[b.key]=true; else delete sel[b.key]; });
      render(); });

    var inp=$('blTaskInp'), res=$('blTaskRes'), chips=$('blTaskChips'), taT;

    // guard: nếu markup link bar chưa có (vd server chưa restart sau khi đổi render.py)
    // thì bỏ qua phần typeahead — KHÔNG để throw làm chết cả controller (mất bảng/tab).
    if(inp && res && chips){
    // vẽ lại các chip task đã chọn (đứng trước input trong cùng field)
    function renderChips(){
      chips.querySelectorAll('.bl-ta-chip').forEach(function(c){ c.remove(); });
      taskSel.forEach(function(k){
        var el=document.createElement('span'); el.className='bl-ta-chip';
        el.innerHTML='<b>'+esc(k)+'</b><span class="x material-symbols-rounded mi-sm" data-rm="'+esc(k)+'">close</span>';
        chips.insertBefore(el, inp);
      });
    }
    function addTask(k){ if(k && taskSel.indexOf(k)<0){ taskSel.push(k); renderChips(); }
      inp.value=''; res.classList.remove('open'); updateLinkBtn(); inp.focus(); }
    function rmTask(k){ taskSel=taskSel.filter(function(t){return t!==k;}); renderChips(); updateLinkBtn(); }

    inp.addEventListener('input', function(){
      var q=inp.value.trim(); clearTimeout(taT);
      if(q.length<2){ res.classList.remove('open'); return; }
      taT=setTimeout(function(){
        getJSON('/search-tasks?q='+encodeURIComponent(q), 15000).then(function(j){
          var rs=(j&&j.results)||[];
          // bỏ task đã chọn khỏi gợi ý
          rs=rs.filter(function(r){ return taskSel.indexOf(r.key)<0; });
          if(!rs.length){ res.innerHTML='<div class="opt">Không có task phù hợp.</div>'; res.classList.add('open'); return; }
          res.innerHTML = rs.map(function(r){
            var meta=[r.assignee, r.status].filter(Boolean).map(esc).join(' · ');
            return '<div class="opt" data-k="'+esc(r.key)+'"><b>'+esc(r.key)+'</b> — '+esc(r.summary)
              +(meta?'<span class="bl-opt-meta">'+meta+'</span>':'')+'</div>'; }).join('');
          res.classList.add('open');
        }).catch(function(){ res.classList.remove('open'); });
      }, 250);
    });
    // Backspace ở ô rỗng = gỡ chip cuối
    inp.addEventListener('keydown', function(e){
      if(e.key==='Backspace' && !inp.value && taskSel.length){ rmTask(taskSel[taskSel.length-1]); }
    });
    res.addEventListener('click', function(e){ var o=e.target.closest('.opt[data-k]'); if(!o) return;
      addTask(o.getAttribute('data-k')); });
    // ✕ trên chip = bỏ task khỏi danh sách đang chọn
    chips.addEventListener('click', function(e){ var x=e.target.closest('[data-rm]'); if(!x) return;
      rmTask(x.getAttribute('data-rm')); });
    document.addEventListener('click', function(e){ if(!e.target.closest('#blTaskTA')) res.classList.remove('open'); });
    }  // end guard typeahead

    var lbtn=$('blLinkBtn');
    if(lbtn) lbtn.addEventListener('click', function(){
      var keys=Object.keys(sel).filter(function(k){return sel[k];});
      if(!keys.length) return;
      if(!taskSel.length) { toast('Vui lòng tìm và chọn task ở ô bên trái để liên kết', false); return; }
      doLink(keys, taskSel.slice());
    });
  }

  // op: 'add' (thêm task(s) vào bug), 'remove' (gỡ 1 task khỏi bug), 'clear' (gỡ hết)
  // task: str (1 task — vd unlink) hoặc list[str] (multi-select link bar)
  function doLink(keys, task, op){
    op = op || 'add';
    var tList = Array.isArray(task) ? task : [task];
    postJSON('/link-task', { keys: keys, task: task, op: op }, 20000).then(function(j){
      if(j && j.ok && j.links){
        var m=j.links;   // {bugKey: [tasks...]} trạng thái mới
        BUGS.forEach(function(b){ if(m.hasOwnProperty(b.key)) b.tasks = m[b.key]||[]; });
        if(op==='add'){ keys.forEach(function(k){ delete sel[k]; });
          taskSel=[]; var inp=$('blTaskInp'), ch=$('blTaskChips');
          if(inp) inp.value=''; if(ch) ch.querySelectorAll('.bl-ta-chip').forEach(function(c){ c.remove(); });
          toast('Đã liên kết '+keys.length+' mục với '+tList.join(', ')+' ✓', true); }
        else toast('Đã gỡ liên kết ✓', true);
        renderTabs(); render();
      } else toast('Lỗi lưu liên kết', false);
    }).catch(function(){ toast('Lỗi mạng khi liên kết', false); });
  }


  if(activeFid){ var av0=availMonths(); if(av0.indexOf(curMonth)<0) curMonth = av0.length?av0[0]:''; }
  renderTabs(); render(); updateActiveChip(); updateSrcLine();
})();

// ================= BUG METRICS (dashboard admin, guard #bugMetrics) =================
// Tổng bug + bug theo từng status (cột "Status" gốc), chọn theo file + sheet, kèm
// "dòng lịch sử thay đổi qua mỗi lần sync" (delta giữa các mốc). Nguồn = bug_log_store
// (snapshot mỗi lần file Drive đổi). KHÔNG reload — F5 để lấy mốc mới.
(function(){
  var card = $('bugMetricCard'); if(!card) return;
  // DATA null (chưa sync / render cũ) -> coi như rỗng để rơi vào nhánh empty-state
  // bên dưới (hiện thông báo), KHÔNG return sớm để tránh card trắng câm.
  var DATA = readJSON('bugMetrics') || {};
  var fileSel = $('bmFile'), sheetSel = $('bmSheet');
  var curBox = $('bmCurrent'), histBox = $('bmHistory'), syncedBox = $('bmSynced');
  var FILES = DATA.files || [], METRICS = DATA.metrics || {};

  // Màu ổn định theo tên status -> cùng status luôn cùng màu giữa các mốc.
  var PALETTE = ['#4c9aff','#36b37e','#ffab00','#ff5630','#6554c0','#00b8d9','#ff7452','#57d9a3','#8777d9','#ff8b00'];
  function colorOf(name){
    var h=0; name=String(name); for(var i=0;i<name.length;i++){ h=(h*31 + name.charCodeAt(i))>>>0; }
    return PALETTE[h % PALETTE.length];
  }
  function fmtAt(at){ return String(at||'').replace('T',' ').slice(0,16); }
  function delta(cur, prev){
    var d = (cur||0) - (prev||0); if(!d) return '';
    return '<span class="bm-delta '+(d>0?'up':'down')+'">'+(d>0?'▲':'▼')+Math.abs(d)+'</span>';
  }
  // Status mà TĂNG = TỐT (xanh): đã fix/xong/đóng. Còn lại tăng = xấu (đỏ).
  function isGood(name){ return /fix|done|resolv|clos|xong|hoàn|đóng|pass/i.test(String(name)); }
  // Delta dạng % + mũi tên (card view). good = tăng có lợi không -> chọn màu.
  function deltaCard(cur, prev, good){
    if(prev==null) return '';
    var d=(cur||0)-(prev||0);
    if(!d) return '<span class="bm-delta flat">0%<span class="material-symbols-rounded bm-arr">remove</span></span>';
    var benefit = good ? d>0 : d<0;          // thay đổi này có lợi?
    var cls = benefit ? 'down' : 'up';        // down=xanh(tốt) · up=đỏ(xấu)
    var txt = (d>0?'+':'')+d;          // số tăng/giảm tuyệt đối (bỏ %, base nhỏ làm % nổ)
    var arr = d>0 ? 'trending_up' : 'trending_down';
    return '<span class="bm-delta '+cls+'">'+txt+
      '<span class="material-symbols-rounded bm-arr">'+arr+'</span></span>';
  }

  if(!FILES.length){
    var body = card.querySelector('.bm-body');
    if(body) body.innerHTML = '<div class="bm-empty">Chưa có dữ liệu metric bug. '+
      'Vào tab Bug Log → bấm “Đồng bộ ngay”.</div>';
    if(fileSel) fileSel.style.display='none';
    if(sheetSel) sheetSel.style.display='none';
    if(syncedBox) syncedBox.textContent = 'Đã đồng bộ: '+(DATA.syncedAt||'—');
    return;
  }

  // ----- File vừa update lên đầu + chấm ● đánh dấu file đổi, mất khi đã xem -----
  // "đổi" = mốc sync mới nhất của file khác với mốc đã xem (lưu localStorage qa-bm-seen).
  // Lần đầu (chưa có localStorage) -> seed tất cả là đã xem, tránh highlight loạn (như NEW badge).
  function fileLatestAt(fid){
    var sheets = METRICS[fid] || {}, max = '';
    Object.keys(sheets).forEach(function(m){
      var arr = sheets[m] || [];
      if(arr.length){ var at = arr[arr.length-1].at || ''; if(at > max) max = at; }
    });
    return max;
  }
  var SEEN_KEY = 'qa-bm-seen', SEEN = {};
  (function(){
    var raw = null; try{ raw = localStorage.getItem(SEEN_KEY); }catch(e){}
    if(raw == null){   // lần đầu -> baseline, không highlight gì
      FILES.forEach(function(f){ SEEN[f.fid] = fileLatestAt(f.fid); });
      try{ localStorage.setItem(SEEN_KEY, JSON.stringify(SEEN)); }catch(e){}
    } else { try{ SEEN = JSON.parse(raw) || {}; }catch(e){ SEEN = {}; } }
  })();
  function isChanged(fid){ var at = fileLatestAt(fid); return !!at && at !== SEEN[fid]; }
  function saveSeen(){ try{ localStorage.setItem(SEEN_KEY, JSON.stringify(SEEN)); }catch(e){} }
  // file đổi gần nhất lên đầu (chuỗi ISO so sánh trực tiếp); tie -> theo tên
  FILES.sort(function(a,b){
    var x = fileLatestAt(a.fid), y = fileLatestAt(b.fid);
    if(x !== y) return x < y ? 1 : -1;
    return (a.label||'').toLowerCase().localeCompare((b.label||'').toLowerCase());
  });

  // Status được track ở CẢ card + lịch sử (tổng bug vẫn tính trên tất cả status).
  var TRACKED = ['New','Fixed','Closed','Reopen'];
  function isTracked(k){ return TRACKED.indexOf(k) >= 0; }

  function snapshots(){ return ((METRICS[fileSel.value]||{})[sheetSel.value])||[]; }

  // Mọi status từng xuất hiện trong lịch sử (file,sheet) -> tập cột ổn định.
  function statusKeys(snaps){
    var seen={}, order=[];
    snaps.forEach(function(s){ Object.keys(s.statuses||{}).forEach(function(k){
      if(!seen[k]){ seen[k]=1; order.push(k); } }); });
    return order.sort();
  }

  function render(){
    var snaps = snapshots();
    if(!snaps.length){
      curBox.innerHTML = '<div class="bm-empty">Sheet này chưa có dữ liệu metric.</div>';
      histBox.innerHTML = ''; return;
    }
    var keys = statusKeys(snaps);
    var latest = snaps[snaps.length-1];
    var prev = snaps.length>1 ? snaps[snaps.length-2] : null;

    // ----- Hiện tại: mỗi status 1 card (tổng + theo status), delta % vs mốc trước -----
    var cards = '<div class="bm-card bm-card-total">'+
      '<div class="bm-card-lbl">Tổng bug</div>'+
      '<div class="bm-card-row"><span class="bm-card-num">'+latest.total+'</span>'+
      deltaCard(latest.total, prev?prev.total:null, false)+'</div></div>';
    // Card cố định theo TRACKED (New/Fixed/Closed/Reopen) — luôn hiện đủ kể cả khi
    // status đó chưa từng xuất hiện trong lịch sử (count=0), tránh "thiếu status".
    TRACKED.forEach(function(k){
      var v=(latest.statuses||{})[k]||0, pv=prev?((prev.statuses||{})[k]||0):0, c=colorOf(k);
      cards += '<div class="bm-card" style="--bm-acc:'+c+'">'+
        '<div class="bm-card-lbl" style="color:'+c+'">'+esc(k)+'</div>'+
        '<div class="bm-card-row"><span class="bm-card-num">'+v+'</span>'+
        deltaCard(v, prev?pv:null, isGood(k))+'</div></div>';
    });
    curBox.innerHTML = '<div class="bm-cards">'+cards+'</div>';

    // ----- Lịch sử: mỗi mốc sync 1 dòng (mới nhất trên cùng) + delta vs mốc trước -----
    // Chỉ hiện 3 mốc gần nhất (delta vẫn so với mốc liền trước, kể cả mốc thứ 4 đã ẩn).
    var rows='', shown=0;
    for(var i=snaps.length-1;i>=0 && shown<3;i--,shown++){
      var s=snaps[i], p=i>0?snaps[i-1]:null;
      var chips = keys.filter(isTracked).map(function(k){
        var v=(s.statuses||{})[k]||0, pv=p?((p.statuses||{})[k]||0):0;
        if(!v && !pv) return '';
        return '<span class="bm-hchip"><span class="bm-dot" style="background:'+colorOf(k)+'"></span>'+
          esc(k)+' '+v+(p?delta(v,pv):'')+'</span>';
      }).filter(Boolean).join('');
      rows += '<div class="bm-hrow"><div class="bm-htime">'+esc(fmtAt(s.at))+'</div>'+
        '<div class="bm-htotal">Tổng '+s.total+(p?delta(s.total,p.total):'')+'</div>'+
        '<div class="bm-hchips">'+chips+'</div></div>';
    }
    histBox.innerHTML = rows;
  }

  function fillSheets(){
    var f = FILES.filter(function(x){return x.fid===fileSel.value;})[0] || FILES[0];
    var months = (f&&f.months)||[];
    sheetSel.innerHTML = months.map(function(m){
      return '<option value="'+esc(m)+'">'+esc(m)+'</option>'; }).join('');
  }

  function buildFileOpts(){          // chấm ● cho file đổi; giữ nguyên lựa chọn hiện tại
    var cur = fileSel.value;
    fileSel.innerHTML = FILES.map(function(f){
      return '<option value="'+esc(f.fid)+'">'+(isChanged(f.fid)?'● ':'')+esc(f.label)+'</option>';
    }).join('');
    if(cur) fileSel.value = cur;
  }
  function markSeen(fid){            // đã xem file -> cập nhật mốc + bỏ chấm highlight
    var at = fileLatestAt(fid);
    if(at && SEEN[fid] !== at){ SEEN[fid] = at; saveSeen(); buildFileOpts(); }
  }
  buildFileOpts();
  fileSel.addEventListener('change', function(){ markSeen(fileSel.value); fillSheets(); render(); });
  sheetSel.addEventListener('change', render);
  if(syncedBox) syncedBox.textContent = 'Đã đồng bộ: '+(DATA.syncedAt||'—');
  fillSheets(); render();
  markSeen(fileSel.value);           // file đang hiển thị mặc định = đã xem
})();

// ================= ANALYTICS (guard #analyticsData, issue #158) =================
// Gom metric bug: Valid Bug Rate + chart bug theo dev/dự án + Tỷ lệ Reopen.
// Data nguồn = analyticsData (bug_log cache). Dùng $/esc/toast/readJSON ở scope chung.
(function(){
  var DATA = readJSON('analyticsData'); if(!DATA) return;
  var BUGS = DATA.bugs||[], REOPEN = DATA.reopen||{};
  var PIE_COLORS = ['#4c9aff','#36b37e','#ffab00','#ff5630','#6554c0','#00b8d9','#ff7452','#57d9a3','#8777d9','#ff8b00','#2684ff','#172b4d'];

  // Data for cross metrics
  var TC_DATA = DATA.tcData || {};
  var TC_CASES = TC_DATA.cases || [];
  var BUG_LINKS = DATA.bugLinks || {};
  var TC_LINKS = DATA.tcLinks || {};

  function tasksOf(v) {
    if(!v) return [];
    if(Array.isArray(v.tasks)) return v.tasks.filter(Boolean);
    if(typeof v.task === 'string' && v.task) return [v.task];
    return [];
  }

  // ---------- New KPI Metrics (Cross Task, TC, Bug) ----------
  var anTcCoverageBox = $('anTcCoverageBox'), anTcExecutionBox = $('anTcExecutionBox'), anBugDensityBox = $('anBugDensityBox');
  function renderCrossMetrics() {
    if(!anTcCoverageBox || !anTcExecutionBox || !anBugDensityBox) return;

    var linkedTaskSet = {};
    var tcTaskSet = {};
    var bugTaskSet = {};
    var totalBugCountLinked = 0;

    Object.keys(BUG_LINKS).forEach(function(bugKey) {
      var ts = tasksOf(BUG_LINKS[bugKey]);
      if (ts.length) totalBugCountLinked++;
      ts.forEach(function(t) { linkedTaskSet[t] = true; bugTaskSet[t] = true; });
    });
    Object.keys(TC_LINKS).forEach(function(folderId) {
      tasksOf(TC_LINKS[folderId]).forEach(function(t) { linkedTaskSet[t] = true; tcTaskSet[t] = true; });
    });

    var totalTasks = Object.keys(linkedTaskSet).length;
    var tasksWithTc = Object.keys(tcTaskSet).length;

    // Coverage
    if (totalTasks === 0) {
      anTcCoverageBox.innerHTML = '<div class="an-empty">Chưa có task nào được liên kết với testcase hoặc bug.</div>';
    } else {
      var covPct = (tasksWithTc / totalTasks) * 100;
      var covDisp = (covPct % 1 === 0 ? covPct.toFixed(0) : covPct.toFixed(1)) + '%';
      anTcCoverageBox.innerHTML = 
        '<div class="an-valid-main"><span class="an-valid-pct">'+covDisp+'</span>'
        + '<span class="an-valid-cap">task có test case</span></div>'
        + '<div class="an-valid-break">'
        +   '<div class="an-stat"><span class="an-stat-n">'+tasksWithTc+'</span><span class="an-stat-l">Task có TC</span></div>'
        +   '<div class="an-stat-op">/</div>'
        +   '<div class="an-stat"><span class="an-stat-n">'+totalTasks+'</span><span class="an-stat-l">Tổng số Task (có hoạt động)</span></div>'
        + '</div>';
    }

    // Bug Density
    if (totalTasks === 0) {
      anBugDensityBox.innerHTML = '<div class="an-empty">Chưa có data</div>';
    } else {
      var density = totalBugCountLinked / totalTasks;
      var denDisp = density.toFixed(2);
      anBugDensityBox.innerHTML = 
        '<div class="an-valid-main"><span class="an-valid-pct">'+denDisp+'</span>'
        + '<span class="an-valid-cap">bug / task</span></div>'
        + '<div class="an-valid-break">'
        +   '<div class="an-stat"><span class="an-stat-n">'+totalBugCountLinked+'</span><span class="an-stat-l">Tổng số Bug liên kết</span></div>'
        +   '<div class="an-stat-op">/</div>'
        +   '<div class="an-stat"><span class="an-stat-n">'+totalTasks+'</span><span class="an-stat-l">Tổng số Task (có hoạt động)</span></div>'
        + '</div>';
    }

    // TC Execution & Pass Rate
    if (TC_CASES.length === 0) {
      anTcExecutionBox.innerHTML = '<div class="an-empty" style="width:100%;">Chưa có data test case</div>';
    } else {
      var pass = 0, fail = 0, norun = 0;
      TC_CASES.forEach(function(c) {
        var r = c.result || 'norun';
        if (r === 'pass') pass++;
        else if (r === 'fail') fail++;
        if (r === 'norun') norun++;
      });
      var total = TC_CASES.length;
      var executed = total - norun;
      var execPct = (executed / total) * 100;
      var execDisp = (execPct % 1 === 0 ? execPct.toFixed(0) : execPct.toFixed(1)) + '%';
      var passRateDisp = '—';
      if (executed > 0) {
        var pr = (pass / executed) * 100;
        passRateDisp = (pr % 1 === 0 ? pr.toFixed(0) : pr.toFixed(1)) + '%';
      }

      anTcExecutionBox.innerHTML = 
        '<div style="flex:1;">'
        + '<div class="an-valid-main"><span class="an-valid-pct">'+execDisp+'</span>'
        + '<span class="an-valid-cap">tiến độ chạy</span></div>'
        + '<div class="an-valid-break">'
        +   '<div class="an-stat"><span class="an-stat-n">'+executed+'</span><span class="an-stat-l">Đã chạy</span></div>'
        +   '<div class="an-stat-op">/</div>'
        +   '<div class="an-stat"><span class="an-stat-n">'+total+'</span><span class="an-stat-l">Tổng số Case</span></div>'
        + '</div>'
        + '</div>'
        + '<div style="flex:1; border-left:1px solid var(--outline-variant); padding-left:32px;">'
        + '<div class="an-valid-main"><span class="an-valid-pct">'+passRateDisp+'</span>'
        + '<span class="an-valid-cap">tỷ lệ Pass</span></div>'
        + '<div class="an-valid-break">'
        +   '<div class="an-stat"><span class="an-stat-n">'+pass+'</span><span class="an-stat-l">Pass</span></div>'
        +   '<div class="an-stat-op">/</div>'
        +   '<div class="an-stat"><span class="an-stat-n">'+executed+'</span><span class="an-stat-l">Đã chạy</span></div>'
        + '</div>'
        + '</div>';
    }
  }

  function getCreatedMonthYear(iso){
    if(!iso) return '';
    var p = iso.split('-');
    return p.length>=2 ? p[1]+'/'+p[0] : '';
  }
  // danh sách tháng/năm để fill dropdown (năm hiện tại + năm có trong data)
  var FULL_MONTH_YEARS = (function(){
    var years = {}; years[new Date().getFullYear()] = true;
    BUGS.forEach(function(b){ if(b.created){ var p=b.created.split('-'); if(p[0]) years[parseInt(p[0],10)]=true; } });
    var out = [];
    Object.keys(years).sort().reverse().forEach(function(y){
      if(y && !isNaN(y)) for(var i=1;i<=12;i++){ var mm=i<10?'0'+i:''+i; out.push(mm+'/'+y); }
    });
    return out;
  })();
  var curMonth = (function(){ var d=new Date(), m=d.getMonth()+1; return (m<10?'0'+m:m)+'/'+d.getFullYear(); })();

  function fillMonth(sel){
    if(!sel) return;
    if(FULL_MONTH_YEARS.length){
      sel.innerHTML = FULL_MONTH_YEARS.map(function(m){ return '<option value="'+esc(m)+'">Tháng '+esc(m)+'</option>'; }).join('');
      sel.value = curMonth;
    } else sel.innerHTML = '<option value="">Chưa có dữ liệu</option>';
  }

  // ---------- Valid Bug Rate = Closed / (Tổng bug − Reject) ----------
  var validMonthSel = $('anValidMonth'), validBox = $('anValidBox');
  function isReject(s){ return /reject/i.test(s||''); }
  function isClosed(s){ return /closed|đã đóng/i.test(s||''); }
  function renderValid(){
    if(!validMonthSel || !validBox) return;
    var m = validMonthSel.value;
    var mBugs = BUGS.filter(function(b){ return getCreatedMonthYear(b.created) === m; });
    var total = mBugs.length;
    var reject = mBugs.filter(function(b){ return isReject(b.status); }).length;
    var closed = mBugs.filter(function(b){ return isClosed(b.status); }).length;
    var denom = total - reject;
    if(total === 0){
      validBox.innerHTML = '<div class="an-empty">Không có bug trong tháng này</div>';
      return;
    }
    var pct = denom > 0 ? (closed/denom*100) : null;
    var pctDisp = pct === null ? '—' : (pct%1===0 ? pct.toFixed(0) : pct.toFixed(1)) + '%';
    var rejPct = total > 0 ? (reject/total*100) : 0;
    var rejDisp = (rejPct%1===0 ? rejPct.toFixed(0) : rejPct.toFixed(1)) + '%';

    validBox.innerHTML =
      '<div style="flex:1;">'
      + '<div class="an-valid-main"><span class="an-valid-pct">'+pctDisp+'</span>'
      + '<span class="an-valid-cap">bug hợp lệ đã đóng</span></div>'
      + '<div class="an-valid-break">'
      +   '<div class="an-stat"><span class="an-stat-n">'+closed+'</span><span class="an-stat-l">Closed</span></div>'
      +   '<div class="an-stat-op">/</div>'
      +   '<div class="an-stat"><span class="an-stat-n">'+denom+'</span><span class="an-stat-l">Tổng '+total+' − Reject '+reject+'</span></div>'
      + '</div>'
      + '</div>'
      + '<div style="flex:1; border-left:1px solid var(--outline-variant); padding-left:32px;">'
      + '<div class="an-valid-main"><span class="an-valid-pct">'+rejDisp+'</span>'
      + '<span class="an-valid-cap">tỷ lệ Reject</span></div>'
      + '<div class="an-valid-break">'
      +   '<div class="an-stat"><span class="an-stat-n">'+reject+'</span><span class="an-stat-l">Reject</span></div>'
      +   '<div class="an-stat-op">/</div>'
      +   '<div class="an-stat"><span class="an-stat-n">'+total+'</span><span class="an-stat-l">Tổng số Bug</span></div>'
      + '</div>'
      + '</div>';
  }

  // ---------- Bar chart: bug của dev theo dự án ----------
  var metricMonthSel = $('anMetricMonth'), metricCharts = $('anMetricCharts');
  function renderMetric(){
    if(!metricMonthSel || !metricCharts) return;
    var selectedMonth = metricMonthSel.value;
    if(!selectedMonth){ metricCharts.innerHTML = '<div class="an-empty">Không có dữ liệu</div>'; return; }
    var mBugs = BUGS.filter(function(b){ return getCreatedMonthYear(b.created) === selectedMonth; });
    var devs = {}, projSet = {};
    mBugs.forEach(function(b){
      var devList = (b.dev||'Chưa gán').trim().split(/[,;+&]/).map(function(s){ return s.trim(); }).filter(Boolean);
      if(!devList.length) devList = ['Chưa gán'];
      var fraction = 1/devList.length, p = (b.project||'Khác').trim();
      devList.forEach(function(d){
        if(!devs[d]) devs[d] = { total:0, projs:{} };
        devs[d].projs[p] = (devs[d].projs[p]||0) + fraction;
        devs[d].total += fraction;
      });
      projSet[p] = true;
    });
    var devList = Object.keys(devs).sort(function(a,b){ return devs[b].total - devs[a].total; });
    var projList = Object.keys(projSet).sort();
    if(!devList.length){ metricCharts.innerHTML = '<div class="an-empty">Không có dữ liệu trong tháng này</div>'; return; }
    // tổng số bug theo từng dự án + tổng toàn tháng (bug đa-dev tính phân số nên tổng = số bug thật)
    var projTotals = {}, grandTotal = mBugs.length;
    projList.forEach(function(p){ projTotals[p] = 0; });
    devList.forEach(function(d){ var pj = devs[d].projs; Object.keys(pj).forEach(function(p){ projTotals[p] += pj[p]; }); });
    var maxTotal = 0; devList.forEach(function(d){ if(devs[d].total>maxTotal) maxTotal = devs[d].total; });
    var yMax = Math.max(5, Math.ceil(maxTotal/5)*5), steps = 5, chartHeight = 260;
    var ticksHtml = '';
    for(var i=0;i<=steps;i++){
      var val = Math.round((yMax/steps)*i), bottomPct = (i/steps)*100;
      ticksHtml += '<div style="position:absolute; bottom:'+bottomPct+'%; right:8px; transform:translateY(50%); font-size:11px; color:var(--on-surface-variant);">'+val+'</div>';
    }
    var barsHtml = '';
    devList.forEach(function(d){
      var dData = devs[d], segmentsHtml = '';
      projList.forEach(function(p, idx){
        var count = dData.projs[p];
        if(count){
          var pct = (count/yMax)*100, color = PIE_COLORS[idx%PIE_COLORS.length], displayCount = +(count.toFixed(2));
          segmentsHtml = '<div style="width:100%; height:'+pct+'%; background:'+color+'; display:flex; align-items:center; justify-content:center; color:#fff; font-size:11px; font-weight:600; overflow:hidden;" title="'+esc(p)+': '+displayCount+'">' + (pct>6?displayCount:'') + '</div>' + segmentsHtml;
        }
      });
      var displayTotal = +(dData.total.toFixed(2));
      barsHtml += '<div style="display:flex; flex-direction:column; align-items:center; width:48px; margin:0 12px; z-index:1;">'
        + '<div style="font-size:12.5px; font-weight:700; color:var(--on-surface); margin-bottom:6px;">'+displayTotal+'</div>'
        + '<div style="width:100%; height:'+chartHeight+'px; display:flex; flex-direction:column; justify-content:flex-end; border-radius:4px 4px 0 0; overflow:hidden;">' + segmentsHtml + '</div>'
        + '<div style="font-size:12px; margin-top:10px; text-align:center; word-break:break-word; color:var(--on-surface-variant); width:64px; line-height:1.3;">'+esc(d)+'</div>'
        + '</div>';
    });
    var legendHtml = '';
    projList.forEach(function(p, idx){
      var color = PIE_COLORS[idx%PIE_COLORS.length];
      legendHtml += '<div style="display:flex; align-items:center; margin-right:16px; margin-bottom:8px; font-size:13.5px;">'
        + '<span style="display:inline-block; width:14px; height:14px; background:'+color+'; border-radius:3px; margin-right:6px;"></span>'
        + '<span style="color:var(--on-surface);">'+esc(p)+' <strong>('+(+(projTotals[p].toFixed(2)))+')</strong></span></div>';
    });
    var totalHtml = '<div style="text-align:center; margin-bottom:14px; font-size:14px; color:var(--on-surface);">'
      + 'Tổng số bug: <strong style="font-size:16px;">'+grandTotal+'</strong></div>';
    metricCharts.innerHTML = '<div style="width:100%; display:flex; flex-direction:column; padding:10px 0;">'
      + totalHtml
      + '<div style="display:flex; justify-content:center; flex-wrap:wrap; margin-bottom:24px;">' + legendHtml + '</div>'
      + '<div style="display:flex; align-items:flex-start;">'
      +   '<div style="position:relative; height:'+chartHeight+'px; width:40px; flex-shrink:0;">' + ticksHtml + '</div>'
      +   '<div class="hide-scrollbar" style="position:relative; flex:1; height:'+(chartHeight+50)+'px; display:flex; align-items:flex-start; overflow-x:auto; border-bottom:1px solid var(--outline-variant);">'
      +     '<div style="display:flex; height:'+(chartHeight+40)+'px; padding-top:0;">' + barsHtml + '</div>'
      +   '</div></div></div>';
  }

  // ---------- Reopen table ----------
  var reopenMonthSel = $('anReopenMonth'), reopenKpi = $('anReopenKpi'),
      reopenHead = $('anReopenHead'), reopenRows = $('anReopenRows');
  var reopenExpanded = {};
  function reopenPct(n, d){ if(d<=0) return null; var p = n/d*100; return (p%1===0 ? p.toFixed(0) : p.toFixed(1)); }
  function fixOf(r){ return (r && r.fix!=null) ? (+r.fix||0) : ((+(r&&r.count)||0)+1); }
  function renderReopen(){
    if(!reopenMonthSel || !reopenHead || !reopenRows) return;
    var selectedMonth = reopenMonthSel.value;
    if(!selectedMonth){
      if(reopenKpi) reopenKpi.innerHTML = '';
      reopenHead.innerHTML = '';
      reopenRows.innerHTML = '<tr><td style="text-align:center;color:var(--on-surface-variant);padding:30px">Không có dữ liệu</td></tr>';
      return;
    }
    var mBugs = BUGS.filter(function(b){ return getCreatedMonthYear(b.created) === selectedMonth; });
    var bugsPerDev = {}, totalBugs = mBugs.length, bugByKey = {};
    mBugs.forEach(function(b){
      var devList = (b.dev||'Chưa gán').trim().split(/[,;+&]/).map(function(s){ return s.trim(); }).filter(Boolean);
      if(!devList.length) devList = ['Chưa gán'];
      var fraction = 1/devList.length;
      devList.forEach(function(d){ bugsPerDev[d] = (bugsPerDev[d]||0) + fraction; });
      if(b.key) bugByKey[b.key] = b;
    });
    var distinctPerDev = {}, fixPerDev = {}, detailPerDev = {}, distinctTotal = 0;
    Object.keys(REOPEN).forEach(function(key){
      var r = REOPEN[key]||{}, cnt = +r.count||0; if(cnt<=0) return;
      var b = bugByKey[key];
      if(!b){ var rm = r.month||'', p = rm.split('-'), fm = p.length>=2 ? (p[1]+'/'+p[0]) : rm; if(fm !== selectedMonth) return; }
      var devStr = ((b ? b.dev : r.dev)||'Chưa gán').trim(), fx = fixOf(r);
      var devList = devStr.split(/[,;+&]/).map(function(s){ return s.trim(); }).filter(Boolean);
      if(!devList.length) devList = ['Chưa gán'];
      var fraction = 1/devList.length; distinctTotal++;
      devList.forEach(function(d){
        distinctPerDev[d] = (distinctPerDev[d]||0) + fraction;
        fixPerDev[d] = (fixPerDev[d]||0) + (fx*fraction);
        (detailPerDev[d] = detailPerDev[d]||[]).push({ id: b?b.id:key, summary: b?b.summary:'', reopen: cnt*fraction, fix: fx*fraction });
      });
    });
    if(reopenKpi){
      var hp = reopenPct(distinctTotal, totalBugs);
      reopenKpi.innerHTML = hp === null ? '<span class="rk-sub">Không có bug trong tháng này.</span>'
        : '<span class="rk-pct">'+hp+'%</span> bug bị reopen';
    }
    reopenHead.innerHTML = '<th>Developer</th><th>Bug bị reopen</th><th>Tổng số lần fix bug</th><th>Tỷ lệ reopen</th>';
    var devList = Object.keys(distinctPerDev).sort(function(a,b){ return distinctPerDev[b] - distinctPerDev[a]; });
    if(!devList.length){
      reopenRows.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--on-surface-variant);padding:30px">Chưa ghi nhận reopen nào trong tháng này 🎉</td></tr>';
      return;
    }
    function rateCell(nb, denom){ var r = reopenPct(nb, denom); return r === null ? '—' : r+'%'; }
    function detailRow(dev){
      var items = (detailPerDev[dev]||[]).slice().sort(function(a,b){ return b.reopen - a.reopen; });
      var li = items.map(function(it){
        return '<div class="rk-bug"><span class="rk-bug-id">'+esc(it.id)+'</span>'
          + '<span class="rk-bug-sum">'+esc(it.summary||'(không mô tả)')+'</span>'
          + '<span class="rk-bug-n">'+(+(it.reopen.toFixed(2)))+' lần reopen · '+(+(it.fix.toFixed(2)))+' lần fix</span></div>';
      }).join('');
      return '<tr class="rk-detail"><td colspan="4"><div class="rk-detail-box">'
        + '<div class="rk-detail-hd">Chi tiết bug bị reopen của '+esc(dev)+'</div>' + li + '</div></td></tr>';
    }
    reopenRows.innerHTML = devList.map(function(d){
      var nb = distinctPerDev[d], fx = fixPerDev[d], denom = bugsPerDev[d]||0, open = !!reopenExpanded[d];
      var row = '<tr class="rk-row'+(open?' open':'')+'" data-dev="'+esc(d)+'">'
        + '<td><span class="rk-caret material-symbols-rounded">'+(open?'expand_more':'chevron_right')+'</span>'+esc(d)+'</td>'
        + '<td>'+(+(nb.toFixed(2)))+'</td><td>'+(+(fx.toFixed(2)))+'</td>'
        + '<td class="col-total">'+rateCell(nb, denom)+'</td></tr>';
      if(open) row += detailRow(d);
      return row;
    }).join('');
  }
  if(reopenRows) reopenRows.addEventListener('click', function(e){
    var tr = e.target.closest('.rk-row'); if(!tr) return;
    var dev = tr.getAttribute('data-dev'); if(!dev) return;
    reopenExpanded[dev] = !reopenExpanded[dev];
    renderReopen();
  });

  // ---------- Export PDF (bar chart) ----------
  var btnExport = $('anExportChart');
  if(btnExport) btnExport.addEventListener('click', function(){
    if(!metricCharts || !metricCharts.innerHTML || metricCharts.innerHTML.indexOf('an-empty') >= 0){ toast('Không có dữ liệu để export', false); return; }
    var origText = btnExport.innerHTML;
    btnExport.innerHTML = '<span class="material-symbols-rounded mi-sm">sync</span> Đang xuất...';
    btnExport.disabled = true;
    function doExport(){
      var titleEl = document.createElement('div');
      titleEl.style.cssText = 'font-size:24px; font-weight:bold; text-align:center; width:100%; margin-bottom:20px;';
      titleEl.style.color = getComputedStyle(document.body).getPropertyValue('--on-surface') || '#000';
      titleEl.textContent = 'Số lượng bug theo từng dev (tháng '+(metricMonthSel.value||'')+')';
      metricCharts.insertBefore(titleEl, metricCharts.firstChild);
      var innerScroll = metricCharts.querySelector('div[style*="overflow-x:auto"]') || metricCharts.querySelector('div[style*="overflow-x: auto"]');
      var origInnerOverflow = '';
      if(innerScroll){ origInnerOverflow = innerScroll.style.overflowX; innerScroll.style.overflowX = 'visible'; }
      var origWidth = metricCharts.style.width;
      metricCharts.style.width = Math.max(metricCharts.scrollWidth, 1200)+'px';
      html2canvas(metricCharts, { scale:2, backgroundColor: getComputedStyle(document.body).getPropertyValue('--surface')||'#fff' }).then(function(canvas){
        titleEl.remove();
        if(innerScroll) innerScroll.style.overflowX = origInnerOverflow;
        metricCharts.style.width = origWidth;
        var imgData = canvas.toDataURL('image/png');
        window.__lastExportedImage = imgData;  // để reporter tháng (Playwright) upload PNG lên Drive
        var pdf = new window.jspdf.jsPDF('l','mm','a4');
        var pdfWidth = pdf.internal.pageSize.getWidth(), pdfHeight = pdf.internal.pageSize.getHeight();
        var imgProps = pdf.getImageProperties(imgData), margin = 10;
        var imgWidth = pdfWidth - margin*2, imgHeight = (imgProps.height*imgWidth)/imgProps.width;
        if(imgHeight > pdfHeight - margin*2){ imgHeight = pdfHeight - margin*2; imgWidth = (imgProps.width*imgHeight)/imgProps.height; }
        var xPos = margin + (pdfWidth - margin*2 - imgWidth)/2, yPos = margin + (pdfHeight - margin*2 - imgHeight)/2;
        pdf.addImage(imgData, 'PNG', xPos, yPos, imgWidth, imgHeight);
        pdf.save('Bug_Metric_'+(metricMonthSel.value||'chart')+'.pdf');
        btnExport.innerHTML = origText; btnExport.disabled = false;
        toast('Export PDF thành công ✓', true);
      }).catch(function(err){
        titleEl.remove();
        if(innerScroll) innerScroll.style.overflowX = origInnerOverflow;
        metricCharts.style.width = origWidth;
        btnExport.innerHTML = origText; btnExport.disabled = false;
        toast('Lỗi export PDF', false); console.error(err);
      });
    }
    if(!window.html2canvas || !window.jspdf){
      var p1 = new Promise(function(res, rej){ var s=document.createElement('script'); s.src='https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js'; s.onload=res; s.onerror=rej; document.head.appendChild(s); });
      var p2 = new Promise(function(res, rej){ var s=document.createElement('script'); s.src='https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js'; s.onload=res; s.onerror=rej; document.head.appendChild(s); });
      Promise.all([p1,p2]).then(doExport).catch(function(){ btnExport.innerHTML=origText; btnExport.disabled=false; toast('Lỗi tải thư viện PDF', false); });
    } else doExport();
  });

  fillMonth(validMonthSel); fillMonth(metricMonthSel); fillMonth(reopenMonthSel);
  if(validMonthSel) validMonthSel.addEventListener('change', renderValid);
  if(metricMonthSel) metricMonthSel.addEventListener('change', renderMetric);
  if(reopenMonthSel) reopenMonthSel.addEventListener('change', renderReopen);
  renderCrossMetrics();
  renderValid(); renderMetric(); renderReopen();
})();

// ===== Quản lý Test Case (#157 / epic #151) — controller TRONG IIFE ngoài cùng =====
// Guard #tcBody: chỉ chạy ở trang /test-cases. Data từ #tcData (rỗng tới #152).
(function(){
  var body = $('tcBody'); if(!body) return;
  var data = readJSON('tcData') || {};
  var folders = data.folders || [];
  var cases = data.cases || [];
  var editable = !!window.QA_TC_EDITABLE;
  var links = readJSON('tcLinks') || {};   // {folderId:{tasks:[...]}} — link bộ ↔ task (#155)
  function tasksOf(fid){ var v=links[fid]; return (v&&v.tasks)||[]; }

  var PRI = { critical:['b-critical','Nghiêm trọng'], high:['b-high','Cao'],
              medium:['b-checking','Trung bình'], low:['b-todo','Thấp'] };
  var RES = { pass:['pass','check_circle','Pass'], fail:['fail','cancel','Fail'],
              impact:['impact','warning','Impact'],
              norun:['norun','remove_circle_outline','Not Run'] };
  function priHtml(p){ var d=PRI[p]; return d ? '<span class="badge '+d[0]+'">'+d[1]+'</span>'
                                              : '<span class="badge b-todo">'+esc(p||'—')+'</span>'; }
  function resHtml(r){ var d=RES[r]||RES.norun;
    return '<span class="tc-result '+d[0]+'"><span class="material-symbols-rounded">'+d[1]+'</span> '+d[2]+'</span>'; }
  function longCell(t){ t=t||''; var n=t.split('\n').length;
    var hint = n>3 ? '<span class="tc-more"><span class="material-symbols-rounded">unfold_more</span>Xem thêm</span>' : '';
    return '<div class="tc-long">'+esc(t)+'</div>'+hint; }

  // ---- Repository panel (folder filter) ----
  var curFolder = '';  // '' = tất cả
  // Folder đang thu gọn (ẩn con). Nhớ qua localStorage để sống sót reload.
  var collapsed = {};
  try { collapsed = JSON.parse(localStorage.getItem('tc-collapsed')||'{}') || {}; } catch(_e){ collapsed = {}; }
  function saveCollapsed(){ try { localStorage.setItem('tc-collapsed', JSON.stringify(collapsed)); } catch(_e){} }
  function toggleCollapse(fid){ if(collapsed[fid]) delete collapsed[fid]; else collapsed[fid]=1; saveCollapsed(); renderTree(); }
  function casesIn(fid){
    if(!fid) return cases;
    var subIds = folders.filter(function(f){ return f.parent_id===fid; }).map(function(f){ return f.id; });
    var allowed = [fid].concat(subIds);
    return cases.filter(function(c){ return allowed.indexOf(c.folder) >= 0; });
  }
  function renderTree(){
    var tree=$('tcTree'); if(!tree) return;
    var html = '<div class="tc-node'+(curFolder===''?' active':'')+'" data-folder="">'
             + '<span class="material-symbols-rounded">folder_open</span> Tất cả dự án'
             + '<span class="tc-node-count">'+cases.length+'</span></div>';
    folders.forEach(function(f){
      html += '<div class="tc-node'+(curFolder===f.id?' active':'')+'" data-folder="'+esc(f.id)+'" style="margin-left:14px">'
            + '<span class="material-symbols-rounded">folder</span> '+esc(f.name||f.id)
            + '<span class="tc-node-count">'+casesIn(f.id).length+'</span></div>';
    });
    tree.innerHTML = html;
    tree.querySelectorAll('.tc-node').forEach(function(n){
      n.addEventListener('click', function(){ curFolder=n.dataset.folder; renderTree(); page=1; render(); });
    });
  }

  // ---- Metric cards (JS tính từ cases hiện hành) ----
  function renderMetrics(){
    var box=$('tcMetrics'); if(!box) return;
    var list=casesIn(curFolder);
    var pass=0,fail=0,run=0;
    list.forEach(function(c){ var r=c.result||'norun';
      if(r==='pass')pass++; else if(r==='fail')fail++; if(r!=='norun')run++; });
    var norun=list.length-run;
    function card(cls,ic,lbl,val){ return '<div class="tc-metric '+cls+'"><div class="ic '+cls+'">'
      +'<span class="material-symbols-rounded">'+ic+'</span></div>'
      +'<div><div class="lbl">'+lbl+'</div><div class="val">'+val+'</div></div></div>'; }
    box.innerHTML = card('total','library_books','Tổng số TC',list.length)
      + card('pass','check_circle','Đã Pass',pass)
      + card('fail','cancel','Failed',fail)
      + card('norun','remove_circle_outline','Not Run',norun);
  }

  // ---- Biểu đồ (#153): donut theo trạng thái + bar theo bộ. Vanilla SVG, palette Atlassian-blue ----
  var RES_ORDER = ['pass','fail','impact','norun'];
  var RES_COLOR = { pass:'#36b37e', fail:'#ff5630', impact:'#ffab00', norun:'#97a0af' };
  var RES_LABEL = { pass:'Pass', fail:'Fail', impact:'Impact', norun:'Not Run' };

  function statusCounts(list){
    var c = { pass:0, fail:0, impact:0, norun:0 };
    list.forEach(function(x){ var r=x.result||'norun'; if(c[r]==null) r='norun'; c[r]++; });
    return c;
  }
  // Donut SVG bằng stroke-dasharray trên <circle> (clockwise từ 12h). total ở giữa.
  function donutSVG(segs, total){
    var size=180, sw=26, r=(size-sw)/2, cx=size/2, cy=size/2, circ=2*Math.PI*r, off=0, parts='';
    if(total>0){
      segs.forEach(function(s){
        if(!s.value) return;
        var len=s.value/total*circ;
        parts += '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="'+s.color+'" '
          + 'stroke-width="'+sw+'" stroke-dasharray="'+len+' '+(circ-len)+'" '
          + 'stroke-dashoffset="'+(-off)+'" transform="rotate(-90 '+cx+' '+cy+')"/>';
        off += len;
      });
    } else {
      parts = '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="var(--outline-variant)" stroke-width="'+sw+'"/>';
    }
    return '<svg class="tc-donut" viewBox="0 0 '+size+' '+size+'" width="'+size+'" height="'+size+'">'+parts
      + '<text x="'+cx+'" y="'+(cy-2)+'" text-anchor="middle" class="tc-donut-num">'+total+'</text>'
      + '<text x="'+cx+'" y="'+(cy+18)+'" text-anchor="middle" class="tc-donut-cap">test case</text></svg>';
  }
  function renderCharts(){
    var box=$('tcCharts'); if(!box) return;
    var list=casesIn(curFolder);
    var sc=statusCounts(list), total=list.length;
    // Donut theo trạng thái + legend
    var segs=RES_ORDER.map(function(k){ return { value:sc[k], color:RES_COLOR[k] }; });
    var legend=RES_ORDER.map(function(k){
      var n=sc[k], pct=total? Math.round(n/total*100):0;
      return '<div class="tc-leg"><span class="tc-leg-dot" style="background:'+RES_COLOR[k]+'"></span>'
        + '<span class="tc-leg-lbl">'+RES_LABEL[k]+'</span>'
        + '<span class="tc-leg-val">'+n+' <span class="tc-leg-pct">('+pct+'%)</span></span></div>';
    }).join('');
    var donutCard = '<div class="tc-chart-card"><div class="tc-chart-title">Phân bố theo trạng thái</div>'
      + '<div class="tc-donut-wrap">'+donutSVG(segs,total)+'<div class="tc-legend">'+legend+'</div></div></div>';

    // Bar ngang theo bộ (folder gốc) — stacked theo trạng thái, so sánh giữa các bộ
    var tops=folders.filter(function(f){ return !f.parent_id; });
    var rows=tops.map(function(f){ return { name:f.name||f.id, list:casesIn(f.id) }; })
                 .filter(function(r){ return r.list.length; })
                 .sort(function(a,b){ return b.list.length-a.list.length; });
    var maxN=rows.reduce(function(m,r){ return Math.max(m,r.list.length); }, 0) || 1;
    var barCard;
    if(!rows.length){
      barCard = '<div class="tc-chart-card"><div class="tc-chart-title">Phân bố theo bộ</div>'
        + '<div class="tc-bar-empty">Chưa có bộ test case nào.</div></div>';
    } else {
      var bars=rows.map(function(r){
        var s=statusCounts(r.list);
        var segHtml=RES_ORDER.map(function(k){
          if(!s[k]) return '';
          return '<span class="tc-bar-seg" style="width:'+(s[k]/r.list.length*100)+'%;background:'
            + RES_COLOR[k]+'" title="'+RES_LABEL[k]+': '+s[k]+'"></span>';
        }).join('');
        return '<div class="tc-bar-row"><div class="tc-bar-name" title="'+esc(r.name)+'">'+esc(r.name)+'</div>'
          + '<div class="tc-bar-track" style="width:'+Math.max(8, r.list.length/maxN*100)+'%">'+segHtml+'</div>'
          + '<div class="tc-bar-n">'+r.list.length+'</div></div>';
      }).join('');
      barCard = '<div class="tc-chart-card"><div class="tc-chart-title">Phân bố theo bộ</div>'
        + '<div class="tc-bars">'+bars+'</div></div>';
    }
    box.innerHTML = donutCard + barCard;
  }

  // ---- Bảng + pagination 10/trang ----
  var PER=10, page=1;
  function render(){
    renderMetrics();
    renderCharts();
    renderLinkBar();
    var list=casesIn(curFolder);
    if(!list.length){
      body.innerHTML = '<tr><td colspan="7"><div class="tc-empty">'
        + '<span class="material-symbols-rounded">checklist</span>'
        + (editable ? 'Chưa có test case. Bấm <b>Import</b> để nhập từ Google Sheet.'
                    : 'Chưa có test case nào trong bộ này.')
        + '</div></td></tr>';
      $('tcPager').style.display='none';
      return;
    }
    var pages=Math.ceil(list.length/PER); if(page>pages)page=pages; if(page<1)page=1;
    var slice=list.slice((page-1)*PER, page*PER);
    body.innerHTML = slice.map(function(c,i){
      return '<tr data-idx="'+((page-1)*PER+i)+'">'
        + '<td class="tc-id"><div>'+esc(c.id||'')+'</div></td>'
        + '<td class="tc-item"><div>'+esc(c.item||'')+'</div></td>'
        + '<td>'+longCell(c.pre)+'</td>'
        + '<td>'+longCell(c.step)+'</td>'
        + '<td>'+longCell(c.exp)+'</td>'
        + '<td>'+priHtml(c.priority)+'</td>'
        + '<td>'+resHtml(c.result)+'</td></tr>';
    }).join('');
    // filler rows giữ chiều cao bảng cố định khi trang cuối thiếu dòng
    var fillerHtml='<tr class="tc-filler"><td class="tc-id">&nbsp;</td><td class="tc-item">&nbsp;</td>'
      + '<td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>';
    var filler=''; for(var f=slice.length; f<PER; f++) filler+=fillerHtml;
    body.insertAdjacentHTML('beforeend', filler);
    body.querySelectorAll('tr[data-idx]').forEach(function(tr){
      tr.style.cursor='pointer';
      tr.addEventListener('click', function(){ openDrawer(list[+tr.dataset.idx]); });
    });
    // pager
    var pg=$('tcPager'); pg.style.display='';
    var from=(page-1)*PER+1, to=Math.min(page*PER, list.length);
    $('tcPagerInfo').textContent='Hiển thị '+from+'–'+to+' trong '+list.length+' test case';
    var nav=$('tcPagerNav'); nav.innerHTML='';
    function btn(label,disabled,goto,active){
      var b=document.createElement('button');
      b.className = active ? 'pager-page active' : (label.indexOf('chevron')>=0 ? 'pager-btn' : 'pager-page');
      b.innerHTML = label.indexOf('chevron')>=0 ? '<span class="material-symbols-rounded mi-sm">'+label+'</span>' : label;
      b.disabled=!!disabled;
      if(!disabled && goto) b.addEventListener('click',function(){ page=goto; render(); });
      nav.appendChild(b);
    }
    function ellipsis(){ var s=document.createElement('span'); s.className='pager-ellipsis'; s.textContent='…'; nav.appendChild(s); }
    btn('chevron_left', page<=1, page-1);
    var win=1, last=0; // luôn hiện trang 1, trang cuối, và current ± win
    for(var p=1;p<=pages;p++){
      if(p===1 || p===pages || (p>=page-win && p<=page+win)){
        if(last && p-last>1) ellipsis();
        btn(String(p), false, p, p===page);
        last=p;
      }
    }
    btn('chevron_right', page>=pages, page+1);
  }

  // ---- Drawer chi tiết (full Pre/Step/Expected) ----
  var dov=$('tcDrawerOv'), dr=$('tcDrawer');
  function field(ic,lbl,val,mono){ return '<div class="tc-d-field"><div class="tc-d-label">'
    +'<span class="material-symbols-rounded">'+ic+'</span>'+lbl+'</div>'
    +'<div class="tc-d-box'+(mono?' mono':'')+'">'+esc(val||'—')+'</div></div>'; }
  function openDrawer(c){
    $('tcdKey').textContent=c.id||'';
    $('tcdBody').innerHTML = '<h2>'+esc(c.item||'')+'</h2>'
      + '<div class="tc-d-meta">'+priHtml(c.priority)+' '+resHtml(c.result)+'</div>'
      + field('fact_check','Pre-Condition',c.pre,true)
      + field('format_list_numbered','Step',c.step)
      + field('task_alt','Expected Output',c.exp);
    dov.classList.add('open'); dr.classList.add('open');
  }
  function closeDrawer(){ dov.classList.remove('open'); dr.classList.remove('open'); }
  if(dov) dov.addEventListener('click', closeDrawer);
  if($('tcdClose')) $('tcdClose').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeDrawer(); });

  // ---- Modal Import (Drive: dán link -> chọn sheet -> chọn folder -> ghi đè) #152 ----
  var imp=$('tcImportOverlay');
  var urlIn=$('tcImpUrl'), sheetSel=$('tcImpSheet'), folderSel=$('tcImpFolder'),
      submitBtn=$('tcImpSubmit');
  var lastSheetUrl='';   // tránh fetch lại sheet khi url không đổi
  window.tcCloseImport=function(){ if(imp) imp.classList.remove('open'); };
  // Modal báo lỗi (button OK) — dùng cho import thiếu ID, v.v.
  window.tcCloseError=function(){ var ov=$('tcErrorOverlay'); if(ov) ov.classList.remove('open'); };
  window.tcShowError=function(msg, title){
    var ov=$('tcErrorOverlay'); if(!ov){ toast(msg, false); return; }
    var m=$('tcErrorMsg'); if(m) m.textContent=msg||'Có lỗi xảy ra';
    var t=$('tcErrorTitle'); if(t) t.textContent=title||'Có lỗi xảy ra';
    ov.classList.add('open');
    var ok=$('tcErrorOk'); if(ok) { ok.focus(); ok.onclick = window.tcCloseError; }
  };
  window.tcShowSuccess=function(msg, title){
    var ov=$('tcErrorOverlay'); if(!ov){ toast(msg, true); return; }
    var m=$('tcErrorMsg'); if(m) m.innerHTML='<span style="color:var(--success); white-space:pre-wrap;">'+esc(msg||'Thành công')+'</span>';
    var t=$('tcErrorTitle'); if(t) t.textContent=title||'Thành công';
    ov.classList.add('open');
    var ok=$('tcErrorOk'); 
    if(ok) {
        ok.focus();
        ok.onclick = function() { location.reload(); };
    }
  };
  function doTcSync(fid){
    if(!editable) return;
    toast('Đang đồng bộ từ Google Sheets...', true);
    postJSON('/tc-sync', { folder: fid }, 60000).then(function(res){
      if(res && res.ok){
        window.tcShowSuccess(res.msg || 'Đồng bộ thành công.', 'Đồng bộ thành công');
      } else {
        window.tcShowError((res && res.msg) || 'Lỗi đồng bộ.', 'Đồng bộ thất bại');
      }
    }).catch(function(){ window.tcShowError('Lỗi mạng khi đồng bộ.', 'Đồng bộ thất bại'); });
  }

  function fillFolderSel(){
    if(!folderSel) return;
    var tops = folders.filter(function(f){ return !f.parent_id; });
    var opts = '<option value="">Chọn thư mục...</option>';
    tops.forEach(function(f){
      opts += '<option value="'+esc(f.id)+'">'+esc(f.name||f.id)+'</option>';
    });

    folderSel.innerHTML = opts;
  }
  function resetSheetSel(msg){
    if(sheetSel) sheetSel.innerHTML='<option value="">'+(msg||'Chọn một trang...')+'</option>';
  }
  function loadSheets(){
    var u=(urlIn&&urlIn.value||'').trim();
    if(!u){ resetSheetSel(); lastSheetUrl=''; return; }
    if(u===lastSheetUrl) return;
    lastSheetUrl=u; resetSheetSel('Đang tải...');
    getJSON('/tc-sheets?url='+encodeURIComponent(u)).then(function(j){
      if(!j||!j.ok){ resetSheetSel('Lỗi'); toast((j&&j.msg)||'Không đọc được file Drive', false); lastSheetUrl=''; return; }
      var sheets=j.sheets||[];
      if(!sheets.length){ resetSheetSel('Không có sheet'); return; }
      sheetSel.innerHTML='<option value="">Tất cả sheet (bỏ qua template)</option>'
        + sheets.map(function(s){ return '<option value="'+esc(s)+'">'+esc(s)+'</option>'; }).join('');
      if(sheets.length===1){ sheetSel.value=sheets[0]; }
    }).catch(function(){ resetSheetSel('Lỗi'); toast('Lỗi mạng khi đọc file Drive', false); lastSheetUrl=''; });
  }
  if(urlIn){ urlIn.addEventListener('change', loadSheets);
    urlIn.addEventListener('blur', loadSheets); }
  if($('tcImportBtn')) $('tcImportBtn').addEventListener('click', function(){
    if(!imp) return; fillFolderSel(); imp.classList.add('open');
    lastSheetUrl = '';
    loadSheets();
    if(urlIn) urlIn.focus(); });
  if(submitBtn) submitBtn.addEventListener('click', function(){
    var u=(urlIn&&urlIn.value||'').trim();
    var sheet=(sheetSel&&sheetSel.value||'').trim();
    var folder=(folderSel&&folderSel.value||'').trim();
    if(!u){ toast('Chưa dán link Google Sheet', false); return; }
    if(!folder){ toast('Chưa chọn folder đích', false); return; }
    // sheet rỗng = import cả file (bỏ qua sheet template) — backend lo phần này
    var hasCases = cases.some(function(c){ return c.folder===folder; });
    if(hasCases && !confirm('Bộ này đã có test case. Import sẽ GHI ĐÈ toàn bộ (kết quả chạy '
        +'theo ID được giữ lại). Tiếp tục?')) return;
    submitBtn.disabled=true;
    postJSON('/tc-import', { url:u, sheet:sheet, folder:folder }, 60000).then(function(j){
      submitBtn.disabled=false;
      if(j&&j.ok){ toast(j.msg||'Import thành công', true); window.tcCloseImport();
        setTimeout(function(){ location.reload(); }, 600); }
      else { window.tcShowError((j&&j.msg)||'Import thất bại',
               (j&&j.missing_id_rows)?'Thiếu ID — không thể import':'Import thất bại'); }
    }).catch(function(){ submitBtn.disabled=false; toast('Lỗi mạng khi import', false); });
  });

  // ---- Modal tạo thư mục (lưu thật qua /tc-add-folder, /tc-rename-folder) #152 ----
  var fov=$('tcFolderOverlay');
  window.tcCloseFolder=function(){ if(fov) fov.classList.remove('open'); };
  if($('tcAddFolder')) $('tcAddFolder').addEventListener('click', function(){
    if(!fov) return;
    var inp=$('tcFolderName'); if(inp) inp.value='';
    var saveBtn=$('tcFolderSave');
    if(saveBtn) { saveBtn.textContent='Tạo'; saveBtn.removeAttribute('data-edit-id'); }
    var titleEl=fov.querySelector('.modal-head h3');
    if(titleEl) titleEl.textContent='Thêm bộ / thư mục';
    fov.classList.add('open');
    if(inp) inp.focus(); });
  if($('tcFolderSave')) $('tcFolderSave').addEventListener('click', function(){
    var btn=$('tcFolderSave');
    var name=(($('tcFolderName')||{}).value||'').trim();
    if(!name){ toast('Chưa nhập tên thư mục', false); return; }
    var editId = btn.getAttribute('data-edit-id');
    btn.disabled=true;
    if(editId) {
      postJSON('/tc-rename-folder', { id: editId, name: name }).then(function(j){
        btn.disabled=false;
        if(j&&j.ok){ folders=j.folders||folders; window.tcCloseFolder();
          renderTree(); fillFolderSel(); toast('Đã đổi tên thư mục', true); }
        else { toast((j&&j.msg)||'Không đổi được tên', false); }
      }).catch(function(){ btn.disabled=false; toast('Lỗi mạng khi lưu', false); });
    } else {
      postJSON('/tc-add-folder', { name:name }).then(function(j){
        btn.disabled=false;
        if(j&&j.ok){ folders=j.folders||folders; window.tcCloseFolder();
          renderTree(); fillFolderSel(); toast('Đã thêm "'+name+'"', true); }
        else { toast((j&&j.msg)||'Không thêm được thư mục', false); }
      }).catch(function(){ btn.disabled=false; toast('Lỗi mạng khi lưu', false); });
    }
  });

  // ---- Rename / Delete folder (context menu trên mỗi folder) ----
  function renameFolder(fid){
    var f = null;
    for(var i=0; i<folders.length; i++){ if(folders[i].id===fid){ f=folders[i]; break; } }
    if(!f || !fov) return;
    var inp=$('tcFolderName'); if(inp) inp.value=f.name;
    var saveBtn=$('tcFolderSave');
    if(saveBtn) { saveBtn.textContent='Lưu'; saveBtn.setAttribute('data-edit-id', fid); }
    var titleEl=fov.querySelector('.modal-head h3');
    if(titleEl) titleEl.textContent='Đổi tên thư mục';
    fov.classList.add('open');
    if(inp) { inp.focus(); inp.select(); }
  }

  function deleteFolder(fid){
    var f = null;
    for(var i=0; i<folders.length; i++){ if(folders[i].id===fid){ f=folders[i]; break; } }
    if(!f) return;
    var cnt = casesIn(fid).length;
    var msg = 'Bạn có chắc chắn muốn xoá thư mục "'+f.name+'"?';
    if(cnt > 0) msg += '\n\n⚠ Có '+cnt+' test case trong thư mục này cũng sẽ bị XOÁ VĨNH VIỄN!';
    if(!confirm(msg)) return;
    postJSON('/tc-delete-folder', { id: fid }).then(function(j){
      if(j&&j.ok){
        folders=j.folders||folders;
        cases=cases.filter(function(c){ return c.folder!==fid; });
        if(curFolder===fid) curFolder='';
        renderTree(); page=1; render(); fillFolderSel();
        toast('Đã xoá thư mục', true);
      } else { toast((j&&j.msg)||'Không xoá được thư mục', false); }
    }).catch(function(){ toast('Lỗi mạng khi xoá', false); });
  }

  var _origRenderTree = renderTree;
  renderTree = function(){
    var tree=$('tcTree'); if(!tree) return;
    var html = '<div class="tc-node'+(curFolder===''?' active':'')+'" data-folder="">'+
               '<span class="tc-twisty spacer"></span>'+
               '<span class="material-symbols-rounded">folder_open</span> Tất cả dự án'+
               '<span class="tc-node-count">'+cases.length+'</span></div>';
    
    var tops = folders.filter(function(f){ return !f.parent_id; });
    var subsByParent = {};
    folders.forEach(function(f){
      if(f.parent_id) {
        subsByParent[f.parent_id] = subsByParent[f.parent_id] || [];
        subsByParent[f.parent_id].push(f);
      }
    });

    function renderNode(f, depth){
      var actions = '';
      if(editable){
        var renBtn = depth === 0 ? '<button class="tc-fa-btn" data-action="rename" data-fid="'+esc(f.id)+'" title="Đổi tên"><span class="material-symbols-rounded mi-xs">edit</span></button>' : '';
        var syncBtn = (data.imports && data.imports[f.id]) ? '<button class="tc-fa-btn" data-action="sync" data-fid="'+esc(f.id)+'" title="Đồng bộ lại từ Google Sheets"><span class="material-symbols-rounded mi-xs">sync</span></button>' : '';
        actions = '<span class="tc-folder-actions">'
          + syncBtn
          + renBtn
          + '<button class="tc-fa-btn danger" data-action="delete" data-fid="'+esc(f.id)+'" title="Xoá"><span class="material-symbols-rounded mi-xs">delete</span></button>'
          + '</span>';
      }
      var children = subsByParent[f.id] || [];
      var hasKids = children.length > 0;
      var isCol = !!collapsed[f.id];
      // Nút thu gọn/mở (chỉ folder có con); folder không con -> spacer giữ thẳng hàng.
      var twisty = hasKids
        ? '<button class="tc-twisty" data-twisty="'+esc(f.id)+'" title="'+(isCol?'Mở':'Thu gọn')+'">'
          + '<span class="material-symbols-rounded mi-sm">'+(isCol?'chevron_right':'expand_more')+'</span></button>'
        : '<span class="tc-twisty spacer"></span>';
      var ml = 14 + (depth * 16);
      var ic = depth > 0 ? 'subdirectory_arrow_right' : 'folder';
      html += '<div class="tc-node'+(curFolder===f.id?' active':'')+'" data-folder="'+esc(f.id)+'" style="margin-left:'+ml+'px">'+
              twisty+
              '<span class="material-symbols-rounded">'+ic+'</span> '+
              '<span style="flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="'+esc(f.name||f.id)+'">'+esc(f.name||f.id)+'</span>'+
              '<span class="tc-node-count">'+casesIn(f.id).length+'</span>'+
              actions+'</div>';

      if(isCol) return;   // thu gọn -> ẩn cây con
      children.forEach(function(c){ renderNode(c, depth + 1); });
    }

    tops.forEach(function(f){ renderNode(f, 0); });

    // Các folder con mồ côi (nếu lỡ bị lỗi data)
    var allTopIds = tops.map(function(t){ return t.id; });
    folders.forEach(function(f){
      if(f.parent_id && allTopIds.indexOf(f.parent_id) === -1 && (!subsByParent[f.parent_id] || subsByParent[f.parent_id].indexOf(f) >= 0)){
         renderNode(f, 0); // render nó như top nếu mất cha
         subsByParent[f.parent_id] = []; // xoá để tránh lặp
      }
    });

    tree.innerHTML = html;
    tree.querySelectorAll('.tc-node').forEach(function(n){
      n.addEventListener('click', function(e){
        if(e.target.closest('.tc-fa-btn')) return;
        if(e.target.closest('.tc-twisty')) return;   // bấm chevron = thu gọn, không đổi folder
        curFolder=n.dataset.folder; renderTree(); page=1; render();
      });
    });
    tree.querySelectorAll('.tc-twisty[data-twisty]').forEach(function(btn){
      btn.addEventListener('click', function(e){
        e.stopPropagation();
        toggleCollapse(btn.getAttribute('data-twisty'));
      });
    });
    tree.querySelectorAll('.tc-fa-btn').forEach(function(btn){
      btn.addEventListener('click', function(e){
        e.stopPropagation();
        var action = btn.getAttribute('data-action');
        var fid = btn.getAttribute('data-fid');
        if(action==='rename') renameFolder(fid);
        else if(action==='delete') deleteFolder(fid);
        else if(action==='sync') doTcSync(fid);
      });
    });
  };

  // ---- Liên kết bộ ↔ task Jira (#155): link bar + modal type-ahead ----
  function isSubFolder(fid){
    if(!fid) return false;
    for(var i=0;i<folders.length;i++){ if(folders[i].id===fid) return !!folders[i].parent_id; }
    return false;
  }
  function folderName(fid){
    for(var i=0;i<folders.length;i++){ if(folders[i].id===fid) return folders[i].name||fid; }
    return fid;
  }
  function taskChip(fid, key){
    var rm = editable ? '<button class="tc-task-x" data-rm="'+esc(key)+'" title="Gỡ link">'
      +'<span class="material-symbols-rounded mi-xs">close</span></button>' : '';
    return '<span class="tc-task-chip"><a class="tc-task-key" data-key="'+esc(key)+'" href="'
      +(window.__jiraBase||'')+'/browse/'+encodeURIComponent(key)+'">'+esc(key)+'</a>'+rm+'</span>';
  }
  function renderLinkBar(){
    var bar=$('tcLinkBar'); if(!bar) return;
    // CHỈ hiện khi chọn sub-folder — mỗi sub-folder = 1 bộ test viết khi nhận task
    // nên link theo sub-folder. Folder gốc / "Tất cả" không link (#155).
    if(!isSubFolder(curFolder)){ bar.style.display='none'; return; }
    bar.style.display='';
    var ts=tasksOf(curFolder);
    var chips = ts.length ? ts.map(function(k){ return taskChip(curFolder,k); }).join('')
                          : '<span class="tc-link-none">Chưa liên kết task nào.</span>';
    var btn = editable ? '<button class="tc-link-add" id="tcLinkAdd">'
      +'<span class="material-symbols-rounded mi-sm">add_link</span> Liên kết task</button>' : '';
    bar.innerHTML = '<span class="tc-link-lbl"><span class="material-symbols-rounded mi-sm">link</span> '
      +'Task Jira của <b>'+esc(folderName(curFolder))+'</b>:</span>'
      +'<span class="tc-link-tasks">'+chips+'</span>'+btn;
    var add=$('tcLinkAdd'); if(add) add.addEventListener('click', openLinkModal);
    // chip: click key -> mở drawer/Jira; click ✕ -> gỡ link
    bar.querySelectorAll('.tc-task-key').forEach(function(a){
      a.addEventListener('click', function(e){
        if(window.__openDetail){ e.preventDefault(); window.__openDetail(a.getAttribute('data-key')); } });
    });
    bar.querySelectorAll('.tc-task-x').forEach(function(b){
      b.addEventListener('click', function(){ unlinkTask(curFolder, b.getAttribute('data-rm')); }); });
  }

  function persistLink(fid, task, op){
    return postJSON('/tc-link-task', { folder:fid, task:task, op:op }).then(function(j){
      if(j&&j.ok){ if(j.tasks&&j.tasks.length) links[fid]={tasks:j.tasks};
                   else delete links[fid];
                   renderLinkBar(); renderLinkChips(); return true; }
      toast((j&&j.msg)||'Không lưu được liên kết', false); return false;
    }).catch(function(){ toast('Lỗi mạng khi lưu liên kết', false); return false; });
  }
  function unlinkTask(fid, key){ persistLink(fid, key, 'remove').then(function(ok){
    if(ok) toast('Đã gỡ '+key, true); }); }

  // ---- Modal type-ahead tìm task ----
  var lov=$('tcLinkOverlay'), lsearch=$('tcLinkSearch'), lresults=$('tcLinkResults');
  var linkFid='';
  window.tcCloseLink=function(){ if(lov) lov.classList.remove('open'); };
  function openLinkModal(){
    if(!lov) return; linkFid=curFolder;
    var fn=$('tcLinkFolderName'); if(fn) fn.textContent=folderName(linkFid);
    if(lsearch) lsearch.value=''; if(lresults) lresults.innerHTML='';
    renderLinkChips(); lov.classList.add('open'); if(lsearch) lsearch.focus();
  }
  function renderLinkChips(){
    var box=$('tcLinkChips'); if(!box) return;
    var ts=tasksOf(linkFid);
    box.innerHTML = ts.length ? ts.map(function(k){ return taskChip(linkFid,k); }).join('')
                              : '<span class="tc-link-none">Chưa liên kết task nào.</span>';
    box.querySelectorAll('.tc-task-x').forEach(function(b){
      b.addEventListener('click', function(){ unlinkTask(linkFid, b.getAttribute('data-rm')); }); });
    box.querySelectorAll('.tc-task-key').forEach(function(a){
      a.addEventListener('click', function(e){ e.preventDefault();
        window.open(a.getAttribute('href'), '_blank'); }); });
  }
  if(lsearch){
    var lseq=0, ldeb;
    lsearch.addEventListener('input', function(){
      var q=(lsearch.value||'').trim(); clearTimeout(ldeb);
      // Hỗ trợ paste nhiều task cùng lúc (VD: "TASK-1, TASK-2")
      var multi = q.split(/[\s,;]+/).filter(function(x){ return /^[A-Za-z]+-\d+$/.test(x); });
      if(multi.length > 1 || (multi.length === 1 && /[,;]/.test(q))){
        var newTasks = multi.filter(function(k){ return tasksOf(linkFid).indexOf(k) < 0; });
        if(newTasks.length){
          persistLink(linkFid, newTasks, 'add').then(function(ok){
            if(ok){ toast('Đã liên kết ' + newTasks.length + ' task', true); }
          });
        }
        lsearch.value=''; lresults.innerHTML='';
        return;
      }

      if(q.length<2){ lresults.innerHTML=''; return; }
      ldeb=setTimeout(function(){
        var my=++lseq; lresults.innerHTML='<div class="tc-link-loading">Đang tìm…</div>';
        getJSON('/global-search?q='+encodeURIComponent(q), 15000).then(function(j){
          if(my!==lseq) return;
          var rs=(j&&j.ok&&j.results)||[];
          if(!rs.length){ lresults.innerHTML='<div class="tc-link-loading">Không tìm thấy task</div>'; return; }
          lresults.innerHTML=rs.map(function(r){
            var linked=tasksOf(linkFid).indexOf(r.key)>=0;
            return '<div class="tc-link-res'+(linked?' linked':'')+'" data-key="'+esc(r.key)+'">'
              +'<span class="tc-link-res-key">'+esc(r.key)+'</span>'
              +'<span class="tc-link-res-sum">'+esc(r.summary||'')+'</span>'
              +(linked?'<span class="material-symbols-rounded mi-sm">check</span>'
                      :'<span class="material-symbols-rounded mi-sm">add</span>')+'</div>';
          }).join('');
          lresults.querySelectorAll('.tc-link-res').forEach(function(el){
            el.addEventListener('click', function(){
              var key=el.getAttribute('data-key');
              if(tasksOf(linkFid).indexOf(key)>=0) return;   // đã link
              persistLink(linkFid, key, 'add').then(function(ok){
                if(ok){ toast('Đã liên kết '+key, true);
                  el.classList.add('linked');
                  el.querySelector('.material-symbols-rounded').textContent='check'; } });
            });
          });
        }).catch(function(){ if(my!==lseq) return;
          lresults.innerHTML='<div class="tc-link-loading">Lỗi tìm kiếm</div>'; });
      }, 300);
    });
  }
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') window.tcCloseLink(); });

  // Deep-link ?folder=<id> (từ drawer task "Bộ test case liên quan", #155)
  try {
    var pf=new URLSearchParams(location.search).get('folder');
    if(pf && folders.some(function(f){ return f.id===pf; })) curFolder=pf;
  } catch(e){}

  renderTree(); render();
})();

})();   // ===== đóng IIFE ngoài cùng (shared scope) — bug-metrics block nằm TRONG để dùng $/esc/readJSON
