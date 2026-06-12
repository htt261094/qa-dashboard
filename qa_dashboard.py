#!/usr/bin/env python3
"""QA Team Dashboard for Jira (Bảo Kim) — entry point.

Local web server on http://localhost:<PORT>. F5 = fresh pull from Jira.
Layered modules: config -> issues -> {jira_api, state} -> render -> (this file).
Run: python qa_dashboard.py
"""
import http.server
import socketserver
import json
import sys
import os
from datetime import datetime
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs

# Core modules live in ./core/ (issue #85). Add it to sys.path so sibling-style
# imports (`from config import ...`) keep working unchanged.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'core'))

from config import (JIRA_URL, USERS, PORT, STATE_FILE, ADMIN_EMAIL, ALLOWED_DOMAIN,
                    AUTH_ENABLED, SELF_USER, PUBLIC_BASE_URL,
                    display_name, username_from_email)
from auth import (SESSION_COOKIE, STATE_COOKIE, DRIVE_STATE_COOKIE, SESSION_TTL, STATE_TTL,
                  login_url, exchange_code, email_allowed, email_from_session,
                  make_session_token, make_state_token, state_valid,
                  drive_login_url, exchange_code_tokens)
from drive_token import save_refresh_token, has_drive_token, delete_drive_token
from bug_log_store import (scan as bug_log_scan, start_scheduler as start_bug_log_scheduler,
                           load_bug_log)
from bug_log_source import load_sources, save_sources, extract_file_id, MAX_SOURCES
from task_link import load_links, set_task_links, tasks_of
from jira_api import (fetch_all, fetch_activity_feed, load_dismissed,
                      dismiss_activities, run_parallel, fetch_issue_detail,
                      search_parent_ptsp, search_people, search_qa_tasks, global_search)
from state import load_snapshots, save_snapshots, build_snapshot
from docs import load_docs, save_docs, valid_tree
from roadmap import load_roadmap, save_roadmap, valid_roadmap
from pat_store import save_user_pat, has_pat, delete_user_pat, load_user_pat
from custom_status import (load_bundle, set_custom_status, is_valid, values_of)
from jira_write import get_transitions, do_transition, add_comment, create_subtask
from render import (render_page, render_qa_v2, render_docs_page,
                    render_roadmap_v2, render_bug_log_v2,
                    render_settings_page, render_error_page, render_403)

ACTIVITY_DAYS = 7  # cửa sổ activity feed kéo từ Jira changelog


def _build_view(data, scope):
    """Snapshot diff để highlight task mới (new_keys). Activity giờ kéo từ Jira feed
    (device-independent), không còn dùng local diff/pending.

    Baseline RIÊNG cho từng scope (admin='__all__', QA=username): data của scope này
    KHÔNG ghi đè baseline scope khác. Trước đây dùng chung 1 snapshot -> admin (toàn team)
    và QA (1 người) giẫm baseline nhau, khiến task cũ bị gắn NEW oan rồi nhấp nháy."""
    cur_snapshot = build_snapshot(data)
    scope_key = scope or '__all__'
    snaps = load_snapshots()
    prev_snap = snaps.get(scope_key)
    first_run = prev_snap is None
    new_keys = set() if first_run else (set(cur_snapshot) - set(prev_snap.keys()))
    snaps[scope_key] = cur_snapshot
    save_snapshots(snaps)
    return new_keys, first_run


# ===== HTTP server =====
class Handler(http.server.BaseHTTPRequestHandler):
    # ----- Auth (Google OAuth login + session cookie ký HMAC) -----
    # Identity = session cookie (đặt sau khi đăng nhập Google, đã verify @ALLOWED_DOMAIN).
    # Fallback Cloudflare Access header nếu có (không bắt buộc). AUTH_ENABLED=False -> local dev.
    def _cookies(self):
        c = SimpleCookie()
        raw = self.headers.get('Cookie')
        if raw:
            try:
                c.load(raw)
            except Exception:
                pass
        return c

    def _cookie(self, name):
        m = self._cookies().get(name)
        return m.value if m else ''

    def _base_url(self):
        """scheme://host gốc để build redirect_uri OAuth + quyết cờ Secure cookie.

        Ưu tiên PUBLIC_BASE_URL trong .env (prod) -> KHÔNG tin Host/X-Forwarded-Proto của
        client (chống Host-header injection, issue #49). Chưa cấu hình => suy từ request
        (local dev: localhost/127.0.0.1)."""
        if PUBLIC_BASE_URL:
            return PUBLIC_BASE_URL
        host = self.headers.get('Host', f'localhost:{PORT}')
        proto = (self.headers.get('X-Forwarded-Proto')
                 or ('http' if host.startswith(('localhost', '127.0.0.1')) else 'https'))
        return f'{proto}://{host}'

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

    def _user_email(self):
        """Email người đăng nhập từ session cookie; fallback Cloudflare header. '' nếu chưa login."""
        email = email_from_session(self._cookie(SESSION_COOKIE))
        if email:
            return email
        return (self.headers.get('Cf-Access-Authenticated-User-Email') or '').strip().lower()

    def _authed(self):
        """Request có được phép vào không. AUTH tắt -> luôn True (local dev)."""
        if not AUTH_ENABLED:
            return True
        return bool(self._user_email())

    def _domain_ok(self):
        """Domain gate ở tầng app (defense-in-depth; login Google đã verify sẵn)."""
        email = self._user_email()
        if not email or not ALLOWED_DOMAIN:   # local, hoặc chưa cấu hình domain -> cho qua
            return True
        return email.endswith('@' + ALLOWED_DOMAIN)

    def _is_admin(self):
        """Role admin = được edit roadmap/tài liệu. Local (chưa login) -> admin (chính bạn)."""
        email = self._user_email()
        if not email or not ADMIN_EMAIL:
            return not AUTH_ENABLED  # AUTH bật mà chưa login -> KHÔNG phải admin
        return email == ADMIN_EMAIL

    def _user_ctx(self):
        """(email, is_admin) cho nav chip; None khi chưa login (local dev)."""
        email = self._user_email()
        return (email, self._is_admin()) if email else None

    def _self_username(self):
        """Jira username của chính người đăng nhập (cho tab My work). Local dev /
        admin-email-không-trong-USERS -> SELF_USER (default thanhht1)."""
        return username_from_email(self._user_email()) or username_from_email(ADMIN_EMAIL) or SELF_USER

    def _bugs_for_task(self, task_key):
        """Chiều ngược của task_link: list bug ĐÃ LINK tới `task_key`, cho drawer detail.
        Nguồn = load_links() (bugKey->task) ∩ load_bug_log() (chi tiết bug). Đọc cache
        local/property -> nhẹ. Lỗi -> [] (drawer vẫn mở bình thường, chỉ thiếu mục bug)."""
        try:
            links = load_links()
        except Exception:
            return []
        bug_keys = [bk for bk, v in links.items() if task_key in tasks_of(v)]
        if not bug_keys:
            return []
        try:
            files = (load_bug_log() or {}).get('files', {}) or {}
        except Exception:
            return []
        idx = {}
        for f in files.values():
            for k, b in (f.get('bugs', {}) or {}).items():
                idx[k] = b
        out = []
        for bk in bug_keys:
            b = idx.get(bk)
            if not b:
                continue
            out.append({
                'id': f"{b.get('project', '')}-{b.get('service') + '-' if b.get('service') else ''}{b.get('bug_no', '')}".strip('-'),
                'summary': b.get('summary', ''),
                'severity': b.get('severity', ''),
                'status': b.get('status', ''),
                'module': b.get('feature', ''),
            })
        return out

    def _bell_activities(self, with_patch=False):
        """Activities cho chuông notif — TÍNH GIỐNG HỆT ở mọi tab để bell đồng nhất.
        Scope = đúng như dashboard `/`: admin/local -> cả team (None), QA -> chính họ.
        Gồm cả custom-status events (cust_act) + cờ is_unread theo dismissed của người đăng nhập.
        Tách khỏi data trang (mỗi tab vẫn tự fetch data riêng theo scope của nó).

        with_patch=True -> trả (merged, tasks) với tasks={key:{status?,customs}} để client
        vá status + nhãn nội bộ real-time qua poll (Decision #24), KHÔNG reload. status lấy
        từ chính feed (issue đổi trong window), customs từ overlay -> gần như zero extra call."""
        email = self._user_email()
        scope = None if self._is_admin() else username_from_email(email)
        try:
            res = run_parallel({
                'feed': lambda: fetch_activity_feed(days=ACTIVITY_DAYS, scope_user=scope,
                                                    with_status=with_patch),
                'dismissed': lambda: load_dismissed(email),
                'custom': lambda: load_bundle(scope, ACTIVITY_DAYS),
            })
        except RuntimeError:
            # Jira không với tới được -> chuông RỖNG, KHÔNG kéo sập cả trang. Các tab không
            # cần Jira (Tài liệu/Roadmap/Bug Log/Cài đặt — data đọc cache local) vẫn hoạt động;
            # tab cần Jira (`/`, /my-work, /leader-eval) tự show lỗi từ data job của nó.
            return ([], {}) if with_patch else []
        dismissed = res['dismissed']
        overlay, cust_act = res['custom']
        feed = res['feed']
        statuses = {}
        if with_patch:
            feed, statuses = feed
        merged = sorted(feed + cust_act, key=lambda a: a.get('when') or '', reverse=True)
        for a in merged:
            a['is_unread'] = a['id'] not in dismissed
        if not with_patch:
            return merged
        # patch cho từng task có khả năng vừa đổi: status (từ feed) hoặc nhãn custom (overlay/cust_act).
        # customs LUÔN gửi list (kể cả [] khi gỡ hết nhãn) -> client xoá chip cũ chính xác.
        keys = set(statuses) | set(overlay) | {a.get('key') for a in cust_act if a.get('key')}
        tasks = {}
        for k in keys:
            entry = {'customs': values_of(overlay.get(k))}
            if statuses.get(k):
                entry['status'] = statuses[k]
            tasks[k] = entry
        return merged, tasks

    def _forbidden(self):
        # Trang 403 tối giản — KHÔNG lộ domain/điều kiện được phép (giấu thông tin).
        self.send_response(403)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(render_403().encode('utf-8'))

    def _redirect(self, location, cookies=None):
        self.send_response(302)
        self.send_header('Location', location)
        for ck in (cookies or []):
            self.send_header('Set-Cookie', ck)
        self.end_headers()

    def _set_cookie(self, name, value, max_age, secure):
        parts = [f'{name}={value}', 'Path=/', 'HttpOnly', 'SameSite=Lax',
                 f'Max-Age={max_age}']
        if secure:
            parts.append('Secure')
        return '; '.join(parts)

    # ----- OAuth routes -----
    def _do_login(self):
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

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/login':
            self._do_login()
            return
        if path == '/oauth/callback':
            self._do_callback()
            return
        if path == '/logout':
            self._do_logout()
            return
        if not self._authed():
            self._redirect('/login')
            return
        if not self._domain_ok():
            self._forbidden()
            return
        # ----- Drive connect (admin-only) — sau gate authed/domain -----
        if path == '/drive/connect':
            self._do_drive_connect()
            return
        if path == '/oauth/drive-callback':
            self._do_drive_callback()
            return
        if path.startswith('/uploads/'):
            import os
            from pathlib import Path
            from urllib.parse import quote
            filename = os.path.basename(path)
            uploads_dir = Path("/Users/thanhht/qa-dashboard/uploads")
            file_path = uploads_dir / filename
            if not file_path.exists() or not file_path.is_file():
                self.send_response(404)
                self.end_headers()
                return
            ext = file_path.suffix.lower()
            content_type = 'application/octet-stream'
            if ext == '.pdf':
                content_type = 'application/pdf'
            elif ext in ('.xlsx', '.xls'):
                content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            elif ext in ('.docx', '.doc'):
                content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
                content_type = f'image/{ext[1:] if ext != ".jpg" else "jpeg"}'
            disp = 'inline' if ext in ('.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp') else 'attachment'
            try:
                data = file_path.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Disposition', f"{disp}; filename*=UTF-8''{quote(filename)}")
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_response(500)
                self.end_headers()
            return

        if self.path in ('/my-work', '/my-work.html'):
            # Việc của tôi = lens cá nhân của admin (task của chính mình). QA thường KHÔNG
            # cần (dashboard `/` của họ đã auto-scope về chính họ) -> đá về dashboard.
            if not self._is_admin():
                self._redirect('/')
                return
            scope = self._self_username()
            try:
                # data trang = task của chính admin (scope self); chuông notif = _bell_activities()
                # (đồng nhất mọi tab). overlay nhãn custom là scope-independent -> lấy từ bundle(self).
                res = run_parallel({
                    'data': lambda: fetch_all(scope),
                    'custom': lambda: load_bundle(scope, ACTIVITY_DAYS),
                    'bell': self._bell_activities,
                })
                data = res['data']
                overlay, _cust_act = res['custom']
                new_keys, _first_run = _build_view(data, scope)
                # UI hệt QA member (render_qa_v2), chỉ highlight tab "Việc của tôi" ở sidebar
                html_out = render_qa_v2(data, new_keys, res['bell'], overlay,
                                        self._user_ctx(), nav_active='mywork')
            except RuntimeError as e:
                html_out = render_error_page(str(e))
            self._html(html_out)
            return

        if self.path.startswith('/leader-eval'):
            if not self._is_admin():
                self._redirect('/')
                return
            q = parse_qs(urlparse(self.path).query)
            month_str = (q.get('month') or [''])[0]
            category = (q.get('category') or [''])[0]
            leader = (q.get('leader') or [''])[0]
            sel_assignees = q.get('assignee', [])
            
            if not month_str:
                now = datetime.now()
                month_str = f"{now.year}-{now.month:02d}"
            try:
                y, m = map(int, month_str.split('-'))
            except ValueError:
                now = datetime.now()
                y, m = now.year, now.month
            try:
                from jira_api import fetch_leader_eval_tasks, fetch_project_categories
                res = run_parallel({
                    'tasks': lambda: fetch_leader_eval_tasks(category, leader, sel_assignees, y, m),
                    'categories': fetch_project_categories,
                    'bell': self._bell_activities,
                })
                from render import render_leader_eval_page
                self._html(render_leader_eval_page(res['tasks'], y, m, user=self._user_ctx(), activities=res['bell'],
                                                   categories=res['categories'],
                                                   sel_category=category, sel_leader=leader, sel_assignees=sel_assignees))
            except RuntimeError as e:
                self._html(render_error_page(str(e)))
            return

        if self.path in ('/docs', '/docs.html'):
            # tài liệu training: load song song tài liệu và chuông notif (đồng nhất mọi tab)
            try:
                res = run_parallel({'docs': load_docs, 'bell': self._bell_activities})
                self._html(render_docs_page(res['docs'], editable=self._is_admin(),
                                            user=self._user_ctx(), activities=res['bell']))
            except RuntimeError as e:
                self._html(render_error_page(str(e)))
            return
        if self.path in ('/roadmap', '/roadmap.html'):
            # roadmap team (UI v2): roadmap + chuông notif (đồng nhất mọi tab) song song
            try:
                res = run_parallel({'roadmap': load_roadmap, 'bell': self._bell_activities})
                self._html(render_roadmap_v2(res['roadmap'], editable=self._is_admin(),
                                             user=self._user_ctx(), activities=res['bell']))
            except RuntimeError as e:
                self._html(render_error_page(str(e)))
            return
        if self.path in ('/bug-log', '/bug-log.html'):
            # Bug Log (#55): bug từ Excel/Drive (cache bug_log_store) + link app-side (task_link)
            # + chuông notif. Không gọi Jira search (cache đọc local/property) -> nhẹ.
            try:
                res = run_parallel({'bug': load_bug_log, 'links': load_links,
                                    'sources': load_sources, 'bell': self._bell_activities})
                # Bug Log mở cho MỌI QA (kể cả non-admin): liên kết Task + quản lý link
                # drive nguồn. editable=True cho mọi user đã authed (route đã gate authed).
                self._html(render_bug_log_v2(res['bug'], res['links'],
                                             editable=True,
                                             user=self._user_ctx(), activities=res['bell'],
                                             sources=res['sources']))
            except RuntimeError as e:
                self._html(render_error_page(str(e)))
            return
        if path == '/issue-comments':
            # JSON chi tiết 1 issue (drawer + comment panel lazy-load). Read-only PAT chung.
            q = parse_qs(urlparse(self.path).query)
            key = (q.get('key') or [''])[0]
            parts = key.split('-')
            if len(parts) != 2 or not parts[0].isalnum() or not parts[1].isdigit():
                self._json(400, b'{"ok":false,"msg":"key"}')
                return
            try:
                # Jira detail + bug đã link tới task (chiều ngược task_link) song song.
                res = run_parallel({'detail': lambda: fetch_issue_detail(key),
                                    'bugs': lambda: self._bugs_for_task(key)})
                detail = res['detail']
                detail['bugs'] = res['bugs']
                self._json(200, json.dumps({'ok': True, 'detail': detail}).encode('utf-8'))
            except RuntimeError:
                self._json(400, b'{"ok":false,"msg":"loi"}')
            return
        if path == '/activity-feed':
            # JSON feed cho chuông notif — client poll định kỳ để cập nhật real-time,
            # KHÔNG reload trang (Decision #24). Cùng nguồn _bell_activities() nên đồng nhất
            # mọi tab + đã gắn is_unread theo dismissed của người đăng nhập.
            try:
                acts, tasks = self._bell_activities(with_patch=True)
                self._json(200, json.dumps(
                    {'ok': True, 'activities': acts, 'tasks': tasks}).encode('utf-8'))
            except RuntimeError:
                self._json(400, b'{"ok":false}')
            return
        if path == '/has-pat':
            # FE check trước khi mở form tạo sub-task: chưa có PAT -> mở luôn modal Cài đặt PAT.
            # Lỗi Jira -> bỏ qua (ok=false) để FE vẫn mở form, backend /create-subtask tự chặn.
            try:
                self._json(200, json.dumps(
                    {'ok': True, 'hasPat': has_pat(self._user_email())}).encode('utf-8'))
            except RuntimeError:
                self._json(200, b'{"ok":false}')
            return
        if path == '/has-drive':
            # FE (modal Setting) check trạng thái kết nối Drive — admin-only. Load lười để
            # KHÔNG +1 Jira call mỗi lần render shell. Lỗi Jira -> ok=false, FE báo nhẹ.
            if not self._is_admin():
                self._json(200, b'{"ok":true,"hasDrive":false,"authEnabled":false}')
                return
            try:
                self._json(200, json.dumps(
                    {'ok': True, 'hasDrive': has_drive_token(),
                     'authEnabled': AUTH_ENABLED}).encode('utf-8'))
            except RuntimeError:
                self._json(200, b'{"ok":false}')
            return
        if path == '/search-parents':
            # type-ahead Task-PTSP cho form tạo sub-task. Read-only PAT chung.
            q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
            try:
                self._json(200, json.dumps(
                    {'ok': True, 'results': search_parent_ptsp(q)}).encode('utf-8'))
            except RuntimeError:
                self._json(400, b'{"ok":false}')
            return
        if path == '/search-tasks':
            # type-ahead task của QA team cho Bug Log linkbar (link bug -> task QA đang làm,
            # KHÔNG phải Task-PTSP của dev). Read-only PAT chung.
            q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
            try:
                self._json(200, json.dumps(
                    {'ok': True, 'results': search_qa_tasks(q)}).encode('utf-8'))
            except RuntimeError:
                self._json(400, b'{"ok":false}')
            return
        if path == '/global-search':
            # Quick-search toàn Jira cho thanh search topbar (key / số / text summary).
            # Read-only PAT chung. Mở task ra drawer qua /issue-comments khi click.
            q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
            try:
                self._json(200, json.dumps(
                    {'ok': True, 'results': global_search(q)}).encode('utf-8'))
            except RuntimeError:
                self._json(400, b'{"ok":false}')
            return
        if path == '/search-people':
            # type-ahead user (field Leader) cho form tạo sub-task. Read-only PAT chung.
            q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
            try:
                self._json(200, json.dumps(
                    {'ok': True, 'results': search_people(q)}).encode('utf-8'))
            except RuntimeError:
                self._json(400, b'{"ok":false}')
            return
        if self.path in ('/settings', '/settings.html'):
            # Cài đặt PAT cá nhân (mã hoá khi lưu) — thao tác Jira ghi đúng tên người dùng
            try:
                hd = has_drive_token() if self._is_admin() else False
                self._html(render_settings_page(has_pat(self._user_email()), user=self._user_ctx(),
                                                 has_drive=hd, auth_enabled=AUTH_ENABLED,
                                                 activities=self._bell_activities()))
            except RuntimeError as e:
                self._html(render_error_page(str(e)))
            return
        if self.path not in ('/', '/index.html'):
            self.send_response(404)
            self.end_headers()
            return
        email = self._user_email()  # dismiss tách theo người đăng nhập
        # admin/local -> scope None (xem cả team); QA thường -> scope = username của họ
        if self._is_admin():
            scope = None
        else:
            scope = username_from_email(email)
            if scope is None:   # non-admin không khớp QA nào -> không cho xem data team
                self._html(render_error_page(
                    "Tài khoản của bạn chưa được gắn với QA nào trong hệ thống. "
                    "Liên hệ admin (Thành) để cấp quyền."))
                return
        try:
            # các call độc lập -> chạy song song (fetch_all tự song song 5 call bên trong)
            res = run_parallel({
                'data': lambda: fetch_all(scope),
                'feed': lambda: fetch_activity_feed(days=ACTIVITY_DAYS, scope_user=scope),
                'dismissed': lambda: load_dismissed(email),
                # 1 lần đọc property -> (nhãn custom hiện tại, sự kiện đổi nhãn để báo admin)
                'custom': lambda: load_bundle(scope, ACTIVITY_DAYS),
                # bug log = cache local (+1 property read) -> metric bug trên dashboard admin
                'buglog': load_bug_log,
            })
            data, feed, dismissed = res['data'], res['feed'], res['dismissed']
            overlay, cust_act = res['custom']
            new_keys, first_run = _build_view(data, scope)
            # gộp custom-status events vào feed Jira, sort mới->cũ.
            # CHÚ Ý: phải GIỐNG _bell_activities() (nguồn chuông cho /my-work,/docs,/roadmap)
            # để notif đồng nhất mọi tab — `/` đã canonical nên tự tính tại đây (đỡ fetch 2 lần).
            merged = sorted(feed + cust_act, key=lambda a: a.get('when') or '', reverse=True)
            for a in merged:
                a['is_unread'] = a['id'] not in dismissed
            html_out = render_page(data, new_keys, first_run, merged, ACTIVITY_DAYS,
                                   roadmap_data=load_roadmap(), user=self._user_ctx(),
                                   custom_overlay=overlay, bug_log_data=res['buglog'])
        except RuntimeError as e:
            html_out = render_error_page(str(e))
        self._html(html_out)

    def _html(self, html_out):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        self.wfile.write(html_out.encode('utf-8'))

    def _read_json_body(self, max_len):
        length = int(self.headers.get('Content-Length', 0))
        if not (0 < length <= max_len):
            return None
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def _reply_json(self, ok, payload):
        self._json(200 if ok else 400, json.dumps(payload).encode('utf-8'))

    def _handle_jira_write(self):
        """Transition / comment THẬT lên Jira bằng PAT cá nhân của người đăng nhập.
        Không có PAT -> từ chối (để KHÔNG ghi nhầm tên tài khoản chung)."""
        pat = load_user_pat(self._user_email())
        if not pat:
            self._reply_json(False, {'ok': False, 'code': 'no_pat',
                'msg': 'Bạn chưa cấu hình PAT. Vào ⚙ Cài đặt để thêm, rồi thử lại.'})
            return
        try:
            payload = self._read_json_body(20_000)
            if not isinstance(payload, dict):
                self._reply_json(False, {'ok': False, 'msg': 'Dữ liệu không hợp lệ.'})
                return
            key = payload.get('key')
            if not isinstance(key, str) or not key:
                self._reply_json(False, {'ok': False, 'msg': 'Thiếu key task.'})
                return
            if self.path == '/jira-transitions':
                # CHỈ trả các transition QA này thật sự đổi được (theo PAT + workflow).
                ok, data = get_transitions(key, pat)
                self._reply_json(ok, {'ok': True, 'transitions': data} if ok else {'ok': False, 'msg': data})
            elif self.path == '/do-transition':
                tid = payload.get('id')
                if not isinstance(tid, (str, int)) or str(tid) == '':
                    self._reply_json(False, {'ok': False, 'msg': 'Thiếu transition id.'})
                    return
                ok, msg = do_transition(key, tid, pat)
                self._reply_json(ok, {'ok': ok, 'msg': msg})
            else:  # /add-comment
                body = payload.get('body')
                if not isinstance(body, str):
                    self._reply_json(False, {'ok': False, 'msg': 'Thiếu nội dung comment.'})
                    return
                ok, msg = add_comment(key, body[:5000], pat)
                self._reply_json(ok, {'ok': ok, 'msg': msg})
        except (ValueError, json.JSONDecodeError, OSError):
            self._reply_json(False, {'ok': False, 'msg': 'Lỗi xử lý yêu cầu.'})

    def _handle_create_subtask(self):
        """Tạo Sub-task QA dưới 1 Task-PTSP, NHÂN DANH chủ PAT cá nhân (reporter = người
        đăng nhập). Admin + QA member đều dùng được (chỉ cần đã đăng nhập + có PAT)."""
        import re
        pat = load_user_pat(self._user_email())
        if not pat:
            self._reply_json(False, {'ok': False, 'code': 'no_pat',
                'msg': 'Bạn chưa cấu hình PAT. Vào ⚙ Cài đặt để thêm, rồi thử lại.'})
            return
        try:
            payload = self._read_json_body(20_000)
            if not isinstance(payload, dict):
                self._reply_json(False, {'ok': False, 'msg': 'Dữ liệu không hợp lệ.'})
                return
            parent = (payload.get('parent') or '').strip()
            summary = payload.get('summary') or ''
            duedate = (payload.get('duedate') or '').strip()
            start_date = (payload.get('startDate') or '').strip()
            assignee = (payload.get('assignee') or '').strip() or None
            leader = (payload.get('leader') or '').strip() or None
            if not re.match(r'^[A-Za-z0-9]+-\d+$', parent):
                self._reply_json(False, {'ok': False, 'msg': 'Task cha không hợp lệ.'})
                return
            datep = r'^\d{4}-\d{2}-\d{2}$'
            if not re.match(datep, duedate) or not re.match(datep, start_date):
                self._reply_json(False, {'ok': False,
                    'msg': 'Ngày phải đúng định dạng YYYY-MM-DD.'})
                return
            ok, res = create_subtask(parent, summary, duedate, start_date,
                                     assignee, leader, pat)
            if ok:
                self._reply_json(True, {'ok': True, 'key': res,
                    'url': f'{JIRA_URL}/browse/{res}', 'msg': f'Đã tạo {res} ✓'})
            else:
                self._reply_json(False, {'ok': False, 'msg': res})
        except (ValueError, json.JSONDecodeError, OSError):
            self._reply_json(False, {'ok': False, 'msg': 'Lỗi xử lý yêu cầu.'})

    def do_POST(self):
        if not self._authed() or not self._domain_ok():
            self._json(403, b'{"ok":false,"err":"forbidden"}')
            return
        if self.path == '/dismiss':
            ok = False
            try:
                length = int(self.headers.get('Content-Length', 0))
                if 0 < length <= 100_000:
                    payload = json.loads(self.rfile.read(length).decode('utf-8'))
                    ids = payload.get('ids') if isinstance(payload, dict) else None
                    if isinstance(ids, list) and all(isinstance(x, str) for x in ids):
                        ok = dismiss_activities(self._user_email(), ids[:500])
            except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
                ok = False
            self._json(200 if ok else 400, b'{"ok":true}' if ok else b'{"ok":false}')
            return
        if self.path == '/save-pat':
            # Lưu PAT cá nhân (mã hoá). Bất kỳ user đã đăng nhập đều lưu được PAT CỦA HỌ.
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not (0 < length <= 10_000):
                    self._json(400, b'{"ok":false,"msg":"payload"}')
                    return
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                pat = payload.get('pat') if isinstance(payload, dict) else None
                if not isinstance(pat, str):
                    self._json(400, b'{"ok":false,"msg":"thieu pat"}')
                    return
                ok, msg = save_user_pat(self._user_email(), pat)
            except (ValueError, json.JSONDecodeError, OSError):
                ok, msg = False, 'Lỗi xử lý yêu cầu.'
            self._json(200 if ok else 400,
                       json.dumps({'ok': ok, 'msg': msg}).encode('utf-8'))
            return
        if self.path == '/delete-pat':
            try:
                ok = delete_user_pat(self._user_email())
            except (RuntimeError, OSError):
                ok = False
            self._json(200 if ok else 400, b'{"ok":true}' if ok else b'{"ok":false}')
            return
        if self.path == '/disconnect-drive':
            if not self._is_admin():
                self._json(403, b'{"ok":false,"err":"forbidden"}')
                return
            try:
                ok = delete_drive_token()
            except (RuntimeError, OSError):
                ok = False
            self._json(200 if ok else 400, b'{"ok":true}' if ok else b'{"ok":false}')
            return
        if self.path == '/sync-bug-log':
            # Trigger thủ công: chạy scan() bug log ngay (admin-only).
            if not self._is_admin():
                self._json(403, b'{"ok":false,"err":"forbidden"}')
                return
            try:
                res = bug_log_scan()
            except Exception:   # noqa: BLE001 — scan đã redact token; chặn mọi lỗi lạ
                res = {'ok': False, 'errors': ['Lỗi không xác định khi scan.']}
            self._json(200 if res.get('ok') else 400,
                       json.dumps(res, ensure_ascii=False).encode('utf-8'))
            return
        if self.path == '/save-bug-log-sources':
            # Lưu list file Drive nguồn (paste link -> rút id) rồi scan ngay.
            # Body: {sources:[{link|id, label}]}. Server rút file id, validate, save_sources,
            # rồi chạy scan() để đọc data luôn (user chốt "tự sync ngay sau khi lưu").
            # MỌI QA authed được sửa nguồn (do_POST đã gate authed) — user chốt mở toàn quyền.
            out = None
            err = ''
            try:
                length = int(self.headers.get('Content-Length', 0))
                if 0 < length <= 100_000:
                    payload = json.loads(self.rfile.read(length).decode('utf-8'))
                    raw = payload.get('sources') if isinstance(payload, dict) else None
                    if isinstance(raw, list) and len(raw) <= MAX_SOURCES:
                        clean = []
                        bad = False
                        for it in raw:
                            if not isinstance(it, dict):
                                bad = True
                                break
                            fid = extract_file_id(str(it.get('link') or it.get('id') or ''))
                            if not fid:
                                bad = True
                                break
                            label = it.get('label', '')
                            service = str(it.get('service') or '').strip()
                            clean.append({'id': fid, 'label': label if isinstance(label, str) else '', 'service': service})
                        if bad:
                            err = 'Có link Drive không hợp lệ — kiểm tra lại.'
                        elif save_sources(clean):
                            out = clean
                        else:
                            err = 'Không lưu được nguồn (Jira property lỗi).'
                    else:
                        err = 'Danh sách nguồn không hợp lệ.'
                else:
                    err = 'Payload rỗng hoặc quá lớn.'
            except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
                out = None
                err = 'Lỗi xử lý dữ liệu.'
            if out is None:
                self._json(400, json.dumps({'ok': False, 'err': err or 'Lỗi'}).encode('utf-8'))
                return
            # Lưu xong -> scan ngay để đọc data (không đợi scheduler 10p).
            try:
                res = bug_log_scan()
            except Exception:   # noqa: BLE001 — scan đã redact token
                res = {'ok': False, 'errors': ['Lỗi không xác định khi scan.']}
            res['saved'] = len(out)
            self._json(200, json.dumps(res, ensure_ascii=False).encode('utf-8'))
            return
        if self.path == '/link-task':
            # Liên kết / gỡ link list test-case (bug key) <-> 1 Jira task (#55).
            # Mở cho MỌI QA authed (khớp editable=True ở render). Lưu app-side, không ghi Jira.
            out = None
            try:
                length = int(self.headers.get('Content-Length', 0))
                if 0 < length <= 50_000:
                    payload = json.loads(self.rfile.read(length).decode('utf-8'))
                    if isinstance(payload, dict):
                        keys = payload.get('keys')
                        task = payload.get('task', '')
                        op = payload.get('op', 'add')
                        # task = str (1 task) hoặc list[str] (multi-select link bar #55)
                        task_ok = isinstance(task, str) or (
                            isinstance(task, list) and all(isinstance(x, str) for x in task))
                        if (isinstance(keys, list) and all(isinstance(x, str) for x in keys)
                                and task_ok and op in ('add', 'remove', 'clear')):
                            task = task[:50] if isinstance(task, list) else task
                            out = set_task_links(self._user_email(), keys[:500], task, op)
            except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
                out = None
            if out is not None:
                self._json(200, json.dumps({'ok': True, 'links': out}).encode('utf-8'))
            else:
                self._json(400, b'{"ok":false}')
            return
        if self.path == '/set-custom-status':
            # QA toggle nhãn nội bộ cho task (chọn nhiều). Author = người đăng nhập (không cần PAT).
            values = None
            try:
                length = int(self.headers.get('Content-Length', 0))
                if 0 < length <= 20_000:
                    payload = json.loads(self.rfile.read(length).decode('utf-8'))
                    if isinstance(payload, dict):
                        key = payload.get('key')
                        value = payload.get('status', '')
                        summary = payload.get('summary', '')
                        if (isinstance(key, str) and key and isinstance(value, str)
                                and is_valid(value) and isinstance(summary, str)):
                            values = set_custom_status(self._user_email(), key, value, summary[:200])
            except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
                values = None
            if values is not None:
                self._json(200, json.dumps({'ok': True, 'values': values}).encode('utf-8'))
            else:
                self._json(400, b'{"ok":false}')
            return
        if self.path in ('/jira-transitions', '/do-transition', '/add-comment'):
            self._handle_jira_write()
            return
        if self.path == '/create-subtask':
            self._handle_create_subtask()
            return
        if self.path == '/batch-eval':
            if not self._is_admin():
                self._json(403, b'{"ok":false,"err":"forbidden"}')
                return
            try:
                length = int(self.headers.get('Content-Length', 0))
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                keys = payload.get('keys', [])
                num_val = payload.get('num_val')
                text_val = payload.get('text_val')
                pat = load_user_pat(self._user_email())
                if not pat:
                    self._json(400, json.dumps({'ok': False, 'msg': 'Bạn chưa cấu hình PAT. Vào ⚙ Cài đặt để thêm.'}).encode('utf-8'))
                    return
                from jira_write import batch_update_evaluations
                ok, msg = batch_update_evaluations(keys, num_val, text_val, pat)
                self._json(200 if ok else 400, json.dumps({'ok': ok, 'msg': msg}).encode('utf-8'))
            except Exception as e:
                self._json(400, json.dumps({'ok': False, 'msg': str(e)}).encode('utf-8'))
            return
        if self.path == '/upload-file':
            if not self._is_admin():
                self._json(403, b'{"ok":false,"err":"forbidden"}')
                return
            try:
                import os
                import time
                import re
                from pathlib import Path
                
                content_length = int(self.headers.get('Content-Length', 0))
                if content_length > 25_000_000: # 25MB safety cap (limit is 20MB)
                    self._json(400, b'{"ok":false,"msg":"File qua lon (> 20MB)"}')
                    return
                
                body = self.rfile.read(content_length)
                
                # Parse multipart boundary
                ctype = self.headers.get('Content-Type', '')
                if 'boundary=' not in ctype:
                    self._json(400, b'{"ok":false,"msg":"Thieu multipart boundary"}')
                    return
                
                boundary = ctype.split('boundary=')[1].strip()
                boundary_bytes = ('--' + boundary).encode('utf-8')
                
                # Custom parse multipart
                parts = body.split(boundary_bytes)
                filename = None
                file_data = None
                for part in parts:
                    if not part or part == b'--\r\n' or part == b'--':
                        continue
                    idx = part.find(b'\r\n\r\n')
                    header_end = idx + 4
                    if idx == -1:
                        idx = part.find(b'\n\n')
                        header_end = idx + 2
                    if idx == -1:
                        continue
                        
                    header_part = part[:idx].decode('utf-8', errors='ignore')
                    m = re.search(r'filename="([^"]+)"', header_part)
                    if m:
                        filename = m.group(1)
                        file_data = part[header_end:]
                        if file_data.endswith(b'\r\n'):
                            file_data = file_data[:-2]
                        elif file_data.endswith(b'\n'):
                            file_data = file_data[:-1]
                        break
                
                if not filename or file_data is None:
                    self._json(400, b'{"ok":false,"msg":"Khong tim thay file trong request"}')
                    return
                
                # Clean filename (prevent directory traversal)
                filename = os.path.basename(filename)
                
                # Target path setup
                uploads_dir = Path("/Users/thanhht/qa-dashboard/uploads")
                uploads_dir.mkdir(parents=True, exist_ok=True)
                
                # Check collision, append timestamp if duplicate
                stem = Path(filename).stem
                suffix = Path(filename).suffix
                target_path = uploads_dir / filename
                if target_path.exists():
                    timestamp = int(time.time())
                    filename = f"{stem}_{timestamp}{suffix}"
                    target_path = uploads_dir / filename
                
                # Write file
                target_path.write_bytes(file_data)
                
                # Return success JSON
                self._json(200, json.dumps({
                    "ok": True,
                    "filename": filename,
                    "url": f"/uploads/{filename}"
                }, ensure_ascii=False).encode('utf-8'))
                
            except Exception as e:
                self._json(500, json.dumps({
                    "ok": False,
                    "msg": f"Loi he thong: {str(e)}"
                }).encode('utf-8'))
            return
        if self.path == '/save-docs':
            if not self._is_admin():
                self._json(403, b'{"ok":false,"err":"forbidden"}')
                return
            ok = False
            try:
                length = int(self.headers.get('Content-Length', 0))
                if 0 < length <= 1_000_000:
                    payload = json.loads(self.rfile.read(length).decode('utf-8'))
                    if valid_tree(payload):
                        ok = save_docs(payload)
            except (ValueError, json.JSONDecodeError, OSError):
                ok = False
            self._json(200 if ok else 400, b'{"ok":true}' if ok else b'{"ok":false}')
            return
        if self.path == '/save-roadmap':
            if not self._is_admin():
                self._json(403, b'{"ok":false,"err":"forbidden"}')
                return
            ok = False
            try:
                length = int(self.headers.get('Content-Length', 0))
                if 0 < length <= 1_000_000:
                    payload = json.loads(self.rfile.read(length).decode('utf-8'))
                    if valid_roadmap(payload):
                        ok = save_roadmap(payload)
            except (ValueError, json.JSONDecodeError, OSError):
                ok = False
            self._json(200 if ok else 400, b'{"ok":true}' if ok else b'{"ok":false}')
            return
        self.send_response(404)
        self.end_headers()

    def _json(self, status, body):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] {fmt % args}\n")


def main():
    print("QA Team Dashboard")
    print(f"  Jira:      {JIRA_URL}")
    print(f"  Tracking:  {', '.join(display_name(u) for u in USERS)}")
    print(f"  Dashboard: http://localhost:{PORT}/")
    print(f"  State:     {STATE_FILE.name}")
    print("  Ctrl+C để stop\n")

    start_bug_log_scheduler()   # daemon thread poll Drive 10p (no-op nếu chưa kết nối Drive)

    try:
        with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as server:
            server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    except OSError as e:
        msg = str(e).lower()
        # Linux/mac errno 48/98 ; Windows WSAEADDRINUSE 10048
        if 'address already in use' in msg or 'each socket address' in msg or e.errno in (48, 98, 10048):
            print(f"\nERROR: Port {PORT} đang bị process khác chiếm (có thể server cũ vẫn chạy).", file=sys.stderr)
            print("       → Đóng server cũ, hoặc đổi JIRA_PORT trong .env sang port khác.", file=sys.stderr)
            sys.exit(1)
        raise


if __name__ == '__main__':
    main()
