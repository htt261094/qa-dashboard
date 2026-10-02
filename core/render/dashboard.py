"""Lens cá nhân "Việc của tôi" (`/my-work`) — 1 bảng + tabs + KPI + drawer.

Dashboard team (`render_admin_v2`, workload, metric bug) đã gỡ ở Decision #97 — app giờ
là của riêng 1 người nên chỉ còn lens cá nhân.
"""
from datetime import datetime, timedelta

from config import JIRA_URL, STUCK_DAYS
from issues import (parse_date, i_assignee, i_assignee_name, i_status, i_summary,
                    i_duedate, i_created, i_comment_count, days_overdue, is_stuck)
from custom_status import values_of

from render.base import _json_script
from render.shell import _avatar, _document_v2, _conn_error_card


def _snap_note(data):
    """Mô tả bản data đang hiện cho banner token hết hạn: 'dữ liệu lúc HH:MM dd/mm'."""
    fa = (data or {}).get('fetched_at')
    when = fa.strftime('%H:%M %d/%m') if hasattr(fa, 'strftime') else '?'
    return f'dữ liệu lúc {when}'



# ===== Lens cá nhân — payload =====
def build_my_work_payload(data, cmap):
    """Dựng data thuần cho lens "Việc của tôi" từ snapshot Jira đã scope.

    Chỉ tính toán, KHÔNG dựng markup. Trả `(tasks, meta)`:
    - tasks: list task active + done_week, mỗi task là dict field UI-agnostic.
    - meta : count KPI (active/overdue/stuck/dueweek/done + STUCK_DAYS).
    """
    active = data['active']
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
            'jiraUrl': f'{JIRA_URL}/browse/{iss["key"]}',
        })
    meta = {'active': len(active), 'overdue': n_over, 'stuck': n_stuck,
            'dueweek': n_dueweek, 'done': len(data['done_week']), 'stuckDays': STUCK_DAYS}
    return tasks, meta


# ===== Dashboard QA v2 (lens cá nhân — 1 bảng + tabs + KPI + drawer) =====
def render_qa_v2(data, activities, cmap, user, nav_active='mywork',
                 jira_error=False, stale=False):
    # Lens cá nhân = 100% data Jira (không có block local nào) -> Jira down thì cả vùng
    # nội dung báo lỗi, giữ skeleton sidebar/topbar.
    if jira_error:
        content = (
            '<div class="page-head"><div class="page-title">Tổng quan — Việc của tôi</div></div>'
            + _conn_error_card()
        )
        return _document_v2(content, nav_active, user, activities,
                            title='QA Workspace — Việc của tôi')

    tasks, meta = build_my_work_payload(data, cmap)
    n_over, n_stuck, n_dueweek = meta['overdue'], meta['stuck'], meta['dueweek']

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
        f'<div class="kpi success" data-f="done"><div class="label">Done</div><div class="value">{meta["done"]}</div></div>'
        '</div>'
    )
    table = (
        '<div class="card"><table><thead><tr>'
        '<th style="width:90px">ID</th><th>Tiêu đề</th><th style="width:160px">Trạng thái</th>'
        '<th style="width:150px">Người xử lý</th><th style="width:110px">Ngày tạo</th><th style="width:130px">Hạn chót</th>'
        '<th style="width:70px">Thao tác</th>'
        '</tr></thead><tbody id="rows"></tbody></table></div>'
        '<div class="pager-row"><div class="pager" id="pager"></div></div>'
    )
    content = (
        '<div class="page-head"><div class="page-title">Tổng quan — Việc của tôi</div></div>'
        + tabs + kpis + table
        + _json_script('qaData', {'tasks': tasks, 'meta': meta})
    )
    return _document_v2(content, nav_active, user, activities, title='QA Workspace — Việc của tôi',
                        stale=stale, stale_note=_snap_note(data) if stale else '')
