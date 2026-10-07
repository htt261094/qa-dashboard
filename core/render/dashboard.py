"""Lens cá nhân "Việc của tôi" (`/my-work`) — 1 bảng + tabs + KPI + drawer.

Dashboard team (`render_admin_v2`, workload, metric bug) đã gỡ ở Decision #97 — app giờ
là của riêng 1 người nên chỉ còn lens cá nhân.
"""
from datetime import datetime, timedelta

from config import JIRA_URL, STUCK_DAYS
from issues import (parse_date, i_assignee, i_assignee_name, i_status, i_summary,
                    i_duedate, i_created, i_comment_count, days_overdue, is_stuck,
                    i_resolved, i_updated)
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
            'nComments': i_comment_count(iss),
            'hasNote': canon_key(iss['key']) in note_idx,
            'jiraUrl': f'{JIRA_URL}/browse/{iss["key"]}',
        })
    # Done tasks (tất cả) — để tab/KPI "Done" xem được list, không chỉ số đếm.
    for iss in data['done_week']:
        st = i_status(iss)
        a = i_assignee(iss)
        aname = i_assignee_name(iss)
        init, cls = _avatar(a, aname)
        tasks.append({
            'key': iss['key'], 'summary': i_summary(iss), 'jira': st,
            'customs': [], 'canCustom': False,
            'assignee': {'name': aname, 'init': init, 'cls': cls},
            'due': i_duedate(iss) or '', 'dueDisp': i_duedate(iss) or '',
            'dueCls': '', 'overdue': False, 'stuck': False, 'dueWeek': False,
            'created': (i_created(iss) or '')[:10], 'createdDisp': (i_created(iss) or '')[:10] or '—',
            'nComments': i_comment_count(iss),
            'hasNote': canon_key(iss['key']) in note_idx,
            'jiraUrl': f'{JIRA_URL}/browse/{iss["key"]}',
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
    if jira_error:
        content = (
            '<div class="page-head"><div class="page-title">Tổng quan — Việc của tôi</div></div>'
            + _conn_error_card()
        )
        return _document_v2(content, nav_active, user, activities,
                            title='QA Workspace — Việc của tôi')

    tasks, meta = build_my_work_payload(data, cmap, notes)
    n_over, n_stuck, n_dueweek = meta['overdue'], meta['stuck'], meta['dueweek']

    # KPI = số tổng quan, đồng thời là nút lọc nhanh (bấm 1 cái -> board chỉ hiện card khớp;
    # bấm "Active của tôi" = về xem tất cả). Mặc định không lọc -> board hiện HẾT mọi cột.
    kpis = (
        '<div class="kpis" id="kpis">'
        f'<div class="kpi sel" data-f="all"><div class="label">Active của tôi</div><div class="value">{meta["active"]}</div></div>'
        f'<div class="kpi warn" data-f="overdue"><div class="label">Quá hạn</div><div class="value">{n_over}</div></div>'
        f'<div class="kpi stuck" data-f="stuck"><div class="label">Kẹt ≥ {STUCK_DAYS} ngày</div><div class="value">{n_stuck}</div></div>'
        f'<div class="kpi" data-f="dueweek"><div class="label">Due tuần này</div><div class="value">{n_dueweek}</div></div>'
        f'<div class="kpi success" data-f="done"><div class="label">Done</div><div class="value">{meta["done"]}</div></div>'
        '</div>'
    )
    # Board kiểu Jira: cột theo status, card render client-side từ qaData (#24 poll vá tại chỗ).
    board = '<div class="board" id="board"></div>'
    content = (
        '<div class="page-head"><div class="page-title">Tổng quan — Việc của tôi</div></div>'
        + kpis + board
        + _json_script('qaData', {'tasks': tasks, 'meta': meta})
    )
    return _document_v2(content, nav_active, user, activities, title='QA Workspace — Việc của tôi',
                        stale=stale, stale_note=_snap_note(data) if stale else '')
