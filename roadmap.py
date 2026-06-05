"""Roadmap team QA: các giai đoạn (mốc thời gian) › mục › sub-task. Load/save .roadmap_config.json.

Roadmap = list giai đoạn. Mỗi giai đoạn {phase: str, items: [item]}.
node (item/sub-task) = {title, status, progress(int 0-100), due(str 'YYYY-MM-DD' | '')}.
item có thể thêm "subtasks": [leaf]. Tự author + chỉnh tay (KHÔNG suy từ Jira).
"""
import json
from datetime import datetime

from config import ROADMAP_FILE

MAX_PHASES = 100
MAX_ITEMS = 1000

# (value, label) — value lưu JSON, label hiện UI. CSS class = rm-st-<value>.
RM_STATUSES = [
    ('planned', 'Planned'),
    ('in_progress', 'In Progress'),
    ('done', 'Done'),
    ('blocked', 'Blocked'),
]
RM_STATUS_VALUES = {v for v, _ in RM_STATUSES}

ROADMAP_DEFAULT = [
    {'phase': 'Q3 2026', 'items': [
        {'title': 'Ví dụ: Tăng test coverage luồng Chi Hộ', 'status': 'in_progress',
         'progress': 40, 'due': '2026-07-15', 'subtasks': [
            {'title': 'Rà soát test case hiện có', 'status': 'done', 'progress': 100, 'due': '2026-07-05'},
            {'title': 'Bổ sung case thiếu', 'status': 'in_progress', 'progress': 30, 'due': '2026-07-15'},
         ]},
        {'title': 'Ví dụ: Chuẩn hoá bộ test case regression', 'status': 'planned',
         'progress': 0, 'due': '', 'subtasks': []},
    ]},
    {'phase': 'Q4 2026', 'items': [
        {'title': 'Ví dụ: Tự động hoá smoke test', 'status': 'planned', 'progress': 0, 'due': '', 'subtasks': []},
    ]},
]


def _valid_leaf(it):
    return (isinstance(it, dict)
            and isinstance(it.get('title', ''), str)
            and isinstance(it.get('status', 'planned'), str)
            and isinstance(it.get('due', ''), str)
            and isinstance(it.get('progress', 0), int)
            and 0 <= it.get('progress', 0) <= 100)


def _valid_item(it):
    if not _valid_leaf(it):
        return False
    subs = it.get('subtasks', [])
    return isinstance(subs, list) and all(_valid_leaf(s) for s in subs)


def valid_roadmap(data):
    if not isinstance(data, list) or len(data) > MAX_PHASES:
        return False
    total = 0
    for ph in data:
        if not isinstance(ph, dict) or not isinstance(ph.get('phase', ''), str):
            return False
        items = ph.get('items')
        if not isinstance(items, list):
            return False
        for it in items:
            total += 1 + len(it.get('subtasks', []) if isinstance(it, dict) else [])
            if total > MAX_ITEMS or not _valid_item(it):
                return False
    return True


def _parse_due(s):
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def due_alerts(data, today=None, within_days=14):
    """Mục/sub-task chưa Done mà còn <= within_days tới hạn (gồm cả quá hạn).

    Trả list dict {phase, title, due, days_left} sort theo days_left tăng dần.
    days_left < 0 = quá hạn. Dùng cho cảnh báo ở phần Hoạt động dashboard.
    """
    today = today or datetime.now().date()
    out = []
    for ph in (data or []):
        pname = ph.get('phase', '')
        for it in (ph.get('items') or []):
            nodes = [it] + list(it.get('subtasks') or [])
            for n in nodes:
                if n.get('status') == 'done':
                    continue
                d = _parse_due(n.get('due', ''))
                if d is None:
                    continue
                days = (d - today).days
                if days <= within_days:
                    out.append({'phase': pname, 'title': n.get('title', ''),
                                'due': n.get('due', ''), 'days_left': days})
    out.sort(key=lambda a: a['days_left'])
    return out


def load_roadmap():
    if ROADMAP_FILE.exists():
        try:
            data = json.loads(ROADMAP_FILE.read_text(encoding='utf-8'))
            if valid_roadmap(data):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return ROADMAP_DEFAULT


def save_roadmap(data):
    if not valid_roadmap(data):
        return False
    try:
        ROADMAP_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return True
    except OSError:
        return False
