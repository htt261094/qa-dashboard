"""Configuration: env loading, file paths, constants, and name helpers.

Importing this module loads .env (or OS env vars) and validates that JIRA_URL/JIRA_PAT
exist — exits with a clear message if not. Every other module imports from here.
"""
import os
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
ROADMAP_FILE = SCRIPT_DIR / '.roadmap_config.json'
SYNC_META_FILE = SCRIPT_DIR / '.sync_meta.json'         # dirty-flag per key (remote_store flush)
PAT_CACHE_FILE = SCRIPT_DIR / '.pat_store.json'         # cache map {email: enc_pat} (ĐÃ mã hoá)
DRIVE_TOKEN_FILE = SCRIPT_DIR / '.drive_token.json'      # cache refresh token (mã hoá) fallback
BUG_LOG_SOURCE_FILE = SCRIPT_DIR / '.bug_log_source.json'  # cache file Drive nguồn bug log
BUG_LOG_FILE = SCRIPT_DIR / '.bug_log.json'              # cache snapshot bug log (fallback + render nhanh)
BUG_TASK_LINK_FILE = SCRIPT_DIR / '.bug_task_link.json'  # cache link bug/test-case -> Jira task (#55)
TESTCASE_FILE = SCRIPT_DIR / '.testcase_config.json'    # cache bộ test case import từ Drive (#152)
TESTCASE_TASK_LINK_FILE = SCRIPT_DIR / '.testcase_task_link.json'  # cache link bộ test case -> Jira task (#155)
SNAPSHOT_CACHE_FILE = SCRIPT_DIR / '.snapshot_cache.json'  # L3 cache đĩa snapshot task (offline fallback, #137)
TC_FILE = SCRIPT_DIR / '.tc_config.json'                   # test case folders + cases (persistence #152)

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

# ----- Tạo Sub-task (id lấy từ createmeta Jira DC — instance-specific, KHÔNG đổi tuỳ tiện) -----
SUBTASK_TYPE_ID = '10003'              # issuetype "Sub-task"
TASK_PTSP_TYPE_ID = '10103'            # issuetype "Task-PTSP" (parent của sub-task QA)
START_DATE_FIELD = 'customfield_10208'  # "Start date" (required khi tạo, default = hôm nay)
LEADER_FIELD = 'customfield_10606'      # "Leader" (user-picker, optional)
LEADER_EVAL_NUM_FIELD = 'customfield_10605'  # "Leader đánh giá (Số)" (number)
LEADER_EVAL_TEXT_FIELD = 'customfield_10604' # "Leader đánh giá (Text)" (text)

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
              'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'SESSION_SECRET',
              'PUBLIC_BASE_URL', 'BUG_LOG_POLL_SECONDS', 'JIRA_MAX_CONCURRENT',
              'CF_ACCOUNT_ID', 'CF_KV_NAMESPACE_ID', 'CF_API_TOKEN',
              'OLLAMA_URL', 'OLLAMA_MODEL'):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


CFG = _load_env()
# OFFLINE mode (Decision: tách Bug Log chạy standalone khi không vào được Jira/VPN).
# Bật bằng env OFFLINE=1 -> KHÔNG bắt buộc JIRA creds + jira_api ngắt mọi call property
# (fallback cache local tức thì). Đặt env này TRƯỚC khi import config (xem bug_log_offline.py).
OFFLINE = (CFG.get('OFFLINE') or os.environ.get('OFFLINE') or '').strip().lower() in ('1', 'true', 'yes')

if not CFG.get('JIRA_URL') or not CFG.get('JIRA_PAT'):
    if not OFFLINE:
        print("ERROR: Thiếu JIRA_URL hoặc JIRA_PAT. Tạo file .env theo .env.example.", file=sys.stderr)
        sys.exit(1)
    # OFFLINE: không cần Jira -> giá trị dummy để các `from config import JIRA_URL, PAT` không vỡ.
    CFG.setdefault('JIRA_URL', 'http://offline.invalid')
    CFG.setdefault('JIRA_PAT', 'offline')

JIRA_URL = CFG['JIRA_URL'].rstrip('/')
PAT = CFG['JIRA_PAT']
USERS = [u.strip() for u in CFG.get('JIRA_USERS', 'quangbm,nhungnh,phuongct,tholt,thanhht1').split(',') if u.strip()]
PORT = int(CFG.get('JIRA_PORT', '8080'))
# ----- Bug Log: nhịp poll Drive (giây) của daemon scan (Decision #54). -----
# Default 600s (10 phút). Nhờ Tầng-1 metadata-first, mỗi poll khi không file nào đổi chỉ
# tốn N call metadata rẻ -> hạ xuống 2-3 phút (120-180) vẫn an toàn nếu muốn data tươi hơn.
# Chặn sàn 30s để khỏi spam Drive API do gõ nhầm.
try:
    BUG_LOG_POLL_SECONDS = max(30, int(CFG.get('BUG_LOG_POLL_SECONDS', '600')))
except ValueError:
    BUG_LOG_POLL_SECONDS = 600
# ----- Trần số call Jira REST đồng thời (Decision #129/#133) -----
# ThreadingHTTPServer + ThreadPool lồng (/ outer + fetch_all 5 call + refresh nền + scheduler)
# có thể nhân số call Jira đồng thời lên rất nhanh -> nguy cơ nện Jira DC / cạn socket.
# Semaphore (jira_api) chặn trần này; pool_maxsize của _SESSION đặt khớp. Default 12,
# clamp [1, 64] để khỏi vô hiệu hoá (0/âm) hay đặt quá lố do gõ nhầm.
try:
    JIRA_MAX_CONCURRENT = min(64, max(1, int(CFG.get('JIRA_MAX_CONCURRENT', '12'))))
except ValueError:
    JIRA_MAX_CONCURRENT = 12
# ----- Chatbot (LLM local qua Ollama, Decision #32) -----
# App proxy sang Ollama chạy CÙNG host (KHÔNG expose Ollama ra ngoài — không có auth).
# Browser nói chuyện với app (đã qua OAuth/domain gate), app stream tiếp sang Ollama.
# Bỏ trống OLLAMA_MODEL = tắt tính năng chatbot (widget không render).
OLLAMA_URL = (CFG.get('OLLAMA_URL') or 'http://localhost:11434').rstrip('/')
OLLAMA_MODEL = CFG.get('OLLAMA_MODEL', 'gemma4:12b').strip()
CHAT_ENABLED = bool(OLLAMA_MODEL)
# keep_alive: model nằm thường trú trong GPU/RAM bao lâu sau request cuối. '10m' = nhả sau
# 10p không dùng (default — host 16GB, model 12B 8GB ghim mãi gây swap ~11GB; nhả khi rảnh để
# giải phóng RAM, chỉ câu đầu sau idle chịu ~30s nạp lại). '-1' = giữ mãi (không cold-load
# nhưng swap liên tục — chỉ hợp máy nhiều RAM/chuyên Ollama); '0' = nhả ngay sau mỗi câu.
OLLAMA_KEEP_ALIVE = (CFG.get('OLLAMA_KEEP_ALIVE') or '10m').strip()
# ----- Auth (qua Cloudflare Access; identity = header Cf-Access-Authenticated-User-Email) -----
# Email role ADMIN: được edit roadmap/tài liệu. Rỗng = không khoá (local dev).
# Hỗ trợ NHIỀU admin (JIRA_ADMIN_EMAIL = danh sách email cách nhau dấu phẩy).
# ADMIN_EMAIL giữ lại = phần tử đầu (tương thích ngược cho code cũ tham chiếu 1 email).
ADMIN_EMAILS = {e.strip() for e in CFG.get('JIRA_ADMIN_EMAIL', '').lower().split(',')} - {''}
ADMIN_EMAIL = list(ADMIN_EMAILS)[0] if ADMIN_EMAILS else ''
# Username Jira của chính admin (cho tab "My work" — task của riêng mình). Local dev (chưa
# login) fallback về đây. Default = thanhht1 (acting manager). Override qua .env nếu cần.
SELF_USER = CFG.get('JIRA_SELF_USER', 'thanhht1').strip()
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


# Canonical QA tester name theo ALIAS đầu (ascii, lowercase). Dùng để gom các biến
# thể typo của cột "Tester" (qa_pic) trong file bug Drive về 1 tên chuẩn:
# NhungNH/NhungNH -> Nhung, ThoLT/TholT/ThoLt -> Thơ, Phuong -> Phương, ...
# 'thanh' và 'tho' prefix khác nhau nên không xung đột; chỉ cần liệt kê đủ team.
_TESTER_ALIASES = (
    ('thanh', 'Thành'),
    ('phuong', 'Phương'),
    ('nhung', 'Nhung'),
    ('quang', 'Quang'),
    ('hien', 'Hiền'),
    ('tho', 'Thơ'),
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
    """Pretty name of a Jira actor: short name for QA team, else displayName/username."""
    a = author_obj or {}
    name = a.get('name', '')
    return DEFAULT_DISPLAY_NAMES.get(name, a.get('displayName') or name or '?')
