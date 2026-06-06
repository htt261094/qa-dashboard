// Filter theo người: 1 dòng có khớp filter hiện tại không? (dòng không mang
// data-assignee/reporter -> luôn hiện, vd bảng không theo người)
function rowMatch(row){
  var f = window.qaFilter;
  if (!f || !f.user) return true;
  var a = row.getAttribute('data-assignee'), r = row.getAttribute('data-reporter');
  if (a === null && r === null) return true;  // dòng không theo người -> luôn hiện
  return a === f.user || r === f.user;         // luôn lọc cả assignee lẫn reporter
}

function setupPaginate(box){
  if (box._pg) { if (box._pgRefilter) box._pgRefilter(); return; }   // re-render khi đổi filter
  var size = parseInt(box.getAttribute('data-paginate'), 10) || 5;
  var allRows = Array.prototype.slice.call(box.querySelectorAll('tbody > tr'));
  if (!allRows.length) { box._pg = true; return; }
  if (!allRows[0].offsetHeight) return;      // hidden (e.g. inactive tab) -> defer until shown
  box._pg = true;
  var page = 0;
  var tbody = allRows[0].parentNode;
  var cols = allRows[0].cells.length;
  var rowH = allRows[0].offsetHeight;
  var fillers = [];
  var nav = document.createElement('div'); nav.className = 'pager';
  var prev = document.createElement('button'); prev.className = 'pager-btn'; prev.textContent = '‹ Prev';
  var info = document.createElement('span'); info.className = 'pager-info';
  var next = document.createElement('button'); next.className = 'pager-btn'; next.textContent = 'Next ›';
  nav.appendChild(prev); nav.appendChild(info); nav.appendChild(next);
  box.appendChild(nav);
  function render(){
    var rows = allRows.filter(rowMatch);     // chỉ phân trang trên tập đã lọc
    var pages = Math.max(1, Math.ceil(rows.length / size));
    if (page >= pages) page = pages - 1;
    if (page < 0) page = 0;
    allRows.forEach(function(r){ r.style.display = 'none'; });   // ẩn hết, rồi mở dòng trang hiện tại
    var shown = 0;
    for (var i = page*size; i < (page+1)*size && i < rows.length; i++){ rows[i].style.display = ''; shown++; }
    while (fillers.length) { var f = fillers.pop(); if (f.parentNode) f.parentNode.removeChild(f); }
    for (var k = shown; k < size; k++){
      var tr = document.createElement('tr'); tr.className = 'pager-filler';
      var td = document.createElement('td'); td.colSpan = cols; td.style.height = rowH + 'px'; td.innerHTML = '&nbsp;';
      tr.appendChild(td); tbody.appendChild(tr); fillers.push(tr);
    }
    info.textContent = rows.length
      ? (page*size + 1) + '–' + Math.min((page+1)*size, rows.length) + ' / ' + rows.length
      : '0 / 0';
    prev.disabled = (page === 0); next.disabled = (page >= pages - 1);
  }
  box._pgRefilter = function(){ page = 0; render(); };
  prev.addEventListener('click', function(){ if (page > 0) { page--; render(); } });
  next.addEventListener('click', function(){ page++; render(); });   // render() tự kẹp về trang cuối hợp lệ
  render();
}
document.querySelectorAll('[data-paginate]').forEach(setupPaginate);

// Paging cho Activity: 5 issue (act-group)/trang. min-height = trang cao nhất
// để pager Prev/Next không nhảy khi đổi trang. Tự cập nhật khi dismiss bớt group.
function setupActListPaging(list){
  if (!list || list._pgInit) return;
  list._pgInit = true;
  var size = 5, page = 0;
  var nav = document.createElement('div'); nav.className = 'pager';
  var prev = document.createElement('button'); prev.className = 'pager-btn'; prev.textContent = '‹ Prev';
  var info = document.createElement('span'); info.className = 'pager-info';
  var next = document.createElement('button'); next.className = 'pager-btn'; next.textContent = 'Next ›';
  nav.appendChild(prev); nav.appendChild(info); nav.appendChild(next);
  list.parentNode.insertBefore(nav, list.nextSibling);
  function groupsArr(){ return Array.prototype.slice.call(list.querySelectorAll('.act-group')); }
  function showPage(g){
    g.forEach(function(el, i){ el.style.display = (i >= page*size && i < (page+1)*size) ? '' : 'none'; });
  }
  function measure(){              // đo chiều cao trang cao nhất -> khoá min-height
    var g = groupsArr(), pages = Math.max(1, Math.ceil(g.length / size)), saved = page, max = 0;
    list.style.minHeight = '';
    for (var p = 0; p < pages; p++){ page = p; showPage(g); if (list.offsetHeight > max) max = list.offsetHeight; }
    page = Math.min(saved, pages - 1); if (page < 0) page = 0;
    list.style.minHeight = max + 'px';
  }
  function render(){
    var g = groupsArr(), pages = Math.max(1, Math.ceil(g.length / size));
    if (page >= pages) page = pages - 1; if (page < 0) page = 0;
    showPage(g);
    nav.style.display = g.length > size ? '' : 'none';
    info.textContent = g.length
      ? (page*size + 1) + '–' + Math.min((page+1)*size, g.length) + ' / ' + g.length + ' task'
      : '0';
    prev.disabled = (page === 0); next.disabled = (page >= pages - 1);
  }
  list._pgRender = function(){ measure(); render(); };   // dismiss -> đo lại + vẽ lại
  prev.addEventListener('click', function(){ if (page > 0) { page--; render(); } });
  next.addEventListener('click', function(){ page++; render(); });
  measure(); render();
}
setupActListPaging(document.querySelector('.act-list'));

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
function bindDonut(wrap){
  var pctEl = wrap.querySelector('.donut-pct');
  var lblEl = wrap.querySelector('.donut-lbl');
  if (!pctEl || !lblEl) return;
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
}
document.querySelectorAll('.donut-wrap').forEach(bindDonut);

// Vẽ lại donut "issue per status" theo filter người (client-side, không thêm Jira call).
// Donut "per assignee" giữ nguyên (số tổng). Data active nhúng ở #qaChartData.
function _escH(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
try { window.__chart = JSON.parse(document.getElementById('qaChartData').textContent); }
catch (e) { window.__chart = null; }

function _buildDonut(items, palette, hrefFn){
  items = items.filter(function(x){ return x[1] > 0; }).sort(function(a,b){ return b[1] - a[1]; });
  var total = items.reduce(function(s,x){ return s + x[1]; }, 0);
  if (!total) return { svg: '', total: 0, legend: '' };
  var r = 80, circ = 2 * Math.PI * r, cum = 0, segs = '', legend = '';
  items.forEach(function(it, i){
    var frac = it[1] / total, pct = Math.round(frac * 100), color = palette[i % palette.length];
    var dash = frac * circ, offset = -cum * circ;
    var seg = '<circle cx="100" cy="100" r="80" fill="none" stroke="' + color + '" stroke-width="40" '
      + 'stroke-dasharray="' + dash.toFixed(2) + ' ' + (circ - dash).toFixed(2) + '" '
      + 'stroke-dashoffset="' + offset.toFixed(2) + '" transform="rotate(-90 100 100)" '
      + 'data-pct="' + pct + '" data-label="' + _escH(it[0]) + '"><title>' + _escH(it[0]) + ': ' + it[1] + ' (' + pct + '%)</title></circle>';
    var href = hrefFn ? hrefFn(it[0]) : '';
    if (href) seg = '<a href="' + href + '" target="_blank">' + seg + '</a>';
    segs += seg;
    var lbl = '<span class="legend-swatch" style="background:' + color + '"></span>' + _escH(it[0]);
    if (href) lbl = '<a class="legend-lbl" href="' + href + '" target="_blank" title="Mở trong Jira">' + lbl + '</a>';
    legend += '<tr><td>' + lbl + '</td><td class="legend-val">' + it[1] + '</td></tr>';
    cum += frac;
  });
  return { svg: segs, total: total, legend: legend };
}

function updateStatusDonut(){
  var card = document.querySelector('[data-chart="status"]');
  var cfg = window.__chart;
  if (!card || !cfg || !cfg.active) return;
  var user = window.qaFilter && window.qaFilter.user;
  var counts = {};
  cfg.active.forEach(function(it){
    if (user && it.a !== user) return;     // donut status: CHỈ theo assignee (việc đang nằm trên tay)
    var s = it.s || '—';
    counts[s] = (counts[s] || 0) + 1;
  });
  function href(s){
    var jql = cfg.base + ' AND status = "' + s + '"';
    if (user) jql += ' AND assignee = ' + user;
    return cfg.jiraUrl + '/issues/?jql=' + encodeURIComponent(jql);
  }
  var d = _buildDonut(Object.keys(counts).map(function(s){ return [s, counts[s]]; }), cfg.palette, href);
  var svg = card.querySelector('.donut');
  var center = card.querySelector('.donut-pct');
  var tbody = card.querySelector('.chart-legend table tbody');
  if (svg) svg.innerHTML = d.svg;
  if (center) center.textContent = d.total;
  if (tbody) tbody.innerHTML = d.legend;
  var wrap = card.querySelector('.donut-wrap');
  if (wrap) bindDonut(wrap);
}

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

// Activity dismiss: lưu vào Jira user property (đồng bộ chéo máy)
function postDismiss(ids){
  if (!ids.length) return;
  fetch('/dismiss', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids: ids })
  }).catch(function(){});
}
// Bỏ qua 1 mục
function dismissActivity(btn){
  var row = btn.closest('.act-row');
  if (!row) return;
  var id = row.getAttribute('data-actid');
  postDismiss(id ? [id] : []);
  var grp = row.closest('.act-group');
  row.remove();
  if (grp && !grp.querySelector('.act-row')) grp.remove();   // group rỗng -> xoá
  var box = document.getElementById('actStream');
  var list = box && box.querySelector('.act-list');
  if (list && list._pgRender) list._pgRender();              // cập nhật lại paging
  var left = box ? box.querySelectorAll('.act-row').length : 0;
  var c = box && box.querySelector('.act-unread'); if (c) c.textContent = left;
  if (!left && list) {
    list.innerHTML = '<div class="empty">Đã đọc hết. F5 để xem hoạt động mới từ Jira.</div>';
  }
}
// Đã đọc hết: gom mọi id đang hiện -> dismiss
(function(){
  var btn = document.getElementById('actClear');
  if (!btn) return;
  btn.addEventListener('click', function(){
    var box = document.getElementById('actStream');
    var ids = box ? Array.prototype.map.call(box.querySelectorAll('.act-row[data-actid]'),
              function(r){ return r.getAttribute('data-actid'); }).filter(Boolean) : [];
    postDismiss(ids);
    if (box) box.innerHTML = '<h2>🔔 Hoạt động <span class="count">0</span></h2>' +
      '<div class="empty">Đã đọc hết. F5 để xem hoạt động mới từ Jira.</div>';
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

// Thu gọn / mở tất cả node Story trong cây tiến độ test
function toggleStories(btn){
  var folds = document.querySelectorAll('.lines-sec .lnode-fold');
  if (!folds.length) return;
  var anyOpen = Array.prototype.some.call(folds, function(d){ return d.open; });
  folds.forEach(function(d){ d.open = !anyOpen; });
  btn.textContent = anyOpen ? '⊞ Mở tất cả Story' : '⊟ Thu gọn Story';
}

// Tài liệu training (/docs): cây folder + link Drive, auto-save lên server.
(function(){
  var tree = document.getElementById('docTree');
  if (!tree) return;
  var status = document.getElementById('docStatus');
  var addRoot = document.getElementById('docAddRoot');
  var collapseBtn = document.getElementById('docCollapseAll');

  function tpl(id){ return document.importNode(document.getElementById(id).content, true).firstElementChild; }
  function dropEmpty(){ var e = tree.querySelector('.doc-empty'); if (e) e.remove(); }

  function collect(ul){
    var out = [];
    Array.prototype.forEach.call(ul.children, function(li){
      if (li.classList.contains('doc-folder')){
        var name = li.querySelector(':scope > details > summary .doc-fname').textContent.trim();
        var childUl = li.querySelector(':scope > details > .doc-children');
        out.push({ type: 'folder', name: name, children: childUl ? collect(childUl) : [] });
      } else if (li.classList.contains('doc-link')){
        out.push({ type: 'link',
                   title: li.querySelector('.doc-title').textContent.trim(),
                   url: li.getAttribute('data-url') || '' });
      }
    });
    return out;
  }

  var timer = null;
  function save(){
    status.textContent = 'Đang lưu…'; status.style.color = '#6b778c';
    fetch('/save-docs', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(collect(tree)) })
      .then(function(r){ return r.json(); })
      .then(function(j){ status.textContent = j.ok ? 'Đã lưu ✓' : 'Lỗi lưu'; status.style.color = j.ok ? '#36b37e' : '#de350b'; })
      .catch(function(){ status.textContent = 'Lỗi lưu'; status.style.color = '#de350b'; });
  }
  function scheduleSave(){ if (timer) clearTimeout(timer); timer = setTimeout(save, 600); }

  function childrenUlOf(btn){ return btn.closest('details').querySelector(':scope > .doc-children'); }

  addRoot.addEventListener('click', function(){
    dropEmpty();
    var node = tpl('docFolderTpl');
    tree.appendChild(node);
    node.querySelector('.doc-fname').focus();
    scheduleSave();
  });
  collapseBtn.addEventListener('click', function(){
    var folds = tree.querySelectorAll('.doc-fold');
    var anyOpen = Array.prototype.some.call(folds, function(d){ return d.open; });
    folds.forEach(function(d){ d.open = !anyOpen; });
    collapseBtn.textContent = anyOpen ? '⊞ Mở tất cả' : '⊟ Thu gọn tất cả';
  });

  // ----- Popup sửa tài liệu (tên / link / xoá) -----
  var overlay = document.getElementById('docmOverlay');
  var mTitle = document.getElementById('docmTitle');
  var mUrl = document.getElementById('docmUrl');
  var editingLi = null, editingNew = false;

  function applyLink(li, title, url){
    li.setAttribute('data-url', url);
    var a = li.querySelector('.doc-title');
    a.textContent = title; a.setAttribute('href', url);
    var u = li.querySelector('.doc-url');
    u.textContent = url; u.title = url;
  }
  function openModal(li, isNew){
    editingLi = li; editingNew = !!isNew;
    mTitle.value = li.querySelector('.doc-title').textContent.trim();
    mUrl.value = li.getAttribute('data-url') || '';
    overlay.classList.add('open');
    mTitle.focus(); mTitle.select();
  }
  function closeModal(saved){
    if (!saved && editingNew && editingLi && !(editingLi.getAttribute('data-url') || '').trim()){
      editingLi.remove();          // hủy khi vừa tạo mới mà chưa có link -> bỏ node rỗng
    }
    overlay.classList.remove('open'); editingLi = null; editingNew = false;
  }
  document.getElementById('docmSave').addEventListener('click', function(){
    if (!editingLi) return;
    applyLink(editingLi, mTitle.value.trim() || 'Tài liệu', mUrl.value.trim());
    editingNew = false; scheduleSave(); closeModal(true);
  });
  document.getElementById('docmDel').addEventListener('click', function(){
    if (!editingLi) return;
    if (confirm('Xoá tài liệu này?')){ editingLi.remove(); editingNew = false; scheduleSave(); closeModal(true); }
  });
  document.getElementById('docmCancel').addEventListener('click', function(){ closeModal(false); });
  document.getElementById('docmClose').addEventListener('click', function(){ closeModal(false); });
  overlay.addEventListener('click', function(e){ if (e.target === overlay) closeModal(false); });
  document.addEventListener('keydown', function(e){
    if (!overlay.classList.contains('open')) return;
    if (e.key === 'Escape') closeModal(false);
    else if (e.key === 'Enter' && document.activeElement !== mTitle) { /* allow */ }
  });
  mUrl.addEventListener('keydown', function(e){ if (e.key === 'Enter') document.getElementById('docmSave').click(); });

  tree.addEventListener('click', function(e){
    var t = e.target;
    if (t.classList.contains('doc-title')){          // bấm tên = mở tab mới
      var url = t.closest('.doc-link').getAttribute('data-url') || '';
      if (!/^https?:\/\//i.test(url)){
        e.preventDefault();
        alert('Tài liệu chưa có link hợp lệ. Bấm ✎ để dán URL (bắt đầu http/https).');
      }   // hợp lệ -> để <a target=_blank> mở native (ctrl/giữa-chuột vẫn chạy)
    } else if (t.classList.contains('doc-edit')){     // bấm ✎ = mở popup
      openModal(t.closest('.doc-link'), false);
    } else if (t.classList.contains('doc-add-folder')){
      var ul = childrenUlOf(t); var node = tpl('docFolderTpl');
      ul.appendChild(node); t.closest('details').open = true;
      node.querySelector('.doc-fname').focus(); scheduleSave();
    } else if (t.classList.contains('doc-add-link')){
      var ul2 = childrenUlOf(t); var ln = tpl('docLinkTpl');
      applyLink(ln, 'Tài liệu mới', '');
      ul2.appendChild(ln); t.closest('details').open = true;
      openModal(ln, true);                            // mở popup ngay để nhập tên + link
    } else if (t.classList.contains('doc-del')){      // chỉ còn folder mới có nút này
      var node2 = t.closest('.doc-node');
      var hasKids = node2.querySelector('.doc-children') && node2.querySelector('.doc-children').children.length;
      if (!hasKids || confirm('Xoá thư mục này và toàn bộ bên trong?')){ node2.remove(); scheduleSave(); }
    }
  });

  tree.addEventListener('input', function(e){       // chỉ tên folder còn sửa inline
    if (e.target.classList.contains('doc-fname')) scheduleSave();
  });
})();

// Roadmap (/roadmap): giai đoạn › mục › sub-task. Bấm xổ cây; sửa qua popup ✎; auto-save.
(function(){
  var rmList = document.getElementById('rmList');
  if (!rmList) return;
  var status = document.getElementById('rmStatus');
  var RM_LABEL = { planned: 'Planned', in_progress: 'In Progress', done: 'Done', blocked: 'Blocked' };

  function tpl(id){ return document.importNode(document.getElementById(id).content, true).firstElementChild; }
  function clampN(n){ n = parseInt(n, 10); if (isNaN(n)) n = 0; return Math.max(0, Math.min(100, n)); }
  function dropEmpty(){ var e = rmList.querySelector('.rm-empty'); if (e) e.remove(); }

  function readNode(li){
    return {
      title: li.querySelector('.rm-title').textContent.trim(),
      status: li.getAttribute('data-status') || 'planned',
      progress: clampN(li.getAttribute('data-progress')),
      due: li.getAttribute('data-due') || ''
    };
  }
  function collect(){
    var out = [];
    rmList.querySelectorAll('.rm-phase').forEach(function(ph){
      var items = [];
      ph.querySelectorAll('.rm-items > .rm-item').forEach(function(li){
        var it = readNode(li);
        it.subtasks = [];
        li.querySelectorAll('.rm-subs > .rm-sub').forEach(function(s){ it.subtasks.push(readNode(s)); });
        items.push(it);
      });
      out.push({ phase: ph.querySelector('.rm-pname').textContent.trim(), items: items });
    });
    return out;
  }

  var timer = null;
  function save(){
    status.textContent = 'Đang lưu…'; status.style.color = '#6b778c';
    fetch('/save-roadmap', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(collect()) })
      .then(function(r){ return r.json(); })
      .then(function(j){ status.textContent = j.ok ? 'Đã lưu ✓' : 'Lỗi lưu'; status.style.color = j.ok ? '#36b37e' : '#de350b'; })
      .catch(function(){ status.textContent = 'Lỗi lưu'; status.style.color = '#de350b'; });
  }
  function scheduleSave(){ if (timer) clearTimeout(timer); timer = setTimeout(save, 600); }

  function headOf(li){ return li.classList.contains('rm-sub') ? li : li.querySelector('.rm-irow'); }
  function paintNode(li){            // đồng bộ phần hiển thị từ data-*
    var n = readNode(li), h = headOf(li);
    var badge = h.querySelector('.rm-status');
    badge.className = 'rm-status rm-st-' + n.status;
    badge.textContent = RM_LABEL[n.status] || n.status;
    h.querySelector('.rm-bar > i').style.width = n.progress + '%';
    h.querySelector('.rm-bar').title = n.progress + '%';
    h.querySelector('.rm-pct').textContent = n.progress + '%';
    var due = h.querySelector('.rm-due');
    due.textContent = '📅 ' + n.due; due.hidden = !n.due;
  }
  function updateSummary(ph){
    var items = ph.querySelectorAll('.rm-items > .rm-item');
    var total = items.length, done = 0;
    items.forEach(function(li){ if (li.getAttribute('data-status') === 'done') done++; });
    var pct = total ? Math.round(done / total * 100) : 0;
    ph.querySelector('.rm-sum-txt').textContent = done + '/' + total + ' xong';
    ph.querySelector('.rm-sum-bar > i').style.width = pct + '%';
  }
  function subsOf(itemLi){ return itemLi.querySelectorAll('.rm-subs > .rm-sub'); }
  function deriveStatus(subs){      // all done->done · có blocked->blocked · có in_progress/done->in_progress
    var sts = [];
    subs.forEach(function(s){ sts.push(s.getAttribute('data-status') || 'planned'); });
    if (sts.every(function(x){ return x === 'done'; })) return 'done';
    if (sts.some(function(x){ return x === 'blocked'; })) return 'blocked';
    if (sts.some(function(x){ return x === 'in_progress' || x === 'done'; })) return 'in_progress';
    return 'planned';
  }
  function recalcItem(itemLi){      // có sub-task -> % = trung bình, status = suy từ sub-task
    if (!itemLi) return;
    var subs = subsOf(itemLi);
    if (!subs.length) return;       // không sub-task -> giữ % + status sửa tay
    var sum = 0;
    subs.forEach(function(s){ sum += clampN(s.getAttribute('data-progress')); });
    itemLi.setAttribute('data-progress', Math.round(sum / subs.length));
    itemLi.setAttribute('data-status', deriveStatus(subs));
    paintNode(itemLi);
    updateSummary(itemLi.closest('.rm-phase'));   // status mục đổi -> đếm "x/y xong" lại
  }

  // ----- popup sửa node / giai đoạn -----
  var ov = document.getElementById('rmmOverlay');
  var mTitle = document.getElementById('rmmTitle'), mStatus = document.getElementById('rmmStatus');
  var mProg = document.getElementById('rmmProg'), mDue = document.getElementById('rmmDue');
  var mFields = document.getElementById('rmmFields'), mHead = document.getElementById('rmmHead');
  var mProgNote = document.getElementById('rmmProgNote');
  var mStatusNote = document.getElementById('rmmStatusNote');
  var editEl = null, editKind = '';   // kind: 'phase' | 'item' | 'sub'

  function openPhase(ph){
    editEl = ph; editKind = 'phase';
    mHead.textContent = 'Sửa giai đoạn'; mFields.style.display = 'none';
    mTitle.value = ph.querySelector('.rm-pname').textContent.trim();
    ov.classList.add('open'); mTitle.focus(); mTitle.select();
  }
  function openNode(li){
    editEl = li; editKind = li.classList.contains('rm-sub') ? 'sub' : 'item';
    mHead.textContent = editKind === 'sub' ? 'Sửa sub-task' : 'Sửa mục';
    mFields.style.display = '';
    var n = readNode(li);
    mTitle.value = n.title; mStatus.value = n.status; mProg.value = n.progress; mDue.value = n.due;
    syncLocks();
    ov.classList.add('open'); mTitle.focus(); mTitle.select();
  }
  // khóa/mở status + % tùy ngữ cảnh: mục có sub-task -> cả 2 tự tính; Done -> % auto 100
  function syncLocks(){
    var derived = editKind === 'item' && subsOf(editEl).length > 0;
    mStatus.disabled = derived; mStatusNote.hidden = !derived;
    if (derived){
      mProg.disabled = true; mProgNote.hidden = false; mProgNote.textContent = 'Tự tính theo sub-task';
    } else if (mStatus.value === 'done'){
      mProg.value = 100; mProg.disabled = true; mProgNote.hidden = false; mProgNote.textContent = 'Done = 100%';
    } else {
      mProg.disabled = false; mProgNote.hidden = true;
    }
  }
  mStatus.addEventListener('change', syncLocks);
  function closeM(){ ov.classList.remove('open'); editEl = null; editKind = ''; }

  document.getElementById('rmmSave').addEventListener('click', function(){
    if (!editEl) return;
    if (editKind === 'phase'){
      editEl.querySelector('.rm-pname').textContent = mTitle.value.trim() || 'Giai đoạn';
    } else {
      var derived = editKind === 'item' && subsOf(editEl).length > 0;
      if (!derived){                       // node sửa tay: set status + %, Done -> auto 100%
        var st = mStatus.value;
        editEl.setAttribute('data-status', st);
        editEl.setAttribute('data-progress', st === 'done' ? 100 : clampN(mProg.value));
      }
      editEl.setAttribute('data-due', mDue.value || '');
      editEl.querySelector('.rm-title').textContent = mTitle.value.trim() || '(chưa đặt tên)';
      paintNode(editEl);
      if (editKind === 'item') recalcItem(editEl);                  // có sub-task -> suy % + status
      else recalcItem(editEl.closest('.rm-item'));                  // sửa sub -> cập nhật mục cha
      updateSummary(editEl.closest('.rm-phase'));
    }
    scheduleSave(); closeM();
  });
  document.getElementById('rmmDel').addEventListener('click', function(){
    if (!editEl) return;
    if (editKind === 'phase'){
      if (editEl.querySelectorAll('.rm-item').length && !confirm('Xoá giai đoạn này và toàn bộ mục bên trong?')) return;
      editEl.remove();
    } else {
      var ph = editEl.closest('.rm-phase');
      if (editKind === 'item' && editEl.querySelectorAll('.rm-sub').length && !confirm('Xoá mục này và các sub-task?')) return;
      var parentItem = editKind === 'sub' ? editEl.closest('.rm-item') : null;
      editEl.remove();
      if (parentItem) recalcItem(parentItem);   // xoá sub -> cập nhật % mục cha
      updateSummary(ph);
    }
    scheduleSave(); closeM();
  });
  document.getElementById('rmmCancel').addEventListener('click', closeM);
  document.getElementById('rmmClose').addEventListener('click', closeM);
  ov.addEventListener('click', function(e){ if (e.target === ov) closeM(); });
  document.addEventListener('keydown', function(e){ if (ov.classList.contains('open') && e.key === 'Escape') closeM(); });

  // ----- toolbar -----
  document.getElementById('rmAddPhase').addEventListener('click', function(){
    dropEmpty();
    var ph = tpl('rmPhaseTpl');
    rmList.appendChild(ph); updateSummary(ph);
    openPhase(ph);                       // mở popup đặt tên ngay
  });
  document.getElementById('rmCollapse').addEventListener('click', function(){
    var folds = rmList.querySelectorAll('.rm-fold');
    var anyOpen = Array.prototype.some.call(folds, function(d){ return d.open; });
    folds.forEach(function(d){ d.open = !anyOpen; });
    this.textContent = anyOpen ? '⊞ Mở tất cả' : '⊟ Thu gọn tất cả';
  });

  rmList.addEventListener('click', function(e){
    var t = e.target;
    if (t.classList.contains('rm-edit-phase')){ e.preventDefault(); openPhase(t.closest('.rm-phase')); }
    else if (t.classList.contains('rm-edit')){ e.preventDefault(); openNode(t.closest('.rm-node')); }
    else if (t.classList.contains('rm-add-item')){
      e.preventDefault();
      var ph = t.closest('.rm-phase');
      var li = tpl('rmItemTpl');
      ph.querySelector('.rm-items').appendChild(li);
      t.closest('details').open = true; updateSummary(ph);
      openNode(li);
    } else if (t.classList.contains('rm-add-sub')){
      e.preventDefault();
      var item = t.closest('.rm-item');
      var sub = tpl('rmSubTpl');
      item.querySelector('.rm-subs').appendChild(sub);
      var d = item.querySelector('.rm-ifold'); if (d) d.open = true;
      recalcItem(item);            // có sub-task -> % mục chuyển sang tự tính
      openNode(sub);
    }
  });
})();

// Filter theo người (assignee/reporter): lái lại pagination + thu workload về 1 người.
// Nhớ lựa chọn qua localStorage để sống sót auto-reload 15p. Charts/activity giữ nguyên (số tổng).
(function(){
  var bar = document.getElementById('filterBar');
  if (!bar) return;
  var sel = document.getElementById('personFilter');
  var clearBtn = document.getElementById('filterClear');
  var countEl = document.getElementById('filterCount');
  window.qaFilter = { user: '' };

  try {                                        // khôi phục lựa chọn cũ
    var saved = JSON.parse(localStorage.getItem('qa-filter') || 'null');
    if (saved && saved.user) {
      window.qaFilter = { user: saved.user };
      sel.value = saved.user;
    }
  } catch (e) {}

  function persist(){ try { localStorage.setItem('qa-filter', JSON.stringify(window.qaFilter)); } catch (e) {} }

  function updateCounts(){
    // Header/tab badge phải khớp số đã lọc, không phải tổng server-side.
    // Loại pager-filler (không có data-attr -> rowMatch trả true -> overcount).
    document.querySelectorAll('[data-paginate]').forEach(function(box){
      var rows = Array.prototype.slice.call(box.querySelectorAll('tbody > tr:not(.pager-filler)'));
      var n = rows.filter(rowMatch).length;
      var panel = box.getAttribute('data-panel');
      if (panel) {                                  // attention tab -> badge trên nút tab
        var block = box.closest('.tabbed');
        var tb = block && block.querySelector('.tab[data-tab="' + panel + '"] .tab-count');
        if (tb) tb.textContent = n;
      } else {                                      // Done / New24 -> .count trong h2
        var badge = box.querySelector('h2 .count');
        if (badge) badge.textContent = n;
      }
    });
    var wl = document.querySelector('.wl');         // Workload "N active"
    if (wl) {
      var wlBadge = wl.closest('.section').querySelector('h2 .count');
      if (wlBadge) {
        var tot = 0;
        document.querySelectorAll('.wl-item').forEach(function(d){
          if (window.qaFilter.user && d.getAttribute('data-user') !== window.qaFilter.user) return;
          tot += d.querySelectorAll('.wl-task').length;
        });
        wlBadge.textContent = tot + ' active';
      }
    }
  }

  function apply(){
    document.querySelectorAll('[data-paginate]').forEach(function(box){
      if (box._pgRefilter) box._pgRefilter(); else setupPaginate(box);
    });
    document.querySelectorAll('.wl-item').forEach(function(d){   // workload: chỉ hiện người đã chọn
      var u = d.getAttribute('data-user');
      if (!window.qaFilter.user) { d.style.display = ''; }
      else if (u === window.qaFilter.user) { d.style.display = ''; d.open = true; }
      else { d.style.display = 'none'; }
    });
    updateCounts();
    if (typeof updateStatusDonut === 'function') updateStatusDonut();  // donut status theo filter
    clearBtn.hidden = !window.qaFilter.user;
    countEl.textContent = window.qaFilter.user && sel.options[sel.selectedIndex]
      ? 'Đang lọc: ' + sel.options[sel.selectedIndex].text : '';
    persist();
    // KHÔNG gọi layout() ở đây: layout resize donut theo chiều cao cột -> filter làm block
    // nhảy size. Giữ size donut cố định (đã set lúc load), chỉ đổi nội dung donut status.
  }

  sel.addEventListener('change', function(){ window.qaFilter.user = sel.value; apply(); });
  clearBtn.addEventListener('click', function(){ window.qaFilter.user = ''; sel.value = ''; apply(); });

  apply();                                     // áp filter đã khôi phục (nếu có) ngay khi load
})();

// Read-only (không phải owner qua Cloudflare Access): khoá contenteditable trong roadmap/tài liệu.
// Nút edit đã ẩn bằng CSS .ro; server vẫn chặn 403 — đây chỉ là lớp UX.
document.querySelectorAll('.ro [contenteditable]').forEach(function(el){
  el.setAttribute('contenteditable', 'false');
});
