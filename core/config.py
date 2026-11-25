"""Configuration: env loading, file paths, constants, and name helpers.

Importing this module loads .env (or OS env vars) and validates that JIRA_URL/JIRA_EMAIL/
JIRA_API_TOKEN exist (Jira Cloud — #197) — exits with a clear message if not. Every other module imports from here.
"""
import os
import re
import sys
import threading
from pathlib import Path

# Windows console defaults to cp1252 -> Vietnamese prints crash. Force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

# ----- Paths -----
# config.py lives in ./core/ (issue #85); project root is its parent. State/cache
# files + .env stay at the root (generated in cwd as before); assets moved to ./assets/.
SCRIPT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = SCRIPT_DIR / 'assets'
ENV_FILE = SCRIPT_DIR / '.env'
DOCS_FILE = SCRIPT_DIR / '.docs_config.json'
SYNC_META_FILE = SCRIPT_DIR / '.sync_meta.json'         # dirty-flag per key (remote_store flush)
PAT_CACHE_FILE = SCRIPT_DIR / '.pat_store.json'         # cache map {email: enc_pat} (ĐÃ mã hoá)
BUG_LOG_SOURCE_FILE = SCRIPT_DIR / '.bug_log_source.json'  # cache file Drive nguồn bug log
BUG_LOG_FILE = SCRIPT_DIR / '.bug_log.json'              # cache snapshot bug log (fallback + render nhanh)
BUG_MONTHLY_FILE = SCRIPT_DIR / '.bug_monthly.json'      # snapshot status per-bug chốt theo tháng (tồn đọng vs mới, hướng B)
BUG_TASK_LINK_FILE = SCRIPT_DIR / '.bug_task_link.json'  # cache link bug/test-case -> Jira task (#55)
JIRA_ACCOUNTS_FILE = SCRIPT_DIR / '.jira_accounts.json'  # cache map username <-> accountId Jira Cloud (#197)
UPLOADS_DIR = SCRIPT_DIR / 'uploads'   # file tài liệu upload (Decision #23) — ghi đè ở dưới nếu .env có UPLOADS_DIR

def atomic_write(path, text, encoding='utf-8'):
    """Ghi text xuống `path` atomic: ghi `*.tmp` CÙNG THƯ MỤC rồi os.replace.
    os.replace là atomic trên cùng filesystem (cả Windows lẫn macOS) → kill process
    đúng lúc ghi sẽ KHÔNG để lại file JSON cụt (state hỏng câm). Có retry nếu bị lock.
    Trả True nếu ghi xong, False nếu lỗi.
    """
    import time
    path = Path(path)
    tmp = path.with_name(f'{path.name}.{os.getpid()}.{threading.get_ident():x}.tmp')
    try:
        tmp.write_text(text, encoding=encoding)
    except OSError as e:
        print(f"[ERROR] atomic_write failed to write tmp {path}: {e}", file=sys.stderr)
        return False

    for _ in range(5):
        try:
            os.replace(tmp, path)
            return True
        except OSError:
            time.sleep(0.1)

    try:
        print(f"[ERROR] atomic_write failed to replace {path} after retries", file=sys.stderr)
        if tmp.exists():
            tmp.unlink()
    except OSError:
        pass
    return False


# ----- Domain constants -----
STUCK_DAYS = 5   # task In Progress/PENDING không đổi >= 5 ngày = "kẹt"


def jql_cf(field_id):
    """'customfield_10305' -> 'cf[10305]' — tham chiếu field trong JQL bằng ID (tên field trên
    Cloud có bản trùng/'(migrated)' nên tham chiếu theo tên dễ trúng nhầm field rỗng)."""
    return f"cf[{field_id.rsplit('_', 1)[-1]}]"

DEFAULT_DISPLAY_NAMES = {}


def _load_env():
    cfg = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in ('LINEAR_API_KEY', 'LINEAR_BASE_URL', 'LINEAR_MAX_CONCURRENT', 'LINEAR_TEAM_KEYS',
              'LINEAR_EXCLUDED_TEAMS', 'LINEAR_SELF_USER', 'BUG_LOG_LINEAR_ENABLED',
              'JIRA_ENABLED', 'JIRA_URL', 'JIRA_EMAIL', 'JIRA_API_TOKEN', 'JIRA_ACCOUNT_IDS', 'JIRA_PORT',
              'JIRA_ADMIN_EMAIL', 'JIRA_ALLOWED_DOMAIN',
              'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'SESSION_SECRET',
              'PUBLIC_BASE_URL', 'LOCAL_ONLY', 'LOCAL_AUTOLOGIN', 'BUG_LOG_POLL_SECONDS', 'BUG_LOG_JIRA_ENABLED',
              'JIRA_MAX_CONCURRENT',
              'CF_ACCOUNT_ID', 'CF_KV_NAMESPACE_ID', 'CF_API_TOKEN', 'UPLOADS_DIR'):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


CFG = _load_env()
# Thư mục lưu tài liệu upload (issue #37). Mặc định <root>/uploads — bám SCRIPT_DIR nên
# chạy đúng mọi OS (trước hardcode path macOS -> upload chết trên host Windows).
# Override bằng UPLOADS_DIR trong .env / env var nếu muốn để ổ khác.
if CFG.get('UPLOADS_DIR'):
    UPLOADS_DIR = Path(CFG['UPLOADS_DIR']).expanduser()
try:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass  # tạo lúc upload đầu tiên nếu ở đây fail (vd đường dẫn override chưa mount)

# Linear GraphQL API (nguồn chính thay Jira).
LINEAR_API_KEY = CFG.get('LINEAR_API_KEY', '').strip()
LINEAR_BASE_URL = (CFG.get('LINEAR_BASE_URL') or 'https://linear.app/thehumaninc').strip().rstrip('/')
LINEAR_TEAM_KEYS = [t.strip().upper() for t in CFG.get('LINEAR_TEAM_KEYS', '').split(',') if t.strip()]
LINEAR_EXCLUDED_TEAMS = [t.strip().upper() for t in CFG.get('LINEAR_EXCLUDED_TEAMS', 'VC').split(',') if t.strip()]
try:
    LINEAR_MAX_CONCURRENT = min(64, max(1, int(CFG.get('LINEAR_MAX_CONCURRENT', '12'))))
except ValueError:
    LINEAR_MAX_CONCURRENT = 12

# Jira Cloud tạm ngắt (mặc định tắt). Chỉ bật khi JIRA_ENABLED=1 và đủ credentials.
JIRA_ENABLED = (CFG.get('JIRA_ENABLED') or '0').strip().lower() in ('1', 'true', 'yes')
JIRA_URL = CFG.get('JIRA_URL', '').strip().rstrip('/')
JIRA_EMAIL = CFG.get('JIRA_EMAIL', '').strip()
JIRA_API_TOKEN = CFG.get('JIRA_API_TOKEN', '').strip()

if not LINEAR_API_KEY and not (JIRA_ENABLED and JIRA_URL and JIRA_EMAIL and JIRA_API_TOKEN):
    print("ERROR: Thiếu LINEAR_API_KEY trong .env (hoặc bật JIRA_ENABLED=1 với đủ JIRA_URL/JIRA_EMAIL/JIRA_API_TOKEN).",
          file=sys.stderr)
    sys.exit(1)

# Giữ tên `PAT` = token chung: nhiều module import nó để REDACT khỏi thông báo lỗi.
PAT = LINEAR_API_KEY or JIRA_API_TOKEN
# Override map username -> accountId (JSON {"quangbm": "712020:..."}). Chỉ cần khi Jira bật.
JIRA_ACCOUNT_IDS = CFG.get('JIRA_ACCOUNT_IDS', '').strip()
PORT = int(CFG.get('JIRA_PORT', '8080'))
# ----- Bug Log: nhịp poll (giây) của daemon scan. Default 600s (10 phút). -----
try:
    BUG_LOG_POLL_SECONDS = max(30, int(CFG.get('BUG_LOG_POLL_SECONDS', '600')))
except ValueError:
    BUG_LOG_POLL_SECONDS = 600
# ----- Bug Log: nguồn Linear (mặc định BẬT) & Jira (tạm ngắt, mặc định TẮT) -----
BUG_LOG_LINEAR_ENABLED = (CFG.get('BUG_LOG_LINEAR_ENABLED') or '1').strip().lower() not in ('0', 'false', 'no')
BUG_LOG_JIRA_ENABLED = JIRA_ENABLED and (CFG.get('BUG_LOG_JIRA_ENABLED') or '0').strip().lower() in ('1', 'true', 'yes')

# ----- Bug Log nguồn Jira (#104): issue type "Bug Testing" + field Severity + JQL mặc định -----
# Instance-specific (dò lại bằng /rest/api/2/issuetype + /rest/api/2/field nếu migrate/đổi cấu hình).
BUG_TESTING_TYPE_ID = CFG.get('BUG_TESTING_TYPE_ID', '10382').strip()            # issuetype "Bug Testing"
BUG_SEVERITY_FIELD = CFG.get('BUG_SEVERITY_FIELD', 'customfield_10404').strip()  # select "Severity" (Blocker/Critical/High/Medium/Low)
SPRINT_FIELD = CFG.get('SPRINT_FIELD', 'customfield_10020').strip()               # array sprint object (state active/future/closed) — #106/B
# JQL nguồn Bug Log mặc định (chưa lọc project — chia theo squad = project.key ở tầng hiển thị).
BUG_TESTING_JQL = (CFG.get('BUG_TESTING_JQL', '').strip()
                   or f'issuetype = {BUG_TESTING_TYPE_ID} ORDER BY created DESC')

# ----- Trần số call Jira REST đồng thời (Decision #129/#133) -----
# ThreadingHTTPServer + ThreadPool lồng (/ outer + fetch_all 5 call + refresh nền + scheduler)
# có thể nhân số call Jira đồng thời lên rất nhanh -> nguy cơ nện Jira DC / cạn socket.
# Semaphore (jira_api) chặn trần này; pool_maxsize của _SESSION đặt khớp. Default 12,
# clamp [1, 64] để khỏi vô hiệu hoá (0/âm) hay đặt quá lố do gõ nhầm.
try:
    JIRA_MAX_CONCURRENT = min(64, max(1, int(CFG.get('JIRA_MAX_CONCURRENT', '12'))))
except ValueError:
    JIRA_MAX_CONCURRENT = 12
# ----- Auth (Google OAuth; identity = session cookie HMAC do app ký — Decision #15) -----
# ⚠ KHÔNG còn tin header Cf-Access-Authenticated-User-Email: CF Access đã bỏ, tunnel plain
# không strip header giả → tin nó = auth bypass (Decision #92, đã gỡ khỏi _user_email).
# Email role ADMIN: được edit roadmap/tài liệu. Rỗng = không khoá (local dev).
# Hỗ trợ NHIỀU admin (JIRA_ADMIN_EMAIL = danh sách email cách nhau dấu phẩy).
# ADMIN_EMAIL giữ lại = phần tử đầu (tương thích ngược cho code cũ tham chiếu 1 email).
ADMIN_EMAILS = {e.strip() for e in CFG.get('JIRA_ADMIN_EMAIL', '').lower().split(',')} - {''}
ADMIN_EMAIL = list(ADMIN_EMAILS)[0] if ADMIN_EMAILS else ''
# Danh sách account cần track kèm role.
TRACKED_ROLES = {
    'thaohtt@wealify.com': 'PO',
    'nhanpt@wealify.com': 'QA',
    'huypk@wealify.com': 'DEV',
    'datnh@wealify.com': 'DEV',
    'thuyetvt@wealify.com': 'QA',
    'cuongtln@wealify.com': 'Designer',
    'ducnh@wealify.com': 'DEV',
    'tuan.pv@wealify.com': 'DEV',
    'giangtt@wealify.com': 'DEV',
    'thanhht@wealify.com': 'QA Lead',
    'phuongnl@wealify.com': 'BA',
}
SELF_USER = CFG.get('LINEAR_SELF_USER', '').strip()
USERS = list(TRACKED_ROLES.keys())


def role_of(email):
    return TRACKED_ROLES.get((email or '').strip().lower(), '')


TRACKED_DEV_EMAILS = {e for e, r in TRACKED_ROLES.items() if r == 'DEV'}
TRACKED_DEVS = {e.split('@', 1)[0].lower() for e in TRACKED_DEV_EMAILS}
_DEV_ALIAS_MAP = {d.replace('.', ''): d for d in TRACKED_DEVS}


def normalize_tracked_dev(raw, email=''):
    """Return canonical dev local-part if in TRACKED_DEVS, else ''."""
    em = (email or '').strip().lower()
    if em in TRACKED_DEV_EMAILS:
        return em.split('@', 1)[0]
    key = (raw or '').strip().lower()
    if key in TRACKED_DEVS:
        return key
    return _DEV_ALIAS_MAP.get(key.replace('.', ''), '')
# Domain được phép vào (vd 'baokim.vn'). Rỗng = không chặn domain ở app (để Cloudflare lo).
ALLOWED_DOMAIN = CFG.get('JIRA_ALLOWED_DOMAIN', '').strip().lstrip('@').lower()

# ----- Google OAuth login (thay Cloudflare Access) -----
# Cấu hình đủ 2 cái dưới => AUTH_ENABLED: app bắt đăng nhập Google, lọc theo ALLOWED_DOMAIN.
# Bỏ trống => local dev: không bắt login, mọi request = admin (như trước).
GOOGLE_CLIENT_ID = CFG.get('GOOGLE_CLIENT_ID', '').strip()
GOOGLE_CLIENT_SECRET = CFG.get('GOOGLE_CLIENT_SECRET', '').strip()
SESSION_SECRET = CFG.get('SESSION_SECRET', '').strip()  # khoá ký session cookie (HMAC)
# Khoá RIÊNG mã hoá PAT cá nhân at-rest (issue #45). Bỏ trống => fallback SESSION_SECRET
# (giữ tương thích: PAT đã lưu vẫn giải mã được). Set khác SESSION_SECRET => tách hẳn
# blast radius: rotate session KHÔNG xoá PAT, và ngược lại. Đổi giá trị này = re-enter PAT.
PAT_SECRET = CFG.get('PAT_SECRET', '').strip()
# URL gốc công khai (vd 'https://baokim-qa.com'). Khi set => dùng cái này để build
# redirect_uri OAuth + quyết cờ Secure cookie, KHÔNG tin Host/X-Forwarded-Proto của client
# (chống Host-header injection — issue #49). Bỏ trống => suy từ request (local dev).
PUBLIC_BASE_URL = CFG.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
AUTH_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

# Chế độ CHỈ-MÁY-NÀY (Decision #96, MẶC ĐỊNH BẬT): dashboard là của riêng chủ máy, chỉ phục
# vụ request gõ từ chính máy host (localhost) — request đi qua tunnel cloudflared/Cloudflare
# edge bị 403 dù tunnel còn chạy. Set LOCAL_ONLY=0 trong .env để mở lại domain công khai.
LOCAL_ONLY = (CFG.get('LOCAL_ONLY') or '1').strip().lower() not in ('0', 'false', 'no')
if LOCAL_ONLY:
    # Domain công khai không còn với tới -> login Google phải quay về localhost (redirect URI
    # http://localhost:<PORT>/oauth/callback đã đăng ký sẵn — Decision #15). An toàn khi suy
    # từ Host vì gate LOCAL_ONLY đã ép Host là loopback.
    PUBLIC_BASE_URL = ''

# Tự đăng nhập chính chủ (Decision #98, MẶC ĐỊNH BẬT khi LOCAL_ONLY + AUTH): request đã qua gate
# LOCAL_ONLY = người ngồi trước máy host = chính chủ -> khỏi login Google. Identity vẫn là EMAIL
# (không phải 'local') để API token cá nhân đã lưu theo email tiếp tục dùng được (#20).
# Set LOCAL_AUTOLOGIN=0 để quay lại login Google bình thường.
LOCAL_AUTOLOGIN = (LOCAL_ONLY and AUTH_ENABLED
                   and (CFG.get('LOCAL_AUTOLOGIN') or '1').strip().lower() not in ('0', 'false', 'no'))


def _owner_email():
    """Email chính chủ cho auto-login: `<SELF_USER>@<ALLOWED_DOMAIN>` nếu nằm trong admin, else
    admin DUY NHẤT. Nhiều admin mà không đoán được -> '' (tắt auto-login, KHÔNG chọn bừa vì
    ADMIN_EMAILS là set không thứ tự)."""
    guess = f'{SELF_USER}@{ALLOWED_DOMAIN}'.lower() if (SELF_USER and ALLOWED_DOMAIN) else ''
    if guess and guess in ADMIN_EMAILS:
        return guess
    return next(iter(ADMIN_EMAILS)) if len(ADMIN_EMAILS) == 1 else ''


OWNER_EMAIL = _owner_email() if LOCAL_AUTOLOGIN else ''

# ----- Cloudflare Workers KV = kho sync chéo máy KHÔNG cần VPN (thay Jira property) -----
# Cả 3 giá trị có mặt => KV_ENABLED: remote_store dùng KV làm kho chung (reachable qua
# api.cloudflare.com trên internet công cộng, sống cả khi Jira/VPN down). Bỏ trống =>
# fallback về Jira property như cũ (nhưng vẫn local-first nên save không còn fail vì mạng).
CF_ACCOUNT_ID = CFG.get('CF_ACCOUNT_ID', '').strip()
CF_KV_NAMESPACE_ID = CFG.get('CF_KV_NAMESPACE_ID', '').strip()
CF_API_TOKEN = CFG.get('CF_API_TOKEN', '').strip()
KV_ENABLED = bool(CF_ACCOUNT_ID and CF_KV_NAMESPACE_ID and CF_API_TOKEN)
if AUTH_ENABLED and not SESSION_SECRET:
    print("ERROR: Bật Google OAuth nhưng thiếu SESSION_SECRET trong .env.\n"
          "       Tạo bằng: python3 -c \"import secrets;print(secrets.token_urlsafe(48))\"",
          file=sys.stderr)
    sys.exit(1)


def derive_subkey(label, length=32):
    """Khoá con TÁCH-MIỀN từ SESSION_SECRET theo nhãn vai trò (issue #45).

    HKDF-Expand 1 block (HMAC-SHA256) — đủ vì SESSION_SECRET đã entropy cao (48 byte
    random). Mỗi vai trò 1 `label` riêng => không tái dùng cùng một khoá cho 2 mục đích
    (vd ký cookie vs mã hoá PAT). Rò rỉ khoá con này KHÔNG suy ra khoá con khác (cần root
    secret). Trả b'' nếu thiếu secret (auth disabled) — caller coi như chưa cấu hình.
    """
    import hashlib
    import hmac as _hmac
    if not SESSION_SECRET:
        return b''
    block = _hmac.new(SESSION_SECRET.encode('utf-8'),
                      label.encode('utf-8') + b'\x01', hashlib.sha256).digest()
    return block[:length]


def username_from_email(email):
    """Map email đăng nhập -> Jira username (local-part). None nếu không khớp QA nào.
    Vd 'quangbm@baokim.vn' -> 'quangbm' (nếu trong USERS); email lạ -> None."""
    local = (email or '').strip().lower().split('@')[0]
    return local if local in USERS else None


def display_name(username):
    """Short team name for a QA username, else the username unchanged."""
    return DEFAULT_DISPLAY_NAMES.get(username, username)


# Chuẩn hoá key Jira để so khớp link BỀN qua đổi project key mỗi kỳ nửa năm.
# Bối cảnh: Jira đổi key khi chuyển kỳ (DA51H26 -> DA52H26 -> DA51H27 ...) NHƯNG số issue
# giữ nguyên khi move -> link cũ lưu key kỳ trước trượt hết khi so với task live kỳ mới.
# Cách chữa: gộp đoạn "kỳ" `<digit>H<2-digit-year>` về placeholder '#' -> mọi phiên bản key
# của CÙNG 1 issue (khác nhau chỉ ở kỳ) canon về một chuỗi, khớp nhau bất kể kỳ nào.
#   DA51H26-1252 / DA52H26-1252 / DA51H27-1252  ->  DA5#-1252
# Key KHÔNG theo mẫu kỳ (vd DA2B-100) giữ nguyên -> so khớp đúng như cũ.
# ⚠ TWIN ở app_v2.js (canonKey) — sửa 1 bên PHẢI sửa bên kia.
_HALFYEAR_RE = re.compile(r'\dH\d{2}(-\d+)$')


def canon_key(key):
    """Key Jira đã gộp đoạn kỳ nửa năm -> so khớp link bền qua rename kỳ. '' -> ''."""
    if not key:
        return key
    return _HALFYEAR_RE.sub(r'#\1', key.strip())


# Canonical QA tester name theo ALIAS đầu (ascii, lowercase). Dùng để gom các biến
# thể typo của cột "Tester" (qa_pic) trong file bug Drive về 1 tên chuẩn:
# NhungNH/NhungNH -> Nhung, ThoLT/TholT/ThoLt -> Thơ, Phuong -> Phương, ...
# 'thanh' và 'tho' prefix khác nhau nên không xung đột; chỉ cần liệt kê đủ team.
_TESTER_ALIASES = (
    ('thuyet', 'Thuyết'),
    ('nhan', 'Nhàn'),
    ('thanh', 'Thành'),
)


def _ascii_key(s):
    """lowercase + bỏ dấu tiếng Việt + chỉ giữ chữ cái — để so khớp tên không phụ thuộc
    hoa/thường, dấu, khoảng trắng, hậu tố initials."""
    import unicodedata
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return ''.join(c for c in s.lower() if c.isalpha())


def _damerau(a, b):
    """Optimal-string-alignment distance: như Levenshtein nhưng đổi chỗ 2 ký tự liền
    kề tính là 1 (nên 'nhung' vs 'nhugn' = 1, không phải 2)."""
    la, lb = len(a), len(b)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


def normalize_tester(raw):
    """Map giá trị free-text cột Tester (qa_pic) về tên QA chuẩn của team.
    Gom các biến thể typo (NhungNH -> Nhung, ThoLT/TholT/ThoLt -> Thơ, ...).
    Khớp 2 tầng: (1) prefix chính xác; (2) fuzzy — phần đầu tên sai ≤1 lỗi gõ
    (gồm đổi chỗ 2 ký tự, vd 'Nhugn' -> Nhung). Không khớp -> trả chuỗi gốc trim."""
    k = _ascii_key(raw)
    if not k:
        return ''
    # tầng 1: prefix chính xác (rẻ, bắt phần lớn ca)
    for prefix, name in _TESTER_ALIASES:
        if k.startswith(prefix):
            return name
    # tầng 2: fuzzy phần đầu — bỏ qua alias quá ngắn (<4) để tránh khớp bừa.
    # so từng độ dài lát cắt quanh len(prefix) (cho thêm/bớt 1 ký tự) rồi lấy min distance.
    best_name, best = '', 99
    for prefix, name in _TESTER_ALIASES:
        if len(prefix) < 4:
            continue
        for plen in (len(prefix) - 1, len(prefix), len(prefix) + 1):
            seg = k[:plen]
            if not seg:
                continue
            dist = _damerau(prefix, seg)
            if dist < best:
                best, best_name = dist, name
    if best <= 1:
        return best_name
    return (raw or '').strip()


def actor_name(author_obj):
    """Pretty name of a Jira actor: short name for QA team, else displayName/username.
    Jira Cloud không có 'name' — jira_cloud.normalize gắn 'name' = local-part email (#197)."""
    a = author_obj or {}
    name = a.get('name', '')
    return DEFAULT_DISPLAY_NAMES.get(name, a.get('displayName') or name or '?')
