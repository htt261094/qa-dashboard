/* ===== QA Suite UI v2 — JS shell (dashboard QA + roadmap). Inline qua _document_v2. ===== */
/* Phần shared chạy mọi trang; dashboard guard #rows; roadmap guard #rmList2. Endpoint thật. */
(function(){
'use strict';

// ---------- helpers ----------
function esc(s){ return (s==null?'':String(s))
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function $(id){ return document.getElementById(id); }
function readJSON(id){ var el=$(id); if(!el) return null; try{ return JSON.parse(el.textContent); }catch(e){ return null; } }
function postJSON(url, body, ms){
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

// ---------- toast ----------
var toastT;
function toast(msg, ok){ var el=$('toast'); if(!el) return; el.textContent=msg;
  el.className = 'toast show' + (ok===false?' err':'');
  clearTimeout(toastT); toastT=setTimeout(function(){ el.className='toast'; }, 2200); }

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
  function open(){ ov.classList.add('open'); var m=$('pmenu'); if(m) m.classList.remove('open'); }
  function close(){ ov.classList.remove('open'); }
  var s=$('pmSettings'); if(s) s.addEventListener('click', open);
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
      case 'custom_status': return w+' gắn nhãn '+k+': '+esc(n.new||'');
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
      if(curPill==='todo') return t.jira==='TO DO' && !t.isNew && !t.overdue;
      if(curPill==='progress') return (t.jira==='In Progress'||t.jira==='PENDING') && !t.stuck && !t.overdue;
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
          +esc(custMap[v]||v)+'</span>'; }).join('')+'</div>';
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
          +'<td><span class="badge '+badgeCls(t.jira)+'">'+esc(t.jira)+'</span>'+chipHTML(t)+'</td>'
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
    }

    function updateCounts(){
      var counts={todo:0,progress:0,'new':0,stuck:0,overdue:0,done:0};
      TASKS.forEach(function(t){
        if(!memberMatch(t)||!searchMatch(t)) return;
        if(t.isNew) counts['new']++;
        if(t.overdue) counts.overdue++;
        if(t.stuck) counts.stuck++;
        if(t.jira==='TO DO' && !t.isNew && !t.overdue) counts.todo++;
        if((t.jira==='In Progress'||t.jira==='PENDING') && !t.stuck && !t.overdue) counts.progress++;
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
    var a=e.target.closest('[data-act]'); if(!a) return;
    var act=a.getAttribute('data-act'), key=a.getAttribute('data-key');
    if(act==='smenu'){ e.stopPropagation(); openStatusMenu(a); }
    else if(act==='detail'){ openDetail(key); }
    else if(act==='cmt'){ toggleCmt(key); }
    else if(act==='cmt-close'){ toggleCmt(key); }
    else if(act==='cmt-send'){ sendComment(key); }
    if(a.classList.contains('rm') && a.getAttribute('data-val')!=null){ rmCust(key, a.getAttribute('data-val')); }
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
  function jiraCls(v){ v=(v||'').toUpperCase();
    if(v==='DONE') return 'b-done'; if(v==='CANCELLED') return 'b-critical';
    if(v==='IN PROGRESS') return 'b-checking'; if(v==='PENDING') return 'b-blocked';
    if(v==='TO DO') return 'b-todo'; return 'b-todo'; }
  function synth(key, d){
    return { key:key, summary:d.summary||key, jira:d.status||'',
      assignee:{ name:d.assignee||'—', init:initOf(d.assignee||'?'), cls:avById(d.assignee||'?') },
      dueDisp:d.duedate||'Chưa đặt hạn',
      jiraUrl:(window.__jiraBase||'')+'/browse/'+key };
  }
  function renderDrawer(t){
    var list=COMMENTS[t.key], hist;
    if(list==null) hist='<div class="cmt-empty">Đang tải…</div>';
    else if(!list.length) hist='<div class="cmt-empty">Chưa có bình luận nào</div>';
    else hist=list.map(function(c){ return '<div class="cmt-item"><span class="av '+avById(c.author)+'">'+esc(initOf(c.author))+'</span>'
      +'<div class="cmt-main"><div class="cmt-meta"><b>'+esc(c.author)+'</b><span>'+esc((c.when||'').slice(0,16).replace('T',' '))+'</span></div>'
      +'<div class="cmt-text">'+esc(c.body)+'</div></div></div>'; }).join('');
    var desc=(DETAIL[t.key]&&DETAIL[t.key].description)?esc(DETAIL[t.key].description):esc(t.summary);
    drawer.innerHTML='<div class="drawer-head"><a class="key" href="'+esc(t.jiraUrl)+'" target="_blank">'+esc(t.key)+'</a>'
      +'<span class="badge '+jiraCls(t.jira)+'">'+esc(t.jira)+'</span>'
      +'<button class="x material-symbols-rounded" data-act="drawer-close">close</button></div>'
      +'<div class="drawer-body"><h2>'+esc(t.summary)+'</h2>'
      +'<div class="dt-grid"><div class="lbl">Người xử lý</div><div class="val"><span class="assignee"><span class="av '+esc(t.assignee.cls)+'">'+esc(t.assignee.init)+'</span> '+esc(t.assignee.name)+'</span></div>'
      +'<div class="lbl">Ngày tạo</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].created)?esc(DETAIL[t.key].created):'—')+'</div>'
      +'<div class="lbl">Hạn chót</div><div class="val"><span class="due">'+esc(t.dueDisp)+'</span></div>'
      +'<div class="lbl">Cập nhật</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].updated)?esc(DETAIL[t.key].updated):'—')+'</div>'
      +'<div class="lbl">Dev phụ trách</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].devs&&DETAIL[t.key].devs.length)?DETAIL[t.key].devs.map(esc).join(', '):'—')+'</div></div>'
      +'<div class="dt-sec-title">Mô tả</div><div class="dt-desc">'+desc+'</div>'
      +bugSectionHtml(DETAIL[t.key])
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
  var EDIT = !!META.editable;
  var STATUS_OPTS = META.statuses || [['planned','Planned'],['in_progress','In Progress'],['done','Done'],['blocked','Blocked']];
  var PEOPLE = META.people || [];
  var STLABEL={}; STATUS_OPTS.forEach(function(s){ STLABEL[s[0]]=s[1]; });
  var STCLS={done:'s-done', in_progress:'s-prog', planned:'s-plan', blocked:'s-block'};
  var curFilter='all', saveT=null;

  function uid(p){ return p+Date.now().toString(36)+Math.floor(Math.random()*1e4); }
  function planById(id){ return PLANS.filter(function(p){ return p.id===id; })[0]; }
  function taskById(p,tid){ return (p.tasks||[]).filter(function(t){ return t.id===tid; })[0]; }
  function subById(t,sid){ return (t.subs||[]).filter(function(s){ return s.id===sid; })[0]; }
  function taskDone(t){ return (t.subs&&t.subs.length)?t.subs.every(function(s){return s.done;}):!!t.done; }
  function taskStarted(t){ return (t.subs&&t.subs.length)?t.subs.some(function(s){return s.done;}):!!t.done; }
  function planStatus(p){ if(!p.tasks||!p.tasks.length) return p.status||'planned';
    if(p.tasks.every(taskDone)) return 'done';
    if(p.tasks.some(function(t){ return taskStarted(t)||taskDone(t); })) return 'in_progress'; return 'planned'; }
  function planFrac(p){ if(!p.tasks||!p.tasks.length) return null;
    var d=p.tasks.filter(taskDone).length; return {done:d, total:p.tasks.length, pct:Math.round(d/p.tasks.length*100)}; }
  function taskFrac(t){ if(!t.subs||!t.subs.length) return null;
    var d=t.subs.filter(function(s){return s.done;}).length; return {done:d, total:t.subs.length, pct:Math.round(d/t.subs.length*100)}; }

  function dParts(due){ if(!due) return {m:'--', d:'--', disp:'Chưa đặt hạn', over:false};
    var dt=new Date(due+'T00:00:00'); if(isNaN(dt.getTime())) return {m:'--', d:'--', disp:esc(due), over:false};
    var dd=('0'+dt.getDate()).slice(-2), mm=('0'+(dt.getMonth()+1)).slice(-2);
    var today=new Date(); today.setHours(0,0,0,0);
    return {m:'Thg '+(dt.getMonth()+1), d:dd, disp:dd+'/'+mm+'/'+dt.getFullYear(), over: dt<today}; }

  function save(){ if(!EDIT) return; clearTimeout(saveT); var st=$('rmStatus');
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
      +'<div class="rm-subs">'+subs+subadd+'</div></div>';
  }
  function subHTML(p,t,s){
    var ic=s.done?'check_box':'check_box_outline_blank';
    var mini= EDIT?'<div class="rm-tmini"><button data-rm="edit-sub" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'" data-s="'+esc(s.id)+'"><span class="material-symbols-rounded mi-xs">edit</span></button>'
      +'<button class="del" data-rm="del-sub" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'" data-s="'+esc(s.id)+'"><span class="material-symbols-rounded mi-xs">close</span></button></div>':'';
    return '<div class="rm-sub'+(s.done?' done':'')+'"><div class="rm-sub-left">'
      +'<span class="rm-chk '+(s.done?'on':'off')+'" data-rm="toggle-sub" data-p="'+esc(p.id)+'" data-t="'+esc(t.id)+'" data-s="'+esc(s.id)+'"><span class="material-symbols-rounded mi-sm">'+ic+'</span></span>'
      +'<span class="rm-sub-name">'+esc(s.title)+'</span></div>'+mini+'</div>';
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
      {key:'pic',label:'Người xử lý',type:'select',value:PEOPLE[0]||'',options:peopleOpts} ],
      onSave:function(v){ if(!v.title) return 'Cần nhập tên task';
        p.tasks=p.tasks||[]; p.tasks.push({id:uid('t'), title:v.title, pic:v.pic||'', done:false, subs:[]});
        p.open=true; render(); save(); toast('Đã thêm task', true); } }); }
  function editTask(pid,tid){ var p=planById(pid), t=taskById(p,tid); if(!t) return;
    openModal({ icon:'edit', title:'Sửa Task', fields:[
      {key:'title',label:'Tên task',type:'text',value:t.title},
      {key:'pic',label:'Người xử lý',type:'select',value:t.pic,options:peopleOpts} ],
      onSave:function(v){ if(!v.title) return 'Cần nhập tên task';
        t.title=v.title; t.pic=v.pic; render(); save(); toast('Đã cập nhật', true); } }); }
  function delTask(pid,tid){ var p=planById(pid), t=taskById(p,tid); if(!t) return;
    if(!confirm('Xoá task "'+t.title+'"?')) return;
    p.tasks=p.tasks.filter(function(x){ return x.id!==tid; }); render(); save(); toast('Đã xoá', true); }
  function addSub(pid,tid){ var p=planById(pid), t=taskById(p,tid); if(!t) return;
    openModal({ icon:'add', title:'Thêm Sub-task', saveLabel:'Tạo', fields:[
      {key:'title',label:'Tên sub-task',type:'text',placeholder:'VD: Cập nhật config'} ],
      onSave:function(v){ if(!v.title) return 'Cần nhập tên sub-task';
        t.subs=t.subs||[]; t.subs.push({id:uid('s'), title:v.title, done:false}); render(); save(); toast('Đã thêm sub-task', true); } }); }
  function editSub(pid,tid,sid){ var p=planById(pid), t=taskById(p,tid), s=subById(t,sid); if(!s) return;
    openModal({ icon:'edit', title:'Sửa Sub-task', fields:[ {key:'title',label:'Tên sub-task',type:'text',value:s.title} ],
      onSave:function(v){ if(!v.title) return 'Cần nhập tên sub-task'; s.title=v.title; render(); save(); toast('Đã cập nhật', true); } }); }
  function delSub(pid,tid,sid){ var p=planById(pid), t=taskById(p,tid);
    t.subs=t.subs.filter(function(x){ return x.id!==sid; }); render(); save(); toast('Đã xoá', true); }

  box.addEventListener('click', function(e){
    var el=e.target.closest('[data-rm]'); if(!el) return;
    var a=el.getAttribute('data-rm'), pid=el.getAttribute('data-p'), tid=el.getAttribute('data-t'), sid=el.getAttribute('data-s');
    if(a==='toggle'){ var p=planById(pid); if(p){ p.open=!p.open; render(); } return; }
    if(!EDIT) return;          // các thao tác còn lại cần quyền sửa
    e.stopPropagation();
    if(a==='edit-plan') editPlan(pid);
    else if(a==='del-plan') delPlan(pid);
    else if(a==='add-task') addTask(pid);
    else if(a==='edit-task') editTask(pid,tid);
    else if(a==='del-task') delTask(pid,tid);
    else if(a==='add-sub') addSub(pid,tid);
    else if(a==='edit-sub') editSub(pid,tid,sid);
    else if(a==='del-sub') delSub(pid,tid,sid);
    else if(a==='toggle-task'){ var p=planById(pid), t=taskById(p,tid); if(t){
      if(t.subs&&t.subs.length){ var all=taskDone(t); t.subs.forEach(function(s){ s.done=!all; }); } else t.done=!t.done;
      p.status=planStatus(p); render(); save(); } }
    else if(a==='toggle-sub'){ var p=planById(pid), t=taskById(p,tid), s=subById(t,sid); if(s){ s.done=!s.done; p.status=planStatus(p); render(); save(); } }
  });
  document.querySelectorAll('#rmSeg button').forEach(function(b){ b.addEventListener('click', function(){
    curFilter=b.getAttribute('data-f'); document.querySelectorAll('#rmSeg button').forEach(function(x){ x.classList.toggle('active', x===b); }); render(); }); });
  var add=$('rmAddPlan'); if(add) add.addEventListener('click', addPlan);
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
        if (!node.date) {
          node.date = '--';
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

  function getFileIconClass(name, type) {
    var ext = name.split('.').pop().toLowerCase();
    if (ext === 'xlsx' || ext === 'xls') return { icon: 'table_chart', cls: 'file-excel' };
    if (ext === 'pdf') return { icon: 'picture_as_pdf', cls: 'file-pdf' };
    if (ext === 'docx' || ext === 'doc') return { icon: 'description', cls: 'file-sop' };
    if (type === 'Link' || ext === 'url') return { icon: 'link', cls: 'file-link' };
    return { icon: 'article', cls: 'file-sop' };
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
      var fileData = getFileIconClass(d.name, d.type);
      var actCol = EDIT ? '<td class="action-col" onclick="event.stopPropagation()">' +
          '<button class="action-btn material-symbols-rounded" onclick="openContextMenu(event, \'' + esc(d.id) + '\')">more_vert</button>' +
        '</td>' : '';
      return '<tr onclick="window.open(\'' + esc(d.url) + '\', \'_blank\')">' +
        '<td>' +
          '<div class="file-name-cell">' +
            '<span class="file-icon-wrapper ' + esc(fileData.cls) + '">' +
              '<span class="material-symbols-rounded">' + esc(fileData.icon) + '</span>' +
            '</span>' +
            '<span class="file-name">' + esc(d.name) + '</span>' +
          '</div>' +
        '</td>' +
        '<td class="date-modified">' + esc(d.date) + '</td>' +
        actCol +
      '</tr>';
    }).join('');
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

  window.editDoc = function() {
    var doc = findFileById(DOC_TREE, contextMenuSelectedId);
    if (!doc) return;
    var titleInp = $('linkTitleInp');
    var urlInp = $('linkUrlInp');
    if (titleInp && urlInp) {
      titleInp.value = doc.name;
      urlInp.value = doc.url;
    }
    openModal('linkModal');
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
      doc.date = 'Vừa xong';
      closeModal('linkModal');
      renderTable();
      saveDocs();
      showBottomToast('Cập nhật tài liệu thành công ✔');
    }
  };

  window.openLink = function() {
    var doc = findFileById(DOC_TREE, contextMenuSelectedId);
    if (doc) window.open(doc.url, '_blank');
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
    
    if (linkFolderSel) linkFolderSel.innerHTML = opts;
    if (uploadFolderSel) uploadFolderSel.innerHTML = opts;
    if (folderParentSel) folderParentSel.innerHTML = '<option value="root">Thư mục gốc (Root)</option>' + opts;
    
    if (currentPath.length > 0) {
      var currentFolderId = currentPath[currentPath.length - 1].id;
      if (linkFolderSel) { linkFolderSel.value = currentFolderId; linkFolderSel.disabled = true; }
      if (uploadFolderSel) { uploadFolderSel.value = currentFolderId; uploadFolderSel.disabled = true; }
      if (folderParentSel) { folderParentSel.value = currentFolderId; folderParentSel.disabled = true; }
    } else {
      if (linkFolderSel) linkFolderSel.disabled = false;
      if (uploadFolderSel) uploadFolderSel.disabled = false;
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
      name: title.indexOf('.url') >= 0 ? title : title + '.url',
      date: 'Vừa xong',
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
              date: 'Vừa xong',
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
  var taskSel = '';        // task key đã chọn ở ô tìm
  var tabs=$('blTabs'), rows=$('blRows'), pager=$('blPager'), cnt=$('blCount');

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
    if(b.task){
      // × để NGOÀI <a> (nếu nằm trong sẽ đi theo href + bị bắt nhầm). Cả 2 trong 1 wrapper.
      var unlink = EDIT ? '<span class="unlink material-symbols-rounded mi-xs" data-unlink="'+esc(b.key)+'" title="Gỡ liên kết">close</span>' : '';
      return '<span class="bl-jira-wrap"><a class="bl-jira" href="'+esc(base)+'/browse/'+esc(b.task)+'" target="_blank" rel="noopener">🔗 '+esc(b.task)+'</a>'+unlink+'</span>';
    }
    return '<span class="bl-nolink">⛓️‍💥 Chưa liên kết</span>';
  }

  // file đang xem: '' = tất cả, else chỉ bug có fid===activeFid
  function fileBugs(){ return activeFid ? BUGS.filter(function(b){ return b.fid===activeFid; }) : BUGS; }
  // tháng có mặt trong file đang xem (giữ thứ tự MONTHS)
  function availMonths(){ var fb=fileBugs(); return MONTHS.filter(function(m){ return fb.some(function(b){ return b.month===m; }); }); }
  function monthBugs(){ return fileBugs().filter(function(b){ return b.month===curMonth; }); }

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
    page=1; renderTabs(); render(); updateActiveChip();
    toast(activeFid ? ('Đang xem: '+activeLabel()) : 'Đang xem: tất cả file', true);
  }
  function updateActiveChip(){ var c=$('blActiveFile'); if(!c) return;
    if(activeFid){ c.textContent='📄 '+activeLabel(); c.style.display=''; }
    else c.style.display='none';
  }

  function renderTabs(){
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
        +'<td style="white-space:nowrap">'+esc(b.created||'—')+'</td>'
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
    btn.disabled = !(n>0); }

  // ----- events: tabs -----
  tabs.addEventListener('click', function(e){ var t=e.target.closest('.bl-tab'); if(!t) return;
    curMonth=t.getAttribute('data-m'); page=1; renderTabs(); render(); });
  // ----- events: pager -----
  pager.addEventListener('click', function(e){ var b=e.target.closest('[data-pg]'); if(!b||b.disabled) return;
    page=parseInt(b.getAttribute('data-pg'),10)||1; render(); });
  // ----- events: tick + unlink (delegate trên tbody) -----
  rows.addEventListener('click', function(e){
    var u=e.target.closest('[data-unlink]');
    if(u){ e.preventDefault(); doLink([u.getAttribute('data-unlink')], ''); return; }
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

  // "Đồng bộ ngay" — F5 chỉ render cache; nút này gọi scan() Drive ngay rồi reload (admin)
  (function(){
    var b=$('blSyncBtn'); if(!b) return;
    b.addEventListener('click', function(){
      b.disabled=true;
      toast('Đang đọc lại data từ Drive…', true);
      postJSON('/sync-bug-log', {}, 90000).then(function(j){
        if(j && j.ok){ toast('Đã đồng bộ ✓ — đang tải lại', true); setTimeout(function(){ location.reload(); }, 900); }
        else { b.disabled=false; toast((j&&(j.errors&&j.errors[0]))||'Đồng bộ lỗi', false); }
      }).catch(function(){ b.disabled=false; toast('Lỗi mạng khi đồng bộ', false); });
    });
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
    function rowHtml(label, link){
      return '<div class="bl-src-row">'
        +'<input type="text" class="bl-src-label" placeholder="Nhãn (tuỳ chọn)" value="'+esc(label||'')+'">'
        +'<input type="text" class="bl-src-link" placeholder="Link Google Drive" value="'+esc(link||'')+'">'
        +'<button type="button" class="del material-symbols-rounded mi-sm" title="Xoá">delete</button></div>';
    }
    function renderList(){
      if(!SOURCES.length){ listEl.innerHTML='<div class="bl-src-empty">Chưa có link nào — bấm “Thêm link”.</div>'; return; }
      listEl.innerHTML = SOURCES.map(function(s){ return rowHtml(s.label, driveLink(s.id)); }).join('');
    }
    function open(){ renderList(); ov.classList.add('open'); }
    function close(){ ov.classList.remove('open'); }
    var b=$('blManageBtn'); if(b) b.addEventListener('click', open);
    var c=$('blSrcClose'); if(c) c.addEventListener('click', close);
    var cc=$('blSrcCancel'); if(cc) cc.addEventListener('click', close);
    ov.addEventListener('click', function(e){ if(e.target===ov) close(); });
    var add=$('blSrcAdd'); if(add) add.addEventListener('click', function(){
      var empty=listEl.querySelector('.bl-src-empty'); if(empty) listEl.innerHTML='';
      listEl.insertAdjacentHTML('beforeend', rowHtml('', '')); });
    listEl.addEventListener('click', function(e){ var d=e.target.closest('.del'); if(!d) return;
      var row=d.closest('.bl-src-row'); if(row) row.remove();
      if(!listEl.querySelector('.bl-src-row')) listEl.innerHTML='<div class="bl-src-empty">Chưa có link nào — bấm “Thêm link”.</div>'; });
    var sv=$('blSrcSave'); if(sv) sv.addEventListener('click', function(){
      var list=[];
      listEl.querySelectorAll('.bl-src-row').forEach(function(row){
        var link=(row.querySelector('.bl-src-link').value||'').trim();
        var label=(row.querySelector('.bl-src-label').value||'').trim();
        if(link) list.push({ link:link, label:label });   // bỏ dòng trống
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

    var inp=$('blTaskInp'), res=$('blTaskRes'), taT;
    inp.addEventListener('input', function(){ taskSel=''; updateLinkBtn();
      var q=inp.value.trim(); clearTimeout(taT);
      if(q.length<2){ res.classList.remove('open'); return; }
      taT=setTimeout(function(){
        getJSON('/search-tasks?q='+encodeURIComponent(q), 15000).then(function(j){
          var rs=(j&&j.results)||[];
          if(!rs.length){ res.innerHTML='<div class="opt">Không tìm thấy task.</div>'; res.classList.add('open'); return; }
          res.innerHTML = rs.map(function(r){
            var meta=[r.assignee, r.status].filter(Boolean).map(esc).join(' · ');
            return '<div class="opt" data-k="'+esc(r.key)+'"><b>'+esc(r.key)+'</b> — '+esc(r.summary)
              +(meta?'<span class="bl-opt-meta">'+meta+'</span>':'')+'</div>'; }).join('');
          res.classList.add('open');
        }).catch(function(){ res.classList.remove('open'); });
      }, 250);
    });
    res.addEventListener('click', function(e){ var o=e.target.closest('.opt[data-k]'); if(!o) return;
      taskSel=o.getAttribute('data-k'); inp.value=taskSel; res.classList.remove('open'); updateLinkBtn(); });
    document.addEventListener('click', function(e){ if(!e.target.closest('#blTaskTA')) res.classList.remove('open'); });

    var lbtn=$('blLinkBtn');
    lbtn.addEventListener('click', function(){
      var keys=Object.keys(sel).filter(function(k){return sel[k];});
      if(!keys.length) return;
      if(!taskSel) { toast('Vui lòng tìm và chọn task ở ô bên trái để liên kết', false); return; }
      doLink(keys, taskSel);
    });
  }

  function doLink(keys, task){
    postJSON('/link-task', { keys: keys, task: task }, 20000).then(function(j){
      if(j && j.ok && j.links){
        var m=j.links;
        BUGS.forEach(function(b){ if(m.hasOwnProperty(b.key)) b.task = m[b.key]||''; });
        if(task){ keys.forEach(function(k){ delete sel[k]; }); taskSel=''; var inp=$('blTaskInp'); if(inp) inp.value='';
          toast('Đã liên kết '+keys.length+' mục với '+task+' ✓', true); }
        else toast('Đã gỡ liên kết ✓', true);
        renderTabs(); render();
      } else toast('Lỗi lưu liên kết', false);
    }).catch(function(){ toast('Lỗi mạng khi liên kết', false); });
  }

  // ===== Metric Table =====
  var metricMonthSel = $('blMetricMonth'), metricHead = $('blMetricHead'), metricRows = $('blMetricRows');
  
  function renderMetric() {
    if(!metricMonthSel || !metricHead || !metricRows) return;
    var selectedMonth = metricMonthSel.value;
    if(!selectedMonth) {
      metricHead.innerHTML = '';
      metricRows.innerHTML = '<tr><td style="text-align:center;color:var(--on-surface-variant);padding:30px">Không có dữ liệu</td></tr>';
      return;
    }
    
    // Lấy bugs của tháng
    var mBugs = BUGS.filter(function(b){ return b.month === selectedMonth; });
    
    // Tập hợp dev và project
    var devs = {}; // dev -> { proj -> count }
    var projs = {}; // proj -> true
    
    mBugs.forEach(function(b) {
      var d = (b.dev || 'Chưa gán').trim();
      var p = (b.project || 'Khác').trim();
      if(!devs[d]) devs[d] = {};
      if(!devs[d][p]) devs[d][p] = 0;
      devs[d][p]++;
      projs[p] = true;
    });
    
    var projList = Object.keys(projs).sort();
    
    // Header
    var ths = '<th>Developer</th>';
    projList.forEach(function(p) { ths += '<th>' + esc(p) + '</th>'; });
    ths += '<th>Tổng cộng</th>';
    metricHead.innerHTML = ths;
    
    // Rows
    var devList = Object.keys(devs).sort();
    if(devList.length === 0) {
      metricRows.innerHTML = '<tr><td colspan="' + (projList.length + 2) + '" style="text-align:center;color:var(--on-surface-variant);padding:30px">Không có dữ liệu trong tháng này</td></tr>';
      return;
    }
    
    var html = devList.map(function(d) {
      var row = '<tr><td>' + esc(d) + '</td>';
      var total = 0;
      projList.forEach(function(p) {
        var count = devs[d][p] || 0;
        total += count;
        row += '<td>' + (count > 0 ? count : '') + '</td>';
      });
      row += '<td class="col-total">' + total + '</td></tr>';
      return row;
    }).join('');
    
    metricRows.innerHTML = html;
  }
  
  // ----- Reopen metric (issue #69): % bug bị reopen + số lần fix theo dev + drill-down -----
  var reopenMonthSel = $('blReopenMonth'), reopenKpi = $('blReopenKpi'),
      reopenHead = $('blReopenHead'), reopenRows = $('blReopenRows');
  var reopenExpanded = {};   // dev -> đang xổ chi tiết hay không

  function reopenPct(n, d){ if(d <= 0) return null; var p = n / d * 100; return (p % 1 === 0 ? p.toFixed(0) : p.toFixed(1)); }
  function fixOf(r){ return (r && r.fix != null) ? (+r.fix || 0) : ((+(r && r.count) || 0) + 1); }  // migration: entry cũ thiếu fix -> reopen+1

  function renderReopen() {
    if(!reopenMonthSel || !reopenHead || !reopenRows) return;
    var selectedMonth = reopenMonthSel.value;
    if(!selectedMonth) {
      if(reopenKpi) reopenKpi.innerHTML = '';
      reopenHead.innerHTML = '';
      reopenRows.innerHTML = '<tr><td style="text-align:center;color:var(--on-surface-variant);padding:30px">Không có dữ liệu</td></tr>';
      return;
    }
    // bug của tháng theo dev (mẫu số tỷ lệ) + tra bug theo key
    var mBugs = BUGS.filter(function(b){ return b.month === selectedMonth; });
    var bugsPerDev = {}, totalBugs = mBugs.length, bugByKey = {};
    mBugs.forEach(function(b){
      var d = (b.dev || 'Chưa gán').trim();
      bugsPerDev[d] = (bugsPerDev[d] || 0) + 1;
      if(b.key) bugByKey[b.key] = b;
    });
    // reopen của tháng: distinct bug + tổng lần fix, theo dev; gom chi tiết per-dev cho drill-down
    var distinctPerDev = {}, fixPerDev = {}, detailPerDev = {}, distinctTotal = 0;
    Object.keys(REOPEN).forEach(function(key){
      var r = REOPEN[key] || {}; var cnt = +r.count || 0; if(cnt <= 0) return;
      var b = bugByKey[key];
      var month = b ? b.month : (r.month || '');
      if(month !== selectedMonth) return;
      var dev = ((b ? b.dev : r.dev) || 'Chưa gán').trim();
      var fx = fixOf(r);
      distinctPerDev[dev] = (distinctPerDev[dev] || 0) + 1;
      fixPerDev[dev] = (fixPerDev[dev] || 0) + fx;
      distinctTotal++;
      (detailPerDev[dev] = detailPerDev[dev] || []).push({
        id: b ? b.id : key, summary: b ? b.summary : '', reopen: cnt, fix: fx
      });
    });
    // KPI headline
    if(reopenKpi) {
      var hp = reopenPct(distinctTotal, totalBugs);
      reopenKpi.innerHTML = hp === null
        ? '<span class="rk-sub">Không có bug trong tháng này.</span>'
        : '<span class="rk-pct">' + hp + '%</span> bug bị reopen';
    }
    reopenHead.innerHTML = '<th>Developer</th><th>Bug bị reopen</th>'
      + '<th>Tổng số lần fix bug</th><th>Tỷ lệ reopen</th>';
    var devList = Object.keys(distinctPerDev).sort(function(a,b){
      return distinctPerDev[b] - distinctPerDev[a];
    });
    if(devList.length === 0) {
      reopenRows.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--on-surface-variant);padding:30px">Chưa ghi nhận reopen nào trong tháng này 🎉</td></tr>';
      return;
    }
    function rateCell(nb, denom){
      var r = reopenPct(nb, denom);
      return r === null ? '—' : r + '%';
    }
    function detailRow(dev){
      var items = (detailPerDev[dev] || []).slice().sort(function(a,b){ return b.reopen - a.reopen; });
      var li = items.map(function(it){
        return '<div class="rk-bug"><span class="rk-bug-id">' + esc(it.id) + '</span>'
          + '<span class="rk-bug-sum">' + esc(it.summary || '(không mô tả)') + '</span>'
          + '<span class="rk-bug-n">' + it.reopen + ' lần reopen · ' + it.fix + ' lần fix</span></div>';
      }).join('');
      return '<tr class="rk-detail"><td colspan="4"><div class="rk-detail-box">'
        + '<div class="rk-detail-hd">Chi tiết bug bị reopen của ' + esc(dev) + '</div>' + li
        + '</div></td></tr>';
    }
    var body = devList.map(function(d){
      var nb = distinctPerDev[d], fx = fixPerDev[d], denom = bugsPerDev[d] || 0;
      var open = !!reopenExpanded[d];
      var row = '<tr class="rk-row' + (open ? ' open' : '') + '" data-dev="' + esc(d) + '">'
        + '<td><span class="rk-caret material-symbols-rounded">' + (open ? 'expand_more' : 'chevron_right') + '</span>' + esc(d) + '</td>'
        + '<td>' + nb + '</td><td>' + fx + '</td>'
        + '<td class="col-total">' + rateCell(nb, denom) + '</td></tr>';
      if(open) row += detailRow(d);
      return row;
    }).join('');
    reopenRows.innerHTML = body;
  }

  // bấm dòng dev -> xổ/đóng chi tiết
  if(reopenRows) reopenRows.addEventListener('click', function(e){
    var tr = e.target.closest('.rk-row'); if(!tr) return;
    var dev = tr.getAttribute('data-dev'); if(!dev) return;
    reopenExpanded[dev] = !reopenExpanded[dev];
    renderReopen();
  });

  if(metricMonthSel) {
    if(MONTHS.length > 0) {
      metricMonthSel.innerHTML = MONTHS.map(function(m){
        return '<option value="' + esc(m) + '">' + esc(m) + '</option>';
      }).join('');
      metricMonthSel.value = curMonth;
    } else {
      metricMonthSel.innerHTML = '<option value="">Chưa có dữ liệu</option>';
    }
    metricMonthSel.addEventListener('change', renderMetric);
  }

  if(reopenMonthSel) {
    if(MONTHS.length > 0) {
      reopenMonthSel.innerHTML = MONTHS.map(function(m){
        return '<option value="' + esc(m) + '">' + esc(m) + '</option>';
      }).join('');
      reopenMonthSel.value = curMonth;
    } else {
      reopenMonthSel.innerHTML = '<option value="">Chưa có dữ liệu</option>';
    }
    reopenMonthSel.addEventListener('change', renderReopen);
  }

  tabs.addEventListener('click', function(e){
    var t=e.target.closest('.bl-tab'); if(!t) return;
    if(metricMonthSel && metricMonthSel.value !== curMonth) {
      metricMonthSel.value = curMonth;
      renderMetric();
    }
    if(reopenMonthSel && reopenMonthSel.value !== curMonth) {
      reopenMonthSel.value = curMonth;
      renderReopen();
    }
  });

  if(activeFid){ var av0=availMonths(); if(av0.indexOf(curMonth)<0) curMonth = av0.length?av0[0]:''; }
  renderTabs(); render(); renderMetric(); renderReopen(); updateActiveChip();
})();

})();
