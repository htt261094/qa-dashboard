"""HTML rendering. CSS lives in styles.css and JS in app.js (loaded per-render, inlined).

All render_* functions return HTML fragments; render_page assembles the full document.
"""
import json
import math
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta

from config import SCRIPT_DIR, JIRA_URL, USERS, STUCK_DAYS, display_name
from issues import (parse_date, i_assignee, i_reporter, i_status, i_summary, i_duedate,
                    i_created, i_resolved, i_updated, i_type, days_overdue, days_since_update,
                    is_stuck, esc, status_class, issue_link)
from pic import PIC_PEOPLE, load_pic
from docs import load_docs
from roadmap import RM_STATUSES, load_roadmap, due_alerts


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


# ===== Activity stream (feed từ Jira changelog; dismiss đồng bộ qua Jira user property) =====
def render_activities(activities, days=7):
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
    for a in activities[:300]:
        k = a['key']
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(a)

    blocks = []
    for k in order:
        items = sorted(groups[k], key=lambda a: a.get('when') or '')  # timeline cũ -> mới
        sm = esc(items[0].get('summary', ''))
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


def _attn_row(issue, new_keys, extra_cells):
    new_cls = ' class="is-new"' if issue['key'] in new_keys else ''
    return (f'<tr{new_cls}{_person_attrs(issue)}><td>{issue_link(issue)}</td>'
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
        rows.append(f"""<tr{new_cls}{_person_attrs(issue)}>
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
        rows.append(f"""<tr{new_cls}{_person_attrs(issue)}>
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
def render_nav(active, user=None):
    """user = (email, is_admin) khi đăng nhập qua Cloudflare Access; None khi local."""
    def tab(href, key, label):
        cls = 'navtab active' if key == active else 'navtab'
        return f'<a class="{cls}" href="{href}">{label}</a>'
    chip = ''
    if user and user[0]:
        email, is_admin = user
        role = '<span class="nav-role nav-admin">Admin</span>' if is_admin else '<span class="nav-role">Chỉ xem</span>'
        chip = (f'<span class="nav-user" title="{esc(email)}">👤 {esc(email)} {role}</span>'
                '<a class="nav-logout" href="/logout" title="Đăng xuất">↩ Đăng xuất</a>')
    # admin (hoặc local dev user=None) thấy đủ; QA thường KHÔNG thấy Báo cáo tuần (toàn team)
    is_admin = user[1] if (user and len(user) > 1) else True
    report_tab = tab('/report', 'report', '📋 Báo cáo tuần') if is_admin else ''
    return ('<nav class="topnav">'
            + tab('/', 'dashboard', '📊 Tổng quan')
            + report_tab
            + tab('/roadmap', 'roadmap', '🗺 Roadmap')
            + tab('/docs', 'docs', '📚 Tài liệu')
            + chip
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


# Issue type -> css class cho badge tier (Project=tier1, Sub-task=tier5 là phần QA)
_TYPE_CLASS = {'Epic': 'ty-epic', 'Story': 'ty-story', 'Task': 'ty-task',
               'Task-PTSP': 'ty-ptsp', 'Sub-task': 'ty-sub'}
# Thứ tự sort node cùng cấp: việc đang chạy lên trước, done xuống cuối
_TASK_ORDER = {'In Progress': 0, 'PENDING': 1, 'TO DO': 2, 'DONE': 3, 'CANCELLED': 4}


def _qa_leaves(key, children, qa_keys, known):
    """Các sub-task QA nằm dưới 1 node (gồm cả chính nó nếu là QA)."""
    out, stack = [], [key]
    while stack:
        k = stack.pop()
        if k in qa_keys:
            out.append(known[k])
        stack.extend(children.get(k, []))
    return out


def _qa_pct(leaves):
    """(done, denom, pct) trên tập sub-task QA — mẫu số bỏ CANCELLED."""
    done = sum(1 for i in leaves if (i_status(i) or '').upper() in ('DONE', 'CLOSED', 'RESOLVED'))
    cancel = sum(1 for i in leaves if (i_status(i) or '').upper() == 'CANCELLED')
    denom = len(leaves) - cancel
    return done, denom, (round(done / denom * 100) if denom else 0)


def _type_badge(iss):
    t = i_type(iss)
    return f'<span class="ty {_TYPE_CLASS.get(t, "ty-other")}">{esc(t or "?")}</span>'


def _render_node(key, known, children, qa_keys, parent_of):
    iss = known.get(key)
    if iss is None:  # tham chiếu cha nhưng không có quyền xem
        return (f'<li class="lnode lnode-missing"><span class="ty ty-other">?</span> '
                f'<span class="key">{esc(key)}</span> '
                f'<span class="ln-sum">(không xem được)</span></li>')
    is_qa = key in qa_keys
    parts = [_type_badge(iss), issue_link(iss), f'<span class="ln-sum">{esc(i_summary(iss))}</span>']
    if is_qa:  # node QA (sub-task) — hiện PIC + status + cờ
        st = i_status(iss)
        parts.append(f'<span class="ln-asg">{esc(display_name(i_assignee(iss)))}</span>')
        parts.append(f'<span class="status {status_class(st)}">{esc(st)}</span>')
        od = days_overdue(iss)
        if od is not None:
            parts.append(f'<span class="rpt-tag tag-od">trễ {od}d</span>')
        if is_stuck(iss):
            parts.append(f'<span class="rpt-tag tag-st">kẹt {days_since_update(iss)}d</span>')
    else:  # node context (Story/Task/Task-PTSP) — hiện tiến độ test gộp bên dưới
        done, denom, pct = _qa_pct(_qa_leaves(key, children, qa_keys, known))
        if denom:
            bar_cls = 'ln-done' if pct == 100 else ('ln-mid' if pct >= 50 else 'ln-low')
            parts.append(f'<span class="ln-prog"><span class="ln-bar">'
                         f'<span class="{bar_cls}" style="width:{pct}%"></span></span>'
                         f'<span class="ln-pct">{done}/{denom} ({pct}%)</span></span>')
    kids = sorted(children.get(key, []),
                  key=lambda k: (_TASK_ORDER.get(i_status(known[k]), 9) if k in known else 9, k))
    sub = (f'<ul class="lntree">{"".join(_render_node(k, known, children, qa_keys, parent_of) for k in kids)}</ul>'
           if kids else '')
    row = f'<div class="lnode-row">{" ".join(parts)}</div>'
    cls = 'lnode' + (' lnode-qa' if is_qa else '')
    # Story/Epic = node thu gọn được (<details> native, mặc định mở)
    if i_type(iss) in ('Story', 'Epic') and kids:
        return f'<li class="{cls}"><details class="lnode-fold" open><summary>{row}</summary>{sub}</details></li>'
    return f'<li class="{cls}">{row}{sub}</li>'


def render_lines_section(line_data):
    if not line_data or not line_data.get('qa_issues'):
        return ''
    known = line_data['known']
    parent_of = line_data['parent_of']
    qa_keys = {i['key'] for i in line_data['qa_issues']}

    children = defaultdict(list)
    roots = []
    for k in known:
        p = parent_of.get(k)
        if p and p in known:
            children[p].append(k)
        else:  # gốc cao nhất (thường Story), hoặc cha không xem được
            roots.append(k)

    proj_roots = defaultdict(list)
    for r in roots:
        proj_roots[_project_of(r)].append(r)

    blocks = []
    for prj in sorted(proj_roots):
        rs = proj_roots[prj]
        all_leaves = [i for r in rs for i in _qa_leaves(r, children, qa_keys, known)]
        done, denom, pct = _qa_pct(all_leaves)
        rs_sorted = sorted(rs, key=lambda r: _qa_pct(_qa_leaves(r, children, qa_keys, known))[2])
        tree = ''.join(_render_node(r, known, children, qa_keys, parent_of) for r in rs_sorted)
        blocks.append(
            f'<div class="ln-proj"><h3>{esc(prj)} '
            f'<span class="ln-proj-pct">{done}/{denom} sub-task done · {pct}%</span></h3>'
            f'<ul class="lntree lntree-root">{tree}</ul></div>')

    win = line_data.get('window')
    win_txt = ''
    if win:
        start, end = win
        last_day = end - timedelta(days=1)
        win_txt = f'Tuần {start.strftime("%d/%m")}–{last_day.strftime("%d/%m")} · '
    return ('<div class="section lines-sec"><div class="rpt-script-head">'
            '<h2>🌳 Tiến độ test theo line dự án</h2>'
            '<button class="report-copy-btn" type="button" onclick="toggleStories(this)">⊟ Thu gọn Story</button></div>'
            f'<p class="rpt-legend-note">{win_txt}sub-task QA <b>In Progress / PENDING</b> luôn hiện kể cả ngoài tuần. '
            'Cây: Project › Story › Task › Task-PTSP › <b>Sub-task (QA)</b>. % tính trên sub-task QA, bỏ CANCELLED.</p>'
            + ''.join(blocks) + '</div>')


def render_report_page(data, line_data=None, user=None):
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

    legend_note = ('<p class="rpt-legend-note">🔴 có overdue/kẹt · 🟡 phần lớn chưa khởi động · 🟢 on track'
                   ' · thanh phân bổ: <span class="lg seg-todo"></span> TO DO'
                   ' <span class="lg seg-prog"></span> In Progress <span class="lg seg-pend"></span> PENDING</p>')

    body = (
        render_nav('report', user) +
        '<header class="report-head"><div><h1>📋 Báo cáo tuần — QA</h1>'
        f'<div class="meta">Chốt số: <strong>{fetched}</strong> · gom theo project key · '
        f'Tracking: {esc(", ".join(display_name(u) for u in USERS))}</div></div>'
        '<button class="report-print-btn" type="button" onclick="window.print()">🖨 In báo cáo</button></header>'
        + render_kpis(data['active'], data['new24'], data['done_week'], data['created_week'], data['resolved_week'])
        + charts
        + f'<div class="section"><h2>Tổng quan theo dự án</h2>{table}{legend_note}</div>'
        + render_lines_section(line_data)
    )
    return _document(body)


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


# ===== Full page =====
def render_page(data, new_keys, first_run, activities, activity_days=7, roadmap_data=None, user=None):
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
    # QA thường đã bị lọc sẵn theo chính họ -> filterbar vô nghĩa, ẩn đi. Admin/local mới có.
    is_admin = user[1] if (user and len(user) > 1) else True
    filterbar = render_filterbar() if is_admin else ''
    # cảnh báo hạn roadmap = việc của admin -> QA thường không thấy
    roadmap_alerts = render_roadmap_alerts(roadmap_data) if is_admin else ''
    body = (
        render_kpis(data['active'], data['new24'], data['done_week'], data['created_week'], data['resolved_week']) +
        roadmap_alerts +
        render_activities(activities, activity_days) +
        filterbar +
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

    inner = render_nav('dashboard', user) + header + first_run_note + body + footer
    return _document(inner)


# ===== Tài liệu training (tab /docs): cây folder + link Google Drive =====
def _doc_folder_html(name, children_html):
    return (
        '<li class="doc-node doc-folder">'
        '<details class="doc-fold" open>'
        '<summary class="doc-frow">'
        '<span class="doc-ficon">📁</span>'
        f'<span class="doc-fname" contenteditable="true">{esc(name)}</span>'
        '<span class="doc-fact">'
        '<button type="button" class="doc-add-folder" title="Thêm thư mục con">＋📁</button>'
        '<button type="button" class="doc-add-link" title="Thêm link tài liệu">＋🔗</button>'
        '<button type="button" class="doc-del" title="Xoá thư mục">×</button>'
        '</span></summary>'
        f'<ul class="doc-children">{children_html}</ul>'
        '</details></li>'
    )


def _doc_link_html(title, url):
    return (
        f'<li class="doc-node doc-link" data-url="{esc(url)}">'
        '<span class="doc-licon">🔗</span>'
        f'<a class="doc-title" href="{esc(url)}" target="_blank" rel="noopener" '
        f'title="Mở để view/edit ở Google">{esc(title)}</a>'
        f'<span class="doc-url" title="{esc(url)}">{esc(url)}</span>'
        '<button type="button" class="doc-edit" title="Sửa tài liệu">✎</button>'
        '</li>'
    )


def _doc_node_html(node):
    if node.get('type') == 'link':
        return _doc_link_html(node.get('title', ''), node.get('url', ''))
    kids = ''.join(_doc_node_html(c) for c in (node.get('children') or []))
    return _doc_folder_html(node.get('name', ''), kids)


def render_docs_page(tree, editable=True, user=None):
    nodes = ''.join(_doc_node_html(n) for n in (tree or []))
    empty = '' if nodes else '<li class="doc-empty">Chưa có thư mục. Bấm “＋ Thư mục gốc” để bắt đầu.</li>'
    ro = '' if editable else ' ro'
    banner = '' if editable else '<div class="ro-banner">👁 Chế độ chỉ xem — chỉ quản lý mới chỉnh sửa được.</div>'
    body = (
        render_nav('docs', user) +
        '<header><h1>📚 Tài liệu training</h1>'
        '<div class="meta">Cây thư mục · link tới Google Drive · click để mở tab mới view/edit · tự động lưu</div></header>'
        + banner +
        f'<div class="section docs-sec{ro}">'
        '<div class="docs-toolbar">'
        '<button type="button" id="docAddRoot" class="docs-btn">＋ Thư mục gốc</button>'
        '<button type="button" id="docCollapseAll" class="docs-btn">⊟ Thu gọn tất cả</button>'
        '<span class="doc-save-status" id="docStatus"></span>'
        '</div>'
        f'<ul class="doc-tree" id="docTree">{nodes}{empty}</ul>'
        f'<template id="docFolderTpl">{_doc_folder_html("Thư mục mới", "")}</template>'
        f'<template id="docLinkTpl">{_doc_link_html("Tài liệu mới", "")}</template>'
        '</div>'
        # popup sửa tài liệu (tên / link / xoá)
        '<div class="docm-overlay" id="docmOverlay">'
        '<div class="docm-modal" role="dialog" aria-label="Sửa tài liệu">'
        '<div class="docm-head"><h3>Sửa tài liệu</h3>'
        '<button type="button" class="docm-close" id="docmClose" aria-label="Đóng">×</button></div>'
        '<label class="docm-label" for="docmTitle">Tên tài liệu</label>'
        '<input type="text" id="docmTitle" class="docm-input" autocomplete="off">'
        '<label class="docm-label" for="docmUrl">Link Google Drive</label>'
        '<input type="text" id="docmUrl" class="docm-input" placeholder="https://docs.google.com/..." autocomplete="off">'
        '<div class="docm-actions">'
        '<button type="button" class="docm-del" id="docmDel">🗑 Xoá tài liệu</button>'
        '<button type="button" class="docm-cancel" id="docmCancel">Huỷ</button>'
        '<button type="button" class="docm-save" id="docmSave">Lưu</button>'
        '</div></div></div>'
    )
    return _document(body)


# ===== Roadmap (tab /roadmap): giai đoạn › mục › sub-task =====
_RM_LABELS = {v: l for v, l in RM_STATUSES}


def _rm_clamp(prog):
    try:
        return max(0, min(100, int(prog)))
    except (TypeError, ValueError):
        return 0


def _rm_due_chip(due):
    hidden = '' if due else ' hidden'
    return f'<span class="rm-due"{hidden}>📅 {esc(due)}</span>'


def _rm_node_cells(node):
    """Phần hiển thị chung của 1 node (item/sub-task): badge + tên + due + bar + ✎."""
    status = node.get('status', 'planned')
    prog = _rm_clamp(node.get('progress', 0))
    return (
        f'<span class="rm-status rm-st-{esc(status)}">{esc(_RM_LABELS.get(status, status))}</span>'
        f'<span class="rm-title">{esc(node.get("title", ""))}</span>'
        f'{_rm_due_chip(node.get("due", ""))}'
        f'<span class="rm-bar" title="{prog}%"><i style="width:{prog}%"></i></span>'
        f'<span class="rm-pct">{prog}%</span>'
        '<button type="button" class="rm-edit" title="Sửa">✎</button>'
    )


def _rm_data_attrs(node):
    return (f' data-status="{esc(node.get("status", "planned"))}"'
            f' data-progress="{_rm_clamp(node.get("progress", 0))}"'
            f' data-due="{esc(node.get("due", ""))}"')


def _rm_item_progress(item):
    """% mục: nếu có sub-task -> trung bình % sub-task (mục không sửa tay); else % của chính nó."""
    subs = item.get('subtasks') or []
    if subs:
        vals = [_rm_clamp(s.get('progress', 0)) for s in subs]
        return round(sum(vals) / len(vals)) if vals else 0
    return _rm_clamp(item.get('progress', 0))


def _rm_item_status(item):
    """Status mục suy từ sub-task: all done->done · có blocked->blocked · có in_progress
    (hoặc đã có vài done) -> in_progress · còn lại -> planned. Không sub-task -> status của chính nó."""
    subs = item.get('subtasks') or []
    if not subs:
        return item.get('status', 'planned')
    sts = [s.get('status', 'planned') for s in subs]
    if all(s == 'done' for s in sts):
        return 'done'
    if any(s == 'blocked' for s in sts):
        return 'blocked'
    if any(s in ('in_progress', 'done') for s in sts):
        return 'in_progress'
    return 'planned'


def _rm_subtask_html(sub):
    return f'<li class="rm-node rm-sub"{_rm_data_attrs(sub)}>{_rm_node_cells(sub)}</li>'


def _rm_item_html(item):
    subs = item.get('subtasks') or []
    # % + status hiển thị = tổng hợp từ sub-task nếu có
    item = dict(item, progress=_rm_item_progress(item), status=_rm_item_status(item))
    subs_html = ''.join(_rm_subtask_html(s) for s in subs)
    head = (f'<div class="rm-irow">{_rm_node_cells(item)}'
            '<button type="button" class="rm-add-sub" title="Thêm sub-task">＋</button></div>')
    inner = (f'<details class="rm-ifold" open><summary>{head}</summary>'
             f'<ul class="rm-subs">{subs_html}</ul></details>')
    return f'<li class="rm-node rm-item"{_rm_data_attrs(item)}>{inner}</li>'


def _rm_phase_html(phase):
    name = phase.get('phase', '')
    items = phase.get('items') or []
    done = sum(1 for i in items if i.get('status') == 'done')
    total = len(items)
    pct = round(done / total * 100) if total else 0
    items_html = ''.join(_rm_item_html(i) for i in items)
    return (
        '<div class="rm-phase">'
        '<details class="rm-fold" open><summary class="rm-phead">'
        '<span class="rm-picon">📅</span>'
        f'<span class="rm-pname">{esc(name)}</span>'
        f'<span class="rm-summary"><span class="rm-sum-txt">{done}/{total} xong</span>'
        f'<span class="rm-sum-bar"><i style="width:{pct}%"></i></span></span>'
        '<span class="rm-pact">'
        '<button type="button" class="rm-add-item" title="Thêm mục">＋ Mục</button>'
        '<button type="button" class="rm-edit-phase" title="Sửa giai đoạn">✎</button>'
        '</span></summary>'
        f'<ul class="rm-items">{items_html}</ul>'
        '</details></div>'
    )


def _rm_status_options():
    return ''.join(f'<option value="{esc(v)}">{esc(l)}</option>' for v, l in RM_STATUSES)


def render_roadmap_page(data, editable=True, user=None):
    phases = ''.join(_rm_phase_html(p) for p in (data or []))
    empty = '' if phases else '<div class="rm-empty">Chưa có giai đoạn. Bấm “＋ Giai đoạn” để bắt đầu.</div>'
    ro = '' if editable else ' ro'
    banner = '' if editable else '<div class="ro-banner">👁 Chế độ chỉ xem — chỉ quản lý mới chỉnh sửa được.</div>'
    body = (
        render_nav('roadmap', user) +
        '<header><h1>🗺 Roadmap team QA</h1>'
        '<div class="meta">Theo mốc thời gian · bấm để xổ cây · sửa qua ✎ · tự động lưu</div></header>'
        + banner +
        f'<div class="section rm-sec{ro}">'
        '<div class="rm-toolbar">'
        '<button type="button" id="rmAddPhase" class="rm-tbtn">＋ Giai đoạn</button>'
        '<button type="button" id="rmCollapse" class="rm-tbtn">⊟ Thu gọn tất cả</button>'
        '<span class="rm-legend">'
        + ''.join(f'<span class="rm-lg rm-st-{esc(v)}">{esc(l)}</span>' for v, l in RM_STATUSES)
        + '</span>'
        '<span class="doc-save-status" id="rmStatus"></span>'
        '</div>'
        f'<div class="rm-list" id="rmList">{phases}{empty}</div>'
        f'<template id="rmPhaseTpl">{_rm_phase_html({"phase": "Giai đoạn mới", "items": []})}</template>'
        f'<template id="rmItemTpl">{_rm_item_html({"title": "Mục mới", "status": "planned", "progress": 0, "due": "", "subtasks": []})}</template>'
        f'<template id="rmSubTpl">{_rm_subtask_html({"title": "Sub-task mới", "status": "planned", "progress": 0, "due": ""})}</template>'
        '</div>'
        # popup sửa node (tên / trạng thái / % / hạn / xoá). Phase chỉ dùng tên + xoá.
        '<div class="docm-overlay" id="rmmOverlay">'
        '<div class="docm-modal" role="dialog" aria-label="Sửa">'
        '<div class="docm-head"><h3 id="rmmHead">Sửa mục</h3>'
        '<button type="button" class="docm-close" id="rmmClose" aria-label="Đóng">×</button></div>'
        '<label class="docm-label" for="rmmTitle">Tiêu đề</label>'
        '<input type="text" id="rmmTitle" class="docm-input" autocomplete="off">'
        '<div class="rmm-grid" id="rmmFields">'
        '<div><label class="docm-label" for="rmmStatus">Trạng thái</label>'
        f'<select id="rmmStatus" class="docm-input">{_rm_status_options()}</select>'
        '<small class="rmm-note" id="rmmStatusNote" hidden>Tự tính theo sub-task</small></div>'
        '<div><label class="docm-label" for="rmmProg">% tiến độ</label>'
        '<input type="number" id="rmmProg" class="docm-input" min="0" max="100">'
        '<small class="rmm-note" id="rmmProgNote" hidden>Tự tính theo sub-task</small></div>'
        '<div><label class="docm-label" for="rmmDue">Hạn</label>'
        '<input type="date" id="rmmDue" class="docm-input"></div>'
        '</div>'
        '<div class="docm-actions">'
        '<button type="button" class="docm-del" id="rmmDel">🗑 Xoá</button>'
        '<button type="button" class="docm-cancel" id="rmmCancel">Huỷ</button>'
        '<button type="button" class="docm-save" id="rmmSave">Lưu</button>'
        '</div></div></div>'
    )
    return _document(body)


def render_roadmap_alerts(roadmap_data):
    """Block cảnh báo (dashboard): mục roadmap chưa xong, hạn <= 2 tuần. Tách khỏi feed Jira."""
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
            f'<span class="rm-al-phase">{esc(a["phase"])}</span>'
            f'<span class="rm-al-due">📅 {esc(a["due"])}</span></div>'
        )
    return (f'<div class="section rm-alerts"><h2>🗺 Roadmap sắp đến hạn '
            f'<span class="count">{len(alerts)}</span></h2>'
            f'<div class="rm-al-list">{"".join(rows)}</div></div>')


def render_error_page(msg):
    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><title>Error</title>
<script>(function(){{try{{var t=localStorage.getItem('qa-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>{load_css()}</style></head>
<body><div class="container"><header><h1>QA Team Dashboard</h1></header>
<div class="error"><strong>Lỗi pull data từ Jira:</strong><br>{esc(msg)}</div>
<p style="color:#6b778c;margin-top:16px">Check JIRA_URL, JIRA_PAT trong file .env. F5 để retry.</p>
</div></body></html>"""
