"""Overlay status VỪA GHI — hiện ngay trạng thái mới, không chờ Jira/cache bắt kịp
(Decision #90).

Vấn đề: sau khi đổi status thành công, client đã vá tại chỗ (#24) nhưng mọi lần render
SAU đó lại đọc lại status từ Jira, mà có 2 tầng trễ:
  1. cache SWR (`_CACHE_TTL=120s`, stale tới 900s) + snapshot KV/đĩa (#84) — chuyển tab
     hoặc máy khác mở là ra data cũ;
  2. search index của Jira (`/rest/api/2/search`) lag vài giây sau transition — F5 ngay
     (force=True, bỏ qua cache) vẫn có thể trả status cũ.
→ user thấy trạng thái "nhảy về" giá trị cũ.

Cách xử: nhớ `{key: {status, at}}` trong RAM process khi ghi thành công, rồi vá lên mọi
issue đọc từ Jira trước khi render. Override tự hết khi:
  - `updated` của issue >= thời điểm ghi (data đã bao gồm thao tác của mình → tin Jira,
    kể cả khi người khác đổi tiếp sang status khác);
  - hoặc quá `_TTL` (backstop, khớp cửa sổ stale của SWR).

Ranh giới có chủ đích:
  - CHỈ status Jira. Nhãn nội bộ đã là store local (#21) nên không cần; duedate vẫn theo
    hành vi cũ (vá client-side).
  - RAM per-process, KHÔNG sync chéo máy: đúng trọng tâm — trễ nằm ở cache/index của
    CHÍNH process đang serve; máy khác có snapshot riêng và sẽ tự tươi.
  - Chỉ ghi đè TÊN status, không dựng lại `statusCategory` (không chỗ nào đọc field đó).

Layer: config -> issues -> (this) -> jira_api.
"""
import threading
from datetime import datetime, timedelta

from issues import parse_date, i_status, i_updated

_TTL = 900        # giây — bằng _CACHE_STALE_TTL (jira_api): quá đó thì cache cũng hết stale
_SKEW = 2         # giây — bù lệch giây/truncate khi so `updated` với thời điểm ghi

_lock = threading.Lock()
_pending = {}     # key -> {'status': name, 'at': datetime}


def record(key, status):
    """Ghi nhận status vừa set thành công cho `key`."""
    if not key or not status:
        return
    with _lock:
        _pending[str(key)] = {'status': str(status), 'at': datetime.now()}


def drop(key):
    with _lock:
        _pending.pop(str(key), None)


def _prune(now):
    """Bỏ override quá hạn. Caller GIỮ lock."""
    for k in [k for k, v in _pending.items() if v['at'] + timedelta(seconds=_TTL) < now]:
        _pending.pop(k, None)


def pending():
    """Bản chụp override còn hiệu lực: {key: {'status','at'}}."""
    now = datetime.now()
    with _lock:
        if not _pending:
            return {}
        _prune(now)
        return {k: dict(v) for k, v in _pending.items()}


def patch_issues(issues):
    """Vá `fields.status.name` cho các issue có override còn hiệu lực. MUTATE tại chỗ
    (issue nằm trong cache SWR → vá luôn để mọi bản copy trong RAM thống nhất)."""
    pend = pending()
    if not pend or not issues:
        return issues
    for iss in issues:
        if not isinstance(iss, dict):
            continue
        ov = pend.get(iss.get('key'))
        if not ov:
            continue
        upd = parse_date(i_updated(iss))
        if upd and upd + timedelta(seconds=_SKEW) >= ov['at']:
            # Data này đã bao gồm thao tác của mình (hoặc mới hơn) → Jira là chân lý.
            drop(iss.get('key'))
            pend.pop(iss.get('key'), None)
            continue
        if i_status(iss) == ov['status']:
            continue
        fields = iss.setdefault('fields', {})
        st = fields.get('status')
        if not isinstance(st, dict):
            st = {}
            fields['status'] = st
        st['name'] = ov['status']
    return issues


def patch_data(data):
    """Vá 3 bucket của `fetch_all`/snapshot (active/new24/done_week) tại chỗ."""
    if not isinstance(data, dict):
        return data
    if not pending():
        return data
    for k in ('active', 'new24', 'done_week'):
        patch_issues(data.get(k) or [])
    return data


def patch_status_map(statuses):
    """Vá map {key: status} của activity feed (#24 — patch real-time cho client).

    Feed KHÔNG fetch field `updated` nên ở đây không so được mốc thời gian; chỉ áp
    override còn trong `_pending` — vòng đời do `patch_issues` (bucket có `updated`) và
    `_TTL` quyết định."""
    pend = pending()
    if not pend or not isinstance(statuses, dict):
        return statuses
    for key, ov in pend.items():
        if key in statuses:
            statuses[key] = ov['status']
    return statuses
