"""Lớp link Bộ test case ↔ Jira task (issue #155, sub của epic #151).

Chốt khi bàn (issue #155): link ở mức **CẢ BỘ (folder)**, KHÔNG per-case. Khoá =
`folder_id` của bộ test case (top folder trong testcase_store). 1 bộ link tới NHIỀU task.

Store RIÊNG (không dùng chung với bug-task-link) để tách namespace: bug key dạng
`{project}#{month}#{bug_no}` vs folder id `f_<hex>` — tránh đụng khoá. Pattern y hệt
`task_link.py`: Cloudflare KV (sync chéo máy) + cache local fallback.

  { "links": { "<folderId>": {"tasks": ["PSIT1H26-123", ...], "by": "quangbm", "at": iso}, ... } }

Migration-safe: thiếu `links` -> {}. Concurrent edit 2 máy = last-write-wins (chấp nhận).

Layer: config -> jira_api -> remote_store -> (this). Không cycle (pattern y task_link.py).
"""
import json
import re
from datetime import datetime

from config import TESTCASE_TASK_LINK_FILE, username_from_email, atomic_write
from remote_store import synced_load, synced_save

TC_LINK_PROP = 'qa-dashboard-testcase-task-link'
_KEY_RE = re.compile(r'^[A-Za-z][A-Za-z0-9]*-\d+$')   # PROJ-123 (key Jira hợp lệ)


# ----- storage (Cloudflare KV = source of truth; cache local = fallback) -----
def _read_cache():
    if TESTCASE_TASK_LINK_FILE.exists():
        try:
            d = json.loads(TESTCASE_TASK_LINK_FILE.read_text(encoding='utf-8'))
            if isinstance(d, dict) and 'links' in d:
                return d
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(data):
    atomic_write(TESTCASE_TASK_LINK_FILE, json.dumps(data, ensure_ascii=False, indent=2))


def _empty():
    return {'links': {}}


def _valid_data(d):
    return isinstance(d, dict) and 'links' in d


def _load_data():
    """Kho chung = Cloudflare KV (sync chéo máy); cache local = fallback offline."""
    return synced_load(TC_LINK_PROP, _read_cache, _write_cache, _valid_data, _empty())


def load_links():
    """{folderId: {'tasks','by','at'}} — link hiện tại. {} nếu chưa có."""
    return _load_data().get('links', {})


def tasks_of(link_val):
    """List task keys của 1 entry link. Luôn trả list (có thể rỗng)."""
    if not isinstance(link_val, dict):
        return []
    ts = link_val.get('tasks')
    if isinstance(ts, list):
        return [t for t in ts if isinstance(t, str) and t]
    return []


def valid_task_key(task):
    return bool(_KEY_RE.match((task or '').strip()))


def set_folder_links(email, folder_id, task_key, op='add'):
    """Đổi link task của 1 bộ test case (`folder_id`). Author = người đăng nhập (không
    cần PAT — lớp app-side, không ghi Jira). 1 bộ link tới NHIỀU task.

    `task_key` nhận str (1 task) HOẶC list[str] (cho 'add'/'remove').
    op:
      'add'    -> thêm task(s) vào tasks của bộ (idempotent)
      'remove' -> gỡ task(s) khỏi tasks của bộ
      'clear'  -> gỡ HẾT task của bộ (`task_key` bỏ qua)

    Trả list[str] tasks MỚI của bộ nếu lưu được; None nếu input không hợp lệ."""
    folder_id = (folder_id or '').strip()
    if not folder_id:
        return None
    raw = task_key if isinstance(task_key, list) else [task_key]
    task_keys = [t.strip() for t in raw if isinstance(t, str) and t.strip()]
    if op in ('add', 'remove'):
        if not task_keys or not all(valid_task_key(t) for t in task_keys):
            return None
    data = _load_data()
    links = data.setdefault('links', {})
    username = username_from_email(email) or 'local'
    iso = datetime.now().isoformat()
    cur = tasks_of(links.get(folder_id))
    if op == 'add':
        for t in task_keys:
            if t not in cur:
                cur.append(t)
    elif op == 'remove':
        cur = [t for t in cur if t not in task_keys]
    else:  # clear
        cur = []
    if cur:
        links[folder_id] = {'tasks': cur, 'by': username, 'at': iso}
    else:
        links.pop(folder_id, None)
    # Local-first: luôn an toàn ở local, đẩy KV best-effort.
    synced_save(TC_LINK_PROP, data, _write_cache, _valid_data)
    return cur


def folders_for_task(task_key):
    """Chiều ngược: list folder_id của các bộ ĐÃ LINK tới `task_key`. [] nếu lỗi/không có."""
    task_key = (task_key or '').strip()
    if not task_key:
        return []
    try:
        links = load_links()
    except Exception:
        return []
    return [fid for fid, v in links.items() if task_key in tasks_of(v)]
