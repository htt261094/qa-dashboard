"""Mã hoá đối xứng cho dữ liệu nhạy cảm (PAT của từng QA).

Chuẩn: Fernet (AES-128-CBC + HMAC-SHA256) từ thư viện `cryptography` — chuẩn công
nghiệp, authenticated encryption (chống sửa ngầm ciphertext).

Khoá mã hoá DERIVE từ SESSION_SECRET (đã có sẵn trong .env, random 48 byte) qua scrypt.
Local dev (không SESSION_SECRET) -> sinh & lưu khoá ngẫu nhiên ở file `.crypto_key`
(đã gitignore) để vẫn mã hoá thật, không bao giờ lưu plaintext.

GIỚI HẠN (phải hiểu đúng): app cần tự giải mã để dùng PAT -> khoá phải nằm nơi app
đọc được. Vì vậy lớp này CHỐNG rò rỉ file at-rest (commit nhầm, lọt backup), KHÔNG
chống được khi kẻ tấn công chiếm cả server (có cả ciphertext lẫn khoá). Đây là ranh
giới chấp nhận được — server bị chiếm thì PAT chung trong .env cũng mất.
"""
import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from config import SESSION_SECRET, SCRIPT_DIR

_KEY_FILE = SCRIPT_DIR / '.crypto_key'
# Salt cố định: vai trò chống rainbow-table ít quan trọng vì secret nguồn entropy cao.
_SALT = b'qa-dashboard.pat.v1'
_fernet = None


def _local_key_material():
    """Khoá nguồn cho local dev: đọc .crypto_key, chưa có thì sinh & lưu (gitignore)."""
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()
    import secrets
    km = secrets.token_bytes(48)
    _KEY_FILE.write_bytes(km)
    try:
        _KEY_FILE.chmod(0o600)  # best-effort siết quyền (no-op trên Windows)
    except OSError:
        pass
    return km


def _get_fernet():
    global _fernet
    if _fernet is None:
        source = SESSION_SECRET.encode('utf-8') if SESSION_SECRET else _local_key_material()
        kdf = Scrypt(salt=_SALT, length=32, n=2 ** 14, r=8, p=1)
        key = base64.urlsafe_b64encode(kdf.derive(source))
        _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext):
    """str -> token chuỗi (urlsafe base64). Raise nếu input không phải str."""
    if not isinstance(plaintext, str):
        raise TypeError('encrypt expects str')
    return _get_fernet().encrypt(plaintext.encode('utf-8')).decode('ascii')


def decrypt(token):
    """token -> str gốc; None nếu token hỏng/sai khoá (không raise, để caller xử nhẹ)."""
    if not token:
        return None
    try:
        return _get_fernet().decrypt(token.encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError, TypeError):
        return None
