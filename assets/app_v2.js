/* ===== QA Suite UI v2 — JS shell (Việc của tôi · Tài liệu · Bug Log · Analytics). Inline qua _document_v2. ===== */
/* Phần shared chạy mọi trang; Việc của tôi guard #rows. Endpoint thật. */
(function(){
'use strict';

// ---------- helpers ----------
function esc(s){ return (s==null?'':String(s))
  .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function $(id){ return document.getElementById(id); }
function readJSON(id){ var el=$(id); if(!el) return null; try{ return JSON.parse(el.textContent); }catch(e){ return null; } }
// Canon key Jira để so khớp link BỀN qua đổi project key mỗi kỳ nửa năm (DA51H26<->DA52H26<->
// DA51H27). Gộp đoạn kỳ `<digit>H<2-digit-year>` cuối key -> '#' => mọi phiên bản key của CÙNG
// issue khớp nhau. TWIN của config.canon_key (Python) — sửa 1 bên PHẢI sửa bên kia.
function canonKey(k){ return k ? String(k).trim().replace(/\dH\d{2}(-\d+)$/, '#$1') : k; }
// Phosphor (light) icon — map tên Material cũ -> glyph Phosphor. Giữ class `material-symbols-rounded`
// làm hook CSS (nhiều rule nhắm nó), thêm `ph-light ph-<name>`. Đồng bộ với bảng map ở render (Python).
var PHMAP={
 'close':'x','link':'link','info':'info','edit':'pencil-simple','create_new_folder':'folder-plus',
 'upload':'upload-simple','sync':'arrows-clockwise','search':'magnifying-glass','expand_more':'caret-down',
 'calendar_month':'calendar-dots','bug_report':'bug-beetle','warning':'warning','trending_up':'trend-up',
 'settings':'gear-six','folder_open':'folder-open','error':'warning-circle','dark_mode':'moon','circle':'circle',
 'chevron_right':'caret-right','check':'check','assignment':'clipboard-text','add':'plus','visibility':'eye',
 'unfold_more':'arrows-down-up','table_view':'table','table_chart':'table','tab':'browsers','speed':'gauge',
 'share':'share-network','search_off':'magnifying-glass-minus','refresh':'arrow-clockwise','picture_as_pdf':'file-pdf',
 'person_search':'user-focus','open_in_new':'arrow-square-out','notifications':'bell','logout':'sign-out','lock':'lock',
 'hub':'graph','hourglass_bottom':'hourglass','history':'clock-counter-clockwise','group':'users','folder_off':'folder-minus',
 'folder':'folder','event_busy':'calendar-x','engineering':'wrench','edit_calendar':'calendar-plus','download':'download-simple',
 'difference':'git-diff','description':'file-text','delete':'trash','content_copy':'copy','cloud_upload':'cloud-arrow-up',
 'cloud_off':'cloud-slash','cloud':'cloud','chevron_left':'caret-left','check_circle':'check-circle','autorenew':'arrows-clockwise',
 'add_task':'plus-circle','add_link':'link-simple','add_circle':'plus-circle','checklist':'list-checks','monitoring':'chart-line-up',
 'map':'map-trifold','person':'user','star':'star','space_dashboard':'squares-four','contrast':'circle-half','key':'key',
 'hourglass_empty':'hourglass-simple','progress_activity':'circle-notch','light_mode':'sun','visibility_off':'eye-slash',
 'chat_bubble_outline':'chat-circle','expand_less':'caret-up','celebration':'confetti','event':'calendar-blank',
 'more_vert':'dots-three-vertical','remove':'minus','check_box':'check-square','indeterminate_check_box':'minus-square',
 'check_box_outline_blank':'square','slideshow':'presentation','article':'article','sync_alt':'arrows-left-right',
 'cancel':'x-circle','trending_down':'trend-down','apps':'squares-four','radio_button_unchecked':'circle',
 'fiber_new':'sparkle','chat_bubble':'chat-circle-dots','swap_horiz':'arrows-left-right','person_add':'user-plus',
 'bolt':'lightning','sell':'tag','remove_circle_outline':'minus-circle','subdirectory_arrow_right':'arrow-elbow-down-right',
 'library_books':'books','fact_check':'check-square','format_list_numbered':'list-numbers','task_alt':'check-circle',
 'keyboard_arrow_down':'caret-down','keyboard_arrow_right':'caret-right','code':'file-html',
 'smart_toy':'robot','precision_manufacturing':'gauge','pending':'clock','block':'prohibit'
};
function phIcon(name, extra, weight){
  var ph=PHMAP[name]||name;
  return '<span class="material-symbols-rounded'+(extra?' '+extra:'')+' ph-'+(weight||'light')+' ph-'+ph+'"></span>';
}
// ---------- Severity DÙNG CHUNG (Decision #104) ----------
// Severity = ĐÚNG giá trị field Jira (Blocker/Critical/High/Medium/Low — không convert về 3 mức
// như #85 thời Google Sheet). Ô trống / giá trị lạ -> 'none' (Chưa phân loại, không vẽ trong pie).
// PHẢI khớp _SEV_ORDER/_SEV_PIE/_SEV_LABEL/_sev_bucket phía Python (bug_backlog.py).
// Đặt ở scope chung vì DÙNG Ở 2 NƠI: pie chart /analytics + cột Severity bảng /bug-log.
var SEV_ORDER = ['blocker','critical','high','medium','low','none'];
var SEV_PIE   = ['blocker','critical','high','medium','low'];
var SEV_LABEL = { blocker:'Blocker', critical:'Critical', high:'High', medium:'Medium',
                  low:'Low', none:'Chưa phân loại' };
var SEV_COLOR = { blocker:'#7a0916', critical:'#de350b', high:'#ff5630', medium:'#ffab00',
                  low:'#36b37e', none:'#97a0af' };
function sevOf(b){
  var s = (''+(b.severity||'')).trim().toLowerCase();
  return SEV_PIE.indexOf(s) >= 0 ? s : 'none';
}
// Pager numbered DÙNG CHUNG toàn app (đồng bộ: range info + số trang + ellipsis + mũi tên).
// data-pg = số trang TUYỆT ĐỐI; container tự bắt click qua delegation. start là index 0-based.
function pagerHTML(page, pages, total, start, count, unit){
  unit = unit || 'mục';
  var ph='<span class="pager-summary">'+(start+1)+'–'+(start+count)+' / '+total+' '+unit+' · trang '+page+'/'+pages+'</span>'
    +'<div class="pager-nav"><button class="pager-btn"'+(page<=1?' disabled':'')+' data-pg="'+(page-1)+'"><span class="material-symbols-rounded ph-light ph-caret-left mi-xs"></span></button>';
  var win=1, last=0; // luôn hiện trang 1, trang cuối, và current ± win; còn lại rút gọn '…'
  for(var i=1;i<=pages;i++){
    if(i===1 || i===pages || (i>=page-win && i<=page+win)){
      if(last && i-last>1) ph+='<span class="pager-ellipsis">…</span>';
      ph+='<button class="pager-page'+(i===page?' active':'')+'" data-pg="'+i+'">'+i+'</button>';
      last=i;
    }
  }
  ph+='<button class="pager-btn"'+(page>=pages?' disabled':'')+' data-pg="'+(page+1)+'"><span class="material-symbols-rounded ph-light ph-caret-right mi-xs"></span></button></div>';
  return ph;
}
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

// ---------- ghi chú riêng theo task (Decision #101) — drawer mọi trang ----------
// NOTE_TXT[key] = bản đang có ở client (đã gõ/đã lưu) -> drawer render lại (poll 60s, đổi status)
// KHÔNG làm mất chữ đang gõ. Lần đầu lấy từ detail.note (/issue-comments). Chỉ chính chủ.
var NOTE_TXT={}, NOTE_AT={};
function noteSectionHtml(key, d){
  if(!window.__isAdmin || !d) return '';
  if(NOTE_TXT[key]===undefined){ NOTE_TXT[key]=(d.note&&d.note.t)||''; NOTE_AT[key]=(d.note&&d.note.at)||''; }
  var at=NOTE_AT[key] ? 'Đã lưu '+esc(NOTE_AT[key].slice(0,16).replace('T',' ')) : 'Chỉ mình bạn thấy · tự lưu';
  return '<div class="dt-sec-title">Ghi chú riêng</div>'
    +'<div class="dt-note"><textarea class="dt-note-ta" data-note-key="'+esc(key)+'" rows="3" maxlength="5000" '
    +'placeholder="Checklist, lý do đang chờ, link Chat… (không đẩy lên Jira)">'+esc(NOTE_TXT[key])+'</textarea>'
    +'<div class="dt-note-st" id="noteSt-'+esc(key)+'">'+at+'</div></div>';
}
(function(){
  var timers={};
  function save(key){
    clearTimeout(timers[key]); delete timers[key];
    var txt=NOTE_TXT[key]||'', st=$('noteSt-'+key);
    if(st) st.textContent='Đang lưu…';
    postJSON('/set-note', { key:key, text:txt }, 15000).then(function(j){
      var el=$('noteSt-'+key);
      if(j && j.ok){ NOTE_AT[key]=(j.note&&j.note.at)||'';
        if(el) el.textContent=NOTE_AT[key]?('Đã lưu '+NOTE_AT[key].slice(0,16).replace('T',' ')):'Đã xoá ghi chú';
        if(window.__applyNotePatch) window.__applyNotePatch(key, !!(txt.trim())); }
      else if(el) el.textContent='⚠ Không lưu được — thử gõ lại';
    }).catch(function(){ var el=$('noteSt-'+key); if(el) el.textContent='⚠ Lỗi mạng — chưa lưu'; });
  }
  document.addEventListener('input', function(e){
    var ta=e.target; if(!ta.classList || !ta.classList.contains('dt-note-ta')) return;
    var key=ta.getAttribute('data-note-key'); NOTE_TXT[key]=ta.value;
    var st=$('noteSt-'+key); if(st) st.textContent='Chưa lưu…';
    clearTimeout(timers[key]); timers[key]=setTimeout(function(){ save(key); }, 900);
  });
  // blur = lưu ngay (đóng drawer/chuyển trang không mất chữ của 900ms cuối)
  document.addEventListener('focusout', function(e){
    var ta=e.target; if(!ta.classList || !ta.classList.contains('dt-note-ta')) return;
    var key=ta.getAttribute('data-note-key'); if(timers[key]) save(key);
  });
  window.addEventListener('pagehide', function(){
    Object.keys(timers).forEach(function(key){
      try{ fetch('/set-note', { method:'POST', keepalive:true,
        headers:{'Content-Type':'application/json'}, body:JSON.stringify({key:key, text:NOTE_TXT[key]||''}) }); }catch(_){}
    });
  });
})();

// ---------- toast (stack queue, max 3, giữ nguyên signature toast(msg, ok)) ----------
function toast(msg, ok){
  var wrap=$('toastWrap');
  if(!wrap){ wrap=document.createElement('div'); wrap.className='toast-wrap'; wrap.id='toastWrap';
    document.body.appendChild(wrap); }
  while(wrap.children.length>=3) wrap.removeChild(wrap.firstChild);
  var el=document.createElement('div');
  el.className='toast'+(ok===false?' err':'');
  el.innerHTML=phIcon(ok===false?'error':'check_circle')+'<span></span>';
  el.lastChild.textContent=msg;
  wrap.appendChild(el);
  setTimeout(function(){ el.classList.add('out');
    setTimeout(function(){ if(el.parentNode) el.parentNode.removeChild(el); }, 250); }, 2600);
}

// ---------- @-mention trong ô bình luận (drawer + inline QA), dùng chung mọi trang ----------
// Gõ "@" trong textarea comment -> dropdown user; chọn -> chèn markup Jira [~username].
// Backend (jira_api._comment_snippet / fetch_activity_feed) parse [~username] thành "được nhắc"
// + Jira notify đúng người (Decision #20/#24). QA team hiện ngay (window.__mentionUsers);
// gõ >=2 ký tự augment thêm bằng Jira user search (/search-people, PAT chung read-only).
(function mentionAutocomplete(){
  var LOCAL = (window.__mentionUsers || []);   // [{name,display}]
  function fold(s){ return (s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/đ/g,'d'); }
  function isCmtTa(el){ return el && el.tagName==='TEXTAREA' && /^(dtTa|cmtTa)-/.test(el.id||''); }

  var dd=null, cur=null, at=-1, items=[], sel=0, seq=0, deb=null;
  function ddEl(){ if(!dd){ dd=document.createElement('div'); dd.className='mention-dd'; dd.style.display='none'; document.body.appendChild(dd); } return dd; }
  function open(){ return dd && dd.style.display!=='none'; }
  function close(){ if(dd) dd.style.display='none'; cur=null; at=-1; items=[]; sel=0; clearTimeout(deb); }

  // Query = chuỗi ngay sau '@' cuối cùng (không khoảng trắng), tính tới caret. '@' phải đứng đầu
  // hoặc sau khoảng trắng/'(' để không dính vào email hay giữa từ.
  function trigger(ta){
    var pos=ta.selectionStart||0, before=ta.value.slice(0,pos);
    var m=/(^|[\s(\[])@([^\s@]{0,30})$/.exec(before);
    if(!m) return null;
    return { q:m[2], at:pos-m[2].length-1 };   // vị trí ký tự '@'
  }
  function render(hint){
    var el=ddEl(), h='';
    if(items.length) h=items.map(function(u,i){
      return '<div class="mention-opt'+(i===sel?' active':'')+'" data-i="'+i+'">'
        +'<span class="mention-name">'+esc(u.display||u.name)+'</span>'
        +'<span class="mention-user">@'+esc(u.name)+'</span></div>'; }).join('');
    if(hint) h+=hint;                                   // dòng "Đang tìm trên Jira…"
    else if(!items.length) h='<div class="mention-empty">Không tìm thấy</div>';
    el.innerHTML=h; el.style.display='block';
  }
  function place(ta){
    var r=ta.getBoundingClientRect(), el=ddEl();
    el.style.left=Math.max(8, r.left)+'px';
    el.style.width=Math.max(220, Math.min(r.width, 360))+'px';
    if(r.top < 260){ el.style.top=(r.bottom+2)+'px'; el.style.transform='none'; }        // dưới
    else { el.style.top=(r.top-2)+'px'; el.style.transform='translateY(-100%)'; }        // trên (né nút Gửi)
  }
  function pick(u){
    if(!cur || at<0 || !u) return;
    var ta=cur, pos=ta.selectionStart||0, val=ta.value, ins='[~'+u.name+'] ';
    ta.value=val.slice(0,at)+ins+val.slice(pos);
    var np=at+ins.length; ta.selectionStart=ta.selectionEnd=np; ta.focus();
    close();
  }
  function search(ta, info){
    cur=ta; at=info.at;
    var q=info.q, fq=fold(q), my=++seq;
    var loc=LOCAL.filter(function(u){ return !fq || fold(u.name).indexOf(fq)>=0 || fold(u.display).indexOf(fq)>=0; });
    // Roster QA hiện ngay; gõ >=1 ký tự -> tìm TOÀN BỘ user Jira (/search-people) rồi merge vào.
    items=loc.slice(0,10); sel=0; render(q.length>=1 && '<div class="mention-empty">Đang tìm user trên Jira…</div>'); place(ta);
    clearTimeout(deb);
    if(q.length>=1){
      deb=setTimeout(function(){
        getJSON('/search-people?q='+encodeURIComponent(q), 12000).then(function(j){
          if(my!==seq || cur!==ta) return;
          var rs=(j&&j.ok&&j.results)||[], seen={}, merged=[];
          loc.concat(rs).forEach(function(u){ if(u&&u.name&&!seen[u.name]){ seen[u.name]=1; merged.push(u); } });
          items=merged.slice(0,10); if(sel>=items.length) sel=0; render(); place(ta);
        }).catch(function(){ if(my===seq && cur===ta) render(); });   // lỗi -> bỏ dòng "đang tìm"
      }, 220);
    }
  }

  document.addEventListener('input', function(e){
    if(!isCmtTa(e.target)) return;
    var info=trigger(e.target);
    if(info) search(e.target, info); else close();
  });
  // Capture để chặn Enter/Esc/mũi tên TRƯỚC handler drawer (Esc vốn đóng drawer) khi dropdown mở.
  document.addEventListener('keydown', function(e){
    if(!open() || !cur) return;
    if(e.key==='ArrowDown'){ e.preventDefault(); sel=(sel+1)%Math.max(1,items.length); render(); }
    else if(e.key==='ArrowUp'){ e.preventDefault(); sel=(sel-1+Math.max(1,items.length))%Math.max(1,items.length); render(); }
    else if(e.key==='Enter' || e.key==='Tab'){ if(items.length){ e.preventDefault(); e.stopPropagation(); pick(items[sel]); } else close(); }
    else if(e.key==='Escape'){ e.preventDefault(); e.stopPropagation(); close(); }
  }, true);
  document.addEventListener('mousedown', function(e){
    if(!dd) return;
    var o=e.target.closest ? e.target.closest('.mention-opt') : null;
    if(o){ e.preventDefault(); pick(items[+o.getAttribute('data-i')]); return; }
    if(!e.target.closest('.mention-dd') && !isCmtTa(e.target)) close();
  });
  window.addEventListener('scroll', function(){ if(open() && cur) place(cur); }, true);
})();

// ---------- confirm modal (thay confirm() native — Promise<bool>, dùng chung mọi trang) ----------
// confirmModal({title, message, confirmText, cancelText, danger}) -> Promise resolve true/false.
// danger mặc định TRUE (phần lớn dùng cho thao tác xoá/phá huỷ). Enter = đồng ý, Esc = huỷ.
// Keydown bắt ở capture + stopImmediatePropagation -> KHÔNG đóng nhầm drawer/palette phía sau.
function confirmModal(opts){
  opts = opts || {};
  return new Promise(function(resolve){
    var ov=$('confirmOv');
    if(!ov){
      ov=document.createElement('div'); ov.className='confirm-ov'; ov.id='confirmOv';
      ov.innerHTML='<div class="cmodal"><div class="cmodal-head">'
        +'<span class="material-symbols-rounded ph-light ph-warning" id="cmIcon"></span>'
        +'<h3 id="cmTitle"></h3></div>'
        +'<div class="cmodal-body" id="cmBody"></div>'
        +'<div class="cmodal-foot">'
        +'<button type="button" class="btn btn-ghost" id="cmCancel"></button>'
        +'<button type="button" class="btn" id="cmOk"></button></div></div>';
      document.body.appendChild(ov);
    }
    var modal=ov.querySelector('.cmodal');
    var okBtn=$('cmOk'), cancelBtn=$('cmCancel'), icon=$('cmIcon');
    var danger = opts.danger !== false;
    $('cmTitle').textContent = opts.title || 'Xác nhận';
    $('cmBody').textContent = opts.message || '';
    okBtn.textContent = opts.confirmText || 'Đồng ý';
    cancelBtn.textContent = opts.cancelText || 'Huỷ';
    modal.classList.toggle('danger', danger);
    okBtn.className = 'btn ' + (danger ? 'btn-danger-solid' : 'btn-primary');
    icon.textContent = danger ? 'warning' : 'help';
    var done=false;
    function cleanup(val){
      if(done) return; done=true;
      ov.classList.remove('open');
      document.removeEventListener('keydown', onKey, true);
      okBtn.onclick=cancelBtn.onclick=ov.onclick=null;
      resolve(val);
    }
    function onKey(e){
      if(!ov.classList.contains('open')) return;
      if(e.key==='Escape'){ e.preventDefault(); e.stopImmediatePropagation(); cleanup(false); }
      else if(e.key==='Enter'){ e.preventDefault(); e.stopImmediatePropagation(); cleanup(true); }
    }
    okBtn.onclick=function(){ cleanup(true); };
    cancelBtn.onclick=function(){ cleanup(false); };
    ov.onclick=function(e){ if(e.target===ov) cleanup(false); };
    document.addEventListener('keydown', onKey, true);
    ov.classList.add('open');
    setTimeout(function(){ okBtn.focus(); }, 30);
  });
}

// ---------- theme ----------
function setThemeAttr(t){ document.documentElement.setAttribute('data-theme', t);
  try{ localStorage.setItem('qa-theme', t); }catch(e){}
  var ic=$('themeIc'); if(ic) ic.className='material-symbols-rounded ph-light ph-'+(t==='dark'?'sun':'moon'); }
function applyTheme(t, animate){
  if(animate && document.startViewTransition){ document.startViewTransition(function(){ setThemeAttr(t); }); return; }
  if(animate){ var h=document.documentElement; h.classList.add('theme-anim');
    setTimeout(function(){ h.classList.remove('theme-anim'); }, 380); }
  setThemeAttr(t);
}
(function(){ var t='light'; try{ t=localStorage.getItem('qa-theme')||'light'; }catch(e){} applyTheme(t); })();
(function(){ var b=$('themeBtn'); if(b) b.addEventListener('click', function(){
  applyTheme(document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark', true); }); })();

// ---------- progress bar điều hướng (che server render chậm khi chuyển tab) ----------
(function(){
  var bar=document.createElement('div'); bar.className='nav-progress'; bar.innerHTML='<i></i>';
  document.body.appendChild(bar);
  function show(){ bar.classList.add('on'); }
  document.addEventListener('click', function(e){
    var a=e.target.closest('.nav a[href], .pmenu a[href]');
    if(!a) return;
    if(a.target==='_blank' || e.ctrlKey || e.metaKey || e.shiftKey) return;
    show();
  });
  // back-forward cache: trang cũ hiện lại -> tắt bar
  window.addEventListener('pageshow', function(){ bar.classList.remove('on'); });
})();

// ---------- row stagger helper (gọi sau tbody.innerHTML=) ----------
function animRows(tb){ if(!tb) return; tb.classList.remove('anim');
  void tb.offsetWidth; tb.classList.add('anim'); }

// ---------- skeleton helpers ----------
function skelDrawer(){
  return '<div class="skel skel-line w60" style="height:18px"></div>'
    +'<div class="skel skel-line w80" style="height:18px;margin-bottom:16px"></div>'
    +'<div class="skel skel-line w40"></div><div class="skel skel-line w60"></div>'
    +'<div class="skel skel-line w40"></div><div class="skel skel-line w80"></div>'
    +'<div class="skel skel-block"></div>'
    +skelComments();
}
function skelComments(){
  var row='<div class="skel-row"><div class="skel skel-av"></div>'
    +'<div class="skel-main"><div class="skel skel-line w40"></div><div class="skel skel-line w80"></div></div></div>';
  return row+row;
}

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
    dd.innerHTML='<div class="skel-row"><div class="skel skel-badge"></div><div class="skel-main"><div class="skel skel-line w80"></div></div></div>'
      +'<div class="skel-row"><div class="skel skel-badge"></div><div class="skel-main"><div class="skel skel-line w60"></div></div></div>'
      +'<div class="skel-row"><div class="skel skel-badge"></div><div class="skel-main"><div class="skel skel-line w40"></div></div></div>'; open();
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

// ---------- command palette (Ctrl+K) — điều hướng + hành động + task Jira + bug log ----------
// DOM #cpOverlay ở shell (mọi trang v2). Đặt TRƯỚC các module khác để keydown Escape của
// palette chạy trước (stopImmediatePropagation -> không đóng nhầm drawer/smenu phía sau).
(function(){
  var ov=$('cpOverlay'); if(!ov) return;
  var inp=$('cpInput'), listEl=$('cpList');
  var isAdmin=!!window.__isAdmin;
  function norm(s){ return (s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/đ/g,'d'); }
  var ST={ 'TO DO':'st-open','In Progress':'st-fixing','PENDING':'st-default',
           'DONE':'st-fixed','CANCELLED':'st-closed' };
  var BUG_CLS={ 'New':'st-open','Fixing':'st-fixing','Fixed':'st-fixed','Reopen':'st-reopen',
                'Rejected':'st-rejected','Closed':'st-closed' };
  var NAV=[
    {label:'Hôm nay', href:'/today', icon:'sun-horizon'},
    {label:'Việc của tôi', href:'/my-work', icon:'person'},
    {label:'Bug Log', href:'/bug-log', icon:'bug_report'},
    {label:'Analytics', href:'/analytics', icon:'monitoring'},
    {label:'Tài liệu', href:'/docs', icon:'description'}
  ].filter(Boolean);
  var ACTS=[
    {label:'Tạo Sub-task', icon:'add_task', run:function(){ var b=$('createSubBtn'); if(b) b.click(); }},
    {label:'Đổi giao diện sáng / tối', icon:'contrast', run:function(){ var b=$('themeBtn'); if(b) b.click(); }},
    {label:'Cài đặt API token / Drive', icon:'key', run:function(){ var o=$('setOverlay'); if(o) o.classList.add('open'); }},
    {label:'Bật / tắt thông báo desktop', icon:'notifications', run:function(){ var d=window.__desktopNotif; if(!d) return;
      if(d.on()) d.disable(); else d.enable(); }},
    isAdmin?{label:'Sync bug log ngay', icon:'sync', run:function(){
      toast('Đang sync bug log…', true);
      postJSON('/sync-bug-log', {}, 60000).then(function(j){
        toast(j&&j.ok?'Đã sync bug log ✓':((j&&j.msg)||'Lỗi sync bug log'), !!(j&&j.ok));
      }).catch(function(){ toast('Lỗi mạng khi sync', false); }); }}:null
  ].filter(Boolean);

  var isOpen=false, q='', seq=0, taskRows=[], bugRows=[], flat=[], active=0, deb;

  function itemHtml(it, idx){
    var right=it.right||'';
    return '<div class="cp-item'+(idx===active?' active':'')+'" data-i="'+idx+'">'
      +phIcon(it.icon,'mi-sm')
      +'<span class="cp-lbl">'+it.html+'</span>'+right+'</div>';
  }
  function render(){
    var nq=norm(q);
    var nav=NAV.filter(function(n){ return !nq || norm(n.label).indexOf(nq)>=0; });
    var acts=ACTS.filter(function(a){ return !nq || norm(a.label).indexOf(nq)>=0; });
    flat=[];
    var h='';
    function sec(title, items){
      if(!items.length) return;
      h+='<div class="cp-sec">'+title+'</div>';
      items.forEach(function(it){ h+=itemHtml(it, flat.length); flat.push(it); });
    }
    sec('Điều hướng', nav.map(function(n){ return { icon:n.icon, html:esc(n.label),
      run:(function(href){ return function(){ location.href=href; }; })(n.href) }; }));
    sec('Hành động', acts.map(function(a){ return { icon:a.icon, html:esc(a.label), run:a.run }; }));
    if(q.length>=2){
      sec('Task Jira', taskRows===null
        ? [{ icon:'hourglass_empty', html:'<span class="skel skel-line w80" style="margin:0"></span>', run:function(){} }]
        : taskRows.map(function(r){ return { icon:'assignment',
            html:'<b class="cp-key">'+esc(r.key)+'</b> '+esc(r.summary||''),
            right:(r.status?'<span class="st-badge '+(ST[r.status]||'st-default')+'">'+esc(r.status)+'</span>':''),
            run:(function(key){ return function(){
              if(window.__openDetail) window.__openDetail(key);
              else window.open((window.__jiraBase||'')+'/browse/'+encodeURIComponent(key), '_blank'); }; })(r.key) }; }));
      sec('Bug (bug log)', bugRows===null
        ? [{ icon:'hourglass_empty', html:'<span class="skel skel-line w60" style="margin:0"></span>', run:function(){} }]
        : bugRows.map(function(b){ return { icon:'bug_report',
            html:'<b class="cp-key">'+esc(b.id||'')+'</b> '+esc(b.summary||''),
            right:(b.status?'<span class="st-badge '+(BUG_CLS[b.status]||'st-default')+'">'+esc(b.status)+'</span>':''),
            run:(function(key){ return function(){
              location.href='/bug-log?bug='+encodeURIComponent(key); }; })(b.key) }; }));
    }
    if(!flat.length) h='<div class="cp-empty">Không có kết quả cho "'+esc(q)+'"</div>';
    if(active>=flat.length) active=Math.max(0, flat.length-1);
    listEl.innerHTML=h;
    var ae=listEl.querySelector('.cp-item.active');
    if(ae) ae.scrollIntoView({ block:'nearest' });
  }
  function fetchAsync(){
    var my=++seq;
    taskRows=null; bugRows=null; render();
    getJSON('/global-search?q='+encodeURIComponent(q), 15000).then(function(j){
      if(my!==seq) return; taskRows=((j&&j.ok&&j.results)||[]).slice(0,8); render();
    }).catch(function(){ if(my!==seq) return; taskRows=[]; render(); });
    getJSON('/search-bugs?q='+encodeURIComponent(q), 15000).then(function(j){
      if(my!==seq) return; bugRows=(j&&j.ok&&j.results)||[]; render();
    }).catch(function(){ if(my!==seq) return; bugRows=[]; render(); });
  }
  function openPal(){
    isOpen=true; ov.classList.add('open');
    inp.value=''; q=''; taskRows=[]; bugRows=[]; active=0; seq++;
    render(); setTimeout(function(){ inp.focus(); }, 30);
  }
  function closePal(){ isOpen=false; ov.classList.remove('open'); inp.blur(); }
  function exec(){ var it=flat[active]; if(!it) return; closePal(); it.run(); }
  function move(d){ if(!flat.length) return;
    active=(active+d+flat.length)%flat.length; render(); }

  document.addEventListener('keydown', function(e){
    if((e.ctrlKey||e.metaKey) && !e.altKey && (e.key==='k'||e.key==='K')){
      e.preventDefault(); if(isOpen) closePal(); else openPal(); return; }
    if(!isOpen) return;
    if(e.key==='Escape'){ e.stopImmediatePropagation(); closePal(); }
    else if(e.key==='ArrowDown'){ e.preventDefault(); move(1); }
    else if(e.key==='ArrowUp'){ e.preventDefault(); move(-1); }
    else if(e.key==='Enter'){ e.preventDefault(); exec(); }
  });
  inp.addEventListener('input', function(){
    q=(inp.value||'').trim(); active=0;
    clearTimeout(deb);
    if(q.length<2){ seq++; taskRows=[]; bugRows=[]; render(); return; }
    render();                                  // lọc nav/actions ngay, phần async chờ debounce
    deb=setTimeout(fetchAsync, 300);
  });
  listEl.addEventListener('mousedown', function(e){   // mousedown: chạy trước blur
    var it=e.target.closest('.cp-item'); if(!it) return;
    e.preventDefault(); active=parseInt(it.getAttribute('data-i'),10)||0; exec();
  });
  listEl.addEventListener('mousemove', function(e){
    var it=e.target.closest('.cp-item'); if(!it) return;
    var i=parseInt(it.getAttribute('data-i'),10);
    if(i!==active){ active=i; render(); }
  });
  ov.addEventListener('mousedown', function(e){ if(e.target===ov) closePal(); });
})();

// ---------- toggle thông báo desktop trong modal Setting (Decision #103) ----------
(function(){
  var btn=$('setNotifBtn'), st=$('setNotifState'); if(!btn) return;
  function refresh(){
    var d=window.__desktopNotif, perm=window.Notification?Notification.permission:'unsupported';
    var on=!!(d && d.on());
    btn.textContent=on?'Tắt thông báo':'Bật thông báo';
    st.textContent = perm==='unsupported' ? 'Trình duyệt không hỗ trợ.'
      : perm==='denied' ? '⚠ Trình duyệt đang chặn — bấm ổ khoá cạnh thanh địa chỉ → Thông báo → Cho phép.'
      : on ? '✓ Đang bật.' : 'Đang tắt.';
    st.className='set-drive-state'+(on?' ok':(perm==='denied'?' warn':''));
  }
  btn.addEventListener('click', function(){ var d=window.__desktopNotif; if(!d) return;
    if(d.on()){ d.disable(); refresh(); } else d.enable().then(refresh); });
  // __desktopNotif định nghĩa ở module chuông (chạy SAU module này) -> refresh khi mở modal
  document.addEventListener('click', function(e){ if(e.target.closest('#pmSettings')) setTimeout(refresh, 0); });
  setTimeout(refresh, 0);
})();

// ---------- settings PAT modal ----------
(function(){
  var ov=$('setOverlay'); if(!ov) return;
  // Card "Kết nối Drive" đã gỡ (#104): Bug Log nguồn Jira, không còn Google Drive.
  function open(){ ov.classList.add('open'); var m=$('pmenu'); if(m) m.classList.remove('open'); }
  function close(){ ov.classList.remove('open'); }
  var s=$('pmSettings'); if(s) s.addEventListener('click', open);
  var c=$('setClose'); if(c) c.addEventListener('click', close);
  var cc=$('setCancel'); if(cc) cc.addEventListener('click', close);
  ov.addEventListener('click', function(e){ if(e.target===ov) close(); });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape' && ov.classList.contains('open')) close(); });
  var show=$('patShowBtn'), inp=$('patInp');
  if(show&&inp) show.addEventListener('click', function(){
    if(inp.type==='password'){ inp.type='text'; show.className='eye material-symbols-rounded mi-sm ph-light ph-eye-slash'; }
    else { inp.type='password'; show.className='eye material-symbols-rounded mi-sm ph-light ph-eye'; } });
  var save=$('patSaveBtn');
  if(save) save.addEventListener('click', function(){
    var v=(inp.value||'').trim(); if(!v){ toast('Chưa nhập API token', false); return; }
    save.disabled=true;
    postJSON('/save-pat', { pat:v }, 20000).then(function(j){
      save.disabled=false; toast(j.msg || (j.ok?'Đã lưu token':'Lỗi lưu token'), j.ok);
      if(j.ok){ inp.value=''; close(); }
    }).catch(function(){ save.disabled=false; toast('Lỗi mạng khi lưu token', false); }); });
  var del=$('patDelBtn');
  if(del) del.addEventListener('click', function(){
    confirmModal({title:'Xoá API token', message:'Xoá API token đã lưu? Thao tác Jira sẽ không còn ghi tên bạn.', confirmText:'Xoá token'}).then(function(ok){ if(!ok) return;
    fetch('/delete-pat', { method:'POST' }).then(function(r){ return r.json(); })
      .then(function(j){ toast(j.ok?'Đã xoá token':'Lỗi xoá', j.ok); if(j.ok) close(); })
      .catch(function(){ toast('Lỗi mạng', false); }); }); });
})();
// popup nhắc PAT khi server trả no_pat
function patToast(j){ if(j && j.code==='no_pat'){ var ov=$('setOverlay'); if(ov) ov.classList.add('open');
  toast(j.msg || 'Cần API token Jira để thao tác', false); return true; } return false; }

// ---------- Đổi Due date theo QUYỀN Jira (ghi bằng PAT cá nhân) — bảng + drawer, dùng chung ----------
// DUE_PERM[key]: true = được sửa · false = không được · 'no_pat' = chưa có PAT · 'loading'/undefined.
// Quyền lấy từ /editmeta (Jira trả field CHÍNH user hiện tại được sửa) — check LAZY lúc bấm ô Hạn
// (không hỏi trước từng dòng); enforce thật vẫn ở /set-duedate. Ô Hạn hiện được ở CẢ bảng lẫn drawer.
var DUE_PERM = {};
function ensureDuePerm(key, cb){
  var cur = DUE_PERM[key];
  if(cur!==undefined && cur!=='loading'){ if(cb) cb(cur); return; }
  if(cur==='loading'){ return; }
  DUE_PERM[key]='loading';
  postJSON('/duedate-perm', { key:key }, 15000).then(function(j){
    DUE_PERM[key] = (j && j.code==='no_pat') ? 'no_pat'
                    : (j && j.ok && j.canEdit ? true : false);
    if(cb) cb(DUE_PERM[key]);
  }).catch(function(){ DUE_PERM[key]=false; if(cb) cb(false); });
}
// Ô Hạn chót có thể bấm để sửa (cả bảng lẫn drawer). Trả nguyên cụm <span class="due-cell">.
function dueValHTML(t){
  return '<span class="due-cell" data-act="due-edit" data-key="'+esc(t.key)+'" data-due="'+esc(t.due||'')
    +'" title="Bấm để đổi hạn"><span class="due '+esc(t.dueCls||'')+'">'+esc(t.dueDisp||'—')+'</span>'
    +'<span class="due-pen material-symbols-rounded ph-light ph-calendar-plus mi-xs"></span></span>';
}
function dueToday(){ var d=new Date();
  return d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2); }
function recomputeDue(t, val){          // đồng bộ dueDisp/dueCls/overdue sau khi đổi hạn
  val=(val||'').trim(); t.due=val; t.dueDisp = val || 'Chưa đặt hạn';
  var st=(t.jira||'').toUpperCase();
  var od = !!val && val < dueToday() && st!=='DONE' && st!=='CANCELLED';
  t.overdue = od; t.dueCls = od ? 'overdue' : '';
}
window.__recomputeDue = recomputeDue;
// Vá field vào task obj sau khi sửa (title/assignee/due) — dùng bởi __applyFieldPatch mỗi controller.
function applyTaskFields(t, patch){
  if(patch.summary!=null) t.summary=patch.summary;
  if(patch.assignee!=null){ var nm=patch.assignee.display||patch.assignee.name||'—';
    t.assignee={ name:nm, init:initOf(nm), cls:avById(patch.assignee.name||nm) }; }
  if(patch.due!=null) recomputeDue(t, patch.due);
}
window.__applyTaskFields = applyTaskFields;
// Ghi hạn mới lên Jira (PAT cá nhân) rồi vá bảng/drawer. Tách ra để date-picker gọi trực tiếp.
function saveDue(key, val, inDrawer){
  postJSON('/set-duedate', { key:key, duedate:val }, 20000).then(function(j){
    if(patToast(j)){ dueAfterChange(key, inDrawer); return; }
    if(j.ok){ if(window.__applyDuePatch) window.__applyDuePatch(key, val);
      toast(val?'Đã đổi hạn ✓':'Đã xoá hạn ✓', true); dueAfterChange(key, inDrawer); }
    else { toast(j.msg||'Lỗi đổi hạn', false); dueAfterChange(key, inDrawer); }
  }).catch(function(){ toast('Lỗi mạng', false); dueAfterChange(key, inDrawer); });
}
// Bấm ô Hạn -> hiện NGAY date picker (native calendar), tự lưu khi chọn xong; KHÔNG còn box Lưu/Huỷ.
// showPicker() cần user-activation: click LẦN ĐẦU 1 task phải chờ round-trip check quyền nên activation
// mất -> input vẫn focus (bấm để mở lịch); các lần sau quyền đã cache -> mở lịch tức thì.
function dueEditor(cell, key, cur){
  cell.classList.add('editing');
  var inDrawer=!!cell.closest('#drawer');
  cell.innerHTML='<input type="date" class="due-input" value="'+esc(cur)+'">';
  var inp=cell.querySelector('.due-input'); if(!inp) return;
  var done=false;
  inp.addEventListener('change', function(){
    if(done) return; done=true;
    var val=(inp.value||'').trim();
    if(val===(cur||'')){ dueAfterChange(key, inDrawer); return; }   // không đổi -> khôi phục
    toast(key+': đang đổi hạn…', true); saveDue(key, val, inDrawer);
  });
  inp.addEventListener('keydown', function(e){
    if(e.key==='Escape'){ e.preventDefault(); if(done) return; done=true; dueAfterChange(key, inDrawer); } });
  inp.addEventListener('blur', function(){                          // bấm ra ngoài không chọn -> khôi phục
    setTimeout(function(){ if(!done){ done=true; dueAfterChange(key, inDrawer); } }, 200); });
  inp.focus();
  try{ inp.showPicker(); }catch(e){}
}
// Khôi phục ô/bảng/drawer sau save (đã patch) hoặc cancel. inDrawer = ô nằm trong drawer.
function dueAfterChange(key, inDrawer){
  if(inDrawer){ if(window.__openDetail) window.__openDetail(key); }
  else if(window.__rerenderRows){ window.__rerenderRows(); }
}
// Click handler dùng chung (event delegation trên document) cho cả bảng lẫn drawer.
document.addEventListener('click', function(e){
  var a=e.target.closest('[data-act]'); if(!a) return;
  var act=a.getAttribute('data-act');
  if(act==='due-edit'){
    var cell=a.closest('.due-cell'); if(!cell || cell.classList.contains('editing')) return;
    var key=a.getAttribute('data-key'), cur=a.getAttribute('data-due')||'';
    cell.innerHTML='<span class="due-loading">…</span>';
    ensureDuePerm(key, function(perm){
      if(perm==='no_pat'){ patToast({code:'no_pat', msg:'Cần API token Jira để đổi hạn — vào ⚙ Cài đặt'}); dueAfterChange(key, !!cell.closest('#drawer')); return; }
      if(perm!==true){ toast('Bạn không có quyền đổi hạn task này trên Jira', false); dueAfterChange(key, !!cell.closest('#drawer')); return; }
      if(document.body.contains(cell)) dueEditor(cell, key, cur);
    });
  }
});

// ---------- SỬA TASK trong drawer (title / assignee / due) — dùng chung mọi trang ----------
// Bút ✎ ở drawer-head -> form sửa ngay đầu drawer-body. Quyền lấy LAZY qua /edit-perms (theo PAT
// cá nhân); enforce thật ở /update-issue. Lưu xong vá tại chỗ qua window.__applyFieldPatch(key,patch).
(function(){
  function drawerKey(){ var k=document.querySelector('#drawer .key'); return k?k.textContent.trim():''; }
  function curSummary(){ var h=document.querySelector('#drawer .drawer-body h2'); return h?(h.textContent||''):''; }
  function curDue(){ var c=document.querySelector('#drawer .due-cell'); return c?(c.getAttribute('data-due')||''):''; }
  function curAssignee(){ var a=document.querySelector('#drawer .dt-grid .assignee'); if(!a) return '';
    var t=''; for(var i=0;i<a.childNodes.length;i++){ var n=a.childNodes[i];   // bỏ chữ cái avatar, chỉ lấy tên
      if(n.nodeType===3) t+=n.textContent; } return t.trim(); }
  function closeForm(){ var f=$('editForm'); if(f&&f.parentNode) f.parentNode.removeChild(f); }

  function renderForm(perms){
    closeForm();
    var body=document.querySelector('#drawer .drawer-body'); if(!body) return;
    var canS=perms.summary, canA=perms.assignee, canD=perms.duedate;
    var h='<div class="edit-form" id="editForm"><div class="edit-title">Sửa task</div>'
      +'<label class="edit-lbl">Tiêu đề</label>'
      +(canS?'<input type="text" id="edTitle" class="edit-inp" value="'+esc(curSummary())+'">'
            :'<div class="edit-ro">'+esc(curSummary())+' <em>— không có quyền sửa</em></div>')
      +'<label class="edit-lbl">Người xử lý</label>';
    if(canA) h+='<div class="edit-asg"><input type="text" id="edAsgInp" class="edit-inp" placeholder="'
      +esc(curAssignee()||'Gõ tên để tìm...')+'" autocomplete="off">'
      +'<input type="hidden" id="edAsgName"><div class="edit-asg-dd" id="edAsgDd"></div></div>'
      +'<div class="edit-asg-cur">Hiện tại: <b>'+esc(curAssignee()||'—')+'</b></div>';
    else h+='<div class="edit-ro">'+esc(curAssignee()||'—')+' <em>— không có quyền sửa</em></div>';
    h+='<label class="edit-lbl">Hạn chót</label>'
      +(canD?'<input type="date" id="edDue" class="edit-inp" value="'+esc(curDue())+'">'
            :'<div class="edit-ro">'+(esc(curDue())||'Chưa đặt hạn')+' <em>— không có quyền sửa</em></div>')
      +'<div class="edit-foot"><button type="button" class="btn btn-ghost" data-act="edit-cancel">Huỷ</button>'
      +'<button type="button" class="btn btn-primary" data-act="edit-save">Lưu thay đổi</button></div></div>';
    body.insertAdjacentHTML('afterbegin', h);
    body.scrollTop=0;
    var ti=$('edTitle'); if(ti) ti.focus();
    bindAsg();
  }
  function bindAsg(){
    var inp=$('edAsgInp'), dd=$('edAsgDd'), hid=$('edAsgName'); if(!inp||!dd||!hid) return;
    var deb, seq=0;
    inp.addEventListener('input', function(){
      hid.value='';                       // gõ lại -> huỷ lựa chọn cũ (chỉ gửi khi có chọn)
      var q=(inp.value||'').trim(); clearTimeout(deb);
      if(q.length<2){ dd.style.display='none'; dd.innerHTML=''; return; }
      var my=++seq;
      deb=setTimeout(function(){
        getJSON('/search-people?q='+encodeURIComponent(q), 15000).then(function(j){
          if(my!==seq) return; var rs=(j&&j.ok&&j.results)||[];
          dd.innerHTML = rs.length ? rs.map(function(u){
            return '<div class="edit-asg-opt" data-name="'+esc(u.name)+'" data-disp="'+esc(u.display)+'">'
              +esc(u.display)+' <small>'+esc(u.name)+'</small></div>'; }).join('')
            : '<div class="edit-asg-empty">Không tìm thấy</div>';
          dd.style.display='block';
        }).catch(function(){ if(my!==seq) return; dd.style.display='none'; });
      }, 300);
    });
    dd.addEventListener('mousedown', function(e){ var o=e.target.closest('.edit-asg-opt'); if(!o) return;
      e.preventDefault(); hid.value=o.getAttribute('data-name'); inp.value=o.getAttribute('data-disp');
      dd.style.display='none'; });
  }

  document.addEventListener('click', function(e){
    var a=e.target.closest('[data-act]'); if(!a) return;
    var act=a.getAttribute('data-act');
    if(act==='edit-toggle'){
      if($('editForm')){ closeForm(); return; }
      var key=drawerKey(); if(!key) return;
      a.disabled=true;
      postJSON('/edit-perms', { key:key }, 15000).then(function(j){
        a.disabled=false; if(patToast(j)) return;
        if(!j.ok){ toast(j.msg||'Không lấy được quyền sửa', false); return; }
        var p=j.fields||{};
        if(!p.summary && !p.assignee && !p.duedate){ toast('Bạn không có quyền sửa task này trên Jira', false); return; }
        renderForm(p);
      }).catch(function(){ a.disabled=false; toast('Lỗi mạng', false); });
    } else if(act==='edit-cancel'){ closeForm(); }
    else if(act==='edit-save'){
      var key=drawerKey(); if(!key) return;
      var body={ key:key }, hasChange=false;
      var ti=$('edTitle');
      if(ti){ var s=(ti.value||'').trim(); if(!s){ toast('Tiêu đề không được rỗng', false); return; }
        if(s!==curSummary()){ body.summary=s; hasChange=true; } }
      var hid=$('edAsgName'); if(hid && hid.value){ body.assignee=hid.value; hasChange=true; }
      var du=$('edDue'); if(du){ var dv=(du.value||'').trim(); if(dv!==curDue()){ body.duedate=dv; hasChange=true; } }
      if(!hasChange){ toast('Chưa có thay đổi nào', false); return; }
      a.disabled=true; toast(key+': đang lưu…', true);
      postJSON('/update-issue', body, 20000).then(function(j){
        a.disabled=false; if(patToast(j)) return;
        if(j.ok){
          var patch={};
          if(body.summary!=null) patch.summary=body.summary;
          if(body.assignee!=null){ var ai=$('edAsgInp'); patch.assignee={ name:body.assignee, display:(ai&&ai.value)||body.assignee }; }
          if(body.duedate!=null) patch.due=body.duedate;
          closeForm();
          if(window.__applyFieldPatch) window.__applyFieldPatch(key, patch);
          else if(window.__openDetail) window.__openDetail(key);
          toast('Đã lưu thay đổi ✓', true);
        } else toast(j.msg||'Lỗi lưu thay đổi', false);
      }).catch(function(){ a.disabled=false; toast('Lỗi mạng khi lưu', false); });
    }
  });
})();

// ---------- status menu (.smenu) DÙNG CHUNG — đổi status Jira + gắn nhãn nội bộ ----------
// #smenu giờ nằm ở shell (mọi trang v2). Controller gọi window.__openSmenu(caret, task, hooks);
// hooks.onChanged(kind, key, payload) chạy sau khi ghi thành công (kind='status'|'customs')
// để controller cập nhật bảng/KPI/drawer của riêng nó. Task obj được mutate tại chỗ
// (t.jira / t.customs / t.canCustom) nên controller chỉ cần re-render.
var __sm={ caret:null, task:null, jira:null, hooks:null };
var smInflight={};
function smEl(){ return $('smenu'); }
function smClose(){ var m=smEl(); if(m){ m.classList.remove('open'); m.innerHTML=''; }
  __sm.caret=null; __sm.task=null; __sm.jira=null; __sm.hooks=null; }
function smRender(t, jiraState){
  __sm.jira=jiraState;
  var cur={}; (t.customs||[]).forEach(function(v){ cur[v]=1; });
  var h='<div class="smenu-grp">Status Jira</div>';
  if(jiraState===null) h+='<div style="padding:6px 14px"><div class="skel skel-line w80"></div><div class="skel skel-line w60"></div></div>';
  else if(jiraState.code==='no_pat') h+='<div class="smenu-note" data-sm="nopat"><span class="material-symbols-rounded ph-light ph-lock mi-sm"></span>Cần API token Jira để đổi status — bấm để thêm</div>';
  else if(!jiraState.ok) h+='<div class="smenu-note muted"><span class="material-symbols-rounded ph-light ph-warning-circle mi-sm"></span>'+esc(jiraState.msg||'Lỗi tải status')+'</div>';
  else if(!jiraState.transitions.length) h+='<div class="smenu-note muted"><span class="material-symbols-rounded ph-light ph-info mi-sm"></span>Không có bước chuyển khả dụng</div>';
  else jiraState.transitions.forEach(function(tr){
    h+='<div class="smenu-opt" data-sm="jira" data-id="'+esc(tr.id)+'" data-to="'+esc(tr.to)+'">'
      +'<span class="dot" style="background:#0052cc"></span>'+esc(tr.to)+'<span class="chk material-symbols-rounded ph-light ph-check"></span></div>'; });
  var allowed=t.canCustom;
  h+='<div class="smenu-grp brd">Nhãn nội bộ — chọn nhiều</div>';
  if(!allowed) h+='<div class="smenu-note muted"><span class="material-symbols-rounded ph-light ph-info mi-sm"></span>Chỉ gắn khi <b>TO DO</b> / <b>In Progress</b></div>';
  (window.QA_CUSTOM_STATUSES||[]).forEach(function(p){
    var on=cur[p[0]]?' on':'';
    h+='<div class="smenu-opt'+on+(allowed?'':' disabled')+'"'+(allowed?' data-sm="cust" data-val="'+esc(p[0])+'"':'')+'>'
      +'<span class="dot" style="background:#6554c0"></span>'+esc(p[1])+'<span class="chk material-symbols-rounded ph-light ph-check"></span></div>'; });
  h+='<div class="smenu-foot"><small>'+((t.customs||[]).length?(t.customs.length+' nhãn'):'Chưa gắn nhãn')+'</small>'
    +'<button type="button" data-sm="close">Xong</button></div>';
  smEl().innerHTML=h;
}
function smPosition(caret){
  var m=smEl();
  m.classList.add('open'); m.style.maxHeight='none';
  var r=caret.getBoundingClientRect(), gap=6, pad=8;
  var below=window.innerHeight-r.bottom-gap-pad, above=r.top-gap-pad;
  var avail=Math.max(below,above); m.style.maxHeight=avail+'px';
  var mh=Math.min(m.offsetHeight, avail);
  var top=(below>=above)?r.bottom+gap:r.top-gap-mh;
  m.style.top=Math.max(pad, top)+'px';
  m.style.left=Math.min(r.left, window.innerWidth-292)+'px';
}
window.__openSmenu=function(caret, t, hooks){
  var m=smEl(); if(!m||!t) return;
  var key=t.key;
  if(__sm.task && __sm.task.key===key && m.classList.contains('open')){ smClose(); return; }
  __sm.caret=caret; __sm.task=t; __sm.hooks=hooks||{};
  smRender(t, null); smPosition(caret);
  postJSON('/jira-transitions', { key:key }, 20000)
    .then(function(j){ if(__sm.task&&__sm.task.key===key&&m.classList.contains('open')){ smRender(t, j); smPosition(__sm.caret); } })
    .catch(function(){ if(__sm.task&&__sm.task.key===key&&m.classList.contains('open')){ smRender(t, { ok:false, msg:'Lỗi mạng khi tải status' }); smPosition(__sm.caret); } });
};
// Sau khi controller rebuild bảng (innerHTML) -> caret cũ rời DOM; bám lại caret mới cùng key.
window.__smRebind=function(){
  var m=smEl(); if(!(__sm.task && m && m.classList.contains('open'))) return;
  var nc=document.querySelector('[data-act="smenu"][data-key="'+__sm.task.key+'"]');
  if(nc) __sm.caret=nc;
};
function smNotify(kind, key, payload){
  if(__sm.hooks && __sm.hooks.onChanged) __sm.hooks.onChanged(kind, key, payload);
}
function smDoTransition(key, id, toName){
  var t=__sm.task, hooks=__sm.hooks; smClose();
  if(smInflight['t'+key]) return; smInflight['t'+key]=true;
  toast(key+': đang đổi status…', true);
  // `to` gửi kèm để server chốt overlay status vừa ghi (Decision #90) khi nó không đọc
  // lại được status từ Jira; `j.status` (server đọc lại thật) thắng nếu có.
  postJSON('/do-transition', { key:key, id:id, to:toName }, 20000).then(function(j){
    smInflight['t'+key]=false; if(patToast(j)) return;
    if(j.ok){ var st=(j.status||toName);
      if(t){ t.jira=st;
        var can=(st==='TO DO'||st==='In Progress');
        if(!can) t.customs=[]; t.canCustom=can; }
      if(hooks && hooks.onChanged) hooks.onChanged('status', key, st);
      toast(key+' → '+st+' ✓', true); }
    else toast(j.msg||('Lỗi đổi status '+key), false);
  }).catch(function(){ smInflight['t'+key]=false; toast('Lỗi mạng khi đổi status', false); });
}
// Gắn/gỡ nhãn — dùng cả từ menu lẫn nút × trên chip (onChanged truyền riêng khi gọi ngoài menu).
window.__smSetCustom=function(t, key, val, onChanged){
  if(!t) return;
  var fk=key+'#'+val; if(smInflight[fk]) return; smInflight[fk]=true;
  postJSON('/set-custom-status', { key:key, status:val, summary:t.summary||'' }, 20000).then(function(j){
    smInflight[fk]=false;
    if(!j.ok){ toast('Lỗi lưu nhãn '+key, false); return; }
    t.customs = Array.isArray(j.values) ? j.values : (t.customs||[]);
    if(onChanged) onChanged('customs', key, t.customs);
    else smNotify('customs', key, t.customs);
    var m=smEl();
    if(__sm.task && __sm.task.key===key && m && m.classList.contains('open')){
      window.__smRebind(); smRender(__sm.task, __sm.jira); smPosition(__sm.caret); }
  }).catch(function(){ smInflight[fk]=false; toast('Lỗi mạng khi lưu nhãn', false); });
};
(function(){
  var m=smEl(); if(!m) return;
  m.addEventListener('click', function(e){
    var o=e.target.closest('[data-sm]'); if(!o||!__sm.task) return;
    var kind=o.getAttribute('data-sm'), key=__sm.task.key;
    if(kind==='close'){ smClose(); }
    else if(kind==='nopat'){ smClose(); var ov=$('setOverlay'); if(ov) ov.classList.add('open'); }
    else if(kind==='jira'){ smDoTransition(key, o.getAttribute('data-id'), o.getAttribute('data-to')); }
    else if(kind==='cust'){ window.__smSetCustom(__sm.task, key, o.getAttribute('data-val')); }
  });
  document.addEventListener('click', function(e){
    if(m.classList.contains('open') && !e.target.closest('#smenu') && !e.target.closest('[data-act="smenu"]')) smClose(); });
  window.addEventListener('scroll', function(e){
    if(!m.classList.contains('open')) return;
    if(e.target && e.target.nodeType===1 && (e.target===m || (e.target.closest && e.target.closest('#smenu')))) return;
    smClose();
  }, true);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') smClose(); });
})();

// ---------- trang /settings ĐẦY ĐỦ (render_settings_page) — khác modal ở trên (IDs riêng) ----------
(function(){
  var input=$('patInput'); if(!input) return;   // chỉ chạy trên trang /settings
  var saveBtn=$('patSave'), showBtn=$('patShow'), delBtn=$('patDelete');
  if(saveBtn) saveBtn.addEventListener('click', function(){
    var pat=(input.value||'').trim(); if(!pat){ toast('Chưa nhập API token', false); return; }
    saveBtn.disabled=true;
    postJSON('/save-pat', { pat:pat }, 20000).then(function(j){
      saveBtn.disabled=false; toast(j.msg || (j.ok?'Đã lưu token':'Lỗi lưu token'), j.ok);
      if(j.ok){ input.value=''; setTimeout(function(){ location.reload(); }, 1500); }
    }).catch(function(){ saveBtn.disabled=false; toast('Lỗi mạng khi lưu token', false); }); });
  if(showBtn) showBtn.addEventListener('click', function(){
    input.type = input.type==='password' ? 'text' : 'password'; });
  if(delBtn) delBtn.addEventListener('click', function(){
    confirmModal({title:'Xoá API token', message:'Xoá API token đã lưu? Sau đó thao tác Jira sẽ không còn ghi tên bạn.', confirmText:'Xoá token'}).then(function(ok){ if(!ok) return;
    fetch('/delete-pat', { method:'POST' }).then(function(r){ return r.json(); })
      .then(function(j){ toast(j.ok?'Đã xoá token':'Lỗi xoá', j.ok);
        if(j.ok) setTimeout(function(){ location.reload(); }, 1200); })
      .catch(function(){ toast('Lỗi mạng', false); }); }); });
  // Nút ngắt kết nối Drive đã gỡ (#104): Bug Log nguồn Jira.
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
  function kindCls(n){ if(n.mention) return 'k-mention';
    if(n.kind==='status') return 'k-status'; if(n.kind==='duedate') return 'k-due'; return ''; }
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
        +phIcon(ic,'nkind '+kindCls(n))+'</span>'
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
    var freshUnread=0, freshIds={};
    acts.forEach(function(n){
      if(localRead[n.id]) n.is_unread=false;          // dismiss local thắng (Jira property có thể chưa kịp sync)
      if(!seenIds[n.id]){ seenIds[n.id]=1; if(n.is_unread){ freshUnread++; freshIds[n.id]=1; } }
    });
    NOTIFS = acts;
    render();
    fireDesktop(acts.filter(function(n){ return n.is_unread && freshIds[n.id]; }));
    if(freshUnread>0){ toast('🔔 '+freshUnread+' thông báo mới', true);
      // pulse chuông khi có unread MỚI (không pulse khi chỉ re-render)
      if(dot){ dot.classList.remove('pulse'); void dot.offsetWidth; dot.classList.add('pulse'); }
    }
  }
  // --------- thông báo desktop (Decision #103) ---------
  // Chỉ 1 tab "leader" (Web Lock) được poll khi ẩn + bắn Notification -> nhiều tab KHÔNG bắn trùng,
  // tab ẩn còn lại vẫn nghỉ như cũ (đỡ tải Jira). Chỉ bắn khi KHÔNG tab dashboard nào đang focus
  // (đang nhìn thì đã có toast + chuông). Id đã bắn lưu localStorage -> reload không bắn lại.
  var isLeader=false;
  try{ if(navigator.locks) navigator.locks.request('qa-notif-leader', function(){
    isLeader=true; return new Promise(function(){}); }); }catch(_){}
  function lsGet(k){ try{ return localStorage.getItem(k); }catch(_){ return null; } }
  function lsSet(k,v){ try{ localStorage.setItem(k,v); }catch(_){} }
  function desktopOn(){ return lsGet('qa-desktop-notif')==='1' && window.Notification
    && Notification.permission==='granted'; }
  window.addEventListener('focus', function(){ lsSet('qa-focus','1'); });
  window.addEventListener('blur', function(){ lsSet('qa-focus','0'); });
  if(document.hasFocus()) lsSet('qa-focus','1');
  window.addEventListener('pagehide', function(){ if(document.hasFocus()) lsSet('qa-focus','0'); });
  // cờ 'qa-focus' chung mọi tab: tab nào đang focus thì '1' (blur/đóng -> '0'); leader đọc cờ này
  // để biết bạn có đang nhìn MỘT tab dashboard nào đó không, kể cả khi chính leader đang ẩn.
  function anyFocused(){ return document.hasFocus() || lsGet('qa-focus')==='1'; }
  function plain(html){ var d=document.createElement('div'); d.innerHTML=html; return d.textContent||''; }
  function fireDesktop(items){
    if(!isLeader || !desktopOn() || anyFocused() || !items.length) return;
    var shown={}; try{ shown=JSON.parse(lsGet('qa-notif-shown')||'{}')||{}; }catch(_){}
    var now=Date.now(), fresh=items.filter(function(n){ return !shown[n.id]; });
    fresh.forEach(function(n){ shown[n.id]=now; });
    Object.keys(shown).forEach(function(k){ if(now-shown[k]>14*864e5) delete shown[k]; });
    var keys=Object.keys(shown); if(keys.length>500) keys.sort(function(a,b){ return shown[a]-shown[b]; })
      .slice(0, keys.length-500).forEach(function(k){ delete shown[k]; });
    lsSet('qa-notif-shown', JSON.stringify(shown));
    if(!fresh.length) return;
    function open(n){ return function(){ try{ window.focus(); }catch(_){}
      if(n){ postJSON('/dismiss', { ids:[n.id] }, 20000).catch(function(){}); markRead([n.id]);
        if(window.__openDetail) window.__openDetail(n.key); }
      this.close(); }; }
    try{
      if(fresh.length>3){
        var nb=new Notification('QA Workspace · '+fresh.length+' thông báo mới', {
          body: fresh.slice(0,3).map(function(n){ return plain(ntext(n)); }).join('\n')+'\n…', tag:'qa-batch' });
        nb.onclick=open(null);
      } else fresh.forEach(function(n){
        var x=new Notification((n.mention?'🔔 Được nhắc · ':'')+(n.key||'QA Workspace'), {
          body: plain(ntext(n))+(n.body?'\n“'+n.body+'”':''), tag:n.id });
        x.onclick=open(n);
      });
    }catch(_){}
  }
  window.__desktopNotif={
    on: function(){ return desktopOn(); },
    wanted: function(){ return lsGet('qa-desktop-notif')==='1'; },
    enable: function(){
      if(!window.Notification){ toast('Trình duyệt không hỗ trợ thông báo desktop', false); return Promise.resolve(false); }
      return Promise.resolve(Notification.requestPermission()).then(function(p){
        if(p==='granted'){ lsSet('qa-desktop-notif','1'); toast('Đã bật thông báo desktop ✓', true);
          // đánh dấu đã thấy mọi noti hiện có -> không bắn dồn cả lô cũ ngay sau khi bật
          var shown={}; NOTIFS.forEach(function(n){ shown[n.id]=Date.now(); });
          lsSet('qa-notif-shown', JSON.stringify(shown)); return true; }
        toast(p==='denied' ? 'Trình duyệt đang CHẶN thông báo cho localhost — mở biểu tượng ổ khoá cạnh thanh địa chỉ để cho phép'
                           : 'Chưa cấp quyền thông báo', false);
        return false; });
    },
    disable: function(){ lsSet('qa-desktop-notif','0'); toast('Đã tắt thông báo desktop', true); }
  };

  function poll(){
    // tab ẩn -> bỏ qua, đỡ tải Jira; trừ tab leader khi bật thông báo desktop (#103)
    if(document.hidden && !(isLeader && desktopOn())) return;
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
      customs:d.customs||[], canCustom:(d.status==='TO DO'||d.status==='In Progress'),
      assignee:{ name:d.assignee||'—', init:initOf(d.assignee||'?'), cls:avById(d.assignee||'?') },
      due:d.duedate||'', dueDisp:d.duedate||'Chưa đặt hạn', dueCls:'',
      created:d.created||'', createdDisp:d.created||'—',
      overdue:false, stuck:false, isNew:false,
      jiraUrl:(window.__jiraBase||'')+'/browse/'+key };
  }
  function matchFilter(t,f){ if(f==='overdue') return t.overdue; if(f==='stuck') return t.stuck;
    if(f==='dueweek') return !!t.dueWeek;
    if(f==='done') return t.jira.toUpperCase()==='DONE';
    return t.jira.toUpperCase()!=='DONE'; }
  function visibleTasks(){
    var q=(($('searchInp')||{}).value||'').toLowerCase();
    return TASKS.filter(function(t){ return matchFilter(t,curFilter) &&
      (!q || (t.key+' '+t.summary).toLowerCase().indexOf(q)>=0); });
  }

  function chipHTML(t){
    if(!t.customs || !t.customs.length) return '';
    return '<div class="cust-chips">'+t.customs.map(function(v){
      return '<span class="cust-chip"><span class="material-symbols-rounded ph-light ph-circle"></span>'
        +esc(custMap[v]||v)+'<span class="rm material-symbols-rounded ph-light ph-x" data-key="'+esc(t.key)
        +'" data-val="'+esc(v)+'"></span></span>'; }).join('')+'</div>';
  }
  function rowHTML(t){
    // COMMENTS[key] là mảng khi đã fetch (dùng số live); chưa fetch (undefined/null=đang tải)
    // -> dùng số đếm server nhúng sẵn (t.nComments) để hiện NGAY, không cần mở panel/drawer.
    var nc=COMMENTS[t.key] ? COMMENTS[t.key].length : (t.nComments||0);
    var cnt = nc ? '<span class="cmt-count">'+nc+'</span>' : '';
    return '<tr'+(t.overdue?' class="overdue-row"':'')+' data-key="'+esc(t.key)+'">'
      +'<td><a class="key" href="'+esc(t.jiraUrl)+'" target="_blank">'+esc(t.key)+'</a></td>'
      +'<td class="title clickable" data-act="detail" data-key="'+esc(t.key)+'">'+esc(t.summary)
      +(t.hasNote?' <span class="note-ic material-symbols-rounded ph-light ph-note-pencil mi-xs" title="Có ghi chú riêng"></span>':'')+'</td>'
      +'<td class="status-cell"><div class="stat-wrap"><span class="badge '+jiraCls(t.jira)+'">'+esc(t.jira)+'</span>'
      +'<button class="caret material-symbols-rounded ph-light ph-caret-down mi-sm" data-act="smenu" data-key="'+esc(t.key)+'"></button></div>'+chipHTML(t)+'</td>'
      +'<td><span class="assignee"><span class="av '+esc(t.assignee.cls)+'">'+esc(t.assignee.init)+'</span> '+esc(t.assignee.name)+'</span></td>'
      +'<td class="cell-date">'+esc(t.createdDisp)+'</td>'
      +'<td>'+dueValHTML(t)+'</td>'
      +'<td><span style="display:inline-flex;align-items:center;gap:2px">'
      +'<button class="act-btn'+(openCmt[t.key]?' on':'')+'" data-act="cmt" data-key="'+esc(t.key)+'" title="Bình luận">'
      +'<span class="material-symbols-rounded ph-light ph-chat-circle mi-sm"></span>'+cnt+'</button></span></td>'
      +'</tr>' + (openCmt[t.key] ? cmtRow(t.key) : '');
  }
  function cmtRow(key){
    var list=COMMENTS[key]||null;
    var hist;
    if(list===null) hist=skelComments();
    else if(!list.length) hist='<div class="cmt-empty">Chưa có bình luận nào</div>';
    else hist=list.map(function(c){ return '<div class="cmt-item"><span class="av '+avById(c.author)+'">'+esc(initOf(c.author))+'</span>'
      +'<div class="cmt-main"><div class="cmt-meta"><b>'+esc(c.author)+'</b><span>'+esc((c.when||'').slice(0,16).replace('T',' '))+'</span></div>'
      +'<div class="cmt-text">'+esc(c.body)+'</div></div></div>'; }).join('');
    return '<tr class="cmt-row"><td colspan="7"><div class="cmt-panel">'
      +'<div class="cmt-history">'+hist+'</div>'
      +'<div class="cmt-box"><textarea id="cmtTa-'+esc(key)+'" placeholder="Viết bình luận của bạn... (gõ @ để nhắc người)"></textarea>'
      +'<div class="cmt-foot">'
      +'<button class="lbtn close" data-act="cmt-close" data-key="'+esc(key)+'"><span class="material-symbols-rounded ph-light ph-caret-up mi-xs"></span>Đóng</button>'
      +'<button class="lbtn primary" data-act="cmt-send" data-key="'+esc(key)+'">Gửi</button>'
      +'</div></div></div></td></tr>';
  }
  function renderRows(anim){
    var all=visibleTasks();
    if(!all.length){ tbody.innerHTML='<tr><td colspan="7"><div class="empty-state">'
        +'<span class="es-ic"><span class="material-symbols-rounded ph-light ph-confetti"></span></span>'
        +'<div class="es-title">Không có task nào 🎉</div>'
        +'<div class="es-hint">Sạch việc ở bộ lọc này — nghỉ tay chút đi.</div>'
        +'</div></td></tr>';
      $('pager').innerHTML=''; return; }
    var pages=Math.max(1, Math.ceil(all.length/PER_PAGE));
    if(curPage>pages) curPage=pages; if(curPage<1) curPage=1;
    var start=(curPage-1)*PER_PAGE, slice=all.slice(start, start+PER_PAGE);
    var html=slice.map(rowHTML).join('');
    for(var k=slice.length;k<PER_PAGE;k++){
      html+='<tr class="pager-filler"><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>';
    }
    tbody.innerHTML=html;
    if(anim) animRows(tbody);
    $('pager').innerHTML=pagerHTML(curPage, pages, all.length, start, slice.length, 'task');

    if(window.__smRebind) window.__smRebind();
  }
  function setFilter(f){ curFilter=f; curPage=1;
    document.querySelectorAll('#tabs button').forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-f')===f); });
    document.querySelectorAll('#kpis .kpi').forEach(function(k){ k.classList.toggle('sel', k.getAttribute('data-f')===f); });
    renderRows(true); }

  // dueWeek flag (cho filter) — tính nhanh client từ dueCls? dueweek đã đếm server; ở đây
  // filter dueweek dùng cờ: task không overdue và dueCls!=overdue và due trong tuần.
  // Đơn giản: đánh dấu dueWeek nếu meta cần — ở đây bỏ filter dueweek trên bảng (KPI chỉ là số).

  // event delegation
  document.addEventListener('click', function(e){
    var pg=e.target.closest('[data-pg]'); if(pg && !pg.disabled && pg.closest('#pager')){ curPage=parseInt(pg.getAttribute('data-pg'),10)||1; renderRows(true); return; }
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
    var f=k.getAttribute('data-f'); setFilter(f); }); });
  var si=$('searchInp'); if(si) si.addEventListener('input', function(){ curPage=1; renderRows(true); });

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
    else $('drawer').innerHTML='<div class="drawer-body">'+skelDrawer()+'</div>';
    if(COMMENTS[key]===undefined){ COMMENTS[key]=null; fetchComments(key).then(function(){
      var tt=taskByKey(key);
      if(tt && $('drawer').classList.contains('open')) renderDrawer(tt); }); } }
  window.__openDetail = openDetail;
  function closeDetail(){ $('drawerOv').classList.remove('open'); $('drawer').classList.remove('open'); }
  function renderDrawer(t){
    var chips = (t.customs&&t.customs.length) ? t.customs.map(function(v){
      return '<span class="cust-chip"><span class="material-symbols-rounded ph-light ph-circle"></span>'+esc(custMap[v]||v)+'</span>'; }).join('')
      : '<span style="color:var(--on-surface-variant)">—</span>';
    var flags=''; if(t.overdue) flags+='<span class="dt-flag od"><span class="material-symbols-rounded ph-light ph-calendar-x mi-xs"></span>Quá hạn</span>';
    if(t.stuck) flags+='<span class="dt-flag st"><span class="material-symbols-rounded ph-light ph-hourglass mi-xs"></span>Kẹt</span>';
    if(!flags) flags='<span style="color:var(--on-surface-variant)">—</span>';
    var list=COMMENTS[t.key];
    var hist;
    if(list===null||list===undefined) hist=skelComments();
    else if(!list.length) hist='<div class="cmt-empty">Chưa có bình luận nào</div>';
    else hist=list.map(function(c){ return '<div class="cmt-item"><span class="av '+avById(c.author)+'">'+esc(initOf(c.author))+'</span>'
      +'<div class="cmt-main"><div class="cmt-meta"><b>'+esc(c.author)+'</b><span>'+esc((c.when||'').slice(0,16).replace('T',' '))+'</span></div>'
      +'<div class="cmt-text">'+esc(c.body)+'</div></div></div>'; }).join('');
    var desc=(DETAIL[t.key]&&DETAIL[t.key].description) ? esc(DETAIL[t.key].description) : esc(t.summary);
    $('drawer').innerHTML='<div class="drawer-head"><a class="key" href="'+esc(t.jiraUrl)+'" target="_blank">'+esc(t.key)+'</a>'
      +'<span class="badge '+jiraCls(t.jira)+'">'+esc(t.jira)+'</span>'
      +'<button class="drawer-edit material-symbols-rounded ph-light ph-pencil-simple" data-act="edit-toggle" title="Sửa task (tiêu đề / người xử lý / hạn)"></button>'
      +'<button class="x material-symbols-rounded ph-light ph-x" data-act="drawer-close"></button></div>'
      +'<div class="drawer-body"><h2>'+esc(t.summary)+'</h2>'
      +'<div class="dt-grid"><div class="lbl">Người xử lý</div><div class="val"><span class="assignee"><span class="av '+esc(t.assignee.cls)+'">'+esc(t.assignee.init)+'</span> '+esc(t.assignee.name)+'</span></div>'
      +'<div class="lbl">Ngày tạo</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].created)?esc(DETAIL[t.key].created):esc(t.createdDisp||'—'))+'</div>'
      +'<div class="lbl">Hạn chót</div><div class="val" id="dueVal-'+esc(t.key)+'">'+dueValHTML(t)+'</div>'
      +'<div class="lbl">Cập nhật</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].updated)?esc(DETAIL[t.key].updated):'—')+'</div>'
      +'<div class="lbl">Dev phụ trách</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].devs&&DETAIL[t.key].devs.length)?DETAIL[t.key].devs.map(esc).join(', '):'—')+'</div>'
      +'<div class="lbl">Nhãn nội bộ</div><div class="val">'+chips+'</div>'
      +'<div class="lbl">Cảnh báo</div><div class="val">'+flags+'</div></div>'
      +'<div class="dt-sec-title">Mô tả</div><div class="dt-desc">'+desc+'</div>'
      +bugSectionHtml(DETAIL[t.key])
      +noteSectionHtml(t.key, DETAIL[t.key])
      +'<div class="dt-cmts"><div class="dt-sec-title">Bình luận ('+(list&&list.length||0)+')</div>'
      +'<div class="cmt-panel"><div class="cmt-history">'+hist+'</div>'
      +'<div class="cmt-box"><textarea id="dtTa-'+esc(t.key)+'" placeholder="Viết bình luận... (gõ @ để nhắc người)"></textarea>'
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

  // ----- status menu: dùng module chung (__openSmenu/__smSetCustom, xem section shared) -----
  function qaOnChanged(kind, key){
    renderRows();
    var dEl=$('drawer');
    if(dEl && dEl.classList.contains('open')){
      var ka=dEl.querySelector('.key');
      if(ka && ka.textContent===key){ var t=taskByKey(key); if(t) renderDrawer(t); }
    }
  }
  window.openStatusMenu=function(caret){
    var t=taskByKey(caret.getAttribute('data-key')); if(!t) return;
    window.__openSmenu(caret, t, { onChanged: qaOnChanged });
  };
  function rmCust(key, val){ var t=taskByKey(key);
    if(t) window.__smSetCustom(t, key, val, qaOnChanged); }
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeDetail(); });

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

  window.__applyDuePatch=function(key, val){
    var t=taskByKey(key); if(!t) return;
    recomputeDue(t, val); renderRows();
  };
  window.__applyFieldPatch=function(key, patch){
    var t=taskByKey(key); if(!t) return;
    applyTaskFields(t, patch); renderRows();
    var dEl=$('drawer');
    if(dEl && dEl.classList.contains('open')){
      var ka=dEl.querySelector('.key');
      if(ka && ka.textContent===key) renderDrawer(t);
    }
  };
  window.__rerenderRows=renderRows;
  window.__applyNotePatch=function(key, has){
    var t=TASKS.filter(function(x){ return x.key===key; })[0];
    if(t && !!t.hasNote!==has){ t.hasNote=has; renderRows(); }
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
      customs:d.customs||[], canCustom:(d.status==='TO DO'||d.status==='In Progress'),
      assignee:{ name:d.assignee||'—', init:initOf(d.assignee||'?'), cls:avById(d.assignee||'?') },
      due:d.duedate||'', dueDisp:d.duedate||'Chưa đặt hạn', dueCls:'',
      created:d.created||'', createdDisp:d.created||'—',
      overdue:false, stuck:false, isNew:false,
      jiraUrl:(window.__jiraBase||'')+'/browse/'+key };
  }
  function renderDrawer(t){
    var chips=(t.customs&&t.customs.length)?t.customs.map(function(v){
      return '<span class="cust-chip"><span class="material-symbols-rounded ph-light ph-circle"></span>'+esc(custMap[v]||v)+'</span>';}).join('')
      :'<span style="color:var(--on-surface-variant)">—</span>';
    var flags='';
    if(t.overdue) flags+='<span class="dt-flag od"><span class="material-symbols-rounded ph-light ph-calendar-x mi-xs"></span>Quá hạn</span>';
    if(t.stuck) flags+='<span class="dt-flag st"><span class="material-symbols-rounded ph-light ph-hourglass mi-xs"></span>Kẹt</span>';
    if(!flags) flags='<span style="color:var(--on-surface-variant)">—</span>';
    var list=COMMENTS[t.key], hist;
    if(list==null) hist=skelComments();
    else if(!list.length) hist='<div class="cmt-empty">Chưa có bình luận nào</div>';
    else hist=list.map(function(c){ return '<div class="cmt-item"><span class="av '+avById(c.author)+'">'+esc(initOf(c.author))+'</span>'
      +'<div class="cmt-main"><div class="cmt-meta"><b>'+esc(c.author)+'</b><span>'+esc((c.when||'').slice(0,16).replace('T',' '))+'</span></div>'
      +'<div class="cmt-text">'+esc(c.body)+'</div></div></div>'; }).join('');
    var desc=(DETAIL[t.key]&&DETAIL[t.key].description)?esc(DETAIL[t.key].description):esc(t.summary);
    drawer.innerHTML='<div class="drawer-head"><a class="key" href="'+esc(t.jiraUrl)+'" target="_blank">'+esc(t.key)+'</a>'
      +'<span class="badge '+badgeCls(t.jira)+'">'+esc(t.jira)+'</span>'
      +'<button class="drawer-edit material-symbols-rounded ph-light ph-pencil-simple" data-act="edit-toggle" title="Sửa task (tiêu đề / người xử lý / hạn)"></button>'
      +'<button class="x material-symbols-rounded ph-light ph-x" data-act="drawer-close"></button></div>'
      +'<div class="drawer-body"><h2>'+esc(t.summary)+'</h2>'
      +'<div class="dt-grid"><div class="lbl">Người xử lý</div><div class="val"><span class="assignee"><span class="av '+esc(t.assignee.cls)+'">'+esc(t.assignee.init)+'</span> '+esc(t.assignee.name)+'</span></div>'
      +'<div class="lbl">Ngày tạo</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].created)?esc(DETAIL[t.key].created):esc(t.createdDisp||'—'))+'</div>'
      +'<div class="lbl">Hạn chót</div><div class="val" id="dueVal-'+esc(t.key)+'">'+dueValHTML(t)+'</div>'
      +'<div class="lbl">Cập nhật</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].updated)?esc(DETAIL[t.key].updated):'—')+'</div>'
      +'<div class="lbl">Dev phụ trách</div><div class="val">'+((DETAIL[t.key]&&DETAIL[t.key].devs&&DETAIL[t.key].devs.length)?DETAIL[t.key].devs.map(esc).join(', '):'—')+'</div>'
      +'<div class="lbl">Nhãn nội bộ</div><div class="val">'+chips+'</div>'
      +'<div class="lbl">Cảnh báo</div><div class="val">'+flags+'</div></div>'
      +'<div class="dt-sec-title">Mô tả</div><div class="dt-desc">'+desc+'</div>'
      +bugSectionHtml(DETAIL[t.key])
      +noteSectionHtml(t.key, DETAIL[t.key])
      +'<div class="dt-cmts"><div class="dt-sec-title">Bình luận ('+(list&&list.length||0)+')</div>'
      +'<div class="cmt-panel"><div class="cmt-history">'+hist+'</div>'
      +'<div class="cmt-box"><textarea id="dtTa-'+esc(t.key)+'" placeholder="Viết bình luận... (gõ @ để nhắc người)"></textarea>'
      +'<div class="cmt-foot"><button class="lbtn primary" data-act="dt-send" data-key="'+esc(t.key)+'">Gửi</button></div></div></div></div></div>';
  }
  function openDetail(key){
    ov.classList.add('open'); drawer.classList.add('open');
    if(CUR[key]) renderDrawer(CUR[key]);
    else drawer.innerHTML='<div class="drawer-body">'+skelDrawer()+'</div>';
    if(COMMENTS[key]===undefined){ COMMENTS[key]=null;
      getJSON('/issue-comments?key='+encodeURIComponent(key), 20000).then(function(j){
        if(j&&j.ok&&j.detail){ COMMENTS[key]=j.detail.comments||[]; DETAIL[key]=j.detail; CUR[key]=synth(key,j.detail); }
        else COMMENTS[key]=COMMENTS[key]||[];
        if(CUR[key] && drawer.classList.contains('open')) renderDrawer(CUR[key]);
      }).catch(function(){ COMMENTS[key]=COMMENTS[key]||[]; });
    }
  }
  window.__openDetail=openDetail;
  window.__applyDuePatch=function(key, val){ if(CUR[key]){ recomputeDue(CUR[key], val);
    if(drawer.classList.contains('open')) renderDrawer(CUR[key]); } };
  window.__applyFieldPatch=function(key, patch){ var t=CUR[key]; if(!t) return;
    applyTaskFields(t, patch); if(drawer.classList.contains('open')) renderDrawer(t); };
  function closeDetail(){ ov.classList.remove('open'); drawer.classList.remove('open'); }
  if(ov) ov.addEventListener('click', closeDetail);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') closeDetail(); });
  document.addEventListener('click', function(e){
    var a=e.target.closest('[data-act]'); if(!a) return;
    var act=a.getAttribute('data-act');
    if(act==='drawer-close') closeDetail();
    else if(act==='smenu'){ var sk=a.getAttribute('data-key');
      if(CUR[sk]) window.__openSmenu(a, CUR[sk], { onChanged: function(kind, key){
        if(CUR[key]) renderDrawer(CUR[key]); } }); }
    else if(act==='dt-send'){ var key=a.getAttribute('data-key');
      var ta=$('dtTa-'+key), v=(ta&&ta.value||'').trim(); if(!v){ toast('Chưa nhập bình luận', false); return; }
      postJSON('/add-comment', { key:key, body:v }, 20000).then(function(j){ if(patToast(j)) return;
        if(j.ok){ (COMMENTS[key]=COMMENTS[key]||[]).push({author:'Bạn', when:new Date().toISOString(), body:v});
          if(CUR[key]) renderDrawer(CUR[key]); toast('Đã gửi comment ✓', true); }
        else toast(j.msg||'Lỗi gửi comment', false); }).catch(function(){ toast('Lỗi mạng', false); }); }
  });
})();

// ================= HÔM NAY (guard #todayPage — Decision #102) =================
// Trang không có #rows -> drawer là SHARED DRAWER ở trên. Hàng mention: mở + đánh dấu đã đọc.
(function(){
  var page=$('todayPage'); if(!page) return;
  page.addEventListener('click', function(e){
    if(e.target.closest('a[href]')) return;              // key -> mở Jira tab mới như bình thường
    var row=e.target.closest('[data-today-open]'); if(!row) return;
    var key=row.getAttribute('data-today-open'), id=row.getAttribute('data-actid');
    if(id){ postJSON('/dismiss', { ids:[id] }, 20000).catch(function(){});
      row.classList.add('read'); }
    if(key && window.__openDetail) window.__openDetail(key);
  });
})();

// ================= DOCUMENTS (guard #folderGrid) =================
(function(){
  var grid = $('folderGrid'); if(!grid) return;
  var EDIT = !!window.QA_DOCS_EDITABLE;
  var DOC_TREE = readJSON('docsData') || [];
  var currentPath = []; // Mảng lưu trữ đường dẫn thư mục hiện tại từ root
  var showAllDocs = false; // "Xem tất cả": bỏ giới hạn 5 tài liệu ở màn gốc
  var contextMenuSelectedId = null;
  var viewerDocId = null;   // tài liệu đang mở trong viewer (đồng bộ ?doc= trên URL)
  var urlSuppress = false;  // đang dựng lại từ URL -> không ghi URL (tránh vòng lặp)

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
    showAllDocs = false;
    buildPathToFolder(DOC_TREE, folderId, currentPath);
    updateBreadcrumbs();
    renderFolders();
    renderTable();
    writeUrl(true);
  };

  window.navigateBackToRoot = function() {
    currentPath = [];
    showAllDocs = false;
    updateBreadcrumbs();
    renderFolders();
    renderTable();
    writeUrl(true);
  };

  // "Xem tất cả": ở màn gốc bỏ giới hạn 5 -> liệt kê toàn bộ tài liệu (vẫn sắp mới nhất).
  window.viewAllDocuments = function() {
    currentPath = [];
    showAllDocs = true;
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
      tableTitle.textContent = showAllDocs ? 'Tất cả tài liệu' : 'Tài liệu gần đây';
      if (viewAllDocs) viewAllDocs.style.display = showAllDocs ? 'none' : 'block';
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

    // Kiểu Drive: không có thư mục con thì bỏ luôn mục "Thư mục" (kể cả ở gốc) —
    // thông báo trống để bảng tài liệu lo, tránh 2 khối rỗng cùng lúc.
    if (subfolders.length === 0) {
      grid.innerHTML = '';
      section.style.display = 'none';
      applyProcMode();
      return;
    }

    grid.innerHTML = subfolders.map(function(f) {
      var proc = isProcFolder(f);
      var count = proc ? procFiles(f).length : getFolderCount(f);
      var act = EDIT ? '<button class="action-btn folder-act material-symbols-rounded ph-light'
          + ' ph-dots-three-vertical" data-fid="' + esc(f.id) + '" title="Tuỳ chọn thư mục"></button>' : '';
      return '<div class="folder-card" onclick="navigateToFolder(\'' + esc(f.id) + '\')">' +
        '<div class="folder-icon-box folder-' + esc(f.color || 'blue') + '">' +
          '<span class="material-symbols-rounded ph-light ' + (proc ? 'ph-flow-arrow' : 'ph-folder') + '"></span>' +
        '</div>' +
        '<div class="folder-info">' +
          '<div class="folder-name">' + esc(f.name) + '</div>' +
          '<div class="folder-count">' + count + (proc ? ' quy trình' : ' tài liệu') + '</div>' +
        '</div>' +
        act +
      '</div>';
    }).join('');
    applyProcMode();
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
    // Tên hiển thị có thể do người dùng đặt (không đuôi) -> lấy đuôi từ URL upload luôn
    if (checkExt === 'html' || checkExt === 'htm'
        || /^\/uploads\/.+\.html?($|\?)/i.test(url || '')) return { icon: 'code', cls: 'file-html' };

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

  // ===== Folder "Quy Trình": chế độ TAB, mỗi file HTML = 1 tab xem ngay trong app (#66) =====
  // Folder được đánh dấu bằng `kind:'process'` (server tự đảm bảo có, xem docs.py).
  function isProcFolder(node) {
    return !!node && node.type === 'folder'
      && (node.kind === 'process' || node.name === 'Quy Trình');
  }
  function isHtmlDoc(d) {
    return d && d.type === 'link' && /\.html?($|\?)/i.test(String(d.url || ''));
  }
  function procFiles(folder) {
    return ((folder && folder.children) || []).filter(isHtmlDoc);
  }
  function curProcFolder() {
    var f = currentPath.length ? currentPath[currentPath.length - 1] : null;
    return isProcFolder(f) ? f : null;
  }

  var procActiveId = null;   // tab đang xem
  var procShownId = null;    // tab đã nạp iframe (tránh reload lại khi chỉ vẽ lại thanh tab)

  // Bật/tắt chế độ tab. Gọi ở cuối renderFolders + đầu renderTable nên mọi
  // điều hướng/thao tác đều đi qua đây.
  function applyProcMode() {
    var sec = $('procSection'), list = $('docsListSection'), fsec = $('foldersSection');
    if (!sec) return;                                  // template cũ chưa có viewer tab
    var folder = curProcFolder();
    if (!folder) {
      sec.style.display = 'none';
      if (list) list.style.display = '';
      procActiveId = procShownId = null;
      var b = $('procBody'); if (b) b.innerHTML = '';   // gỡ iframe -> dừng tải
      return;
    }
    sec.style.display = 'block';
    if (list) list.style.display = 'none';
    if (fsec) fsec.style.display = 'none';
    renderProcess(folder);
  }

  function renderProcess(folder) {
    var tabsEl = $('procTabs'), body = $('procBody');
    if (!tabsEl || !body) return;
    var files = procFiles(folder);
    var others = ((folder.children || []).length - files.length);

    if (!files.length) {
      tabsEl.innerHTML = others
        ? '<div class="proc-note">' + others + ' tệp không phải HTML bị ẩn — thư mục này chỉ hiển thị file HTML.</div>'
        : '';
      body.innerHTML = '<div class="empty-state"><div class="es-ic">' + phIcon('code') + '</div>'
        + '<div class="es-title">Chưa có quy trình nào</div>'
        + '<div class="es-hint">' + (EDIT ? 'Tải lên file HTML để tạo tab mới.'
            : 'Quản lý cần tải lên file HTML để hiển thị ở đây.') + '</div></div>';
      procActiveId = procShownId = null;
      return;
    }

    // tab đang chọn còn tồn tại? nếu không -> về tab đầu
    if (!files.some(function(f) { return f.id === procActiveId; })) {
      procActiveId = files[0].id;
      writeUrl(false);                   // ?doc= khớp tab thực tế (replace, không dồn history)
    }

    tabsEl.innerHTML = files.map(function(f) {
      var on = f.id === procActiveId;
      return '<button class="proc-tab' + (on ? ' active' : '') + '" data-id="' + esc(f.id) + '"'
        + ' title="' + esc(f.name) + '">'
        + phIcon('code', 'mi-sm')
        + '<span class="pt-name">' + esc(String(f.name).replace(/\.html?$/i, '')) + '</span>'
        + (EDIT ? '<span class="pt-x material-symbols-rounded ph-light ph-x" data-del="' + esc(f.id) + '"'
                  + ' title="Xoá quy trình này"></span>' : '')
        + '</button>';
    }).join('')
      + (others ? '<div class="proc-note">' + others + ' tệp không phải HTML bị ẩn</div>' : '');

    if (procActiveId !== procShownId) {
      var doc = files.filter(function(f) { return f.id === procActiveId; })[0];
      var raw = fpOpenUrl(safeDocUrl(doc.url) || '');
      // sandbox KHÔNG có allow-same-origin -> origin mờ, script trong file không
      // chạm session/DOM của app (giống viewer overlay, Decision #65).
      // fit=1: file tự báo chiều cao qua postMessage -> iframe cao bằng nội dung,
      // xem hết trong trang thay vì cuộn trong khung.
      body.innerHTML = raw
        ? '<iframe class="proc-frame" id="procFrame" src="' + esc(raw)
          + (raw.indexOf('/file-raw?') === 0 ? '&fit=1' : '') + '" '
          + 'sandbox="allow-scripts allow-popups allow-forms allow-modals" '
          + 'referrerpolicy="no-referrer" title="' + esc(doc.name) + '"></iframe>'
        : '<div class="empty-state"><div class="es-title">Link tài liệu không hợp lệ</div></div>';
      procShownId = procActiveId;
    }
  }

  // Chiều cao do chính file báo lên (origin mờ nên không đọc được từ ngoài).
  // Chỉ nhận message đến TỪ iframe đang hiện (e.source), bỏ qua mọi nguồn khác.
  window.addEventListener('message', function(e) {
    var fr = $('procFrame');
    if (!fr || !e.source || e.source !== fr.contentWindow) return;
    var h = e.data && e.data.__fitHeight;
    if (typeof h !== 'number' || !isFinite(h)) return;
    // KHÔNG cộng bù (dù 1px): mỗi lần set height sinh 'resize' trong iframe -> báo lại,
    // cộng bù sẽ phình dần mỗi vòng. Đặt đúng số đo.
    var v = Math.max(320, Math.min(Math.round(h), 40000));
    if (Math.abs(parseFloat(fr.style.height) - v) < 2) return;
    fr.style.height = v + 'px';
  });

  var procTabsEl = $('procTabs');
  if (procTabsEl) {
    procTabsEl.addEventListener('click', function(e) {
      var del = e.target.closest('.pt-x');
      if (del) {
        e.stopPropagation();
        procDelete(del.getAttribute('data-del'));
        return;
      }
      var tab = e.target.closest('.proc-tab');
      if (!tab) return;
      procActiveId = tab.getAttribute('data-id');
      applyProcMode();
      writeUrl(true);                    // ?doc=<tab> -> share/F5/Back giữ đúng tab
    });
  }

  function procDelete(id) {
    if (!EDIT) return;
    var doc = findFileById(DOC_TREE, id);
    if (!doc) return;
    confirmModal({ title: 'Xoá quy trình', message: 'Xoá "' + doc.name + '" khỏi thư mục Quy Trình?',
                   confirmText: 'Xoá' }).then(function(ok) {
      if (!ok) return;
      var info = findFileParentAndIndex(DOC_TREE, id);
      if (!info) return;
      info.parentList.splice(info.index, 1);
      if (procActiveId === id) procActiveId = null;
      procShownId = null;
      renderFolders();
      renderTable();
      saveDocs();
      showBottomToast('Đã xoá quy trình: ' + doc.name);
    });
  }

  var procUp = $('procUpBtn');
  if (procUp) procUp.addEventListener('click', function() { openModal('uploadModal'); });

  function renderTable() {
    applyProcMode();
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

    // Màn gốc = "Tài liệu gần đây": sắp theo ngày sửa mới nhất, chỉ giữ 5 tài liệu
    // (khi không tìm kiếm — search vẫn ra hết để còn tìm được). Tài liệu thiếu ts xuống cuối.
    if (currentPath.length === 0) {
      filtered.sort(function(a, b) { return (b.ts || 0) - (a.ts || 0); });
      if (!query && !showAllDocs) filtered = filtered.slice(0, 5);
    }

    // Kiểu Google Drive: thư mục chỉ chứa thư mục con -> KHÔNG hiện bảng rỗng, chỉ hiện
    // lưới thư mục. Bảng chỉ xuất hiện khi thật sự có tài liệu (hoặc đang tìm kiếm).
    var hasSub = (currentNode.children || []).some(function(n) { return n.type === 'folder'; });
    var list = $('docsListSection');
    if (list && !curProcFolder()) {
      list.style.display = (!files.length && hasSub && !query) ? 'none' : '';
      if (list.style.display === 'none') return;
    }

    if (filtered.length === 0) {
      var cols = EDIT ? 3 : 2;
      var ic, title, hint;
      if (query) {
        ic = 'search_off'; title = 'Không tìm thấy tài liệu khớp';
        hint = 'Thử từ khoá khác hoặc xoá ô tìm kiếm.';
      } else if (currentPath.length) {
        ic = 'folder_open'; title = 'Thư mục này đang trống';
        hint = EDIT ? 'Tải lên tài liệu hoặc thêm link Drive để bắt đầu.' : '';
      } else {
        ic = 'folder_off'; title = 'Chưa có tài liệu nào';
        hint = EDIT ? 'Tạo thư mục rồi tải tài liệu lên.' : '';
      }
      tbody.innerHTML = '<tr><td colspan="' + cols + '">'
        + '<div class="empty-state"><div class="es-ic">' + phIcon(ic) + '</div>'
        + '<div class="es-title">' + title + '</div>'
        + (hint ? '<div class="es-hint">' + hint + '</div>' : '')
        + '</div></td></tr>';
      return;
    }

    tbody.innerHTML = filtered.map(function(d) {
      var fileData = getFileIconClass(d.name, d.type, d.url);
      var actCol = EDIT ? '<td class="action-col" onclick="event.stopPropagation()">' +
          '<button class="action-btn material-symbols-rounded ph-light ph-dots-three-vertical" onclick="openContextMenu(event, \'' + esc(d.id) + '\')"></button>' +
        '</td>' : '';
      return '<tr class="doc-row" data-id="' + esc(d.id) + '" data-url="' + esc(d.url) + '">' +
        '<td>' +
          '<div class="file-name-cell">' +
            '<span class="file-icon-wrapper ' + esc(fileData.cls) + '">' +
              phIcon(fileData.icon) +
            '</span>' +
            '<span class="file-name">' + esc(d.name.replace(/\.url$/i, '')) + '</span>' +
          '</div>' +
        '</td>' +
        '<td class="date-modified">' + esc(fmtDocDate(d.ts)) + '</td>' +
        actCol +
      '</tr>';
    }).join('');
    animRows(tbody);
  }

  // Chỉ mở link an toàn (chặn javascript:/data: kể cả khi lọt qua validate server)
  function safeDocUrl(u){ return /^(https?:\/\/|\/uploads\/)/i.test(u||'') ? u : null; }

  // ===== Viewer: xem tài liệu NGAY trong app thay vì mở tab mới (Decision #63) =====
  // - /uploads/*.pdf + ảnh  -> browser render thẳng (iframe/img)
  // - /uploads/*.html/.htm  -> iframe /file-raw (sandbox, giữ nguyên CSS/layout) — #65
  // - docx/xlsx/pptx/text   -> GET /file-preview dựng HTML server-side (zero-dep)
  // - link Google Drive     -> nhúng iframe bản /preview của Google
  // - còn lại               -> báo không xem trước được, còn nút Tải xuống / Mở tab mới
  var fpOv = $('fpOverlay'), fpBody = $('fpBody');

  function fpExt(name, url) {
    var s = String(name || '').replace(/\.url$/i, '');
    if (s.indexOf('.') < 0) s = String(url || '').split('?')[0];
    var m = /\.([a-z0-9]+)$/i.exec(s);
    return m ? m[1].toLowerCase() : '';
  }

  // Link Google -> URL nhúng iframe được (/preview). null nếu không nhúng được (vd folder).
  function fpDriveEmbed(u) {
    var m = /^https:\/\/docs\.google\.com\/(document|spreadsheets|presentation)\/d\/([A-Za-z0-9_-]+)/.exec(u);
    if (m) return 'https://docs.google.com/' + m[1] + '/d/' + m[2] + '/preview';
    m = /^https:\/\/drive\.google\.com\/file\/d\/([A-Za-z0-9_-]+)/.exec(u);
    if (m) return 'https://drive.google.com/file/d/' + m[1] + '/preview';
    m = /^https:\/\/drive\.google\.com\/open\?id=([A-Za-z0-9_-]+)/.exec(u);
    if (m) return 'https://drive.google.com/file/d/' + m[1] + '/preview';
    return null;
  }

  // URL để MỞ TAB MỚI: html local phải qua /file-raw (vì /uploads/ serve attachment)
  function fpOpenUrl(u) {
    if (!/^\/uploads\/.+\.html?($|\?)/i.test(u || '')) return u;
    return '/file-raw?f=' + encodeURIComponent(decodeURIComponent(u.replace(/^\/uploads\//i, '')));
  }

  // Định dạng browser tự render được khi mở thẳng `/uploads/...` — đúng tập được serve
  // `inline` ở `_get_uploads` (#70). Ngoài tập này `/uploads/` trả `attachment` -> mở tab
  // mới là TẢI VỀ chứ không xem được.
  var FP_NATIVE_TAB = ['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp'];

  // URL cho nút "Mở tab mới" / menu "Mở link". Khác `fpOpenUrl` (dùng cho src iframe):
  // docx/xlsx/pptx/text không có bản thô nào browser render được -> trỏ `/file-view`
  // (trang xem TOÀN MÀN HÌNH, không sidebar/overlay) thay vì bắn attachment về máy.
  function fpTabUrl(u) {
    u = u || '';
    if (!/^\/uploads\//i.test(u)) return u;             // link Drive: giữ URL Google
    var ext = fpExt('', u);
    if (/^html?$/.test(ext)) return fpOpenUrl(u);        // HTML -> /file-raw (sandbox, #65)
    if (FP_NATIVE_TAB.indexOf(ext) >= 0) return u;       // pdf/ảnh: browser render inline
    return '/file-view?f=' + encodeURIComponent(decodeURIComponent(u.replace(/^\/uploads\//i, '')));
  }

  function fpClose() {
    if (!fpOv) return;
    var wasOpen = fpOv.classList.contains('open');
    fpOv.classList.remove('open');
    if (fpBody) fpBody.innerHTML = '';   // gỡ iframe -> dừng tải/phát nội dung
    viewerDocId = null;
    if (wasOpen) writeUrl(true);         // bỏ ?doc= -> Back quay lại tài liệu vừa xem
  }

  function fpFallback(url, msg) {
    return '<div class="empty-state"><div class="es-ic">' + phIcon('visibility_off') + '</div>'
      + '<div class="es-title">' + esc(msg || 'Không xem trước được định dạng này') + '</div>'
      + '<div class="es-hint">Dùng nút “Tải xuống” hoặc “Mở tab mới” ở trên để mở bản gốc.</div></div>';
  }

  window.openDocPreview = function(doc) {
    if (!doc) return;
    var url = safeDocUrl(doc.url);
    if (!url) { toast('Link tài liệu không hợp lệ', false); return; }
    if (!fpOv || !fpBody) { window.open(url, '_blank'); return; }   // template cũ chưa có viewer

    var name = String(doc.name || '').replace(/\.url$/i, '');
    var ext = fpExt(doc.name, url);
    var local = /^\/uploads\//i.test(url);
    var icon = getFileIconClass(doc.name || '', doc.type, doc.url);
    var fname = local ? decodeURIComponent(url.replace(/^\/uploads\//i, '')) : '';
    var rawUrl = fpOpenUrl(url);   // html local -> /file-raw (render được), còn lại giữ nguyên

    $('fpTitle').textContent = name || 'Tài liệu';
    $('fpSub').textContent = local ? (ext ? ext.toUpperCase() + ' · lưu trên hệ thống' : 'Lưu trên hệ thống')
                                   : 'Google Drive';
    var ic = $('fpIcon');
    if (ic) ic.className = 'material-symbols-rounded ph-light fp-head-ic ' + esc(icon.cls);
    var dl = $('fpDownload'), nt = $('fpNewTab');
    if (dl) { dl.href = url; dl.style.display = local ? '' : 'none'; }
    // /uploads/ serve attachment với mọi định dạng ngoài pdf+ảnh -> tab mới KHÔNG được trỏ
    // thẳng vào đó (sẽ tải về). fpTabUrl chọn /file-raw | /uploads | deep-link viewer.
    if (nt) nt.href = fpTabUrl(url);
    fpBody.innerHTML = '<div class="fp-loading"><div class="skel skel-line w60"></div>'
      + '<div class="skel skel-line w80"></div><div class="skel skel-block"></div></div>';
    fpOv.classList.add('open');
    viewerDocId = doc.id;
    writeUrl(true);                      // ?doc=<id> -> share được đúng tài liệu đang xem

    if (!local) {                                   // link Drive
      var emb = fpDriveEmbed(url);
      fpBody.innerHTML = emb
        ? '<iframe class="fp-frame" src="' + esc(emb) + '" allow="autoplay"></iframe>'
        : fpFallback(url, 'Link này Google không cho nhúng xem trước');
      return;
    }
    if (ext === 'pdf') {
      fpBody.innerHTML = '<iframe class="fp-frame" src="' + esc(url) + '#view=FitH"></iframe>';
      return;
    }
    // HTML: render NGUYÊN BẢN (giữ CSS/layout) qua /file-raw. Sandbox KHÔNG có
    // allow-same-origin -> origin mờ: script trong file không chạm session/DOM app.
    if (ext === 'html' || ext === 'htm') {
      fpBody.innerHTML = '<iframe class="fp-frame" src="' + esc(rawUrl) + '" '
        + 'sandbox="allow-scripts allow-popups allow-forms allow-modals" '
        + 'referrerpolicy="no-referrer"></iframe>';
      return;
    }
    if (['png','jpg','jpeg','gif','webp','svg','bmp'].indexOf(ext) >= 0) {
      fpBody.innerHTML = '<div class="fp-img-wrap"><img class="fp-img" src="' + esc(url) + '" alt="' + esc(name) + '"></div>';
      return;
    }
    getJSON('/file-preview?f=' + encodeURIComponent(fname), 30000).then(function(j) {
      if (!fpOv.classList.contains('open')) return;        // user đã đóng trong lúc chờ
      fpBody.innerHTML = (j && j.ok && j.html) ? j.html : fpFallback(url, (j && j.msg) || '');
      fpBody.scrollTop = 0;
    }).catch(function() {
      if (fpOv.classList.contains('open')) fpBody.innerHTML = fpFallback(url, 'Lỗi tải nội dung xem trước');
    });
  };

  // Đổi sheet xlsx (tab đáy kiểu Excel) — markup do /file-preview dựng, không kèm script
  if (fpBody) fpBody.addEventListener('click', function(e) {
    var tb = e.target.closest ? e.target.closest('.fp-xls-tab') : null;
    if (!tb) return;
    var box = tb.closest('.fp-xls'), id = tb.getAttribute('data-sheet');
    if (!box) return;
    box.querySelectorAll('.fp-xls-tab').forEach(function(b) { b.classList.toggle('active', b === tb); });
    box.querySelectorAll('.fp-xls-pane').forEach(function(p) {
      var on = p.getAttribute('data-sheet') === id;
      p.classList.toggle('active', on);
      if (on) { var w = p.querySelector('.fp-grid-wrap'); if (w) { w.scrollTop = 0; w.scrollLeft = 0; } }
    });
  });

  if (fpOv) {
    fpOv.addEventListener('click', function(e) { if (e.target === fpOv) fpClose(); });
    var fpX = $('fpClose');
    if (fpX) fpX.addEventListener('click', fpClose);
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape' && fpOv.classList.contains('open')) { e.stopPropagation(); fpClose(); }
    }, true);
  }

  // Mở tài liệu qua delegated listener (KHÔNG inline onclick -> không chèn JS qua url)
  var docTbody = $('docTableBody');
  if (docTbody) {
    docTbody.addEventListener('click', function(e) {
      var row = e.target.closest('.doc-row');
      if (!row) return;
      var doc = findFileById(DOC_TREE, row.getAttribute('data-id'));
      if (doc) openDocPreview(doc);
      else { var u = safeDocUrl(row.getAttribute('data-url')); if (u) window.open(u, '_blank'); }
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

  window.previewDoc = function() {
    var doc = findFileById(DOC_TREE, contextMenuSelectedId);
    if (doc) openDocPreview(doc);
  };

  window.openLink = function() {
    var doc = findFileById(DOC_TREE, contextMenuSelectedId);
    var u = doc && safeDocUrl(doc.url);
    if (u) window.open(fpTabUrl(u), '_blank');
  };

  window.copyDocLink = function() {
    var doc = findFileById(DOC_TREE, contextMenuSelectedId);
    if (!doc) return;
    // File trên hệ thống: `/uploads/...` là đường dẫn TƯƠNG ĐỐI, dán ra ngoài vô dụng ->
    // copy deep-link tuyệt đối của workspace. Link Drive thì giữ nguyên URL Google.
    var link = doc.url;
    if (/^\/uploads\//i.test(doc.url || '')) {
      var pid = findParentFolderOfFile(DOC_TREE, doc.id, null);
      link = location.origin + '/docs?'
        + (pid && pid !== 'root' ? 'folder=' + encodeURIComponent(pid) + '&' : '')
        + 'doc=' + encodeURIComponent(doc.id);
    }
    navigator.clipboard.writeText(link).then(function() {
      toast('Đã sao chép link tài liệu vào Clipboard', true);
    });
  };

  window.deleteDoc = function() {
    var indexInfo = findFileParentAndIndex(DOC_TREE, contextMenuSelectedId);
    if (!indexInfo) return;
    confirmModal({title:'Xoá tài liệu', message:'Bạn có chắc chắn muốn xoá tài liệu này?', confirmText:'Xoá'}).then(function(ok){
      if(!ok) return;
      var docName = indexInfo.parentList[indexInfo.index].name;
      indexInfo.parentList.splice(indexInfo.index, 1);
      if (viewerDocId === contextMenuSelectedId) { viewerDocId = null; fpClose(); }
      renderFolders();
      renderTable();
      writeUrl(false);                   // URL trỏ tài liệu vừa xoá -> sửa lại tại chỗ
      saveDocs();
      showBottomToast('Đã xoá tài liệu: ' + docName);
    });
  };

  // ===== Thao tác THƯ MỤC (đổi tên / xoá) — trước đây chỉ tài liệu có context menu =====
  var folderMenuId = null;

  // capture=true: card có inline onclick="navigateToFolder(...)" (bubble) nên phải chặn
  // TRƯỚC nó, không thì bấm "…" vừa mở menu vừa nhảy vào thư mục.
  grid.addEventListener('click', function(e) {
    var btn = e.target.closest('.folder-act');
    if (!btn) return;
    e.stopPropagation();
    e.preventDefault();
    folderMenuId = btn.getAttribute('data-fid');
    var menu = $('folderMenu');
    if (!menu) return;
    var cm = $('contextMenu'); if (cm) cm.classList.remove('open');
    menu.style.top = (e.clientY + window.scrollY) + 'px';
    menu.style.left = (e.clientX - 160 + window.scrollX) + 'px';
    menu.classList.add('open');
  }, true);

  // Dùng lại modal "Tạo thư mục" ở chế độ sửa (ẩn ô thư mục cha)
  window.renameFolderPrompt = function() {
    var f = findFolderById(DOC_TREE, folderMenuId);
    if (!f) return;
    openModal('folderModal');
    var inp = $('folderNameInp');
    if (inp) inp.value = f.name;
    var pf = $('folderParentField');
    if (pf) pf.style.display = 'none';
    document.querySelectorAll('#folderColorPicker .color-opt').forEach(function(o) {
      o.classList.toggle('selected', o.getAttribute('data-color') === (f.color || 'blue'));
    });
    var head = document.querySelector('#folderModal .modal-head h3');
    if (head) head.textContent = 'Sửa thư mục';
    var btn = document.querySelector('#folderModal .modal-foot .btn-primary');
    if (btn) {
      btn.textContent = 'Lưu thay đổi';
      btn.setAttribute('onclick', 'applyFolderEdit(\'' + esc(f.id) + '\')');
    }
  };

  window.applyFolderEdit = function(id) {
    var f = findFolderById(DOC_TREE, id);
    if (!f) return;
    var name = (($('folderNameInp') || {}).value || '').trim();
    if (!name) { toast('Vui lòng nhập tên thư mục', false); return; }
    var sel = document.querySelector('#folderColorPicker .color-opt.selected');
    f.name = name;
    f.color = sel ? sel.getAttribute('data-color') : (f.color || 'blue');
    closeModal('folderModal');
    updateBreadcrumbs();
    renderFolders();
    renderTable();
    saveDocs();
    showBottomToast('Đã cập nhật thư mục "' + name + '"');
  };

  window.deleteFolder = function() {
    var f = findFolderById(DOC_TREE, folderMenuId);
    if (!f) return;
    if (isProcFolder(f)) {
      toast('Thư mục "Quy Trình" là mặc định của hệ thống, không xoá được', false);
      return;
    }
    var files = getAllFilesRecursive(f).length;
    var subs = (f.children || []).filter(function(n) { return n.type === 'folder'; }).length;
    var extra = (files || subs)
      ? ' Bên trong còn ' + files + ' tài liệu' + (subs ? ' và ' + subs + ' thư mục con' : '') + '.'
      : '';
    confirmModal({ title: 'Xoá thư mục',
                   message: 'Xoá thư mục "' + f.name + '"?' + extra
                     + ' Tài liệu đã tải lên vẫn còn trên máy chủ nhưng sẽ mất khỏi danh sách.',
                   confirmText: 'Xoá' }).then(function(ok) {
      if (!ok) return;
      var info = findFileParentAndIndex(DOC_TREE, f.id);   // tìm theo id, dùng cho cả folder
      if (!info) return;
      info.parentList.splice(info.index, 1);
      // đang đứng trong (hoặc dưới) thư mục vừa xoá -> lùi ra ngoài
      if (currentPath.some(function(n) { return n.id === f.id; })) {
        var idx = currentPath.findIndex(function(n) { return n.id === f.id; });
        currentPath = currentPath.slice(0, idx);
      }
      updateBreadcrumbs();
      renderFolders();
      renderTable();
      writeUrl(false);                   // URL trỏ thư mục vừa xoá -> sửa lại tại chỗ
      saveDocs();
      showBottomToast('Đã xoá thư mục: ' + f.name);
    });
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
      // trả modal về chế độ TẠO (renameFolderPrompt sẽ đổi lại sau khi gọi openModal)
      var pf0 = $('folderParentField'); if (pf0) pf0.style.display = '';
      var h0 = document.querySelector('#folderModal .modal-head h3');
      if (h0) h0.textContent = 'Tạo thư mục mới';
      var b0 = document.querySelector('#folderModal .modal-foot .btn-primary');
      if (b0) { b0.textContent = 'Tạo thư mục'; b0.setAttribute('onclick', 'createFolder()'); }
      document.querySelectorAll('#folderColorPicker .color-opt').forEach(function(o, i) {
        o.classList.toggle('selected', i === 0);
      });
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

      // Cho phép chọn NHIỀU tệp + đảm bảo có ô danh sách tệp, kể cả khi template
      // (docs.py) chưa restart — JS/CSS hot-reload theo F5 nhưng Python nạp 1 lần.
      if (fileInput) fileInput.multiple = true;
      var fileList = ensureFileListBox(uploadForm);
      if (fileList) fileList.innerHTML = '';
      var proc = !!curProcFolder();
      selectFiles = [];
      if (fileInput) fileInput.accept = proc ? '.html,.htm' : '';
      var hint = dropzone ? dropzone.querySelector('.hint') : null;
      if (hint) hint.textContent = proc
        ? 'Chỉ nhận file .html / .htm — mỗi file thành 1 tab quy trình (chọn được nhiều tệp, tối đa 20MB/tệp)'
        : 'Hỗ trợ .pdf, .xlsx, .docx, .png — chọn được nhiều tệp (tối đa 20MB/tệp)';
      var mh = document.querySelector('#uploadModal .modal-head h3');
      if (mh) mh.textContent = proc ? 'Tải lên file HTML quy trình' : 'Tải lên tài liệu';
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

  // Drag and Drop & Upload (chọn + tải NHIỀU tệp cùng lúc)
  var selectFiles = [];

  window.handleFileSelect = function(event) {
    if (event.target.files && event.target.files.length) {
      handleFiles(event.target.files);
    }
    event.target.value = '';
  };

  // Tạo ô danh sách tệp trong modal nếu template chưa có (docs.py chưa restart)
  function ensureFileListBox(uploadForm) {
    var box = $('uploadFileList');
    if (box) return box;
    if (!uploadForm) return null;
    box = document.createElement('div');
    box.id = 'uploadFileList';
    box.className = 'upload-file-list';
    uploadForm.insertBefore(box, uploadForm.firstChild);
    return box;
  }

  // Tạo khay tiến trình nổi nếu template chưa có; gắn nút đóng 1 lần
  function ensureUploadTray() {
    var tray = $('uploadTray');
    if (!tray) {
      tray = document.createElement('div');
      tray.id = 'uploadTray';
      tray.className = 'upload-tray';
      tray.setAttribute('aria-hidden', 'true');
      tray.innerHTML =
        '<div class="ut-head">' +
        '<span class="material-symbols-rounded ph-light ph-cloud-arrow-up"></span>' +
        '<span class="ut-title" id="utTitle">Đang tải lên…</span>' +
        '<button class="ut-close material-symbols-rounded ph-light ph-x" id="utClose" title="Đóng"></button>' +
        '</div><div class="ut-list" id="utList"></div>';
      document.body.appendChild(tray);
    }
    var closeBtn = tray.querySelector('#utClose');
    if (closeBtn && !closeBtn.__bound) {
      closeBtn.__bound = true;
      closeBtn.addEventListener('click', function() {
        tray.classList.remove('show');
        tray.setAttribute('aria-hidden', 'true');
      });
    }
    return tray;
  }

  // Danh sách tệp đã chọn trong modal (xoá bớt được trước khi tải)
  function renderSelectedFiles() {
    var box = $('uploadFileList');
    if (!box) return;
    box.innerHTML = selectFiles.map(function(f, i) {
      return '<div class="ufl-item">' +
        '<span class="material-symbols-rounded ph-light ph-file"></span>' +
        '<span class="ufl-name" title="' + esc(f.name) + '">' + esc(f.name) + '</span>' +
        '<span class="ufl-size">' + (f.size / (1024 * 1024)).toFixed(2) + ' MB</span>' +
        '<button class="ufl-rm" data-i="' + i + '" title="Bỏ tệp này">' +
        '<span class="material-symbols-rounded ph-light ph-x"></span></button>' +
        '</div>';
    }).join('');
    box.querySelectorAll('.ufl-rm').forEach(function(b) {
      b.addEventListener('click', function() {
        selectFiles.splice(parseInt(b.getAttribute('data-i'), 10), 1);
        if (!selectFiles.length) { resetUploadModal(); return; }
        renderSelectedFiles();
        updateUploadBtn();
      });
    });
  }

  function updateUploadBtn() {
    var btn = $('uploadBtn');
    if (!btn) return;
    btn.disabled = !selectFiles.length;
    var totMB = selectFiles.reduce(function(s, f) { return s + f.size; }, 0) / (1024 * 1024);
    btn.textContent = selectFiles.length === 1
      ? 'Bắt đầu tải lên (' + totMB.toFixed(2) + ' MB)'
      : 'Tải lên ' + selectFiles.length + ' tệp (' + totMB.toFixed(2) + ' MB)';
  }

  function resetUploadModal() {
    selectFiles = [];
    var dropzone = $('dropzone');
    var uploadForm = $('uploadForm');
    var btn = $('uploadBtn');
    if (dropzone) dropzone.style.display = 'block';
    if (uploadForm) uploadForm.style.display = 'none';
    if (btn) { btn.disabled = true; btn.textContent = 'Bắt đầu tải lên'; }
  }

  function handleFiles(files) {
    var arr = Array.prototype.slice.call(files || []);
    // Thư mục Quy Trình = tab HTML -> chặn định dạng khác ngay ở client
    if (curProcFolder()) {
      var before = arr.length;
      arr = arr.filter(function(f) { return /\.html?$/i.test(f.name || ''); });
      if (arr.length < before) toast('Thư mục Quy Trình chỉ nhận file .html / .htm', false);
    }
    if (!arr.length) return;
    // gộp vào lựa chọn hiện có, khử trùng theo tên+size (chọn 2 lần không bị đúp)
    arr.forEach(function(f) {
      var dup = selectFiles.some(function(g) { return g.name === f.name && g.size === f.size; });
      if (!dup) selectFiles.push(f);
    });

    var dropzone = $('dropzone');
    var uploadForm = $('uploadForm');
    if (dropzone) dropzone.style.display = 'none';
    if (uploadForm) uploadForm.style.display = 'block';
    renderSelectedFiles();
    updateUploadBtn();
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
        handleFiles(e.dataTransfer.files);
      }
    });
  }

  // Thêm tài liệu vừa tải lên vào cây + re-render + lưu
  function addUploadedDoc(res, targetFolderId) {
    var targetFolder = targetFolderId ? findFolderById(DOC_TREE, targetFolderId) : null;
    var newDoc = {
      id: "d_" + Date.now() + "_" + Math.floor(Math.random() * 1000),
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
    // Vừa tải lên trong thư mục Quy Trình -> mở luôn tab mới
    if (curProcFolder() && isHtmlDoc(newDoc)) procActiveId = newDoc.id;
    renderFolders();
    renderTable();
    saveDocs();
  }

  // Khay tiến trình nổi góc dưới bên phải — tải tuần tự từng tệp (backend 1 tệp/request)
  function runUploadQueue(files, targetFolderId) {
    var tray = ensureUploadTray();
    var list = $('utList');
    var title = $('utTitle');
    if (!tray || !list) return;

    list.innerHTML = '';
    tray.classList.add('show');
    tray.setAttribute('aria-hidden', 'false');

    var items = files.map(function(f) {
      var el = document.createElement('div');
      el.className = 'ut-item';
      el.innerHTML = '<div class="ut-item-row"><span class="ut-name" title="' + esc(f.name) +
        '">' + esc(f.name) + '</span><span class="ut-status">Chờ…</span></div>' +
        '<div class="ut-bar"><i></i></div>';
      list.appendChild(el);
      return { file: f, el: el, bar: el.querySelector('.ut-bar i'), st: el.querySelector('.ut-status') };
    });

    var idx = 0, ok = 0, fail = 0;

    function finish() {
      if (title) title.textContent = fail
        ? ('Hoàn tất — ' + ok + ' thành công, ' + fail + ' lỗi')
        : ('Đã tải lên ' + ok + ' tệp ✔');
      if (!fail) setTimeout(function() {
        tray.classList.remove('show');
        tray.setAttribute('aria-hidden', 'true');
      }, 4500);
    }

    function next() {
      if (idx >= items.length) { finish(); return; }
      var it = items[idx];
      if (title) title.textContent = 'Đang tải lên ' + (idx + 1) + '/' + items.length + '…';
      it.st.textContent = '0%';

      var fd = new FormData();
      fd.append('file', it.file);
      var xhr = new XMLHttpRequest();
      xhr.open('POST', '/upload-file', true);

      xhr.upload.onprogress = function(e) {
        if (e.lengthComputable) {
          var pct = Math.round((e.loaded / e.total) * 100);
          it.bar.style.width = pct + '%';
          it.st.textContent = pct + '%';
        }
      };
      xhr.onload = function() {
        var res = null;
        try { res = JSON.parse(xhr.responseText); } catch (ex) {}
        if (xhr.status === 200 && res && res.ok) {
          it.bar.style.width = '100%';
          it.st.textContent = '✔';
          it.el.classList.add('ok');
          addUploadedDoc(res, targetFolderId);
          ok++;
        } else {
          it.st.textContent = '✕';
          it.el.classList.add('err');
          it.el.title = (res && res.msg) ? res.msg
            : (xhr.status === 403 ? 'Không có quyền tải lên' : ('Lỗi máy chủ ' + xhr.status));
          fail++;
        }
        idx++;
        next();
      };
      xhr.onerror = function() {
        it.st.textContent = '✕';
        it.el.classList.add('err');
        it.el.title = 'Lỗi kết nối mạng';
        fail++;
        idx++;
        next();
      };
      xhr.send(fd);
    }
    next();
  }

  // Real Upload logic — đóng modal, đẩy tiến trình xuống khay góc dưới bên phải
  window.performRealUpload = function() {
    if (!selectFiles.length) return;
    var folderSel = $('uploadFolderSel');
    var targetFolderId = folderSel ? folderSel.value : '';
    var files = selectFiles.slice();
    selectFiles = [];
    closeModal('uploadModal');
    runUploadQueue(files, targetFolderId);
  };

  // Close context menu on click outside
  document.addEventListener('click', function(e) {
    if (e.target.closest('.action-btn')) return;    // chính nút vừa mở menu
    ['contextMenu', 'folderMenu'].forEach(function(id) {
      var menu = $(id); if (menu) menu.classList.remove('open');
    });
  });

  // Đóng modal/context-menu docs bằng phím Esc
  document.addEventListener('keydown', function(e) {
    if (e.key !== 'Escape') return;
    ['folderModal', 'linkModal', 'uploadModal', 'contextMenu', 'folderMenu'].forEach(function(id) {
      var m = $(id); if (m) m.classList.remove('open');
    });
  });

  // ===== Deep-link URL: ?folder=<id> · ?doc=<id> (tab Quy Trình cũng dùng ?doc=) =====
  // Trước đây /docs là 1 route duy nhất, mọi điều hướng chỉ nằm trong JS -> không share
  // được link, F5 về gốc, Back rời trang. Giờ URL phản ánh vị trí; pushState + popstate
  // cho Back/Forward đi trong cây. Pattern giống /bug-log?bug= và /test-cases?folder=.
  function writeUrl(push) {
    if (urlSuppress || !window.history || !history.pushState) return;
    var q;
    try { q = new URLSearchParams(location.search); } catch (e) { return; }
    var fid = currentPath.length ? currentPath[currentPath.length - 1].id : '';
    if (fid) q.set('folder', fid); else q.delete('folder');
    // trong thư mục Quy Trình: ?doc = tab đang xem; nơi khác: tài liệu đang mở viewer
    var did = curProcFolder() ? (procActiveId || '') : (viewerDocId || '');
    if (did) q.set('doc', did); else q.delete('doc');
    var qs = q.toString();
    var url = location.pathname + (qs ? '?' + qs : '');
    if (url === location.pathname + location.search) return;   // không đổi -> khỏi ghi
    history[push ? 'pushState' : 'replaceState']({ docs: 1 }, '', url);
  }

  // Đọc URL -> dựng lại vị trí (dùng cho lần load đầu + popstate)
  function applyUrlState() {
    var q;
    try { q = new URLSearchParams(location.search); } catch (e) { q = null; }
    var wantFolder = q ? (q.get('folder') || '') : '';
    var wantDoc = q ? (q.get('doc') || '') : '';

    // chỉ có ?doc= -> tự suy thư mục cha để mở đúng chỗ
    if (!wantFolder && wantDoc) {
      var pid = findParentFolderOfFile(DOC_TREE, wantDoc, null);
      if (pid && pid !== 'root') wantFolder = pid;
    }

    urlSuppress = true;                       // dựng lại thì đừng ghi URL vòng lại
    currentPath = [];
    if (wantFolder && findFolderById(DOC_TREE, wantFolder)) {
      buildPathToFolder(DOC_TREE, wantFolder, currentPath);
    }
    var proc = curProcFolder();
    if (proc) {
      procActiveId = (wantDoc && findFileById(DOC_TREE, wantDoc)) ? wantDoc : null;
      procShownId = null;                     // buộc nạp lại iframe theo tab của URL
    }
    updateBreadcrumbs();
    renderFolders();
    renderTable();

    var wantView = (!proc && wantDoc) ? findFileById(DOC_TREE, wantDoc) : null;
    if (wantView) openDocPreview(wantView);
    else fpClose();
    urlSuppress = false;
  }

  window.addEventListener('popstate', applyUrlState);

  // Initial render = theo URL (link share / F5 giữ đúng chỗ). URL rác -> về gốc.
  applyUrlState();
})();

// ---------- Tạo Sub-task (modal type-ahead, NHIỀU task cha, dùng chung mọi trang v2) ----------
(function(){
  var ov = $('subOverlay'); if(!ov) return;
  var openBtn = $('createSubBtn');
  var leader = { name:'', display:'' };  // user đã chọn (optional, dùng chung mọi nhóm)
  var groupsBox = $('subGroups'), groupTpl = $('subGroupTpl'), rowTpl = $('subRowTpl');

  function stripPrefix(s){ return (s||'').trim().replace(/^\[[^\]]*\]\s*/,''); }
  // Ngày cuối tháng hiện tại (YYYY-MM-DD) — default cho Hạn chót
  function endOfMonth(){
    var d=new Date(), e=new Date(d.getFullYear(), d.getMonth()+1, 0);
    var mm=('0'+(e.getMonth()+1)).slice(-2), dd=('0'+e.getDate()).slice(-2);
    return e.getFullYear()+'-'+mm+'-'+dd;
  }
  function open(){ ov.classList.add('open');
    var due=$('subDue'); if(due && !due.value){ due.value=endOfMonth(); }
    updateCount();
    var p=$('subParentInp'); if(p) setTimeout(function(){ p.focus(); }, 60); }
  function close(){ ov.classList.remove('open'); if(subPop) subPop.classList.remove('open'); }
  function debounce(fn, ms){ var t; return function(){ var a=arguments, self=this;
    clearTimeout(t); t=setTimeout(function(){ fn.apply(self, a); }, ms||260); }; }

  // --- generic type-ahead: gắn input -> results, gọi search(url), chọn 1 mục ---
  // noChip=true -> chọn xong KHÔNG hiện chip mà xoá input để chọn tiếp (dùng cho ô "thêm task cha")
  function wireTA(inpId, resId, chipId, url, fmt, onPick, noChip){
    var inp=$(inpId), res=$(resId), chip=chipId?$(chipId):null, opts=[], active=-1;
    function place(){ var r=inp.getBoundingClientRect();   // toạ độ viewport cho position:fixed
      res.style.top=(r.bottom+4)+'px'; res.style.left=r.left+'px'; res.style.width=r.width+'px'; }
    function hide(){ res.classList.remove('open'); res.innerHTML=''; opts=[]; active=-1; }
    function show(){ place(); res.classList.add('open'); }
    function showChip(label){ if(!chip) return; chip.innerHTML = label +
        '<button type="button" class="ta-x material-symbols-rounded ph-light ph-x mi-sm" title="Bỏ chọn"></button>';
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
    function pick(i){ var o=opts[i]; if(!o) return;
      if(noChip){ onPick(o); inp.value=''; hide(); inp.focus(); }   // giữ input để thêm cha kế
      else { onPick(o); showChip(fmt(o)); hide(); }
    }
    return {
      reset:function(){ if(chip){ chip.style.display='none'; chip.innerHTML=''; } inp.style.display=''; inp.value=''; hide(); },
      set:function(o){ if(!o){ onPick(null); return; } onPick(o); if(!noChip) showChip(fmt(o)); }
    };
  }

  // Chọn 1 task cha -> thêm 1 NHÓM mới (không hiện chip; giữ input để chọn cha tiếp)
  var parentTA = wireTA('subParentInp','subParentRes',null,'/search-parents?q=',
    function(o){ return '<b>'+esc(o.key)+'</b>'+esc(o.summary||''); },
    function(o){ if(o && o.key) addGroup(o.key, o.summary||''); }, true);
  var leaderTA = wireTA('subLeaderInp','subLeaderRes','subLeaderChip','/search-people?q=',
    function(o){ return '<b>'+esc(o.display||o.name)+'</b><small>'+esc(o.name)+'</small>'; },
    function(o){ leader = o ? {name:o.name, display:o.display||o.name} : {name:'',display:''}; });

  // ===== Nhóm sub-task theo task cha =====
  function groupEls(){ return groupsBox ? Array.prototype.slice.call(groupsBox.querySelectorAll('.st-group')) : []; }
  function findGroup(key){
    var hit=null; groupEls().forEach(function(g){ if(g.getAttribute('data-parent')===key) hit=g; }); return hit;
  }
  function addRow(listEl, title, assignee){
    if(!listEl || !rowTpl) return;
    var node = rowTpl.content.firstElementChild.cloneNode(true);
    var ti = node.querySelector('.st-title'), se = node.querySelector('.st-assignee');
    if(ti) ti.value = title||'';
    if(se){ se.value = assignee||''; se.classList.toggle('unset', !se.value); }
    listEl.appendChild(node); renumber(listEl);
  }
  function ensureGroupRow(listEl){ if(listEl && !listEl.querySelector('.st-row')) addRow(listEl, '', ''); }
  function renumber(listEl){
    if(!listEl) return;
    listEl.querySelectorAll('.st-row').forEach(function(r,i){
      var idx=r.querySelector('.st-idx'); if(idx) idx.textContent=(i+1); });
  }
  function addGroup(key, summary){
    if(!groupsBox || !groupTpl || !key) return;
    var exist=findGroup(key);
    if(exist){   // đã có nhóm cho cha này -> không nhân đôi, cuộn tới + nhấp nháy
      exist.scrollIntoView({block:'center', behavior:'smooth'});
      exist.classList.add('st-group-flash'); setTimeout(function(){ exist.classList.remove('st-group-flash'); }, 900);
      toast('Task cha '+key+' đã có trong danh sách', false); return;
    }
    var node = groupTpl.content.firstElementChild.cloneNode(true);
    node.setAttribute('data-parent', key);
    var gk=node.querySelector('.st-gkey'), gs=node.querySelector('.st-gsum');
    if(gk) gk.textContent = key;
    if(gs) gs.textContent = summary||'';
    var listEl = node.querySelector('.st-list');
    // Auto-gen 2 dòng: "[QA] Viết testcase <cha>" + "[QA] Test <cha>" (QA để "Chưa gán")
    var t=stripPrefix(summary);
    addRow(listEl, '[QA] Viết testcase '+t, ''); addRow(listEl, '[QA] Test '+t, '');
    groupsBox.appendChild(node);
    // hover chip -> popup sub-task đang có của cha này
    var chip=node.querySelector('.st-gchip');
    if(chip){
      chip.addEventListener('mouseenter', function(){ clearTimeout(subPopTimer); showPop(node, key, chip); });
      chip.addEventListener('mouseleave', hidePop);
    }
    preloadSubtasks(key);   // warm cache cho popup
    reflectEmpty(); updateCount();
  }
  function removeGroup(g){ if(g) g.remove(); reflectEmpty(); updateCount(); }
  function reflectEmpty(){
    var empty=$('subGroupsEmpty'); if(empty) empty.style.display = groupEls().length ? 'none' : 'block';
  }
  function getGroups(){
    return groupEls().map(function(g){
      var items=[];
      g.querySelectorAll('.st-row').forEach(function(r){
        var t=(r.querySelector('.st-title')||{}).value||'';
        var a=(r.querySelector('.st-assignee')||{}).value||'';
        t=t.trim(); if(t) items.push({summary:t, assignee:a});
      });
      return {parent:g.getAttribute('data-parent'), summary:(g.querySelector('.st-gsum')||{}).textContent||'', items:items};
    }).filter(function(gr){ return gr.parent && gr.items.length; });
  }
  function updateCount(){
    var groups=getGroups(), n=0, assigned=0;
    groups.forEach(function(gr){ n+=gr.items.length;
      assigned += gr.items.filter(function(x){return x.assignee;}).length; });
    var c=$('subCount'), b=$('subCreate');
    if(c){
      if(!n){ c.textContent=''; }
      else { c.textContent = groups.length+' task cha · '+n+' sub-task · '+assigned+' QA được gán'
        + (n-assigned>0 ? (' · '+(n-assigned)+' chưa gán') : ''); }
    }
    if(b) b.textContent = n>1 ? ('Tạo '+n+' sub-task') : 'Tạo sub-task';
  }
  function reset(){
    leader={name:'',display:''};
    parentTA.reset(); leaderTA.reset();
    if(groupsBox) groupsBox.innerHTML='';
    var d=$('subDue'); if(d) d.value='';
    if(subPop) subPop.classList.remove('open');
    reflectEmpty(); updateCount();
  }

  // Delegation trên container: xoá nhóm / thêm dòng / xoá dòng / đổi tiêu đề / đổi QA
  if(groupsBox){
    groupsBox.addEventListener('click', function(e){
      var gdel=e.target.closest('.st-gdel');
      if(gdel){ removeGroup(gdel.closest('.st-group')); return; }
      var addR=e.target.closest('.st-add-row');
      if(addR){ var list=addR.closest('.st-group').querySelector('.st-list');
        addRow(list,'',''); updateCount();
        var last=list.querySelector('.st-row:last-child .st-title'); if(last) last.focus(); return; }
      var del=e.target.closest('.st-del');
      if(del){ var row=del.closest('.st-row'), list2=del.closest('.st-list');
        if(row) row.remove(); ensureGroupRow(list2); renumber(list2); updateCount(); return; }
    });
    groupsBox.addEventListener('input', function(e){
      if(e.target.classList.contains('st-title')) updateCount();
    });
    groupsBox.addEventListener('change', function(e){
      if(e.target.classList.contains('st-assignee')){
        e.target.classList.toggle('unset', !e.target.value); updateCount();
      }
    });
  }

  // --- popup "sub-task đang có" của task cha: hover chip -> list zoom-in, bấm 1 mục -> thêm dòng QA vào ĐÚNG nhóm ---
  var subCache={}, subPop=null, subPopTimer=null, popGroup=null, popChip=null;
  function preloadSubtasks(key){
    if(!key || subCache[key]) return;
    getJSON('/parent-subtasks?key='+encodeURIComponent(key))
      .then(function(j){ subCache[key]=(j&&j.results)||[]; })
      .catch(function(){});
  }
  function buildPop(){
    if(subPop) return subPop;
    subPop=document.createElement('div'); subPop.className='st-pop';
    document.body.appendChild(subPop);
    subPop.addEventListener('mouseenter', function(){ clearTimeout(subPopTimer); });
    subPop.addEventListener('mouseleave', hidePop);
    subPop.addEventListener('click', function(e){
      var it=e.target.closest('.stp-item'); if(!it || !popGroup) return;
      // Bấm 1 sub-task -> sinh 2 dòng QA vào nhóm của cha đang hover: "Viết testcase" + "Test"
      var list=popGroup.querySelector('.st-list'); if(!list) return;
      var s=stripPrefix(it.getAttribute('data-sum')||'');
      addRow(list, '[QA] Viết testcase '+s, ''); addRow(list, '[QA] Test '+s, ''); updateCount();
      it.classList.add('added'); toast('Đã thêm 2 dòng QA cho: '+s, true);
    });
    return subPop;
  }
  function placePop(){
    if(!subPop || !popChip) return;
    var r=popChip.getBoundingClientRect();
    subPop.style.top=(r.bottom+6)+'px'; subPop.style.left=r.left+'px';
    subPop.style.width=Math.max(r.width, 320)+'px';
  }
  function renderPop(list){
    var p=buildPop();
    if(!list.length){ p.innerHTML='<div class="stp-empty">Task cha chưa có sub-task nào</div>'; return; }
    p.innerHTML='<div class="stp-head">'+list.length+' sub-task đang có <small>· bấm để thêm dòng QA</small></div>'+
      list.map(function(s){
        var cls=/done|cancel/i.test(s.status||'')?'done':'';
        return '<div class="stp-item '+cls+'" data-sum="'+esc(s.summary||'')+'" title="'+esc(s.summary||'')+'">'+
          '<span class="stp-key">'+esc(s.key)+'</span>'+
          '<span class="stp-sum">'+esc(s.summary||'')+'</span>'+
          '<span class="stp-st">'+esc(s.status||'')+'</span>'+
          '<span class="stp-add material-symbols-rounded ph-light ph-plus mi-sm"></span></div>';
      }).join('');
  }
  function showPop(groupEl, key, chip){
    if(!key || !chip) return;
    popGroup=groupEl; popChip=chip;
    var p=buildPop(); p.classList.add('open');
    if(subCache[key]){ renderPop(subCache[key]); placePop(); return; }
    p.innerHTML='<div class="stp-loading">Đang tải sub-task…</div>'; placePop();
    var want=key;
    getJSON('/parent-subtasks?key='+encodeURIComponent(want)).then(function(j){
      var list=(j&&j.results)||[]; subCache[want]=list;
      if(p.classList.contains('open') && popChip===chip){ renderPop(list); placePop(); }
    }).catch(function(){ if(p.classList.contains('open')) p.innerHTML='<div class="stp-empty">Lỗi tải sub-task</div>'; });
  }
  function hidePop(){ subPopTimer=setTimeout(function(){ if(subPop) subPop.classList.remove('open'); }, 180); }

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
    var groups=getGroups();
    var start=($('subStart').value||'').trim();
    var due=($('subDue').value||'').trim();
    if(!groups.length){ toast('Chưa chọn task cha nào', false); return; }
    if(!start){ toast('Chưa chọn ngày bắt đầu', false); return; }
    if(!due){ toast('Chưa chọn hạn chót', false); return; }
    createBtn.disabled=true;
    // Nhiều cha -> gửi `groups`. Timeout dài vì tạo tuần tự N issue trên nhiều cha.
    var payloadGroups=groups.map(function(gr){ return {parent:gr.parent, items:gr.items}; });
    postJSON('/create-subtasks', { groups:payloadGroups, startDate:start,
        duedate:due, leader:leader.name }, 90000)
      .then(function(j){
        createBtn.disabled=false;
        if(!j){ toast('Lỗi tạo sub-task', false); return; }
        if(j.code==='no_pat'){ patToast(j); return; }
        var created=(j.created||[]), failed=(j.failed||[]);
        if(!created.length){
          // Tất cả fail -> báo lỗi cụ thể, GIỮ modal để sửa & thử lại
          var m = failed.length ? ('Không tạo được: '+failed[0].msg) : (j.msg||'Lỗi tạo sub-task');
          toast(m, false); return;
        }
        if(failed.length){
          toast('Đã tạo '+created.length+', lỗi '+failed.length, false);
          setTimeout(function(){ location.reload(); }, 2200);
        } else {
          toast('Đã tạo '+created.length+' sub-task ✓', true); reset(); close();
          setTimeout(function(){ location.reload(); }, 1100);
        }
      })
      .catch(function(){ createBtn.disabled=false; toast('Lỗi mạng khi tạo sub-task', false); });
  });
})();

// ================= BUG LOG (guard #bugLogData) =================
(function(){
  var DATA = readJSON('bugLogData'); if(!DATA) return;
  var BUGS = DATA.bugs||[], MONTHS = DATA.months||[];
  var SOURCES = DATA.sources||[];    // (nguồn Jira cố định — mảng rỗng; giữ cho fileBugs/activeFid no-op)
  var REOPEN = DATA.reopen||{};      // {bugKey:{count,dev,project,month,last}} reopen tích luỹ
  var base = window.__jiraBase || '';
  var activeFid = '';                // (dead sau #104: không còn picker file; luôn '' = xem tất cả)
  var curMonth = MONTHS.length ? MONTHS[0] : '';
  var page = 1, PER = 15;
  var testerFilter = '';   // lọc bảng theo tester (qa_pic); '' = tất cả
  var devFilter = '';      // lọc bảng theo dev in charge (dev_pic); '' = tất cả
  var sevFilter = '';      // lọc theo severity Jira: ''=tất cả, blocker/critical/high/medium/low/none
  // thu gọn nhóm tồn đọng / mới trong tháng (nhớ qua localStorage)
  // nhóm đang xem: 'back' = tồn đọng từ tháng trước · 'new' = mới trong tháng (2 tab riêng)
  var grpTab = 'new';
  try{ var _gt=localStorage.getItem('qa-buglog-grp'); if(_gt==='back'||_gt==='new') grpTab=_gt; }catch(e){}
  function saveGrpTab(){ try{ localStorage.setItem('qa-buglog-grp', grpTab); }catch(e){} }
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

  // ---- Tách "tồn đọng" vs "mới trong tháng" (content-based, khớp fingerprint app) ----
  // Fingerprint = project|service|summary (Decision #54) — PHẢI khớp _fpOf phía analytics
  // + fingerprint() phía Python để nhận đúng bug bị copy sang sheet tháng mới (đổi STT/ngày).
  function _bnorm(s){ return (s==null?'':(''+s)).toLowerCase().split(/\s+/).filter(Boolean).join(' '); }
  function _fpOf(b){ return _bnorm(b.project)+'|'+_bnorm(b.service)+'|'+_bnorm(b.summary); }
  // Tên sheet -> 'MM/YYYY' (Decision #49): Tn năm tường minh; Tn bare lấy năm từ created.
  function _sheetMY(mo, createdIso){
    mo = (''+(mo||'')).trim();
    var m = /^T(\d{1,2})(\d{4})$/.exec(mo);
    if(m){ var a=+m[1]; if(a>=1&&a<=12) return (a<10?'0'+a:''+a)+'/'+m[2]; }
    m = /^T(\d{1,2})$/.exec(mo);
    if(m){ var b2=+m[1]; if(b2>=1&&b2<=12){ var cr=(''+(createdIso||'')); var yy=/^\d{4}/.test(cr)?cr.slice(0,4):(''+new Date().getFullYear()); return (b2<10?'0'+b2:''+b2)+'/'+yy; } }
    return '';
  }
  // Tháng (YYYY-MM) mà tab hiện tại đại diện — suy từ tên sheet (ưu tiên) hoặc created.
  function tabYm(){
    var mb = monthScopeBugs(), cr='';
    for(var i=0;i<mb.length;i++){ if(mb[i].created){ cr=mb[i].created; break; } }
    var my = _sheetMY(curMonth, cr) || getCreatedMonthYear(cr);   // MM/YYYY
    var p=(my||'').split('/'); return p.length>=2 ? p[1]+'-'+p[0] : '';
  }
  // (SHEET-BASED, Decision #75) tồn đọng vs mới tách theo NGÀY CREATED của chính dòng đó
  // so với tháng của sheet đang xem: created < tháng-sheet = tồn đọng (mang sang từ tháng cũ,
  // team bê bug GIỮ NGUYÊN created). Đọc thẳng sheet, KHÔNG fingerprint — khớp computeBacklog.

  // ----- map mức độ / trạng thái -> class + nhãn -----
  function sevCls(s){ var t=(s||'').toLowerCase();
    if(/nghi[êe]m|critical|blocker/.test(t)) return 'sev-crit';
    if(/cao|high|major/.test(t)) return 'sev-high';
    if(/th[ấa]p|low|minor|trivial/.test(t)) return 'sev-low';
    return 'sev-med'; }
  // Trạng thái = ĐÚNG status Jira (#104, không map lifecycle). Màu badge theo tên status
  // workflow Bug Testing; tên lạ -> badge mặc định.
  var JST = {
    'TRIAGE':'st-open', 'Open':'st-open', 'To Do':'st-open', 'TO DO':'st-open',
    'In Progress':'st-fixing', 'TESTING':'st-fixing', 'PENDING':'st-fixing',
    'Reopened':'st-reopen',
    'REJECTED':'st-rejected',
    'Done':'st-closed', 'DONE':'st-closed', 'CANCELLED':'st-closed'
  };
  function stCell(s){ s=s||''; return '<span class="st-badge '+(JST[s]||'st-default')+'">'+esc(s||'—')+'</span>'; }
  // nhãn trạng thái dạng text cho export Excel = chính status Jira.
  function statusLabel(s){ return s||''; }

  // Cột "Liên kết": issue liên quan native Jira (parent + Relates), read-only — #104.
  function taskCell(b){
    var tasks = b.tasks || [];
    if(tasks.length){
      return '<span class="bl-jira-wrap">' + tasks.map(function(t){
        return '<span class="bl-jira-chip"><a class="bl-jira" href="'+esc(base)+'/browse/'+esc(t)+'" target="_blank" rel="noopener">🔗 '+esc(t)+'</a></span>';
      }).join('') + '</span>';
    }
    return '<span class="bl-nolink">⛓️‍💥 Chưa liên kết</span>';
  }

  // file đang xem: '' = tất cả, else chỉ bug có fid===activeFid
  function fileBugs(){ return activeFid ? BUGS.filter(function(b){ return b.fid===activeFid; }) : BUGS; }
  // tháng có mặt trong file đang xem (giữ thứ tự MONTHS)
  function availMonths(){ var fb=fileBugs(); return MONTHS.filter(function(m){ return fb.some(function(b){ return b.month===m; }); }); }
  // bug của ĐÚNG tháng đang chọn (không kèm filter tester/dev/link) -> nguồn cho dropdown lọc
  function monthScopeBugs(){ return fileBugs().filter(function(b){ return b.month===curMonth; }); }
  // Predicate lọc-xem (tester/dev/severity) — KHÔNG gồm điều kiện tháng, để dùng chung cho
  // cả "mới trong tháng" lẫn "tồn đọng từ tháng trước" (nợ cũ nằm ở tháng khác — #104).
  function passFilters(b){
    if(testerFilter && (b.qa||'')!==testerFilter) return false;
    if(devFilter){
      if(devFilter==='__none__'){ if((b.dev||'').trim()) return false; }
      else if((b.dev||'')!==devFilter) return false;
    }
    if(sevFilter && sevOf(b)!==sevFilter) return false;   // 'none' = chưa phân loại (#104)
    return true;
  }
  // bug ĐANG MỞ (parity Python bug_backlog.is_open: Closed/Rejected = đóng).
  function bugOpen(s){ s=(s||''); return s!=='Closed' && s!=='Rejected'; }
  function monthBugs(){ return fileBugs().filter(function(b){ return b.month===curMonth && passFilters(b); }); }
  // danh sách tester (qa_pic) phân biệt trong file đang xem -> đổ vào dropdown lọc
  function populateTesters(){
    var sel0=$('blTesterFilter'); if(!sel0) return;
    var seen={}, list=[];
    monthScopeBugs().forEach(function(b){ var q=(b.qa||'').trim();
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
    monthScopeBugs().forEach(function(b){ var d=(b.dev||'').trim();
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
    var av = availMonths();
    if(!av.length){ populateTesters(); tabs.innerHTML='<span class="bl-count">Chưa có dữ liệu cho file này.</span>'; return; }
    if(av.indexOf(curMonth)<0) curMonth=av[0];
    populateTesters();   // sau khi chốt curMonth -> dropdown chỉ liệt kê dev/tester của đúng tháng
    tabs.innerHTML = av.map(function(m){
      var n = fileBugs().filter(function(b){return b.month===m;}).length;
      return '<button class="bl-tab'+(m===curMonth?' active':'')+'" data-m="'+esc(m)+'">'
        +'<span class="material-symbols-rounded ph-light ph-calendar-dots"></span> '+esc(m)+' ('+n+')</button>';
    }).join('');
  }

  // Ô Severity: hiện ĐÚNG giá trị Jira (#104). Màu theo SEV_COLOR (inline, khỏi phụ thuộc CSS
  // class 5 mức). 'none' = field trống / giá trị lạ -> gạch ngang mờ, title nêu giá trị thô.
  function sevCell(b){
    var k = sevOf(b), raw = (b.severity||'').trim();
    if(k==='none') return '<span class="bl-sev" style="background:transparent;color:var(--on-surface-variant);border:1px solid var(--outline)" title="'
      + (raw ? 'Giá trị lạ: '+esc(raw) : 'Chưa phân loại severity')+'">—</span>';
    return '<span class="bl-sev" style="background:'+SEV_COLOR[k]+';color:#fff" title="'+esc(SEV_LABEL[k])+'">'+esc(SEV_LABEL[k])+'</span>';
  }
  function rowHTML(b){
    return '<tr data-bug="'+esc(b.key)+'">'
      +'<td><a class="bl-id key" href="'+esc(base)+'/browse/'+encodeURIComponent(b.key)+'" target="_blank" rel="noopener" title="Mở trên Jira">'+esc(b.id)+'</a></td>'
      +'<td><b>'+esc(b.summary)+'</b></td>'
      +'<td style="white-space:nowrap">'+esc(formatCreated(b.created))+'</td>'
      +'<td>'+sevCell(b)+'</td>'
      +'<td>'+stCell(b.statusRaw||b.status)+'</td>'
      +'<td>'+esc(b.qa||'—')+'</td>'
      +'<td>'+esc(b.dev||'—')+'</td>'
      +'<td>'+taskCell(b)+'</td></tr>';
  }
  // Tách tồn đọng vs mới trong tháng -> 2 tab riêng (CREATED-BASED cho nguồn Jira — #104,
  // parity Python prev_month_backlog):
  //   - Mới trong tháng  = bug created TRONG tháng của tab (b.month===curMonth).
  //   - Tồn đọng từ tháng trước = bug created < tháng tab VÀ CÒN MỞ tới giờ (lấy từ MỌI tháng,
  //     không chỉ tháng tab) -> nợ cũ chưa đóng. (Jira key ổn định, status live -> tính trực tiếp.)
  // Trả {back, fresh, active}: `active` tự lùi sang nhóm còn lại nếu nhóm đang chọn rỗng.
  function splitGroups(){
    var ym = tabYm(), back=[], fresh=[];
    fileBugs().forEach(function(b){
      if(!passFilters(b)) return;
      var cm=(b.created||'').slice(0,7);
      if(ym && cm && cm < ym){ if(bugOpen(b.status)) back.push(b); }   // nợ cũ còn treo
      else if(b.month===curMonth) fresh.push(b);                       // mới trong tháng tab
    });
    var act = grpTab;
    if(act==='back' && !back.length && fresh.length) act='new';
    else if(act==='new' && !fresh.length && back.length) act='back';
    return {back:back, fresh:fresh, active:act};
  }
  // danh sách bug ĐANG HIỂN THỊ (theo tab nhóm) — dùng cho check-all + export
  function visibleBugs(){ var g=splitGroups(); return g.active==='new' ? g.fresh : g.back; }

  function render(){
    var g = splitGroups(), ordered = g.active==='new' ? g.fresh : g.back;
    var total = ordered.length, pages = Math.max(1, Math.ceil(total/PER));
    if(page>pages) page=pages;
    var start=(page-1)*PER, slice=ordered.slice(start, start+PER);
    var cols = 8;   // ID/Mô tả/Ngày/Severity/Trạng thái/Tester/Dev/Liên kết

    // 2 tab nhóm (ẩn khi tháng không có bug nào)
    var sb=$('blSplitBar');
    if(sb){
      if(g.back.length+g.fresh.length>0){
        sb.style.display='';
        function tabHTML(k, ic, label, n){
          return '<button type="button" class="bl-tab bl-grptab g-'+(k==='back'?'back':'new')
            + (g.active===k?' active':'')+'" data-grp="'+k+'">'
            + '<span class="material-symbols-rounded ph-light '+ic+' mi-sm"></span>'
            + label+' <span class="bl-grptab-n">'+n+'</span></button>';
        }
        sb.innerHTML = tabHTML('back','ph-folder-open','Tồn đọng từ tháng trước', g.back.length)
                     + tabHTML('new','ph-sparkle','Mới trong tháng', g.fresh.length);
      } else sb.style.display='none';
    }

    var html = slice.map(rowHTML).join('');
    if(!total){
      var noneAtAll = !(g.back.length+g.fresh.length);
      html = '<tr><td colspan="'+cols+'"><div class="empty-state">'
        +'<span class="es-ic"><span class="material-symbols-rounded ph-light ph-bug-beetle"></span></span>'
        +'<div class="es-title">'+(noneAtAll ? 'Không có bug nào trong tháng này'
            : (g.active==='new' ? 'Không có bug mới trong tháng' : 'Không có bug tồn đọng từ tháng trước'))+'</div>'
        +'<div class="es-hint">'+(noneAtAll ? 'Đổi tháng hoặc bộ lọc tester/dev để xem bug khác.'
            : 'Chuyển sang tab còn lại hoặc đổi bộ lọc.')+'</div>'
        +'</div></td></tr>';
    }
    rows.innerHTML = html;
    animRows(rows);
    cnt.textContent = 'Hiển thị '+slice.length+' / '+total+' bản ghi';
    // pager (dùng chung — số trang + ellipsis + range info)
    pager.innerHTML = total ? pagerHTML(page, pages, total, start, slice.length, 'bản ghi') : '';
  }

  // đổi tab nhóm -> về trang 1 (tập phân trang đổi)
  function setGroup(g){
    if((g!=='back' && g!=='new') || g===grpTab) return;
    grpTab=g; saveGrpTab(); page=1; render();
  }
  (function(){ var sb=$('blSplitBar'); if(!sb) return;
    sb.addEventListener('click', function(e){ var c=e.target.closest('[data-grp]');
      if(c) setGroup(c.getAttribute('data-grp')); }); })();

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
  // ----- events: lọc theo severity -----
  (function(){ var sf=$('blSevFilter'); if(!sf) return;
    sf.addEventListener('change', function(){ sevFilter=sf.value||''; page=1; render(); }); })();
  // ----- export bảng ĐANG XEM ra .xlsx (đúng tháng + filter hiện tại) -----
  function exportExcel(){
    var list=visibleBugs();   // đúng bảng đang xem: file + tháng + tester/dev/link + tab nhóm
    if(!list.length){ toast('Không có bug nào để export', false); return; }
    var rows=list.map(function(b){
      var sk = sevOf(b);   // Severity: xuất ĐÚNG mức Jira (#104), 'none' -> rỗng
      return [ b.id||'', b.summary||'', formatCreated(b.created),
               (sk==='none' ? '' : SEV_LABEL[sk]),
               statusLabel(b.statusRaw||b.status), b.qa||'', b.dev||'' ]; });
    var lbl=(activeLabel()||'tat-ca').replace(/[^\w]+/g,'-').replace(/^-+|-+$/g,'');
    var mon=(curMonth||'').replace(/[\/]/g,'-');
    var grp=(splitGroups().active==='new') ? 'moi' : 'ton-dong';
    var fname='bug-log_'+lbl+(mon?'_'+mon:'')+'_'+grp+'.xlsx';
    var btn=$('blExportBtn'); if(btn){ btn.disabled=true; }
    fetch('/export-bug-log',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({rows:rows,filename:fname})})
      .then(function(r){ if(!r.ok) throw 0; return r.blob(); })
      .then(function(blob){
        var url=URL.createObjectURL(blob), a=document.createElement('a');
        a.href=url; a.download=fname; document.body.appendChild(a); a.click();
        setTimeout(function(){ URL.revokeObjectURL(url); a.remove(); },1000);
        toast('Đã export '+list.length+' bug', true);
      })
      .catch(function(){ toast('Export lỗi, thử lại', false); })
      .then(function(){ if(btn){ btn.disabled=false; } });
  }
  (function(){ var eb=$('blExportBtn'); if(!eb) return;
    eb.addEventListener('click', exportExcel); })();
  // Liên kết bug<->task thủ công (tick + unlink) đã gỡ (#104): cột "Liên kết" đọc link native Jira.

  // Quản lý link Drive đã gỡ (#104): nguồn Bug Log cố định = Jira "Bug Testing".

  // "Đồng bộ ngay" — F5 chỉ render cache; nút này gọi scan() Jira ngay rồi reload (admin).
  // Khi đang sync: disable + đổi nhãn (spinner) để KHÔNG bấm nhiều lần. Dùng chung cho cả
  // auto-sync hết giờ (runBugSync) -> 1 đường đi duy nhất.
  // Nút GIỮ disabled suốt quá trình sync; chỉ "active" lại khi sync thành công -> reload
  // (trang load lại = nút mới tinh, enabled). Lỗi -> đổi nhãn báo lỗi + gợi ý F5 retry,
  // KHÔNG tự enable lại (tránh bấm dồn khi Drive đang chậm/timeout).
  function runBugSync(b){
    if(!b || b.disabled) return Promise.resolve(false);
    b.disabled=true;
    b.innerHTML='<span class="material-symbols-rounded ph-light ph-circle-notch mi-sm" style="animation:spin 1s linear infinite"></span> Đang đồng bộ…';
    toast('Đang kéo lại Bug Testing từ Jira…', true);
    return postJSON('/sync-bug-log', {}, 90000).then(function(j){
      if(j && j.ok){
        var changes=(j&&j.changes)||[];
        var missing=(j&&j.missing)||[];
        // 2 popup ĐỘC LẬP, hiện song song (#88): thay đổi file (đọc) vs dòng thiếu STT
        // (phải sửa tay). Có cái nào thì hiện cái đó; không có cái nào -> reload như cũ.
        if(missing.length) showBugMissing(missing, j.missing_total||missing.length);
        if(changes.length){ showBugChanges(changes, j.changed||changes.length); return true; }
        if(missing.length) return true;   // chỉ có popup thiếu STT -> reload khi user đóng
        toast('Đã đồng bộ ✓ — không có thay đổi, đang tải lại', true);
        setTimeout(function(){ location.reload(); }, 900); return true;
      }
      b.innerHTML='<span class="material-symbols-rounded ph-light ph-warning-circle mi-sm"></span> Đồng bộ lỗi — F5 để thử lại';
      toast((j&&(j.errors&&j.errors[0]))||'Đồng bộ lỗi', false); return false;
    }).catch(function(){
      b.innerHTML='<span class="material-symbols-rounded ph-light ph-warning-circle mi-sm"></span> Đồng bộ lỗi — F5 để thử lại';
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
        +'<span class="material-symbols-rounded ph-light ph-file-text mi-sm"></span> '+esc(g.file)
        +' <span class="bl-chg-sheet">› '+esc(g.sheet)+'</span></div>';
      g.items.forEach(function(c){
        var desc=c.desc||'', summ=c.summary?(' — '+c.summary):'', who=c.author?(' · '+c.author):'';
        html+='<div class="bl-chg-item bl-chg-'+esc(c.kind||'')+'">'
          +phIcon(ICON[c.kind]||'edit','mi-sm')
          +'<span class="bl-chg-txt">'+esc(desc)+esc(summ)+'<span class="bl-chg-who">'+esc(who)+'</span></span></div>';
      });
      html+='</div>';
    });
    var lst=$('blChgList'); if(lst) lst.innerHTML=html;
    var sm=$('blChgSummary');
    if(sm) sm.textContent='Đồng bộ xong: '+(total||changes.length)+' thay đổi'
      +(changes.length<(total||0)?(' (hiện '+changes.length+' dòng đầu)'):'')+'.';
    ov.classList.add('open');
    popOpen.chg=true; pairSync();
  }
  // Popup 2 (#88): dòng ĐỦ THÔNG TIN nhưng CHƯA có STT. Không có STT = không có khoá diff
  // -> dòng đó im lặng rơi khỏi mọi metric/bảng, popup 1 không bao giờ nêu được. Tách popup
  // riêng vì đây là việc phải làm tay (mở file đánh lại STT), hiện SONG SONG với popup 1.
  var missingRows = [];
  function showBugMissing(list, total){
    var ov=$('blMissOv'); if(!ov || !list.length) return;
    missingRows = list;
    var groups={}, order=[];
    list.forEach(function(m){
      var f=m.file||'(không rõ file)', s=m.sheet||'(không rõ sheet)', gk=f+' '+s;
      if(!groups[gk]){ groups[gk]={file:f, sheet:s, items:[]}; order.push(gk); }
      groups[gk].items.push(m);
    });
    var html='';
    order.forEach(function(gk){
      var g=groups[gk];
      html+='<div class="bl-chg-grp"><div class="bl-chg-grp-h">'
        +'<span class="material-symbols-rounded ph-light ph-file-text mi-sm"></span> '+esc(g.file)
        +' <span class="bl-chg-sheet">› '+esc(g.sheet)+'</span></div>';
      g.items.forEach(function(m){
        var meta=[m.created, m.status, m.qa_pic?('QA: '+m.qa_pic):'', m.dev_pic?('Dev: '+m.dev_pic):'']
          .filter(Boolean).join(' · ');
        html+='<div class="bl-miss-item">'
          +'<span class="bl-miss-row" title="Dòng trong file Excel">D'+esc(String(m.row||'?'))+'</span>'
          +'<span class="bl-chg-txt">'+esc(m.summary||'')
          +(m.feature?'<span class="bl-miss-feat"> ['+esc(m.feature)+']</span>':'')
          +(meta?'<span class="bl-chg-who"><br>'+esc(meta)+'</span>':'')+'</span></div>';
      });
      html+='</div>';
    });
    var lst=$('blMissList'); if(lst) lst.innerHTML=html;
    var sm=$('blMissSummary');
    if(sm) sm.textContent=(total||list.length)+' dòng có đủ thông tin nhưng chưa đánh STT — '
      +'chưa có STT thì bug KHÔNG vào bảng/metric. Mở file đánh lại STT rồi đồng bộ lại.'
      +(list.length<(total||0)?(' (hiện '+list.length+' dòng đầu)'):'');
    ov.classList.add('open');
    popOpen.miss=true; pairSync();
  }

  // ackWatermark != null => popup đang hiện là "thay đổi tích luỹ" (admin chưa xem): khi đóng
  // phải BÁO server đã xem (đẩy watermark) RỒI mới reload, để reload không popup lại y hệt.
  // null => popup đồng bộ tay (server đã đánh dấu đã xem trong /sync-bug-log) -> reload thẳng.
  var ackWatermark = null;
  // 2 popup song song: reload CHỈ khi cả hai đã đóng (đóng popup này không được cướp mất
  // popup kia). `.bl-pair` trên body = layout 2 panel cạnh nhau, 1 lớp nền mờ duy nhất.
  var popOpen = { chg:false, miss:false };
  function pairSync(){
    document.body.classList.toggle('bl-pair', popOpen.chg && popOpen.miss);
  }
  function finishPops(){
    if(popOpen.chg || popOpen.miss) return;
    if(ackWatermark !== null){
      var wm = ackWatermark; ackWatermark = null;
      postJSON('/seen-bug-log-changes', { watermark: wm }, 10000)
        .then(function(){ location.reload(); })
        .catch(function(){ location.reload(); });   // soft-fail: chưa đẩy được -> lần sau popup lại
      return;
    }
    location.reload();
  }
  (function(){
    var ov=$('blChgOv'); if(!ov) return;
    function close(){
      ov.classList.remove('open'); popOpen.chg=false; pairSync(); finishPops();
    }
    var ok=$('blChgOk'), cl=$('blChgClose');
    if(ok) ok.addEventListener('click', close);
    if(cl) cl.addEventListener('click', close);
    ov.addEventListener('click', function(e){ if(e.target===ov) close(); });
  })();
  (function(){
    var ov=$('blMissOv'); if(!ov) return;
    function close(){
      ov.classList.remove('open'); popOpen.miss=false; pairSync(); finishPops();
    }
    var ok=$('blMissOk'), cl=$('blMissClose'), cp=$('blMissCopy');
    if(ok) ok.addEventListener('click', close);
    if(cl) cl.addEventListener('click', close);
    ov.addEventListener('click', function(e){ if(e.target===ov) close(); });
    if(cp) cp.addEventListener('click', function(){
      var txt=missingRows.map(function(m){
        return [m.file||'', m.sheet||'', 'dòng '+(m.row||'?'), m.summary||''].join(' | ');
      }).join('\n');
      if(navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(txt).then(function(){ toast('Đã sao chép ✓', true); })
          .catch(function(){ toast('Không sao chép được', false); });
      } else toast('Trình duyệt không cho sao chép', false);
    });
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
      el.innerHTML='<span class="material-symbols-rounded ph-light ph-arrows-clockwise mi-sm"></span> Tự đồng bộ từ Jira mỗi '+mins+' phút · '+tail;
    }
    tick(); setInterval(tick, 1000);
  })();

  // Picker file + modal CRUD link Drive đã gỡ (#104): nguồn Bug Log = Jira "Bug Testing" cố định.

  // Link bar + liên kết task thủ công đã gỡ (#104): cột "Liên kết" đọc issue liên quan từ Jira.

  if(activeFid){ var av0=availMonths(); if(av0.indexOf(curMonth)<0) curMonth = av0.length?av0[0]:''; }

  // Deep-link ?bug=<key> (từ command palette): nhảy đúng file + tháng + trang,
  // highlight dòng. Copy pattern ?folder= của test-cases.
  var deepBug = null;
  try{ deepBug = new URLSearchParams(location.search).get('bug'); }catch(e){}
  if(deepBug){
    var db = BUGS.filter(function(b){ return b.key===deepBug; })[0];
    if(db){
      testerFilter=''; devFilter=''; sevFilter='';
      var tf=$('blTesterFilter'), df=$('blDevFilter'), svf=$('blSevFilter');
      if(tf) tf.value=''; if(df) df.value=''; if(svf) svf.value='';
      if(db.fid && SOURCES.some(function(s){ return s.id===db.fid; })) activeFid=db.fid;
      if(db.month) curMonth=db.month;
      var list0=monthBugs();
      var idx=-1; list0.forEach(function(b,i){ if(b.key===deepBug) idx=i; });
      if(idx>=0) page=Math.floor(idx/PER)+1;
    } else { deepBug=null; toast('Bug không còn trong log', false); }
  }

  renderTabs(); render(); updateActiveChip(); updateSrcLine();
  if(deepBug){
    var flashTr=rows.querySelector('tr[data-bug="'+CSS.escape(deepBug)+'"]');
    if(flashTr){ flashTr.classList.add('row-flash');
      flashTr.scrollIntoView({ block:'center' }); }
  }
})();

// ================= ANALYTICS (guard #analyticsData, issue #158) =================
// Gom metric bug: Valid Bug Rate + chart bug theo dev/dự án + Tỷ lệ Reopen.
// Data nguồn = analyticsData (bug_log cache). Dùng $/esc/toast/readJSON ở scope chung.
(function(){
  var DATA = readJSON('analyticsData'); if(!DATA) return;
  var BUGS = DATA.bugs||[], REOPEN = DATA.reopen||{};
  // Chart FROZEN cho tháng đã đóng (Decision #47) — số liệu chốt cuối tháng, KHÔNG trôi khi
  // team sửa/copy sheet tháng sau. chartMonths[YYYY-MM] = {grand,devs,bl}. Tháng hiện tại +
  // tháng chưa có frozen -> tính LIVE.
  var CHART_FROZEN = DATA.chartMonths || {};
  function curYm(){ var d=new Date(); return d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2); }
  var PIE_COLORS = ['#4c9aff','#36b37e','#ffab00','#ff5630','#6554c0','#00b8d9','#ff7452','#57d9a3','#8777d9','#ff8b00','#2684ff','#172b4d'];

  // Metric từ Jira — nguồn bug đã chuyển sang Jira (#104). Option A (#105): 'open_age' tính thuần
  // client-side (created + status), không cần resolutiondate/changelog. Card [data-jm] render
  // empty-state server-side; hàm này thay body bằng số thật (giữ nguyên empty-state nếu không có bug mở).
  // Bug "đang mở" = lifecycle KHÔNG phải Closed/Rejected (dùng chung isClosed/isReject bên dưới).
  var OA_BUCKETS = [  // [nhãn, maxNgày (inclusive, null = vô cực), màu — xanh->đỏ theo tuổi]
    ['≤3 ngày', 3, '#36b37e'], ['4–7 ngày', 7, '#57d9a3'], ['8–14 ngày', 14, '#ffab00'],
    ['15–30 ngày', 30, '#ff7452'], ['>30 ngày', null, '#ff5630']
  ];
  function _ageDays(iso){
    if(!iso) return null;
    var d = new Date(iso + 'T00:00:00'); if(isNaN(d)) return null;
    var ms = Date.now() - d.getTime();
    return ms < 0 ? 0 : Math.floor(ms / 86400000);
  }
  function renderJiraMetrics(){
    var card = document.querySelector('[data-jm="open_age"]'); if(!card) return;
    var body = card.querySelector('.jm-empty'); if(!body) return;
    var open = BUGS.filter(function(b){ return b.created && !isClosed(b.status) && !isReject(b.status); });
    var ages = open.map(function(b){ return _ageDays(b.created); }).filter(function(a){ return a != null; });
    if(!ages.length){
      body.innerHTML = '<div class="es-ic"><span class="material-symbols-rounded">task_alt</span></div>'
        + '<div class="es-title">Không có bug nào đang mở</div>'
        + '<div class="es-hint">Mọi bug đều đã đóng hoặc bị từ chối.</div>';
      return;
    }
    var counts = OA_BUCKETS.map(function(){ return 0; }), maxC = 0;
    ages.forEach(function(a){
      for(var i=0;i<OA_BUCKETS.length;i++){ if(OA_BUCKETS[i][1]==null || a<=OA_BUCKETS[i][1]){ counts[i]++; break; } }
    });
    counts.forEach(function(c){ if(c>maxC) maxC = c; });
    var sorted = ages.slice().sort(function(x,y){ return x-y; });
    var mid = Math.floor(sorted.length/2);
    var median = sorted.length%2 ? sorted[mid] : Math.round((sorted[mid-1]+sorted[mid])/2);
    var maxAge = sorted[sorted.length-1];
    var bars = OA_BUCKETS.map(function(bk, i){
      var c = counts[i], pct = maxC ? (c/maxC*100) : 0;
      return '<div style="display:flex; align-items:center; gap:10px; margin-bottom:8px; font-size:13px;">'
        + '<span style="flex:0 0 78px; color:var(--on-surface-variant); text-align:right;">'+bk[0]+'</span>'
        + '<div style="flex:1; height:20px; background:var(--surface-variant,rgba(0,0,0,.06)); border-radius:4px; overflow:hidden;">'
        +   '<div style="height:100%; width:'+Math.max(c?6:0,pct)+'%; background:'+bk[2]+'; border-radius:4px;"></div>'
        + '</div>'
        + '<span style="flex:0 0 32px; font-weight:700; color:var(--on-surface); text-align:left; font-variant-numeric:tabular-nums;">'+c+'</span>'
        + '</div>';
    }).join('');
    var head = '<div style="display:flex; gap:28px; margin-bottom:16px;">'
      + '<div><div style="font-size:26px; font-weight:800; color:var(--on-surface); font-variant-numeric:tabular-nums;">'+open.length+'</div>'
      +   '<div style="font-size:12px; color:var(--on-surface-variant);">bug đang mở</div></div>'
      + '<div><div style="font-size:26px; font-weight:800; color:var(--on-surface); font-variant-numeric:tabular-nums;">'+median+'</div>'
      +   '<div style="font-size:12px; color:var(--on-surface-variant);">tuổi trung vị (ngày)</div></div>'
      + '<div><div style="font-size:26px; font-weight:800; color:#ff5630; font-variant-numeric:tabular-nums;">'+maxAge+'</div>'
      +   '<div style="font-size:12px; color:var(--on-surface-variant);">bug mở lâu nhất (ngày)</div></div>'
      + '</div>';
    // Thay cả body (bỏ class empty-state để hết canh giữa dọc) -> dùng wrapper padding thường.
    body.className = 'jm-filled';
    body.setAttribute('style', 'padding:4px 20px 20px;');
    body.innerHTML = head + bars;
  }
  renderJiraMetrics();

  function getCreatedMonthYear(iso){
    if(!iso) return '';
    var p = iso.split('-');
    return p.length>=2 ? p[1]+'/'+p[0] : '';
  }
  // Tháng theo tên SHEET (Tn) -> 'MM/YYYY'. Chính sách mới 2026-07: bucket chart theo sheet
  // tháng T (KHÔNG theo created date). 'Tn' bare lấy năm từ created; 'Tn<yyyy>' năm tường minh;
  // sheet module/không phải Tn -> fallback created. PHẢI khớp _month_of() phía Python (bug_backlog.py).
  function _sheetMY(mo, createdIso){
    mo = (''+(mo||'')).trim();
    var m = /^T(\d{1,2})(\d{4})$/.exec(mo);
    if(m){ var a=+m[1]; if(a>=1&&a<=12) return (a<10?'0'+a:''+a)+'/'+m[2]; }
    m = /^T(\d{1,2})$/.exec(mo);
    if(m){ var b2=+m[1]; if(b2>=1&&b2<=12){ var cr=(''+(createdIso||'')); var yy=/^\d{4}/.test(cr)?cr.slice(0,4):(''+new Date().getFullYear()); return (b2<10?'0'+b2:''+b2)+'/'+yy; } }
    return '';
  }
  function monthOf(b){ return _sheetMY(b.month, b.created) || getCreatedMonthYear(b.created); }
  // Version snapshot chart — PHẢI khớp _CHART_V phía Python (bug_backlog.py). Lệch = bỏ frozen,
  // tính LIVE lại để không hiện số theo semantics cũ trong lúc chờ scan rebuild.
  var CHART_V = 6;
  // Frozen dùng khi: (a) snapshot ĐÚNG version, hoặc (b) snapshot CHỐT CỨNG (_frozen=true do
  // freeze_month() ghi sau khi report gửi CTO) — bản chốt cứng là bản ghi lịch sử, tin theo
  // nguyên trạng dù version có bump về sau (Decision #69).
  // Tháng HIỆN TẠI: chỉ dùng frozen nếu đã chốt cứng; còn lại luôn LIVE.
  function frozenFor(selYm){
    if(!selYm) return null;
    var f = CHART_FROZEN[selYm]||null;
    if(!f) return null;
    if(f._frozen) return f;
    return (selYm !== curYm() && f._v===CHART_V) ? f : null;
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
    // FROZEN cho tháng đã đóng (Decision #47); LIVE (dedup fp) cho tháng hiện tại/chưa freeze.
    var selYm = toYm(m); var frozen = frozenFor(selYm);
    var total, reject, closed;
    if(frozen && frozen.valid){
      total = frozen.valid.total||0; reject = frozen.valid.reject||0; closed = frozen.valid.closed||0;
    } else {
      var mBugs = dedupByFp(BUGS.filter(function(b){ return monthOf(b) === m; }));
      total = mBugs.length;
      reject = mBugs.filter(function(b){ return isReject(b.status); }).length;
      closed = mBugs.filter(function(b){ return isClosed(b.status); }).length;
    }
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
      + '<div class="an-valid-main"><span class="an-valid-pct an-good">'+pctDisp+'</span>'
      + '<span class="an-valid-cap">bug hợp lệ đã đóng</span></div>'
      + '<div class="an-valid-break">'
      +   '<div class="an-stat an-num-good"><span class="an-stat-n">'+closed+'</span><span class="an-stat-l">Closed</span></div>'
      +   '<div class="an-stat-op">/</div>'
      +   '<div class="an-stat"><span class="an-stat-n">'+denom+'</span><span class="an-stat-l">Tổng '+total+' − Reject '+reject+'</span></div>'
      + '</div>'
      + '</div>'
      + '<div style="flex:1; border-left:1px solid var(--outline-variant); padding-left:32px;">'
      + '<div class="an-valid-main"><span class="an-valid-pct an-bad">'+rejDisp+'</span>'
      + '<span class="an-valid-cap">tỷ lệ Reject</span></div>'
      + '<div class="an-valid-break">'
      +   '<div class="an-stat an-num-bad"><span class="an-stat-n">'+reject+'</span><span class="an-stat-l">Reject</span></div>'
      +   '<div class="an-stat-op">/</div>'
      +   '<div class="an-stat"><span class="an-stat-n">'+total+'</span><span class="an-stat-l">Tổng số Bug</span></div>'
      + '</div>'
      + '</div>';
  }

  // ---------- Severity: pie chart (Decision #85) ----------
  // Thang 3 mức + sevOf() dùng chung ở scope ngoài (cùng dùng cho cột Severity ở /bug-log).
  // Ô trống/giá trị lạ -> 'none': KHÔNG vẽ trong pie nhưng vẫn hiện thành ghi chú dưới chart
  // (bỏ hẳn thì mất mẫu số, CTO tưởng tháng chỉ có ngần ấy bug).
  function sevCounts(list){
    var c = {}; SEV_ORDER.forEach(function(k){ c[k]=0; });
    list.forEach(function(b){ c[sevOf(b)]++; });
    return c;
  }
  // Pie SVG thuần path (KHÔNG conic-gradient — html2canvas không render được conic, ảnh gửi
  // CTO sẽ trắng bệch). 1 nhóm duy nhất -> vẽ <circle> vì cung 360° làm path arc suy biến.
  function pieSVG(segs, size){
    var total = 0; segs.forEach(function(s){ total += s.n; });
    if(total <= 0) return '';
    var r = size/2, cx = r, cy = r;
    var live = segs.filter(function(s){ return s.n > 0; });
    if(live.length === 1)
      return '<svg width="'+size+'" height="'+size+'" viewBox="0 0 '+size+' '+size+'">'
        + '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="'+live[0].color+'"></circle></svg>';
    var a0 = -Math.PI/2, paths = '';
    live.forEach(function(s){
      var a1 = a0 + (s.n/total)*Math.PI*2;
      var x0 = cx + r*Math.cos(a0), y0 = cy + r*Math.sin(a0);
      var x1 = cx + r*Math.cos(a1), y1 = cy + r*Math.sin(a1);
      var large = (a1-a0) > Math.PI ? 1 : 0;
      paths += '<path d="M '+cx+' '+cy+' L '+x0.toFixed(2)+' '+y0.toFixed(2)
        + ' A '+r+' '+r+' 0 '+large+' 1 '+x1.toFixed(2)+' '+y1.toFixed(2)+' Z" fill="'+s.color+'">'
        + '<title>'+esc(s.label)+': '+s.n+'</title></path>';
      a0 = a1;
    });
    return '<svg width="'+size+'" height="'+size+'" viewBox="0 0 '+size+' '+size+'">'+paths+'</svg>';
  }
  // Khối "Phân bố theo mức độ nghiêm trọng" — nằm TRONG #anMetricCharts nên tự lọt vào ảnh
  // Export PDF/PNG mà reporter tháng gửi CTO.
  function sevBlockHTML(list){
    var c = sevCounts(list), total = list.length;
    if(!total) return '';
    // Pie CHỈ 3 mức (user chốt); mẫu số % = bug ĐÃ phân loại, không phải tổng bug tháng.
    var classified = SEV_PIE.reduce(function(a,k){ return a + c[k]; }, 0);
    if(!classified)
      return '<div style="width:100%; border-top:1px solid var(--outline-variant); margin-top:8px; padding-top:18px;">'
        + '<div class="an-empty">Chưa bug nào của tháng này được điền cột Severity ('+total+' bug).</div></div>';
    var segs = SEV_PIE.filter(function(k){ return c[k] > 0; }).map(function(k){
      return { label: SEV_LABEL[k], n: c[k], color: SEV_COLOR[k] }; });
    var rows = segs.map(function(s){
      var p = s.n/classified*100, pd = (p%1===0 ? p.toFixed(0) : p.toFixed(1))+'%';
      return '<div style="display:flex; align-items:center; gap:8px; font-size:13.5px; margin-bottom:8px;">'
        + '<span style="width:14px; height:14px; border-radius:3px; background:'+s.color+'; display:inline-block; flex-shrink:0;"></span>'
        + '<span style="color:var(--on-surface); flex:1;">'+esc(s.label)+'</span>'
        + '<strong style="color:var(--on-surface);">'+s.n+'</strong>'
        + '<span style="color:var(--on-surface-variant); min-width:48px; text-align:right;">'+pd+'</span></div>';
    }).join('');
    var note = c.none
      ? '<div style="text-align:center; font-size:12.5px; color:var(--on-surface-variant); margin-top:14px;">'
        + 'Chưa phân loại: <strong>'+c.none+'</strong>/'+total+' bug — không tính vào biểu đồ.</div>'
      : '';
    return '<div style="width:100%; border-top:1px solid var(--outline-variant); margin-top:8px; padding-top:18px;">'
      + '<div style="text-align:center; font-size:14px; font-weight:600; color:var(--on-surface); margin-bottom:14px;">'
      +   'Phân bố theo mức độ nghiêm trọng (Severity) — '+classified+' bug đã phân loại</div>'
      + '<div style="display:flex; gap:28px; align-items:center; justify-content:center; flex-wrap:wrap;">'
      +   '<div style="flex-shrink:0;">'+pieSVG(segs, 200)+'</div>'
      +   '<div style="min-width:280px;">'+rows+'</div>'
      + '</div>' + note + '</div>';
  }

  // ---------- Bar chart: bug của dev theo dự án ----------
  var metricMonthSel = $('anMetricMonth'), metricCharts = $('anMetricCharts');
  function renderMetric(){
    if(!metricMonthSel || !metricCharts) return;
    var backlogStripEl = $('anBacklogStrip');
    if(backlogStripEl) backlogStripEl.innerHTML = '';  // reset, tránh dải tồn đọng cũ sót khi đổi tháng
    var selectedMonth = metricMonthSel.value;
    if(!selectedMonth){ metricCharts.innerHTML = '<div class="an-empty">Không có dữ liệu</div>'; return; }
    // Biểu đồ cột + "Tổng số bug" CHỈ tính BUG MỚI PHÁT SINH trong tháng T — SHEET-BASED
    // (Decision #75): dòng nằm trong sheet tháng T (monthOf===tháng chọn) có created trong T.
    // Đếm DÒNG (không dedup) -> grandTotal = "mới phát sinh" khớp dải tồn đọng + màn Bug.
    // Tính LIVE cho MỌI tháng. Freeze (#47/#69) VẪN áp cho Valid Bug Rate + Reopen.
    var selYm = toYm(selectedMonth);
    var devs = {}, projSet = {}, grandTotal = 0, fixedCount = 0, bc;
    var mBugs = BUGS.filter(function(b){
      return monthOf(b) === selectedMonth && (b.created||'').slice(0,7) === selYm; });
    mBugs.forEach(function(b){
      var dl = (b.dev||'Chưa gán').trim().split(/[,;+&\/]/).map(function(s){ return s.trim(); }).filter(Boolean);
      if(!dl.length) dl = ['Chưa gán'];
      var fraction = 1/dl.length, p = (b.project||'Khác').trim();
      dl.forEach(function(d){
        if(!devs[d]) devs[d] = { total:0, projs:{} };
        devs[d].projs[p] = (devs[d].projs[p]||0) + fraction;
        devs[d].total += fraction;
      });
      projSet[p] = true;
    });
    grandTotal = mBugs.length;
    bc = computeBacklog(selYm);
    // Đã fix trong tháng = bug MỚI PHÁT SINH đã Closed (bc.newFixed).
    fixedCount = bc.newFixed||0;
    var devList = Object.keys(devs).sort(function(a,b){ return devs[b].total - devs[a].total; });
    var projList = Object.keys(projSet).sort();
    if(!devList.length){ metricCharts.innerHTML = '<div class="an-empty">Không có dữ liệu trong tháng này</div>'; return; }
    // tổng số bug theo từng dự án + tổng toàn tháng (bug đa-dev tính phân số nên tổng = số bug thật)
    var projTotals = {};
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
    // Biểu đồ cột (vùng Export PDF) CHỈ thể hiện bug MỚI phát sinh của tháng T — user chốt 2026-08-03.
    // Số tính LIVE (không còn khoá freeze cho chart này), dải tồn đọng T-1 render ở #anBacklogStrip
    // (TÁCH ngoài metricCharts) nên KHÔNG lọt vào ảnh report.
    var totalHtml = '<div style="text-align:center; margin-bottom:14px; font-size:14px; color:var(--on-surface);">'
      + 'Tổng số bug: <strong style="font-size:16px;">'+grandTotal+'</strong>'
      + ' · Bug mới đã fix: <strong style="font-size:16px; color:#36b37e;">'+fixedCount+'</strong>'
      + '<span style="color:var(--on-surface-variant);">/'+(bc.newOwn||0)+'</span></div>';
    var backlogStrip = $('anBacklogStrip');
    if(backlogStrip){
      if(bc.hasSnapshot){
        backlogStrip.innerHTML = '<div style="max-width:820px; margin:0 auto; padding:14px 18px; border:1px solid var(--outline-variant); border-radius:8px;">'
          + '<div style="font-size:13.5px; color:var(--on-surface); margin-bottom:10px;">'
          +   '<strong>'+(bc.newOwn||0)+'</strong> bug mới phát sinh '
          +   '(đã fix <strong style="color:#36b37e;">'+(bc.newFixed||0)+'</strong>, '
          +   'chưa fix <strong>'+(bc.newOpen||0)+'</strong>) · '
          +   'Tồn đọng từ tháng trước: '
          +   '<strong>'+bc.total+'</strong> (còn <strong style="color:#ff5630;">'+bc.stillOpen+'</strong>, đã xử lý '+bc.resolved+')'
          + '</div>' + compBar(backlogSegs(bc), 26) + '</div>';
      } else { backlogStrip.innerHTML = ''; }
    }
    metricCharts.innerHTML = '<div style="width:100%; display:flex; flex-direction:column; padding:10px 0;">'
      + totalHtml
      + '<div style="display:flex; justify-content:center; flex-wrap:wrap; margin-bottom:24px;">' + legendHtml + '</div>'
      + '<div style="display:flex; align-items:flex-start;">'
      +   '<div style="position:relative; height:'+chartHeight+'px; width:40px; flex-shrink:0;">' + ticksHtml + '</div>'
      +   '<div class="hide-scrollbar" style="position:relative; flex:1; height:'+(chartHeight+50)+'px; display:flex; align-items:flex-start; overflow-x:auto; border-bottom:1px solid var(--outline-variant);">'
      +     '<div style="display:flex; height:'+(chartHeight+40)+'px; padding-top:0;">' + barsHtml + '</div>'
      +   '</div></div>'
      // Pie severity CÙNG tập bug với bar chart (mới phát sinh trong T) -> tổng 2 chart khớp nhau.
      + sevBlockHTML(mBugs)
      + '</div>';
  }

  // ---------- Reopen table ----------
  var reopenMonthSel = $('anReopenMonth'), reopenKpi = $('anReopenKpi'),
      reopenHead = $('anReopenHead'), reopenRows = $('anReopenRows');
  var reopenExpanded = {};
  function reopenPct(n, d){ if(d<=0) return null; var p = n/d*100; return (p%1===0 ? p.toFixed(0) : p.toFixed(1)); }
  // Số lần fix = SUY từ count + trạng thái hiện tại (parity _reopen_table Python). KHÔNG đọc
  // accumulator r.fix cũ (undercount vì team hay skip status 'Fixed' -> ca vô lý "2 reopen 1 fix").
  // Mỗi reopen = 1 fix bị QA trả lại; +1 nếu bug đang ở trạng thái đã-giao-fix (Fixed/Closed).
  // Bug rời file (b không có) -> giả định đã giao 1 lần cuối.
  function fixDeliv(r, b){
    var cnt = +(r&&r.count)||0;
    if(b && b.status!=null) return cnt + ((b.status==='Fixed'||b.status==='Closed') ? 1 : 0);
    return cnt + 1;
  }
  function renderReopen(){
    if(!reopenMonthSel || !reopenHead || !reopenRows) return;
    var selectedMonth = reopenMonthSel.value;
    if(!selectedMonth){
      if(reopenKpi) reopenKpi.innerHTML = '';
      reopenHead.innerHTML = '';
      reopenRows.innerHTML = '<tr><td style="text-align:center;color:var(--on-surface-variant);padding:30px">Không có dữ liệu</td></tr>';
      return;
    }
    // FROZEN cho tháng đã đóng (Decision #47) — giữ nguyên semantics live (RAW, không dedup),
    // chỉ chặn trôi. Tháng hiện tại/chưa freeze -> tính LIVE từ BUGS + REOPEN.
    var selYm = toYm(selectedMonth); var frozen = frozenFor(selYm);
    var bugsPerDev = {}, totalBugs = 0, distinctPerDev = {}, fixPerDev = {}, detailPerDev = {}, distinctTotal = 0;
    if(frozen && frozen.reopen){
      var fr = frozen.reopen;
      totalBugs = fr.totalBugs||0; distinctTotal = fr.distinctTotal||0;
      Object.keys(fr.devs||{}).forEach(function(d){
        var e = fr.devs[d]||{};
        distinctPerDev[d] = e.nb||0; fixPerDev[d] = e.fx||0; bugsPerDev[d] = e.denom||0;
        detailPerDev[d] = e.detail||[];
      });
    } else {
      var mBugs = BUGS.filter(function(b){ return monthOf(b) === selectedMonth; });
      totalBugs = mBugs.length;
      var bugByKey = {};
      mBugs.forEach(function(b){
        var devList = (b.dev||'Chưa gán').trim().split(/[,;+&\/]/).map(function(s){ return s.trim(); }).filter(Boolean);
        if(!devList.length) devList = ['Chưa gán'];
        // Full attribution: bug nhiều dev -> mỗi dev tính đủ 1 (KHÔNG chia 1/n) -> số nguyên.
        // Parity với _reopen_table (bug_backlog.py).
        devList.forEach(function(d){ bugsPerDev[d] = (bugsPerDev[d]||0) + 1; });
        if(b.key) bugByKey[b.key] = b;
      });
      Object.keys(REOPEN).forEach(function(key){
        var r = REOPEN[key]||{}, cnt = +r.count||0; if(cnt<=0) return;
        var b = bugByKey[key];
        // CHỈ đếm bug CÒN trong current bugs của tháng; entry orphan (bug rời file/bị filter) -> bỏ.
        // Parity với _reopen_table (bug_backlog.py) — data clean, filter-consistent.
        if(!b) return;
        var devStr = (b.dev||'Chưa gán').trim(), fx = fixDeliv(r, b);
        var devList = devStr.split(/[,;+&\/]/).map(function(s){ return s.trim(); }).filter(Boolean);
        if(!devList.length) devList = ['Chưa gán'];
        distinctTotal++;
        // Full attribution: mỗi dev cùng fix bug này tính đủ số reopen/fix (KHÔNG chia 1/n)
        // -> chi tiết số nguyên. Parity với _reopen_table (bug_backlog.py).
        devList.forEach(function(d){
          distinctPerDev[d] = (distinctPerDev[d]||0) + 1;
          fixPerDev[d] = (fixPerDev[d]||0) + fx;
          (detailPerDev[d] = detailPerDev[d]||[]).push({ id: b.id, summary: b.summary, reopen: cnt, fix: fx });
        });
      });
    }
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
        + '<td>'+phIcon(open?'expand_more':'chevron_right','rk-caret')+esc(d)+'</td>'
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

  // ---------- Tồn đọng T-1 (dùng cho dải tóm tắt TRONG chart export) ----------
  function isOpenBug(s){ return !isClosed(s) && !isReject(s); }
  function toYm(mmYYYY){ var p=(mmYYYY||'').split('/'); return p.length>=2 ? p[1]+'-'+p[0] : ''; }  // MM/YYYY -> YYYY-MM
  function prevYm(ym){ var y=+ym.slice(0,4), m=+ym.slice(5,7)-1; if(m===0){y--;m=12;} return y+'-'+(m<10?'0'+m:m); }
  function curSheetOf(ym){ return 'T'+String(parseInt(ym.slice(5,7),10)); }  // 2026-07 -> 'T7'
  // Fingerprint nội dung — PHẢI khớp _norm/fingerprint phía Python (bug_backlog.py) để match 2 phía.
  // CỐ Ý BỎ feature (Decision #54): cột "Chức năng" hay bị đổi lúc copy sang sheet tháng mới -> fp đứt.
  function _bnorm(s){ return (s==null?'':(''+s)).toLowerCase().split(/\s+/).filter(Boolean).join(' '); }
  function _fpOf(b){ return _bnorm(b.project)+'|'+_bnorm(b.service)+'|'+_bnorm(b.summary); }
  // Khử trùng theo `key` (issue.key Jira ỔN ĐỊNH, duy nhất — #104) -> không gộp nhầm 2 bug
  // khác nhau trùng summary. Bug không key (legacy) -> fallback fingerprint. created mới nhất
  // thắng. PHẢI khớp _dedup_by_fp phía Python.
  function dedupByFp(list){
    var by = {};
    list.forEach(function(b){ var k=b.key||_fpOf(b), p=by[k]; if(!p || (b.created||'') >= (p.created||'')) by[k]=b; });
    return Object.keys(by).map(function(k){ return by[k]; });
  }

  // Tính tồn đọng cho tháng report 'YYYY-MM' — CREATED-BASED cho nguồn Jira (#104, PHẢI khớp
  // prev_month_backlog phía Python + splitGroups màn Bug). Jira key ổn định + status live ->
  // tính trực tiếp, không sheet/fingerprint/carry:
  //   - mới phát sinh (fresh): created TRONG tháng report.
  //   - tồn đọng (back): created < tháng report VÀ CÒN MỞ tới giờ (nợ cũ chưa đóng, từ mọi tháng).
  // 'đã xử lý nợ cũ' (resolved) KHÔNG suy được chính xác theo lịch sử (không snapshot) -> 0.
  function computeBacklog(reportYm){
    var prev = prevYm(reportYm);
    var back=[], fresh=[];
    BUGS.forEach(function(b){
      var cm=(b.created||'').slice(0,7);
      if(cm===reportYm) fresh.push(b);
      else if(cm && cm < reportYm && isOpenBug(b.status)) back.push(b);
    });
    var newFixed=0;
    fresh.forEach(function(b){ if(isClosed(b.status)) newFixed++; });
    return { hasSnapshot: fresh.length>0 || back.length>0, prev:prev,
             newCount: fresh.length, total: back.length,
             stillOpen: back.length, resolved: 0,
             newOwn: fresh.length, newFixed: newFixed, newOpen: fresh.length - newFixed };
  }

  // Thanh tỷ lệ ngang: [{label,n,color}] -> stacked bar + chú thích số.
  function compBar(segs, height){
    var sum = 0; segs.forEach(function(s){ sum += s.n; });
    if(sum <= 0) return '<div class="an-empty">Không có bug trong kỳ này</div>';
    var bar = segs.map(function(s){ if(!s.n) return '';
      var pct = s.n/sum*100;
      return '<div title="'+esc(s.label)+': '+s.n+'" style="width:'+pct+'%; background:'+s.color
        + '; display:flex; align-items:center; justify-content:center; color:#fff; font-size:12.5px; font-weight:700;">'
        + (pct>7 ? s.n : '') + '</div>';
    }).join('');
    var legend = segs.map(function(s){
      return '<div style="display:flex; align-items:center; gap:6px; font-size:13px; color:var(--on-surface);">'
        + '<span style="width:12px; height:12px; border-radius:3px; background:'+s.color+'; display:inline-block;"></span>'
        + esc(s.label)+' <strong>'+s.n+'</strong></div>';
    }).join('');
    return '<div style="display:flex; height:'+(height||30)+'px; border-radius:6px; overflow:hidden; background:var(--surface-variant);">'+bar+'</div>'
      + '<div style="display:flex; gap:20px; flex-wrap:wrap; margin-top:12px;">'+legend+'</div>';
  }

  // Segment chuẩn cho 1 kỳ — 4 nhóm KHÔNG chồng lấn (tổng = bug mới + tồn đọng T-1):
  // Mới đã fix · Mới chưa fix · Tồn đọng T-1 còn treo · Tồn đọng T-1 đã xử lý.
  function backlogSegs(c){
    return [
      { label:'Bug mới đã fix', n:c.newFixed||0, color:'#36b37e' },
      { label:'Bug mới chưa fix', n:c.newOpen||0, color:'#4c9aff' },
      { label:'Tồn đọng T-1 còn', n:c.stillOpen, color:'#ff5630' },
      { label:'Tồn đọng T-1 đã xử lý', n:c.resolved, color:'#00b8d9' }
    ];
  }

  // ---------- Export PDF (bar chart) ----------
  var btnExport = $('anExportChart');
  if(btnExport) btnExport.addEventListener('click', function(){
    if(!metricCharts || !metricCharts.innerHTML || metricCharts.innerHTML.indexOf('an-empty') >= 0){ toast('Không có dữ liệu để export', false); return; }
    var origText = btnExport.innerHTML;
    btnExport.innerHTML = '<span class="material-symbols-rounded ph-light ph-arrows-clockwise mi-sm"></span> Đang xuất...';
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
  renderValid(); renderMetric(); renderReopen();
})();


})();   // ===== đóng IIFE ngoài cùng (shared scope) — bug-metrics block nằm TRONG để dùng $/esc/readJSON

/* ===== Custom select `xsel` (Decision #87) =====================================
   Popup của <select> native do OS vẽ -> không theme được (list trắng giữa nền tối, font hệ
   thống, không bo góc). Ở đây nâng cấp TẠI CHỖ mọi <select> trên trang: dựng trigger + menu
   tự vẽ, còn <select> gốc giữ nguyên trong DOM (ẩn) làm NGUỒN SỰ THẬT.
   => Controller cũ đọc `sel.value`, gán `sel.innerHTML`, bắt 'change' đều chạy y như trước;
      không phải sửa 20 chỗ render `<select>` bên Python.
   Đồng bộ ngược 3 kênh: (a) MutationObserver childList -> options bị build lại từ data;
   (b) attribute `disabled`; (c) override property `value`/`selectedIndex` per-element vì gán
   thuộc tính KHÔNG sinh event nào để nghe. */
(function(){
  var VAL = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
  var IDX = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'selectedIndex');
  if(!VAL || !IDX) return;                        // trình duyệt lạ -> để native, không phá
  var SEARCH_MIN = 10;                            // >= n option thì thêm ô tìm
  var cur = null;                                 // api đang mở menu

  function icon(name){ return '<span class="material-symbols-rounded ph-light ph-'+name+'"></span>'; }
  function esc(s){ return (s==null?'':String(s))
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }   // module ngoài IIFE chung -> esc riêng
  function fold(s){ return String(s||'').toLowerCase().normalize('NFD')
    .replace(/[̀-ͯ]/g,'').replace(/đ/g,'d'); }  // NFD KHÔNG tách đ -> thay tay (#39)

  function label(sel){ var o=sel.options[sel.selectedIndex]; return o ? o.textContent : ''; }

  function sync(api){
    api.lbl.textContent = label(api.sel);
    api.btn.disabled = api.sel.disabled;
    api.wrap.classList.toggle('disabled', api.sel.disabled);
    api.btn.title = api.sel.title || api.lbl.textContent;
    if(cur === api) fill(api);
  }

  // ---- menu ----
  function fill(api, q){
    var m=api.menu, sel=api.sel, html='', qq=fold(q||''), n=0;
    Array.prototype.forEach.call(sel.children, function(node){
      if(node.tagName==='OPTGROUP'){
        var inner='';
        Array.prototype.forEach.call(node.children, function(o){
          var h=optHTML(o,qq); if(h){ n++; inner+=h; } });
        if(inner) html += '<div class="xsel-grp">'+esc(node.label)+'</div>'+inner;
      } else if(node.tagName==='OPTION'){
        var h=optHTML(node,qq); if(h){ n++; html+=h; }
      }
    });
    var body = api.body || m;
    body.innerHTML = html || '<div class="xsel-empty">Không có mục nào khớp</div>';
    if(!n) return;
    var on = body.querySelector('.xsel-opt.on') || body.querySelector('.xsel-opt:not(.dis)');
    setActive(api, on);
  }
  function optHTML(o, qq){
    if(qq && fold(o.textContent).indexOf(qq)<0) return '';
    return '<div class="xsel-opt'+(o.selected?' on':'')+(o.disabled?' dis':'')+'" data-v="'+esc(o.value)+'">'
      + '<span class="t">'+esc(o.textContent)+'</span>'
      + '<span class="material-symbols-rounded ph-light ph-check chk"></span></div>';
  }
  function setActive(api, el){
    var body=api.body||api.menu;
    body.querySelectorAll('.xsel-opt.active').forEach(function(x){ x.classList.remove('active'); });
    if(el){ el.classList.add('active'); scrollIn(body, el); }
  }
  function scrollIn(box, el){
    var t=el.offsetTop, b=t+el.offsetHeight;
    if(t < box.scrollTop) box.scrollTop=t-4;
    else if(b > box.scrollTop+box.clientHeight) box.scrollTop=b-box.clientHeight+4;
  }

  function place(api){
    var r=api.btn.getBoundingClientRect(), m=api.menu;
    m.style.minWidth=Math.max(r.width, 180)+'px';
    m.style.maxHeight='';
    var below=window.innerHeight-r.bottom-12, above=r.top-12;
    var up = below < 220 && above > below;
    m.classList.toggle('up', up);
    m.style.maxHeight=Math.min(360, Math.max(160, up?above:below))+'px';
    var h=m.offsetHeight, w=m.offsetWidth;
    m.style.top = (up ? Math.max(8, r.top-6-h) : r.bottom+6)+'px';
    m.style.left = Math.max(8, Math.min(r.left, window.innerWidth-w-8))+'px';
  }

  function open(api){
    if(cur) close();
    cur=api;
    var m=document.createElement('div'); m.className='xsel-menu'; api.menu=m;
    if(api.sel.options.length>=SEARCH_MIN){
      var s=document.createElement('div'); s.className='xsel-search';
      s.innerHTML=icon('magnifying-glass')+'<input type="text" placeholder="Tìm…" autocomplete="off">';
      m.appendChild(s);
      api.body=document.createElement('div'); m.appendChild(api.body);
      api.q=s.querySelector('input');
      api.q.addEventListener('input', function(){ fill(api, api.q.value); });
    } else { api.body=null; api.q=null; }
    document.body.appendChild(m);
    fill(api);
    place(api);
    api.wrap.classList.add('open');
    api.btn.setAttribute('aria-expanded','true');
    if(api.q) api.q.focus(); else api.btn.focus();

    m.addEventListener('mousedown', function(e){ e.preventDefault(); });  // giữ focus
    m.addEventListener('click', function(e){
      var o=e.target.closest('.xsel-opt'); if(!o || o.classList.contains('dis')) return;
      pick(api, o.getAttribute('data-v'));
    });
    m.addEventListener('mousemove', function(e){
      var o=e.target.closest('.xsel-opt'); if(o && !o.classList.contains('dis')) setActive(api, o);
    });
  }
  function close(){
    if(!cur) return;
    var api=cur; cur=null;
    if(api.menu && api.menu.parentNode) api.menu.parentNode.removeChild(api.menu);
    api.menu=null; api.body=null; api.q=null;
    api.wrap.classList.remove('open');
    api.btn.setAttribute('aria-expanded','false');
  }
  function pick(api, v){
    var sel=api.sel, changed = String(VAL.get.call(sel)) !== String(v);
    VAL.set.call(sel, v);
    close(); api.btn.focus(); sync(api);
    if(changed) sel.dispatchEvent(new Event('change', {bubbles:true}));
  }
  function move(api, d){
    var body=api.body||api.menu;
    var list=Array.prototype.filter.call(body.querySelectorAll('.xsel-opt'), function(o){ return !o.classList.contains('dis'); });
    if(!list.length) return;
    var i=list.indexOf(body.querySelector('.xsel-opt.active'));
    setActive(api, list[Math.max(0, Math.min(list.length-1, (i<0?0:i)+d))]);
  }

  // ---- dựng 1 select ----
  function build(sel){
    if(sel.__xsel || sel.multiple || sel.size>1 || sel.hasAttribute('data-noxsel')) return;
    var wrap=document.createElement('div'); wrap.className='xsel';
    if(sel.className) wrap.className += ' xsel-of-'+sel.className.split(/\s+/)[0];
    sel.parentNode.insertBefore(wrap, sel);
    wrap.appendChild(sel);
    sel.classList.add('xsel-native'); sel.setAttribute('tabindex','-1'); sel.setAttribute('aria-hidden','true');
    var btn=document.createElement('button');
    btn.type='button'; btn.className='xsel-btn'; btn.setAttribute('aria-haspopup','listbox');
    btn.setAttribute('aria-expanded','false');
    btn.innerHTML='<span class="xsel-lbl"></span>'
      +'<span class="material-symbols-rounded ph-light ph-caret-down xsel-car"></span>';
    wrap.appendChild(btn);
    var api={sel:sel, wrap:wrap, btn:btn, lbl:btn.querySelector('.xsel-lbl'), menu:null};
    sel.__xsel=api;

    btn.addEventListener('click', function(e){ e.preventDefault(); e.stopPropagation();
      if(cur===api) close(); else open(api); });
    btn.addEventListener('keydown', function(e){
      if(cur!==api){
        if(e.key==='ArrowDown'||e.key==='ArrowUp'||e.key==='Enter'||e.key===' '){ e.preventDefault(); open(api); }
        return;
      }
      if(e.key==='Escape'){ e.preventDefault(); e.stopPropagation(); close(); btn.focus(); }
      else if(e.key==='ArrowDown'){ e.preventDefault(); move(api,1); }
      else if(e.key==='ArrowUp'){ e.preventDefault(); move(api,-1); }
      else if(e.key==='Home'){ e.preventDefault(); move(api,-999); }
      else if(e.key==='End'){ e.preventDefault(); move(api,999); }
      else if(e.key==='Enter'||(e.key==='Tab')){
        var a=(api.body||api.menu).querySelector('.xsel-opt.active');
        if(a){ e.preventDefault(); pick(api, a.getAttribute('data-v')); }
      }
    }, true);

    // native đã ẩn -> code cũ gọi sel.focus() (vd auto-focus field đầu trong modal) sẽ rơi vào
    // hư không; chuyển hướng sang trigger để bàn phím vẫn dùng được
    sel.focus = function(){ btn.focus(); };
    // (c) gán property KHÔNG sinh event -> chặn tại chỗ để nhãn khỏi lệch data
    try{
      Object.defineProperty(sel, 'value', {configurable:true,
        get:function(){ return VAL.get.call(this); },
        set:function(v){ VAL.set.call(this, v); sync(api); }});
      Object.defineProperty(sel, 'selectedIndex', {configurable:true,
        get:function(){ return IDX.get.call(this); },
        set:function(v){ IDX.set.call(this, v); sync(api); }});
    }catch(e){}
    // (a)(b) options build lại / disabled đổi
    new MutationObserver(function(){ sync(api); })
      .observe(sel, {childList:true, subtree:true, attributes:true, attributeFilter:['disabled','title']});
    sel.addEventListener('change', function(){ sync(api); });  // ai đó set rồi tự dispatch
    sync(api);
  }

  function scan(root){
    (root||document).querySelectorAll('select:not(.xsel-native)').forEach(build);
  }
  scan();
  // Select sinh động (modal roadmap, cây thư mục /docs, palette…) -> bắt lúc chèn vào DOM
  var pend=false;
  new MutationObserver(function(muts){
    if(pend) return;
    for(var i=0;i<muts.length;i++){ if(muts[i].addedNodes.length){ pend=true;
      requestAnimationFrame(function(){ pend=false; scan(); }); return; } }
  }).observe(document.body, {childList:true, subtree:true});

  // đóng khi bấm ra ngoài / cuộn / resize / Esc ở tầng document
  document.addEventListener('mousedown', function(e){
    if(!cur) return;
    var t=e.target;
    if(t && t.closest && (t.closest('.xsel-menu') || t.closest('.xsel')===cur.wrap)) return;
    close();
  }, true);
  document.addEventListener('keydown', function(e){
    if(cur && e.key==='Escape'){ e.stopPropagation(); var b=cur.btn; close(); b.focus(); }
  }, true);
  window.addEventListener('resize', close);
  window.addEventListener('scroll', function(){ if(cur) place(cur); }, true);
})();

/* ===== Mobile sidebar off-canvas toggle (#navToggle / #navScrim) ===== */
(function(){
  var app=document.querySelector('.app'); if(!app) return;
  var btn=document.getElementById('navToggle'), scrim=document.getElementById('navScrim'),
      sb=document.getElementById('sidebar');
  function close(){ app.classList.remove('nav-open'); }
  function toggle(){ app.classList.toggle('nav-open'); }
  if(btn) btn.addEventListener('click', function(e){ e.stopPropagation(); toggle(); });
  if(scrim) scrim.addEventListener('click', close);
  // Bấm 1 link điều hướng trong sidebar -> đóng (trước khi trang mới load)
  if(sb) sb.querySelectorAll('.nav a').forEach(function(a){ a.addEventListener('click', close); });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape') close(); });
  // Về desktop thì luôn reset trạng thái off-canvas
  window.addEventListener('resize', function(){ if(window.innerWidth>820) close(); });
})();
