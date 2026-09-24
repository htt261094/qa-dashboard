"""Lớp biên Jira Cloud (#197) — mọi khác biệt Cloud vs Data Center gom về đây.

Jira Cloud khác DC ở 3 chỗ gốc:
  1. Auth: Basic base64(email:api_token) thay PAT Bearer.
  2. Identity: GDPR mode — KHÔNG còn `name`/`username`, chỉ còn `accountId`.
  3. Tên status sau migrate đổi case ('Done', 'To Do'), changelog cũ giữ tên DC ('DONE', 'TO DO').

Chiến lược "dịch ở biên": identity NỘI BỘ của app vẫn là username (= local-part email, vd
'quangbm') -> mọi store (custom_status, task_link, pat_store, dismissed, KV) giữ nguyên khoá,
KHÔNG migrate data. Chỉ dịch ở ranh giới gọi Jira:
  - ĐỌC: normalize() duyệt response, gắn `name` = username vào mọi user object, đưa tên
    status về tên DC, đổi mention `[~accountid:X]` -> `[~username]` -> accessor i_*,
    actor_name, render, JS (twin) chạy y như trước.
  - GHI / JQL: jql_user()/user_ref()/mentions_to_accounts() đổi username -> accountId.

Người không có email hiển thị (privacy) -> identity = 'accountid:<id>' (vẫn dùng được cho
mention/JQL/payload vì account_id() nhận cả dạng này).

Layer: config -> (this) -> jira_api / jira_write / pat_store. Không import ngược.
Token KHÔNG bao giờ được log/print — lỗi mạng redact trước khi raise.
"""
import base64
import json
import re
import sys
import threading
import time

import requests

from config import (JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_ACCOUNT_IDS,
                    JIRA_ACCOUNTS_FILE, ALLOWED_DOMAIN, OFFLINE, atomic_write)

# Domain email công ty — dựng email từ username để tìm accountId ('quangbm' -> quangbm@baokim.vn).
MAIL_DOMAIN = (ALLOWED_DOMAIN or JIRA_EMAIL.split('@')[-1] or 'baokim.vn').lower()
_ACC_PREFIX = 'accountid:'


# ===== AUTH =====

def basic_auth(email, token):
    """Giá trị header Authorization cho Jira Cloud (email + API token)."""
    raw = f'{email}:{token}'.encode('utf-8')
    return 'Basic ' + base64.b64encode(raw).decode('ascii')


def auth_headers(email=None, token=None, extra=None):
    """Header gọi Jira. Mặc định = token CHUNG (.env); truyền email/token để gọi nhân danh
    1 người (token cá nhân — Decision #20)."""
    h = {'Authorization': basic_auth(email or JIRA_EMAIL, token or JIRA_API_TOKEN),
         'Accept': 'application/json'}
    if extra:
        h.update(extra)
    return h


def split_cred(cred):
    """Credential cá nhân lưu dạng 'email:token' (chính là cặp Basic auth). Trả (email, token)
    hoặc (None, None) nếu không đúng dạng (vd PAT Jira DC cũ không có ':' -> coi như chưa có)."""
    if not cred or not isinstance(cred, str) or ':' not in cred:
        return None, None
    email, token = cred.split(':', 1)
    email, token = email.strip(), token.strip()
    if '@' not in email or not token:
        return None, None
    return email, token


def redact(msg, *secrets):
    """Xoá token (chung + cá nhân) khỏi chuỗi lỗi trước khi log/trả client."""
    if not isinstance(msg, str):
        return msg
    for s in (JIRA_API_TOKEN,) + secrets:
        if s:
            msg = msg.replace(s, '<REDACTED>')
    return msg


# ===== STATUS: đưa tên Cloud về tên DC =====
# Downstream (Python bucket/filter + JS pill/badge/twin) so khớp tên status DC chính xác
# ('TO DO', 'DONE'...). Cloud trả 'To Do'/'Done', changelog migrate lại giữ 'TO DO'/'DONE'
# -> chuẩn hoá MỘT chỗ ở biên thay vì sửa ~40 chỗ so sánh. Status lạ giữ nguyên.
_STATUS_CANON = {
    'to do': 'TO DO',
    'in progress': 'In Progress',
    'pending': 'PENDING',
    'done': 'DONE',
    'cancelled': 'CANCELLED',
    'canceled': 'CANCELLED',
}


def canon_status(name):
    if not isinstance(name, str):
        return name
    return _STATUS_CANON.get(name.strip().lower(), name)


# ===== MAP username <-> accountId =====
_lock = threading.Lock()
_by_user = {}          # username -> accountId
_by_acc = {}           # accountId -> username
_miss_at = {}          # username -> monotonic lần resolve fail gần nhất (negative cache)
_MISS_TTL = 600


def _load_map():
    try:
        if JIRA_ACCOUNTS_FILE.exists():
            d = json.loads(JIRA_ACCOUNTS_FILE.read_text(encoding='utf-8'))
            if isinstance(d, dict):
                for u, a in d.items():
                    if isinstance(u, str) and isinstance(a, str) and a:
                        _by_user[u.lower()] = a
                        _by_acc[a] = u.lower()
    except (OSError, ValueError):
        pass
    if JIRA_ACCOUNT_IDS:           # env override THẮNG cache file
        try:
            for u, a in (json.loads(JIRA_ACCOUNT_IDS) or {}).items():
                if u and a:
                    _by_user[str(u).lower()] = str(a)
                    _by_acc[str(a)] = str(u).lower()
        except ValueError:
            print('[WARN] JIRA_ACCOUNT_IDS không phải JSON hợp lệ — bỏ qua', file=sys.stderr)


_load_map()


def _persist():
    with _lock:
        snap = dict(_by_user)
    atomic_write(JIRA_ACCOUNTS_FILE, json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True))


def _local_part(email):
    return (email or '').strip().lower().split('@')[0] if email and '@' in email else ''


def remember(account_id, username):
    """Ghi nhận cặp (accountId, username) thấy được trong response. Persist khi có cặp mới."""
    if not account_id or not username or username.startswith(_ACC_PREFIX):
        return
    with _lock:
        if _by_user.get(username) == account_id:
            return
        _by_user[username] = account_id
        _by_acc[account_id] = username
    _persist()


def username_of(user_obj):
    """Username nội bộ của 1 user object Cloud: local-part email > map đã biết > 'accountid:<id>'."""
    if not isinstance(user_obj, dict):
        return ''
    acc = user_obj.get('accountId') or ''
    u = _local_part(user_obj.get('emailAddress'))
    if u:
        # CHỈ học map từ email cùng domain công ty — email ngoài có thể trùng local-part
        if (user_obj.get('emailAddress') or '').lower().endswith('@' + MAIL_DOMAIN):
            remember(acc, u)
        return u
    with _lock:
        known = _by_acc.get(acc)
    if known:
        return known
    return f'{_ACC_PREFIX}{acc}' if acc else ''


def username_of_account(account_id):
    """accountId -> username đã biết (None nếu chưa gặp)."""
    with _lock:
        return _by_acc.get(account_id)


def _resolve_remote(username):
    """Tìm accountId theo email <username>@<domain> qua /user/search (token chung).
    Trả accountId hoặc None. Không raise."""
    if OFFLINE:
        return None
    email = f'{username}@{MAIL_DOMAIN}'
    try:
        r = requests.get(f'{JIRA_URL}/rest/api/2/user/search', headers=auth_headers(),
                         params={'query': email, 'maxResults': 10}, timeout=15)
        if r.status_code != 200:
            return None
        for u in r.json() or []:
            if (u.get('emailAddress') or '').lower() == email and u.get('accountId'):
                return u['accountId']
    except (requests.RequestException, ValueError):
        return None
    return None


def account_id(username):
    """username nội bộ -> accountId Jira Cloud. Nhận cả 'accountid:<id>' / accountId trần.
    Resolve lazy + cache file; fail -> None (negative cache 10' để khỏi spam Jira)."""
    u = (username or '').strip()
    if not u:
        return None
    if u.lower().startswith(_ACC_PREFIX):
        return u[len(_ACC_PREFIX):]
    if ':' in u or (len(u) >= 20 and u.isalnum()):
        return u                                   # đã là accountId (712020:uuid / 24-hex cũ)
    key = u.lower()
    with _lock:
        hit = _by_user.get(key)
        miss = _miss_at.get(key)
    if hit:
        return hit
    if miss and time.monotonic() - miss < _MISS_TTL:
        return None
    acc = _resolve_remote(key)
    if acc:
        remember(acc, key)
        return acc
    with _lock:
        _miss_at[key] = time.monotonic()
    print(f'[WARN] Không tìm được accountId Jira Cloud cho "{key}" '
          f'(email {key}@{MAIL_DOMAIN}). Khai báo JIRA_ACCOUNT_IDS trong .env nếu cần.',
          file=sys.stderr)
    return None


def warm_accounts(usernames):
    """Resolve trước 1 loạt username (gọi lúc khởi động, chạy nền). Trả list username fail."""
    return [u for u in usernames if not account_id(u)]


def jql_user(username):
    """1 user cho JQL: '"<accountId>"'. Không resolve được -> RuntimeError (JQL với user lạ
    bị Cloud trả 400 -> báo rõ thay vì lỗi mù)."""
    acc = account_id(username)
    if not acc:
        raise RuntimeError(f'Không tìm thấy tài khoản Jira Cloud cho "{username}"')
    return f'"{acc}"'


def jql_users(usernames):
    """Danh sách user cho `in (...)`: bỏ qua người không resolve được (log cảnh báo), chỉ
    raise khi KHÔNG ai resolve được (JQL rỗng sẽ vỡ)."""
    accs = [a for a in (account_id(u) for u in usernames) if a]
    if not accs:
        raise RuntimeError('Không resolve được accountId Jira Cloud cho team QA '
                           '(kiểm tra JIRA_USERS / JIRA_ACCOUNT_IDS)')
    return ', '.join(f'"{a}"' for a in accs)


def user_ref(username):
    """Giá trị field user-picker khi GHI (assignee, Leader): {'accountId': ...} hoặc None."""
    acc = account_id(username)
    return {'accountId': acc} if acc else None


# ===== MENTION =====
_MENTION_ACC_RE = re.compile(r'\[~accountid:([^\]\s]+)\]', re.I)
_MENTION_USER_RE = re.compile(r'\[~(?!accountid:)([^\]\s]+)\]', re.I)


def mentions_to_usernames(text):
    """ĐỌC: '[~accountid:X]' -> '[~username]' khi biết X (cờ mention ở feed + hiển thị)."""
    if not isinstance(text, str) or '[~' not in text:
        return text

    def _sub(m):
        u = username_of_account(m.group(1))
        return f'[~{u}]' if u else m.group(0)
    return _MENTION_ACC_RE.sub(_sub, text)


def mentions_to_accounts(text):
    """GHI: '[~username]' (autocomplete #56 chèn) -> '[~accountid:X]' để Cloud render + notify."""
    if not isinstance(text, str) or '[~' not in text:
        return text

    def _sub(m):
        acc = account_id(m.group(1))
        return f'[~accountid:{acc}]' if acc else m.group(0)
    return _MENTION_USER_RE.sub(_sub, text)


# ===== NORMALIZE response =====
_USER_FIELDS_CL = {'assignee', 'reporter', 'leader'}


def _norm_dict(d):
    # user object Cloud: có accountId (+ displayName/emailAddress) -> gắn name/key = username
    if 'accountId' in d and ('displayName' in d or 'emailAddress' in d):
        u = username_of(d)
        if u and not d.get('name'):
            d['name'] = u
        if u and not d.get('key'):
            d['key'] = u
    # status object: có statusCategory -> chuẩn hoá tên
    if 'statusCategory' in d and isinstance(d.get('name'), str):
        d['name'] = canon_status(d['name'])
    # changelog item
    if 'fromString' in d or 'toString' in d:
        fid = (d.get('fieldId') or d.get('field') or '').lower()
        if fid == 'status':
            d['fromString'] = canon_status(d.get('fromString'))
            d['toString'] = canon_status(d.get('toString'))
        elif fid in _USER_FIELDS_CL:
            for k in ('from', 'to'):
                acc = d.get(k)
                if acc:
                    d[k] = username_of_account(acc) or f'{_ACC_PREFIX}{acc}'
    # văn bản có mention (comment body / description)
    for k in ('body', 'description'):
        if isinstance(d.get(k), str):
            d[k] = mentions_to_usernames(d[k])


def normalize(obj):
    """Duyệt đệ quy response JSON Jira Cloud, sửa TẠI CHỖ về hình dạng DC-tương-thích. Trả obj.
    Duyệt con TRƯỚC cha -> user object (author/assignee) được học map trước khi item changelog
    cùng issue cần tra accountId."""
    stack = [(obj, False)]
    while stack:
        node, visited = stack.pop()
        if isinstance(node, dict):
            if visited:
                _norm_dict(node)
            else:
                stack.append((node, True))
                stack.extend((v, False) for v in node.values() if isinstance(v, (dict, list)))
        elif isinstance(node, list):
            stack.extend((v, False) for v in node if isinstance(v, (dict, list)))
    return obj
