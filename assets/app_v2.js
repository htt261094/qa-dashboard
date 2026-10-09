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
    {label:'Tạo task', icon:'add', run:function(){ var b=$('createIssueBtn'); if(b) b.click(); }},
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

// ================= DASHBOARD — board kiểu Jira (guard #board) =================
// Cột theo status Jira (TO DO · In Progress · PENDING · DONE · CANCELLED), card render
// client-side -> thấy hết việc cùng lúc, KHÔNG phải bấm từng bucket. KPI vẫn lọc nhanh được.
(function(){
  var board=$('board'); if(!board) return;
  var DATA = readJSON('qaData') || { tasks:[], meta:{} };
  var TASKS = DATA.tasks || [];
  var META = DATA.meta || {};
  window.__jiraBase = (TASKS[0] && TASKS[0].jiraUrl ? TASKS[0].jiraUrl.replace(/\/browse\/.*$/, '') : (window.__jiraBase||''));

  var custMap={}; (window.QA_CUSTOM_STATUSES||[]).forEach(function(p){ custMap[p[0]]=p[1]; });
  var COMMENTS={};        // key -> [{author,when,body}] (lazy, dùng cho drawer)
  var DETAIL={};          // key -> {description}
  var dndKey=null, dndInflight={};   // kéo-thả đổi status (giống Jira board)

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
  // KHÔNG còn lọc bucket (#114) — board luôn hiện HẾT; chỉ còn lọc theo ô tìm kiếm topbar.
  function visibleTasks(){
    var q=(($('searchInp')||{}).value||'').toLowerCase();
    if(!q) return TASKS.slice();
    return TASKS.filter(function(t){ return (t.key+' '+t.summary).toLowerCase().indexOf(q)>=0; });
  }

  function chipHTML(t){
    if(!t.customs || !t.customs.length) return '';
    return '<div class="cust-chips">'+t.customs.map(function(v){
      return '<span class="cust-chip"><span class="material-symbols-rounded ph-light ph-circle"></span>'
        +esc(custMap[v]||v)+'<span class="rm material-symbols-rounded ph-light ph-x" data-key="'+esc(t.key)
        +'" data-val="'+esc(v)+'"></span></span>'; }).join('')+'</div>';
  }
  function cardHTML(t){
    // COMMENTS[key] là mảng khi đã fetch (số live); chưa fetch -> số server nhúng sẵn (t.nComments).
    var nc=COMMENTS[t.key] ? COMMENTS[t.key].length : (t.nComments||0);
    var fl='';
    if(t.overdue) fl+='<span class="bc-flag od" title="Quá hạn"><span class="material-symbols-rounded ph-light ph-calendar-x mi-xs"></span></span>';
    if(t.stuck)   fl+='<span class="bc-flag st" title="Kẹt ≥ '+(META.stuckDays||5)+' ngày"><span class="material-symbols-rounded ph-light ph-hourglass mi-xs"></span></span>';
    var cls='bcard'+(t.overdue?' od':(t.stuck?' st':''));
    return '<div class="'+cls+'" draggable="true" data-act="detail" data-key="'+esc(t.key)+'">'
      +'<div class="bc-top"><a class="key" href="'+esc(t.jiraUrl)+'" target="_blank">'+esc(t.key)+'</a>'
      +'<span class="bc-top-r">'+fl
      +'<button class="caret material-symbols-rounded ph-light ph-caret-down mi-sm" data-act="smenu" data-key="'+esc(t.key)+'" title="Đổi trạng thái"></button></span></div>'
      +'<div class="bc-title">'+esc(t.summary)
      +(t.hasNote?' <span class="note-ic material-symbols-rounded ph-light ph-note-pencil mi-xs" title="Có ghi chú riêng"></span>':'')+'</div>'
      +chipHTML(t)
      +'<div class="bc-foot"><span class="assignee"><span class="av '+esc(t.assignee.cls)+'">'+esc(t.assignee.init)+'</span> '+esc(t.assignee.name)+'</span>'
      +'<span class="bc-foot-r">'+dueValHTML(t)
      +(nc?'<span class="bc-cmt" title="'+nc+' bình luận"><span class="material-symbols-rounded ph-light ph-chat-circle mi-xs"></span>'+nc+'</span>':'')
      +'</span></div>'
      +'</div>';
  }
  // Thứ tự cột cố định như board Jira; CANCELLED/status lạ chỉ hiện khi có card.
  var COLS=['TO DO','In Progress','PENDING','DONE','CANCELLED'];
  var CORE={'TO DO':1,'In Progress':1,'PENDING':1,'DONE':1};
  function renderBoard(){
    var all=visibleTasks();
    if(!all.length){ board.innerHTML='<div class="empty-state board-empty">'
        +'<span class="es-ic"><span class="material-symbols-rounded ph-light ph-confetti"></span></span>'
        +'<div class="es-title">Không có task nào 🎉</div>'
        +'<div class="es-hint">Sạch việc rồi — nghỉ tay chút đi.</div>'
        +'</div>'; return; }
    var groups={};
    all.forEach(function(t){ var s=(t.jira||'').trim()||'—'; (groups[s]=groups[s]||[]).push(t); });
    var order=[];
    // Luôn hiện 4 cột lõi (kể cả rỗng) + CANCELLED/status lạ chỉ khi có card.
    COLS.forEach(function(s){ if(CORE[s] || (groups[s]&&groups[s].length)) order.push(s); });
    Object.keys(groups).forEach(function(s){ if(order.indexOf(s)<0) order.push(s); });
    board.innerHTML = order.map(function(s){
      var list=groups[s]||[];
      var body = list.length ? list.map(cardHTML).join('')
               : '<div class="bcol-empty">Kéo task vào đây</div>';
      return '<div class="bcol" data-col="'+esc(s)+'">'
        +'<div class="bcol-head"><span class="bcol-name"><span class="bcol-dot '+jiraCls(s)+'"></span>'+esc(s)+'</span>'
        +'<span class="cc">'+list.length+'</span></div>'
        +'<div class="bcol-body">'+body+'</div></div>';
    }).join('');
    if(window.__smRebind) window.__smRebind();
  }

  // event delegation (board card: toàn card = mở drawer; caret = đổi status; chip x = bỏ nhãn)
  document.addEventListener('click', function(e){
    var rm=e.target.closest('.rm[data-val]'); if(rm){ rmCust(rm.getAttribute('data-key'), rm.getAttribute('data-val')); return; }
    if(e.target.closest('a.key')) return;        // link ID -> mở Jira, KHÔNG mở drawer
    var a=e.target.closest('[data-act]'); if(!a) return;
    var act=a.getAttribute('data-act'), key=a.getAttribute('data-key');
    if(act==='smenu'){ e.stopPropagation(); openStatusMenu(a); }
    else if(act==='detail'){ openDetail(key); }
  });
  var si=$('searchInp'); if(si) si.addEventListener('input', function(){ renderBoard(); });

  // ----- Kéo-thả đổi status giữa cột (giống Jira board) -----
  // Thả 1 card sang cột khác = chuyển issue sang status của cột đó. Phải đi qua transition
  // HỢP LỆ của Jira (PAT cá nhân) -> chính là workflow + quyền của chính chủ:
  //  - lúc dragstart: tra /jira-transitions (cache theo key) rồi SÁNG cột chuyển được
  //    (.can-drop) / MỜ cột không chuyển được (.no-drop) -> biết TRƯỚC khi thả.
  //  - dragover: chỉ nhận thả ở cột hợp lệ (con trỏ cấm ở cột no-drop).
  //  - drop: dùng transition đã cache (không round-trip lại), không có -> báo, KHÔNG ép.
  var trCache={};   // key -> [{id,to}] | 'nopat' (undefined = chưa tra / lỗi mạng tạm)
  function fetchTr(key){
    if(trCache[key]!==undefined) return Promise.resolve(trCache[key]);
    return postJSON('/jira-transitions', { key:key }, 20000).then(function(j){
      if(j && j.code==='no_pat'){ trCache[key]='nopat'; return 'nopat'; }
      if(j && j.ok){ trCache[key]=j.transitions||[]; return trCache[key]; }
      return false;                                  // lỗi -> KHÔNG cache (lần kéo sau thử lại)
    }).catch(function(){ return false; });
  }
  function clearMarks(){
    board.querySelectorAll('.bcol.drop-tgt,.bcol.can-drop,.bcol.no-drop').forEach(function(c){
      c.classList.remove('drop-tgt','can-drop','no-drop'); });
  }
  function markTargets(key){
    if(dndKey!==key) return;                          // drag đã xong/đổi card
    var trs=trCache[key]; if(!Array.isArray(trs)) return;   // nopat/lỗi -> không tô, drop tự báo
    var t=taskByKey(key), cur=((t&&t.jira)||'').trim().toUpperCase();
    var set={}; trs.forEach(function(x){ set[(x.to||'').trim().toUpperCase()]=1; });
    board.querySelectorAll('.bcol').forEach(function(c){
      var s=(c.getAttribute('data-col')||'').trim().toUpperCase();
      c.classList.remove('can-drop','no-drop');
      if(s===cur) return;                             // cột hiện tại: trung tính (no-op)
      if(set[s]) c.classList.add('can-drop'); else c.classList.add('no-drop');
    });
  }
  function droppable(col){                            // cột này có nhận thả card đang kéo không
    if(!dndKey) return false;
    var t=taskByKey(dndKey), s=(col.getAttribute('data-col')||'').trim();
    if((t&&t.jira||'').trim()===s) return true;       // thả lại cột cũ = no-op, cho qua
    var trs=trCache[dndKey];
    if(!Array.isArray(trs)) return true;              // chưa biết -> cho thả, drop validate sau
    var up=s.toUpperCase();
    return trs.some(function(x){ return (x.to||'').trim().toUpperCase()===up; });
  }
  board.addEventListener('dragstart', function(e){
    var card=e.target.closest('.bcard'); if(!card){ return; }
    dndKey=card.getAttribute('data-key'); card.classList.add('dragging');
    if(e.dataTransfer){ e.dataTransfer.effectAllowed='move';
      try{ e.dataTransfer.setData('text/plain', dndKey); }catch(_){} }
    var key=dndKey; fetchTr(key).then(function(){ markTargets(key); });   // tô cột theo workflow+quyền
  });
  board.addEventListener('dragend', function(){
    var d=board.querySelector('.bcard.dragging'); if(d) d.classList.remove('dragging');
    clearMarks(); dndKey=null;
  });
  board.addEventListener('dragover', function(e){
    if(!dndKey) return; var col=e.target.closest('.bcol'); if(!col) return;
    if(!droppable(col)) return;                       // cột cấm -> không preventDefault -> con trỏ "cấm"
    e.preventDefault(); if(e.dataTransfer) e.dataTransfer.dropEffect='move';
    if(!col.classList.contains('drop-tgt')){
      board.querySelectorAll('.bcol.drop-tgt').forEach(function(c){ c.classList.remove('drop-tgt'); });
      col.classList.add('drop-tgt'); }
  });
  board.addEventListener('drop', function(e){
    if(!dndKey) return; var col=e.target.closest('.bcol'); if(!col) return;
    e.preventDefault();
    var target=col.getAttribute('data-col'), key=dndKey, t=taskByKey(key);
    clearMarks();
    if(!t) return;
    if((t.jira||'').trim()===target) return;          // thả lại cột cũ -> bỏ qua
    moveCard(t, key, target);
  });
  function moveCard(t, key, target){
    if(dndInflight[key]) return; dndInflight[key]=true;
    fetchTr(key).then(function(trs){                  // dùng cache đã tra lúc dragstart
      if(trs==='nopat'){ dndInflight[key]=false;
        patToast({ code:'no_pat', msg:'Cần API token Jira để đổi status — vào ⚙ Cài đặt' }); return; }
      if(!Array.isArray(trs)){ dndInflight[key]=false; toast('Lỗi tải bước chuyển', false); return; }
      var tr=trs.filter(function(x){
        return (x.to||'').trim().toUpperCase()===target.toUpperCase(); })[0];
      if(!tr){ dndInflight[key]=false;
        toast('Không có bước chuyển "'+t.jira+'" → "'+target+'" trên Jira', false); return; }
      toast(key+': đang chuyển sang "'+target+'"…', true);
      postJSON('/do-transition', { key:key, id:tr.id, to:tr.to }, 20000).then(function(r){
        dndInflight[key]=false; delete trCache[key]; if(patToast(r)) return;   // status đổi -> cache cũ vô hiệu
        if(r.ok){ var st=r.status||tr.to; t.jira=st;
          var can=(st==='TO DO'||st==='In Progress'); if(!can) t.customs=[]; t.canCustom=can;
          renderBoard(); toast(key+' → '+st+' ✓', true);
          var dEl=$('drawer'); if(dEl && dEl.classList.contains('open')){
            var ka=dEl.querySelector('.key'); if(ka && ka.textContent===key) renderDrawer(t); } }
        else toast(r.msg||('Lỗi đổi status '+key), false);
      }).catch(function(){ dndInflight[key]=false; toast('Lỗi mạng khi đổi status', false); });
    });
  }
  // Warm trCache TRƯỚC khi kéo để màu cột hiện NGAY (không chờ round-trip lúc dragstart):
  //  - nhấn chuột xuống card = tra sớm hơn dragstart vài trăm ms (đủ cho card sắp kéo);
  //  - nền lúc load: tra sẵn các card KHÔNG phải DONE/CANCELLED (card hay kéo), tuần tự cho nhẹ.
  board.addEventListener('mousedown', function(e){
    var card=e.target.closest('.bcard'); if(card) fetchTr(card.getAttribute('data-key'));
  });
  var _warmed=false;
  function warmTransitions(){
    if(_warmed) return; _warmed=true;
    var keys=[], seen={};
    TASKS.forEach(function(t){ var s=(t.jira||'').toUpperCase();
      if(s==='DONE'||s==='CANCELLED'||seen[t.key]) return; seen[t.key]=1; keys.push(t.key); });
    (function next(i){ if(i>=keys.length) return;
      fetchTr(keys[i]).then(function(){ next(i+1); }, function(){ next(i+1); }); })(0);
  }

  // ----- comment fetch (dùng cho drawer) -----
  function fetchComments(key){ return getJSON('/issue-comments?key='+encodeURIComponent(key), 20000)
    .then(function(j){ if(j&&j.ok&&j.detail){ COMMENTS[key]=j.detail.comments||[]; DETAIL[key]=j.detail;
        if(!taskByKey(key)) EXTRA[key]=synthTask(key, j.detail); }
      else COMMENTS[key]=COMMENTS[key]||[]; })
    .catch(function(){ COMMENTS[key]=COMMENTS[key]||[]; }); }

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
          renderDrawer(taskByKey(key)); renderBoard(); toast('Đã gửi comment ✓', true); }
        else toast(j.msg||'Lỗi gửi comment', false); }).catch(function(){ toast('Lỗi mạng', false); }); }
  });
  var dov=$('drawerOv'); if(dov) dov.addEventListener('click', closeDetail);

  // ----- status menu: dùng module chung (__openSmenu/__smSetCustom, xem section shared) -----
  function qaOnChanged(kind, key){
    renderBoard();
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
      if(p.status && p.status!==t.jira){ t.jira=p.status; delete trCache[t.key]; changed=true; }  // status đổi -> transitions cũ vô hiệu
      if(p.customs){ var a=(t.customs||[]).join(','), b=p.customs.join(',');
        if(a!==b){ t.customs=p.customs; changed=true; } }
    });
    if(!changed) return;
    renderBoard();
    var dEl=$('drawer');
    if(dEl && dEl.classList.contains('open')){
      var ka=dEl.querySelector('.key'); var ok=ka&&ka.textContent;
      if(ok && map[ok]){ var tt=taskByKey(ok); if(tt) renderDrawer(tt); }
    }
  };

  window.__applyDuePatch=function(key, val){
    var t=taskByKey(key); if(!t) return;
    recomputeDue(t, val); renderBoard();
  };
  window.__applyFieldPatch=function(key, patch){
    var t=taskByKey(key); if(!t) return;
    applyTaskFields(t, patch); renderBoard();
    var dEl=$('drawer');
    if(dEl && dEl.classList.contains('open')){
      var ka=dEl.querySelector('.key');
      if(ka && ka.textContent===key) renderDrawer(t);
    }
  };
  window.__rerenderRows=renderBoard;
  window.__applyNotePatch=function(key, has){
    var t=TASKS.filter(function(x){ return x.key===key; })[0];
    if(t && !!t.hasNote!==has){ t.hasNote=has; renderBoard(); }
  };

  renderBoard();
  warmTransitions();
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

// ---------- Tạo task (createmeta-động, giống dialog Create của Jira — Decision #113) ----------
// Chọn Dự án -> Loại task -> form field render THEO createmeta của (project, issuetype).
// Field bắt buộc + schema do Jira trả; JS dựng widget tương ứng. Tạo bằng API token cá nhân.
(function(){
  var ov=$('ciOverlay'); if(!ov) return;
  var openBtn=$('createIssueBtn');
  var projInp=$('ciProjInp'), projRes=$('ciProjRes'), projChip=$('ciProjChip');
  var typeSel=$('ciType'), fieldsBox=$('ciFields'), hint=$('ciHint');
  var parentWrap=$('ciParentWrap'), parentInp=$('ciParentInp'), parentRes=$('ciParentRes'),
      parentChip=$('ciParentChip'), parentLbl=$('ciParentLbl');
  var createBtn=$('ciCreate');
  var proj=null;               // {key,name}
  var types=[];                // [{id,name,subtask}]
  var parentKey='';            // key task cha đã chọn
  var userVals={};             // {fieldId:[{name,display}]} cho field user
  var uchipTpl=$('ciUserChipTpl');

  function debounce(fn, ms){ var t; return function(){ var a=arguments, self=this;
    clearTimeout(t); t=setTimeout(function(){ fn.apply(self, a); }, ms||260); }; }

  function open(){ reset(); ov.classList.add('open');
    setTimeout(function(){ if(projInp) projInp.focus(); }, 60); }
  function close(){ ov.classList.remove('open'); projRes.classList.remove('open'); parentRes.classList.remove('open'); }
  function reset(){
    proj=null; types=[]; parentKey=''; userVals={};
    projInp.value=''; projInp.style.display=''; projChip.style.display='none'; projChip.innerHTML='';
    typeSel.innerHTML='<option value="">— Chọn dự án trước —</option>'; typeSel.disabled=true;
    fieldsBox.innerHTML=''; hint.style.display='block';
    hint.textContent='Chọn dự án và loại task để hiện các trường cần nhập.';
    parentWrap.style.display='none'; parentInp.value=''; parentInp.style.display='';
    parentChip.style.display='none'; parentChip.innerHTML='';
    createBtn.disabled=true;
  }

  // ===== typeahead đơn (project / parent): input -> results fixed-position, chọn 1 -> chip =====
  function wireTA(inp, res, chip, loader, fmt, onPick, minLen){
    function place(){ var r=inp.getBoundingClientRect();
      res.style.top=(r.bottom+4)+'px'; res.style.left=r.left+'px'; res.style.width=r.width+'px'; }
    function hide(){ res.classList.remove('open'); res.innerHTML=''; res._opts=[]; res._act=-1; }
    function show(){ place(); res.classList.add('open'); }
    function showChip(label){ chip.innerHTML=label+
        '<button type="button" class="ta-x material-symbols-rounded ph-light ph-x mi-sm" title="Bỏ chọn"></button>';
      chip.style.display='flex'; inp.style.display='none';
      chip.querySelector('.ta-x').addEventListener('click', function(){
        chip.style.display='none'; chip.innerHTML=''; inp.style.display=''; inp.value=''; onPick(null); inp.focus(); }); }
    var run=debounce(function(){
      var q=(inp.value||'').trim();
      if(q.length<(minLen||0) && !(minLen===0)){ hide(); return; }
      loader(q).then(function(opts){
        res._opts=opts||[]; res._act=-1;
        if(!res._opts.length){ res.innerHTML='<div class="ta-empty">Không tìm thấy</div>'; show(); return; }
        res.innerHTML=res._opts.map(function(o,i){ return '<div class="ta-opt" data-i="'+i+'">'+fmt(o)+'</div>'; }).join('');
        show();
      }).catch(function(){ hide(); });
    }, 240);
    inp.addEventListener('input', run);
    inp.addEventListener('focus', function(){ if((inp.value||'').trim().length>=(minLen||0)) run(); });
    window.addEventListener('scroll', function(){ if(res.classList.contains('open')) place(); }, true);
    window.addEventListener('resize', function(){ if(res.classList.contains('open')) place(); });
    inp.addEventListener('keydown', function(e){
      if(!res.classList.contains('open')) return;
      var opts=res._opts||[];
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){ e.preventDefault();
        res._act+=(e.key==='ArrowDown'?1:-1);
        if(res._act<0) res._act=opts.length-1; if(res._act>=opts.length) res._act=0;
        res.querySelectorAll('.ta-opt').forEach(function(el,i){ el.classList.toggle('act', i===res._act); });
      } else if(e.key==='Enter'){ e.preventDefault(); if(res._act>=0) pick(res._act); }
      else if(e.key==='Escape'){ hide(); } });
    res.addEventListener('mousedown', function(e){ var el=e.target.closest('.ta-opt'); if(el) pick(+el.getAttribute('data-i')); });
    inp.addEventListener('blur', function(){ setTimeout(hide, 150); });
    function pick(i){ var o=(res._opts||[])[i]; if(!o) return; onPick(o); showChip(fmt(o)); hide(); }
  }

  wireTA(projInp, projRes, projChip,
    function(q){ return getJSON('/create-projects?q='+encodeURIComponent(q)).then(function(j){
        if(j && j.code==='no_pat'){ patToast(j); return []; } return (j&&j.results)||[]; }); },
    function(o){ return '<b>'+esc(o.key)+'</b>'+esc(o.name||''); },
    function(o){ pickProject(o); }, 0);
  wireTA(parentInp, parentRes, parentChip,
    function(q){ return getJSON('/search-parents?q='+encodeURIComponent(q)).then(function(j){ return (j&&j.results)||[]; }); },
    function(o){ return '<b>'+esc(o.key)+'</b>'+esc(o.summary||''); },
    function(o){ parentKey=o?(o.key||''):''; }, 2);

  function pickProject(o){
    if(!o){ proj=null; typeSel.disabled=true; typeSel.innerHTML='<option value="">— Chọn dự án trước —</option>';
      fieldsBox.innerHTML=''; parentWrap.style.display='none'; createBtn.disabled=true; return; }
    proj=o; fieldsBox.innerHTML=''; parentWrap.style.display='none'; parentKey=''; createBtn.disabled=true;
    typeSel.disabled=true; typeSel.innerHTML='<option value="">Đang tải…</option>';
    hint.style.display='block'; hint.textContent='Đang tải loại task của '+o.key+'…';
    getJSON('/create-issuetypes?project='+encodeURIComponent(o.key)).then(function(j){
      if(j && j.code==='no_pat'){ patToast(j); return; }
      if(!j || !j.ok){ typeSel.innerHTML='<option value="">(lỗi tải loại task)</option>';
        hint.textContent=(j&&j.msg)||'Không tải được loại task.'; return; }
      types=j.results||[];
      typeSel.innerHTML='<option value="">— Chọn loại task —</option>'+types.map(function(t){
        return '<option value="'+esc(t.id)+'" data-sub="'+(t.subtask?1:0)+'">'+esc(t.name)+'</option>'; }).join('');
      typeSel.disabled=false; hint.textContent='Chọn loại task để hiện các trường.';
    }).catch(function(){ typeSel.innerHTML='<option value="">(lỗi mạng)</option>';
      hint.textContent='Lỗi mạng khi tải loại task.'; });
  }

  typeSel.addEventListener('change', function(){
    var id=typeSel.value||''; fieldsBox.innerHTML=''; createBtn.disabled=true;
    if(!id){ parentWrap.style.display='none'; hint.style.display='block';
      hint.textContent='Chọn loại task để hiện các trường.'; return; }
    var t=null; for(var i=0;i<types.length;i++){ if(types[i].id===id){ t=types[i]; break; } }
    var isSub=!!(t && t.subtask);
    parentWrap.style.display=isSub?'block':'none';
    if(parentLbl) parentLbl.innerHTML=isSub?'Task cha <span class="ci-req">*</span>':'Task cha <small class="mhint">(sub-task)</small>';
    hint.style.display='block'; hint.textContent='Đang tải các trường…';
    getJSON('/create-fields?project='+encodeURIComponent(proj.key)+'&type='+encodeURIComponent(id)).then(function(j){
      if(j && j.code==='no_pat'){ patToast(j); return; }
      if(!j || !j.ok){ hint.textContent=(j&&j.msg)||'Không tải được các trường.'; return; }
      renderFields(j.fields||[]);
    }).catch(function(){ hint.textContent='Lỗi mạng khi tải các trường.'; });
  });

  // ===== render field động theo schema createmeta =====
  var SKIP_SYS={ parent:1 };   // parent render riêng (ô Task cha ở trên)
  function fieldHtml(m){
    var t=m.type, items=m.items||'', av=m.allowedValues||[];
    var req=m.required?' <span class="ci-req">*</span>':'';
    var lbl='<label>'+esc(m.name)+req+'</label>';
    if(!m.supported){
      return '<div class="ci-field ci-unsup"><label>'+esc(m.name)+req+'</label>'
        +'<div class="ci-note">Trường này không nhập được ở đây — sửa trực tiếp trên Jira sau khi tạo.</div></div>'; }
    var ctrl='';
    if(t==='user' || (t==='array'&&items==='user')){
      ctrl='<div class="ci-user" data-multi="'+(t==='array'?1:0)+'"><div class="ci-uchips"></div>'
        +'<div class="typeahead"><input type="text" class="ci-uinp" placeholder="Gõ tên người…" autocomplete="off" spellcheck="false">'
        +'<div class="ta-results ci-ures"></div></div></div>';
    } else if(av.length && (t==='option'||t==='priority'||t==='resolution'||t==='securitylevel'
         ||t==='version'||t==='component'||t==='group'
         ||(t==='array'&&(items==='option'||items==='version'||items==='component'||items==='group')))){
      var multi=(t==='array');
      var o=multi?'':'<option value="">— Không chọn —</option>';
      o+=av.map(function(a){ return '<option value="'+esc(a.id)+'">'+esc(a.label)+'</option>'; }).join('');
      ctrl='<select class="ci-inp"'+(multi?' multiple size="4" data-noxsel':'')+'>'+o+'</select>';
    } else if(t==='array' && items==='string'){
      ctrl='<input type="text" class="ci-inp" placeholder="Nhiều giá trị, cách nhau dấu phẩy" autocomplete="off">';
    } else if(t==='number'){
      ctrl='<input type="number" class="ci-inp" step="any" autocomplete="off">';
    } else if(t==='date'){
      ctrl='<input type="date" class="ci-inp">';
    } else if(t==='datetime'){
      ctrl='<input type="datetime-local" class="ci-inp">';
    } else if(t==='string' && (m.system==='description'||m.system==='environment')){
      ctrl='<textarea class="ci-inp" rows="3"></textarea>';
    } else {
      ctrl='<input type="text" class="ci-inp" autocomplete="off" spellcheck="false">';
    }
    return '<div class="ci-field" data-fid="'+esc(m.id)+'" data-type="'+esc(t)+'" data-items="'+esc(items)+'" data-req="'+(m.required?1:0)+'">'+lbl+ctrl+'</div>';
  }
  function renderFields(metas){
    // summary lên đầu, required trước optional (giữ ổn định bằng thứ tự Jira trong mỗi nhóm)
    var shown=metas.filter(function(m){ return !SKIP_SYS[m.system]; });
    shown.sort(function(a,b){
      var ra=(a.system==='summary')?0:(a.required?1:2), rb=(b.system==='summary')?0:(b.required?1:2);
      return ra-rb; });
    fieldsBox.innerHTML=shown.map(fieldHtml).join('');
    hint.style.display='none'; createBtn.disabled=false;
    var first=fieldsBox.querySelector('.ci-inp, .ci-uinp'); if(first) try{ first.focus(); }catch(e){}
  }

  // user field typeahead (delegation trên fieldsBox) — chọn user -> chip + đẩy userVals[fid]
  (function(){
    function uField(el){ return el.closest ? el.closest('.ci-field') : null; }
    function fidOf(f){ return f ? f.getAttribute('data-fid') : ''; }
    function renderChips(f){
      var fid=fidOf(f), box=f.querySelector('.ci-uchips'), list=userVals[fid]||[];
      box.innerHTML='';
      list.forEach(function(u, idx){
        var c=uchipTpl.content.firstElementChild.cloneNode(true);
        c.querySelector('.ci-uchip-t').textContent=u.display||u.name;
        c.querySelector('.ci-uchip-x').addEventListener('click', function(){
          userVals[fid].splice(idx,1); renderChips(f); });
        box.appendChild(c); }); }
    var run=debounce(function(inp){
      var f=uField(inp), res=f.querySelector('.ci-ures'), q=(inp.value||'').trim();
      function place(){ var r=inp.getBoundingClientRect();
        res.style.top=(r.bottom+4)+'px'; res.style.left=r.left+'px'; res.style.width=r.width+'px'; }
      if(q.length<1){ res.classList.remove('open'); res.innerHTML=''; return; }
      getJSON('/search-people?q='+encodeURIComponent(q)).then(function(j){
        var opts=(j&&j.results)||[]; res._opts=opts;
        if(!opts.length){ res.innerHTML='<div class="ta-empty">Không tìm thấy</div>'; }
        else res.innerHTML=opts.map(function(o,i){ return '<div class="ta-opt" data-i="'+i+'"><b>'+esc(o.display||o.name)+'</b><small>'+esc(o.name)+'</small></div>'; }).join('');
        place(); res.classList.add('open');
      }).catch(function(){ res.classList.remove('open'); }); }, 240);
    fieldsBox.addEventListener('input', function(e){
      if(e.target.classList && e.target.classList.contains('ci-uinp')) run(e.target); });
    fieldsBox.addEventListener('mousedown', function(e){
      var opt=e.target.closest('.ci-opt, .ta-opt'); if(!opt) return;
      var res=opt.closest('.ci-ures'); if(!res) return;
      var f=uField(res), fid=fidOf(f), o=(res._opts||[])[+opt.getAttribute('data-i')]; if(!o) return;
      var multi=f.querySelector('.ci-user').getAttribute('data-multi')==='1';
      if(!userVals[fid]) userVals[fid]=[];
      if(!multi) userVals[fid]=[];
      if(!userVals[fid].some(function(u){ return u.name===o.name; })) userVals[fid].push({name:o.name, display:o.display||o.name});
      renderChips(f); res.classList.remove('open'); res.innerHTML='';
      var inp=f.querySelector('.ci-uinp'); inp.value=''; inp.focus(); });
    fieldsBox.addEventListener('blur', function(e){
      if(e.target.classList && e.target.classList.contains('ci-uinp')){
        var res=uField(e.target).querySelector('.ci-ures'); setTimeout(function(){ res.classList.remove('open'); }, 160); } }, true);
  })();

  function collect(){
    var out={};
    fieldsBox.querySelectorAll('.ci-field').forEach(function(f){
      if(f.classList.contains('ci-unsup')) return;
      var fid=f.getAttribute('data-fid'), t=f.getAttribute('data-type'), items=f.getAttribute('data-items');
      if(f.querySelector('.ci-user')){
        var arr=(userVals[fid]||[]).map(function(u){ return u.name; });
        out[fid]=(f.querySelector('.ci-user').getAttribute('data-multi')==='1')?arr:(arr[0]||''); return; }
      var el=f.querySelector('.ci-inp'); if(!el) return;
      if(el.tagName==='SELECT' && el.multiple){
        out[fid]=Array.prototype.slice.call(el.selectedOptions).map(function(o){ return o.value; }).filter(Boolean);
      } else if(t==='array' && items==='string'){
        out[fid]=(el.value||'').split(',').map(function(s){ return s.trim(); }).filter(Boolean);
      } else { out[fid]=el.value; }
    });
    return out;
  }

  createBtn.addEventListener('click', function(){
    if(!proj || !proj.key){ toast('Chưa chọn dự án', false); return; }
    var type=typeSel.value||''; if(!type){ toast('Chưa chọn loại task', false); return; }
    if(parentWrap.style.display!=='none' && !parentKey){
      // chỉ bắt buộc khi loại là sub-task (label có dấu *)
      if(parentLbl && /ci-req/.test(parentLbl.innerHTML)){ toast('Sub-task cần chọn task cha', false); return; } }
    createBtn.disabled=true;
    postJSON('/create-issue', { project:proj.key, type:type, parent:parentKey, fields:collect() }, 90000)
      .then(function(j){
        createBtn.disabled=false;
        if(!j){ toast('Lỗi tạo task', false); return; }
        if(j.code==='no_pat'){ patToast(j); return; }
        if(j.ok){ toast(j.msg||'Đã tạo task ✓', true); close();
          setTimeout(function(){ location.reload(); }, 1100); }
        else { toast(j.msg||'Không tạo được task', false); }    // GIỮ modal để sửa & thử lại
      })
      .catch(function(){ createBtn.disabled=false; toast('Lỗi mạng khi tạo task', false); });
  });

  if(openBtn) openBtn.addEventListener('click', open);
  var cbtn=$('ciCancel'), xbtn=$('ciClose');
  if(cbtn) cbtn.addEventListener('click', close);
  if(xbtn) xbtn.addEventListener('click', close);
  ov.addEventListener('mousedown', function(e){ if(e.target===ov) close(); });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape' && ov.classList.contains('open')) close(); });
})();

// ================= BUG LOG (guard #bugLogData) =================
(function(){
  var DATA = readJSON('bugLogData'); if(!DATA) return;
  var BUGS = DATA.bugs||[], MONTHS = DATA.months||[];
  var SOURCES = DATA.sources||[];    // (nguồn Jira cố định — mảng rỗng; giữ cho fileBugs/activeFid no-op)
  var REOPEN = DATA.reopen||{};      // {bugKey:{count,dev,project,month,last}} reopen tích luỹ
  var base = window.__jiraBase || '';
  var activeFid = '';                // (dead sau #104: không còn picker file; luôn '' = xem tất cả)
  var page = 1, PER = 15;
  var testerFilter = '';   // lọc bảng theo tester (qa_pic); '' = tất cả
  var devFilter = '';      // lọc bảng theo dev in charge (dev_pic); '' = tất cả
  var sevFilter = '';      // lọc theo severity Jira: ''=tất cả, blocker/critical/high/medium/low/none
  // ===== TAB = squad / backlog (Decision #108) =====
  // 4 tab squad CỐ ĐỊNH (user chốt): mỗi tab = bug ĐANG trong active sprint của squad đó (MỌI
  // status). Tab cuối "backlog" = bug NGOÀI active sprint (future + backlog #107) & còn mở,
  // chia tiếp theo 4 squad bằng section header trong bảng. Thay hẳn lăng kính tháng cũ (#75).
  var SQUADS = ['SIT1','SIT2','SIT3','SIT4'];
  function squadRank(sq){ var i=SQUADS.indexOf(sq); return i<0 ? 99 : i; }   // 'Khác' xuống cuối
  function squadOf(b){ var p=(b.project||'').trim(); return SQUADS.indexOf(p)>=0 ? p : 'Khác'; }
  var tab = SQUADS[0];
  try{ var _t=localStorage.getItem('qa-buglog-tab');
       if(_t && (_t==='backlog' || SQUADS.indexOf(_t)>=0)) tab=_t; }catch(e){}
  function saveTab(){ try{ localStorage.setItem('qa-buglog-tab', tab); }catch(e){} }
  var tabs=$('blTabs'), rows=$('blRows'), pager=$('blPager'), cnt=$('blCount');

  function formatCreated(iso) {
    if(!iso) return '—';
    var p = iso.split('-');
    if(p.length >= 3) return p[2]+'/'+p[1]+'/'+p[0];
    return iso;
  }

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

  function fileBugs(){ return BUGS; }   // activeFid đã chết (#104): luôn xem tất cả
  // Predicate lọc-xem (tester/dev/severity) — áp chung cho mọi tab.
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
  function isActive(b){ return (b.sprintState||'backlog')==='active'; }   // trong active sprint (#107)
  // --- membership từng tab (Decision #108) ---
  //   tab squad  = bug active-sprint của squad đó, MỌI status (user chốt "tất cả bug trong sprint").
  //   tab backlog= bug NGOÀI active sprint (future + backlog #107) & CÒN MỞ (bỏ Closed/Rejected —
  //                backlog = việc chờ xử lý, không lôi bug cũ đã đóng), chia tiếp theo squad.
  function activeBugs(sq){ return fileBugs().filter(function(b){
    return isActive(b) && squadOf(b)===sq && passFilters(b); }); }
  function backlogBugs(){ return fileBugs().filter(function(b){
    return !isActive(b) && bugOpen(b.status) && passFilters(b); }); }
  // Bug có thể xuất hiện ở ĐÂU ĐÓ trên trang (active mọi status ∪ backlog còn mở) -> nguồn dropdown.
  function scopeBugs(){ return fileBugs().filter(function(b){
    return isActive(b) || bugOpen(b.status); }); }

  // danh sách tester (qa_pic) phân biệt -> đổ vào dropdown lọc
  function populateTesters(){
    var sel0=$('blTesterFilter'); if(!sel0) return;
    var seen={}, list=[];
    scopeBugs().forEach(function(b){ var q=(b.qa||'').trim();
      if(q && !seen[q]){ seen[q]=true; list.push(q); } });
    list.sort(function(a,b){ return a.localeCompare(b); });
    if(testerFilter && list.indexOf(testerFilter)<0) testerFilter='';
    sel0.innerHTML='<option value="">Tất cả tester</option>'+list.map(function(q){
      return '<option value="'+esc(q)+'"'+(q===testerFilter?' selected':'')+'>'+esc(q)+'</option>'; }).join('');
    populateDevs();
  }
  // danh sách dev (dev_pic) phân biệt -> đổ vào dropdown lọc
  function populateDevs(){
    var sel0=$('blDevFilter'); if(!sel0) return;
    var seen={}, list=[], hasNone=false;
    scopeBugs().forEach(function(b){ var d=(b.dev||'').trim();
      if(d){ if(!seen[d]){ seen[d]=true; list.push(d); } } else hasNone=true; });
    list.sort(function(a,b){ return a.localeCompare(b); });
    if(devFilter && devFilter!=='__none__' && list.indexOf(devFilter)<0) devFilter='';
    if(devFilter==='__none__' && !hasNone) devFilter='';
    var noneOpt = hasNone ? '<option value="__none__"'+(devFilter==='__none__'?' selected':'')+'>(Chưa gán dev)</option>' : '';
    sel0.innerHTML='<option value="">Tất cả dev</option>'+noneOpt+list.map(function(d){
      return '<option value="'+esc(d)+'"'+(d===devFilter?' selected':'')+'>'+esc(d)+'</option>'; }).join('');
  }

  // số bug mỗi tab (đã áp filter -> badge khớp bảng)
  function tabCount(t){ return t==='backlog' ? backlogBugs().length : activeBugs(t).length; }
  function renderTabs(){
    populateTesters();
    var h = SQUADS.map(function(sq){
      return '<button class="bl-tab'+(tab===sq?' active':'')+'" data-tab="'+esc(sq)+'">'
        +'<span class="material-symbols-rounded ph-light ph-users-three"></span> '
        +esc(sq)+' <span class="bl-grptab-n">'+tabCount(sq)+'</span></button>';
    }).join('');
    h += '<button class="bl-tab'+(tab==='backlog'?' active':'')+'" data-tab="backlog">'
      +'<span class="material-symbols-rounded ph-light ph-tray"></span> '
      +'Backlog <span class="bl-grptab-n">'+tabCount('backlog')+'</span></button>';
    tabs.innerHTML = h;
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
  // danh sách bug đang xem của tab hiện tại (đã sort, dùng cho render + export).
  //   tab squad  -> active-sprint squad đó, sort created mới trước.
  //   tab backlog-> gom theo squad (SIT1..SIT4..Khác), trong mỗi squad sort created mới trước.
  function orderedBugs(){
    if(tab==='backlog'){
      return backlogBugs().slice().sort(function(a,b){
        var ra=squadRank(squadOf(a)), rb=squadRank(squadOf(b));
        if(ra!==rb) return ra-rb;
        return (b.created||'').localeCompare(a.created||'');
      });
    }
    return activeBugs(tab).slice().sort(function(a,b){
      return (b.created||'').localeCompare(a.created||''); });
  }
  // dùng cho export (toàn bộ bug tab hiện tại, không phân trang)
  function visibleBugs(){ return orderedBugs(); }

  function render(){
    var isBack = (tab==='backlog');
    var ordered = orderedBugs();
    var total = ordered.length, pages = Math.max(1, Math.ceil(total/PER));
    if(page>pages) page=pages;
    var start=(page-1)*PER, slice=ordered.slice(start, start+PER);
    var cols = 8;   // ID/Mô tả/Ngày/Severity/Trạng thái/Tester/Dev/Liên kết

    var html='';
    if(isBack){
      // đếm từng squad (cho section header) 1 lần
      var secN={}; ordered.forEach(function(b){ var s=squadOf(b); secN[s]=(secN[s]||0)+1; });
      for(var i=0;i<slice.length;i++){
        var b=slice[i], gi=start+i, sq=squadOf(b);
        // header khi: đầu trang, hoặc squad khác dòng liền trước trong danh sách đầy đủ
        if(i===0 || squadOf(ordered[gi-1])!==sq){
          html += '<tr class="bl-section"><td colspan="'+cols+'">'
            + '<span class="material-symbols-rounded ph-light ph-users-three mi-sm"></span> '
            + esc(sq)+' <span class="bl-sec-n">'+secN[sq]+'</span></td></tr>';
        }
        html += rowHTML(b);
      }
    } else {
      html = slice.map(rowHTML).join('');
    }
    if(!total){
      html = '<tr><td colspan="'+cols+'"><div class="empty-state">'
        +'<span class="es-ic"><span class="material-symbols-rounded ph-light ph-bug-beetle"></span></span>'
        +'<div class="es-title">'+(isBack ? 'Không có bug nào ngoài sprint đang chờ'
            : 'Squad '+esc(tab)+' chưa có bug trong sprint đang chạy')+'</div>'
        +'<div class="es-hint">Đổi tab squad/backlog hoặc bỏ bộ lọc tester/dev/severity để xem bug khác.</div>'
        +'</div></td></tr>';
    }
    rows.innerHTML = html;
    animRows(rows);
    cnt.textContent = 'Hiển thị '+slice.length+' / '+total+' bản ghi';
    // pager (dùng chung — số trang + ellipsis + range info)
    pager.innerHTML = total ? pagerHTML(page, pages, total, start, slice.length, 'bản ghi') : '';
  }

  // đổi tab squad/backlog -> về trang 1, dựng lại badge tab + bảng
  function setTab(t){
    if((t!=='backlog' && SQUADS.indexOf(t)<0) || t===tab) return;
    tab=t; saveTab(); page=1; renderTabs(); render();
  }
  // ----- events: tabs -----
  tabs.addEventListener('click', function(e){ var t=e.target.closest('.bl-tab'); if(!t) return;
    setTab(t.getAttribute('data-tab')); });
  // ----- events: pager -----
  pager.addEventListener('click', function(e){ var b=e.target.closest('[data-pg]'); if(!b||b.disabled) return;
    page=parseInt(b.getAttribute('data-pg'),10)||1; render(); });
  // filter đổi -> cập nhật cả badge tab (đếm theo filter) lẫn bảng
  // ----- events: lọc theo tester -----
  (function(){ var tf=$('blTesterFilter'); if(!tf) return;
    tf.addEventListener('change', function(){ testerFilter=tf.value||''; page=1; renderTabs(); render(); }); })();
  // ----- events: lọc theo dev in charge -----
  (function(){ var df=$('blDevFilter'); if(!df) return;
    df.addEventListener('change', function(){ devFilter=df.value||''; page=1; renderTabs(); render(); }); })();
  // ----- events: lọc theo severity -----
  (function(){ var sf=$('blSevFilter'); if(!sf) return;
    sf.addEventListener('change', function(){ sevFilter=sf.value||''; page=1; renderTabs(); render(); }); })();
  // ----- export bảng ĐANG XEM ra .xlsx (tab squad/backlog + filter hiện tại) -----
  function exportExcel(){
    var list=visibleBugs();   // toàn bộ bug tab đang xem (squad/backlog) + tester/dev/sev filter
    if(!list.length){ toast('Không có bug nào để export', false); return; }
    var rows=list.map(function(b){
      var sk = sevOf(b);   // Severity: xuất ĐÚNG mức Jira (#104), 'none' -> rỗng
      return [ b.id||'', b.summary||'', formatCreated(b.created),
               (sk==='none' ? '' : SEV_LABEL[sk]),
               statusLabel(b.statusRaw||b.status), b.qa||'', b.dev||'' ]; });
    var fname='bug-log_'+(tab==='backlog'?'backlog':tab.toLowerCase())+'.xlsx';
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

  // Deep-link ?bug=<key> (từ command palette): nhảy đúng tab squad/backlog + trang,
  // highlight dòng. Copy pattern ?folder= của test-cases.
  var deepBug = null;
  try{ deepBug = new URLSearchParams(location.search).get('bug'); }catch(e){}
  if(deepBug){
    var db = BUGS.filter(function(b){ return b.key===deepBug; })[0];
    if(db){
      testerFilter=''; devFilter=''; sevFilter='';
      var tf=$('blTesterFilter'), df=$('blDevFilter'), svf=$('blSevFilter');
      if(tf) tf.value=''; if(df) df.value=''; if(svf) svf.value='';
      // tab chứa bug: active-sprint -> tab squad của nó; ngoài sprint -> backlog.
      var dtab = isActive(db) ? squadOf(db) : 'backlog';
      if(dtab==='backlog' || SQUADS.indexOf(dtab)>=0) tab=dtab;
      var list0=orderedBugs();
      var idx=-1; list0.forEach(function(b,i){ if(b.key===deepBug) idx=i; });
      if(idx>=0) page=Math.floor(idx/PER)+1;
    } else { deepBug=null; toast('Bug không còn trong log', false); }
  }

  renderTabs(); render();
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

  // Tuổi bug đang mở (#105, redesign #106) — tính thuần client-side (created + status), không cần
  // resolutiondate/changelog. Bug "đang mở" = lifecycle KHÔNG phải Closed/Rejected.
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
  // Thống kê tuổi bug đang mở (KHÔNG lọc tháng — phản ánh trạng thái HIỆN TẠI của mọi bug mở).
  function computeOpenAge(){
    var open = BUGS.filter(function(b){ return b.created && inActive(b) && !isClosed(b.status) && !isReject(b.status); });
    var ages = open.map(function(b){ return _ageDays(b.created); }).filter(function(a){ return a != null; });
    if(!ages.length) return { open: open.length, ages: [], counts: OA_BUCKETS.map(function(){return 0;}),
                              median: 0, maxAge: 0, total: 0 };
    var counts = OA_BUCKETS.map(function(){ return 0; });
    ages.forEach(function(a){
      for(var i=0;i<OA_BUCKETS.length;i++){ if(OA_BUCKETS[i][1]==null || a<=OA_BUCKETS[i][1]){ counts[i]++; break; } }
    });
    var sorted = ages.slice().sort(function(x,y){ return x-y; });
    var mid = Math.floor(sorted.length/2);
    var median = sorted.length%2 ? sorted[mid] : Math.round((sorted[mid-1]+sorted[mid])/2);
    return { open: open.length, ages: ages, counts: counts, median: median,
             maxAge: sorted[sorted.length-1], total: ages.length };
  }

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
  function isReject(s){ return /reject/i.test(s||''); }
  function isClosed(s){ return /closed|đã đóng/i.test(s||''); }
  function sevCounts(list){
    var c = {}; SEV_ORDER.forEach(function(k){ c[k]=0; });
    list.forEach(function(b){ c[sevOf(b)]++; });
    return c;
  }
  var JBASE = (window.__jiraBase||'').replace(/\/+$/,'');
  function pctDisp(p){ return p==null ? '—' : (p%1===0 ? p.toFixed(0) : p.toFixed(1))+'%'; }
  function devList1(s){
    var l=(s||'Chưa gán').trim().split(/[,;+&\/]/).map(function(x){return x.trim();}).filter(Boolean);
    return l.length ? l : ['Chưa gán'];
  }

  // ===== SCOPE = bug trong sprint đang chạy (#106/B) =====
  // Toàn trang tính theo active sprint: squad lệch nhịp vẫn đúng vì mỗi bug mang state sprint của
  // board nó (xác minh probe). Mất lăng kính tháng + freeze/twin Python (dead code, #100) có CHỦ Ý.
  function inActive(b){ return (b.sprintState||'backlog')==='active'; }
  function scopeBugs(){ return BUGS.filter(inActive); }

  // ===== compute trên 1 LIST bug (= SCOPE) — không còn month/freeze =====
  function computeValid(list){
    var mb=dedupByFp(list), total=mb.length,
        reject=mb.filter(function(b){return isReject(b.status);}).length,
        closed=mb.filter(function(b){return isClosed(b.status);}).length, denom=total-reject;
    return { total:total, reject:reject, closed:closed, denom:denom,
             valid: denom>0 ? closed/denom*100 : null,
             rejPct: total>0 ? reject/total*100 : 0 };
  }
  function reopenPct(n, d){ if(d<=0) return null; var p = n/d*100; return (p%1===0 ? p.toFixed(0) : p.toFixed(1)); }
  // Số lần fix = số reopen + 1 nếu bug đang ở trạng thái đã-giao-fix (Fixed/Closed).
  function fixDeliv(r, b){
    var cnt = +(r&&r.count)||0;
    if(b && b.status!=null) return cnt + ((b.status==='Fixed'||b.status==='Closed') ? 1 : 0);
    return cnt + 1;
  }
  // Trả {totalBugs, distinctTotal, perDev:{dev:{nb,fx,denom,proj,detail[]}}} trên LIST (SCOPE).
  // detail kèm key/sev/status để drawer hiển thị (không fetch thêm).
  function computeReopen(list){
    var totalBugs=list.length, distinctTotal=0, perDev={}, byKey={};
    function ensure(d){ return perDev[d] || (perDev[d]={nb:0,fx:0,denom:0,proj:{},detail:[]}); }
    list.forEach(function(b){
      devList1(b.dev).forEach(function(d){ var x=ensure(d); x.denom++;
        var p=(b.project||'Khác').trim(); x.proj[p]=(x.proj[p]||0)+1; });
      if(b.key) byKey[b.key]=b;
    });
    Object.keys(REOPEN).forEach(function(key){
      var r=REOPEN[key]||{}, cnt=+r.count||0; if(cnt<=0) return;
      var b=byKey[key]; if(!b) return;        // chỉ bug trong SCOPE
      var fx=fixDeliv(r,b); distinctTotal++;
      devList1(b.dev).forEach(function(d){ var x=ensure(d); x.nb++; x.fx+=fx;
        x.detail.push({ id:b.id, key:b.key||'', summary:b.summary, reopen:cnt, fix:fx,
                        sev:sevOf(b), status:(b.status_raw||b.status||'') }); });
    });
    Object.keys(perDev).forEach(function(d){ var pj=perDev[d].proj||{}, best='', bn=-1;
      Object.keys(pj).forEach(function(p){ if(pj[p]>bn){ bn=pj[p]; best=p; } });
      perDev[d].squad=best; });
    return { totalBugs:totalBugs, distinctTotal:distinctTotal, perDev:perDev };
  }

  // ===== state chung =====
  var metricCharts = $('anMetricCharts');
  var squadFilter = 'all';   // tab lọc squad cho chart

  // ===== 4 KPI =====
  function fillKpi(cid, badgeCls, badgeTxt, valHtml, sub, footHtml){
    var card=$(cid); if(!card) return;
    var b=card.querySelector('.ank-badge'); if(b){ b.className='ank-badge '+badgeCls; b.textContent=badgeTxt; }
    var body=card.querySelector('.ank-body');
    if(body) body.innerHTML='<span class="ank-val">'+valHtml+'</span><span class="ank-sub">'+sub+'</span>';
    var f=card.querySelector('.ank-foot'); if(f) f.innerHTML=footHtml;
  }
  function renderKpis(){
    var SCOPE=scopeBugs();
    // Valid
    var v=computeValid(SCOPE);
    if(!v.total){
      fillKpi('anKpiValid','soft','Mục tiêu >90%','—','chưa có bug','<span class="ank-mut">Không có bug trong sprint</span>');
      fillKpi('anKpiReject','soft','Tốt: <5%','—','chưa có bug','<span class="ank-mut">—</span>');
    } else {
      var vp=v.valid;
      fillKpi('anKpiValid', vp!=null&&vp>=90?'ok':'soft', vp!=null&&vp>=90?'Đạt >90%':'Mục tiêu >90%',
        pctDisp(vp), 'bug hợp lệ đã đóng',
        '<span class="ank-f-main"><b class="c-ok">'+v.closed+'</b> Closed <span class="sep">/</span> <b>'+v.denom+'</b> Tổng − Reject '+v.reject+'</span>'
        +'<span class="ank-f-side" title="Closed / (Tổng − Reject)">Công thức: Chuẩn</span>');
      var rp=v.rejPct;
      fillKpi('anKpiReject', rp<5?'ok':'bad', rp<5?'Tốt: <5%':'Cao: ≥5%',
        '<span class="c-bad">'+pctDisp(rp)+'</span>', 'tỷ lệ reject',
        '<span class="ank-f-main"><b class="c-bad">'+v.reject+'</b> Reject <span class="sep">/</span> <b>'+v.total+'</b> Tổng số Bug</span>'
        +'<span class="ank-f-side">'+v.reject+' / '+v.total+' bug</span>');
    }
    // Reopen
    var ro=computeReopen(SCOPE), hp=reopenPct(ro.distinctTotal, ro.totalBugs);
    if(hp===null){
      fillKpi('anKpiReopen','soft','—','—','chưa có bug','<span class="ank-mut">Không có bug trong sprint</span>');
    } else {
      var hpn=+hp, rcls=hpn<=10?'ok':(hpn<=25?'warn':'bad'),
          rtxt=hpn<=10?'Chất lượng cao':(hpn<=25?'Cần theo dõi':'Cần cải thiện'),
          good=Math.max(0, 100-hpn);
      fillKpi('anKpiReopen', rcls, rtxt, '<span class="c-ok">'+hp+'%</span>', 'bug bị reopen',
        '<span class="ank-f-main">Fix lần đầu thành công</span>'
        +'<span class="ank-f-side c-ok">● '+(good%1===0?good.toFixed(0):good.toFixed(1))+'% đạt chuẩn</span>');
    }
    // Open (trạng thái hiện tại, không theo tháng)
    var oa=computeOpenAge();
    fillKpi('anKpiOpen', oa.open>0?'info':'ok', oa.open>0?'Đang xử lý':'Sạch',
      ''+oa.open, 'bug đang active',
      '<span class="ank-f-main">Trung vị: <b class="c-info">'+oa.median+' ngày</b></span>'
      +'<span class="ank-f-side">Lâu nhất: <b>'+oa.maxAge+' ngày</b></span>');
  }

  // ===== section Tuổi bug đang mở =====
  function renderAge(){
    var pills=$('anAgePills'), dist=$('anAgeDist'); if(!dist) return;
    var oa=computeOpenAge();
    if(pills) pills.innerHTML =
        '<span class="an-pill info"><span class="k">Bug đang mở:</span><b>'+oa.open+'</b></span>'
      + '<span class="an-pill warn"><span class="k">Tuổi trung vị:</span><b>'+oa.median+' ngày</b></span>'
      + '<span class="an-pill"><span class="k">Mở lâu nhất:</span><b>'+oa.maxAge+' ngày</b></span>';
    if(!oa.total){
      dist.innerHTML='<div class="an-empty">Không có bug nào đang mở 🎉</div>'; return;
    }
    var maxC=0; oa.counts.forEach(function(c){ if(c>maxC) maxC=c; });
    dist.innerHTML='<div class="oa-dist-title">Phân bố theo tuổi</div>'
      + OA_BUCKETS.map(function(bk,i){
          var c=oa.counts[i], pct=maxC?c/maxC*100:0, share=oa.total?Math.round(c/oa.total*100):0;
          return '<div class="oa-row'+(c?'':' zero')+'">'
            + '<span class="lab">'+bk[0]+'</span>'
            + '<div class="oa-track"><div class="oa-fill" style="width:'+(c?Math.max(6,pct):0)+'%;background:'+bk[2]+';">'
            +   (c?'<span class="oa-inbar">'+c+' bug</span>':'')+'</div></div>'
            + '<span class="oa-cnt">'+share+'%</span></div>';
        }).join('');
  }

  // ===== chart bug theo squad & dev, chồng severity (SCOPE = active sprint, #106/B) =====
  function renderMetric(){
    if(!metricCharts) return;
    var sev=$('anSevStrip'), stats=$('anChartStats'), tabs=$('anSquadTabs'), badge=$('anChartSquadBadge');
    if(sev) sev.innerHTML='';
    var mBugs=scopeBugs();
    var squads={}, devCount={};
    mBugs.forEach(function(b){
      var p=(b.project||'Khác').trim(), sk=sevOf(b);
      var sq=squads[p]||(squads[p]={devs:{}, total:0});
      devList1(b.dev).forEach(function(d){
        var dv=sq.devs[d]||(sq.devs[d]={sev:{}, total:0});
        dv.sev[sk]=(dv.sev[sk]||0)+1; dv.total++; sq.total++;
        devCount[d]=true;
      });
    });
    var squadList=Object.keys(squads).sort();
    var grand=mBugs.length, fixed=mBugs.filter(function(b){return isClosed(b.status);}).length,
        nDev=Object.keys(devCount).length;
    if(badge) badge.textContent=squadList.length+' squad • '+nDev+' dev';
    if(stats) stats.innerHTML=
        '<div class="an-stile"><b>'+grand+'</b><span>Bug trong sprint</span></div>'
      + '<div class="an-stile"><b class="c-ok">'+fixed+'<i>/'+grand+'</i></b><span>Đã đóng</span></div>';
    // tabs lọc squad
    if(tabs){
      var th='<button class="an-tab'+(squadFilter==='all'?' on':'')+'" data-sq="all">Tất cả <i>'+nDev+' dev • '+grand+'</i></button>';
      squadList.forEach(function(p){ var sq=squads[p], dc=Object.keys(sq.devs).length;
        th+='<button class="an-tab'+(squadFilter===p?' on':'')+'" data-sq="'+esc(p)+'">'+esc(p)+' <i>'+dc+' dev • '+sq.total+'</i></button>'; });
      tabs.innerHTML=th;
    }
    if(!squadList.length){ metricCharts.innerHTML='<div class="an-empty">Không có bug nào trong sprint đang chạy</div>'; }
    else {
      // yMax từ dev đông bug nhất
      var maxDev=0; squadList.forEach(function(p){ var dv=squads[p].devs;
        Object.keys(dv).forEach(function(d){ if(dv[d].total>maxDev) maxDev=dv[d].total; }); });
      var yMax=Math.max(4, Math.ceil(maxDev/2)*2), steps=yMax/2, H=190;
      var grid=''; for(var g=0;g<=steps;g++){ grid+='<div class="an-grline"><span>'+Math.round(yMax-(yMax/steps)*g)+'</span></div>'; }
      var shownSquads=squadList.filter(function(p){ return squadFilter==='all'||squadFilter===p; });
      var groups=shownSquads.map(function(p){
        var sq=squads[p], devs=Object.keys(sq.devs).sort(function(a,b){ return sq.devs[b].total-sq.devs[a].total; });
        var bars=devs.map(function(d){
          var dv=sq.devs[d], segs='';
          SEV_ORDER.forEach(function(sk){ var n=dv.sev[sk]; if(!n) return;
            var h=n/yMax*H;
            segs+='<div class="an-seg" style="height:'+h+'px;background:'+SEV_COLOR[sk]+';" title="'+esc(SEV_LABEL[sk])+': '+n+'"></div>'; });
          return '<div class="an-devcol" title="'+esc(d)+': '+dv.total+' bug">'
            + '<span class="an-devn">'+dv.total+'</span>'
            + '<div class="an-bar" style="height:'+H+'px;">'+segs+'</div>'
            + '<span class="an-devl">'+esc(d)+'</span></div>';
        }).join('');
        return '<div class="an-squad"><div class="an-squad-bars">'+bars+'</div>'
          + '<div class="an-squad-name">'+esc(p)+' <i>'+sq.total+'</i></div></div>';
      }).join('');
      metricCharts.innerHTML='<div class="an-chart-inner">'
        + '<div class="an-grid" style="height:'+H+'px;">'+grid+'</div>'
        + '<div class="an-groups">'+groups+'</div></div>';
    }
    // strip severity (tất cả mBugs)
    if(sev){
      var c=sevCounts(mBugs), parts=SEV_PIE.filter(function(k){return c[k]>0;}).map(function(k){
        return '<span class="an-sevp" style="--sc:'+SEV_COLOR[k]+';"><span class="d"></span>'+esc(SEV_LABEL[k])+': <b>'+c[k]+'</b></span>'; }).join('');
      var none=c.none?'<span class="an-sevp mut">Chưa phân loại: <b>'+c.none+'</b></span>':'';
      sev.innerHTML = mBugs.length
        ? '<span class="an-sevp-lbl">Mức độ nghiêm trọng:</span>'+parts+none
        : '';
    }
  }
  if($('anSquadTabs')) $('anSquadTabs').addEventListener('click', function(e){
    var b=e.target.closest('.an-tab'); if(!b) return;
    squadFilter=b.getAttribute('data-sq')||'all'; renderMetric();
  });

  // ===== bảng Reopen + drawer =====
  var reopenHead=$('anReopenHead'), reopenRows=$('anReopenRows'), LAST_REOPEN=null;
  function riskOf(pct){
    if(pct==null) return {t:'—', c:'mut'};
    if(pct===0) return {t:'Chuẩn', c:'ok'};
    if(pct<=10) return {t:'Tốt', c:'ok'};
    if(pct<=20) return {t:'An toàn', c:'warn'};
    return {t:'Cần chú ý', c:'bad'};
  }
  function renderReopen(){
    if(!reopenHead || !reopenRows) return;
    var avg=$('anReopenAvg'), tip=$('anReopenTip'), cbadge=$('anReopenCountBadge');
    var ro=computeReopen(scopeBugs()); LAST_REOPEN=ro;
    var perDev=ro.perDev, devList=Object.keys(perDev).sort(function(a,b){
      var pa=reopenPct(perDev[a].nb,perDev[a].denom), pb=reopenPct(perDev[b].nb,perDev[b].denom);
      return (pb===null?-1:+pb)-(pa===null?-1:+pa) || perDev[b].nb-perDev[a].nb; });
    var hp=reopenPct(ro.distinctTotal, ro.totalBugs);
    if(cbadge) cbadge.textContent=devList.length+' dev';
    if(avg) avg.innerHTML='TB Reopen tháng này: <b class="'+(hp===null?'mut':(+hp>20?'c-bad':(+hp>10?'c-warn':'c-ok')))+'">'+(hp===null?'—':hp+'%')+'</b>';
    reopenHead.innerHTML='<th>Developer</th><th class="ctr">Reopen / Fix</th><th class="ctr">Tỷ lệ Reopen</th>'
      +'<th class="ctr">Đánh giá</th><th class="rgt">Chi tiết</th>';
    if(!devList.length){
      reopenRows.innerHTML='<tr><td colspan="5" class="anrt-empty">Chưa ghi nhận reopen nào trong tháng này 🎉</td></tr>';
      if(tip) tip.innerHTML=''; return;
    }
    reopenRows.innerHTML=devList.map(function(d){
      var e=perDev[d], pr=reopenPct(e.nb,e.denom), rk=riskOf(pr===null?null:+pr),
          pv=pr===null?0:+pr, cN=pv>20?'#ff5630':(pv>10?'#ffab00':'#36b37e');
      var action = e.nb>0
        ? '<button class="anrt-btn" data-dev="'+esc(d)+'"><span class="material-symbols-rounded ph-light ph-eye mi-sm"></span> Xem bug ('+e.nb+')</button>'
        : '<span class="anrt-none">Chưa có reopen</span>';
      return '<tr><td class="anrt-dev"><span class="anrt-ava c-'+rk.c+'">'+esc((d[0]||'?').toUpperCase())+'</span>'
        + '<span><b>'+esc(d)+'</b>'+(e.squad?'<i>'+esc(e.squad)+'</i>':'')+'</span></td>'
        + '<td class="ctr mono"><b class="'+(e.nb>0?'c-bad':'')+'">'+e.nb+'</b> / '+e.fx+'</td>'
        + '<td class="ctr"><div class="anrt-rate"><div class="anrt-track"><div class="anrt-fill" style="width:'+Math.min(100,pv)+'%;background:'+cN+';"></div></div>'
        +   '<span class="mono">'+(pr===null?'—':pr+'%')+'</span></div></td>'
        + '<td class="ctr"><span class="anrt-risk c-'+rk.c+'">'+rk.t+'</span></td>'
        + '<td class="rgt">'+action+'</td></tr>';
    }).join('');
    // quick tip
    if(tip){
      var warn=devList.filter(function(d){ var p=reopenPct(perDev[d].nb,perDev[d].denom); return p!==null && +p>20; });
      tip.innerHTML = warn.length
        ? '<span class="an-tip bad"><span class="material-symbols-rounded ph-light ph-warning mi-sm"></span> Có <b>'+warn.length+' dev</b> vượt ngưỡng reopen (&gt;20%). Nên review chất lượng fix &amp; SIT.</span>'
        : '<span class="an-tip ok"><span class="material-symbols-rounded ph-light ph-check-circle mi-sm"></span> Không dev nào vượt ngưỡng reopen 20%. Chất lượng release ổn định.</span>';
    }
  }
  if(reopenRows) reopenRows.addEventListener('click', function(e){
    var b=e.target.closest('.anrt-btn'); if(!b) return;
    openDrawer(b.getAttribute('data-dev'));
  });

  // ---- drawer chi tiết bug reopen của 1 dev (chỉ field có sẵn — #106) ----
  var drawer=$('anDrawer'), drawerBody=$('anDrawerBody'), drawerDev=$('anDrawerDev');
  function openDrawer(dev){
    if(!drawer || !LAST_REOPEN) return;
    var e=(LAST_REOPEN.perDev||{})[dev]; if(!e) return;
    if(drawerDev) drawerDev.textContent=dev+(e.squad?' • '+e.squad:'');
    var items=(e.detail||[]).slice().sort(function(a,b){ return b.reopen-a.reopen; });
    var rows=items.map(function(it){
      var link=(it.key && JBASE) ? '<a href="'+JBASE+'/browse/'+encodeURIComponent(it.key)+'" target="_blank" rel="noopener">'+esc(it.id||it.key)+'</a>' : esc(it.id||it.key||'(bug)');
      var sv=it.sev&&it.sev!=='none' ? '<span class="andr-sev" style="background:'+SEV_COLOR[it.sev]+';">'+esc(SEV_LABEL[it.sev])+'</span>' : '';
      return '<div class="andr-bug">'
        + '<div class="andr-bug-top"><span class="andr-key">'+link+'</span>'+sv
        +   '<span class="andr-rp">'+(+(it.reopen))+'x reopen</span>'
        +   (it.status?'<span class="andr-st">'+esc(it.status)+'</span>':'')+'</div>'
        + '<div class="andr-sum">'+esc(it.summary||'(không mô tả)')+'</div></div>';
    }).join('');
    if(drawerBody) drawerBody.innerHTML =
        '<div class="andr-banner">Số bug bị reopen: <b class="c-bad">'+e.nb+'</b> · Tổng lượt fix: <b>'+e.fx
      + '</b> · Tỷ lệ: <b>'+(reopenPct(e.nb,e.denom)||'—')+(reopenPct(e.nb,e.denom)===null?'':'%')+'</b></div>'
      + (rows || '<div class="an-empty">Không có bug reopen.</div>');
    drawer.classList.add('open'); drawer.setAttribute('aria-hidden','false');
  }
  function closeDrawer(){ if(drawer){ drawer.classList.remove('open'); drawer.setAttribute('aria-hidden','true'); } }
  if($('anDrawerClose')) $('anDrawerClose').addEventListener('click', closeDrawer);
  if($('anDrawerBackdrop')) $('anDrawerBackdrop').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', function(e){ if(e.key==='Escape' && drawer && drawer.classList.contains('open')) closeDrawer(); });

  // ===== Tình trạng theo Sprint — bug đang mở phân active/future/backlog (#106/B) =====
  function spTile(cls, title, sub, n, color){
    return '<div class="an-sp-tile '+cls+'"><div class="an-sp-n" style="color:'+color+'">'+n+'</div>'
      + '<div class="an-sp-t">'+title+'</div><div class="an-sp-s">'+sub+'</div></div>';
  }
  function renderSprint(){
    var el=$('anSprintBody'); if(!el) return;
    var openBugs=BUGS.filter(function(b){ return isOpenBug(b.status); });
    var buckets={active:0, future:0, backlog:0}, backlogBySquad={};
    openBugs.forEach(function(b){
      var st=b.sprintState||'backlog'; if(!(st in buckets)) st='backlog';
      buckets[st]++;
      if(st==='backlog'){ var p=(b.project||'Khác').trim(); backlogBySquad[p]=(backlogBySquad[p]||0)+1; }
    });
    if(!openBugs.length){ el.innerHTML='<div class="an-empty">Không có bug nào đang mở 🎉</div>'; return; }
    var tiles='<div class="an-sp-tiles">'
      + spTile('active','Trong sprint','Đang làm kỳ này', buckets.active, '#36b37e')
      + spTile('future','Đã xếp kỳ sau','PO đã đưa vào sprint tới', buckets.future, '#4c9aff')
      + spTile('backlog','Backlog chờ PO','Rớt sprint — cần leader quyết', buckets.backlog, '#ff5630')
      + '</div>';
    var bar=compBar([
      {label:'Trong sprint', n:buckets.active, color:'#36b37e'},
      {label:'Kỳ sau', n:buckets.future, color:'#4c9aff'},
      {label:'Backlog chờ PO', n:buckets.backlog, color:'#ff5630'}], 26);
    var sq=Object.keys(backlogBySquad).sort();
    var blList = buckets.backlog
      ? '<div class="an-sp-bl"><span class="an-sp-bl-lbl">Backlog chờ PO theo squad:</span>'
        + sq.map(function(p){ return '<span class="an-sevp mut">'+esc(p)+': <b>'+backlogBySquad[p]+'</b></span>'; }).join('')
        + '</div>'
      : '<div class="an-sp-bl ok"><span class="material-symbols-rounded ph-light ph-check-circle mi-sm"></span> Không có bug nào kẹt ngoài sprint.</div>';
    el.innerHTML = tiles + '<div class="an-sp-bar">'+bar+'</div>' + blList + sprintChecklist(openBugs);
  }

  // Checklist review cuối sprint (#111): bug ĐANG MỞ trong active sprint thiếu metadata mà 2
  // leader phải soát — chưa gán dev / chưa đặt severity. (Bug rớt sprint đã nêu ở khối backlog.)
  function sprintChecklist(openBugs){
    var act=openBugs.filter(inActive);
    var noDev=act.filter(function(b){ return !(b.dev||'').trim(); });
    var noSev=act.filter(function(b){ return sevOf(b)==='none'; });
    if(!noDev.length && !noSev.length){
      return '<div class="an-ck ok"><span class="material-symbols-rounded ph-light ph-check-circle mi-sm"></span>'
        + ' Mọi bug trong sprint đã đủ dev + severity.</div>';
    }
    function rows(list){
      return list.map(function(b){
        return '<a class="an-ck-row" href="'+JBASE+'/browse/'+encodeURIComponent(b.key)+'" target="_blank" rel="noopener">'
          + '<span class="an-ck-key">'+esc(b.key)+'</span>'
          + '<span class="an-ck-sum">'+esc(b.summary||'')+'</span>'
          + '<span class="an-ck-squad">'+esc(b.project||'—')+'</span></a>';
      }).join('');
    }
    function group(title, list){
      if(!list.length) return '';
      return '<div class="an-ck-grp"><div class="an-ck-head">'+esc(title)+' <b>'+list.length+'</b></div>'
        + '<div class="an-ck-list">'+rows(list)+'</div></div>';
    }
    return '<div class="an-ck"><div class="an-ck-title">'
      + '<span class="material-symbols-rounded ph-light ph-clipboard-text mi-sm"></span> Cần soát trước khi chốt sprint</div>'
      + group('Chưa gán dev', noDev) + group('Chưa đặt severity', noSev) + '</div>';
  }

  // ---------- helper (giữ lại cho dedup/compBar) ----------
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
  var btnExport = $('anExport');
  if(btnExport) btnExport.addEventListener('click', function(){
    if(!metricCharts || !metricCharts.innerHTML || metricCharts.innerHTML.indexOf('an-empty') >= 0){ toast('Không có dữ liệu để export', false); return; }
    var origText = btnExport.innerHTML;
    btnExport.innerHTML = '<span class="material-symbols-rounded ph-light ph-arrows-clockwise mi-sm"></span> Đang xuất...';
    btnExport.disabled = true;
    function doExport(){
      var titleEl = document.createElement('div');
      titleEl.style.cssText = 'font-size:24px; font-weight:bold; text-align:center; width:100%; margin-bottom:20px;';
      titleEl.style.color = getComputedStyle(document.body).getPropertyValue('--on-surface') || '#000';
      titleEl.textContent = 'Bug theo squad & dev — sprint đang chạy';
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
        pdf.save('Bug_Metric_sprint.pdf');
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

  // ===== Xu hướng Reopen qua các Sprint (#112) — suy thẳng từ data sẵn có, 0 store/0 call =====
  // Gom TẤT CẢ bug theo tên sprint (mọi bug mang field sprint + reopen từ changelog), tính tỷ lệ
  // reopen per-dev mỗi sprint = matrix dev x sprint. Bug không gắn sprint -> bỏ qua.
  function sprintNum(s){ var m=(s||'').match(/(\d+)\s*$/); return m ? +m[1] : 1e9; }
  function sprintSort(a,b){ var na=sprintNum(a), nb=sprintNum(b); return na!==nb ? na-nb : (a<b?-1:a>b?1:0); }
  function roCls(p){ return p===null ? '' : (+p<=10 ? 'ok' : (+p<=25 ? 'warn' : 'bad')); }
  function renderReopenTrend(){
    var el=$('anTrendBody'); if(!el) return;
    var bySprint={};
    BUGS.forEach(function(b){ var s=(b.sprint||'').trim(); if(!s) return; (bySprint[s]||(bySprint[s]=[])).push(b); });
    var sprints=Object.keys(bySprint).sort(sprintSort);
    if(!sprints.length){ el.innerHTML='<div class="an-empty">Chưa có bug nào gắn sprint để dựng xu hướng.</div>'; return; }
    var roBy={}, devSet={};
    sprints.forEach(function(s){ var ro=computeReopen(bySprint[s]); roBy[s]=ro;
      Object.keys(ro.perDev).forEach(function(d){ if(d) devSet[d]=1; }); });
    var devs=Object.keys(devSet).sort();
    // hàng tổng mỗi sprint (gộp mọi dev) — số bug + % reopen chung
    var head='<tr><th class="ant-dev">Developer</th>'
      + sprints.map(function(s){ return '<th class="ant-sp">'+esc(s)+'</th>'; }).join('')
      + '<th class="ant-sp ant-trend">Xu hướng</th></tr>';
    function cell(p, n){
      if(p===null) return '<td class="ant-cell"><span class="ant-na">—</span></td>';
      return '<td class="ant-cell"><span class="ant-pct '+roCls(p)+'">'+p+'%</span>'
        + '<span class="ant-n">'+n+' bug</span></td>';
    }
    var rows=devs.map(function(d){
      var cells='', series=[];
      sprints.forEach(function(s){ var pd=roBy[s].perDev[d];
        if(pd && pd.denom>0){ var p=reopenPct(pd.nb, pd.denom); series.push(p===null?null:+p); cells+=cell(p, pd.denom); }
        else { series.push(null); cells+=cell(null,0); }
      });
      return '<tr><td class="ant-dev">'+esc(d)+'</td>'+cells+'<td class="ant-cell ant-trend">'+trendArrow(series)+'</td></tr>';
    }).join('');
    // hàng "Tất cả" (chung mọi dev) ở cuối
    var allCells='', allSeries=[];
    sprints.forEach(function(s){ var ro=roBy[s], p=reopenPct(ro.distinctTotal, ro.totalBugs);
      allSeries.push(p===null?null:+p); allCells+=cell(p, ro.totalBugs); });
    var allRow='<tr class="ant-all"><td class="ant-dev">Tất cả</td>'+allCells
      +'<td class="ant-cell ant-trend">'+trendArrow(allSeries)+'</td></tr>';
    el.innerHTML='<div class="an-trend-wrap"><table class="ant-table">'
      + '<thead>'+head+'</thead><tbody>'+rows+allRow+'</tbody></table></div>';
  }
  // Mũi tên xu hướng: so 2 giá trị không-null gần nhất. Reopen GIẢM = tốt lên (xanh ▼).
  function trendArrow(series){
    var pts=series.filter(function(v){ return v!=null; });
    if(pts.length<2) return '<span class="ant-flat">·</span>';
    var last=pts[pts.length-1], prev=pts[pts.length-2];
    if(last<prev) return '<span class="ant-up" title="Giảm reopen — tốt lên">▼ '+(prev-last).toFixed(0)+'%</span>';
    if(last>prev) return '<span class="ant-down" title="Tăng reopen — tệ đi">▲ '+(last-prev).toFixed(0)+'%</span>';
    return '<span class="ant-flat" title="Không đổi">→</span>';
  }

  function renderAll(){ renderKpis(); renderSprint(); renderAge(); renderMetric(); renderReopen(); renderReopenTrend(); }
  renderAll();   // không còn selector tháng — toàn trang theo active sprint (#106/B)
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

/* ===== /today — Copy standup (#110): copy text đã dựng server-side vào clipboard =====
   IIFE top-level (ngoài scope `toast`) -> feedback ngay trên nút, không phụ thuộc helper. */
(function(){
  var btn=document.getElementById('copyStandup'), src=document.getElementById('standupText');
  if(!btn || !src) return;
  var orig=btn.innerHTML, timer=0;
  function flash(txt){ btn.textContent=txt; clearTimeout(timer);
    timer=setTimeout(function(){ btn.innerHTML=orig; }, 1600); }
  function legacyCopy(txt){
    try{ var ta=document.createElement('textarea'); ta.value=txt; ta.style.position='fixed'; ta.style.opacity='0';
      document.body.appendChild(ta); ta.select(); var r=document.execCommand('copy'); document.body.removeChild(ta); return r; }
    catch(e){ return false; }
  }
  btn.addEventListener('click', function(){
    var txt=src.textContent || '', ok=function(){ flash('✓ Đã copy'); }, fail=function(){ flash('✗ Không copy được'); };
    if(navigator.clipboard && navigator.clipboard.writeText){
      navigator.clipboard.writeText(txt).then(ok).catch(function(){ legacyCopy(txt)?ok():fail(); });
    } else { legacyCopy(txt)?ok():fail(); }
  });
})();
