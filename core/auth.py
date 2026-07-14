"""Google OAuth login + signed session cookies (stdlib + requests, no new deps).

Replaces the Cloudflare-Access header-trust model with real in-app auth:
the app redirects to Google, verifies the returned email is genuinely owned
AND ends with ALLOWED_DOMAIN (@baokim.vn), then issues an HMAC-signed session
cookie. Anyone without a valid cookie is bounced to /login.

Layer: config -> (this) ; uses `requests` like jira_api. No import cycle.

If GOOGLE_CLIENT_ID/SECRET are not set, AUTH_ENABLED is False and the caller
falls back to the old behaviour (local dev = everyone is admin).
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlencode

import requests

from config import (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET,
                    AUTH_ENABLED, ALLOWED_DOMAIN, derive_subkey)

# ----- constants -----
SESSION_COOKIE = 'qa_session'
STATE_COOKIE = 'qa_oauth_state'
DRIVE_STATE_COOKIE = 'qa_drive_state'   # state riêng cho luồng "Kết nối Drive" (#52)
SESSION_TTL = 7 * 24 * 3600      # 7 ngày (issue #161). Sliding: đang dùng thì gia hạn liên
                                 # tục (xem session_status); chỉ idle > 7 ngày mới phải login lại.
STATE_TTL = 600                  # state CSRF sống 10 phút

_AUTH_EP = 'https://accounts.google.com/o/oauth2/v2/auth'
_TOKEN_EP = 'https://oauth2.googleapis.com/token'
_USERINFO_EP = 'https://www.googleapis.com/oauth2/v2/userinfo'

# Scope chỉ-đọc Drive cho luồng "Kết nối Drive" (issue #52). drive.readonly = đọc file,
# KHÔNG sửa được -> giữ permission file nguyên trạng, không lộ data ra ngoài.
DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.readonly'

# Khoá HMAC ký session/state cookie = khoá con TÁCH-MIỀN từ SESSION_SECRET (issue #45),
# KHÔNG dùng trực tiếp SESSION_SECRET (vốn cũng là nguồn khoá mã hoá PAT). Tách nhãn vai
# trò => rò rỉ khoá này không kéo theo giải mã được PAT. b'' khi auth disabled (như trước).
_SECRET = derive_subkey('qa-dashboard/session-cookie-hmac/v1', 32)


# ----- signed token helpers (payload.b64 . hmac) -----
def _sign(payload_b64):
    return hmac.new(_SECRET, payload_b64, hashlib.sha256).hexdigest()


def _make_token(data):
    """data dict -> 'b64(json).sig'. exp đã nằm trong data."""
    raw = json.dumps(data, separators=(',', ':')).encode('utf-8')
    b64 = base64.urlsafe_b64encode(raw)
    return b64.decode('ascii') + '.' + _sign(b64)


def _read_token(token):
    """'b64.sig' -> dict nếu chữ ký đúng & chưa hết hạn, else None."""
    if not token or '.' not in token or not _SECRET:
        return None
    b64, _, sig = token.partition('.')
    try:
        b64b = b64.encode('ascii')
        if not hmac.compare_digest(_sign(b64b), sig):
            return None
        data = json.loads(base64.urlsafe_b64decode(b64b))
    except (ValueError, json.JSONDecodeError):
        return None
    if float(data.get('exp', 0)) < time.time():
        return None
    return data


# ----- session -----
def make_session_token(email):
    now = time.time()
    # iat (issued-at) để sliding refresh biết token đã sống bao lâu (issue #161).
    return _make_token({'email': email, 'iat': now, 'exp': now + SESSION_TTL})


def email_from_session(token):
    data = _read_token(token)
    return (data or {}).get('email', '') if data else ''


def session_status(token):
    """-> (email, needs_refresh). email='' nếu cookie hỏng/hết hạn.

    needs_refresh=True khi cookie CÒN hạn nhưng đã qua nửa đời -> caller cấp lại cookie
    (sliding session, #161): người đang dùng không bao giờ bị đá về login, chỉ idle hẳn
    quá SESSION_TTL mới phải login lại. Token cũ thiếu 'iat' (trước #161) -> suy từ exp."""
    data = _read_token(token)
    if not data:
        return '', False
    email = data.get('email', '')
    if not email:
        return '', False
    iat = float(data.get('iat', float(data.get('exp', 0)) - SESSION_TTL))
    needs = (time.time() - iat) > (SESSION_TTL / 2)
    return email, needs


# ----- OAuth state (CSRF) -----
def make_state_token(app=False):
    """State CSRF cho OAuth. app=True => nhúng cờ 'app' (ký HMAC, không giả được) để
    _do_callback biết đây là luồng client mobile -> giao token qua App Link (D2 hướng C)."""
    data = {'n': secrets.token_urlsafe(16), 'exp': time.time() + STATE_TTL}
    if app:
        data['app'] = True
    return _make_token(data)


def state_valid(token):
    return _read_token(token) is not None


def state_data(token):
    """dict state nếu chữ ký đúng & chưa hết hạn (đọc cờ 'app'), else None."""
    return _read_token(token)


# ----- OAuth flow -----
def login_url(redirect_uri, state):
    """URL Google để redirect người dùng tới đăng nhập."""
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'access_type': 'online',
        'prompt': 'select_account',
    }
    if ALLOWED_DOMAIN:
        params['hd'] = ALLOWED_DOMAIN   # gợi ý chọn tài khoản workspace
    return _AUTH_EP + '?' + urlencode(params)


def exchange_code(code, redirect_uri):
    """Đổi authorization code -> userinfo dict {email, verified_email, hd, name}.
    Raise RuntimeError nếu lỗi. KHÔNG log token."""
    try:
        tok = requests.post(_TOKEN_EP, data={
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        }, timeout=15)
        if tok.status_code != 200:
            raise RuntimeError('token exchange failed')
        access = tok.json().get('access_token')
        if not access:
            raise RuntimeError('no access_token')
        info = requests.get(_USERINFO_EP,
                            headers={'Authorization': f'Bearer {access}'}, timeout=15)
        if info.status_code != 200:
            raise RuntimeError('userinfo failed')
        return info.json()
    except requests.RequestException:
        raise RuntimeError('Google OAuth network error')


# ----- Drive OAuth (admin-only, TÁCH khỏi login chung — issue #52) -----
# Login chung dùng access_type=online + prompt=select_account (KHÔNG trả refresh_token).
# Luồng này xin scope drive.readonly + offline + consent để Google trả refresh_token một
# lần cho admin -> background thread (#54) tự refresh ra access_token đọc file .xlsx bug log.
def drive_login_url(redirect_uri, state):
    """URL Google để admin cấp quyền Drive (offline -> trả refresh_token)."""
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email ' + DRIVE_SCOPE,
        'state': state,
        'access_type': 'offline',   # bắt buộc để Google trả refresh_token
        # select_account -> luôn hiện màn CHỌN tài khoản (không tự nhảy account default);
        # consent -> ép hỏi lại consent => luôn có refresh_token (kể cả đã cấp trước)
        'prompt': 'select_account consent',
    }
    if ALLOWED_DOMAIN:
        params['hd'] = ALLOWED_DOMAIN
    return _AUTH_EP + '?' + urlencode(params)


def exchange_code_tokens(code, redirect_uri):
    """Đổi authorization code -> (userinfo dict, refresh_token | None).

    Giống exchange_code nhưng GIỮ LẠI refresh_token (login chung vứt đi). Dùng cho
    luồng Drive. Raise RuntimeError nếu lỗi. KHÔNG log token."""
    try:
        tok = requests.post(_TOKEN_EP, data={
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        }, timeout=15)
        if tok.status_code != 200:
            raise RuntimeError('token exchange failed')
        body = tok.json()
        access = body.get('access_token')
        if not access:
            raise RuntimeError('no access_token')
        refresh = body.get('refresh_token')  # chỉ có khi access_type=offline + consent
        info = requests.get(_USERINFO_EP,
                            headers={'Authorization': f'Bearer {access}'}, timeout=15)
        if info.status_code != 200:
            raise RuntimeError('userinfo failed')
        return info.json(), refresh
    except requests.RequestException:
        raise RuntimeError('Google OAuth network error')


def refresh_access_token(refresh_token):
    """refresh_token -> (access_token: str, expires_in: int). Raise RuntimeError nếu lỗi.

    KHÔNG log token; redact refresh_token khỏi mọi error message."""
    if not refresh_token:
        raise RuntimeError('thiếu refresh_token')
    try:
        r = requests.post(_TOKEN_EP, data={
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }, timeout=15)
        if r.status_code != 200:
            # 400 invalid_grant = token bị revoke/đổi mật khẩu -> báo mềm, không lộ token
            raise RuntimeError(f'refresh access_token thất bại (HTTP {r.status_code})')
        body = r.json()
        access = body.get('access_token')
        if not access:
            raise RuntimeError('không nhận được access_token')
        return access, int(body.get('expires_in', 3600))
    except requests.RequestException as e:
        msg = str(e).replace(refresh_token, '<REDACTED>')
        raise RuntimeError(f'lỗi mạng khi refresh token: {msg}')


def email_allowed(userinfo):
    """True nếu email đã verify và đúng domain cho phép."""
    email = (userinfo.get('email') or '').strip().lower()
    if not email:
        return False, ''
    if not userinfo.get('verified_email', False):
        return False, email
    if ALLOWED_DOMAIN and not email.endswith('@' + ALLOWED_DOMAIN):
        return False, email
    return True, email
