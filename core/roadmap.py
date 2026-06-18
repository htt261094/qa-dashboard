"""Roadmap team QA — UI v2 (Stitch). Load/save .roadmap_config.json + Jira property sync.

Schema (plan-based, theo mockup Stitch):
    roadmap = list[plan]
    plan = {id, title, desc, status, pic, due('YYYY-MM-DD'|''), tasks: [task]}
    task = {id, title, pic, done(bool), subs: [leaf]}
    leaf = {id, title, done(bool)}

Status plan ∈ RM_STATUSES (planned/in_progress/done/blocked). PIC = tên hiển thị trong RM_PEOPLE.
Tự author + chỉnh tay (KHÔNG suy từ Jira). Data schema cũ (phase/items/status/progress/due per-node)
được `migrate_roadmap` convert tự động khi load → không mất roadmap đang lưu.
"""
import json
from datetime import datetime

from config import ROADMAP_FILE, USERS, display_name, atomic_write
from remote_store import synced_load, synced_save

ROADMAP_PROP = 'qa-dashboard-roadmap'  # Jira user property = kho sync chéo máy

MAX_PLANS = 100
MAX_ITEMS = 1000

# (value, label) — value lưu JSON, label hiện UI. CSS class = rm-st-<value>.
RM_STATUSES = [
    ('planned', 'Đang lập kế hoạch'),
    ('in_progress', 'Đang thực hiện'),
    ('done', 'Hoàn thành'),
    ('blocked', 'Bị chặn'),
]
RM_STATUS_VALUES = {v for v, _ in RM_STATUSES}

# Người phụ trách (PIC) = QA team theo tên hiển thị + Hiền (manager).
RM_PEOPLE = [display_name(u) for u in USERS] + ['Hiền']

ROADMAP_DEFAULT = [
    {'id': 'p_demo1', 'title': 'Tăng test coverage luồng Chi Hộ',
     'desc': 'Bổ sung & chuẩn hoá test case cho luồng Chi Hộ giai đoạn 2.',
     'status': 'in_progress', 'pic': 'Thành', 'due': '2026-07-15', 'tasks': [
        {'id': 't_demo1', 'title': 'Rà soát test case hiện có', 'pic': 'Quang', 'done': True, 'subs': [
            {'id': 's_demo1', 'title': 'Liệt kê case Core', 'done': True},
            {'id': 's_demo2', 'title': 'Liệt kê case Chi Hộ', 'done': True},
        ]},
        {'id': 't_demo2', 'title': 'Bổ sung case thiếu', 'pic': 'Nhung', 'done': False, 'subs': []},
     ]},
    {'id': 'p_demo2', 'title': 'Tự động hoá smoke test',
     'desc': 'Dựng bộ smoke test tự động chạy mỗi lần deploy.',
     'status': 'planned', 'pic': 'Quang', 'due': '2026-09-30', 'tasks': []},
]


# ===== Validation (schema mới) =====
def _valid_leaf(l):
    return (isinstance(l, dict)
            and isinstance(l.get('title', ''), str)
            and isinstance(l.get('desc', ''), str)
            and isinstance(l.get('done', False), bool)
            and isinstance(l.get('id', ''), str))


def _valid_sub(s):
    if not isinstance(s, dict):
        return False
    if not (isinstance(s.get('title', ''), str)
            and isinstance(s.get('desc', ''), str)
            and isinstance(s.get('done', False), bool)
            and isinstance(s.get('id', ''), str)):
        return False
    leaves = s.get('leaves', [])
    return isinstance(leaves, list) and all(_valid_leaf(l) for l in leaves)


def _valid_task(t):
    if not isinstance(t, dict):
        return False
    if not (isinstance(t.get('title', ''), str)
            and isinstance(t.get('desc', ''), str)
            and isinstance(t.get('pic', ''), str)
            and isinstance(t.get('done', False), bool)
            and isinstance(t.get('id', ''), str)):
        return False
    subs = t.get('subs', [])
    return isinstance(subs, list) and all(_valid_sub(s) for s in subs)


def _valid_plan(p):
    if not isinstance(p, dict):
        return False
    if not (isinstance(p.get('title', ''), str)
            and isinstance(p.get('desc', ''), str)
            and isinstance(p.get('status', 'planned'), str)
            and isinstance(p.get('pic', ''), str)
            and isinstance(p.get('due', ''), str)
            and isinstance(p.get('id', ''), str)):
        return False
    tasks = p.get('tasks', [])
    return isinstance(tasks, list) and all(_valid_task(t) for t in tasks)


def _node_count(data):
    n = 0
    for p in data:
        n += 1 + len(p.get('tasks') or [])
        for t in (p.get('tasks') or []):
            n += len(t.get('subs') or [])
            for s in (t.get('subs') or []):
                n += len(s.get('leaves') or [])
    return n


def valid_roadmap(data):
    if not isinstance(data, list) or len(data) > MAX_PLANS:
        return False
    if not all(_valid_plan(p) for p in data):
        return False
    return _node_count(data) <= MAX_ITEMS


# ===== Helpers (done/status) =====
def sub_done(s):
    leaves = s.get('leaves') or []
    if leaves:
        return all(bool(l.get('done')) for l in leaves)
    return bool(s.get('done'))


def sub_started(s):
    leaves = s.get('leaves') or []
    if leaves:
        return any(bool(l.get('done')) for l in leaves)
    return bool(s.get('done'))


def task_done(t):
    """Task xong = có sub thì mọi sub xong; không sub thì cờ done của chính nó."""
    subs = t.get('subs') or []
    if subs:
        return all(sub_done(s) for s in subs)
    return bool(t.get('done'))


def task_started(t):
    subs = t.get('subs') or []
    if subs:
        return any(sub_done(s) or sub_started(s) for s in subs)
    return bool(t.get('done'))


def plan_done(p):
    tasks = p.get('tasks') or []
    if tasks:
        return all(task_done(t) for t in tasks)
    return p.get('status') == 'done'


def derive_plan_status(p):
    """Status plan: có task -> suy ra (all done->done · có việc chạy->in_progress · else planned);
    không task -> giữ status tay (có thể là blocked/planned do user đặt)."""
    tasks = p.get('tasks') or []
    if not tasks:
        return p.get('status', 'planned')
    if all(task_done(t) for t in tasks):
        return 'done'
    if any(task_started(t) for t in tasks):
        return 'in_progress'
    return 'planned'


# ===== Migration: schema cũ (phase/items/status/progress) -> schema plan mới =====
def _is_legacy(data):
    return (isinstance(data, list)
            and any(isinstance(x, dict) and ('phase' in x or 'items' in x) for x in data))


def _migrate_old_status(st):
    return st if st in RM_STATUS_VALUES else 'planned'


def migrate_roadmap(old):
    """Convert data schema cũ -> mới. Bỏ %/hạn per-node (sub-task thành tick done).
    phase->plan, item->task (done=status==done), subtasks->subs (done=status==done)."""
    plans = []
    for i, ph in enumerate(old or []):
        if not isinstance(ph, dict):
            continue
        tasks = []
        for j, it in enumerate(ph.get('items') or []):
            if not isinstance(it, dict):
                continue
            subs = []
            for k, s in enumerate(it.get('subtasks') or []):
                if isinstance(s, dict):
                    subs.append({'id': f'mig_s{i}_{j}_{k}', 'title': s.get('title', ''),
                                 'done': s.get('status') == 'done'})
            tasks.append({'id': f'mig_t{i}_{j}', 'title': it.get('title', ''), 'pic': '',
                          'done': it.get('status') == 'done', 'subs': subs})
        plan = {'id': f'mig_p{i}', 'title': ph.get('phase', ''), 'desc': '',
                'pic': '', 'due': '', 'tasks': tasks}
        plan['status'] = derive_plan_status(plan)
        plans.append(plan)
    return plans


def _coerce(data):
    """Trả data hợp lệ schema mới (migrate nếu là schema cũ), hoặc None nếu không dùng được."""
    if _is_legacy(data):
        data = migrate_roadmap(data)
    return data if valid_roadmap(data) else None


# ===== Due alerts (plan-level) cho dashboard admin =====
def _parse_due(s):
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def due_alerts(data, today=None, within_days=14):
    """Plan chưa xong mà còn <= within_days tới hạn (gồm quá hạn).
    Trả list {plan, title, due, days_left} sort theo days_left tăng dần."""
    today = today or datetime.now().date()
    out = []
    for p in (data or []):
        if plan_done(p):
            continue
        d = _parse_due(p.get('due', ''))
        if d is None:
            continue
        days = (d - today).days
        if days <= within_days:
            out.append({'plan': p.get('title', ''), 'title': p.get('title', ''),
                        'due': p.get('due', ''), 'days_left': days})
    out.sort(key=lambda a: a['days_left'])
    return out


# ===== Load / save (Jira property primary, file cache fallback) =====
def _read_cache():
    if ROADMAP_FILE.exists():
        try:
            return _coerce(json.loads(ROADMAP_FILE.read_text(encoding='utf-8')))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(data):
    return atomic_write(ROADMAP_FILE, json.dumps(data, ensure_ascii=False, indent=2))


def load_roadmap():
    """Kho chung = Cloudflare KV (sync chéo máy, không cần VPN); file local = fallback offline.
    Data schema cũ được migrate tự động (_coerce) trước khi dùng. Xem remote_store."""
    return synced_load(ROADMAP_PROP, _read_cache, _write_cache,
                       valid_roadmap, ROADMAP_DEFAULT, coerce=_coerce)


def save_roadmap(data):
    """Local-first: ghi file local trước (luôn OK) rồi đẩy KV best-effort. True nếu data đã an
    toàn ở local (kể cả khi KV/VPN down) — không còn fail vì mạng."""
    return synced_save(ROADMAP_PROP, data, _write_cache, valid_roadmap)
