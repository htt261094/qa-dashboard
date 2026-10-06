"""Trang "Hôm nay" (`/today`) — trang chính, chỗ bắt đầu ngày làm việc (Decision #102).

Gom việc CẦN XỬ LÝ TRONG NGÀY từ data đã có, KHÔNG thêm call Jira nào ngoài bundle của
"Việc của tôi": quá hạn · đến hạn hôm nay · kẹt · sắp đến hạn 7 ngày · được nhắc chưa đọc ·
task đang có ghi chú riêng (#101). Mỗi task chỉ nằm ở MỘT nhóm (ưu tiên theo thứ tự trên),
cờ phụ hiện thành badge. Click mở drawer dùng chung (shared drawer — trang không có #rows).
"""
from datetime import datetime, timedelta

from config import STUCK_DAYS, canon_key, JIRA_URL
from issues import esc, parse_date
from custom_status import CUSTOM_STATUSES
from task_notes import index_by_canon

from render.dashboard import build_my_work_payload, _snap_note
from render.shell import _document_v2, _conn_error_card

_WEEKDAYS = ('Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật')
_CUST = dict(CUSTOM_STATUSES)
_UPCOMING_DAYS = 7
# Bug mở "chưa đụng" >= ngưỡng này -> coi là tồn đọng, nhắc ở /today (#109). Dùng STUCK_DAYS
# cho đồng nhất với "task kẹt". Bug đã Closed/Rejected (vòng đời) không tính.
_BUG_STALE_DAYS = STUCK_DAYS
_BUG_DONE = ('closed', 'rejected')


def _jira_cls(v):
    # Twin của jiraCls() trong app_v2.js (màu badge status Jira).
    v = (v or '').upper()
    return {'DONE': 'b-done', 'CANCELLED': 'b-critical', 'IN PROGRESS': 'b-checking',
            'PENDING': 'b-blocked'}.get(v, 'b-todo')


def _due_label(due, today):
    d = parse_date(due) if due else None
    if not d:
        return 'Chưa đặt hạn', ''
    n = (d - today).days
    if n < 0:
        return f'Trễ {-n} ngày', 'od'
    if n == 0:
        return 'Hôm nay', 'today'
    if n == 1:
        return 'Ngày mai', ''
    return f'{d.strftime("%d/%m")} · còn {n} ngày', ''


def _task_row(t, today, note=None):
    due, due_cls = _due_label(t.get('due'), today)
    flags = ''
    if t.get('stuck'):
        flags += f'<span class="dt-flag st">Kẹt ≥ {STUCK_DAYS} ngày</span>'
    chips = ''.join(f'<span class="cust-chip">{esc(_CUST.get(v, v))}</span>'
                    for v in (t.get('customs') or []))
    note_html = ''
    if note:
        first = next((ln.strip() for ln in note.get('t', '').splitlines() if ln.strip()), '')
        note_html = (f'<div class="td-note"><span class="material-symbols-rounded ph-light '
                     f'ph-note-pencil mi-xs"></span>{esc(first[:160])}</div>')
    return (
        f'<div class="td-row" data-today-open="{esc(t["key"])}">'
        f'<a class="key" href="{esc(t["jiraUrl"])}" target="_blank" rel="noopener">{esc(t["key"])}</a>'
        f'<div class="td-main"><div class="td-sum">{esc(t["summary"])}</div>'
        f'{note_html}'
        f'{("<div class=td-chips>" + flags + chips + "</div>") if (flags or chips) else ""}</div>'
        f'<span class="badge {_jira_cls(t["jira"])}">{esc(t["jira"])}</span>'
        f'<span class="td-due {due_cls}">{esc(due)}</span>'
        '</div>'
    )


def _section(title, icon, rows_html, count, tone='', empty=''):
    if not count and not empty:
        return ''
    body = rows_html if count else f'<div class="td-empty">{esc(empty)}</div>'
    return (
        f'<section class="card td-sec {tone}">'
        f'<div class="td-head"><span class="material-symbols-rounded ph-light ph-{icon}"></span>'
        f'<h3>{esc(title)}</h3><span class="tcount">{count}</span></div>'
        f'<div class="td-list">{body}</div></section>'
    )


def _mention_row(a):
    when = (a.get('when') or '')[:16].replace('T', ' ')
    snip = f'<div class="td-note">“{esc(a.get("body") or "")}”</div>' if a.get('body') else ''
    return (
        f'<div class="td-row" data-today-open="{esc(a.get("key", ""))}" data-actid="{esc(a.get("id", ""))}">'
        f'<span class="key">{esc(a.get("key", ""))}</span>'
        f'<div class="td-main"><div class="td-sum"><b>{esc(a.get("author") or "—")}</b> nhắc đến bạn</div>{snip}</div>'
        f'<span class="td-due">{esc(when)}</span></div>'
    )


def build_today_groups(tasks, notes=None, now=None):
    """tasks (từ build_my_work_payload) -> dict nhóm. Thuần, test được không cần render.
    Mỗi task active vào đúng 1 nhóm: overdue > today > stuck > upcoming; task có ghi chú mà
    không rơi vào nhóm nào -> 'noted'. Done/Cancelled bị bỏ."""
    today = (now or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    horizon = today + timedelta(days=_UPCOMING_DAYS)
    note_idx = index_by_canon(notes or {})
    g = {'overdue': [], 'today': [], 'stuck': [], 'upcoming': [], 'noted': []}
    for t in tasks:
        if (t.get('jira') or '').upper() in ('DONE', 'CANCELLED'):
            continue
        d = parse_date(t.get('due')) if t.get('due') else None
        if t.get('overdue'):
            g['overdue'].append(t)
        elif d and d == today:
            g['today'].append(t)
        elif t.get('stuck'):
            g['stuck'].append(t)
        elif d and today < d <= horizon:
            g['upcoming'].append(t)
        elif canon_key(t['key']) in note_idx:
            g['noted'].append(t)
    far = datetime(9999, 1, 1)
    for k in ('overdue', 'today', 'upcoming'):
        g[k].sort(key=lambda t: parse_date(t.get('due')) or far)
    g['stuck'].sort(key=lambda t: t.get('created') or '')
    return g


def _flatten_open_bugs(bug_data):
    """load_bug_log() = {files:{fid:{bugs:{key:bug}}}} -> list bug dict ĐANG MỞ (bỏ Closed/Rejected)."""
    out = []
    for _fid, f in ((bug_data or {}).get('files', {}) or {}).items():
        for _key, b in (f.get('bugs', {}) or {}).items():
            if (b.get('status') or '').strip().lower() in _BUG_DONE:
                continue
            out.append(b)
    return out


def build_bug_aging(bugs, now=None, threshold=_BUG_STALE_DAYS):
    """bugs (bug mở đã lọc Closed/Rejected) -> bug "chưa đụng" >= threshold ngày, gom theo squad.
    Thuần, test được. Tuổi = số ngày từ `updated` (lần đụng gần nhất); cache cũ thiếu `updated`
    -> fallback `created`. Trả {total, squads:[{squad,count,oldest_days}], items:[bug+_age]}."""
    today = (now or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    stale = []
    for b in bugs:
        d = parse_date(b.get('updated') or b.get('created') or '')
        if not d:
            continue
        age = (today - d).days
        if age >= threshold:
            stale.append({**b, '_age': age})
    stale.sort(key=lambda x: x['_age'], reverse=True)
    squads = {}
    for b in stale:
        s = b.get('project') or 'Khác'
        q = squads.setdefault(s, {'squad': s, 'count': 0, 'oldest_days': 0})
        q['count'] += 1
        q['oldest_days'] = max(q['oldest_days'], b['_age'])
    squad_list = sorted(squads.values(), key=lambda x: (-x['oldest_days'], -x['count']))
    return {'total': len(stale), 'squads': squad_list, 'items': stale}


def _age_cls(age):
    if age >= 14:
        return 'tba-hot'
    if age >= _BUG_STALE_DAYS * 2:
        return 'tba-warm'
    return ''


def _bug_aging_section(ag, limit=8):
    """Render card "Bug tồn đọng" cho /today. '' khi không có bug nào quá ngưỡng."""
    if not ag or not ag.get('total'):
        return ''
    chips = ''.join(
        f'<span class="tba-chip"><b>{esc(s["squad"])}</b> {s["count"]}'
        f'<span class="tba-old">· cũ nhất {s["oldest_days"]}d</span></span>'
        for s in ag['squads'])
    rows = ''
    for b in ag['items'][:limit]:
        key = b.get('key', '') or ''
        age = b.get('_age', 0)
        rows += (
            f'<div class="td-row">'
            f'<a class="key" href="{esc(JIRA_URL)}/browse/{esc(key)}" target="_blank" rel="noopener">{esc(key)}</a>'
            f'<div class="td-main"><div class="td-sum">{esc(b.get("summary", ""))}</div></div>'
            f'<span class="tba-squad">{esc(b.get("project") or "—")}</span>'
            f'<span class="tba-age {_age_cls(age)}">{age} ngày</span>'
            '</div>')
    more = ag['total'] - min(limit, len(ag['items']))
    more_html = (f'<a class="tba-more" href="/bug-log">+{more} bug nữa · mở Bug Log →</a>'
                 if more > 0 else '')
    return (
        '<section class="card td-sec td-bugage tone-warn">'
        '<div class="td-head"><span class="material-symbols-rounded ph-light ph-bug-beetle"></span>'
        f'<h3>Bug tồn đọng · chưa đụng ≥ {_BUG_STALE_DAYS} ngày</h3>'
        f'<span class="tcount">{ag["total"]}</span></div>'
        f'<div class="tba-squads">{chips}</div>'
        f'<div class="td-list">{rows}{more_html}</div></section>'
    )


def render_today_v2(data, activities, cmap, user, notes=None, stale=False, jira_error=False,
                    bug_data=None):
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    hello = f'{_WEEKDAYS[now.weekday()]}, {now.strftime("%d/%m/%Y")}'
    head = (f'<div class="page-head"><div><div class="page-title">Hôm nay</div>'
            f'<p>{esc(hello)}</p></div></div>')
    mentions = [a for a in (activities or [])
                if a.get('mention') and a.get('is_unread')]
    if jira_error:
        content = head + _conn_error_card()
        return _document_v2(content, 'today', user, activities, title='Hôm nay — QA Workspace')

    tasks, _meta = build_my_work_payload(data, cmap, notes)
    g = build_today_groups(tasks, notes, now)
    note_idx = index_by_canon(notes or {})

    def rows(lst):
        return ''.join(_task_row(t, today, note_idx.get(canon_key(t['key']))) for t in lst)

    kpis = (
        '<div class="kpis td-kpis">'
        f'<a class="kpi warn" href="#td-overdue"><div class="label">Quá hạn</div><div class="value">{len(g["overdue"])}</div></a>'
        f'<a class="kpi" href="#td-today"><div class="label">Đến hạn hôm nay</div><div class="value">{len(g["today"])}</div></a>'
        f'<a class="kpi stuck" href="#td-stuck"><div class="label">Kẹt ≥ {STUCK_DAYS} ngày</div><div class="value">{len(g["stuck"])}</div></a>'
        f'<a class="kpi" href="#td-mention"><div class="label">Được nhắc · chưa đọc</div><div class="value">{len(mentions)}</div></a>'
        f'<a class="kpi" href="#td-upcoming"><div class="label">{_UPCOMING_DAYS} ngày tới</div><div class="value">{len(g["upcoming"])}</div></a>'
        '</div>'
    )
    urgent = len(g['overdue']) + len(g['today']) + len(g['stuck']) + len(mentions)
    secs = (
        f'<div id="td-overdue">{_section("Quá hạn", "calendar-x", rows(g["overdue"]), len(g["overdue"]), "tone-err")}</div>'
        f'<div id="td-today">{_section("Đến hạn hôm nay", "calendar-check", rows(g["today"]), len(g["today"]), "tone-pri")}</div>'
        f'<div id="td-mention">{_section("Được nhắc đến · chưa đọc", "at", "".join(_mention_row(a) for a in mentions), len(mentions))}</div>'
        f'<div id="td-stuck">{_section(f"Kẹt ≥ {STUCK_DAYS} ngày không cập nhật", "hourglass", rows(g["stuck"]), len(g["stuck"]), "tone-warn")}</div>'
        f'<div id="td-upcoming">{_section(f"Sắp đến hạn · {_UPCOMING_DAYS} ngày tới", "calendar-dots", rows(g["upcoming"]), len(g["upcoming"]))}</div>'
        f'{_section("Đang có ghi chú riêng", "note-pencil", rows(g["noted"]), len(g["noted"]))}'
    )
    if not urgent:
        secs = ('<div class="card"><div class="empty-state">'
                '<span class="es-ic"><span class="material-symbols-rounded ph-light ph-confetti"></span></span>'
                '<div class="es-title">Không có gì gấp hôm nay 🎉</div>'
                '<div class="es-hint">Không quá hạn, không kẹt, không ai đang chờ bạn trả lời.</div>'
                '</div></div>') + secs
    # Bug tồn đọng (#109) — cross-squad, nằm trên lưới task cá nhân vì là việc review của leader.
    bug_sec = _bug_aging_section(build_bug_aging(_flatten_open_bugs(bug_data), now))
    content = head + kpis + bug_sec + f'<div class="td-grid" id="todayPage">{secs}</div>'
    return _document_v2(content, 'today', user, activities, title='Hôm nay — QA Workspace',
                        stale=stale, stale_note=_snap_note(data) if stale else '')
