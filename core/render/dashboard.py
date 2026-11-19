"""Lens cá nhân "Việc của tôi" (`/my-work`) — 1 bảng + tabs + KPI + drawer.

Dashboard team (`render_admin_v2`, workload, metric bug) đã gỡ ở Decision #97 — app giờ
là của riêng 1 người nên chỉ còn lens cá nhân.
"""
from datetime import datetime, timedelta

from config import LINEAR_BASE_URL, STUCK_DAYS, role_of
from issues import (parse_date, i_assignee, i_assignee_name, i_status, i_status_cat, i_summary,
                    i_duedate, i_created, i_comment_count, days_overdue, is_stuck,
                    i_resolved, i_updated, i_type)
from custom_status import values_of
from task_notes import index_by_canon
from config import canon_key

from render.base import _json_script
from render.shell import _avatar, _document_v2, _conn_error_card


def _snap_note(data):
    """Mô tả bản data đang hiện cho banner token hết hạn: 'dữ liệu lúc HH:MM dd/mm'."""
    fa = (data or {}).get('fetched_at')
    when = fa.strftime('%H:%M %d/%m') if hasattr(fa, 'strftime') else '?'
    return f'dữ liệu lúc {when}'



# ===== Lens cá nhân — payload =====
def build_my_work_payload(data, cmap, notes=None):
    """Dựng data thuần cho lens "Việc của tôi" từ snapshot Jira đã scope.

    Chỉ tính toán, KHÔNG dựng markup. Trả `(tasks, meta)`:
    - tasks: list task active + done_week, mỗi task là dict field UI-agnostic.
    - meta : count KPI (active/overdue/stuck/dueweek/done + STUCK_DAYS).
    """
    active = data['active']
    note_idx = index_by_canon(notes or {})   # ghi chú riêng (#101) -> cờ hasNote trên bảng
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)

    tasks = []
    n_over = n_stuck = n_dueweek = 0
    for iss in active:
        st = i_status(iss)
        st_cat = i_status_cat(iss)
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
        asg_email = ((iss.get('fields', {}).get('assignee') or {}).get('emailAddress') or '')
        p_obj = iss.get('fields', {}).get('parent') or {}
        pr_obj = iss.get('fields', {}).get('project') or {}
        tasks.append({
            'key': iss['key'], 'summary': i_summary(iss), 'jira': st, 'cat': st_cat,
            'issuetype': i_type(iss) or 'Task',
            'feature': pr_obj.get('name', ''),
            'featureUrl': pr_obj.get('url', ''),
            'parentKey': p_obj.get('key', ''),
            'parentSummary': (p_obj.get('fields') or {}).get('summary', ''),
            'subtasks': iss.get('subtasks') or [],
            'customs': customs, 'canCustom': st_cat in ('TO DO', 'In Progress'),
            'assignee': {'name': aname, 'email': asg_email, 'role': role_of(asg_email), 'init': init, 'cls': cls},
            'due': i_duedate(iss) or '', 'dueDisp': i_duedate(iss) or 'Chưa đặt hạn',
            'dueCls': duecls, 'overdue': overdue, 'stuck': stuck, 'dueWeek': dueweek,
            'created': (i_created(iss) or '')[:10], 'createdDisp': (i_created(iss) or '')[:10] or '—',
            'nComments': i_comment_count(iss),
            'hasNote': canon_key(iss['key']) in note_idx,
            'jiraUrl': iss.get('url') or f'{LINEAR_BASE_URL}/issue/{iss["key"]}',
        })
    # Done tasks (tất cả) — để tab/KPI "Done" xem được list, không chỉ số đếm.
    for iss in data['done_week']:
        st = i_status(iss)
        st_cat = i_status_cat(iss)
        a = i_assignee(iss)
        aname = i_assignee_name(iss)
        init, cls = _avatar(a, aname)
        asg_email = ((iss.get('fields', {}).get('assignee') or {}).get('emailAddress') or '')
        p_obj = iss.get('fields', {}).get('parent') or {}
        pr_obj = iss.get('fields', {}).get('project') or {}
        tasks.append({
            'key': iss['key'], 'summary': i_summary(iss), 'jira': st,
            'issuetype': i_type(iss) or 'Task',
            'feature': pr_obj.get('name', ''),
            'featureUrl': pr_obj.get('url', ''),
            'parentKey': p_obj.get('key', ''),
            'parentSummary': (p_obj.get('fields') or {}).get('summary', ''),
            'subtasks': iss.get('subtasks') or [],
            'customs': [], 'canCustom': False,
            'assignee': {'name': aname, 'email': asg_email, 'role': role_of(asg_email), 'init': init, 'cls': cls},
            'due': i_duedate(iss) or '', 'dueDisp': i_duedate(iss) or '',
            'dueCls': '', 'overdue': False, 'stuck': False, 'dueWeek': False,
            'created': (i_created(iss) or '')[:10], 'createdDisp': (i_created(iss) or '')[:10] or '—',
            'nComments': i_comment_count(iss),
            'hasNote': canon_key(iss['key']) in note_idx,
            'jiraUrl': iss.get('url') or f'{LINEAR_BASE_URL}/issue/{iss["key"]}',
            # Ngày hoàn thành cho standup (#110): resolutiondate thường null (#4b) -> fallback updated.
            'doneAt': (i_resolved(iss) or i_updated(iss) or '')[:10],
        })
    meta = {'active': len(active), 'overdue': n_over, 'stuck': n_stuck,
            'dueweek': n_dueweek, 'done': len(data['done_week']), 'stuckDays': STUCK_DAYS}
    return tasks, meta


# ===== Dashboard QA v2 (lens cá nhân — 1 bảng + tabs + KPI + drawer) =====
def render_qa_v2(data, activities, cmap, user, nav_active='mywork',
                 jira_error=False, stale=False, notes=None):
    # Lens cá nhân = 100% data Jira (không có block local nào) -> Jira down thì cả vùng
    # nội dung báo lỗi, giữ skeleton sidebar/topbar.
    from linear_api import get_active_cycle_info
    cycle_info = get_active_cycle_info()
    cycle_lbl = cycle_info.get('label') or 'Cycle hiện tại'
    if jira_error:
        content = (
            f'<div class="page-head"><div class="page-title">{cycle_lbl}</div></div>'
            + _conn_error_card()
        )
        return _document_v2(content, nav_active, user, activities,
                            title=f'QA Workspace — {cycle_lbl}')

    tasks, meta = build_my_work_payload(data, cmap, notes)
    cycle_payload = {
        'label': cycle_lbl,
        'startsAt': cycle_info.get('startsAt', ''),
        'endsAt': cycle_info.get('endsAt', ''),
        'today': datetime.now().strftime('%Y-%m-%d'),
    }

    board = (
        '<div class="card bd-card" id="bdCard"></div>'
        '<div class="kb-toolbar">'
        '<select id="kbAsgFilter" class="kb-ctl" title="Lọc theo người phụ trách">'
        '<option value="">Tất cả người</option></select>'
        '<select id="kbFeatFilter" class="kb-ctl" title="Lọc theo Feature / Project">'
        '<option value="">Tất cả Feature</option></select>'
        '<select id="kbTypeFilter" class="kb-ctl" title="Lọc theo loại issue">'
        '<option value="">Tất cả loại</option>'
        '<option value="Bug">Chỉ Bug</option>'
        '<option value="Task">Task</option>'
        '<option value="Sub-task">Sub-task</option>'
        '<option value="Improvement">Improvement</option></select>'
        '<button type="button" class="kb-ctl kb-btn" id="kbGroupBtn" title="Gom nhóm theo Feature">'
        '<span class="material-symbols-rounded ph-light ph-folders mi-xs"></span>'
        '<span>Gom theo Feature</span></button>'
        '</div>'
        '<div class="board" id="board"></div>'
    )
    content = (
        f'<div class="page-head"><div class="page-title">{cycle_lbl}</div></div>'
        + board
        + _json_script('qaData', {'tasks': tasks, 'meta': meta, 'cycle': cycle_payload})
    )
    return _document_v2(content, nav_active, user, activities, title=f'QA Workspace — {cycle_lbl}',
                        stale=stale, stale_note=_snap_note(data) if stale else '')
