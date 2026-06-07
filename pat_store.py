"""Lưu PAT cá nhân của từng QA — mã hoá at-rest, để khi họ đổi status/comment thì
Jira ghi ĐÚNG TÊN họ (attribution), không phải tên người sở hữu PAT chung.

Nguồn lưu = Jira user property `qa-dashboard-pat` = {email: enc_pat}. KHÔNG cache local
plaintext (an toàn hơn). Trước khi lưu PHẢI verify PAT thuộc đúng người đăng nhập
(gọi /myself bằng chính PAT đó, so username với email login) — nếu không, attribution
sẽ sai ngược (QA-A dán PAT QA-B).

Layer: config -> {jira_api, crypto_util} -> (this). Không cycle.
"""
from config import username_from_email, AUTH_ENABLED
from jira_api import load_property, save_property, verify_pat
from crypto_util import encrypt, decrypt

PAT_PROP = 'qa-dashboard-pat'


def _load_map():
    """{email: enc_pat} từ Jira property. {} nếu chưa có / lỗi."""
    try:
        data = load_property(PAT_PROP)
        return data if isinstance(data, dict) else {}
    except RuntimeError:
        return {}


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
    try:
        save_property(PAT_PROP, m)
    except RuntimeError:
        return False, 'Không lưu được lên Jira (lỗi mạng). Thử lại sau.'
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
        try:
            save_property(PAT_PROP, m)
        except RuntimeError:
            return False
    return True
