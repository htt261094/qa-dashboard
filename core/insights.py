"""Insight "Cần chú ý hôm nay" — server-computed, cho admin dashboard.

compute_insights(data, buglog) -> list insight dict, đã rank. Pure function:
KHÔNG network, KHÔNG state (cùng triết lý issues.py). Mọi rule đều defensive —
data bất thường thì skip rule đó, không bao giờ làm vỡ render dashboard.

Item: {'icon': str,                       # Material Symbols name
       'severity': 'crit'|'warn'|'info',
       'text': str,                       # đã escape ở render (đây là plain text)
       'keys': [taskKey, ...],            # chip mở drawer (tối đa 3)
       'href': str}                       # deep-link (vd /bug-log?bug=...) — '' nếu không có
"""
from datetime import datetime, timedelta
from urllib.parse import quote

from config import USERS, STUCK_DAYS, display_name
from issues import (parse_date, i_assignee, i_status, i_duedate,
                    days_overdue, days_since_update, is_stuck)

# Decision #5 — KHÔNG đổi threshold workload (15/5/4)
WORKLOAD_HIGH = 15
WORKLOAD_LOW = 4
REOPEN_ALERT = 2      # bug reopen >= N lần trong tháng -> đáng chú ý
MAX_ITEMS = 8         # cap tổng số insight hiển thị

_SEV_RANK = {'crit': 0, 'warn': 1, 'info': 2}


def _item(icon, severity, text, keys=None, href=''):
    return {'icon': icon, 'severity': severity, 'text': text,
            'keys': (keys or [])[:3], 'href': href}


def _next_business_day(today):
    d = today + timedelta(days=1)
    while d.weekday() >= 5:   # T7/CN -> nhảy tới T2
        d += timedelta(days=1)
    return d


def _rule_overdue(active):
    rows = []
    for iss in active:
        n = days_overdue(iss)
        if n:
            rows.append((n, iss['key']))
    if not rows:
        return None
    rows.sort(reverse=True)
    return _item('event_busy', 'crit',
                 f'{len(rows)} task đã quá hạn — nặng nhất {rows[0][0]} ngày làm việc',
                 [k for _, k in rows])


def _rule_due_soon(active):
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    nbd = _next_business_day(today)
    rows = []
    for iss in active:
        if days_overdue(iss):        # đã quá hạn -> thuộc rule 1, không đếm đôi
            continue
        d = parse_date(i_duedate(iss))
        if d and today <= d <= nbd:
            rows.append((d, iss['key']))
    if not rows:
        return None
    rows.sort()
    return _item('schedule', 'warn',
                 f'{len(rows)} task tới hạn hôm nay / ngày làm việc kế tiếp',
                 [k for _, k in rows])


def _rule_stuck(active):
    rows = []
    for iss in active:
        if is_stuck(iss):
            rows.append((days_since_update(iss) or 0, iss['key']))
    if not rows:
        return None
    rows.sort(reverse=True)
    return _item('hourglass_bottom', 'warn',
                 f'{len(rows)} task kẹt ≥ {STUCK_DAYS} ngày không cập nhật — lâu nhất {rows[0][0]} ngày',
                 [k for _, k in rows])


def _rule_workload(active):
    counts = {u: 0 for u in USERS}
    for iss in active:
        u = i_assignee(iss)
        if u in counts:
            counts[u] += 1
    out = []
    over = [(n, u) for u, n in counts.items() if n >= WORKLOAD_HIGH]
    over.sort(reverse=True)
    for n, u in over:
        out.append(_item('local_fire_department', 'crit',
                         f'{display_name(u)} đang QUÁ TẢI ({n} task active)'))
    light = [u for u, n in counts.items() if n <= WORKLOAD_LOW]
    if over and light:
        names = ', '.join(display_name(u) for u in light)
        out.append(_item('balance', 'info',
                         f'{names} đang nhẹ việc (≤ {WORKLOAD_LOW} task) — cân nhắc chia lại'))
    return out


def _bug_disp(key):
    """Key bug log '{project}#{service}#{sheet}#{no}' -> id hiển thị 'project-service-no'."""
    parts = (key or '').split('#')
    if len(parts) >= 4:
        proj, service, no = parts[0], parts[1], parts[3]
        return '-'.join(p for p in (proj, service, no) if p)
    return key or ''


def _rule_reopen(buglog):
    cur_month = datetime.now().strftime('%m/%Y')
    rows = []
    for key, r in (buglog.get('reopen', {}) or {}).items():
        try:
            if int(r.get('count', 0)) >= REOPEN_ALERT and r.get('month') == cur_month:
                rows.append((int(r['count']), key, r.get('dev', '')))
        except (TypeError, ValueError):
            continue
    rows.sort(reverse=True)
    out = []
    for count, key, dev in rows[:3]:
        dev_txt = f' (dev {dev})' if dev else ''
        out.append(_item('replay', 'warn',
                         f'Bug {_bug_disp(key)} bị reopen {count} lần trong tháng{dev_txt}',
                         # key chứa '#' -> PHẢI quote, không thì browser cắt thành fragment
                         href='/bug-log?bug=' + quote(key, safe='')))
    return out


def _rule_backlog_trend(data):
    c = data.get('created_week')
    r = data.get('resolved_week')
    if not isinstance(c, int) or not isinstance(r, int) or (c == 0 and r == 0):
        return None
    if c <= r:
        return None
    sev = 'warn' if c >= r + 5 else 'info'
    return _item('trending_up', sev,
                 f'Tuần này: vào {c} / ra {r} task — backlog đang phình')


def compute_insights(data, buglog):
    """Rank: crit -> warn -> info (giữ thứ tự rule trong cùng severity), cap MAX_ITEMS.
    Mọi rule bọc defensive: rule lỗi -> bỏ rule đó, không bao giờ raise."""
    data = data or {}
    buglog = buglog or {}
    active = data.get('active') or []
    items = []

    def safe(fn, *args):
        try:
            r = fn(*args)
        except Exception:   # noqa: BLE001 — insight là phụ trợ, không được vỡ dashboard
            return
        if r is None:
            return
        items.extend(r if isinstance(r, list) else [r])

    safe(_rule_overdue, active)
    safe(_rule_due_soon, active)
    safe(_rule_stuck, active)
    safe(_rule_workload, active)
    safe(_rule_reopen, buglog)
    safe(_rule_backlog_trend, data)

    items.sort(key=lambda it: _SEV_RANK.get(it.get('severity'), 3))
    return items[:MAX_ITEMS]
