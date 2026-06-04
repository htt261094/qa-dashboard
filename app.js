function setupPaginate(box){
  if (box._pg) return;                       // idempotent
  var size = parseInt(box.getAttribute('data-paginate'), 10) || 5;
  var rows = Array.prototype.slice.call(box.querySelectorAll('tbody > tr'));
  if (!rows.length) { box._pg = true; return; }
  if (!rows[0].offsetHeight) return;         // hidden (e.g. inactive tab) -> defer until shown
  box._pg = true;
  var pages = Math.ceil(rows.length / size), page = 0;
  var tbody = rows[0].parentNode;
  var cols = rows[0].cells.length;
  var rowH = rows[0].offsetHeight;
  var fillers = [];
  var nav = document.createElement('div'); nav.className = 'pager';
  var prev = document.createElement('button'); prev.className = 'pager-btn'; prev.textContent = '‹ Prev';
  var info = document.createElement('span'); info.className = 'pager-info';
  var next = document.createElement('button'); next.className = 'pager-btn'; next.textContent = 'Next ›';
  nav.appendChild(prev); nav.appendChild(info); nav.appendChild(next);
  box.appendChild(nav);
  function render(){
    var shown = 0;
    for (var i = 0; i < rows.length; i++){
      var on = (i >= page*size && i < (page+1)*size);
      rows[i].style.display = on ? '' : 'none';
      if (on) shown++;
    }
    while (fillers.length) { var f = fillers.pop(); if (f.parentNode) f.parentNode.removeChild(f); }
    for (var k = shown; k < size; k++){
      var tr = document.createElement('tr'); tr.className = 'pager-filler';
      var td = document.createElement('td'); td.colSpan = cols; td.style.height = rowH + 'px'; td.innerHTML = '&nbsp;';
      tr.appendChild(td); tbody.appendChild(tr); fillers.push(tr);
    }
    info.textContent = (page*size + 1) + '–' + Math.min((page+1)*size, rows.length) + ' / ' + rows.length;
    prev.disabled = (page === 0); next.disabled = (page >= pages - 1);
  }
  prev.addEventListener('click', function(){ if (page > 0) { page--; render(); } });
  next.addEventListener('click', function(){ if (page < pages - 1) { page++; render(); } });
  render();
}
document.querySelectorAll('[data-paginate]').forEach(setupPaginate);

// Tabbed block: switch panels on tab click
document.querySelectorAll('.tabbed').forEach(function(block){
  var tabs = block.querySelectorAll('.tab');
  var panels = block.querySelectorAll('.tab-panel');
  tabs.forEach(function(tab){
    tab.addEventListener('click', function(){
      tabs.forEach(function(t){ t.classList.remove('active'); });
      panels.forEach(function(p){ p.hidden = true; });
      tab.classList.add('active');
      var p = block.querySelector('.tab-panel[data-panel="' + tab.getAttribute('data-tab') + '"]');
      if (p) { p.hidden = false; setupPaginate(p); }   // paginate lazily once visible
    });
  });
});

// Column-1 blocks: any cell whose text may be cut off (ellipsis or clipped) shows full text on hover
document.querySelectorAll('[data-paginate] tbody td, .tab-panel tbody td').forEach(function(td){
  if (td.classList.contains('pager-filler') || td.parentNode.classList.contains('pager-filler')) return;
  var t = td.textContent.trim();
  if (t && !td.title) td.title = t;
});

// Donut: hover slice -> show that slice's % in the center (Jira-style)
document.querySelectorAll('.donut-wrap').forEach(function(wrap){
  var pctEl = wrap.querySelector('.donut-pct');
  var lblEl = wrap.querySelector('.donut-lbl');
  var defPct = pctEl.textContent, defLbl = lblEl.textContent;
  wrap.querySelectorAll('circle[data-pct]').forEach(function(c){
    c.addEventListener('mouseenter', function(){
      pctEl.textContent = c.getAttribute('data-pct') + '%';
      lblEl.textContent = c.getAttribute('data-label');
    });
    c.addEventListener('mouseleave', function(){
      pctEl.textContent = defPct;
      lblEl.textContent = defLbl;
    });
  });
});

// Layout: reserve equal height for all column-1 blocks, then size donuts so column-2 == column-1
function layout(){
  var grid = document.querySelector('.grid-2col');
  if (!grid) return;
  var col1 = grid.children[0], col2 = grid.children[1];
  if (!col1 || !col2) return;

  // 1. paginated blocks are naturally 5-row + pager (equal). Only reserve that height
  //    for blocks WITHOUT a pager (empty / "no task" states) so the column stays uniform.
  var secs = Array.prototype.slice.call(col1.children).filter(function(e){ return e.classList.contains('section'); });
  secs.forEach(function(s){ s.style.height = ''; });
  var refH = 0;
  secs.forEach(function(s){ if (s.querySelector('.pager')) refH = Math.max(refH, s.offsetHeight); });
  if (refH) secs.forEach(function(s){ if (!s.querySelector('.pager') && !s.classList.contains('tabbed')) s.style.height = refH + 'px'; });

  // 2. grow/shrink donuts so column-2 height matches column-1
  var wraps = Array.prototype.slice.call(col2.querySelectorAll('.donut-wrap'));
  wraps.forEach(function(w){ w.style.width = ''; w.style.height = ''; w.style.flexBasis = ''; });
  if (!wraps.length) return;
  var slack = col1.offsetHeight - col2.offsetHeight;
  if (Math.abs(slack) < 4) return;
  var card = wraps[0].parentNode;                     // .chart-card
  var maxDonut = Math.max(180, card.clientWidth - 280); // keep donut + legend side by side
  var add = slack / wraps.length;
  wraps.forEach(function(w){
    var size = Math.max(180, Math.min(w.offsetWidth + add, maxDonut));
    w.style.width = size + 'px'; w.style.height = size + 'px'; w.style.flexBasis = size + 'px';
  });
}
window.addEventListener('load', layout);
window.addEventListener('resize', layout);

// PIC modal: open/close + auto-save edits to the server
(function(){
  var fab = document.getElementById('picFab');
  var overlay = document.getElementById('picOverlay');
  if (!fab || !overlay) return;
  var closeBtn = document.getElementById('picClose');
  var status = document.getElementById('picStatus');
  fab.addEventListener('click', function(){ overlay.classList.add('open'); });
  function close(){ overlay.classList.remove('open'); }
  closeBtn.addEventListener('click', close);
  overlay.addEventListener('click', function(e){ if (e.target === overlay) close(); });
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape') close(); });

  var tbody = overlay.querySelector('.pic-table tbody');
  function collect(){
    var out = [], cur = null;
    tbody.querySelectorAll('tr').forEach(function(tr){
      if (tr.classList.contains('pic-grp')) {
        cur = { group: tr.querySelector('.pic-grp-name').textContent.trim(), rows: [] };
        out.push(cur);
      } else if (tr.classList.contains('pic-row')) {
        if (!cur) { cur = { group: '', rows: [] }; out.push(cur); }
        cur.rows.push({
          flow: tr.querySelector('.pic-flow').textContent.trim(),
          pic: tr.querySelector('.pic-select').value
        });
      }
    });
    return out;
  }
  var timer = null;
  function save(){
    status.textContent = 'Đang lưu…'; status.style.color = '#6b778c';
    fetch('/save-pic', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(collect()) })
      .then(function(r){ return r.json(); })
      .then(function(j){ status.textContent = j.ok ? 'Đã lưu ✓' : 'Lỗi lưu'; status.style.color = j.ok ? '#36b37e' : '#de350b'; })
      .catch(function(){ status.textContent = 'Lỗi lưu'; status.style.color = '#de350b'; });
  }
  function scheduleSave(){ if (timer) clearTimeout(timer); timer = setTimeout(save, 600); }

  function tpl(id){ return document.importNode(document.getElementById(id).content, true).firstElementChild; }
  function addRow(grpTr){
    var node = tpl('picRowTpl');
    var ref = grpTr, next = grpTr.nextElementSibling;
    while (next && next.classList.contains('pic-row')) { ref = next; next = next.nextElementSibling; }
    ref.parentNode.insertBefore(node, ref.nextSibling);
    node.querySelector('.pic-flow').focus();
    scheduleSave();
  }
  function delGroup(grpTr){
    var next = grpTr.nextElementSibling;
    while (next && next.classList.contains('pic-row')) { var n2 = next.nextElementSibling; next.remove(); next = n2; }
    grpTr.remove();
    scheduleSave();
  }
  function addGroup(){
    var g = tpl('picGrpTpl'), r = tpl('picRowTpl');
    tbody.appendChild(g); tbody.appendChild(r);
    g.querySelector('.pic-grp-name').focus();
    scheduleSave();
  }

  overlay.addEventListener('click', function(e){
    var t = e.target;
    if (t.classList.contains('pic-del-row')) { t.closest('tr').remove(); scheduleSave(); }
    else if (t.classList.contains('pic-add-row')) { addRow(t.closest('tr')); }
    else if (t.classList.contains('pic-del-grp')) { if (confirm('Xoá cả nhóm này (gồm tất cả luồng bên trong)?')) delGroup(t.closest('tr')); }
    else if (t.classList.contains('pic-add-grp')) { addGroup(); }
  });
  overlay.addEventListener('input', function(e){
    if (e.target.classList.contains('pic-flow') || e.target.classList.contains('pic-grp-name')) scheduleSave();
  });
  overlay.addEventListener('change', function(e){ if (e.target.classList.contains('pic-select')) scheduleSave(); });
})();

// Theme toggle: light <-> soft dark, persisted in localStorage
(function(){
  var btn = document.getElementById('themeFab');
  if (!btn) return;
  function isDark(){ return document.documentElement.getAttribute('data-theme') === 'dark'; }
  function setIcon(){ btn.textContent = isDark() ? '☀️' : '🌙'; }
  setIcon();
  btn.addEventListener('click', function(){
    var next = isDark() ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('qa-theme', next); } catch (e) {}
    setIcon();
  });
})();

// Activity "Đã đọc": clear pending on the server, empty the block (no reload)
(function(){
  var btn = document.getElementById('actClear');
  if (!btn) return;
  btn.addEventListener('click', function(){
    // clear the block immediately (optimistic), then tell the server (best-effort)
    var s = document.getElementById('actStream');
    if (s) s.innerHTML = '<h2>🔔 Hoạt động <span class="count">0</span></h2><div class="empty">Đã đọc hết. Thông báo mới sẽ xuất hiện ở lần refresh sau.</div>';
    fetch('/clear-activities', { method: 'POST' }).catch(function(){});
  });
})();

// Auto-refresh every 15 min (default ON, pausable, remembered per-browser)
(function(){
  var KEY = 'qa-autorefresh', INTERVAL = 15 * 60 * 1000;
  var btn = document.getElementById('autoBtn');
  var timer = null;
  function isOn(){ try { return localStorage.getItem(KEY) !== 'off'; } catch (e) { return true; } }
  function label(){ if (btn) btn.textContent = isOn() ? '⏸ Auto 15p: ON' : '▶ Auto 15p: OFF'; }
  function schedule(){ if (timer) clearTimeout(timer); if (isOn()) timer = setTimeout(function(){ location.reload(); }, INTERVAL); }
  if (btn) btn.addEventListener('click', function(){
    try { localStorage.setItem(KEY, isOn() ? 'off' : 'on'); } catch (e) {}
    label(); schedule();
  });
  label(); schedule();
})();
