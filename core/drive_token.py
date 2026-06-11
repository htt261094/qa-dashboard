"""Lưu refresh_token Google Drive của admin — mã hoá at-rest (issue #52).

Một token duy nhất (của admin, vd thanhht1@) cho phép background thread đọc file
.xlsx bug log trên Drive bằng quyền admin. KHÔNG phải token per-user như PAT —
file là Drive công ty, chỉ cần 1 token đọc.

Nguồn lưu = Jira user property `qa-dashboard-drive-token` = {"rt": enc_refresh_token}.
Mã hoá Fernet (crypto_util) như pat_store. Cache local `.drive_token.json` fallback khi
Jira lỗi. KHÔNG plaintext, KHÔNG log token.

Layer: config -> {jira_api, crypto_util} -> (this). Không cycle.
"""
import json

from config import DRIVE_TOKEN_FILE
from jira_api import load_property, save_property
from crypto_util import encrypt, decrypt

DRIVE_TOKEN_PROP = 'qa-dashboard-drive-token'


def _read_cache():
    if DRIVE_TOKEN_FILE.exists():
        try:
            data = json.loads(DRIVE_TOKEN_FILE.read_text(encoding='utf-8'))
            if isinstance(data, dict) and isinstance(data.get('rt'), str):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(data):
    try:
        DRIVE_TOKEN_FILE.write_text(json.dumps(data), encoding='utf-8')
        try:
            DRIVE_TOKEN_FILE.chmod(0o600)  # siết quyền (no-op trên Windows)
        except OSError:
            pass
    except OSError:
        pass


def save_refresh_token(refresh_token):
    """Mã hoá + lưu refresh_token. Trả (ok: bool, msg: str). KHÔNG log token."""
    rt = (refresh_token or '').strip()
    if not rt:
        return False, 'Google không trả refresh_token. Hãy thử lại (đảm bảo bấm đồng ý lại quyền).'
    payload = {'rt': encrypt(rt)}
    try:
        save_property(DRIVE_TOKEN_PROP, payload)
    except RuntimeError:
        return False, 'Không lưu được lên Jira (lỗi mạng). Thử lại sau.'
    _write_cache(payload)
    return True, 'Đã kết nối Drive. Background sync sẽ đọc file bug log bằng quyền admin.'


def load_refresh_token():
    """refresh_token gốc (giải mã); None nếu chưa kết nối / giải mã hỏng.

    Source of truth = Jira property; local cache = fallback khi Jira lỗi."""
    payload = None
    try:
        data = load_property(DRIVE_TOKEN_PROP)
        if isinstance(data, dict) and isinstance(data.get('rt'), str):
            payload = data
            _write_cache(data)
    except RuntimeError:
        pass  # Jira không với tới -> dùng cache
    if payload is None:
        payload = _read_cache()
    if payload is None:
        return None
    return decrypt(payload['rt'])


def has_drive_token():
    """True nếu đã kết nối Drive (có token ở Jira property hoặc cache local)."""
    try:
        data = load_property(DRIVE_TOKEN_PROP)
        if isinstance(data, dict) and isinstance(data.get('rt'), str):
            return True
    except RuntimeError:
        pass
    return _read_cache() is not None


def delete_drive_token():
    """Ngắt kết nối Drive: xoá property + cache. Trả True nếu xoá xong (hoặc đã trống)."""
    ok = True
    try:
        save_property(DRIVE_TOKEN_PROP, {})
    except RuntimeError:
        ok = False
    try:
        if DRIVE_TOKEN_FILE.exists():
            DRIVE_TOKEN_FILE.unlink()
    except OSError:
        pass
    return ok
