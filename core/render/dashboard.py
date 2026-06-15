"""Dashboard pages v2 — admin team-wide view + QA personal lens, plus the
`render_page` dispatcher.

- `render_page`     : chọn nhánh admin/QA theo `user[1]` (is_admin).
- `render_admin_v2` : dashboard team (pills + member filter + bảng 6 cột + KPI + metric bug + drawer).
- `render_qa_v2`    : lens cá nhân (QA `/` + admin `/my-work`) — 1 bảng + tabs + KPI.

Tách từ render/__init__.py (issue #106 / #86). Zero behavior change — chỉ di
chuyển định nghĩa, re-export ở __init__ để chỗ gọi không phải đổi import.
"""
import json
from datetime import datetime, timedelta

from config import JIRA_URL, STUCK_DAYS
from issues import (parse_date, i_assignee, i_assignee_name, i_status, i_summary,
                    i_duedate, i_created, i_updated, days_overdue, is_stuck, esc)
from custom_status import CUSTOM_STATUSES, values_of

from render.base import _json_script
from render.shell import _avatar, _document_v2, _conn_error_card


# Markup card "Metric Bug" — KHÔNG cần Jira (nguồn = bug_log_store cache local). Tách
# riêng để dùng được cả nhánh bình thường lẫn nhánh jira_error (giữ block này khi Jira down).
def _bug_metric_card_html():
    return (
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
    )


# ===== Full page =====
def render_page(data, new_keys, first_run, activities, activity_days=7, roadmap_data=None,
                user=None, custom_overlay=None, bug_log_data=None, jira_error=False, stale=False):
    is_admin = user[1] if (user and len(user) > 1) else True

    # QA thường (non-admin): data đã auto-scope về chính họ -> UI v2 (shell sidebar Stitch).
    if not is_admin:
        return render_qa_v2(data, new_keys, activities, custom_overlay, user,
                            jira_error=jira_error, stale=stale)

    # Admin -> new v2 dashboard (pills + member filter + 5-col table + KPI cards)
    return render_admin_v2(data, new_keys, activities, custom_overlay, user,
                           bug_log_data=bug_log_data, jira_error=jira_error, stale=stale)


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


# ===== Admin Dashboard v2 (team-wide — pills + member filter + 5-col table + KPI cards) =====
def _snap_note(data):
    """Mô tả nguồn snapshot cho banner offline: 'dữ liệu lúc HH:MM dd/mm (fetch bởi X)'."""
    fa = (data or {}).get('fetched_at')
    when = fa.strftime('%H:%M %d/%m') if hasattr(fa, 'strftime') else '?'
    by = (data or {}).get('fetched_by') or 'máy khác'
    return f'dữ liệu lúc {when} (fetch bởi {by})'


def render_admin_v2(data, new_keys, activities, cmap, user, bug_log_data=None,
                    jira_error=False, stale=False):
    """Admin dashboard v2: team-wide view with status pills, member dropdown, paginated
    5-column table, 3 KPI cards, and a task detail drawer. Data is embedded as JSON and
    rendered entirely client-side by the admin controller in app_v2.js.

    jira_error=True -> Jira không với tới được: chỉ vùng task (pills/bảng/KPI, nguồn Jira)
    đổi sang card lỗi; KHÔNG drop #rows table thật -> dashboard controller bail (guard #rows).
    Block Metric Bug (cache local) VẪN render + hoạt động bình thường."""
    if jira_error:
        content = (
            '<div class="page-head"><div>'
            '<h2 class="page-title">Task Management</h2></div></div>'
            + _conn_error_card()
            + _bug_metric_card_html()
            + _json_script('bugMetrics', _bug_metrics_payload(bug_log_data))
        )
        return _document_v2(content, 'dashboard', user, activities,
                            title='QA Workspace — Task Management')

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
            'isNew': is_new, 'active': True,
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
            'isNew': (i_created(iss) or '')[:10] == today_str, 'active': False,
            'jiraUrl': f'{JIRA_URL}/browse/{key}',
        })

    # Pill counts
    n_todo = sum(1 for t in tasks if t['jira'] == 'TO DO' and not t['isNew'] and not t['overdue'])
    # "In Progress" = MỌI task active không phải TO DO (In Progress, PENDING, và bất kỳ
    # status active mới nào) → todo ∪ progress phủ trọn bucket active, không status nào lọt (issue #39).
    n_prog = sum(1 for t in tasks if t['active'] and t['jira'] != 'TO DO' and not t['stuck'] and not t['overdue'])
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
        + _bug_metric_card_html()
        # Status menu (drawer DOM nằm ở shell _document_v2 -> mọi trang dùng chung)
        + '<div class="smenu" id="smenu"></div>'
        + _json_script('bugMetrics', _bug_metrics_payload(bug_log_data))
        + _json_script('qaData', {'tasks': tasks, 'meta': meta})
        + f'<script>window.QA_CUSTOM_STATUSES={json.dumps(CUSTOM_STATUSES, ensure_ascii=False)};</script>'
    )
    return _document_v2(content, 'dashboard', user, activities,
                        title='QA Workspace — Task Management',
                        stale=stale, stale_note=_snap_note(data) if stale else '')


# ===== Dashboard QA v2 (lens cá nhân — 1 bảng + tabs + KPI + drawer) =====
# Dùng chung cho QA member (`/`, nav_active='dashboard') và admin xem việc mình
# (`/my-work`, nav_active='mywork') — UI hệt nhau, chỉ khác tab sidebar được highlight.
def render_qa_v2(data, new_keys, activities, cmap, user, nav_active='dashboard',
                 jira_error=False, stale=False):
    # Lens cá nhân = 100% data Jira (không có block local nào) -> Jira down thì cả vùng
    # nội dung báo lỗi, giữ skeleton sidebar/topbar.
    if jira_error:
        content = (
            '<div class="page-head"><div class="page-title">Tổng quan — Việc của tôi</div></div>'
            + _conn_error_card()
        )
        return _document_v2(content, nav_active, user, activities,
                            title='QA Dashboard — Việc của tôi')

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
    return _document_v2(content, nav_active, user, activities, title='QA Dashboard — Việc của tôi',
                        stale=stale, stale_note=_snap_note(data) if stale else '')
