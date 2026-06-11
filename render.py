"""HTML rendering. CSS lives in styles.css and JS in app.js (loaded per-render, inlined).

All render_* functions return HTML fragments; render_page assembles the full document.
"""
import json
import math
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta

from config import SCRIPT_DIR, JIRA_URL, USERS, STUCK_DAYS, display_name, username_from_email
from issues import (parse_date, i_assignee, i_reporter, i_assignee_name, i_reporter_name,
                    i_status, i_summary, i_duedate,
                    i_created, i_resolved, i_updated, i_type, days_overdue, days_since_update,
                    is_stuck, esc, status_class, issue_link)
from pic import PIC_PEOPLE, load_pic
from docs import load_docs
from roadmap import (RM_STATUSES, RM_PEOPLE, load_roadmap, due_alerts,
                     task_done, task_started, plan_done, derive_plan_status)
from custom_status import CUSTOM_STATUSES, label_of, values_of
from task_link import tasks_of
from bug_log_store import POLL_SECONDS as BUG_LOG_POLL_SECONDS


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


def load_css_v2():
    """Read styles_v2.css per-render (shell UI v2 — dashboard QA + roadmap)."""
    try:
        return (SCRIPT_DIR / 'styles_v2.css').read_text(encoding='utf-8')
    except OSError:
        return ''


def load_js_v2():
    """Read app_v2.js per-render (shell UI v2)."""
    try:
        return (SCRIPT_DIR / 'app_v2.js').read_text(encoding='utf-8')
    except OSError:
        return ''


def _json_script(elem_id, obj):
    """Embed JSON an toàn vào <script type=application/json> (chống đóng tag sớm)."""
    return (f'<script type="application/json" id="{elem_id}">'
            + json.dumps(obj, ensure_ascii=False).replace('</', '<\\/') + '</script>')


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


# ===== Activity stream (feed từ Jira changelog; dismiss đồng bộ qua Jira user property) =====
def render_activities(activities, days=7, summary_map=None):
    if not activities:
        return ('<div class="section act-stream" id="actStream"><h2>🔔 Hoạt động <span class="count">0</span></h2>'
                f'<div class="empty">Không có hoạt động chưa đọc trong {days} ngày qua.</div></div>')

    def change_html(a):
        kind = a['kind']
        if kind == 'created':
            asg = a.get('assignee')
            tail = f' <span class="act-k act-k-asg">👤 {esc(asg)}</span>' if asg else ''
            return f'<span class="act-k act-k-new">🆕 Tạo mới</span>{tail}'
        if kind == 'comment':
            body = a.get('body') or ''
            snip = f' <span class="act-cmt-body" title="{esc(body)}">{esc(body)}</span>' if body else ''
            return f'<span class="act-k act-k-cmt">💬 comment</span>{snip}'
        if kind == 'status':
            old = a.get('old', a.get('old_status', ''))   # fallback: legacy entries used old_status/status
            new = a.get('new', a.get('status', ''))
            if not old and not new:
                return '<span class="act-k">🔄 Đổi trạng thái</span>'
            return (f'🔄 <span class="status {status_class(old)}">{esc(old)}</span>'
                    f'<span class="act-arrow">→</span>'
                    f'<span class="status {status_class(new)}">{esc(new)}</span>')
        if kind == 'assignee':
            return f'<span class="act-k act-k-asg">👤 Reassign</span> {esc(a.get("old","—"))} → {esc(a.get("new","—"))}'
        if kind == 'duedate':
            return f'<span class="act-k act-k-due">📅 Due</span> {esc(a.get("old",""))} → {esc(a.get("new",""))}'
        if kind == 'priority':
            return f'<span class="act-k act-k-prio">⚡ Priority</span> {esc(a.get("old",""))} → {esc(a.get("new",""))}'
        if kind == 'summary':
            return '<span class="act-k">✏️ Đổi tiêu đề</span>'
        if kind == 'custom_status':
            return f'<span class="act-k act-k-cstat">🏷 Nhãn nội bộ</span> {esc(a.get("new",""))}'
        return ''

    # group activities by task id (newest task first); each change = its own row
    groups, order = {}, []
    for a in activities[:300]:
        k = a['key']
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(a)

    blocks = []
    for k in order:
        items = sorted(groups[k], key=lambda a: a.get('when') or '')  # timeline cũ -> mới
        # summary lưu trong activity (rỗng với record cũ / custom status) -> fallback tra
        # từ data Jira hiện tại (summary_map) để header luôn có title.
        sm = esc(next((it.get('summary') for it in items if it.get('summary')), '')
                 or (summary_map or {}).get(k, ''))
        link = f'<a href="{JIRA_URL}/browse/{esc(k)}" target="_blank" class="key">{esc(k)}</a>'
        rows = ''
        for a in items:
            t = esc((a.get('when') or '')[5:16].replace('T', ' '))
            by = esc(a.get('author') or '—')
            aid = esc(a.get('id', ''))
            rows += (f'<div class="act-row" data-actid="{aid}"><span class="act-change">{change_html(a)}</span>'
                     f'<span class="act-by">{by}</span><span class="act-time">{t}</span>'
                     f'<button class="act-x" type="button" title="Bỏ qua mục này" '
                     f'onclick="dismissActivity(this)">✕</button></div>')
        blocks.append(
            f'<div class="act-group"><div class="act-g-head">{link}'
            f'<span class="act-sum" title="{sm}">{sm}</span></div>{rows}</div>'
        )
    total = sum(len(v) for v in groups.values())
    return (f'<div class="section act-stream" id="actStream"><h2>🔔 Hoạt động'
            f'<span class="act-head-right"><span class="count act-unread">{total}</span>'
            f'<button class="act-clear" id="actClear" type="button">✓ Đã đọc hết</button></span></h2>'
            f'<div class="act-list">{"".join(blocks)}</div></div>')


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


def render_chart_card(title, items, chart_key=''):
    wrap, legend = render_donut(items)
    total = sum(v for _, v, _ in items)
    attr = f' data-chart="{esc(chart_key)}"' if chart_key else ''
    if wrap is None:
        return f"""<div class="section"{attr}><h2>Pie Chart: All Tasks</h2>
        <div class="empty">Không có data để vẽ chart</div></div>"""
    return f"""<div class="section"{attr}>
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
    status_counts, assignee_counts, assignee_disp = {}, {}, {}
    for issue in active:
        s = i_status(issue) or '—'
        status_counts[s] = status_counts.get(s, 0) + 1
        a = i_assignee(issue)
        assignee_counts[a] = assignee_counts.get(a, 0) + 1
        assignee_disp[a] = i_assignee_name(issue)   # name/key -> tên hiển thị (đỡ lòi JIRAUSER)

    status_items = [(s, c, _jql_link(f' AND status = "{s}"')) for s, c in status_counts.items()]
    assignee_items = []
    for a, c in assignee_counts.items():
        if a == 'Unassigned':
            assignee_items.append(('Unassigned', c, _jql_link(' AND assignee is EMPTY')))
        else:
            assignee_items.append((assignee_disp.get(a, display_name(a)), c, _jql_link(f' AND assignee = {a}')))

    # Data nhúng để JS vẽ lại donut STATUS theo filter người (client-side, không thêm Jira call).
    cfg = {
        'active': [{'s': i_status(i) or '—', 'a': i_assignee(i), 'r': i_reporter(i)} for i in active],
        'jiraUrl': JIRA_URL,
        'base': f"assignee in ({','.join(USERS)}) AND statusCategory != Done",
        'palette': DONUT_PALETTE,
    }
    data_script = ('<script type="application/json" id="qaChartData">'
                   + json.dumps(cfg, ensure_ascii=False).replace('</', '<\\/')
                   + '</script>')

    return (
        render_chart_card('Issue count per Status', status_items, 'status') +
        render_chart_card('Issue count per Assignee', assignee_items, 'assignee') +
        data_script
    )


# ===== Workload matrix (expandable per person) =====
def render_workload(active, cmap=None):
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

    # Sort theo due date: gần nhất lên đầu; overdue (ngày quá khứ) tự nhiên ở trên cùng;
    # task không có due date xuống cuối (datetime.max).
    def task_key(iss):
        return parse_date(i_duedate(iss)) or datetime.max

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
                f'{_status_badge(iss, cmap)}'
                f'<span class="wl-task-sum">{esc(i_summary(iss))}</span>'
                f'<span class="wl-task-due">{esc(i_duedate(iss) or "—")}</span>'
                f'<span class="wl-task-stale">{(str(days_since_update(iss)) + "d kẹt") if is_stuck(iss) else ""}</span></div>'
                for iss in tlist
            )
        else:
            trows = '<div class="wl-empty">Không có task active</div>'

        rows.append(
            f'<details class="wl-item" data-user="{esc(u)}"><summary class="wl-row">'
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
def _person_attrs(issue):
    """data-* để client-side filter theo người (assignee/reporter)."""
    return f' data-assignee="{esc(i_assignee(issue))}" data-reporter="{esc(i_reporter(issue))}"'


# Các status chuẩn của workflow Bảo Kim (gộp vào menu thống nhất; chọn = đổi Jira thật nếu hợp lệ)
JIRA_STATUSES = ['TO DO', 'In Progress', 'PENDING', 'DONE', 'CANCELLED']


def _status_badge(issue, cmap=None):
    """Badge status hiển thị: task có custom -> badge tím gộp các nhãn (Jira gốc ở tooltip),
    không có -> badge status Jira thường. Dùng chung lens cá nhân (kèm caret) lẫn view admin
    (read-only) -> admin cũng THẤY nhãn nội bộ QA gắn, không chỉ ở activity feed."""
    st = i_status(issue)
    jira_esc = esc(st)
    cur = values_of((cmap or {}).get(issue['key']))
    if cur:
        labels = ', '.join(label_of(v) for v in cur)
        # tooltip liệt kê ĐỦ nhãn (badge có thể bị cắt … khi nhiều) + status Jira gốc
        tip = esc(f'Nhãn nội bộ ({len(cur)}): {labels} · Jira gốc: {st} (chỉ dashboard)')
        return (f'<span class="status status-custom" '
                f'title="{tip}">● {esc(labels)}</span>')
    return f'<span class="status {status_class(st)}">{jira_esc}</span>'


def status_control(issue, cmap=None):
    """Badge status + nút ▾ mở menu thống nhất. Nếu task có CUSTOM status -> badge hiện
    custom (kiểu status, màu tím ●), status Jira gốc nằm trong tooltip. Không custom -> status Jira.

    Menu (JS) gộp 2 nhóm: 'Status Jira' (chọn -> đổi Jira THẬT nếu nằm trong workflow) và
    'Custom status' (chọn -> chỉ đổi trên dashboard). data-jira = LUÔN là status Jira thật."""
    key = esc(issue['key'])
    st = i_status(issue)
    jira_esc = esc(st)
    cur = values_of((cmap or {}).get(issue['key']))
    badge = _status_badge(issue, cmap)
    return (
        f'{badge}'
        f'<button type="button" class="ustat-caret" data-key="{key}" '
        f'data-jira="{jira_esc}" data-cust="{esc(",".join(cur))}" '
        f'data-sum="{esc(i_summary(issue))}" '
        f'title="Đổi status Jira hoặc gắn custom status" onclick="openStatusMenu(this)">▾</button>'
    )


def summary_cell(issue, comment=True):
    """Ô Summary: dòng tiêu đề (truncate) + ô comment inline ngay dưới (luôn hiện, Enter gửi).
    Comment nằm DƯỚI summary (không thêm cột) -> bảng không tràn ngang ở block hẹp."""
    s = esc(i_summary(issue))
    inp = (f'<input class="cmt-inline" type="text" data-key="{esc(issue["key"])}" '
           f'placeholder="💬 Comment… (Enter)">' if comment else '')
    return f'<td class="summary-cell has-cmt" title="{s}"><div class="sum-text">{s}</div>{inp}</td>'


def _attn_row(issue, new_keys, extra_cells, cmap=None):
    new_cls = ' class="is-new"' if issue['key'] in new_keys else ''
    return (f'<tr{new_cls}{_person_attrs(issue)}><td>{issue_link(issue)}</td>'
            f'<td class="summary-cell" title="{esc(i_summary(issue))}">{esc(i_summary(issue))}</td>'
            f'<td>{esc(i_assignee_name(issue))}</td>'
            f'<td>{_status_badge(issue, cmap)}</td>'
            f'{extra_cells}</tr>')


def render_attention(active, new_keys, cmap=None):
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
                  f'<td>{esc(i_duedate(i) or "")}</td><td class="days-overdue">{d}d</td>', cmap)
                  for d, i in overdue)

    dw_head = '<th>Key</th><th>Summary</th><th>Assignee</th><th>Status</th><th>Due</th>'
    dw_body = ''.join(_attn_row(i, new_keys, f'<td>{esc(i_duedate(i) or "")}</td>', cmap)
                  for _, i in dueweek)

    st_head = '<th>Key</th><th>Summary</th><th>Assignee</th><th>Status</th><th>Kẹt</th>'
    st_body = ''.join(_attn_row(i, new_keys, f'<td class="days-overdue">{d}d</td>', cmap)
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
def render_new24(new24, new_keys, cmap=None):
    if not new24:
        return """<div class="section"><h2>🆕 New 24h (self-created by QA) <span class="count">0</span></h2>
        <div class="empty">Không có task mới do team tự tạo trong 24h</div></div>"""

    rows = []
    for issue in new24:
        new_cls = ' class="is-new"' if issue['key'] in new_keys else ''
        created = (i_created(issue) or '')[:16].replace('T', ' ')
        rows.append(f"""<tr{new_cls}{_person_attrs(issue)}>
            <td>{issue_link(issue)}</td>
            <td class="summary-cell" title="{esc(i_summary(issue))}">{esc(i_summary(issue))}</td>
            <td>{esc(i_reporter_name(issue))}</td>
            <td>{esc(i_assignee_name(issue))}</td>
            <td>{_status_badge(issue, cmap)}</td>
            <td>{esc(created)}</td>
        </tr>""")

    return f"""<div class="section" data-paginate="5">
        <h2>🆕 New 24h (self-created by QA) <span class="count">{len(new24)}</span></h2>
        <table>
            <thead><tr><th>Key</th><th>Summary</th><th>Reporter</th><th>Assignee</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    </div>"""


def render_done_week(done_week, new_keys, cmap=None):
    if not done_week:
        return """<div class="section"><h2>✅ Done (3 ngày) <span class="count">0</span></h2>
        <div class="empty">Chưa có task nào chuyển DONE trong 3 ngày</div></div>"""

    rows = []
    for issue in done_week[:50]:
        new_cls = ' class="is-new"' if issue['key'] in new_keys else ''
        # resolutiondate hay null (workflow không set resolution) -> fallback sang updated
        done_at = (i_resolved(issue) or i_updated(issue) or '')[:16].replace('T', ' ')
        rows.append(f"""<tr{new_cls}{_person_attrs(issue)}>
            <td>{issue_link(issue)}</td>
            <td class="summary-cell" title="{esc(i_summary(issue))}">{esc(i_summary(issue))}</td>
            <td>{esc(i_assignee_name(issue))}</td>
            <td>{_status_badge(issue, cmap)}</td>
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
def render_nav(active, user=None):
    """user = (email, is_admin) khi đăng nhập qua Cloudflare Access; None khi local."""
    def tab(href, key, label):
        cls = 'navtab active' if key == active else 'navtab'
        return f'<a class="{cls}" href="{href}">{label}</a>'
    # Chip = dropdown từ profile: Cài đặt PAT + Đăng xuất. Local dev (user=None) vẫn cho vào /settings.
    if user and user[0]:
        email, is_admin = user
        role = '<span class="nav-role nav-admin">Admin</span>' if is_admin else '<span class="nav-role">Chỉ xem</span>'
        chip = (
            '<div class="nav-user-menu" id="navUserMenu">'
            f'<button type="button" class="nav-user" id="navUserBtn" title="{esc(email)}">👤 {esc(email)} {role} ▾</button>'
            '<div class="nav-menu">'
            '<a class="nav-menu-item" href="/settings">⚙ Cài đặt PAT</a>'
            '<a class="nav-menu-item" href="/logout">↩ Đăng xuất</a>'
            '</div></div>'
        )
    else:
        chip = (
            '<div class="nav-user-menu" id="navUserMenu">'
            '<button type="button" class="nav-user" id="navUserBtn">👤 Local ▾</button>'
            '<div class="nav-menu">'
            '<a class="nav-menu-item" href="/settings">⚙ Cài đặt PAT</a>'
            '</div></div>'
        )
    # admin (hoặc local dev user=None) thấy đủ; QA thường KHÔNG thấy Báo cáo tuần (toàn team)
    # + "Việc của tôi" (QA `/` đã là lens cá nhân nên không cần tab riêng)
    is_admin = user[1] if (user and len(user) > 1) else True
    mywork_tab = tab('/my-work', 'mywork', '🙋 Việc của tôi') if is_admin else ''
    return ('<nav class="topnav">'
            + tab('/', 'dashboard', '📊 Tổng quan')
            + mywork_tab
            + tab('/roadmap', 'roadmap', '🗺 Roadmap')
            + tab('/docs', 'docs', '📚 Tài liệu')
            + chip
            + '</nav>')


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


def _jira_action_widgets():
    """Data status (cho JS dựng menu) + container menu status thống nhất (popup fixed).
    Comment giờ inline mỗi dòng (Enter để gửi) -> không còn modal."""
    # Status Jira KHÔNG inject tĩnh nữa: menu tự fetch transition khả dụng qua PAT của QA.
    return (f'<script>window.QA_CUSTOM_STATUSES={json.dumps(CUSTOM_STATUSES, ensure_ascii=False)};</script>'
            '<div class="umenu" id="statusMenu" hidden></div>')


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
{_jira_action_widgets()}
<script>{load_js()}</script>
</body></html>"""


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
    is_admin = bool(user and len(user) > 1 and user[1])
    status_line = ('<div class="set-state set-ok">✓ Bạn đã lưu PAT. Thao tác đổi status/comment sẽ ghi đúng tên bạn trên Jira.</div>'
                   if has_pat else
                   '<div class="set-state set-none">⚠ Bạn chưa lưu PAT. Hiện thao tác (nếu có) sẽ mang tên tài khoản chung.</div>')
    jira_base = esc(JIRA_URL)
    inner = (
        '<div class="page-head"><div>'
        '<h2 class="page-title">⚙ Cài đặt — Personal Access Token (PAT)</h2>'
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
        + (_render_drive_card(has_drive, auth_enabled) if is_admin else '')
        + '</div>'
    )
    return _document_v2(inner, 'settings', user, activities or [], title='Cài đặt — QA Dashboard')





# ===== Filter bar (client-side filter theo người: assignee / reporter) =====
def render_filterbar():
    opts = '<option value="">— Tất cả —</option>' + ''.join(
        f'<option value="{esc(u)}">{esc(display_name(u))}</option>' for u in USERS)
    return (
        '<div class="filterbar" id="filterBar">'
        '<span class="fb-label">👤 Lọc QA:</span>'
        f'<select id="personFilter">{opts}</select>'
        '<button type="button" class="fb-clear" id="filterClear" hidden>✕ Bỏ lọc</button>'
        '<span class="fb-count" id="filterCount"></span>'
        '</div>'
    )


# ===== QA personal lens (non-admin): blocks theo việc của chính mình =====
def render_kpis_personal(active, done_week):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    overdue = due_week = 0
    for i in active:
        d = parse_date(i_duedate(i))
        if not d:
            continue
        if d < today:
            overdue += 1
        elif week_start <= d < week_end:
            due_week += 1
    stuck = sum(1 for i in active if is_stuck(i))
    stuck_cls = 'warn' if stuck else ''
    return f"""<div class="kpis">
        <div class="kpi"><div class="label">Active của tôi</div><div class="value">{len(active)}</div></div>
        <div class="kpi warn"><div class="label">Overdue</div><div class="value">{overdue}</div></div>
        <div class="kpi {stuck_cls}"><div class="label">Kẹt ≥ {STUCK_DAYS} ngày</div><div class="value">{stuck}</div></div>
        <div class="kpi info"><div class="label">Due This Week</div><div class="value">{due_week}</div></div>
        <div class="kpi success"><div class="label">Done (3 ngày)</div><div class="value">{len(done_week)}</div></div>
    </div>"""


def _p_section(title, count, head, rows_html, empty_msg, cls=''):
    """1 block bảng cho lens cá nhân; có rows -> bật data-paginate=5 (filler giữ chiều cao)."""
    if rows_html:
        inner = f'<table><thead><tr>{head}</tr></thead><tbody>{rows_html}</tbody></table>'
        pag = ' data-paginate="5"'
    else:
        inner = f'<div class="empty">{empty_msg}</div>'
        pag = ''
    extra = f' {cls}' if cls else ''
    return (f'<div class="section{extra}"{pag}>'
            f'<h2>{title} <span class="count">{count}</span></h2>{inner}</div>')


def _p_base(issue, new_keys):
    """(new_cls, 2 ô Key+Summary) — Summary kèm ô comment inline bên dưới (không cột Assignee)."""
    new_cls = ' class="is-new"' if issue['key'] in new_keys else ''
    cells = f'<td>{issue_link(issue)}</td>{summary_cell(issue)}'
    return new_cls, cells


def render_personal(data, new_keys, activities, activity_days, cmap=None):
    active = data['active']
    summary_map = {i['key']: i_summary(i)
                   for bucket in (data['active'], data['new24'], data['done_week'])
                   for i in bucket}
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = today - timedelta(days=today.weekday()) + timedelta(days=7)

    def due_sort(i):   # gần nhất lên đầu; overdue (quá khứ) tự nổi trên; không due -> cuối
        return parse_date(i_duedate(i)) or datetime.max

    def inflight(i):   # In Progress + PENDING = đang xử lý / chờ (không phải TO DO)
        s = i_status(i).upper()
        return 'PROGRESS' in s or 'PEND' in s

    overdue = sorted((i for i in active if days_overdue(i) is not None),
                     key=lambda i: -(days_overdue(i) or 0))
    dueweek = sorted((i for i in active
                      if (d := parse_date(i_duedate(i))) and today <= d < week_end), key=due_sort)
    stuck = sorted((i for i in active if is_stuck(i)), key=lambda i: -(days_since_update(i) or 0))
    inprog = sorted((i for i in active if inflight(i)), key=due_sort)
    todo = sorted((i for i in active if not inflight(i)), key=due_sort)
    done = data['done_week']

    # Overdue / Due tuần / Kẹt -> gom vào 1 block 3 tab (như design gốc của admin)
    def p_panel(head, body, empty_msg):
        if not body:
            return f'<div class="empty">{empty_msg}</div>'
        return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'

    od_rows = ''
    for i in overdue:
        nc, base = _p_base(i, new_keys)
        od_rows += (f'<tr{nc}>{base}<td class="status-cell">{status_control(i, cmap)}</td>'
                    f'<td>{esc(i_duedate(i) or "")}</td><td class="days-overdue">{days_overdue(i)}d</td></tr>')
    dw_rows = ''
    for i in dueweek:
        nc, base = _p_base(i, new_keys)
        dw_rows += (f'<tr{nc}>{base}<td class="status-cell">{status_control(i, cmap)}</td>'
                    f'<td>{esc(i_duedate(i) or "")}</td></tr>')
    st_rows = ''
    for i in stuck:
        nc, base = _p_base(i, new_keys)
        st_rows += (f'<tr{nc}>{base}<td class="status-cell">{status_control(i, cmap)}</td>'
                    f'<td class="days-overdue">{days_since_update(i)}d</td></tr>')
    od_head = '<th>Key</th><th>Summary + comment</th><th>Trạng thái</th><th>Due</th><th>Trễ</th>'
    dw_head = '<th>Key</th><th>Summary + comment</th><th>Trạng thái</th><th>Due</th>'
    st_head = '<th>Key</th><th>Summary + comment</th><th>Trạng thái</th><th>Kẹt</th>'
    alerts = f"""<div class="section tabbed">
        <div class="tab-bar">
            <button class="tab active" type="button" data-tab="p-overdue">⚠ Overdue <span class="tab-count">{len(overdue)}</span></button>
            <button class="tab" type="button" data-tab="p-dueweek">📅 Due tuần <span class="tab-count">{len(dueweek)}</span></button>
            <button class="tab" type="button" data-tab="p-stuck">⏳ Kẹt ≥{STUCK_DAYS}d <span class="tab-count">{len(stuck)}</span></button>
        </div>
        <div class="tab-panel" data-paginate="5" data-panel="p-overdue">{p_panel(od_head, od_rows, 'Không có task quá hạn 🎉')}</div>
        <div class="tab-panel" data-paginate="5" data-panel="p-dueweek" hidden>{p_panel(dw_head, dw_rows, 'Không có task đến hạn trong tuần')}</div>
        <div class="tab-panel" data-paginate="5" data-panel="p-stuck" hidden>{p_panel(st_head, st_rows, f'Không có task kẹt ≥{STUCK_DAYS} ngày 👍')}</div>
    </div>"""
    # Đang làm (In Progress + PENDING)
    ip_rows = ''
    for i in inprog:
        nc, base = _p_base(i, new_keys)
        ip_rows += (f'<tr{nc}>{base}<td class="status-cell">{status_control(i, cmap)}</td>'
                    f'<td>{esc(i_duedate(i) or "—")}</td></tr>')
    ip = _p_section('🔵 Đang làm', len(inprog),
                    '<th>Key</th><th>Summary + comment</th><th>Trạng thái</th><th>Due</th>',
                    ip_rows, 'Không có task đang xử lý')
    # TO DO
    td_rows = ''
    for i in todo:
        nc, base = _p_base(i, new_keys)
        td_rows += (f'<tr{nc}>{base}<td class="status-cell">{status_control(i, cmap)}</td>'
                    f'<td>{esc(i_duedate(i) or "—")}</td></tr>')
    td = _p_section('📋 TO DO của tôi', len(todo),
                    '<th>Key</th><th>Summary + comment</th><th>Trạng thái</th><th>Due</th>',
                    td_rows, 'Không có task TO DO')
    # Done (3 ngày)
    dn_rows = ''
    for i in done[:50]:
        nc, base = _p_base(i, new_keys)
        done_at = (i_resolved(i) or i_updated(i) or '')[:16].replace('T', ' ')
        dn_rows += (f'<tr{nc}>{base}<td><span class="status {status_class(i_status(i))}">{esc(i_status(i))}</span></td>'
                    f'<td>{esc(done_at)}</td></tr>')
    dn = _p_section('✅ Done (3 ngày)', len(done),
                    '<th>Key</th><th>Summary + comment</th><th>Status</th><th>Cập nhật</th>',
                    dn_rows, 'Chưa có task nào chuyển DONE trong 3 ngày')

    # Layout cũ: 3 alert gom 1 block 3 tab; rồi eqrow-2 (Đang làm | Hoạt động) + (TO DO | Done).
    return (
        render_kpis_personal(active, done) +
        alerts +
        f'<div class="eqrow eqrow-2">{ip}{render_activities(activities, activity_days, summary_map)}</div>' +
        f'<div class="eqrow eqrow-2">{td}{dn}</div>'
    )


# ===== Full page =====
def render_page(data, new_keys, first_run, activities, activity_days=7, roadmap_data=None,
                user=None, custom_overlay=None):
    is_admin = user[1] if (user and len(user) > 1) else True

    # QA thường (non-admin): data đã auto-scope về chính họ -> UI v2 (shell sidebar Stitch).
    if not is_admin:
        return render_qa_v2(data, new_keys, activities, custom_overlay, user)

    # Admin -> new v2 dashboard (pills + member filter + 5-col table + KPI cards)
    return render_admin_v2(data, new_keys, activities, custom_overlay, user)


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


# ===================================================================
# ===== UI v2 (Stitch) — shell sidebar dùng cho dashboard QA + roadmap
# ===================================================================
_FONTS_V2 = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
    '&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'
    '<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:'
    'opsz,wght,FILL,GRAD@20,400,0,0" rel="stylesheet">'
)
_AV_CLS = ['av-a', 'av-b', 'av-c', 'av-d', 'av-e', 'av-f']


def _avatar(username, name):
    """(init, cls) cho avatar tròn: chữ cái đầu + màu theo index người trong USERS (ổn định)."""
    init = (name or username or '?').strip()[:1].upper() or '?'
    if username in USERS:
        cls = _AV_CLS[USERS.index(username) % len(_AV_CLS)]
    else:
        seed = sum(ord(c) for c in (username or name or 'x'))
        cls = _AV_CLS[seed % len(_AV_CLS)]
    return init, cls


def render_sidebar_v2(active, user):
    is_admin = user[1] if (user and len(user) > 1) else True
    email = user[0] if (user and user[0]) else ''

    def lnk(href, key, icon, label):
        cls = ' class="active"' if key == active else ''
        fill = " style=\"font-variation-settings:'FILL' 1\"" if key == active else ''
        return (f'<a{cls} href="{href}"><span class="material-symbols-rounded"{fill}>{icon}</span> {label}</a>')

    nav = lnk('/', 'dashboard', 'space_dashboard', 'Dashboard')
    if is_admin:
        nav += lnk('/my-work', 'mywork', 'person', 'Việc của tôi')
        nav += lnk('/leader-eval', 'leadereval', 'star', 'Đánh giá')
    nav += lnk('/roadmap', 'roadmap', 'map', 'Roadmap')
    nav += lnk('/bug-log', 'buglog', 'bug_report', 'Bugs')
    nav += lnk('/docs', 'docs', 'description', 'Tài liệu')

    uname = username_from_email(email) if (email and '@' in email) else None
    short = display_name(uname) if uname else (email.split('@')[0] if '@' in email else 'Local')
    init = (short[:2] or 'ME').upper()
    role = ('<span class="role-chip admin">Admin</span>' if is_admin
            else '<span class="role-chip">Chỉ xem</span>')
    sub = esc(email) if email else 'Local dev'
    logout = ('<div class="sep"></div>'
              '<a class="danger" href="/logout"><span class="material-symbols-rounded mi-sm">logout</span> Đăng xuất</a>'
              ) if email else ''
    return (
        '<aside class="sidebar">'
        '<div class="brand"><h1>QA Workspace</h1></div>'
        f'<nav class="nav">{nav}</nav>'
        '<div class="nav-foot">'
        '<div class="pmenu" id="pmenu">'
        '<button type="button" id="pmSettings"><span class="material-symbols-rounded mi-sm">key</span> Cài đặt PAT</button>'
        f'{logout}</div>'
        '<button class="profile" id="profileBtn">'
        f'<span class="av">{esc(init)}</span>'
        f'<span class="who"><b>{esc(short)} {role}</b><small>{sub}</small></span>'
        '<span class="material-symbols-rounded mi-sm">unfold_more</span>'
        '</button></div></aside>'
    )


def render_topbar_v2():
    return (
        '<div class="topbar">'
        '<div class="search"><span class="si material-symbols-rounded mi-sm">search</span>'
        '<input type="text" id="searchInp" placeholder="Tìm task, kế hoạch..."></div>'
        '<div class="top-right">'
        '<button class="topcreate" id="createSubBtn" title="Tạo sub-task QA dưới 1 Task-PTSP">'
        '<span class="material-symbols-rounded mi-sm">add</span> Tạo Sub-task</button>'
        '<button class="iconbtn" id="bellBtn" title="Thông báo">'
        '<span class="material-symbols-rounded mi-lg">notifications</span>'
        '<span class="badge-dot" id="bellDot" style="display:none">0</span></button>'
        '<button class="iconbtn" id="themeBtn" title="Đổi giao diện">'
        '<span class="material-symbols-rounded" id="themeIc">dark_mode</span></button>'
        '</div>'
        '<div class="notif" id="notif">'
        '<div class="notif-head"><h4>Thông báo</h4>'
        '<a class="notif-readall" id="notifReadAll">Đánh dấu tất cả đã đọc</a></div>'
        '<div class="notif-filters">'
        '<button class="nf-tab active" data-nf="all">Tất cả</button>'
        '<button class="nf-tab" data-nf="unread">Chưa đọc</button></div>'
        '<div class="notif-list" id="notifList"></div></div>'
        '</div>'
    )


def _settings_modal_v2():
    return (
        '<div class="overlay" id="setOverlay">'
        '<div class="modal">'
        '<div class="modal-head"><span class="material-symbols-rounded">key</span>'
        '<h3>Cài đặt PAT cá nhân</h3>'
        '<button type="button" class="x material-symbols-rounded" id="setClose">close</button></div>'
        '<div class="modal-body"><p class="modal-note">Thêm Personal Access Token để thao tác Jira '
        '(đổi status, comment) nhân danh chính bạn. Token được mã hoá khi lưu, không hiển thị lại.</p>'
        '<div class="field"><label>Personal Access Token</label>'
        '<div class="inp-wrap"><input type="password" id="patInp" placeholder="Dán PAT của bạn vào đây..." autocomplete="off" spellcheck="false">'
        '<button type="button" class="eye material-symbols-rounded mi-sm" id="patShowBtn">visibility</button></div></div></div>'
        '<div class="modal-foot">'
        '<button type="button" class="btn btn-danger" id="patDelBtn">Xoá PAT</button>'
        '<button type="button" class="btn btn-ghost" id="setCancel">Huỷ</button>'
        '<button type="button" class="btn btn-primary" id="patSaveBtn">Lưu</button>'
        '</div></div></div>'
    )


def _subtask_modal_v2():
    """Modal tạo Sub-task QA dưới 1 Task-PTSP (dùng chung mọi trang v2).
    Parent + Leader = type-ahead (gọi /search-parents, /search-people); assignee =
    dropdown 5 QA; start date default hôm nay. JS điều khiển trong app_v2.js."""
    today = datetime.now().strftime('%Y-%m-%d')
    opts = '<option value="">— Không gán —</option>'
    for u in USERS:
        opts += f'<option value="{esc(u)}">{esc(display_name(u))}</option>'
    return (
        '<div class="overlay" id="subOverlay"><div class="modal">'
        '<div class="modal-head"><span class="material-symbols-rounded">add_task</span>'
        '<h3>Tạo Sub-task</h3>'
        '<button type="button" class="x material-symbols-rounded" id="subClose">close</button></div>'
        '<div class="modal-body">'
        '<div class="mfield"><label>Task cha — Task-PTSP *</label>'
        '<div class="typeahead" id="subParentTA">'
        '<input type="text" id="subParentInp" placeholder="Gõ key hoặc tên Task-PTSP…" autocomplete="off" spellcheck="false">'
        '<div class="ta-results" id="subParentRes"></div></div>'
        '<div class="ta-chip" id="subParentChip" style="display:none"></div></div>'
        '<div class="mfield"><label>Tiêu đề *</label>'
        '<input type="text" id="subSummary" placeholder="Nội dung sub-task…" autocomplete="off"></div>'
        '<div class="mfield row2">'
        f'<div><label>Ngày bắt đầu *</label><input type="date" id="subStart" value="{today}"></div>'
        '<div><label>Hạn chót *</label><input type="date" id="subDue"></div>'
        '</div>'
        f'<div class="mfield"><label>Người xử lý</label><select id="subAssignee">{opts}</select></div>'
        '<div class="mfield"><label>Leader</label>'
        '<div class="typeahead" id="subLeaderTA">'
        '<input type="text" id="subLeaderInp" placeholder="Gõ tên leader…" autocomplete="off" spellcheck="false">'
        '<div class="ta-results" id="subLeaderRes"></div></div>'
        '<div class="ta-chip" id="subLeaderChip" style="display:none"></div></div>'
        '</div>'
        '<div class="modal-foot">'
        '<button type="button" class="btn btn-ghost" id="subCancel">Huỷ</button>'
        '<button type="button" class="btn btn-primary" id="subCreate">Tạo sub-task</button>'
        '</div></div></div>'
    )


def _document_v2(content_inner, active, user, activities, title='QA Suite'):
    """Shell sidebar Material-3 cho dashboard QA + roadmap. Inline styles_v2.css + app_v2.js.
    `activities` = feed (đã lọc dismissed) cho chuông notif (embed JSON #qaNotif)."""
    return f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
{_FONTS_V2}
<script>(function(){{try{{var t=localStorage.getItem('qa-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>{load_css_v2()}</style></head>
<body>
<div class="app">{render_sidebar_v2(active, user)}
<div class="main">{render_topbar_v2()}
<div class="content">{content_inner}</div></div></div>
{_settings_modal_v2()}
{_subtask_modal_v2()}
<div class="toast" id="toast"></div>
<div class="drawer-ov" id="drawerOv"></div><aside class="drawer" id="drawer"></aside>
{_json_script('qaNotif', activities)}
<script>window.__jiraBase={json.dumps(JIRA_URL)};</script>
<script>{load_js_v2()}</script>
</body></html>"""


# ===== Admin Dashboard v2 (team-wide — pills + member filter + 5-col table + KPI cards) =====
def render_admin_v2(data, new_keys, activities, cmap, user):
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
        # Status menu (drawer DOM nằm ở shell _document_v2 -> mọi trang dùng chung)
        '<div class="smenu" id="smenu"></div>'
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
                'qa': b.get('qa_pic', ''),
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


def render_roadmap_alerts(roadmap_data):
    """Block cảnh báo (dashboard admin shell cũ): plan roadmap chưa xong, hạn <= 2 tuần."""
    alerts = due_alerts(roadmap_data, within_days=14)
    if not alerts:
        return ''
    rows = []
    for a in alerts:
        d = a['days_left']
        if d < 0:
            tag = f'<span class="rm-al-tag rm-al-over">quá hạn {abs(d)}d</span>'
        elif d == 0:
            tag = '<span class="rm-al-tag rm-al-today">hôm nay</span>'
        else:
            tag = f'<span class="rm-al-tag rm-al-soon">còn {d}d</span>'
        rows.append(
            f'<div class="rm-al-row">{tag}'
            f'<span class="rm-al-title">{esc(a["title"])}</span>'
            f'<span class="rm-al-phase">{esc(a["plan"])}</span>'
            f'<span class="rm-al-due">📅 {esc(a["due"])}</span></div>'
        )
    return (f'<div class="section rm-alerts"><h2>🗺 Roadmap sắp đến hạn '
            f'<span class="count">{len(alerts)}</span></h2>'
            f'<div class="rm-al-list">{"".join(rows)}</div></div>')


def render_leader_eval_page(tasks, year, month, user=None, activities=None):
    from config import LEADER_EVAL_NUM_FIELD, LEADER_EVAL_TEXT_FIELD
    rows = []
    for issue in tasks:
        f = issue.get('fields', {})
        st = (f.get('status') or {}).get('name') or ''
        num_val = f.get(LEADER_EVAL_NUM_FIELD)
        num_str = str(num_val) if num_val is not None else ''
        text_val = f.get(LEADER_EVAL_TEXT_FIELD) or ''
        
        rows.append(f'''
        <tr>
            <td style="text-align:center"><input type="checkbox" class="eval-chk" value="{esc(issue['key'])}"></td>
            <td>{issue_link(issue)}</td>
            <td class="summary-cell" title="{esc(i_summary(issue))}">{esc(i_summary(issue))}</td>
            <td>{esc(i_assignee_name(issue))}</td>
            <td><span class="status {status_class(st)}">{esc(st)}</span></td>
            <td>{esc(num_str)}</td>
            <td><div style="max-height:60px;overflow-y:auto;font-size:0.9em">{esc(text_val)}</div></td>
        </tr>''')
    
    table_html = f'''
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
            {''.join(rows) if rows else '<tr><td colspan="7" class="empty">Không có task nào trong tháng này.</td></tr>'}
        </tbody>
    </table>
    </div>
    '''

    month_str = f"{year}-{month:02d}"
    inner = f'''
    <div class="page-head">
        <div>
            <h2 class="page-title">⭐ Đánh giá Task QA (Leader)</h2>
            <div class="page-sub">Lọc task theo tháng tạo, chọn nhiều task để chấm điểm và đánh giá hàng loạt. Lưu trực tiếp lên Jira.</div>
        </div>
        <div class="head-actions">
            <form action="/leader-eval" method="GET" style="display:flex; gap:8px; align-items:center;">
                <label><strong>Chọn tháng:</strong></label>
                <input type="month" name="month" value="{month_str}" class="set-input" style="width:150px; margin:0;" onchange="this.form.submit()">
            </form>
        </div>
    </div>
    
    <div style="display:flex; gap:20px; align-items:flex-start;">
        <div style="flex:1;">
            <div class="section">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <h3>Danh sách Task ({len(tasks)})</h3>
                    <span id="evalSelectedCount" style="color:#85b8ff; font-weight:bold;">0 task đang chọn</span>
                </div>
                {table_html}
            </div>
        </div>
        <div style="width:320px; position:sticky; top:20px;">
            <div class="card">
                <h3>Cập nhật hàng loạt</h3>
                <p class="set-note" style="margin-top:4px;">Chỉ cập nhật cho các task đang được chọn (tick) ở bên trái.</p>
                <div class="set-form" style="display:flex; flex-direction:column; gap:12px; margin-top:16px;">
                    <div>
                        <label style="display:block; margin-bottom:4px; font-weight:500;">Điểm (Số):</label>
                        <input type="number" id="evalNum" class="set-input" placeholder="VD: 8.5" step="0.1">
                        <small style="color:#a5adba;">Bỏ trống nếu không muốn đổi</small>
                    </div>
                    <div>
                        <label style="display:block; margin-bottom:4px; font-weight:500;">Đánh giá (Text):</label>
                        <textarea id="evalText" class="set-input" rows="4" placeholder="Nhận xét..."></textarea>
                        <small style="color:#a5adba;">Bỏ trống nếu không muốn đổi</small>
                    </div>
                    <button type="button" class="btn btn-primary" id="btnBatchEval" style="margin-top:8px;">Lưu lên Jira</button>
                    <div id="evalResult" style="margin-top:8px; font-size:0.9em; white-space:pre-wrap;"></div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            const checkAll = document.getElementById('evalCheckAll');
            const checkboxes = document.querySelectorAll('.eval-chk');
            const countLabel = document.getElementById('evalSelectedCount');
            const btn = document.getElementById('btnBatchEval');
            
            function updateCount() {{
                const sel = document.querySelectorAll('.eval-chk:checked').length;
                countLabel.textContent = sel + ' task đang chọn';
            }}
            
            if (checkAll) {{
                checkAll.addEventListener('change', function() {{
                    checkboxes.forEach(c => c.checked = this.checked);
                    updateCount();
                }});
            }}
            
            checkboxes.forEach(c => c.addEventListener('change', updateCount));
            
            if (btn) {{
                btn.addEventListener('click', async function() {{
                    const keys = Array.from(document.querySelectorAll('.eval-chk:checked')).map(c => c.value);
                    if (keys.length === 0) {{
                        alert('Vui lòng chọn ít nhất 1 task.');
                        return;
                    }}
                    const num_val = document.getElementById('evalNum').value;
                    const text_val = document.getElementById('evalText').value;
                    if (!num_val && !text_val) {{
                        alert('Vui lòng nhập điểm hoặc text.');
                        return;
                    }}
                    
                    const resDiv = document.getElementById('evalResult');
                    resDiv.textContent = 'Đang xử lý...';
                    resDiv.style.color = '#a5adba';
                    btn.disabled = true;
                    
                    try {{
                        const r = await fetch('/batch-eval', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{keys, num_val: num_val || null, text_val: text_val || null}})
                        }});
                        const data = await r.json();
                        resDiv.textContent = data.msg || (data.ok ? 'Thành công' : 'Lỗi');
                        resDiv.style.color = data.ok ? '#94C748' : '#F87168';
                        if (data.ok) {{
                            setTimeout(() => location.reload(), 2000);
                        }}
                    }} catch (e) {{
                        resDiv.textContent = 'Lỗi mạng: ' + e;
                        resDiv.style.color = '#F87168';
                    }} finally {{
                        btn.disabled = false;
                    }}
                }});
            }}
        }});
    </script>
    '''
    return _document_v2(inner, 'leadereval', user, activities or [], title=f'Đánh giá tháng {{month}}/{{year}} — QA Dashboard')


def render_error_page(msg):
    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><title>Error</title>
<script>(function(){{try{{var t=localStorage.getItem('qa-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>{load_css()}</style></head>
<body><div class="container"><header><h1>QA Team Dashboard</h1></header>
<div class="error"><strong>Lỗi pull data từ Jira:</strong><br>{esc(msg)}</div>
<p style="color:#6b778c;margin-top:16px">Check JIRA_URL, JIRA_PAT trong file .env. F5 để retry.</p>
</div></body></html>"""
