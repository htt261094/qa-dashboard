"""Kho sync chéo máy — local-first, KHÔNG phụ thuộc VPN.

Bối cảnh (Decision: cloudflare-kv-store): roadmap/docs/custom-status/PAT là data tự-soạn,
trước lưu Jira user property làm kho chung -> Jira sau VPN nên mất VPN = save FAIL (return
False, data không lưu nổi). Module này thay kho chung bằng **Cloudflare Workers KV** (đọc/ghi
trực tiếp qua REST API api.cloudflare.com — internet công cộng, sống cả khi Jira/VPN down),
và đảo nguyên tắc ghi sang **local-first**:

  - save: ghi file local TRƯỚC (luôn thành công) -> đẩy lên KV best-effort -> dirty-flag nếu
    KV không với tới (flush ở lần load/save kế tiếp khi KV sống lại). Save KHÔNG còn fail vì mạng.
  - load: KV thắng khi với tới được + local KHÔNG dirty (KV = bản mới nhất do host trước ghi);
    KV rỗng -> seed từ local (hoặc Jira 1 lần để migrate); KV không với tới -> dùng local.

Mô hình host-migration (1 instance/lúc, lúc Mac lúc Win) -> KHÔNG ghi đồng thời -> "KV thắng
khi sạch + dirty-flag carry edit offline" là đủ đúng, không cần timestamp. Giới hạn cố hữu:
host ghi local rồi chết trước khi flush, lại sửa tiếp ở host khác -> LWW có thể bỏ edit chưa
flush (hiếm với 1 admin, đã chấp nhận).

Bỏ trống creds CF (KV_ENABLED=False) => fallback Jira property như cũ, NHƯNG vẫn local-first
nên save vẫn không fail vì mạng. jira_api import LAZY (trong hàm) để KHÔNG tạo vòng import
(jira_api có thể import module này).

Layer: config -> (this); jira_api nạp lazy. KHÔNG cycle.
"""
import json
import time
import hashlib
import threading
from urllib.parse import quote

from config import (KV_ENABLED, CF_ACCOUNT_ID, CF_KV_NAMESPACE_ID, CF_API_TOKEN,
                    SYNC_META_FILE, atomic_write)

try:
    import requests
except ImportError:  # config/jira_api đã xử lý thông báo; ở đây chỉ phòng thủ
    requests = None

_KV_BASE = (f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}"
            f"/storage/kv/namespaces/{CF_KV_NAMESPACE_ID}") if KV_ENABLED else ''
_CF_SESSION = requests.Session() if (requests and KV_ENABLED) else None
_TIMEOUT = (5, 15)  # (connect, read) — fail nhanh khi mạng treo, khỏi block server

# Retry trên connection/read error: VPN flip làm socket keep-alive chết -> tự lấy socket mới
# thay vì kẹt (cùng lý do #139 ở _SESSION Jira). KV qua internet công cộng nhưng socket vẫn
# chết khi network đổi. urllib3 cũ thiếu Retry -> bỏ qua (giữ session thường).
if _CF_SESSION is not None:
    try:
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        _cf_adapter = HTTPAdapter(max_retries=Retry(
            total=3, connect=3, read=2, status=0, redirect=0,
            backoff_factor=0.3, raise_on_status=False, allowed_methods=None))
        _CF_SESSION.mount('https://', _cf_adapter)
    except ImportError:
        pass


def _redact(msg):
    """Không bao giờ để CF token lọt ra log/error."""
    return msg.replace(CF_API_TOKEN, '<REDACTED>') if CF_API_TOKEN else msg


def _cf_headers(content_type=None):
    h = {'Authorization': f'Bearer {CF_API_TOKEN}'}
    if content_type:
        h['Content-Type'] = content_type
    return h


# ===== Cloudflare KV low-level =====
def _kv_get(key):
    """Đọc value JSON từ KV. None nếu 404 (chưa có)/giá trị hỏng. Raise RuntimeError nếu lỗi mạng."""
    url = f"{_KV_BASE}/values/{quote(key, safe='')}"
    try:
        r = _CF_SESSION.get(url, headers=_cf_headers(), timeout=_TIMEOUT)
        if r.status_code == 404:
            return None
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"KV error: {_redact(str(e))}")
    try:
        return json.loads(r.text)
    except ValueError:
        return None  # value rác trong KV -> coi như chưa có


def _kv_put(key, value):
    """Ghi value JSON vào KV. Raise RuntimeError nếu KV từ chối/lỗi mạng."""
    url = f"{_KV_BASE}/values/{quote(key, safe='')}"
    try:
        r = _CF_SESSION.put(url, headers=_cf_headers('text/plain'),
                            data=json.dumps(value, ensure_ascii=False).encode('utf-8'),
                            timeout=_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"KV error: {_redact(str(e))}")


def _kv_delete(key):
    """Xoá key khỏi KV (giải phóng chỗ — KV free tier hữu hạn). 404 coi như đã xoá.
    Raise RuntimeError nếu lỗi mạng/từ chối."""
    url = f"{_KV_BASE}/values/{quote(key, safe='')}"
    try:
        r = _CF_SESSION.delete(url, headers=_cf_headers(), timeout=_TIMEOUT)
        if r.status_code == 404:
            return
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"KV error: {_redact(str(e))}")


# ===== Remote backend (KV nếu cấu hình, else Jira property — nạp lazy) =====
def _remote_get(key):
    """Đọc từ kho remote. None nếu chưa có. Raise RuntimeError nếu remote không với tới."""
    if KV_ENABLED:
        return _kv_get(key)
    from jira_api import load_property  # lazy -> tránh vòng import
    return load_property(key)


def _remote_put(key, value):
    if KV_ENABLED:
        _kv_put(key, value)
        return
    from jira_api import save_property
    save_property(key, value)


def _remote_delete(key):
    """Xoá key trên kho remote. Jira: ghi None/rỗng (DC không có DELETE property tiện) ->
    dùng save {} để 'trống'. KV: DELETE thật."""
    if KV_ENABLED:
        _kv_delete(key)
        return
    from jira_api import save_property
    save_property(key, {})


# Public wrappers — cho module GIỮ logic merge/format riêng (bug_log_store union-merge,
# dismiss per-user) nhưng vẫn đẩy lên KV thay Jira. KHÔNG qua local-first LWW (sẽ sai metric).
def remote_get(key):
    """Đọc value từ kho chung (KV/Jira). None nếu chưa có. Raise RuntimeError nếu không với tới."""
    return _remote_get(key)


def remote_put(key, value):
    """Ghi value lên kho chung. Raise RuntimeError nếu không với tới."""
    _remote_put(key, value)


def remote_delete(key):
    """Xoá key khỏi kho chung. Raise RuntimeError nếu không với tới."""
    _remote_delete(key)


def _jira_migrate(key, validate):
    """Đọc Jira property 1 lần để migrate data cũ sang KV (chỉ khi KV bật + KV rỗng + local rỗng).
    Cần VPN; không với tới -> None (bỏ qua, dùng default)."""
    if not KV_ENABLED:
        return None
    try:
        from jira_api import load_property
        data = load_property(key)
    except RuntimeError:
        return None
    return data if (data is not None and validate(data)) else None


# ===== Pending tracking (.sync_meta.json) =====
# 'dirty'   = key có edit local CHƯA đẩy lên kho chung (put khi KV với tới lại).
# 'deleted' = key đã xoá local nhưng CHƯA xoá được trên KV (delete khi KV với tới lại).
# Hai tập loại trừ nhau theo key (put xoá khỏi deleted; delete xoá khỏi dirty).
_meta_lock = threading.Lock()


def _load_meta():
    if SYNC_META_FILE.exists():
        try:
            d = json.loads(SYNC_META_FILE.read_text(encoding='utf-8'))
            if isinstance(d, dict):
                d.setdefault('dirty', [])
                d.setdefault('deleted', [])
                d.setdefault('hashes', {})
                if (isinstance(d['dirty'], list) and isinstance(d['deleted'], list)
                        and isinstance(d['hashes'], dict)):
                    return d
        except (json.JSONDecodeError, OSError):
            pass
    return {'dirty': [], 'deleted': [], 'hashes': {}}


def _hash(value):
    """Hash ổn định của value để bỏ qua PUT khi data KHÔNG đổi (tiết kiệm quota write KV)."""
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _set_hash(key, h):
    with _meta_lock:
        meta = _load_meta()
        if h is None:
            meta['hashes'].pop(key, None)
        else:
            meta['hashes'][key] = h
        _save_meta(meta)


def _get_hash(key):
    return _load_meta()['hashes'].get(key)


def _save_meta(meta):
    atomic_write(SYNC_META_FILE, json.dumps(meta, ensure_ascii=False))


def _mark(key, *, dirty=None, deleted=None):
    """Cập nhật cờ dirty/deleted cho key. dirty và deleted loại trừ nhau."""
    with _meta_lock:
        meta = _load_meta()
        ds, xs = set(meta['dirty']), set(meta['deleted'])
        if dirty is True:
            ds.add(key); xs.discard(key)
        elif dirty is False:
            ds.discard(key)
        if deleted is True:
            xs.add(key); ds.discard(key)
        elif deleted is False:
            xs.discard(key)
        meta['dirty'], meta['deleted'] = sorted(ds), sorted(xs)
        _save_meta(meta)


def _is_dirty(key):
    return key in _load_meta()['dirty']


def _flush_deletes():
    """Thử xoá lại các key pending-delete (KV trước đó không với tới). Không cần value nên
    flush được generic; dirty-put thì flush trong synced_load vì cần đọc cache của key đó."""
    pending = _load_meta()['deleted']
    for key in list(pending):
        try:
            _remote_delete(key)
            _mark(key, deleted=False)
        except RuntimeError:
            break  # KV vẫn chưa với tới -> để lần sau


# ===== Read-TTL: 1 host đang chạy là writer DUY NHẤT của vòng đời nó -> sau khi đã pull KV,
# phục vụ local, KHÔNG chạm KV mỗi lần load (đỡ quota đọc + latency poll). Chỉ pull lại sau
# _PULL_TTL (bắt kịp host khác đã ghi khi mình offline) hoặc khi process mới khởi động.
_PULL_TTL = 120  # giây
_pull_at: dict = {}      # key -> monotonic lúc pull KV gần nhất
_pull_lock = threading.Lock()


def _pull_fresh(key):
    with _pull_lock:
        t = _pull_at.get(key)
    return t is not None and (time.monotonic() - t) < _PULL_TTL


def _mark_pulled(key):
    with _pull_lock:
        _pull_at[key] = time.monotonic()


# ===== High-level: local-first synced load/save =====
def synced_load(key, read_cache, write_cache, validate, default, coerce=None):
    """Đọc data đồng bộ. `read_cache()` -> data|None (đọc file local), `write_cache(data)`,
    `validate(data)->bool`, `coerce` (optional) chuẩn hoá data remote schema cũ trước validate.

    Quy tắc: KV/remote thắng khi với tới được + local KHÔNG dirty; KV rỗng -> seed từ local
    (hoặc Jira migrate); remote không với tới -> local; cuối cùng -> default."""
    def _norm(d):
        return coerce(d) if (coerce and d is not None) else d

    local = read_cache()

    # Read-TTL: vừa pull KV gần đây + local sạch -> phục vụ local, KHÔNG chạm KV (đỡ quota/latency).
    if _pull_fresh(key) and not _is_dirty(key):
        if local is not None and validate(local):
            return local
        # local rỗng bất thường -> bỏ qua TTL, pull lại bên dưới

    _flush_deletes()
    try:
        rdata = _norm(_remote_get(key))
        remote_ok = True
    except RuntimeError:
        rdata, remote_ok = None, False

    if remote_ok:
        _mark_pulled(key)
        if rdata is not None and validate(rdata):
            if _is_dirty(key) and local is not None and validate(local):
                # local có sửa chưa kịp đẩy -> giữ local, flush lên remote
                try:
                    _remote_put(key, local)
                    _mark(key, dirty=False)
                except RuntimeError:
                    pass
                return local
            write_cache(rdata)
            _set_hash(key, _hash(rdata))   # KV == local giờ -> save y hệt sau này sẽ dedupe
            return rdata
        # remote rỗng -> seed từ local, hoặc Jira (migrate 1 lần), else default
        seed = local if (local is not None and validate(local)) else _jira_migrate(key, validate)
        if seed is not None and validate(seed):
            try:
                _remote_put(key, seed)
                _mark(key, dirty=False)
                _set_hash(key, _hash(seed))
            except RuntimeError:
                _mark(key, dirty=True)
            write_cache(seed)
            return seed
        return default

    # remote không với tới -> dùng local
    if local is not None and validate(local):
        return local
    return default


def synced_save(key, data, write_cache, validate=None):
    """Ghi local TRƯỚC (luôn OK) rồi đẩy remote best-effort. Trả True nếu data đã an toàn ở
    local (kể cả khi remote lỗi -> đánh dirty, flush sau). False chỉ khi validate fail."""
    if validate and not validate(data):
        return False
    write_cache(data)
    _flush_deletes()
    h = _hash(data)
    # Dedupe: data y hệt bản đã đẩy + không dirty -> KV đã có rồi, KHỎI PUT (tiết kiệm quota).
    if not _is_dirty(key) and _get_hash(key) == h:
        _mark_pulled(key)
        return True
    try:
        _remote_put(key, data)
        _mark(key, dirty=False)
        _set_hash(key, h)
        _mark_pulled(key)  # local == remote ngay sau ghi -> khỏi pull lại trong TTL
    except RuntimeError:
        _mark(key, dirty=True)
    return True


def synced_delete(key, clear_cache=None):
    """Xoá hẳn 1 key: xoá cache local (clear_cache) + DELETE trên KV (best-effort; KV down ->
    pending-delete, flush sau). Dùng khi data của key bị xoá toàn bộ (giải phóng chỗ KV)."""
    if clear_cache:
        clear_cache()
    _mark(key, dirty=False)
    _set_hash(key, None)   # drop hash -> tạo lại key sau này sẽ ghi (không dedupe nhầm)
    try:
        _remote_delete(key)
        _mark(key, deleted=False)
    except RuntimeError:
        _mark(key, deleted=True)
    _mark_pulled(key)
    return True
