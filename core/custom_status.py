"""Custom status (lớp overlay) cho task — phong phú hơn status Jira nghèo nàn.

QA gắn nhãn tình trạng thật của task (vd 'Dev đang fix bug', 'Chờ BA confirm') NGAY
trên dashboard. Đây là lớp PHỦ local, KHÔNG đụng status Jira thật (mấy nhãn này Jira
không có). Mỗi lần đổi -> ghi 1 sự kiện vào activity log để gộp vào block Hoạt động
(admin mở dashboard thấy ai vừa đổi gì).

Mỗi task gắn được NHIỀU nhãn cùng lúc (vd vừa 'Chờ deploy test' vừa 'Chờ data test').
Lưu = Jira user property `qa-dashboard-custom-status` (sync chéo máy), cache local fallback:
  {
    "status":   { "KEY-1": {"v": ["dev_fixing","wait_data"], "by": "quangbm", "at": iso}, ... },
    "activity": [ {"id","key","summary","by","author","when","new"}, ... ]  # cap + prune
  }
Migration-safe: `v` cũ là string đơn -> đọc như list 1 phần tử (`values_of`).

Layer: config -> jira_api -> (this). Không cycle.
"""
import json
from datetime import datetime, timedelta

from config import SCRIPT_DIR, username_from_email, display_name
from jira_api import load_property, save_property

CUSTOM_PROP = 'qa-dashboard-custom-status'
CACHE_FILE = SCRIPT_DIR / '.custom_status.json'
_ACT_CAP = 200          # giữ tối đa 200 sự kiện gần nhất
_ACT_PRUNE_DAYS = 14    # bỏ sự kiện cũ hơn 14 ngày

# (value, label) — value đi vào data-*, label hiển thị. '' = gỡ nhãn.
# 4 cái đầu theo yêu cầu; còn lại là tình huống QA Bảo Kim hay gặp.
CUSTOM_STATUSES = [
    ('dev_fixing',  'Dev fix bug'),
    ('wait_ba',     'Chờ BA confirm'),
    ('dev_busy',    'Dev có priority cao hơn'),
    ('pm_paused',   'PM tạm dừng'),
    ('wait_deploy', 'Chờ deploy test'),
    ('wait_review', 'Chờ review/UAT'),
    ('wait_data',   'Chờ data test'),
    ('reopened',    'Bug reopen'),
]
_LABELS = dict(CUSTOM_STATUSES)
_VALID = set(_LABELS)


def label_of(value):
    return _LABELS.get(value, value)


def is_valid(value):
    return value == '' or value in _VALID


def values_of(entry):
    """Chuẩn hoá nhãn của 1 task -> list value hợp lệ. Migration-safe:
    `v` cũ là string đơn -> [v]; mới là list -> lọc hợp lệ; thiếu -> []."""
    if not entry:
        return []
    v = entry.get('v')
    if isinstance(v, list):
        return [x for x in v if x in _VALID]
    if isinstance(v, str) and v in _VALID:
        return [v]
    return []


# ----- storage -----
def _read_cache():
    if CACHE_FILE.exists():
        try:
            d = json.loads(CACHE_FILE.read_text(encoding='utf-8'))
            if isinstance(d, dict):
                return d
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(data):
    try:
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        pass


def _empty():
    return {'status': {}, 'activity': []}


def _load_data():
    """Source of truth = Jira property; fallback cache local khi Jira lỗi."""
    try:
        data = load_property(CUSTOM_PROP)
        if isinstance(data, dict) and 'status' in data:
            _write_cache(data)
            return data
    except RuntimeError:
        pass
    cached = _read_cache()
    return cached if cached is not None else _empty()


def load_overlay():
    """{KEY: {'v','by','at'}} — nhãn custom hiện tại của từng task. {} nếu chưa có."""
    return _load_data().get('status', {})


def set_custom_status(email, key, value, summary=''):
    """TOGGLE 1 nhãn custom cho task `key`. Ghi activity. Trả LIST nhãn mới (sau toggle)
    nếu lưu được lên Jira, None nếu lỗi (caller phân biệt fail vs list rỗng).

    value='' -> gỡ HẾT nhãn. value hợp lệ -> bật nếu chưa có, tắt nếu đang có.
    Author lấy từ email đăng nhập (ai bấm), KHÔNG cần PAT.
    """
    if not key or not is_valid(value):
        return None
    data = _load_data()
    statuses = data.setdefault('status', {})
    activity = data.setdefault('activity', [])
    username = username_from_email(email) or 'local'
    author = display_name(username) if username != 'local' else 'Bạn'
    now = datetime.now()
    iso = now.isoformat()
    cur = values_of(statuses.get(key))
    if value == '':
        statuses.pop(key, None)
        cur = []
        desc = '— (gỡ hết nhãn)'
    else:
        if value in cur:
            cur.remove(value)
            desc = '✕ ' + label_of(value)
        else:
            cur.append(value)
            desc = label_of(value)
        if cur:
            statuses[key] = {'v': cur, 'by': username, 'at': iso}
        else:
            statuses.pop(key, None)
    activity.insert(0, {
        'id': f"{key}#cstat#{now.strftime('%Y%m%d%H%M%S%f')}",
        'key': key, 'summary': summary or '', 'by': username, 'author': author,
        'when': iso, 'new': desc,
    })
    # prune theo thời gian + cap số lượng
    cutoff = (now - timedelta(days=_ACT_PRUNE_DAYS)).isoformat()
    data['activity'] = [a for a in activity if a.get('when', '') >= cutoff][:_ACT_CAP]
    try:
        save_property(CUSTOM_PROP, data)
    except RuntimeError:
        return None
    _write_cache(data)
    return cur


def _filter_activity(activity, scope_user, days):
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    out = []
    for a in activity:
        if a.get('when', '') < cutoff:
            continue
        if scope_user and a.get('by') != scope_user:
            continue
        item = dict(a)
        item['kind'] = 'custom_status'
        out.append(item)
    return out


def load_custom_activity(scope_user=None, days=7):
    """Sự kiện đổi custom status, shape giống feed item (kind='custom_status').
    scope_user=None (admin) -> tất cả; 'quangbm' -> chỉ sự kiện do người đó đổi."""
    return _filter_activity(_load_data().get('activity', []), scope_user, days)


def load_bundle(scope_user=None, days=7):
    """1 lần đọc property -> (overlay_map, activity_list). Dùng ở dashboard `/` (đỡ đọc 2 lần)."""
    data = _load_data()
    return data.get('status', {}), _filter_activity(data.get('activity', []), scope_user, days)
