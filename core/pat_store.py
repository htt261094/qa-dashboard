"""Lưu API token Jira cá nhân của từng QA — mã hoá at-rest, để khi họ đổi status/comment thì
Jira ghi ĐÚNG TÊN họ (attribution), không phải tên người sở hữu token chung.

Kho chung = Cloudflare KV `qa-dashboard-pat` = {email: enc_cred} (sync chéo máy — xem
remote_store), cache local `.pat_store.json` làm fallback offline. Giá trị lưu đã mã hoá
Fernet (crypto_util) -> cache at-rest vẫn là ciphertext, nhất quán threat-model Decision #20.

Jira Cloud (#197): credential = 'email:api_token' (chính là cặp Basic auth). Người dùng chỉ
dán token; email = email ĐĂNG NHẬP của họ. Verify bằng /myself với Basic(email login, token):
Cloud buộc email khớp chủ token -> gọi được = token chắc chắn của đúng người (không còn so
username với local-part như thời PAT DC). Tên module/hàm giữ chữ "pat" để caller không đổi.
Entry cũ là PAT Jira DC (không có 'email:') -> coi như CHƯA có token -> UI nhắc dán lại.

Layer: config -> {jira_cloud, jira_api, crypto_util, remote_store} -> (this). Không cycle.
"""
import json

from config import AUTH_ENABLED, PAT_CACHE_FILE, JIRA_EMAIL, SELF_USER, atomic_write
from jira_api import verify_user_token
from jira_cloud import split_cred, MAIL_DOMAIN
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
    """{email: enc_cred} từ kho chung KV (fallback cache local). {} nếu chưa có."""
    return synced_load(PAT_PROP, _read_cache, _write_cache, _valid_map, {})


def _jira_email_for(email):
    """Email dùng cho Basic auth: email đăng nhập; local dev (chưa login) -> email của SELF_USER
    (loopback = admin = chủ máy, Decision #31), fallback email token chung."""
    e = (email or '').strip().lower()
    if e:
        return e
    return f'{SELF_USER}@{MAIL_DOMAIN}' if SELF_USER else JIRA_EMAIL


def save_user_pat(email, token):
    """Verify đúng chủ rồi mã hoá + lưu. Trả (ok: bool, msg: str).

    - Token + email đăng nhập không gọi được /myself -> 'không hợp lệ / hết hạn / không phải của bạn'.
    - Local dev (không email) -> dùng email của SELF_USER.
    """
    token = (token or '').strip()
    if not token:
        return False, 'Chưa nhập API token.'
    if split_cred(token)[0]:
        token = split_cred(token)[1]          # lỡ dán cả 'email:token' -> chỉ lấy token
    jira_email = _jira_email_for(email)
    owner = verify_user_token(jira_email, token)
    if not owner:
        return False, (f'API token không hợp lệ, đã hết hạn, hoặc không thuộc tài khoản {jira_email}. '
                       'Hãy tạo token bằng chính tài khoản Atlassian của bạn.')
    if AUTH_ENABLED and email and owner != jira_email:
        return False, f'API token này thuộc tài khoản "{owner}", không khớp với bạn.'
    store_key = (email or '').strip().lower() or 'local'
    m = _load_map()
    m[store_key] = encrypt(f'{jira_email}:{token}')
    synced_save(PAT_PROP, m, _write_cache, _valid_map)  # local-first: luôn an toàn ở local, đẩy KV best-effort
    return True, f'Đã lưu API token cho {owner}. Từ giờ thao tác của bạn sẽ ghi đúng tên trên Jira.'


def load_user_pat(email):
    """Credential 'email:token' (giải mã) của người đăng nhập; None nếu chưa có / giải mã hỏng /
    là PAT Jira DC cũ (không dùng được trên Cloud)."""
    key = (email or '').strip().lower() or 'local'
    enc = _load_map().get(key)
    cred = decrypt(enc) if enc else None
    return cred if split_cred(cred)[0] else None


def has_pat(email):
    return load_user_pat(email) is not None


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
