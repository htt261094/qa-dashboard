"""Lưu refresh_token Google Drive của admin — mã hoá at-rest (issue #52).

Một token duy nhất (của admin, vd thanhht1@) cho phép background thread đọc file
.xlsx bug log trên Drive bằng quyền admin. KHÔNG phải token per-user như PAT —
file là Drive công ty, chỉ cần 1 token đọc.

Kho chung = Cloudflare KV `qa-dashboard-drive-token` = {"rt": enc_refresh_token} (sync chéo
máy, không cần VPN — xem remote_store). Mã hoá Fernet (crypto_util) như pat_store. Cache local
`.drive_token.json` fallback offline. KHÔNG plaintext, KHÔNG log token.

Layer: config -> {crypto_util, remote_store} -> (this). Không cycle.
"""
import json

from config import DRIVE_TOKEN_FILE, atomic_write
from remote_store import synced_load, synced_save, synced_delete
from crypto_util import encrypt, decrypt

DRIVE_TOKEN_PROP = 'qa-dashboard-drive-token'


def _valid(d):
    return isinstance(d, dict)


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
    res = atomic_write(DRIVE_TOKEN_FILE, json.dumps(data))
    if res:
        try:
            DRIVE_TOKEN_FILE.chmod(0o600)  # siết quyền (no-op trên Windows)
        except OSError:
            pass
    return res


def _load():
    """Payload {'rt': enc} hoặc {} (chưa kết nối). KV (sync chéo máy) + cache local fallback."""
    return synced_load(DRIVE_TOKEN_PROP, _read_cache, _write_cache, _valid, {})


def save_refresh_token(refresh_token):
    """Mã hoá + lưu refresh_token. Trả (ok: bool, msg: str). KHÔNG log token."""
    rt = (refresh_token or '').strip()
    if not rt:
        return False, 'Google không trả refresh_token. Hãy thử lại (đảm bảo bấm đồng ý lại quyền).'
    synced_save(DRIVE_TOKEN_PROP, {'rt': encrypt(rt)}, _write_cache, _valid)  # local-first
    return True, 'Đã kết nối Drive. Background sync sẽ đọc file bug log bằng quyền admin.'


def load_refresh_token():
    """refresh_token gốc (giải mã); None nếu chưa kết nối / giải mã hỏng."""
    payload = _load()
    rt = payload.get('rt') if isinstance(payload, dict) else None
    return decrypt(rt) if isinstance(rt, str) else None


def has_drive_token():
    """True nếu đã kết nối Drive (có token ở KV hoặc cache local)."""
    payload = _load()
    return isinstance(payload, dict) and isinstance(payload.get('rt'), str)


def delete_drive_token():
    """Ngắt kết nối Drive: xoá hẳn key trên KV + cache local. Trả True."""
    synced_delete(DRIVE_TOKEN_PROP,
                  lambda: DRIVE_TOKEN_FILE.exists() and DRIVE_TOKEN_FILE.unlink())
    return True
