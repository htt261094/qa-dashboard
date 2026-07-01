#!/usr/bin/env python3
"""QA Workspace for Jira (Bảo Kim) — entry point.

Local web server on http://localhost:<PORT>. F5 = fresh pull from Jira.
Layered modules: config -> issues -> {jira_api, state} -> render -> (this file).
Run: python qa_dashboard.py
"""
import http.server
from http.server import ThreadingHTTPServer
import ipaddress
import json
import sys
import os
import threading
from datetime import datetime
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs

# Core modules live in ./core/ (issue #85). Add it to sys.path so sibling-style
# imports (`from config import ...`) keep working unchanged.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'core'))

from config import (JIRA_URL, USERS, PORT, ADMIN_EMAIL, ADMIN_EMAILS, ALLOWED_DOMAIN,
                    AUTH_ENABLED, SELF_USER, PUBLIC_BASE_URL, CHAT_ENABLED,
                    display_name, username_from_email)
from chat import chat_stream, prewarm as chat_prewarm
from auth import (SESSION_COOKIE, SESSION_TTL, email_from_session,
                  session_status, make_session_token)
from drive_token import has_drive_token, delete_drive_token
from bug_log_store import (scan as bug_log_scan, start_scheduler as start_bug_log_scheduler,
                           load_bug_log, unseen_changes as bug_log_unseen,
                           mark_changes_seen as bug_log_mark_seen)
from bug_log_source import load_sources, save_sources, extract_file_id, MAX_SOURCES
from task_link import load_links, set_task_links, tasks_of
from testcase_link import (load_links as tc_load_links, set_folder_links as tc_set_folder_links,
                           folders_for_task as tc_folders_for_task)
from jira_api import (fetch_all_shared, scope_data, fetch_activity_feed, load_dismissed,
                      dismiss_activities, run_parallel, fetch_issue_detail,
                      search_parent_ptsp, search_people, search_qa_tasks, global_search)
from docs import load_docs, save_docs, valid_tree
from roadmap import load_roadmap, save_roadmap, valid_roadmap
from testcase_store import (load_testcases, fetch_sheets as tc_fetch_sheets,
                            import_cases as tc_import_cases, add_folder as tc_add_folder,
                            delete_folder as tc_delete_folder, rename_folder as tc_rename_folder)
from pat_store import save_user_pat, has_pat, delete_user_pat, load_user_pat
from custom_status import (load_bundle, values_of)
from render import (render_page, render_qa_v2, render_docs_page,
                    render_roadmap_v2, render_public_roadmap_v2, render_bug_log_v2, render_analytics_v2,
                    render_testcase_v2, render_settings_page, render_error_page,
                    render_403, render_shell_error)
from routes.oauth import OAuthMixin
from routes.write import WriteMixin
from routes.uploads import UploadsMixin

ACTIVITY_DAYS = 7  # cửa sổ activity feed kéo từ Jira changelog


# ===== HTTP server =====
class Handler(OAuthMixin, WriteMixin, UploadsMixin, http.server.BaseHTTPRequestHandler):
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

    def _user_email(self):
        """Email người đăng nhập từ session cookie; fallback Cloudflare header. '' nếu chưa login."""
        email = email_from_session(self._cookie(SESSION_COOKIE))
        if email:
            return email
        return (self.headers.get('Cf-Access-Authenticated-User-Email') or '').strip().lower()

    def _is_loopback(self):
        """TCP peer của request có phải loopback (127.0.0.0/8 hoặc ::1) không.

        Dùng self.client_address[0] = địa chỉ THẬT của socket, KHÔNG phải header
        (X-Forwarded-For/Host bịa được; peer TCP thì không). Là ranh giới tin cậy
        khi AUTH tắt (issue #44): không login => chỉ máy local mới được coi là chính chủ."""
        try:
            ip = ipaddress.ip_address(self.client_address[0])
        except (ValueError, IndexError, TypeError):
            return False
        # IPv4-mapped IPv6 (::ffff:127.0.0.1) -> quy về IPv4 để bắt loopback đúng.
        mapped = getattr(ip, 'ipv4_mapped', None)
        if mapped is not None:
            ip = mapped
        return ip.is_loopback

    def _authed(self):
        """Request có được phép vào không.

        AUTH tắt (local dev) -> CHỈ cho loopback (fail-closed, issue #44): quên set
        GOOGLE_* hay bind nhầm 0.0.0.0 thì máy ngoài KHÔNG tự động thành admin.
        AUTH bật -> phải có email từ session/header."""
        if not AUTH_ENABLED:
            return self._is_loopback()
        return bool(self._user_email())

    def _maybe_refresh_session(self):
        """Sliding session (#161): cookie còn hạn nhưng qua nửa đời -> cấp lại (gia hạn) để
        người đang dùng KHÔNG bao giờ bị đá về login giữa chừng. Stash vào self._pending_cookies;
        _html/_json gắn Set-Cookie khi trả response. Chỉ áp khi identity ĐẾN TỪ session cookie
        (fallback CF header không có cookie để gia hạn)."""
        if not AUTH_ENABLED:
            return
        email, needs = session_status(self._cookie(SESSION_COOKIE))
        if email and needs:
            secure = self._secure_cookie()   # OAuthMixin
            self._pending_cookies = [self._set_cookie(
                SESSION_COOKIE, make_session_token(email), SESSION_TTL, secure)]

    def _domain_ok(self):
        """Domain gate ở tầng app (defense-in-depth; login Google đã verify sẵn)."""
        email = self._user_email()
        if not email or not ALLOWED_DOMAIN:   # local, hoặc chưa cấu hình domain -> cho qua
            return True
        return email.endswith('@' + ALLOWED_DOMAIN)

    def _is_admin(self):
        """Role admin = được edit roadmap/tài liệu. Local (chưa login) -> admin (chính bạn),
        nhưng CHỈ khi request đến từ loopback (fail-closed, issue #44)."""
        email = self._user_email()
        if not email or not ADMIN_EMAILS:
            # AUTH tắt -> admin chỉ khi loopback; AUTH bật mà chưa login -> KHÔNG phải admin.
            return (not AUTH_ENABLED) and self._is_loopback()
        return email in ADMIN_EMAILS

    def _user_ctx(self):
        """(email, is_admin) cho nav chip; None khi chưa login (local dev)."""
        email = self._user_email()
        return (email, self._is_admin()) if email else None

    def _self_username(self):
        """Jira username của chính người đăng nhập (cho tab My work). Local dev /
        admin-email-không-trong-USERS -> SELF_USER (default thanhht1)."""
        return username_from_email(self._user_email()) or username_from_email(ADMIN_EMAIL) or SELF_USER

    def _seen_key(self):
        """Khoá watermark "đã xem popup thay đổi bug-log". Email khi đã login, '_local' cho
        local dev (loopback) — đủ ổn định để giữ trạng thái đã-xem giữa các lần load."""
        return self._user_email() or '_local'

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

    def _testcases_for_task(self, task_key):
        """Chiều ngược của testcase_link: list BỘ test case ĐÃ LINK tới `task_key`,
        cho drawer detail. Mỗi bộ kèm tên + đếm case (gồm folder con) + breakdown
        pass/fail. Lỗi -> [] (drawer vẫn mở, chỉ thiếu mục test case)."""
        try:
            fids = tc_folders_for_task(task_key)
        except Exception:
            return []
        if not fids:
            return []
        try:
            data = load_testcases() or {}
        except Exception:
            return []
        folders = data.get('folders') or []
        cases = data.get('cases') or []
        by_id = {f.get('id'): f for f in folders}
        # con theo cha (để gộp case của folder con vào bộ gốc, như casesIn ở UI)
        children = {}
        for f in folders:
            p = f.get('parent_id')
            if p:
                children.setdefault(p, []).append(f.get('id'))
        out = []
        for fid in fids:
            folder = by_id.get(fid)
            if not folder:
                continue
            allowed = {fid} | set(children.get(fid, []))
            sub = [c for c in cases if c.get('folder') in allowed]
            n_pass = sum(1 for c in sub if c.get('result') == 'pass')
            n_fail = sum(1 for c in sub if c.get('result') == 'fail')
            out.append({
                'id': fid, 'name': folder.get('name', fid),
                'count': len(sub), 'pass': n_pass, 'fail': n_fail,
            })
        return out

    def _wants_fresh(self):
        """True khi browser F5/hard-reload (gửi Cache-Control: no-cache hoặc max-age=0).
        Click chuyển tab (thẻ <a>) KHÔNG gửi header này -> vẫn dùng SWR nhanh. Dùng để ép
        fetch tươi khi user chủ động refresh (Decision #26 bổ sung: 'F5 = luôn tươi')."""
        cc = (self.headers.get('Cache-Control') or '').lower()
        return 'no-cache' in cc or 'max-age=0' in cc

    def _bell_activities(self, with_patch=False, force=False):
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
                # block=False (#160): chuông best-effort — cache quá cũ thì feed rỗng + refresh
                # nền, KHÔNG treo tab (kể cả tab non-Jira) chờ call changelog nặng khi Jira chậm.
                'feed': lambda: fetch_activity_feed(days=ACTIVITY_DAYS, scope_user=scope,
                                                    with_status=with_patch, block=False,
                                                    force=force),
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

    def do_GET(self):
        # Dispatch mỏng: gate auth/domain rồi route tới method _get_* / _do_*.
        # Giữ NGUYÊN thứ tự kiểm tra path (zero behavior change — B0/#111).
        path = urlparse(self.path).path
        # Fail-closed (issue #44): AUTH tắt => toàn server chỉ phục vụ loopback. Request
        # từ máy khác (quên set GOOGLE_*, bind nhầm, đổi tunnel) -> 403 thay vì thành admin.
        if not AUTH_ENABLED and not self._is_loopback():
            self._forbidden()
            return
        if path == '/login':
            self._do_login()
            return
        if path == '/oauth/callback':
            self._do_callback()
            return
        if path == '/logout':
            self._do_logout()
            return
        if path == '/public/roadmap':
            self._get_public_roadmap()
            return
        if not self._authed():
            self._redirect('/login')
            return
        if not self._domain_ok():
            self._forbidden()
            return
        self._maybe_refresh_session()   # sliding session (#161): gia hạn cookie khi đang dùng
        # ----- Drive connect (admin-only) — sau gate authed/domain -----
        if path == '/drive/connect':
            self._do_drive_connect()
            return
        if path == '/oauth/drive-callback':
            self._do_drive_callback()
            return
        if path.startswith('/uploads/'):
            self._get_uploads(path)
            return
        if self.path in ('/my-work', '/my-work.html'):
            self._get_my_work()
            return
        if self.path.startswith('/leader-eval'):
            self._get_leader_eval()
            return
        if self.path in ('/docs', '/docs.html'):
            self._get_docs()
            return
        if self.path in ('/roadmap', '/roadmap.html'):
            self._get_roadmap()
            return
        if self.path in ('/bug-log', '/bug-log.html'):
            self._get_bug_log()
            return
        if self.path in ('/analytics', '/analytics.html'):
            self._get_analytics()
            return
        if self.path in ('/test-cases', '/test-cases.html'):
            self._get_test_cases()
            return
        if path == '/issue-comments':
            self._get_issue_comments()
            return
        if path == '/activity-feed':
            self._get_activity_feed()
            return
        if path == '/has-pat':
            self._get_has_pat()
            return
        if path == '/has-drive':
            self._get_has_drive()
            return
        if path == '/search-parents':
            self._get_search_parents()
            return
        if path == '/search-tasks':
            self._get_search_tasks()
            return
        if path == '/global-search':
            self._get_global_search()
            return
        if path == '/search-people':
            self._get_search_people()
            return
        if path == '/tc-sheets':
            self._get_tc_sheets()
            return
        if self.path in ('/settings', '/settings.html'):
            self._get_settings()
            return
        if self.path not in ('/', '/index.html'):
            self.send_response(404)
            self.end_headers()
            return
        self._get_dashboard()

    # ===== GET route handlers (trích từ do_GET — B0/#111) =====
    # _get_uploads -> routes/uploads.py (UploadsMixin, B3/#115)

    def _get_my_work(self):
        # Việc của tôi = lens cá nhân của admin (task của chính mình). QA thường KHÔNG
        # cần (dashboard `/` của họ đã auto-scope về chính họ) -> đá về dashboard.
        if not self._is_admin():
            self._redirect('/')
            return
        scope = self._self_username()
        fresh = self._wants_fresh()   # F5 -> ép data tươi; click chuyển tab -> SWR nhanh
        # data full team qua snapshot chéo máy rồi scope về chính admin (xem Decision offline-snapshot).
        try:
            full, stale = fetch_all_shared(fetched_by=self._user_email(), force=fresh)
        except RuntimeError:
            self._html(render_shell_error('mywork', self._user_ctx(),
                                          title='Việc của tôi — QA Workspace'))
            return
        data = scope_data(full, scope)
        # overlay nhãn custom qua KV -> sống offline; chuông notif qua Jira -> có thể fail.
        try:
            overlay, _cust_act = load_bundle(scope, ACTIVITY_DAYS)
        except RuntimeError:
            overlay = None
        try:
            bell = self._bell_activities(force=fresh)
        except RuntimeError:
            bell = []
        # UI hệt QA member (render_qa_v2), chỉ highlight tab "Việc của tôi" ở sidebar
        self._html(render_qa_v2(data, bell, overlay, self._user_ctx(),
                                nav_active='mywork', stale=stale))

    def _get_leader_eval(self):
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
        except RuntimeError:
            self._html(render_shell_error('leadereval', self._user_ctx(),
                                          title='Đánh giá — QA Workspace'))

    def _get_docs(self):
        # tài liệu training: load song song tài liệu và chuông notif (đồng nhất mọi tab)
        try:
            res = run_parallel({'docs': load_docs, 'bell': self._bell_activities})
            self._html(render_docs_page(res['docs'], editable=self._is_admin(),
                                        user=self._user_ctx(), activities=res['bell']))
        except RuntimeError as e:
            self._html(render_error_page(str(e)))

    def _get_test_cases(self):
        # Quản lý Test Case (#152/#157): nạp store (KV sync chéo máy, fallback cache) +
        # chuông notif (đồng nhất mọi tab). editable=True -> MỌI QA đăng nhập được
        # import/sửa (user chốt #152), không giới hạn admin.
        try:
            res = run_parallel({'tc': load_testcases, 'bell': self._bell_activities,
                                'links': tc_load_links})
            data, bell, links = res['tc'], res['bell'], res['links']
        except RuntimeError:
            data, bell, links = None, [], {}
        self._html(render_testcase_v2(data=data, editable=True, links=links,
                                      user=self._user_ctx(), activities=bell))

    def _get_roadmap(self):
        # roadmap team (UI v2): roadmap + chuông notif (đồng nhất mọi tab) song song
        try:
            res = run_parallel({'roadmap': load_roadmap, 'bell': self._bell_activities})
            self._html(render_roadmap_v2(res['roadmap'], editable=self._is_admin(),
                                         user=self._user_ctx(), activities=res['bell']))
        except RuntimeError as e:
            self._html(render_error_page(str(e)))

    def _get_public_roadmap(self):
        # Standalone public roadmap (view mode only, no auth required)
        try:
            roadmap = load_roadmap()
            self._html(render_public_roadmap_v2(roadmap))
        except Exception as e:
            self._html(render_error_page(str(e)))

    def _get_bug_log(self):
        # Bug Log (#55): bug từ Excel/Drive (cache bug_log_store) + link app-side (task_link)
        # + chuông notif. Không gọi Jira search (cache đọc local/property) -> nhẹ.
        try:
            res = run_parallel({'bug': load_bug_log, 'links': load_links,
                                'sources': load_sources, 'bell': self._bell_activities})
            # Bug Log mở cho MỌI QA (kể cả non-admin): liên kết Task + quản lý link
            # drive nguồn. editable=True cho mọi user đã authed (route đã gate authed).
            # Popup thay đổi tích luỹ chỉ cho admin (lens quản lý) — non-admin -> None.
            pending = None
            if self._is_admin():
                try:
                    pending = bug_log_unseen(self._seen_key(),
                                             activity=(res['bug'] or {}).get('activity'))
                except Exception:   # noqa: BLE001 — popup là phụ trợ, lỗi -> bỏ qua
                    pending = None
            self._html(render_bug_log_v2(res['bug'], res['links'],
                                         editable=True,
                                         user=self._user_ctx(), activities=res['bell'],
                                         sources=res['sources'], pending=pending))
        except RuntimeError as e:
            self._html(render_error_page(str(e)))

    def _get_analytics(self):
        # Analytics (#158): gom metric bug (Valid Bug Rate + chart dev/dự án + reopen).
        # Nguồn = cache bug_log_store, testcase_store, links (KHÔNG gọi Jira search) + chuông notif.
        try:
            from core.testcase_store import load_testcases
            from core.testcase_link import load_links as tc_load_links
            from core.task_link import load_links
            res = run_parallel({
                'bug': load_bug_log, 
                'bell': self._bell_activities,
                'tc': load_testcases,
                'links': load_links,
                'tc_links': tc_load_links
            })
            self._html(render_analytics_v2(
                res['bug'], 
                user=self._user_ctx(),
                activities=res['bell'],
                testcases=res['tc'],
                links=res['links'],
                tc_links=res['tc_links']
            ))
        except RuntimeError as e:
            self._html(render_error_page(str(e)))

    def _get_issue_comments(self):
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
                                'bugs': lambda: self._bugs_for_task(key),
                                'testcases': lambda: self._testcases_for_task(key)})
            detail = res['detail']
            detail['bugs'] = res['bugs']
            detail['testcases'] = res['testcases']
            self._json(200, json.dumps({'ok': True, 'detail': detail}).encode('utf-8'))
        except RuntimeError:
            self._json(400, b'{"ok":false,"msg":"loi"}')

    def _get_activity_feed(self):
        # JSON feed cho chuông notif — client poll định kỳ để cập nhật real-time,
        # KHÔNG reload trang (Decision #24). Cùng nguồn _bell_activities() nên đồng nhất
        # mọi tab + đã gắn is_unread theo dismissed của người đăng nhập.
        try:
            acts, tasks = self._bell_activities(with_patch=True)
            self._json(200, json.dumps(
                {'ok': True, 'activities': acts, 'tasks': tasks}).encode('utf-8'))
        except RuntimeError:
            self._json(400, b'{"ok":false}')

    def _get_has_pat(self):
        # FE check trước khi mở form tạo sub-task: chưa có PAT -> mở luôn modal Cài đặt PAT.
        # Lỗi Jira -> bỏ qua (ok=false) để FE vẫn mở form, backend /create-subtask tự chặn.
        try:
            self._json(200, json.dumps(
                {'ok': True, 'hasPat': has_pat(self._user_email())}).encode('utf-8'))
        except RuntimeError:
            self._json(200, b'{"ok":false}')

    def _get_has_drive(self):
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

    def _get_search_parents(self):
        # type-ahead Task-PTSP cho form tạo sub-task. Read-only PAT chung.
        q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
        try:
            self._json(200, json.dumps(
                {'ok': True, 'results': search_parent_ptsp(q)}).encode('utf-8'))
        except RuntimeError:
            self._json(400, b'{"ok":false}')

    def _get_search_tasks(self):
        # type-ahead task của QA team cho Bug Log linkbar (link bug -> task QA đang làm,
        # KHÔNG phải Task-PTSP của dev). Read-only PAT chung.
        q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
        try:
            self._json(200, json.dumps(
                {'ok': True, 'results': search_qa_tasks(q)}).encode('utf-8'))
        except RuntimeError:
            self._json(400, b'{"ok":false}')

    def _get_global_search(self):
        # Quick-search toàn Jira cho thanh search topbar (key / số / text summary).
        # Read-only PAT chung. Mở task ra drawer qua /issue-comments khi click.
        q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
        try:
            self._json(200, json.dumps(
                {'ok': True, 'results': global_search(q)}).encode('utf-8'))
        except RuntimeError:
            self._json(400, b'{"ok":false}')

    def _get_search_people(self):
        # type-ahead user (field Leader) cho form tạo sub-task. Read-only PAT chung.
        q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
        try:
            self._json(200, json.dumps(
                {'ok': True, 'results': search_people(q)}).encode('utf-8'))
        except RuntimeError:
            self._json(400, b'{"ok":false}')

    def _get_tc_sheets(self):
        # Import test case (#152): dán link Drive -> liệt kê sheet để chọn tab.
        # Tải file 1 lần (Sheet native -> export xlsx); token redact trong bug_log.
        url = (parse_qs(urlparse(self.path).query).get('url') or [''])[0]
        try:
            self._json(200, json.dumps({'ok': True, **tc_fetch_sheets(url)},
                                       ensure_ascii=False).encode('utf-8'))
        except RuntimeError as e:
            self._json(400, json.dumps({'ok': False, 'msg': str(e)},
                                       ensure_ascii=False).encode('utf-8'))

    def _get_settings(self):
        # Cài đặt PAT cá nhân (mã hoá khi lưu) — thao tác Jira ghi đúng tên người dùng
        try:
            hd = has_drive_token() if self._is_admin() else False
            self._html(render_settings_page(has_pat(self._user_email()), user=self._user_ctx(),
                                             has_drive=hd, auth_enabled=AUTH_ENABLED,
                                             activities=self._bell_activities()))
        except RuntimeError:
            self._html(render_shell_error('settings', self._user_ctx(),
                                          title='Cài đặt — QA Workspace'))

    def _get_dashboard(self):
        email = self._user_email()  # dismiss tách theo người đăng nhập
        # admin/local -> scope None (xem cả team); QA thường -> scope = username của họ
        if self._is_admin():
            scope = None
        else:
            scope = username_from_email(email)
            if scope is None:   # non-admin không khớp QA nào -> không cho xem data team
                self._html(render_shell_error(
                    'dashboard', self._user_ctx(),
                    msg="Tài khoản của bạn chưa được gắn với QA nào trong hệ thống. "
                        "Liên hệ admin (Thành) để cấp quyền."))
                return
        # Block KHÔNG cần Jira (bug-metric / roadmap-alert) — load riêng, đọc cache local khi
        # Jira hỏng (load_bug_log/load_roadmap tự fallback cache, KHÔNG raise). Tách khỏi try
        # Jira để khi Jira down vẫn render được các block này (chỉ vùng task báo lỗi).
        buglog = load_bug_log()
        roadmap = load_roadmap()
        # Task data qua tầng snapshot chéo máy: ai có VPN fetch full team -> ghi KV; người
        # sau (kể cả mất VPN) đọc snapshot KV. stale=True -> Jira không với tới, đang phục vụ
        # snapshot cũ -> render read-only. data LUÔN full team -> scope_data lọc theo người xem.
        fresh = self._wants_fresh()   # F5 -> ép data tươi; click chuyển tab -> SWR nhanh
        try:
            full, stale = fetch_all_shared(fetched_by=email, force=fresh)
        except RuntimeError:
            # Jira không với tới + KV cũng trống -> không có gì hiện vùng task (skeleton + lỗi).
            self._html(render_page(None, [], ACTIVITY_DAYS,
                                   roadmap_data=roadmap, user=self._user_ctx(),
                                   custom_overlay=None, bug_log_data=buglog, jira_error=True))
            return
        data = scope_data(full, scope)
        # nhãn custom qua KV -> sống cả khi offline; feed/dismissed qua Jira -> có thể fail.
        try:
            overlay, cust_act = load_bundle(scope, ACTIVITY_DAYS)
        except RuntimeError:
            overlay, cust_act = None, []
        try:
            # CHÚ Ý: phải GIỐNG _bell_activities() (nguồn chuông cho /my-work,/docs,/roadmap)
            # để notif đồng nhất mọi tab — `/` canonical nên tự tính tại đây (đỡ fetch 2 lần).
            res = run_parallel({
                # block=False (#160): bell best-effort, không treo `/` chờ changelog khi Jira chậm.
                'feed': lambda: fetch_activity_feed(days=ACTIVITY_DAYS, scope_user=scope,
                                                    block=False, force=fresh),
                'dismissed': lambda: load_dismissed(email),
            })
            feed, dismissed = res['feed'], res['dismissed']
        except RuntimeError:
            feed, dismissed = [], {}     # offline -> chuông rỗng, trang vẫn render
        merged = sorted(feed + cust_act, key=lambda a: a.get('when') or '', reverse=True)
        for a in merged:
            a['is_unread'] = a['id'] not in dismissed
        self._html(render_page(data, merged, ACTIVITY_DAYS,
                               roadmap_data=roadmap, user=self._user_ctx(),
                               custom_overlay=overlay, bug_log_data=buglog, stale=stale))

    def _emit_pending_cookies(self):
        """Gắn Set-Cookie đã stash (sliding session #161). An toàn gọi nhiều lần (chỉ có khi
        _maybe_refresh_session set)."""
        for ck in getattr(self, '_pending_cookies', ()):
            self.send_header('Set-Cookie', ck)

    def _security_headers(self):
        # Defense-in-depth (issue #48). frame-ancestors/X-Frame-Options chống clickjack
        # (app có nút ghi Jira: transition/comment/delete). Referrer-Policy tránh rò URL nội bộ.
        # CSP đầy đủ cho script/style để sau (JS/CSS inline -> cần nonce).
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "frame-ancestors 'none'")

    def _html(self, html_out):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self._security_headers()
        self._emit_pending_cookies()
        self.end_headers()
        self.wfile.write(html_out.encode('utf-8'))

    def _read_json_body(self, max_len):
        length = int(self.headers.get('Content-Length', 0))
        if not (0 < length <= max_len):
            return None
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def _reply_json(self, ok, payload):
        self._json(200 if ok else 400, json.dumps(payload).encode('utf-8'))

    def _post_chat(self):
        # Chatbot: nhận {messages:[{role,content}]} -> stream text trả lời từ LLM local.
        # Đã gate authed/domain ở do_POST. Stream từng đoạn (text/plain) để UX gõ-dần;
        # KHÔNG Content-Length -> connection-close báo hết (HTTP/1.0). Client disconnect
        # giữa chừng -> BrokenPipeError, nuốt êm (generator tự dừng).
        if not CHAT_ENABLED:
            self._json(503, b'{"ok":false,"err":"chat_disabled"}')
            return
        try:
            payload = self._read_json_body(200_000)
            messages = payload.get('messages') if isinstance(payload, dict) else None
            if not isinstance(messages, list):
                self._json(400, b'{"ok":false,"err":"bad_request"}')
                return
            # Nội dung tab user đang xem (client scrape DOM) — optional, dùng làm context.
            page_text = payload.get('page') if isinstance(payload, dict) else ''
            page_text = page_text if isinstance(page_text, str) else ''
        except (ValueError, json.JSONDecodeError, OSError):
            self._json(400, b'{"ok":false,"err":"bad_request"}')
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('X-Accel-Buffering', 'no')
        self._security_headers()
        self._emit_pending_cookies()
        self.end_headers()
        try:
            for chunk in chat_stream(messages, page_text):
                if not chunk:
                    continue
                self.wfile.write(chunk.encode('utf-8'))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass   # client đóng tab giữa chừng — bình thường
        except Exception:   # noqa: BLE001 — đã stream 200, không đổi status được; nuốt êm
            pass

    def do_POST(self):
        # Dispatch mỏng: gate auth/domain rồi route tới method _post_* / _handle_*.
        # Giữ NGUYÊN thứ tự kiểm tra path (zero behavior change — B0b/#112).
        # Fail-closed (issue #44): AUTH tắt + không loopback -> 403 (đã gộp trong _authed).
        if not self._authed() or not self._domain_ok():
            self._json(403, b'{"ok":false,"err":"forbidden"}')
            return
        if self.path == '/dismiss':
            self._post_dismiss()
            return
        if self.path == '/save-pat':
            self._post_save_pat()
            return
        if self.path == '/delete-pat':
            self._post_delete_pat()
            return
        if self.path == '/disconnect-drive':
            self._post_disconnect_drive()
            return
        if self.path == '/sync-bug-log':
            self._post_sync_bug_log()
            return
        if self.path == '/save-bug-log-sources':
            self._post_save_bug_log_sources()
            return
        if self.path == '/seen-bug-log-changes':
            self._post_seen_bug_log_changes()
            return
        if self.path == '/link-task':
            self._post_link_task()
            return
        if self.path == '/set-custom-status':
            self._post_set_custom_status()
            return
        if self.path == '/chat':
            self._post_chat()
            return
        if self.path in ('/jira-transitions', '/do-transition', '/add-comment'):
            self._handle_jira_write()
            return
        if self.path == '/create-subtask':
            self._handle_create_subtask()
            return
        if self.path == '/batch-eval':
            self._post_batch_eval()
            return
        if self.path == '/upload-file':
            self._post_upload_file()
            return
        if self.path == '/save-docs':
            self._post_save_docs()
            return
        if self.path == '/save-roadmap':
            self._post_save_roadmap()
            return
        if self.path == '/tc-add-folder':
            self._post_tc_add_folder()
            return
        if self.path == '/tc-rename-folder':
            self._post_tc_rename_folder()
            return
        if self.path == '/tc-delete-folder':
            self._post_tc_delete_folder()
            return
        if self.path == '/tc-import':
            self._post_tc_import()
            return
        if self.path == '/tc-link-task':
            self._post_tc_link_task()
            return
        if self.path == '/tc-sync':
            self._post_tc_sync()
            return
        self.send_response(404)
        self.end_headers()

    # ===== POST route handlers (trích từ do_POST — B0b/#112) =====
    def _post_dismiss(self):
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

    def _post_save_pat(self):
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

    def _post_delete_pat(self):
        try:
            ok = delete_user_pat(self._user_email())
        except (RuntimeError, OSError):
            ok = False
        self._json(200 if ok else 400, b'{"ok":true}' if ok else b'{"ok":false}')

    def _post_disconnect_drive(self):
        if not self._is_admin():
            self._json(403, b'{"ok":false,"err":"forbidden"}')
            return
        try:
            ok = delete_drive_token()
        except (RuntimeError, OSError):
            ok = False
        self._json(200 if ok else 400, b'{"ok":true}' if ok else b'{"ok":false}')

    def _post_sync_bug_log(self):
        # Trigger thủ công: chạy scan() bug log ngay (admin-only).
        if not self._is_admin():
            self._json(403, b'{"ok":false,"err":"forbidden"}')
            return
        try:
            res = bug_log_scan()
        except Exception:   # noqa: BLE001 — scan đã redact token; chặn mọi lỗi lạ
            res = {'ok': False, 'errors': ['Lỗi không xác định khi scan.']}
        # Admin đang xem popup inline (res['changes']) -> đánh dấu đã xem tới giờ này để
        # KHÔNG popup lại y hệt khi reload sau khi đóng.
        if res.get('ok'):
            try:
                bug_log_mark_seen(self._seen_key())
            except Exception:   # noqa: BLE001
                pass
        self._json(200 if res.get('ok') else 400,
                   json.dumps(res, ensure_ascii=False).encode('utf-8'))

    def _post_seen_bug_log_changes(self):
        # Admin đã xem popup thay đổi tích luỹ -> đẩy watermark lên `watermark` (mốc lớn nhất
        # vừa hiện). Admin-only (popup chỉ render cho admin). Soft-fail: lỗi -> popup lại lần sau.
        if not self._is_admin():
            self._json(403, b'{"ok":false}')
            return
        wm = ''
        try:
            length = int(self.headers.get('Content-Length', 0))
            if 0 < length <= 2000:
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                if isinstance(payload, dict):
                    wm = str(payload.get('watermark') or '')
        except (ValueError, json.JSONDecodeError, OSError):
            wm = ''
        try:
            bug_log_mark_seen(self._seen_key(), wm)
        except Exception:   # noqa: BLE001
            pass
        self._json(200, b'{"ok":true}')

    def _post_save_bug_log_sources(self):
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
        # Lưu nguồn mới thường tạo loạt "bug mới" — admin sẽ reload thẳng (không popup
        # inline), nên đánh dấu đã xem để không bị popup đè cả màn ngay sau khi thêm nguồn.
        if res.get('ok') and self._is_admin():
            try:
                bug_log_mark_seen(self._seen_key())
            except Exception:   # noqa: BLE001
                pass
        res['saved'] = len(out)
        self._json(200, json.dumps(res, ensure_ascii=False).encode('utf-8'))

    def _post_link_task(self):
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

    def _post_batch_eval(self):
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

    # _post_upload_file -> routes/uploads.py (UploadsMixin, B3/#115)

    def _post_save_docs(self):
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

    def _post_save_roadmap(self):
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

    # ===== Test Case (#152) — MỌI QA authed được sửa (do_POST đã gate authed/domain) =====
    def _post_tc_add_folder(self):
        out, err = None, ''
        try:
            payload = self._read_json_body(10_000)
            name = payload.get('name') if isinstance(payload, dict) else None
            if not isinstance(name, str):
                err = 'Thiếu tên thư mục.'
            else:
                ok, res = tc_add_folder(name)
                if ok:
                    out = res
                else:
                    err = res
        except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
            err = 'Lỗi xử lý yêu cầu.'
        if out is None:
            self._json(400, json.dumps({'ok': False, 'msg': err or 'Lỗi'},
                                       ensure_ascii=False).encode('utf-8'))
            return
        self._json(200, json.dumps({'ok': True, 'folders': out.get('folders', [])},
                                   ensure_ascii=False).encode('utf-8'))

    def _post_tc_delete_folder(self):
        out, err = None, ''
        try:
            payload = self._read_json_body(10_000)
            fid = payload.get('id') if isinstance(payload, dict) else None
            if not isinstance(fid, str):
                err = 'Thiếu id thư mục.'
            else:
                ok, res = tc_delete_folder(fid)
                if ok:
                    out = res
                else:
                    err = res
        except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
            err = 'Lỗi xử lý yêu cầu.'
        if out is None:
            self._json(400, json.dumps({'ok': False, 'msg': err or 'Lỗi'},
                                       ensure_ascii=False).encode('utf-8'))
            return
        self._json(200, json.dumps({'ok': True, 'folders': out.get('folders', [])},
                                   ensure_ascii=False).encode('utf-8'))

    def _post_tc_rename_folder(self):
        out, err = None, ''
        try:
            payload = self._read_json_body(10_000)
            fid = payload.get('id') if isinstance(payload, dict) else None
            name = payload.get('name') if isinstance(payload, dict) else None
            if not isinstance(fid, str) or not isinstance(name, str):
                err = 'Thiếu id hoặc tên thư mục.'
            else:
                ok, res = tc_rename_folder(fid, name)
                if ok:
                    out = res
                else:
                    err = res
        except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
            err = 'Lỗi xử lý yêu cầu.'
        if out is None:
            self._json(400, json.dumps({'ok': False, 'msg': err or 'Lỗi'},
                                       ensure_ascii=False).encode('utf-8'))
            return
        self._json(200, json.dumps({'ok': True, 'folders': out.get('folders', [])},
                                   ensure_ascii=False).encode('utf-8'))

    def _post_tc_import(self):
        # Import test case -> mỗi sheet GHI ĐÈ 1 sub-folder cùng tên (giữ result cũ theo id).
        # Body: {url, sheet, folder}. sheet rỗng = import cả file (bỏ qua sheet template).
        # Tải + parse trong store; token redact trong bug_log.
        res = {'ok': False, 'msg': 'Lỗi xử lý yêu cầu.'}
        try:
            payload = self._read_json_body(20_000)
            if isinstance(payload, dict):
                url = str(payload.get('url') or '')
                sheet = str(payload.get('sheet') or '')
                folder = str(payload.get('folder') or '')
                res = tc_import_cases(folder, url, sheet, by_email=self._user_email())
        except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
            res = {'ok': False, 'msg': 'Lỗi xử lý yêu cầu.'}
        except Exception:   # noqa: BLE001 — phòng lỗi lạ; store đã redact token
            res = {'ok': False, 'msg': 'Lỗi không xác định khi import.'}
        self._json(200 if res.get('ok') else 400,
                   json.dumps(res, ensure_ascii=False).encode('utf-8'))

    def _post_tc_link_task(self):
        # Liên kết / gỡ link 1 BỘ test case (folder) <-> Jira task (#155).
        # Mở cho MỌI QA authed (khớp editable=True). Lưu app-side, không ghi Jira.
        # Body: {folder, task (str|list[str]), op ('add'|'remove'|'clear')}.
        out = None
        try:
            payload = self._read_json_body(50_000)
            if isinstance(payload, dict):
                folder = payload.get('folder', '')
                task = payload.get('task', '')
                op = payload.get('op', 'add')
                task_ok = isinstance(task, str) or (
                    isinstance(task, list) and all(isinstance(x, str) for x in task))
                if isinstance(folder, str) and task_ok and op in ('add', 'remove', 'clear'):
                    task = task[:50] if isinstance(task, list) else task
                    out = tc_set_folder_links(self._user_email(), folder, task, op)
        except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
            out = None
        if out is not None:
            self._json(200, json.dumps({'ok': True, 'tasks': out}).encode('utf-8'))
        else:
            self._json(400, b'{"ok":false}')

    def _post_tc_sync(self):
        res = {'ok': False, 'msg': 'Lỗi xử lý yêu cầu.'}
        try:
            payload = self._read_json_body(20_000)
            if isinstance(payload, dict):
                folder = str(payload.get('folder') or '')
                from core.testcase_store import load_testcases
                data = load_testcases()
                imports_info = data.get('imports', {}).get(folder)
                if not imports_info:
                    res = {'ok': False, 'msg': 'Không tìm thấy thông tin link Google Sheet cũ để đồng bộ.'}
                else:
                    url = imports_info.get('url', '')
                    sheet = imports_info.get('sheet', '')
                    if sheet == '(toàn bộ file)':
                        sheet = ''
                    res = tc_import_cases(folder, url, sheet, by_email=self._user_email())
        except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
            res = {'ok': False, 'msg': 'Lỗi xử lý yêu cầu.'}
        except Exception:   # noqa: BLE001
            res = {'ok': False, 'msg': 'Lỗi không xác định khi đồng bộ.'}
        self._json(200 if res.get('ok') else 400,
                   json.dumps(res, ensure_ascii=False).encode('utf-8'))

    def _json(self, status, body):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._security_headers()
        self._emit_pending_cookies()   # poll /activity-feed (#161) cũng gia hạn -> tab mở luôn sống
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] {fmt % args}\n")


def main():
    print("QA Workspace")
    print(f"  Jira:      {JIRA_URL}")
    print(f"  Tracking:  {', '.join(display_name(u) for u in USERS)}")
    print(f"  Workspace: http://localhost:{PORT}/")
    if not AUTH_ENABLED:
        print("  ⚠  AUTH TẮT (chưa set GOOGLE_CLIENT_ID/SECRET) — chỉ phục vụ", file=sys.stderr)
        print("     loopback (127.0.0.1). Mọi request local = ADMIN. KHÔNG expose ra ngoài.", file=sys.stderr)
    print("  Ctrl+C để stop\n")

    start_bug_log_scheduler()   # daemon thread poll Drive 10p (no-op nếu chưa kết nối Drive)
    # Nạp sẵn model LLM vào GPU (daemon, không chặn khởi động) -> user đầu không chịu cold-load.
    threading.Thread(target=chat_prewarm, daemon=True).start()

    try:
        # ThreadingHTTPServer (issue #129): mỗi request 1 thread → 1 request chạm Jira
        # treo (read-timeout 30s qua VPN) KHÔNG còn đơ MỌI user/tab khác như TCPServer
        # tuần tự. An toàn vì mọi kho ghi đã có lock (_cache_lock, _scan_lock, _meta_lock,
        # KV) + atomic_write tmp-name duy nhất theo thread (#128 + #129). daemon_threads
        # = thread chết theo process khi Ctrl+C, không treo lúc thoát.
        #
        # allow_reuse_address (#168): trên WINDOWS, SO_REUSEADDR cho phép NHIỀU process bind
        # CÙNG (127.0.0.1:PORT) -> OS xé connection giữa chúng. Restart mà chưa kill server cũ
        # -> 2+ instance co-bind, mỗi cái 1 SESSION_SECRET in-memory -> login bị xé ngang 2
        # process -> chữ ký state lệch -> 403 (sig_ok=False). Tắt trên Windows để bind thứ 2
        # FAIL (rơi vào handler port-in-use bên dưới) thay vì co-bind im lặng. Trên POSIX
        # SO_REUSEADDR nghĩa NGƯỢC (rebind nhanh qua TIME_WAIT khi restart) -> GIỮ True.
        class _Server(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = (os.name != 'nt')
        with _Server(("127.0.0.1", PORT), Handler) as server:
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
