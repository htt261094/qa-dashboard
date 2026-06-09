"""Lớp link Bug / Test-case ↔ Jira task (issue #55, sub của epic #51).

Bug log từ Excel KHÔNG có cột Jira task (xem `_FIELD_MAP` trong bug_log.py). Người dùng
TỰ tạo link trên dashboard: tick các test case → tìm task → bấm "Liên kết với Task".
Link lưu APP-SIDE (Jira user property `qa-dashboard-bug-task-link`, sync chéo máy +
cache local fallback), KHÔNG đụng Excel. Khoá = bug key `{project}#{month}#{bug_no}`.

  { "links": { "<bugKey>": {"task": "PSIT1H26-123", "by": "quangbm", "at": iso}, ... } }

Migration-safe: thiếu `links` -> {}. Concurrent edit 2 máy = last-write-wins (chấp nhận).

Layer: config -> jira_api -> (this). Không cycle (pattern y custom_status.py).
"""
import json
import re
from datetime import datetime

from config import BUG_TASK_LINK_FILE, username_from_email
from jira_api import load_property, save_property

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


def _load_data():
    try:
        data = load_property(LINK_PROP)
        if isinstance(data, dict) and 'links' in data:
            _write_cache(data)
            return data
    except RuntimeError:
        pass
    cached = _read_cache()
    return cached if cached is not None else _empty()


def load_links():
    """{bugKey: {'task','by','at'}} — link hiện tại. {} nếu chưa có."""
    return _load_data().get('links', {})


def valid_task_key(task):
    return bool(_KEY_RE.match((task or '').strip()))


def set_task_links(email, bug_keys, task_key):
    """Gán `task_key` cho list `bug_keys` (hoặc GỠ link nếu task_key=''). Author = người
    đăng nhập (không cần PAT — đây là lớp app-side, không ghi Jira).

    Trả {bugKey: task_or_empty} cho các key vừa đổi nếu lưu được lên Jira; None nếu lỗi
    (caller phân biệt fail vs map rỗng). Khoá không hợp lệ trong list -> bỏ qua."""
    if not isinstance(bug_keys, list) or not bug_keys:
        return None
    task_key = (task_key or '').strip()
    if task_key and not valid_task_key(task_key):
        return None
    data = _load_data()
    links = data.setdefault('links', {})
    username = username_from_email(email) or 'local'
    iso = datetime.now().isoformat()
    out = {}
    for k in bug_keys:
        if not isinstance(k, str) or not k:
            continue
        if task_key:
            links[k] = {'task': task_key, 'by': username, 'at': iso}
            out[k] = task_key
        else:
            links.pop(k, None)
            out[k] = ''
    if not out:
        return None
    try:
        save_property(LINK_PROP, data)
    except RuntimeError:
        return None
    _write_cache(data)
    return out
