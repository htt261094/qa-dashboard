"""HTML rendering. UI v2 (Stitch) assets live in styles_v2.css / app_v2.js; the legacy
styles.css is still inlined by render_error_page. All assets load per-render (inlined).

All render_* functions return HTML fragments; render_page assembles the full document.
"""
import json
import math
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta

from config import JIRA_URL, USERS, STUCK_DAYS, display_name, username_from_email, normalize_tester
from issues import (parse_date, i_assignee, i_reporter, i_assignee_name, i_reporter_name,
                    i_status, i_summary, i_duedate,
                    i_created, i_resolved, i_updated, i_type, days_overdue, days_since_update,
                    is_stuck, esc, status_class, issue_link)
from docs import load_docs
from roadmap import (RM_STATUSES, RM_PEOPLE, load_roadmap, due_alerts,
                     task_done, task_started, plan_done, derive_plan_status)
from custom_status import CUSTOM_STATUSES, label_of, values_of
from task_link import tasks_of
from bug_log_store import POLL_SECONDS as BUG_LOG_POLL_SECONDS

# Shared low-level helpers extracted to render.base; re-exported so existing callers
# (`from render import load_css, _json_script, ...`) keep working. See issue #103 / #86.
from render.base import load_css, load_css_v2, load_js_v2, _json_script
# Shell chrome (sidebar/topbar/modals/_document_v2) extracted to render.shell;
# re-exported so existing callers keep working. See issue #104 / #86.
from render.shell import (_FONTS_V2, _AV_CLS, _avatar, render_sidebar_v2,
                          render_topbar_v2, _settings_modal_v2, _subtask_modal_v2,
                          _document_v2)


def render_403():
    """Trang 403 tối giản — KHÔNG lộ domain/điều kiện được phép (giấu thông tin)."""
    return ('<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><title>403</title>'
            '<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#091e42;'
            'color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}'
            '.b{text-align:center}.c{font-size:64px;font-weight:800;letter-spacing:2px}'
            '.m{color:#a5adba;margin-top:8px}a{color:#85b8ff}</style></head>'
            '<body><div class="b"><div class="c">403</div>'
            '<div class="m">Unauthorized</div>'
            '<p><a href="/logout">Đăng nhập lại</a></p></div></body></html>')


# ===== Settings page (/settings): nhập PAT cá nhân để thao tác Jira ghi đúng tên mình =====
def _render_drive_card(has_drive, auth_enabled):
    """Card 'Kết nối Drive' (admin-only) — lấy refresh_token đọc file bug log (#52)."""
    if not auth_enabled:
        return ('<div class="set-card">'
                '<h2>🔗 Kết nối Google Drive (Bug Log)</h2>'
                '<div class="set-state set-none">⚠ Chưa bật Google OAuth (GOOGLE_CLIENT_ID/SECRET) '
                'nên không kết nối Drive được. Đây là chế độ local dev.</div></div>')
    if has_drive:
        state = ('<div class="set-state set-ok">✓ Đã kết nối Drive. Background sync đọc file bug log '
                 'bằng quyền admin (chỉ đọc).</div>')
        btns = ('<a href="/drive/connect" class="set-btn">Kết nối lại</a>'
                '<button type="button" id="driveDisconnect" class="set-link-del">Ngắt kết nối Drive</button>')
    else:
        state = ('<div class="set-state set-none">⚠ Chưa kết nối Drive. Bug log sync sẽ báo '
                 '"chưa kết nối Drive".</div>')
        btns = '<a href="/drive/connect" class="set-btn">Kết nối Drive</a>'
    # Lưu ý: account chooser luôn hiện (prompt=select_account, auth.py) — chọn ĐÚNG tài
    # khoản @baokim.vn, KHÔNG dùng Gmail cá nhân (sẽ bị domain gate từ chối).
    return (
        '<div class="set-card">'
        '<h2>🔗 Kết nối Google Drive (Bug Log)</h2>'
        f'{state}'
        '<p class="set-note">Cấp quyền <b>chỉ đọc</b> (<code>drive.readonly</code>) bằng tài khoản admin '
        'để background sync tải file <code>.xlsx</code> bug log. Token được mã hoá (AES) trước khi lưu, '
        'không bao giờ lưu dạng thô và không ghi/sửa được file trên Drive.</p>'
        '<p class="set-note">⚠ Khi Google hỏi, hãy <b>chọn tài khoản <code>@baokim.vn</code></b> '
        '(không phải Gmail cá nhân) — tài khoản ngoài domain sẽ bị từ chối.</p>'
        f'<div class="set-form">{btns}</div>'
        '</div>'
    )


def render_settings_page(has_pat, user=None, has_drive=False, auth_enabled=False, activities=None):
    status_line = ('<div class="set-state set-ok">✓ Bạn đã lưu PAT. Thao tác đổi status/comment sẽ ghi đúng tên bạn trên Jira.</div>'
                   if has_pat else
                   '<div class="set-state set-none">⚠ Bạn chưa lưu PAT. Hiện thao tác (nếu có) sẽ mang tên tài khoản chung.</div>')
    jira_base = esc(JIRA_URL)
    inner = (
        '<div class="page-head"><div>'
        '<h2 class="page-title">⚙ Setting — Personal Access Token (PAT)</h2>'
        '<div class="page-sub">PAT giúp dashboard thao tác Jira <strong>nhân danh chính bạn</strong>. '
        'Mã được mã hoá (AES) trước khi lưu, không bao giờ lưu dạng thô.</div>'
        '</div></div>'
        f'<div class="set-wrap">{status_line}'
        '<div class="set-card">'
        '<h2>1. Tạo PAT trên Jira</h2>'
        '<ol class="set-steps">'
        f'<li>Mở <a href="{jira_base}/secure/ViewProfile.jspa" target="_blank" rel="noopener">Hồ sơ Jira của bạn</a> → '
        '<b>Personal Access Tokens</b>.</li>'
        '<li>Bấm <b>Create token</b>, đặt tên (vd "QA Dashboard"), chọn thời hạn.</li>'
        '<li>Copy chuỗi token (chỉ hiện 1 lần).</li>'
        '</ol>'
        '<h2>2. Dán vào đây</h2>'
        '<div class="set-form">'
        '<input type="password" id="patInput" class="set-input" placeholder="Dán PAT của bạn..." autocomplete="off" spellcheck="false">'
        '<button type="button" id="patSave" class="set-btn">Lưu PAT</button>'
        '<button type="button" id="patShow" class="set-btn ghost" title="Hiện/ẩn">👁</button>'
        '</div>'
        + ('<button type="button" id="patDelete" class="set-link-del">Xoá PAT đã lưu</button>' if has_pat else '')
        + '<p class="set-note">⚠ Token được verify thuộc đúng tài khoản của bạn (gọi <code>/myself</code>) trước khi lưu. '
        'PAT của người khác sẽ bị từ chối.</p>'
        '</div>'
        + '</div>'
    )
    return _document_v2(inner, 'settings', user, activities or [], title='Cài đặt — QA Dashboard')


# ===== Full page =====
def render_page(data, new_keys, first_run, activities, activity_days=7, roadmap_data=None,
                user=None, custom_overlay=None, bug_log_data=None):
    is_admin = user[1] if (user and len(user) > 1) else True

    # QA thường (non-admin): data đã auto-scope về chính họ -> UI v2 (shell sidebar Stitch).
    if not is_admin:
        return render_qa_v2(data, new_keys, activities, custom_overlay, user)

    # Admin -> new v2 dashboard (pills + member filter + 5-col table + KPI cards)
    return render_admin_v2(data, new_keys, activities, custom_overlay, user,
                           bug_log_data=bug_log_data)


def _bug_metrics_payload(bug_log_data):
    """bug_log_store.load_bug_log() -> payload cho controller `#bugMetrics` trên dashboard.

    {files:[{fid,label,project,months:[sheet,...]}], metrics:{fid:{month:[snapshot,...]}},
     syncedAt}. snapshot = {at, total, statuses:{raw_status:count}} (xem bug_log_store).
    Tháng (sheet) lấy TỪ lịch sử metric -> chạy được cả khi Jira property ở bản nhẹ
    (đã drop `bugs`). Chỉ liệt kê file CÓ lịch sử metric."""
    bug_log_data = bug_log_data or {}
    files_raw = bug_log_data.get('files', {}) or {}
    metrics = bug_log_data.get('metrics', {}) or {}
    files = []
    for fid, fm in metrics.items():
        months = sorted((m for m in (fm or {}) if m), reverse=True)
        if not months:
            continue
        f = files_raw.get(fid, {}) or {}
        files.append({
            'fid': fid,
            'label': f.get('name') or f.get('project') or fid,
            'project': f.get('project', ''),
            'months': months,
        })
    files.sort(key=lambda x: (x['label'] or '').lower())
    synced = (bug_log_data.get('synced_at', '') or '').replace('T', ' ')[:16]
    return {'files': files, 'metrics': metrics, 'syncedAt': synced or 'chưa đồng bộ'}


# ===== Tài liệu training (tab /docs): cây folder + link Google Drive =====
def render_docs_page(tree, editable=True, user=None, activities=None):
    if activities is None:
        activities = []
    
    action_buttons_html = ""
    if editable:
        action_buttons_html = """
          <button class="btn-sec" onclick="openModal('folderModal')">
            <span class="material-symbols-rounded">create_new_folder</span>
            Tạo thư mục
          </button>
          <button class="btn-pri" onclick="openModal('uploadModal')">
            <span class="material-symbols-rounded">upload</span>
            Tải lên tài liệu
          </button>
          <button class="btn-sec" onclick="openModal('linkModal')">
            <span class="material-symbols-rounded">link</span>
            Thêm link Drive
          </button>
        """

    ro_banner = ""
    if not editable:
        ro_banner = '<div style="margin: 0 32px 16px; padding: 12px 16px; background: var(--surface-variant); color: var(--on-surface-variant); border-radius: 8px; font-size: 13px; display: flex; align-items: center; gap: 8px;"><span class="material-symbols-rounded" style="color: var(--primary);">info</span>👁 Chế độ chỉ xem — chỉ quản lý mới chỉnh sửa được.</div>'

    content_inner = f"""
    <div class="content">
      <div class="content-header">
        <div>
          <h2 class="page-title">Tài liệu QA</h2>
        </div>
        <div class="action-buttons">
          {action_buttons_html}
        </div>
      </div>
      
      {ro_banner}

      <div class="breadcrumbs" id="breadcrumbs" style="display:none">
        <a onclick="navigateBackToRoot()">Tài liệu QA</a>
        <span class="separator">/</span>
        <span class="current" id="currentBreadcrumb">Thư mục</span>
      </div>

      <!-- Folders Section -->
      <div id="foldersSection">
        <div class="section-title-row">
          <h3>Thư mục</h3>
        </div>
        <div class="folder-grid" id="folderGrid"></div>
      </div>

      <!-- Documents List Section -->
      <div>
        <div class="section-title-row">
          <h3 id="tableTitle">Tài liệu gần đây</h3>
          <a class="view-all-link" id="viewAllDocs" onclick="navigateBackToRoot()">Xem tất cả <span class="material-symbols-rounded">chevron_right</span></a>
        </div>
        
        <div class="table-card">
          <table class="doc-table">
            <thead>
              <tr>
                <th>Tên tài liệu</th>
                <th style="width: 180px">Ngày sửa</th>
                {"<th class='action-col'>Hành động</th>" if editable else ""}
              </tr>
            </thead>
            <tbody id="docTableBody">
              <!-- JS renders rows here -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ===== Floating Context Menu ===== -->
    <div class="context-menu" id="contextMenu">
      {"" if not editable else '<button onclick="editDoc()"><span class="material-symbols-rounded mi-sm">edit</span>Sửa đổi</button>'}
      <button onclick="openLink()"><span class="material-symbols-rounded mi-sm">open_in_new</span>Mở link</button>
      <button onclick="copyDocLink()"><span class="material-symbols-rounded mi-sm">content_copy</span>Sao chép link</button>
      {"<div class='divider'></div>" if editable else ""}
      {"" if not editable else '<button class="danger" onclick="deleteDoc()"><span class="material-symbols-rounded mi-sm">delete</span>Xoá tài liệu</button>'}
    </div>

    <!-- ===== Processing Status Toast ===== -->
    <div class="bottom-toast" id="bottomToast">
      <span class="material-symbols-rounded icon-success">check_circle</span>
      <span class="toast-text" id="bottomToastText">Đang xử lý yêu cầu...</span>
    </div>
    """

    if editable:
        content_inner += """
    <!-- ===== MODAL: TẠO THƯ MỤC ===== -->
    <div class="overlay" id="folderModal" onclick="if(event.target===this)closeModal('folderModal')">
      <div class="modal">
        <div class="modal-head">
          <span class="material-symbols-rounded">create_new_folder</span>
          <h3>Tạo thư mục mới</h3>
          <button class="x material-symbols-rounded" onclick="closeModal('folderModal')">close</button>
        </div>
        <div class="modal-body">
          <div class="mfield">
            <label for="folderNameInp">Tên thư mục</label>
            <input type="text" id="folderNameInp" placeholder="Nhập tên thư mục..." autocomplete="off">
          </div>
          <div class="mfield" id="folderParentField">
            <label for="folderParentSel">Thư mục cha</label>
            <select id="folderParentSel">
              <option value="root">Thư mục gốc (Root)</option>
            </select>
          </div>
          <div class="mfield">
            <label>Màu sắc</label>
            <div class="color-picker" id="folderColorPicker">
              <div class="color-opt blue selected" data-color="blue" onclick="selectColor(this)"></div>
              <div class="color-opt orange" data-color="orange" onclick="selectColor(this)"></div>
              <div class="color-opt green" data-color="green" onclick="selectColor(this)"></div>
              <div class="color-opt purple" data-color="purple" onclick="selectColor(this)"></div>
            </div>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-ghost" onclick="closeModal('folderModal')">Huỷ</button>
          <button class="btn btn-primary" onclick="createFolder()">Tạo thư mục</button>
        </div>
      </div>
    </div>

    <!-- ===== MODAL: THÊM LINK DRIVE ===== -->
    <div class="overlay" id="linkModal" onclick="if(event.target===this)closeModal('linkModal')">
      <div class="modal">
        <div class="modal-head">
          <span class="material-symbols-rounded">link</span>
          <h3>Thêm link tài liệu Google Drive</h3>
          <button class="x material-symbols-rounded" onclick="closeModal('linkModal')">close</button>
        </div>
        <div class="modal-body">
          <div class="mfield">
            <label for="linkTitleInp">Tên tài liệu</label>
            <input type="text" id="linkTitleInp" placeholder="Nhập tên tài liệu..." autocomplete="off">
          </div>
          <div class="mfield">
            <label for="linkUrlInp">Đường dẫn Google Drive</label>
            <input type="text" id="linkUrlInp" placeholder="https://docs.google.com/..." autocomplete="off">
          </div>
          <div class="mfield">
            <label for="linkFolderSel">Thư mục</label>
            <select id="linkFolderSel">
            </select>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-ghost" onclick="closeModal('linkModal')">Huỷ</button>
          <button class="btn btn-primary" onclick="addDriveLink()">Lưu tài liệu</button>
        </div>
      </div>
    </div>

    <!-- ===== MODAL: TẢI LÊN TÀI LIỆU ===== -->
    <div class="overlay" id="uploadModal" onclick="if(event.target===this)closeModal('uploadModal')">
      <div class="modal">
        <div class="modal-head">
          <span class="material-symbols-rounded">upload</span>
          <h3>Tải lên tài liệu</h3>
          <button class="x material-symbols-rounded" onclick="closeModal('uploadModal')">close</button>
        </div>
        <div class="modal-body">
          <div class="dropzone" id="dropzone" onclick="document.getElementById('fileInput').click()">
            <span class="material-symbols-rounded icon">cloud_upload</span>
            <div class="text">Kéo thả tệp tin hoặc Click để chọn tệp tải lên</div>
            <div class="hint" style="font-size: 11px; color: var(--on-surface-variant); margin-top: 4px;">Hỗ trợ .pdf, .xlsx, .docx, .png (tối đa 20MB)</div>
            <input type="file" id="fileInput" onchange="handleFileSelect(event)">
          </div>
          
          <div class="mfield" id="uploadForm" style="display:none">
            <label for="uploadFolderSel">Lưu vào thư mục</label>
            <select id="uploadFolderSel">
            </select>
          </div>

          <div class="progress-wrap" id="progressWrap" style="display:none">
            <div class="progress-bar"><i id="progressPercent" style="width: 0%"></i></div>
            <div class="progress-text">
              <span id="uploadFileName">tailieu.pdf</span>
              <span id="uploadPercentage">0%</span>
            </div>
          </div>
        </div>
        <div class="modal-foot" id="uploadModalFoot">
          <button class="btn btn-ghost" onclick="closeModal('uploadModal')">Huỷ</button>
          <button class="btn btn-primary" id="uploadBtn" onclick="performRealUpload()" disabled>Bắt đầu tải lên</button>
        </div>
      </div>
    </div>
    """

    content_inner += f"""
    <script>
      window.QA_DOCS_EDITABLE = {"true" if editable else "false"};
    </script>
    """

    content_inner += _json_script('docsData', tree)

    return _document_v2(content_inner, 'docs', user, activities, title='Tài liệu QA')


# ===== Admin Dashboard v2 (team-wide — pills + member filter + 5-col table + KPI cards) =====
def render_admin_v2(data, new_keys, activities, cmap, user, bug_log_data=None):
    """Admin dashboard v2: team-wide view with status pills, member dropdown, paginated
    5-column table, 3 KPI cards, and a task detail drawer. Data is embedded as JSON and
    rendered entirely client-side by the admin controller in app_v2.js."""
    active = data['active']
    done = data['done_week']
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_str = today.strftime('%Y-%m-%d')
    new_keys = new_keys or set()

    tasks = []
    seen = set()

    # Active tasks (TO DO, In Progress, PENDING, etc.)
    for iss in active:
        key = iss['key']
        if key in seen:
            continue
        seen.add(key)
        st = i_status(iss)
        a = i_assignee(iss)
        aname = i_assignee_name(iss)
        init, cls = _avatar(a, aname)
        overdue = days_overdue(iss) is not None
        stuck = is_stuck(iss)
        customs = values_of((cmap or {}).get(key))
        # "New" = task tạo TRONG NGÀY (created == hôm nay), giữ nguyên cả ngày, reset sang
        # ngày mới. ĐỘC LẬP status -> task sang In Progress/Done vẫn nằm trong list New
        # tới hết ngày (thay cho snapshot-diff new_keys vốn mất sau 1 lần refresh).
        is_new = (i_created(iss) or '')[:10] == today_str
        # New Tasks & TO DO: cột "Updated" hiển thị Created Date; còn lại = Updated thật.
        upd_src = i_created(iss) if (is_new or st == 'TO DO') else i_updated(iss)
        upd_date = (upd_src or '')[:10]
        tasks.append({
            'key': key, 'summary': i_summary(iss), 'jira': st,
            'customs': customs, 'canCustom': st in ('TO DO', 'In Progress'),
            'assignee': {'name': aname, 'init': init, 'cls': cls},
            'due': i_duedate(iss) or '', 'dueDisp': i_duedate(iss) or 'Chưa đặt hạn',
            'dueCls': 'overdue' if overdue else '',
            'updated': upd_date, 'updatedDisp': upd_date or '—',
            'created': (i_created(iss) or '')[:10], 'createdDisp': (i_created(iss) or '')[:10] or '—',
            'overdue': overdue, 'stuck': stuck,
            'isNew': is_new,
            'jiraUrl': f'{JIRA_URL}/browse/{key}',
        })

    # Done tasks (3 ngày)
    for iss in done:
        key = iss['key']
        if key in seen:
            continue
        seen.add(key)
        st = i_status(iss)
        a = i_assignee(iss)
        aname = i_assignee_name(iss)
        init, cls = _avatar(a, aname)
        upd_date = (i_updated(iss) or '')[:10]
        tasks.append({
            'key': key, 'summary': i_summary(iss), 'jira': st,
            'customs': [], 'canCustom': False,
            'assignee': {'name': aname, 'init': init, 'cls': cls},
            'due': i_duedate(iss) or '', 'dueDisp': i_duedate(iss) or '',
            'dueCls': '',
            'updated': upd_date, 'updatedDisp': upd_date or '—',
            'created': (i_created(iss) or '')[:10], 'createdDisp': (i_created(iss) or '')[:10] or '—',
            'overdue': False, 'stuck': False,
            'isNew': (i_created(iss) or '')[:10] == today_str,
            'jiraUrl': f'{JIRA_URL}/browse/{key}',
        })

    # Pill counts
    n_todo = sum(1 for t in tasks if t['jira'] == 'TO DO' and not t['isNew'] and not t['overdue'])
    n_prog = sum(1 for t in tasks if t['jira'] in ('In Progress', 'PENDING') and not t['stuck'] and not t['overdue'])
    n_new = sum(1 for t in tasks if t['isNew'])
    n_stuck = sum(1 for t in tasks if t['stuck'])
    n_over = sum(1 for t in tasks if t['overdue'])
    n_done = sum(1 for t in tasks if t['jira'].upper() == 'DONE')

    # Unique member names for dropdown
    members = []
    seen_m = set()
    for t in tasks:
        nm = t['assignee']['name']
        if nm not in seen_m:
            seen_m.add(nm)
            members.append(nm)
    member_opts = '<div class="member-opt active" data-member="all">All Members</div>'
    for m in sorted(members):
        member_opts += f'<div class="member-opt" data-member="{esc(m)}">{esc(m)}</div>'

    meta = {
        'isAdmin': True,
        'todo': n_todo, 'progress': n_prog, 'new': n_new,
        'stuck': n_stuck, 'overdue': n_over, 'done': n_done,
        'resolvedWeek': data.get('resolved_week', 0),
        'createdWeek': data.get('created_week', 0),
    }

    content = (
        # Page header + member filter
        '<div class="page-head"><div>'
        '<h2 class="page-title">Task Management</h2>'
        '</div>'
        '<div class="member-filter-wrap">'
        '<button class="member-filter-btn" id="memberFilterBtn">'
        '<span class="material-symbols-rounded">group</span>'
        '<span id="selectedMemberLabel">All Members</span>'
        '<span class="material-symbols-rounded">expand_more</span>'
        '</button>'
        f'<div class="member-dropdown" id="memberDropdown">{member_opts}</div>'
        '</div></div>'
        # Status pills
        '<div class="status-pills" id="statusPills">'
        f'<button class="pill-btn active" data-pill="todo">To Do <span class="pill-badge" id="count-todo">{n_todo}</span></button>'
        f'<button class="pill-btn" data-pill="progress">In Progress <span class="pill-badge" id="count-progress">{n_prog}</span></button>'
        f'<button class="pill-btn" data-pill="new">New <span class="pill-badge" id="count-new">{n_new}</span></button>'
        f'<button class="pill-btn" data-pill="stuck">Stuck <span class="pill-badge" id="count-stuck">{n_stuck}</span></button>'
        f'<button class="pill-btn" data-pill="overdue">Overdue <span class="pill-badge" id="count-overdue">{n_over}</span></button>'
        f'<button class="pill-btn" data-pill="done">Done <span class="pill-badge" id="count-done">{n_done}</span></button>'
        '</div>'
        # Table card
        '<div class="card">'
        '<div class="table-header">'
        '<div class="table-title" id="tableTitleText">'
        '<span class="material-symbols-rounded">assignment</span>'
        '<span>To Do Tasks</span></div>'
        '<div class="table-actions"></div></div>'
        '<div style="overflow-x:auto"><table id="taskTable"><thead><tr>'
        '<th style="width:140px">Task ID</th><th>Title</th>'
        '<th style="width:180px">Member</th><th style="width:170px">Status</th>'
        '<th style="width:120px">Due Date</th><th style="width:120px">Ngày tạo</th><th style="width:120px">Updated</th>'
        '</tr></thead><tbody id="rows"></tbody></table></div>'
        '<div class="pager" id="pager"></div></div>'
        # KPI cards
        '<div class="kpi-grid">'
        '<div class="kpi-card"><div class="kpi-icon">'
        '<span class="material-symbols-rounded">speed</span></div>'
        '<div class="kpi-details"><div class="kpi-title">JIRA VELOCITY</div>'
        '<div class="kpi-value" id="kpiVelocity">0</div>'
        '<div class="kpi-trend up"><span class="material-symbols-rounded">trending_up</span>'
        '<span>this week</span></div></div></div>'
        '<div class="kpi-card"><div class="kpi-icon">'
        '<span class="material-symbols-rounded">hub</span></div>'
        '<div class="kpi-details"><div class="kpi-title">TOTAL TASKS</div>'
        '<div class="kpi-value" id="kpiTotalTasks">0</div>'
        '<div class="kpi-trend up"><span class="material-symbols-rounded">trending_up</span>'
        '<span>active</span></div></div></div>'
        '<div class="kpi-card"><div class="kpi-icon">'
        '<span class="material-symbols-rounded">bug_report</span></div>'
        '<div class="kpi-details"><div class="kpi-title">OVERDUE</div>'
        '<div class="kpi-value" id="kpiBugs">0</div>'
        '<div class="kpi-trend down"><span class="material-symbols-rounded">warning</span>'
        '<span>need attention</span></div></div></div></div>'
        # ===== Metric Bug (nguồn = bug_log_store; chọn theo file + sheet; lịch sử mỗi sync)
        '<div class="card bug-metric-card" id="bugMetricCard">'
        '<div class="table-header"><div class="table-title">'
        '<span class="material-symbols-rounded">bug_report</span>'
        '<span>Metric Bug — Tổng &amp; theo Status</span></div>'
        '<div class="bm-filters">'
        '<span class="material-symbols-rounded mi-sm">description</span>'
        '<select id="bmFile" class="bm-sel"></select>'
        '<span class="material-symbols-rounded mi-sm">tab</span>'
        '<select id="bmSheet" class="bm-sel"></select></div></div>'
        '<div class="bm-body">'
        '<div class="bm-current" id="bmCurrent"></div>'
        '<div class="bm-history-wrap"><div class="bm-history-head">'
        '<span class="material-symbols-rounded mi-sm">history</span> '
        'Lịch sử thay đổi qua mỗi lần sync</div>'
        '<div class="bm-history" id="bmHistory"></div></div></div>'
        '<div class="bm-sub" id="bmSynced"></div></div>'
        # Status menu (drawer DOM nằm ở shell _document_v2 -> mọi trang dùng chung)
        '<div class="smenu" id="smenu"></div>'
        + _json_script('bugMetrics', _bug_metrics_payload(bug_log_data))
        + _json_script('qaData', {'tasks': tasks, 'meta': meta})
        + f'<script>window.QA_CUSTOM_STATUSES={json.dumps(CUSTOM_STATUSES, ensure_ascii=False)};</script>'
    )
    return _document_v2(content, 'dashboard', user, activities,
                        title='QA Workspace — Task Management')


# ===== Dashboard QA v2 (lens cá nhân — 1 bảng + tabs + KPI + drawer) =====
# Dùng chung cho QA member (`/`, nav_active='dashboard') và admin xem việc mình
# (`/my-work`, nav_active='mywork') — UI hệt nhau, chỉ khác tab sidebar được highlight.
def render_qa_v2(data, new_keys, activities, cmap, user, nav_active='dashboard'):
    active = data['active']
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    new_keys = new_keys or set()

    tasks = []
    n_over = n_stuck = n_dueweek = 0
    for iss in active:
        st = i_status(iss)
        a = i_assignee(iss)
        aname = i_assignee_name(iss)
        init, cls = _avatar(a, aname)
        d = parse_date(i_duedate(iss))
        overdue = days_overdue(iss) is not None
        stuck = is_stuck(iss)
        duecls = 'overdue' if overdue else ('today' if (d and d == today) else '')
        if overdue:
            n_over += 1
        if stuck:
            n_stuck += 1
        dueweek = bool(d and not overdue and week_start <= d < week_end)
        if dueweek:
            n_dueweek += 1
        customs = values_of((cmap or {}).get(iss['key']))   # values; JS map -> label qua QA_CUSTOM_STATUSES
        tasks.append({
            'key': iss['key'], 'summary': i_summary(iss), 'jira': st,
            'customs': customs, 'canCustom': st in ('TO DO', 'In Progress'),
            'assignee': {'name': aname, 'init': init, 'cls': cls},
            'due': i_duedate(iss) or '', 'dueDisp': i_duedate(iss) or 'Chưa đặt hạn',
            'dueCls': duecls, 'overdue': overdue, 'stuck': stuck, 'dueWeek': dueweek,
            'created': (i_created(iss) or '')[:10], 'createdDisp': (i_created(iss) or '')[:10] or '—',
            'isNew': iss['key'] in new_keys,
            'jiraUrl': f'{JIRA_URL}/browse/{iss["key"]}',
        })
    meta = {'active': len(active), 'overdue': n_over, 'stuck': n_stuck,
            'dueweek': n_dueweek, 'done': len(data['done_week']), 'stuckDays': STUCK_DAYS}

    tabs = (
        '<div class="tabs" id="tabs">'
        f'<button class="active" data-f="all">Task của tôi <span class="tcount">{meta["active"]}</span></button>'
        f'<button data-f="overdue">Quá hạn <span class="tcount">{n_over}</span></button>'
        f'<button data-f="stuck">Bị kẹt <span class="tcount">{n_stuck}</span></button>'
        '</div>'
    )
    kpis = (
        '<div class="kpis" id="kpis">'
        f'<div class="kpi sel" data-f="all"><div class="label">Active của tôi</div><div class="value">{meta["active"]}</div></div>'
        f'<div class="kpi warn" data-f="overdue"><div class="label">Quá hạn</div><div class="value">{n_over}</div></div>'
        f'<div class="kpi stuck" data-f="stuck"><div class="label">Kẹt ≥ {STUCK_DAYS} ngày</div><div class="value">{n_stuck}</div></div>'
        f'<div class="kpi" data-f="dueweek"><div class="label">Due tuần này</div><div class="value">{n_dueweek}</div></div>'
        f'<div class="kpi success" data-f="done"><div class="label">Done (3 ngày)</div><div class="value">{meta["done"]}</div></div>'
        '</div>'
    )
    table = (
        '<div class="card"><table><thead><tr>'
        '<th style="width:90px">ID</th><th>Tiêu đề</th><th style="width:160px">Trạng thái</th>'
        '<th style="width:150px">Người xử lý</th><th style="width:110px">Ngày tạo</th><th style="width:130px">Hạn chót</th>'
        '<th style="width:70px">Thao tác</th>'
        '</tr></thead><tbody id="rows"></tbody></table></div>'
        '<div class="pager" id="pager"></div>'
    )
    content = (
        '<div class="page-head"><div class="page-title">Tổng quan — Việc của tôi</div></div>'
        + tabs + kpis + table
        + '<div class="smenu" id="smenu"></div>'
        + _json_script('qaData', {'tasks': tasks, 'meta': meta})
        + f'<script>window.QA_CUSTOM_STATUSES={json.dumps(CUSTOM_STATUSES, ensure_ascii=False)};</script>'
    )
    return _document_v2(content, nav_active, user, activities, title='QA Dashboard — Việc của tôi')


# ===== Roadmap v2 (plan › task › sub-task, schema Stitch) =====
def render_roadmap_v2(data, editable=True, user=None, activities=None):
    add_btn = ('<button class="btn-pri" id="rmAddPlan"><span class="material-symbols-rounded mi-sm">add_circle</span> Thêm kế hoạch</button>'
               if editable else '')
    banner = '' if editable else '<div class="ro-banner">👁 Chế độ chỉ xem — chỉ quản lý mới chỉnh sửa được.</div>'
    ro = '' if editable else ' ro'
    seg = (
        '<div class="rm-filter"><div class="seg" id="rmSeg">'
        '<button class="active" data-f="all">Tất cả</button>'
        '<button data-f="in_progress">Đang thực hiện</button>'
        '<button data-f="planned">Sắp tới</button>'
        '<button data-f="done">Hoàn thành</button>'
        '</div></div>'
    )
    modal = (
        '<div class="overlay" id="modalOverlay">'
        '<div class="modal">'
        '<div class="modal-head"><span class="material-symbols-rounded" id="modalIcon">edit</span>'
        '<h3 id="modalTitle">Sửa</h3>'
        '<button type="button" class="x material-symbols-rounded" id="modalClose">close</button></div>'
        '<div class="modal-body" id="modalBody"></div>'
        '<div class="modal-foot"><button type="button" class="btn btn-ghost" id="modalCancel">Huỷ</button>'
        '<button type="button" class="btn btn-primary" id="modalSave">Lưu</button></div>'
        '</div></div>'
    )
    rm_meta = {'editable': bool(editable), 'statuses': RM_STATUSES, 'people': RM_PEOPLE}
    content = (
        f'<div class="page-head"><div><h2>Lộ trình QA Team</h2></div>{add_btn}</div>'
        + banner + seg
        + f'<div class="rm-list{ro}" id="rmList2"></div>'
        + modal
        + _json_script('rmData', data or [])
        + _json_script('rmMeta', rm_meta)
    )
    return _document_v2(content, 'roadmap', user, activities or [], title='Roadmap QA Team')


# ===== Bug Log v2 (issue #55) — bug từ Excel/Drive + link ngược Jira task =====
def render_bug_log_v2(data, links, editable=True, user=None, activities=None, sources=None):
    """Tab Bug Log: bảng bug/test-case (nguồn = cache bug_log_store), tab theo THÁNG
    (mỗi sheet Excel = 1 tháng — Decision #54), cột "Liên kết Task" = link app-side
    do user tự gán (task_link), KHÔNG từ Excel. Toàn bộ bảng render client-side bởi
    controller `#bugLogData` trong app_v2.js (tab/tick/link/pager).

    `data`  = bug_log_store.load_bug_log() = {files:{fid:{project,bugs:{key:bug},...}}, synced_at}
    `links` = task_link.load_links()       = {bugKey: {task,by,at}}
    """
    data = data or {}
    links = links or {}
    is_admin = user[1] if (user and len(user) > 1) else True
    files = data.get('files', {}) or {}
    reopen = data.get('reopen', {}) or {}

    bugs = []
    months = set()
    src_files = []   # file Drive đã scan (name/project/count) — cho source card; KHÁC `sources` param
    for fid, f in files.items():
        src_files.append({'name': f.get('name', '') or '(không tên)',
                          'project': f.get('project', ''), 'count': f.get('count', 0)})
        for key, b in (f.get('bugs', {}) or {}).items():
            month = b.get('month', '') or ''
            months.add(month)
            link = links.get(key) or {}
            bugs.append({
                'key': key,
                'fid': fid,
                'id': f"{b.get('project', '')}-{b.get('service') + '-' if b.get('service') else ''}{b.get('bug_no', '')}".strip('-'),
                'summary': b.get('summary', ''),
                'module': b.get('feature', ''),
                'severity': b.get('severity', ''),
                'status': b.get('status', ''),
                'project': b.get('project', ''),
                'month': month,
                'qa': normalize_tester(b.get('qa_pic', '')),
                'dev': b.get('dev_pic', ''),
                'created': (b.get('created', '') or '')[:10],
                'tasks': tasks_of(link),
            })
    # tháng mới nhất trước (chuỗi 'YYYY-MM' hoặc tên sheet -> sort desc theo chuỗi)
    month_list = sorted((m for m in months if m), reverse=True)

    synced = data.get('synced_at', '') or ''
    synced_disp = synced.replace('T', ' ')[:16] if synced else 'chưa đồng bộ'
    poll_min = max(1, BUG_LOG_POLL_SECONDS // 60)

    # source card: gộp các file Drive nguồn
    if src_files:
        src_names = ' · '.join(esc(s['name']) for s in src_files[:4])
        if len(src_files) > 4:
            src_names += f' +{len(src_files) - 4}'
        total_bugs = len(bugs)
        src_line = f'<b>{src_names}</b> — {total_bugs} bản ghi'
    else:
        src_line = '<b>Chưa kết nối nguồn Drive nào.</b> Vào Cài đặt để kết nối Google Drive.'

    # "Đồng bộ ngay" (thêm lại 2026-06-10): F5 chỉ render cache, không kéo Drive ->
    # nút này POST /sync-bug-log chạy scan() ngay rồi reload. Admin-only (endpoint gate).
    sync_btn = ('<button class="btn btn-ghost" id="blSyncBtn" title="Đọc lại data mới từ Drive ngay">'
                '<span class="material-symbols-rounded mi-sm">sync</span> '
                'Đồng bộ ngay</button>') if is_admin else ''
    # "Quản lý link drive" = modal CRUD list link đã add.
    drive_btn = ('<button class="btn btn-ghost" id="blManageBtn">'
                 '<span class="material-symbols-rounded mi-sm">link</span> '
                 'Quản lý link drive</button>') if editable else ''
    # ✎ trên source card: đổi link file bug -> hệ thống đi theo link load data (single).
    edit_link_btn = ('<button class="bl-src-edit material-symbols-rounded" id="blEditLinkBtn" '
                     'title="Chọn file bug để xem">folder_open</button>') if editable else ''

    # link-to-task bar (chỉ khi editable: cho tick + tạo link)
    linkbar = ''
    if editable:
        linkbar = (
            '<div class="bl-linkbar">'
            '<div class="bl-filter" id="blTesterWrap">'
            '<span class="material-symbols-rounded mi-sm">person_search</span>'
            '<select id="blTesterFilter"><option value="">Tất cả tester</option></select>'
            '</div>'
            '<div class="bl-ta" id="blTaskTA">'
            '<span class="material-symbols-rounded mi-sm">add_link</span>'
            '<div class="bl-ta-field" id="blTaskChips">'
            '<input type="text" id="blTaskInp" placeholder="Tìm task để liên kết (đã tick ở cột trái)…" autocomplete="off" spellcheck="false">'
            '</div>'
            '<div class="bl-ta-res" id="blTaskRes"></div></div>'
            '<button class="bl-linkbtn" id="blLinkBtn" disabled>'
            '<span class="material-symbols-rounded mi-sm">link</span> Liên kết với Task '
            '<span id="blSelCount"></span></button>'
            '</div>'
        )

    th_check = '<th style="width:40px"><input type="checkbox" class="bl-check" id="blCheckAll"></th>' if editable else ''
    content = (
        '<div class="page-head"><div>'
        '<h2 class="page-title">Bug Management</h2>'
        f'<div class="bl-sub"><span class="bl-dot"></span> Đã đồng bộ: {esc(synced_disp)}</div>'
        f'<div class="bl-next" id="blNextSync" data-synced="{esc(synced)}" data-interval="{BUG_LOG_POLL_SECONDS}">'
        f'<span class="material-symbols-rounded mi-sm">autorenew</span> '
        f'Tự đồng bộ lại toàn bộ file mỗi {poll_min} phút</div>'
        '</div><div style="display:flex;gap:10px;align-items:center">'
        f'{sync_btn}{drive_btn}</div></div>'
        # source card (✎ = đổi link file bug, tự sync sau khi lưu)
        '<div class="card bl-source">'
        '<span class="ic material-symbols-rounded">table_view</span>'
        '<div class="bl-src-info"><div class="lbl">NGUỒN DỮ LIỆU: GOOGLE DRIVE</div>'
        f'<div class="fname" id="blSrcLine">{src_line}</div>'
        '<span class="bl-active-file" id="blActiveFile" style="display:none"></span></div>'
        f'{edit_link_btn}</div>'
        # tab tháng
        '<div class="bl-tabs" id="blTabs"></div>'
        + linkbar
        # table
        + '<div class="card"><div class="table-header"><div class="table-title">'
        '<span class="material-symbols-rounded">bug_report</span>'
        '<span>Danh sách Bug / Test Case</span></div>'
        '<div class="bl-count" id="blCount"></div></div>'
        '<div style="overflow-x:auto"><table class="bl-table"><thead><tr>'
        f'{th_check}'
        '<th style="width:110px">ID</th><th style="width:140px">Module</th>'
        '<th>Mô tả bug</th><th style="width:110px;white-space:nowrap">Ngày</th>'
        '<th style="width:140px">Trạng thái</th>'
        '<th style="width:120px">Tester</th><th style="width:130px">Dev in charge</th>'
        '<th style="width:160px">Liên kết Task</th>'
        '</tr></thead><tbody id="blRows"></tbody></table></div>'
        '<div class="pager" id="blPager"></div></div>'
        # metric cards container
        '<div class="metrics-row" style="display: flex; gap: 24px; align-items: flex-start; margin-top: 24px; flex-wrap: wrap;">'
        
        # metric card 1 (Pie charts)
        '<div class="card metric-card" style="flex: 1; min-width: 400px; margin-top: 0;">'
        '<div class="metric-header">'
        '<div class="table-title"><span>Metric đo bug của Dev theo dự án (Tháng)</span></div>'
        '<div class="metric-filter" style="display:flex; align-items:center; gap:8px;">'
        '<button class="lbtn ghost" id="btnExportMetricChart" title="Export PDF ảnh chart" style="padding: 4px 8px; font-size: 13px;">'
        '<span class="material-symbols-rounded mi-sm">picture_as_pdf</span> Export PDF</button>'
        '<span class="material-symbols-rounded mi-sm">calendar_month</span> <select id="blMetricMonth"></select></div>'
        '</div>'
        '<div id="blMetricCharts" style="padding: 20px; display: flex; gap: 24px; flex-wrap: wrap; justify-content: center;"></div>'
        '</div>'
        
        # reopen metric card — chất lượng fix của dev (Decision: issue #69)
        '<div class="card metric-card" style="flex: 1; min-width: 400px; margin-top: 0;">'
        '<div class="metric-header">'
        '<div class="table-title"><span>Tỷ lệ Reopen — chất lượng fix của dev (Tháng)</span></div>'
        '<div class="metric-filter"><span class="material-symbols-rounded mi-sm">calendar_month</span> <select id="blReopenMonth"></select></div>'
        '</div>'
        '<div class="bl-reopen-kpi" id="blReopenKpi"></div>'
        '<div style="overflow-x:auto"><table class="bl-table metric-table"><thead><tr id="blReopenHead"></tr></thead><tbody id="blReopenRows"></tbody></table></div>'
        '<div class="bl-reopen-note">Số tích luỹ từ khi bật theo dõi; reopen trước đó không có lịch sử. '
        'Round-trip Fixed→Reopen→Fixed gọn trong 10 phút có thể bị sót.</div>'
        '</div>'

        '</div>' # end metrics-row
        + (_bug_log_source_modals() if editable else '')
        + _json_script('bugLogData', {
            'bugs': bugs, 'months': month_list, 'editable': bool(editable),
            'syncedAt': synced_disp, 'reopen': reopen,
            'sources': [{'id': s.get('id', ''), 'label': s.get('label', ''), 'service': s.get('service', ''),
                          'name': (files.get(s.get('id', ''), {}) or {}).get('name', '')}
                        for s in (sources or []) if s.get('id')],
        })
    )
    return _document_v2(content, 'buglog', user, activities or [],
                        title='QA Workspace — Bug Log')


def _bug_log_source_modals():
    """2 modal admin của Bug Log:
    - #blEditOv: đổi link 1 file bug (paste link Drive) — ✎ trên source card.
    - #blSrcOv : quản lý list link Drive đã add (thêm/sửa/xoá) — nút "Quản lý link drive".
    Cả hai POST /save-bug-log-sources (full list) -> server rút file id + scan ngay."""
    return (
        # ----- đổi link 1 file (single) -----
        '<div class="overlay" id="blEditOv"><div class="modal">'
        '<div class="modal-head"><span class="material-symbols-rounded">folder_open</span>'
        '<h3>Chọn file bug để xem</h3>'
        '<button type="button" class="x material-symbols-rounded" id="blEditClose">close</button></div>'
        '<div class="modal-body"><p class="modal-note">Chọn 1 file Drive đã thêm để xem riêng dữ liệu của file đó. '
        'Quản lý (thêm/sửa/xoá link) ở “Quản lý link drive”.</p>'
        '<div id="blPickList" class="bl-pick-list"></div></div>'
        '<div class="modal-foot">'
        '<button type="button" class="btn btn-ghost" id="blEditCancel">Đóng</button>'
        '</div></div></div>'
        # ----- quản lý list link -----
        '<div class="overlay" id="blSrcOv"><div class="modal" style="width:620px">'
        '<div class="modal-head"><span class="material-symbols-rounded">link</span>'
        '<h3>Quản lý link drive</h3>'
        '<button type="button" class="x material-symbols-rounded" id="blSrcClose">close</button></div>'
        '<div class="modal-body"><p class="modal-note">Danh sách file Drive nguồn đã thêm. '
        'Sửa/xoá/thêm link rồi bấm Lưu — hệ thống sẽ đồng bộ ngay.</p>'
        '<div id="blSrcList" class="bl-src-list"></div>'
        '<button type="button" class="btn btn-ghost" id="blSrcAdd" style="align-self:flex-start">'
        '<span class="material-symbols-rounded mi-sm">add</span> Thêm link</button></div>'
        '<div class="modal-foot">'
        '<button type="button" class="btn btn-ghost" id="blSrcCancel">Huỷ</button>'
        '<button type="button" class="btn btn-primary" id="blSrcSave">Lưu &amp; đồng bộ</button>'
        '</div></div></div>'
    )


def render_leader_eval_page(tasks, year, month, user=None, activities=None, categories=None, sel_category='', sel_leader='', sel_assignees=None):
    from config import LEADER_EVAL_NUM_FIELD, LEADER_EVAL_TEXT_FIELD, USERS, display_name
    import json
    sel_assignees = sel_assignees or []

    rows = []
    unique_statuses = set()
    unique_assignees = {}
    for issue in tasks:
        f = issue.get('fields', {})
        st = (f.get('status') or {}).get('name') or ''
        if st:
            unique_statuses.add(st)
        asg_user = i_assignee(issue)
        asg_name = i_assignee_name(issue)
        unique_assignees[asg_user] = asg_name
        num_val = f.get(LEADER_EVAL_NUM_FIELD)
        num_str = str(num_val) if num_val is not None else ''
        text_val = f.get(LEADER_EVAL_TEXT_FIELD) or ''
        # "Đã đánh giá" = 1 trong 2 field Leader đánh giá có value
        evaluated = '1' if (num_val is not None or text_val.strip()) else '0'

        rows.append(f"""
        <tr class="eval-row" data-status="{esc(st)}" data-key="{esc(issue['key'])}" data-assignee="{esc(asg_user)}" data-evaluated="{evaluated}">
            <td style="text-align:center"><input type="checkbox" class="eval-chk" value="{esc(issue['key'])}"></td>
            <td>{issue_link(issue)}</td>
            <td class="summary-cell clickable" title="{esc(i_summary(issue))}">{esc(i_summary(issue))}</td>
            <td>{esc(asg_name)}</td>
            <td><span class="status {status_class(st)}">{esc(st)}</span></td>
            <td>{esc(num_str)}</td>
            <td><div style="max-height:60px;overflow-y:auto;font-size:0.9em">{esc(text_val)}</div></td>
        </tr>""")

    status_opts = ''
    for st in sorted(unique_statuses):
        status_opts += f'<option value="{esc(st)}">{esc(st)}</option>'

    asg_opts = ''
    for u, n in sorted(unique_assignees.items(), key=lambda kv: kv[1].lower()):
        asg_opts += f'<option value="{esc(u)}">{esc(n)}</option>'

    table_html = f"""
    <div class="card">
    <table class="data-table">
        <thead>
            <tr>
                <th style="width:40px;text-align:center"><input type="checkbox" id="evalCheckAll"></th>
                <th>Key</th>
                <th>Summary</th>
                <th>Assignee</th>
                <th>Status</th>
                <th>Điểm (Số)</th>
                <th>Đánh giá (Text)</th>
            </tr>
        </thead>
        <tbody id="evalTbody">
            {''.join(rows) if rows else '<tr><td colspan="7" class="empty">Không có task nào.</td></tr>'}
        </tbody>
    </table>
    </div>
    """

    cat_opts = '<option value="">-- Tất cả --</option>'
    for c in (categories or []):
        n = c.get('name', '')
        sel = ' selected' if n == sel_category else ''
        cat_opts += f'<option value="{esc(n)}"{sel}>{esc(n)}</option>'

    all_leaders = set(USERS)
    all_leaders.add('thanhht1')
    ld_opts = '<option value="">-- Tất cả --</option>'
    for u in sorted(all_leaders):
        sel = ' selected' if u == sel_leader else ''
        ld_opts += f'<option value="{esc(u)}"{sel}>{esc(display_name(u))}</option>'

    excl_hidden = ''.join(f'<input type="hidden" name="assignee" value="{esc(u)}">' for u in sel_assignees)

    excl_dropdown_opts = '<option value="">+ Chọn Assignee...</option>'
    for u in USERS:
        if u not in sel_assignees:
            excl_dropdown_opts += f'<option value="{esc(u)}">{esc(display_name(u))}</option>'

    month_str = f"{year}-{month:02d}"

    chip_css = """
    <style>
    .eval-filter { display:flex; flex-wrap:wrap; gap:14px 16px; align-items:flex-end; }
    .ef { display:flex; flex-direction:column; gap:6px; }
    .eval-flabel { font-size:12px; font-weight:600; color:var(--on-surface-variant); }
    .eval-filter .set-input { height:42px; box-sizing:border-box; margin:0; }
    .ef-month  .set-input { width:140px; }
    .ef-cat    .set-input { width:200px; }
    .ef-leader .set-input { width:150px; }
    .ef-assignee .set-input { width:200px; }
    .eval-filter .btn-primary { height:42px; padding:0 24px; }
    .eval-chips { flex-basis:100%; display:flex; flex-wrap:wrap; gap:8px; margin-top:2px; }
    .eval-chips:empty { display:none; }
    .eval-chip { display:inline-flex; align-items:center; gap:6px; background:var(--surface-container);
        color:var(--on-surface); padding:4px 8px 4px 12px; border-radius:14px; font-size:13px; font-weight:600; }
    .eval-chip-x { cursor:pointer; color:var(--on-surface-variant); font-size:16px; line-height:1;
        width:18px; height:18px; display:inline-flex; align-items:center; justify-content:center; border-radius:50%; }
    .eval-chip-x:hover { color:#fff; background:#f15b50; }
    .eval-row { cursor:pointer; }
    .eval-row:hover { background:var(--surface-low); }
    .eval-row .summary-cell.clickable { color:var(--on-surface); }
    </style>
    """

    name_map_json = json.dumps({u: display_name(u) for u in USERS})
    excl_chips = ''.join(
        f'<span class="eval-chip" data-val="{esc(u)}">{esc(display_name(u))}'
        f'<span class="eval-chip-x" onclick="removeExcl(\'{esc(u)}\')">\u00d7</span></span>'
        for u in sel_assignees)

    # Build JS as a separate string (NOT inside f-string) to avoid {{/}} hell
    js_block = """
    <script>
    (function() {
        function updateCount() {
            var sel = document.querySelectorAll('.eval-chk:checked').length;
            var lbl = document.getElementById('evalSelectedCount');
            if (lbl) lbl.textContent = sel + ' task \\u0111ang ch\\u1ecdn';
        }

        /* Status + Assignee filters (combined) */
        var sf = document.getElementById('statusFilter');
        var af = document.getElementById('asgFilter');
        var ef = document.getElementById('evalStateFilter');
        function applyRowFilters() {
            var sv = sf ? sf.value : '';
            var av = af ? af.value : '';
            var ev = ef ? ef.value : '';
            document.querySelectorAll('.eval-row').forEach(function(r) {
                var ok = (!sv || r.getAttribute('data-status') === sv) &&
                         (!av || r.getAttribute('data-assignee') === av) &&
                         (!ev || r.getAttribute('data-evaluated') === ev);
                if (ok) {
                    r.style.display = '';
                } else {
                    r.style.display = 'none';
                    var c = r.querySelector('.eval-chk');
                    if (c) c.checked = false;
                }
            });
            updateCount();
        }
        if (sf) sf.addEventListener('change', applyRowFilters);
        if (af) af.addEventListener('change', applyRowFilters);
        if (ef) ef.addEventListener('change', applyRowFilters);

        /* Check-all */
        var ca = document.getElementById('evalCheckAll');
        if (ca) ca.addEventListener('change', function() {
            var me = this;
            document.querySelectorAll('.eval-chk').forEach(function(c) {
                var row = c.closest('tr');
                if (row && row.style.display !== 'none') c.checked = me.checked;
            });
            updateCount();
        });

        /* Individual checkboxes */
        document.querySelectorAll('.eval-chk').forEach(function(c) {
            c.addEventListener('change', updateCount);
        });

        /* Click a row -> open detail drawer (ignore checkbox + links) */
        var tbody = document.getElementById('evalTbody');
        if (tbody) tbody.addEventListener('click', function(e) {
            if (e.target.closest('input, a, label, button')) return;
            var row = e.target.closest('tr.eval-row');
            if (!row) return;
            var key = row.getAttribute('data-key');
            if (key && window.__openDetail) window.__openDetail(key);
        });

        /* Batch eval */
        window._doBatchEval = async function() {
            var keys = Array.from(document.querySelectorAll('.eval-chk:checked')).map(function(c){ return c.value; });
            if (keys.length === 0) { alert('Vui l\\u00f2ng ch\\u1ecdn \\u00edt nh\\u1ea5t 1 task.'); return; }
            var num_val = document.getElementById('evalNum').value;
            var text_val = document.getElementById('evalText').value;
            if (!num_val && !text_val) { alert('Vui l\\u00f2ng nh\\u1eadp \\u0111i\\u1ec3m ho\\u1eb7c text.'); return; }

            var resDiv = document.getElementById('evalResult');
            var btn = document.getElementById('btnBatchEval');
            resDiv.textContent = '\\u0110ang x\\u1eed l\\u00fd...';
            resDiv.style.color = '#a5adba';
            btn.disabled = true;

            try {
                var r = await fetch('/batch-eval', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({keys: keys, num_val: num_val || null, text_val: text_val || null})
                });
                var data = await r.json();
                resDiv.textContent = data.msg || (data.ok ? 'Th\\u00e0nh c\\u00f4ng' : 'L\\u1ed7i');
                resDiv.style.color = data.ok ? '#94C748' : '#F87168';
                if (data.ok) setTimeout(function(){ location.reload(); }, 2000);
            } catch (e) {
                resDiv.textContent = 'L\\u1ed7i m\\u1ea1ng: ' + e;
                resDiv.style.color = '#F87168';
            } finally {
                btn.disabled = false;
            }
        };

        /* Assignee multi-select: dropdown adds a chip on its own row below */
        var dd = document.getElementById('exclDropdown');
        var chips = document.getElementById('exclChipsContainer');
        var hidden = document.getElementById('exclHiddenInputs');

        window.removeExcl = function(val) {
            var chip = chips.querySelector('.eval-chip[data-val="' + val + '"]');
            if (chip) chip.remove();
            var inp = hidden.querySelector('input[value="' + val + '"]');
            if (inp) inp.remove();
            var opt = document.createElement('option');
            opt.value = val;
            opt.textContent = (window.EVAL_NAMES && window.EVAL_NAMES[val]) || val;
            dd.appendChild(opt);
        };

        function addExcl(val) {
            var name = (window.EVAL_NAMES && window.EVAL_NAMES[val]) || val;
            var chip = document.createElement('span');
            chip.className = 'eval-chip';
            chip.setAttribute('data-val', val);
            chip.textContent = name;
            var x = document.createElement('span');
            x.className = 'eval-chip-x';
            x.textContent = '\\u00d7';
            x.onclick = function() { removeExcl(val); };
            chip.appendChild(x);
            chips.appendChild(chip);
            var inp = document.createElement('input');
            inp.type = 'hidden';
            inp.name = 'assignee';
            inp.value = val;
            hidden.appendChild(inp);
        }

        if (dd) dd.addEventListener('change', function() {
            var val = this.value;
            if (!val) return;
            var opt = this.options[this.selectedIndex];
            if (opt) opt.remove();
            this.value = '';
            addExcl(val);
        });
    })();
    </script>
    """
    js_block = '<script>window.EVAL_NAMES = ' + name_map_json + ';</script>' + js_block

    inner = f"""
    {chip_css}
    <div class="page-head">
        <div>
            <h2 class="page-title">\u2b50 \u0110\u00e1nh gi\u00e1 Task QA (Leader)</h2>
            <div class="page-sub">L\u1ecdc task, ch\u1ecdn nhi\u1ec1u task \u0111\u1ec3 ch\u1ea5m \u0111i\u1ec3m v\u00e0 \u0111\u00e1nh gi\u00e1 h\u00e0ng lo\u1ea1t. L\u01b0u tr\u1ef1c ti\u1ebfp l\u00ean Jira.</div>
        </div>
    </div>

    <!-- B\u1ed9 l\u1ecdc -->
    <div class="card" style="margin-bottom:20px; padding:16px;">
        <form action="/leader-eval" method="GET" id="evalFilterForm" class="eval-filter">
            <div class="ef ef-month">
                <label class="eval-flabel">Th\u00e1ng:</label>
                <input type="month" name="month" value="{month_str}" class="set-input">
            </div>
            <div class="ef ef-cat">
                <label class="eval-flabel">Category:</label>
                <select name="category" class="set-input">{cat_opts}</select>
            </div>
            <div class="ef ef-leader">
                <label class="eval-flabel">Leader:</label>
                <select name="leader" class="set-input">{ld_opts}</select>
            </div>
            <div class="ef ef-assignee">
                <label class="eval-flabel">Assignee:</label>
                <select id="exclDropdown" class="set-input">{excl_dropdown_opts}</select>
            </div>
            <button type="submit" class="btn btn-primary">L\u1ecdc</button>
            <div id="exclHiddenInputs" style="display:none;">{excl_hidden}</div>
            <div class="eval-chips" id="exclChipsContainer">{excl_chips}</div>
        </form>
    </div>

    <div style="display:flex; gap:20px; align-items:flex-start;">
        <div style="flex:1;">
            <div class="section">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <div style="display:flex; align-items:center; gap:16px;">
                        <h3 style="margin:0;">Danh s\u00e1ch Task ({len(tasks)})</h3>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <label style="font-size:13px; font-weight:600; color:var(--on-surface-variant);">L\u1ecdc Status:</label>
                            <select id="statusFilter" class="set-input" style="margin:0; padding:4px 28px 4px 8px; font-size:13px; width:160px;">
                                <option value="">-- T\u1ea5t c\u1ea3 --</option>
                                {status_opts}
                            </select>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <label style="font-size:13px; font-weight:600; color:var(--on-surface-variant);">L\u1ecdc Assignee:</label>
                            <select id="asgFilter" class="set-input" style="margin:0; padding:4px 28px 4px 8px; font-size:13px; width:160px;">
                                <option value="">-- T\u1ea5t c\u1ea3 --</option>
                                {asg_opts}
                            </select>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <label style="font-size:13px; font-weight:600; color:var(--on-surface-variant);">\u0110\u00e1nh gi\u00e1:</label>
                            <select id="evalStateFilter" class="set-input" style="margin:0; padding:4px 28px 4px 8px; font-size:13px; width:160px;">
                                <option value="">-- T\u1ea5t c\u1ea3 --</option>
                                <option value="1">\u0110\u00e3 \u0111\u00e1nh gi\u00e1</option>
                                <option value="0">Ch\u01b0a \u0111\u00e1nh gi\u00e1</option>
                            </select>
                        </div>
                    </div>
                    <span id="evalSelectedCount" style="color:#85b8ff; font-weight:bold;">0 task \u0111ang ch\u1ecdn</span>
                </div>
                {table_html}
            </div>
        </div>
        <div style="width:320px; position:sticky; top:20px;">
            <div class="card" style="padding:20px;">
                <h3>C\u1eadp nh\u1eadt h\u00e0ng lo\u1ea1t</h3>
                <p class="set-note" style="margin-top:4px;">Ch\u1ec9 c\u1eadp nh\u1eadt cho c\u00e1c task \u0111ang \u0111\u01b0\u1ee3c ch\u1ecdn (tick) \u1edf b\u00ean tr\u00e1i.</p>
                <div style="display:flex; flex-direction:column; gap:12px; margin-top:16px;">
                    <div>
                        <label style="display:block; margin-bottom:4px; font-weight:500;">\u0110i\u1ec3m (S\u1ed1):</label>
                        <input type="number" id="evalNum" class="set-input" placeholder="VD: 8.5" step="0.1">
                        <small style="color:var(--on-surface-variant);">B\u1ecf tr\u1ed1ng n\u1ebfu kh\u00f4ng mu\u1ed1n \u0111\u1ed5i</small>
                    </div>
                    <div>
                        <label style="display:block; margin-bottom:4px; font-weight:500;">\u0110\u00e1nh gi\u00e1 (Text):</label>
                        <textarea id="evalText" class="set-input" rows="4" placeholder="Nh\u1eadn x\u00e9t..."></textarea>
                        <small style="color:var(--on-surface-variant);">B\u1ecf tr\u1ed1ng n\u1ebfu kh\u00f4ng mu\u1ed1n \u0111\u1ed5i</small>
                    </div>
                    <button type="button" class="btn btn-primary" id="btnBatchEval" style="margin-top:8px;" onclick="window._doBatchEval()">L\u01b0u l\u00ean Jira</button>
                    <div id="evalResult" style="margin-top:8px; font-size:0.9em; white-space:pre-wrap;"></div>
                </div>
            </div>
        </div>
    </div>

    {js_block}
    """
    return _document_v2(inner, 'leadereval', user, activities or [], title=f'\u0110\u00e1nh gi\u00e1 th\u00e1ng {month}/{year} \u2014 QA Dashboard')


def render_error_page(msg):
    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><title>Error</title>
<script>(function(){{try{{var t=localStorage.getItem('qa-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>{load_css()}</style></head>
<body><div class="container"><header><h1>QA Team Dashboard</h1></header>
<div class="error"><strong>Lỗi pull data từ Jira:</strong><br>{esc(msg)}</div>
<p style="color:#6b778c;margin-top:16px">Check JIRA_URL, JIRA_PAT trong file .env. F5 để retry.</p>
</div></body></html>"""
