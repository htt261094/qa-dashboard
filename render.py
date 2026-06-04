"""HTML rendering. CSS lives in styles.css and JS in app.js (loaded per-render, inlined).

All render_* functions return HTML fragments; render_page assembles the full document.
"""
import math
import urllib.parse
from datetime import datetime, timedelta

from config import SCRIPT_DIR, JIRA_URL, USERS, STUCK_DAYS, display_name
from issues import (parse_date, i_assignee, i_reporter, i_status, i_summary, i_duedate,
                    i_created, i_resolved, i_updated, days_overdue, days_since_update,
                    is_stuck, esc, status_class, issue_link)
from pic import PIC_PEOPLE, load_pic


def load_css():
    """Read styles.css per-render (edits hot-reload without restart); inlined into <style>."""
    try:
        return (SCRIPT_DIR / 'styles.css').read_text(encoding='utf-8')
    except OSError:
        return ''


def load_js():
    """Read app.js per-render; inlined into <script>."""
    try:
        return (SCRIPT_DIR / 'app.js').read_text(encoding='utf-8')
    except OSError:
        return ''


# ===== KPI cards =====
def render_kpis(active, new24, done_week, created_week, resolved_week):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)

    overdue_count = 0
    due_week_count = 0
    no_due_count = 0
    for issue in active:
        d = parse_date(i_duedate(issue))
        if not d:
            no_due_count += 1
        elif d < today:
            overdue_count += 1
        elif week_start <= d < week_end:
            due_week_count += 1

    stuck_count = sum(1 for iss in active if is_stuck(iss))
    stuck_cls = 'warn' if stuck_count > 0 else ''
    io_cls = 'success' if resolved_week >= created_week else 'warn'   # vào > ra = backlog phình

    return f"""<div class="kpis">
        <div class="kpi"><div class="label">Total Active</div><div class="value">{len(active)}</div></div>
        <div class="kpi warn"><div class="label">Overdue</div><div class="value">{overdue_count}</div></div>
        <div class="kpi {stuck_cls}"><div class="label">Kẹt ≥ {STUCK_DAYS} ngày</div><div class="value">{stuck_count}</div></div>
        <div class="kpi info"><div class="label">Due This Week</div><div class="value">{due_week_count}</div></div>
        <div class="kpi {io_cls}"><div class="label">Vào / Ra (tuần)</div><div class="value"><span class="kpi-in">{created_week}</span> <span class="kpi-sep">/</span> <span class="kpi-out">{resolved_week}</span></div></div>
        <div class="kpi info"><div class="label">New 24h (Self)</div><div class="value">{len(new24)}</div></div>
        <div class="kpi success"><div class="label">Done (3 ngày)</div><div class="value">{len(done_week)}</div></div>
    </div>"""


# ===== Activity stream (notification, grouped by task, 1 action per row) =====
def render_activities(activities, first_run):
    if first_run:
        return ('<div class="section act-stream" id="actStream"><h2>🔔 Hoạt động <span class="count">—</span></h2>'
                '<div class="empty">Lần đầu chạy — hoạt động sẽ xuất hiện từ lần refresh sau.</div></div>')
    if not activities:
        return ('<div class="section act-stream" id="actStream"><h2>🔔 Hoạt động <span class="count">0</span></h2>'
                '<div class="empty">Không có thông báo mới.</div></div>')

    def change_html(a):
        kind = a['kind']
        if kind == 'created':
            return '<span class="act-k act-k-new">🆕 Tạo mới</span>'
        if kind == 'comment':
            return f'<span class="act-k act-k-cmt">💬 +{a.get("comment_delta", 1)} comment</span>'
        if kind == 'status':
            old = a.get('old', a.get('old_status', ''))   # fallback: legacy entries used old_status/status
            new = a.get('new', a.get('status', ''))
            if not old and not new:
                return '<span class="act-k">🔄 Đổi trạng thái</span>'
            return (f'🔄 <span class="status {status_class(old)}">{esc(old)}</span>'
                    f'<span class="act-arrow">→</span>'
                    f'<span class="status {status_class(new)}">{esc(new)}</span>')
        if kind == 'assignee':
            return f'<span class="act-k act-k-asg">👤 Reassign</span> {esc(display_name(a.get("old","")))} → {esc(display_name(a.get("new","")))}'
        if kind == 'duedate':
            return f'<span class="act-k act-k-due">📅 Due</span> {esc(a.get("old",""))} → {esc(a.get("new",""))}'
        if kind == 'priority':
            return f'<span class="act-k act-k-prio">⚡ Priority</span> {esc(a.get("old",""))} → {esc(a.get("new",""))}'
        if kind == 'summary':
            return '<span class="act-k">✏️ Đổi tiêu đề</span>'
        return ''

    # group activities by task id (newest task first); each change = its own row
    groups, order = {}, []
    for a in activities[:150]:
        k = a['key']
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(a)

    blocks = []
    for k in order[:40]:
        items = sorted(groups[k], key=lambda a: (a.get('detected') or '', a.get('updated') or ''))  # timeline
        sm = esc(items[0].get('summary', ''))
        link = f'<a href="{JIRA_URL}/browse/{esc(k)}" target="_blank" class="key">{esc(k)}</a>'
        rows = ''
        for a in items:
            t = esc((a.get('updated') or '')[5:16].replace('T', ' '))
            by = esc(a.get('author') or '—')
            rows += (f'<div class="act-row"><span class="act-change">{change_html(a)}</span>'
                     f'<span class="act-by">{by}</span><span class="act-time">{t}</span></div>')
        blocks.append(
            f'<div class="act-group"><div class="act-g-head">{link}'
            f'<span class="act-sum" title="{sm}">{sm}</span></div>{rows}</div>'
        )
    more = f'<div class="act-more">… và {len(order) - 40} task khác có thay đổi</div>' if len(order) > 40 else ''
    return (f'<div class="section act-stream" id="actStream"><h2>🔔 Hoạt động'
            f'<span class="act-head-right"><span class="count act-unread">{len(order)}</span>'
            f'<button class="act-clear" id="actClear" type="button">✓ Đã đọc</button></span></h2>'
            f'<div class="act-list">{"".join(blocks)}{more}</div></div>')


# ===== Pie / donut charts =====
# Atlassian-ish palette for chart slices (intentionally muted, matches Jira gadget)
DONUT_PALETTE = ['#94C748', '#85B8FF', '#F87168', '#F5CD47', '#9F8FEF',
                 '#6CC3E0', '#FEC57B', '#E774BB', '#8FB8B0', '#C0B6F2']


def _jql_link(extra):
    """Build a Jira issue-navigator URL filtered to active QA tasks + extra clause."""
    base = f"assignee in ({','.join(USERS)}) AND statusCategory != Done"
    return f"{JIRA_URL}/issues/?jql=" + urllib.parse.quote(base + extra)


def render_donut(items):
    """items: list of (label, value, href). Pure SVG donut, interactive via CSS/anchors."""
    items = [(l, v, h) for l, v, h in items if v > 0]
    items.sort(key=lambda x: -x[1])
    total = sum(v for _, v, _ in items)
    if total == 0:
        return None, []
    r, cx, cy, sw = 80, 100, 100, 40
    circ = 2 * math.pi * r
    segments, legend = [], []
    cum = 0.0
    for i, (label, value, href) in enumerate(items):
        frac = value / total
        pct = round(frac * 100)
        color = DONUT_PALETTE[i % len(DONUT_PALETTE)]
        dash = frac * circ
        offset = -cum * circ
        seg = (
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
            f'stroke-width="{sw}" stroke-dasharray="{dash:.2f} {circ - dash:.2f}" '
            f'stroke-dashoffset="{offset:.2f}" transform="rotate(-90 {cx} {cy})" '
            f'data-pct="{pct}" data-label="{esc(label)}">'
            f'<title>{esc(label)}: {value} ({pct}%)</title></circle>'
        )
        if href:
            seg = f'<a href="{href}" target="_blank">{seg}</a>'
        segments.append(seg)
        lbl = f'<span class="legend-swatch" style="background:{color}"></span>{esc(label)}'
        if href:
            lbl = f'<a class="legend-lbl" href="{href}" target="_blank" title="Mở trong Jira">{lbl}</a>'
        legend.append(f'<tr><td>{lbl}</td><td class="legend-val">{value}</td></tr>')
        cum += frac
    svg = f'<svg viewBox="0 0 200 200" class="donut">{"".join(segments)}</svg>'
    wrap = (
        f'<div class="donut-wrap">{svg}'
        f'<div class="donut-center"><span class="donut-pct">{total}</span>'
        f'<span class="donut-lbl">issues</span></div></div>'
    )
    return wrap, legend


def render_chart_card(title, items):
    wrap, legend = render_donut(items)
    total = sum(v for _, v, _ in items)
    if wrap is None:
        return """<div class="section"><h2>Pie Chart: All Tasks</h2>
        <div class="empty">Không có data để vẽ chart</div></div>"""
    return f"""<div class="section">
        <h2>Pie Chart: All Tasks</h2>
        <div class="chart-card">
            {wrap}
            <div class="chart-legend">
                <div class="legend-title">{esc(title)}<br><strong>Total Issues: {total}</strong></div>
                <table><tbody>{''.join(legend)}</tbody></table>
            </div>
        </div>
    </div>"""


def render_charts(active):
    status_counts, assignee_counts = {}, {}
    for issue in active:
        s = i_status(issue) or '—'
        status_counts[s] = status_counts.get(s, 0) + 1
        a = i_assignee(issue)
        assignee_counts[a] = assignee_counts.get(a, 0) + 1

    status_items = [(s, c, _jql_link(f' AND status = "{s}"')) for s, c in status_counts.items()]
    assignee_items = []
    for a, c in assignee_counts.items():
        if a == 'Unassigned':
            assignee_items.append(('Unassigned', c, _jql_link(' AND assignee is EMPTY')))
        else:
            assignee_items.append((display_name(a), c, _jql_link(f' AND assignee = {a}')))

    return (
        render_chart_card('Issue count per Status', status_items) +
        render_chart_card('Issue count per Assignee', assignee_items)
    )


# ===== Workload matrix (expandable per person) =====
def render_workload(active):
    statuses = ['TO DO', 'In Progress', 'PENDING']
    matrix = {u: {s: 0 for s in statuses} for u in USERS}
    totals = {u: 0 for u in USERS}
    tasks_by_user = {u: [] for u in USERS}

    for issue in active:
        a = i_assignee(issue)
        s = i_status(issue)
        if a in matrix:
            totals[a] += 1
            tasks_by_user[a].append(issue)
            if s in matrix[a]:
                matrix[a][s] += 1
            else:
                # Unknown status -> bucket by name heuristic
                if 'PROGRESS' in s.upper():
                    matrix[a]['In Progress'] += 1
                elif 'PEND' in s.upper():
                    matrix[a]['PENDING'] += 1
                else:
                    matrix[a]['TO DO'] += 1

    status_order = {'TO DO': 0, 'In Progress': 1, 'PENDING': 2}

    def task_key(iss):
        return (status_order.get(i_status(iss), 3), parse_date(i_duedate(iss)) or datetime.max)

    rows = ['<div class="wl-head wl-row"><span>Assignee</span>'
            '<span class="num">TO DO</span><span class="num">In Progress</span>'
            '<span class="num">PENDING</span><span class="num">Total</span></div>']
    for u in USERS:
        total = totals[u]
        if total >= 15:
            badge = '<span class="badge badge-overload">⚠ QUÁ TẢI</span>'
        elif total >= 5:
            badge = '<span class="badge badge-ok">● OK</span>'
        else:
            badge = '<span class="badge badge-light">○ NHẸ</span>'
        cells = ''.join(f'<span class="num">{matrix[u][s]}</span>' for s in statuses)

        tlist = sorted(tasks_by_user[u], key=task_key)
        if tlist:
            trows = ''.join(
                f'<div class="wl-task">{issue_link(iss)}'
                f'<span class="status {status_class(i_status(iss))}">{esc(i_status(iss))}</span>'
                f'<span class="wl-task-sum">{esc(i_summary(iss))}</span>'
                f'<span class="wl-task-due">{esc(i_duedate(iss) or "—")}</span>'
                f'<span class="wl-task-stale">{(str(days_since_update(iss)) + "d kẹt") if is_stuck(iss) else ""}</span></div>'
                for iss in tlist
            )
        else:
            trows = '<div class="wl-empty">Không có task active</div>'

        rows.append(
            f'<details class="wl-item"><summary class="wl-row">'
            f'<span class="wl-name">{esc(display_name(u))}</span>{cells}'
            f'<span class="num wl-total">{total}{badge}</span></summary>'
            f'<div class="wl-tasks">{trows}</div></details>'
        )

    grand_total = sum(totals.values())
    return f"""<div class="section">
        <h2>Workload Matrix <span class="count">{grand_total} active</span></h2>
        <div class="wl">{''.join(rows)}</div>
    </div>"""


# ===== Attention block (tabbed: Overdue / Due tuần / Kẹt) =====
def _attn_row(issue, new_keys, extra_cells):
    new_cls = ' class="is-new"' if issue['key'] in new_keys else ''
    return (f'<tr{new_cls}><td>{issue_link(issue)}</td>'
            f'<td class="summary-cell" title="{esc(i_summary(issue))}">{esc(i_summary(issue))}</td>'
            f'<td>{esc(display_name(i_assignee(issue)))}</td>'
            f'<td><span class="status {status_class(i_status(issue))}">{esc(i_status(issue))}</span></td>'
            f'{extra_cells}</tr>')


def render_attention(active, new_keys):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = today - timedelta(days=today.weekday()) + timedelta(days=7)

    overdue = sorted(((days_overdue(i), i) for i in active if days_overdue(i) is not None),
                     key=lambda x: -x[0])
    dueweek = sorted(((parse_date(i_duedate(i)), i) for i in active
                      if parse_date(i_duedate(i)) and today <= parse_date(i_duedate(i)) < week_end),
                     key=lambda x: x[0])
    stuck = sorted(((days_since_update(i), i) for i in active if is_stuck(i)),
                   key=lambda x: -(x[0] or 0))

    def table(head, body, empty_msg):
        if not body:
            return f'<div class="empty">{empty_msg}</div>'
        return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    od_head = '<th>Key</th><th>Summary</th><th>Assignee</th><th>Status</th><th>Due</th><th>Trễ</th>'
    od_body = ''.join(_attn_row(i, new_keys,
                  f'<td>{esc(i_duedate(i) or "")}</td><td class="days-overdue">{d}d</td>')
                  for d, i in overdue)

    dw_head = '<th>Key</th><th>Summary</th><th>Assignee</th><th>Status</th><th>Due</th>'
    dw_body = ''.join(_attn_row(i, new_keys, f'<td>{esc(i_duedate(i) or "")}</td>')
                  for _, i in dueweek)

    st_head = '<th>Key</th><th>Summary</th><th>Assignee</th><th>Status</th><th>Kẹt</th>'
    st_body = ''.join(_attn_row(i, new_keys, f'<td class="days-overdue">{d}d</td>')
                  for d, i in stuck)

    return f"""<div class="section tabbed">
        <div class="tab-bar">
            <button class="tab active" type="button" data-tab="overdue">⚠ Overdue <span class="tab-count">{len(overdue)}</span></button>
            <button class="tab" type="button" data-tab="dueweek">📅 Due tuần <span class="tab-count">{len(dueweek)}</span></button>
            <button class="tab" type="button" data-tab="stuck">⏳ Kẹt ≥{STUCK_DAYS}d <span class="tab-count">{len(stuck)}</span></button>
        </div>
        <div class="tab-panel" data-paginate="5" data-panel="overdue">{table(od_head, od_body, 'Không có task quá hạn 🎉')}</div>
        <div class="tab-panel" data-paginate="5" data-panel="dueweek" hidden>{table(dw_head, dw_body, 'Không có task đến hạn trong tuần')}</div>
        <div class="tab-panel" data-paginate="5" data-panel="stuck" hidden>{table(st_head, st_body, f'Không có task kẹt ≥{STUCK_DAYS} ngày 👍')}</div>
    </div>"""


# ===== New 24h / Done buckets =====
def render_new24(new24, new_keys):
    if not new24:
        return """<div class="section"><h2>🆕 New 24h (self-created by QA) <span class="count">0</span></h2>
        <div class="empty">Không có task mới do team tự tạo trong 24h</div></div>"""

    rows = []
    for issue in new24:
        new_cls = ' class="is-new"' if issue['key'] in new_keys else ''
        created = (i_created(issue) or '')[:16].replace('T', ' ')
        rows.append(f"""<tr{new_cls}>
            <td>{issue_link(issue)}</td>
            <td class="summary-cell" title="{esc(i_summary(issue))}">{esc(i_summary(issue))}</td>
            <td>{esc(display_name(i_reporter(issue)))}</td>
            <td>{esc(display_name(i_assignee(issue)))}</td>
            <td><span class="status {status_class(i_status(issue))}">{esc(i_status(issue))}</span></td>
            <td>{esc(created)}</td>
        </tr>""")

    return f"""<div class="section" data-paginate="5">
        <h2>🆕 New 24h (self-created by QA) <span class="count">{len(new24)}</span></h2>
        <table>
            <thead><tr><th>Key</th><th>Summary</th><th>Reporter</th><th>Assignee</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    </div>"""


def render_done_week(done_week, new_keys):
    if not done_week:
        return """<div class="section"><h2>✅ Done (3 ngày) <span class="count">0</span></h2>
        <div class="empty">Chưa có task nào chuyển DONE trong 3 ngày</div></div>"""

    rows = []
    for issue in done_week[:50]:
        new_cls = ' class="is-new"' if issue['key'] in new_keys else ''
        # resolutiondate hay null (workflow không set resolution) -> fallback sang updated
        done_at = (i_resolved(issue) or i_updated(issue) or '')[:16].replace('T', ' ')
        rows.append(f"""<tr{new_cls}>
            <td>{issue_link(issue)}</td>
            <td class="summary-cell" title="{esc(i_summary(issue))}">{esc(i_summary(issue))}</td>
            <td>{esc(display_name(i_assignee(issue)))}</td>
            <td><span class="status {status_class(i_status(issue))}">{esc(i_status(issue))}</span></td>
            <td>{esc(done_at)}</td>
        </tr>""")

    return f"""<div class="section" data-paginate="5">
        <h2>✅ Done (3 ngày) <span class="count">{len(done_week)}</span></h2>
        <table>
            <thead><tr><th>Key</th><th>Summary</th><th>Assignee</th><th>Status</th><th>Cập nhật</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    </div>"""


# ===== PIC modal =====
def _pic_options(pic):
    opts = ''
    if pic and pic not in PIC_PEOPLE:
        opts += f'<option value="{esc(pic)}" selected>{esc(pic)}</option>'
    for p in PIC_PEOPLE:
        sel = ' selected' if p == pic else ''
        opts += f'<option value="{esc(p)}"{sel}>{esc(p)}</option>'
    return opts


def _pic_row_html(flow, pic):
    return (
        '<tr class="pic-row">'
        f'<td><div class="pic-flow" contenteditable="true">{esc(flow)}</div></td>'
        f'<td class="pic-pic-cell"><select class="pic-select">{_pic_options(pic)}</select></td>'
        '<td class="pic-act"><button type="button" class="pic-del-row" title="Xoá luồng" aria-label="Xoá luồng">×</button></td>'
        '</tr>'
    )


def _pic_group_head_html(group):
    return (
        '<tr class="pic-grp">'
        f'<td colspan="2"><div class="pic-grp-name" contenteditable="true">{esc(group)}</div></td>'
        '<td class="pic-act">'
        '<button type="button" class="pic-add-row" title="Thêm luồng vào nhóm" aria-label="Thêm luồng">+</button>'
        '<button type="button" class="pic-del-grp" title="Xoá cả nhóm" aria-label="Xoá cả nhóm">×</button>'
        '</td></tr>'
    )


def render_pic_modal(pic_data):
    body = []
    for g in pic_data:
        body.append(_pic_group_head_html(g.get('group', '')))
        for r in (g.get('rows') or []):
            body.append(_pic_row_html(r.get('flow', ''), r.get('pic', '')))

    return f"""
<button class="pic-fab" id="picFab" title="PIC theo line dự án" aria-label="PIC theo line dự án">👥</button>
<div class="pic-overlay" id="picOverlay">
  <div class="pic-modal" role="dialog" aria-label="PIC theo line dự án">
    <div class="pic-modal-head">
      <h3>👥 PIC theo line dự án</h3>
      <div style="display:flex;align-items:center;gap:16px">
        <span class="pic-save-status" id="picStatus"></span>
        <button class="pic-close" id="picClose" aria-label="Đóng">×</button>
      </div>
    </div>
    <div class="pic-body">
      <table class="pic-table">
        <thead><tr><th>Dự án - Luồng</th><th>Người phụ trách</th><th class="pic-act"></th></tr></thead>
        <tbody>{''.join(body)}</tbody>
      </table>
      <div class="pic-add-grp-wrap"><button type="button" class="pic-add-grp">+ Thêm nhóm</button></div>
      <p class="pic-hint">Bấm vào text để sửa · di chuột vào dòng/nhóm để hiện nút thêm <b>+</b> / xoá <b>×</b> · tự động lưu.</p>
    </div>
    <template id="picRowTpl">{_pic_row_html('', '')}</template>
    <template id="picGrpTpl">{_pic_group_head_html('')}</template>
  </div>
</div>"""


# ===== Shared shell + top nav =====
def render_nav(active):
    def tab(href, key, label):
        cls = 'navtab active' if key == active else 'navtab'
        return f'<a class="{cls}" href="{href}">{label}</a>'
    return ('<nav class="topnav">'
            + tab('/', 'dashboard', '📊 Tổng quan')
            + tab('/report', 'report', '📋 Báo cáo tuần')
            + '</nav>')


def _document(inner):
    """Wrap page-body HTML in the full document (css/theme-init/fabs/pic-modal/js)."""
    return f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8">
<title>QA Team Dashboard — Bảo Kim</title>
<script>(function(){{try{{var t=localStorage.getItem('qa-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>{load_css()}</style></head>
<body>
<div class="container">{inner}</div>
<button class="theme-fab" id="themeFab" title="Đổi light / dark" aria-label="Đổi theme">🌙</button>
{render_pic_modal(load_pic())}
<script>{load_js()}</script>
</body></html>"""


# ===== Weekly report (separate /report view) =====
def _project_of(key):
    """Project key prefix from an issue key: 'PSIT1H26-123' -> 'PSIT1H26'."""
    return key.rsplit('-', 1)[0] if '-' in key else key


def _rpt_zero():
    return {'active': 0, 'todo': 0, 'prog': 0, 'pend': 0, 'other': 0,
            'overdue': 0, 'stuck': 0, 'done': 0, 'od_list': [], 'st_list': []}


def _rag(d):
    """Red if any overdue/stuck; Amber if half-or-more still TO DO; else Green."""
    if d['overdue'] or d['stuck']:
        return ('R', '🔴', 'Có task overdue/kẹt')
    if d['active'] == 0 and d['done'] == 0:
        return ('G', '⚪', 'Không có task')
    if d['active'] and d['todo'] * 2 >= d['active']:
        return ('A', '🟡', 'Phần lớn chưa khởi động')
    return ('G', '🟢', 'On track')


def _rpt_collect(data):
    proj = {}
    for iss in data['active']:
        d = proj.setdefault(_project_of(iss['key']), _rpt_zero())
        d['active'] += 1
        s = (i_status(iss) or '').upper()
        if s == 'TO DO':
            d['todo'] += 1
        elif 'PROGRESS' in s:
            d['prog'] += 1
        elif 'PEND' in s:
            d['pend'] += 1
        else:
            d['other'] += 1
        od = days_overdue(iss)
        if od is not None:
            d['overdue'] += 1
            d['od_list'].append((od, iss))
        if is_stuck(iss):
            d['stuck'] += 1
            d['st_list'].append((days_since_update(iss) or 0, iss))
    for iss in data['done_week']:
        proj.setdefault(_project_of(iss['key']), _rpt_zero())['done'] += 1
    return proj


def _comp_bar(d):
    """Horizontal stacked bar of status composition (print-friendly CSS, no SVG)."""
    if not d['active']:
        return '<div class="compbar empty-bar"></div>'
    segs = []
    for cls, n, lbl in (('seg-todo', d['todo'], 'TO DO'), ('seg-prog', d['prog'], 'In Progress'),
                        ('seg-pend', d['pend'], 'PENDING'), ('seg-other', d['other'], 'Khác')):
        if n:
            segs.append(f'<span class="{cls}" style="width:{n / d["active"] * 100:.1f}%" title="{lbl}: {n}"></span>')
    return f'<div class="compbar">{"".join(segs)}</div>'


def _report_chart(title, items):
    wrap, legend = render_donut(items)
    if wrap is None:
        return f'<div class="rpt-chart"><h3>{esc(title)}</h3><div class="empty">Không có data</div></div>'
    return (f'<div class="rpt-chart"><h3>{esc(title)}</h3>'
            f'<div class="chart-card">{wrap}'
            f'<div class="chart-legend"><table><tbody>{"".join(legend)}</tbody></table></div></div></div>')


def render_report_page(data):
    proj = _rpt_collect(data)
    fetched = data['fetched_at'].strftime('%Y-%m-%d %H:%M')
    sev = {'R': 0, 'A': 1, 'G': 2}
    items = []
    for name, d in proj.items():
        items.append((name, d, _rag(d)))
    items.sort(key=lambda x: (sev[x[2][0]], -x[1]['active']))

    rows = []
    for name, d, (code, dot, why) in items:
        rows.append(
            f'<tr class="rag-row rag-{code}"><td class="rpt-proj">{esc(name)}</td>'
            f'<td class="num">{d["done"] or ""}</td><td class="num"><strong>{d["active"]}</strong></td>'
            f'<td class="num">{d["todo"] or ""}</td><td class="num">{d["prog"] or ""}</td><td class="num">{d["pend"] or ""}</td>'
            f'<td class="num rpt-od">{d["overdue"] or ""}</td><td class="num rpt-st">{d["stuck"] or ""}</td>'
            f'<td class="rpt-bar">{_comp_bar(d)}</td>'
            f'<td class="rpt-rag" title="{esc(why)}">{dot}</td></tr>'
        )
    empty_row = '<tr><td colspan="10" class="empty">Không có task active</td></tr>'
    table = (f'<table class="rpt-table"><thead><tr>'
             f'<th>Dự án</th><th class="num">Done</th><th class="num">Đang chạy</th>'
             f'<th class="num">TO DO</th><th class="num">In Prog</th><th class="num">PEND</th>'
             f'<th class="num">Overdue</th><th class="num">Kẹt</th><th>Phân bổ</th><th>RAG</th>'
             f'</tr></thead><tbody>{"".join(rows) or empty_row}</tbody></table>')

    proj_items = [(n, d['active'], _jql_link(f' AND project = {n}')) for n, d, _ in items if d['active']]
    st_total = {'TO DO': 0, 'In Progress': 0, 'PENDING': 0}
    for _, d, _ in items:
        st_total['TO DO'] += d['todo']
        st_total['In Progress'] += d['prog']
        st_total['PENDING'] += d['pend']
    status_items = [(s, c, _jql_link(f' AND status = "{s}"')) for s, c in st_total.items() if c]
    charts = (f'<div class="report-charts">'
              f'{_report_chart("Khối lượng theo dự án", proj_items)}'
              f'{_report_chart("Trạng thái (đang chạy)", status_items)}</div>')

    notes = []
    for name, d, _ in items:
        if not d['od_list'] and not d['st_list']:
            continue
        lines = []
        for od, iss in sorted(d['od_list'], key=lambda x: -x[0]):
            lines.append(f'<li><span class="rpt-tag tag-od">trễ {od}d</span> {issue_link(iss)} '
                         f'<span class="rpt-li-sum">{esc(i_summary(iss))}</span> '
                         f'<span class="rpt-li-asg">{esc(display_name(i_assignee(iss)))}</span></li>')
        for st, iss in sorted(d['st_list'], key=lambda x: -x[0]):
            lines.append(f'<li><span class="rpt-tag tag-st">kẹt {st}d</span> {issue_link(iss)} '
                         f'<span class="rpt-li-sum">{esc(i_summary(iss))}</span> '
                         f'<span class="rpt-li-asg">{esc(display_name(i_assignee(iss)))}</span></li>')
        notes.append(f'<div class="rpt-note"><h4>{esc(name)}</h4><ul>{"".join(lines)}</ul></div>')
    notes_html = ('<div class="section"><h2>📌 Điểm cần lưu ý (overdue / kẹt)</h2>'
                  + (''.join(notes) if notes else '<div class="empty">Không có task overdue hay kẹt 🎉</div>')
                  + '</div>')

    legend_note = ('<p class="rpt-legend-note">🔴 có overdue/kẹt · 🟡 phần lớn chưa khởi động · 🟢 on track'
                   ' · thanh phân bổ: <span class="lg seg-todo"></span> TO DO'
                   ' <span class="lg seg-prog"></span> In Progress <span class="lg seg-pend"></span> PENDING</p>')

    body = (
        render_nav('report') +
        '<header class="report-head"><div><h1>📋 Báo cáo tuần — QA</h1>'
        f'<div class="meta">Chốt số: <strong>{fetched}</strong> · gom theo project key · '
        f'Tracking: {esc(", ".join(display_name(u) for u in USERS))}</div></div>'
        '<button class="report-print-btn" type="button" onclick="window.print()">🖨 In báo cáo</button></header>'
        + render_kpis(data['active'], data['new24'], data['done_week'], data['created_week'], data['resolved_week'])
        + charts
        + f'<div class="section"><h2>Tổng quan theo dự án</h2>{table}{legend_note}</div>'
        + notes_html
    )
    return _document(body)


# ===== Full page =====
def render_page(data, new_keys, first_run, activities):
    fetched = data['fetched_at'].strftime('%Y-%m-%d %H:%M:%S')

    left_col = (
        render_done_week(data['done_week'], new_keys) +
        render_new24(data['new24'], new_keys) +
        render_attention(data['active'], new_keys)
    )
    right_col = (
        render_charts(data['active']) +          # status chart -> person chart
        render_workload(data['active'])
    )
    body = (
        render_kpis(data['active'], data['new24'], data['done_week'], data['created_week'], data['resolved_week']) +
        render_activities(activities, first_run) +
        f'<div class="grid-2col"><div class="col">{left_col}</div>'
        f'<div class="col">{right_col}</div></div>'
    )

    first_run_note = ''
    if first_run:
        first_run_note = '<div class="first-run">📍 First run — đã ghi nhận snapshot ban đầu. F5 lần sau sẽ highlight task mới phát sinh.</div>'

    new_count = len(new_keys)
    new_badge = f' · <strong style="color:#ff8b00">{new_count} task mới từ lần refresh trước</strong>' if new_count > 0 else ''

    header = (f'<header><h1>QA Team Dashboard</h1>'
              f'<div class="meta">Last refresh: <strong>{fetched}</strong>{new_badge} · '
              f'<kbd>F5</kbd> refresh · <button id="autoBtn" class="auto-btn" type="button"></button></div></header>')
    footer = (f'<p style="text-align:center;color:#6b778c;font-size:12px;margin-top:30px">'
              f'Data live từ {esc(JIRA_URL)} · Tracking: {esc(", ".join(display_name(u) for u in USERS))}</p>')

    inner = render_nav('dashboard') + header + first_run_note + body + footer
    return _document(inner)


def render_error_page(msg):
    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><title>Error</title>
<script>(function(){{try{{var t=localStorage.getItem('qa-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>{load_css()}</style></head>
<body><div class="container"><header><h1>QA Team Dashboard</h1></header>
<div class="error"><strong>Lỗi pull data từ Jira:</strong><br>{esc(msg)}</div>
<p style="color:#6b778c;margin-top:16px">Check JIRA_URL, JIRA_PAT trong file .env. F5 để retry.</p>
</div></body></html>"""
