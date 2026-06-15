"""OAuthMixin — login/callback/logout (Google) + Drive connect/callback.

Tách từ qa_dashboard.py (issue #86 / B1). Zero behavior change: chỉ di chuyển định
nghĩa method, không đổi logic/route/output.

Mixin dùng các helper dùng chung định nghĩa ở Handler (resolve qua MRO):
`self._base_url()`, `self._redirect()`, `self._cookie()`, `self._forbidden()`,
`self._html()`, `self._is_admin()`. Hai helper CHỈ OAuth dùng (`_secure_cookie`,
`_set_cookie`) gom luôn vào đây.

Layer rule: KHÔNG import qa_dashboard (tránh vòng import).
"""
from urllib.parse import urlparse, parse_qs

from config import AUTH_ENABLED, PUBLIC_BASE_URL
from auth import (SESSION_COOKIE, STATE_COOKIE, DRIVE_STATE_COOKIE, SESSION_TTL, STATE_TTL,
                  login_url, exchange_code, email_allowed,
                  make_session_token, make_state_token, state_valid,
                  drive_login_url, exchange_code_tokens)
from drive_token import save_refresh_token
from render import render_error_page, render_login_page


class OAuthMixin:
    # ----- cookie helpers (chỉ OAuth dùng) -----
    def _secure_cookie(self):
        """Cờ Secure cho cookie. Dùng base_url (đã ưu tiên PUBLIC_BASE_URL); khi AUTH bật ở
        prod mà chưa set PUBLIC_BASE_URL, vẫn ép Secure trừ khi host là loopback — để
        client KHÔNG ép rớt Secure qua X-Forwarded-Proto: http (issue #49)."""
        base = self._base_url()
        if base.startswith('https'):
            return True
        host = self.headers.get('Host', '')
        is_loopback = host.startswith(('localhost', '127.0.0.1'))
        return AUTH_ENABLED and not PUBLIC_BASE_URL and not is_loopback

    def _set_cookie(self, name, value, max_age, secure):
        parts = [f'{name}={value}', 'Path=/', 'HttpOnly', 'SameSite=Lax',
                 f'Max-Age={max_age}']
        if secure:
            parts.append('Secure')
        return '; '.join(parts)

    # ----- OAuth routes -----
    def _do_login(self):
        # Mặc định: hiện màn hình đăng nhập (nút "Đăng nhập với Google"). CHỈ khi user
        # bấm nút (-> ?go=1) mới set state cookie + 302 sang Google. Trước đây 302 thẳng
        # nên không có màn login nào hiện ra.
        q = parse_qs(urlparse(self.path).query)
        if (q.get('go') or [''])[0] != '1':
            self._html(render_login_page())
            return
        state = make_state_token()
        secure = self._secure_cookie()
        url = login_url(self._base_url() + '/oauth/callback', state)
        self._redirect(url, [self._set_cookie(STATE_COOKIE, state, STATE_TTL, secure)])

    def _do_callback(self):
        q = parse_qs(urlparse(self.path).query)
        code = (q.get('code') or [''])[0]
        state = (q.get('state') or [''])[0]
        if not code or not state or state != self._cookie(STATE_COOKIE) or not state_valid(state):
            self._forbidden()
            return
        try:
            info = exchange_code(code, self._base_url() + '/oauth/callback')
        except RuntimeError as e:
            self._html(render_error_page(str(e)))
            return
        ok, email = email_allowed(info)
        if not ok:
            self._forbidden()
            return
        secure = self._secure_cookie()
        self._redirect('/', [
            self._set_cookie(SESSION_COOKIE, make_session_token(email), SESSION_TTL, secure),
            self._set_cookie(STATE_COOKIE, '', 0, secure),  # clear state
        ])

    def _do_logout(self):
        secure = self._secure_cookie()
        self._redirect('/login', [self._set_cookie(SESSION_COOKIE, '', 0, secure)])

    # ----- Drive connect (admin-only, tách khỏi login chung — issue #52) -----
    def _do_drive_connect(self):
        if not self._is_admin():
            self._forbidden()
            return
        state = make_state_token()
        secure = self._secure_cookie()
        url = drive_login_url(self._base_url() + '/oauth/drive-callback', state)
        self._redirect(url, [self._set_cookie(DRIVE_STATE_COOKIE, state, STATE_TTL, secure)])

    def _do_drive_callback(self):
        if not self._is_admin():
            self._forbidden()
            return
        q = parse_qs(urlparse(self.path).query)
        code = (q.get('code') or [''])[0]
        state = (q.get('state') or [''])[0]
        if not code or not state or state != self._cookie(DRIVE_STATE_COOKIE) or not state_valid(state):
            self._forbidden()
            return
        secure = self._secure_cookie()
        clear = self._set_cookie(DRIVE_STATE_COOKIE, '', 0, secure)
        try:
            info, refresh = exchange_code_tokens(code, self._base_url() + '/oauth/drive-callback')
        except RuntimeError as e:
            self._html(render_error_page(str(e)))
            return
        ok, _email = email_allowed(info)  # token phải của tài khoản đúng domain
        if not ok:
            self._forbidden()
            return
        save_ok, _msg = save_refresh_token(refresh)
        if not save_ok:
            self._html(render_error_page(_msg))
            return
        self._redirect('/bug-log', [clear])
