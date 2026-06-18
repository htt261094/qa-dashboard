"""Lưu PAT cá nhân của từng QA — mã hoá at-rest, để khi họ đổi status/comment thì
Jira ghi ĐÚNG TÊN họ (attribution), không phải tên người sở hữu PAT chung.

Kho chung = Cloudflare KV `qa-dashboard-pat` = {email: enc_pat} (sync chéo máy, không cần
VPN — xem remote_store), cache local `.pat_store.json` làm fallback offline. Giá trị lưu LÀ
PAT đã mã hoá Fernet (crypto_util) -> cache at-rest vẫn là ciphertext, KHÔNG plaintext, nhất
quán threat-model Decision #20. Trước khi lưu PHẢI verify PAT thuộc đúng người đăng nhập (gọi
/myself bằng chính PAT đó, so username với email login) — nếu không, attribution sẽ sai ngược
(QA-A dán PAT QA-B).

Layer: config -> {jira_api, crypto_util, remote_store} -> (this). Không cycle.
"""
import json

from config import username_from_email, AUTH_ENABLED, PAT_CACHE_FILE, atomic_write
from jira_api import verify_pat
from crypto_util import encrypt, decrypt
from remote_store import synced_load, synced_save, synced_delete

PAT_PROP = 'qa-dashboard-pat'


def _valid_map(d):
    return isinstance(d, dict)


def _read_cache():
    if PAT_CACHE_FILE.exists():
        try:
            d = json.loads(PAT_CACHE_FILE.read_text(encoding='utf-8'))
            if isinstance(d, dict):
                return d
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(data):
    return atomic_write(PAT_CACHE_FILE, json.dumps(data, ensure_ascii=False))


def _load_map():
    """{email: enc_pat} từ kho chung KV (fallback cache local). {} nếu chưa có."""
    return synced_load(PAT_PROP, _read_cache, _write_cache, _valid_map, {})


def save_user_pat(email, pat):
    """Verify đúng chủ rồi mã hoá + lưu. Trả (ok: bool, msg: str).

    - PAT không gọi được /myself -> 'PAT không hợp lệ hoặc đã hết hạn'.
    - Có login (AUTH bật) và username Jira != local-part email -> 'PAT không phải của bạn'.
    - Local dev (không email) -> chỉ cần PAT hợp lệ.
    """
    pat = (pat or '').strip()
    if not pat:
        return False, 'Chưa nhập PAT.'
    owner = verify_pat(pat)
    if not owner:
        return False, 'PAT không hợp lệ hoặc đã hết hạn.'
    key = (email or '').strip().lower()
    if AUTH_ENABLED and key:
        expected = username_from_email(email)
        if expected and owner.lower() != expected.lower():
            return False, f'PAT này thuộc tài khoản "{owner}", không khớp với bạn. Hãy tạo PAT bằng chính tài khoản của bạn.'
    store_key = key or 'local'
    m = _load_map()
    m[store_key] = encrypt(pat)
    synced_save(PAT_PROP, m, _write_cache, _valid_map)  # local-first: luôn an toàn ở local, đẩy KV best-effort
    return True, f'Đã lưu PAT cho {owner}. Từ giờ thao tác của bạn sẽ ghi đúng tên trên Jira.'


def load_user_pat(email):
    """PAT gốc (giải mã) của người đăng nhập; None nếu chưa có / giải mã hỏng."""
    key = (email or '').strip().lower() or 'local'
    enc = _load_map().get(key)
    return decrypt(enc) if enc else None


def has_pat(email):
    key = (email or '').strip().lower() or 'local'
    return key in _load_map()


def delete_user_pat(email):
    key = (email or '').strip().lower() or 'local'
    m = _load_map()
    if key in m:
        m.pop(key)
        if m:
            synced_save(PAT_PROP, m, _write_cache, _valid_map)
        else:
            # map rỗng -> xoá hẳn key trên KV (đỡ rác chỗ KV limited)
            synced_delete(PAT_PROP, lambda: PAT_CACHE_FILE.unlink(missing_ok=True))
    return True
