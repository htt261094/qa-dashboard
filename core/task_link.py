"""Lớp link Bug / Test-case ↔ Jira task (issue #55, sub của epic #51).

Bug log từ Excel KHÔNG có cột Jira task (xem `_FIELD_MAP` trong bug_log.py). Người dùng
TỰ tạo link trên dashboard: tick các test case → tìm task → bấm "Liên kết với Task".
Link lưu APP-SIDE (Jira user property `qa-dashboard-bug-task-link`, sync chéo máy +
cache local fallback), KHÔNG đụng Excel. Khoá = bug key `{project}#{month}#{bug_no}`.

  { "links": { "<bugKey>": {"tasks": ["PSIT1H26-123", ...], "by": "quangbm", "at": iso}, ... } }

1 bug link tới NHIỀU task (issue: 2026-06-10). Migration-safe: link cũ dạng
`{"task": "PROJ-1"}` (1 task string) đọc qua `tasks_of()` thành list 1 phần tử.
Thiếu `links` -> {}. Concurrent edit 2 máy = last-write-wins (chấp nhận).

Layer: config -> jira_api -> (this). Không cycle (pattern y custom_status.py).
"""
import json
import re
from datetime import datetime

from config import BUG_TASK_LINK_FILE, username_from_email
from remote_store import synced_load, synced_save

LINK_PROP = 'qa-dashboard-bug-task-link'
_KEY_RE = re.compile(r'^[A-Za-z][A-Za-z0-9]*-\d+$')   # PROJ-123 (key Jira hợp lệ)


# ----- storage (Jira property = source of truth; cache local = fallback) -----
def _read_cache():
    if BUG_TASK_LINK_FILE.exists():
        try:
            d = json.loads(BUG_TASK_LINK_FILE.read_text(encoding='utf-8'))
            if isinstance(d, dict) and 'links' in d:
                return d
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(data):
    try:
        BUG_TASK_LINK_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        pass


def _empty():
    return {'links': {}}


def _valid_data(d):
    return isinstance(d, dict) and 'links' in d


def _load_data():
    """Kho chung = Cloudflare KV (sync chéo máy, không cần VPN); cache local = fallback offline."""
    return synced_load(LINK_PROP, _read_cache, _write_cache, _valid_data, _empty())


def load_links():
    """{bugKey: {'tasks','by','at'}} — link hiện tại. {} nếu chưa có."""
    return _load_data().get('links', {})


def tasks_of(link_val):
    """List task keys của 1 entry link (migration-safe). Đọc `tasks` (list mới) hoặc
    `task` (string cũ, 1 task) -> luôn trả list (có thể rỗng)."""
    if not isinstance(link_val, dict):
        return []
    ts = link_val.get('tasks')
    if isinstance(ts, list):
        return [t for t in ts if isinstance(t, str) and t]
    t = link_val.get('task')
    return [t] if isinstance(t, str) and t else []


def valid_task_key(task):
    return bool(_KEY_RE.match((task or '').strip()))


def set_task_links(email, bug_keys, task_key, op='add'):
    """Đổi link task của list `bug_keys`. Author = người đăng nhập (không cần PAT —
    đây là lớp app-side, không ghi Jira). 1 bug có thể link NHIỀU task.

    `task_key` nhận str (1 task) HOẶC list[str] (nhiều task, cho 'add'/'remove') —
    multi-select link bar (#55) gửi list để link nhiều task 1 lần.

    op:
      'add'    -> thêm task(s) vào tasks của mỗi bug (idempotent, bỏ qua nếu đã có)
      'remove' -> gỡ task(s) khỏi tasks của mỗi bug
      'clear'  -> gỡ HẾT task của mỗi bug (`task_key` bỏ qua)

    Trả {bugKey: [tasks...]} (trạng thái MỚI) cho các key vừa đổi nếu lưu được lên Jira;
    None nếu lỗi (caller phân biệt fail vs map rỗng). Khoá bug không hợp lệ -> bỏ qua."""
    if not isinstance(bug_keys, list) or not bug_keys:
        return None
    # chuẩn hoá task_key -> list các task hợp lệ (cho add/remove)
    raw = task_key if isinstance(task_key, list) else [task_key]
    task_keys = [t.strip() for t in raw if isinstance(t, str) and t.strip()]
    if op in ('add', 'remove'):
        if not task_keys or not all(valid_task_key(t) for t in task_keys):
            return None
    data = _load_data()
    links = data.setdefault('links', {})
    username = username_from_email(email) or 'local'
    iso = datetime.now().isoformat()
    out = {}
    for k in bug_keys:
        if not isinstance(k, str) or not k:
            continue
        cur = tasks_of(links.get(k))
        if op == 'add':
            for t in task_keys:
                if t not in cur:
                    cur.append(t)
        elif op == 'remove':
            cur = [t for t in cur if t not in task_keys]
        else:  # clear
            cur = []
        if cur:
            links[k] = {'tasks': cur, 'by': username, 'at': iso}
        else:
            links.pop(k, None)
        out[k] = cur
    if not out:
        return None
    # Local-first: luôn an toàn ở local, đẩy KV best-effort (không còn fail vì mạng).
    synced_save(LINK_PROP, data, _write_cache, _valid_data)
    return out
