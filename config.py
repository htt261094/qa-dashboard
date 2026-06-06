"""Configuration: env loading, file paths, constants, and name helpers.

Importing this module loads .env (or OS env vars) and validates that JIRA_URL/JIRA_PAT
exist — exits with a clear message if not. Every other module imports from here.
"""
import os
import sys
from pathlib import Path

# Windows console defaults to cp1252 -> Vietnamese prints crash. Force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

# ----- Paths -----
SCRIPT_DIR = Path(__file__).parent
ENV_FILE = SCRIPT_DIR / '.env'
STATE_FILE = SCRIPT_DIR / '.last_seen.json'
PIC_FILE = SCRIPT_DIR / '.pic_config.json'
DOCS_FILE = SCRIPT_DIR / '.docs_config.json'
ROADMAP_FILE = SCRIPT_DIR / '.roadmap_config.json'

# ----- Domain constants -----
STUCK_DAYS = 5   # task In Progress/PENDING không đổi >= 5 ngày = "kẹt"

DEFAULT_DISPLAY_NAMES = {
    'quangbm': 'Quang',
    'nhungnh': 'Nhung',
    'phuongct': 'Phương',
    'tholt': 'Thơ',
    'thanhht1': 'Thành',
    'hiennt19': 'Hiền',
}


def _load_env():
    cfg = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in ('JIRA_URL', 'JIRA_PAT', 'JIRA_USERS', 'JIRA_PORT',
              'JIRA_ADMIN_EMAIL', 'JIRA_ALLOWED_DOMAIN',
              'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'SESSION_SECRET'):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


CFG = _load_env()
if not CFG.get('JIRA_URL') or not CFG.get('JIRA_PAT'):
    print("ERROR: Thiếu JIRA_URL hoặc JIRA_PAT. Tạo file .env theo .env.example.", file=sys.stderr)
    sys.exit(1)

JIRA_URL = CFG['JIRA_URL'].rstrip('/')
PAT = CFG['JIRA_PAT']
USERS = [u.strip() for u in CFG.get('JIRA_USERS', 'quangbm,nhungnh,phuongct,tholt,thanhht1').split(',') if u.strip()]
PORT = int(CFG.get('JIRA_PORT', '8080'))
# ----- Auth (qua Cloudflare Access; identity = header Cf-Access-Authenticated-User-Email) -----
# Email role ADMIN: được edit roadmap/tài liệu. Rỗng = không khoá (local dev).
ADMIN_EMAIL = CFG.get('JIRA_ADMIN_EMAIL', '').strip().lower()
# Domain được phép vào (vd 'baokim.vn'). Rỗng = không chặn domain ở app (để Cloudflare lo).
ALLOWED_DOMAIN = CFG.get('JIRA_ALLOWED_DOMAIN', '').strip().lstrip('@').lower()

# ----- Google OAuth login (thay Cloudflare Access) -----
# Cấu hình đủ 2 cái dưới => AUTH_ENABLED: app bắt đăng nhập Google, lọc theo ALLOWED_DOMAIN.
# Bỏ trống => local dev: không bắt login, mọi request = admin (như trước).
GOOGLE_CLIENT_ID = CFG.get('GOOGLE_CLIENT_ID', '').strip()
GOOGLE_CLIENT_SECRET = CFG.get('GOOGLE_CLIENT_SECRET', '').strip()
SESSION_SECRET = CFG.get('SESSION_SECRET', '').strip()  # khoá ký session cookie (HMAC)
AUTH_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
if AUTH_ENABLED and not SESSION_SECRET:
    print("ERROR: Bật Google OAuth nhưng thiếu SESSION_SECRET trong .env.\n"
          "       Tạo bằng: python3 -c \"import secrets;print(secrets.token_urlsafe(48))\"",
          file=sys.stderr)
    sys.exit(1)


def username_from_email(email):
    """Map email đăng nhập -> Jira username (local-part). None nếu không khớp QA nào.
    Vd 'quangbm@baokim.vn' -> 'quangbm' (nếu trong USERS); email lạ -> None."""
    local = (email or '').strip().lower().split('@')[0]
    return local if local in USERS else None


def display_name(username):
    """Short team name for a QA username, else the username unchanged."""
    return DEFAULT_DISPLAY_NAMES.get(username, username)


def actor_name(author_obj):
    """Pretty name of a Jira actor: short name for QA team, else displayName/username."""
    a = author_obj or {}
    name = a.get('name', '')
    return DEFAULT_DISPLAY_NAMES.get(name, a.get('displayName') or name or '?')
