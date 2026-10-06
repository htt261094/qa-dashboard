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
from datetime import datetime
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs

# Chạy bằng pythonw (autostart lúc logon — Decision #99) thì KHÔNG có console: sys.stdout/stderr
# = None -> log_message/print(file=sys.stderr) raise AttributeError mỗi request. Đổ cả 2 ra
# reports/dashboard.log (append, line-buffered) để còn đọc được log khi chạy ẩn.
if sys.stdout is None or sys.stderr is None:
    _logdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reports')
    os.makedirs(_logdir, exist_ok=True)
    _logf = open(os.path.join(_logdir, 'dashboard.log'), 'a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stdout or _logf
    sys.stderr = sys.stderr or _logf

# Core modules live in ./core/ (issue #85). Add it to sys.path so sibling-style
# imports (`from config import ...`) keep working unchanged.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'core'))

from config import (JIRA_URL, USERS, PORT, ADMIN_EMAIL, ADMIN_EMAILS, ALLOWED_DOMAIN,
                    AUTH_ENABLED, SELF_USER, PUBLIC_BASE_URL, LOCAL_ONLY,
                    LOCAL_AUTOLOGIN, OWNER_EMAIL, display_name, username_from_email, canon_key)
from auth import (SESSION_COOKIE, SESSION_TTL, email_from_session,
                  session_status, make_session_token)
from bug_log_store import (scan as bug_log_scan, start_scheduler as start_bug_log_scheduler,
                           load_bug_log, unseen_changes as bug_log_unseen,
                           mark_changes_seen as bug_log_mark_seen, search_bugs)
from bug_log_source import load_sources
from bug_backlog import load_backlog
from jira_api import (fetch_all_shared, scope_data, fetch_activity_feed, load_dismissed,
                      dismiss_activities, run_parallel, fetch_issue_detail,
                      search_parent_tasks, search_people, global_search,
                      fetch_subtasks)
from docs import load_docs, save_docs, valid_tree, ensure_process_folder
from pat_store import save_user_pat, has_pat, delete_user_pat
from custom_status import (load_bundle, load_overlay, values_of,
                           clear_labels_for_done)
from task_notes import load_notes, note_for
from render import (render_qa_v2, render_today_v2, render_docs_page, render_bug_log_v2, render_analytics_v2,
                    render_settings_page, render_error_page, render_403, render_shell_error)
from routes.oauth import OAuthMixin
from routes.write import WriteMixin
from routes.uploads import UploadsMixin

ACTIVITY_DAYS = 7  # cửa sổ activity feed kéo từ Jira changelog

def _drop_own_activities(merged, email):
    """Bỏ khỏi chuông các noti do CHÍNH người đang login gây ra (tự tạo task/đổi status/
    comment rồi thấy lại noti của mình). Áp cho cả admin lẫn member.
    Feed Jira chỉ có 'author' (tên rút gọn = display_name); custom-status có thêm 'by' (username).
    Không xác định được người login (local dev/email lạ) -> giữ nguyên."""
    me_user = username_from_email(email)
    if not me_user:
        return merged
    me_name = display_name(me_user)
    return [a for a in merged
            if a.get('by') != me_user and a.get('author') != me_name]


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
        """Email người đăng nhập, từ session cookie. '' nếu chưa login. (Bearer token cho
        app Android đã gỡ cùng app — Decision #97.)

        ⚠ KHÔNG tin header `Cf-Access-Authenticated-User-Email` (issue #44 khuyến nghị #3,
        Decision #92): header đó chỉ đáng tin khi CÓ Cloudflare Access ngồi trước tự set +
        strip header giả. Nhưng CF Access đã bị bỏ (Decision #15) — tunnel hiện tại là plain
        cloudflared KHÔNG strip → client bịa header trần đi thẳng tới origin. Với AUTH bật,
        `_authed()`/`_is_admin()` chỉ cần email hợp lệ (không đòi loopback) → set header =
        thành admin, bypass toàn bộ Google OAuth. Identity CHỈ đến từ token HMAC do app ký."""
        email = email_from_session(self._cookie(SESSION_COOKIE))
        if email:
            return email
        # Auto-login chính chủ (Decision #98): đã qua gate LOCAL_ONLY = người ngồi trước máy.
        # An toàn chỉ vì MỌI POST còn qua _same_origin_ok (bỏ cookie = mất lớp SameSite chống CSRF).
        if self._autologin_ok():
            return OWNER_EMAIL
        return ''

    def _autologin_ok(self):
        return bool(LOCAL_AUTOLOGIN and OWNER_EMAIL and self._local_only_ok())

    def _same_origin_ok(self):
        """Chống CSRF cho POST (Decision #98). Browser luôn gắn `Sec-Fetch-Site`/`Origin` cho POST
        cross-site — trang web lạ đang mở (hoặc HTML upload chạy trong iframe sandbox /file-raw,
        origin 'null') POST tới localhost sẽ mang Host=localhost nên gate LOCAL_ONLY KHÔNG chặn
        được. Trước đây cookie SameSite=Lax che; auto-login không cần cookie nên phải chặn ở đây.
        Thiếu cả 2 header (curl/script local) -> cho qua: tiến trình trên chính máy nằm ngoài
        mô hình đe doạ (nó đọc được .env rồi)."""
        sfs = (self.headers.get('Sec-Fetch-Site') or '').strip().lower()
        if sfs and sfs not in ('same-origin', 'none'):
            return False
        origin = self.headers.get('Origin')
        if origin is not None:
            host = (self.headers.get('Host') or '').strip().lower()
            if urlparse(origin.strip()).netloc.lower() != host or not host:
                return False
        return True

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

    # Header mà Cloudflare edge / cloudflared LUÔN gắn cho request đi qua tunnel. Browser gõ
    # thẳng localhost không bao giờ gửi -> có mặt = request đến từ internet (Decision #96).
    _TUNNEL_HEADERS = ('Cf-Connecting-IP', 'Cf-Ray', 'Cf-Visitor', 'Cdn-Loop', 'X-Forwarded-For')
    _LOCAL_HOSTS = ('localhost', '127.0.0.1', '[::1]')

    def _local_only_ok(self):
        """LOCAL_ONLY (Decision #96): chỉ cho request từ CHÍNH máy host.

        3 điều kiện, thiếu 1 là chặn:
        (1) peer TCP là loopback — chặn máy khác trong LAN (bind 127.0.0.1 đã là lớp 1);
        (2) không mang header tunnel — tunnel cloudflared cũng tới từ 127.0.0.1 nên (1) KHÔNG
            phân biệt được, phải nhận diện qua header Cloudflare gắn;
        (3) Host là localhost/127.0.0.1/[::1] — chặn DNS rebinding (trang web lạ trỏ domain
            của nó về 127.0.0.1 để browser của chính bạn gọi vào app)."""
        if not LOCAL_ONLY:
            return True
        if not self._is_loopback():
            return False
        if any(self.headers.get(h) for h in self._TUNNEL_HEADERS):
            return False
        host = (self.headers.get('Host') or '').strip().lower()
        name = host if host.endswith(']') else host.rsplit(':', 1)[0]
        return name in self._LOCAL_HOSTS

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
        """Role admin = chính chủ dashboard. Local (chưa login) -> admin (chính bạn),
        nhưng CHỈ khi request đến từ loopback (fail-closed, issue #44)."""
        email = self._user_email()
        if not email or not ADMIN_EMAILS:
            # AUTH tắt -> admin chỉ khi loopback; AUTH bật mà chưa login -> KHÔNG phải admin.
            return (not AUTH_ENABLED) and self._is_loopback()
        return email in ADMIN_EMAILS

    def _activity_scope(self):
        """Username để scope feed/overlay cho người đang xem. None = admin (= roster, mà roster
        giờ chỉ còn chính chủ — Decision #97); người khác -> username_from_email."""
        if self._is_admin():
            return None
        return username_from_email(self._user_email())

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
        """Chiều ngược (#104): list bug Jira "Bug Testing" có link native (parent / Relates to)
        tới `task_key`, cho drawer detail. Mỗi bug mang sẵn `tasks` = issue liên quan (đọc từ
        Jira lúc scan) -> so khớp theo CANON key (bền qua đổi project key mỗi kỳ, config.canon_key).
        Lỗi -> [] (drawer vẫn mở, chỉ thiếu mục bug)."""
        ck = canon_key(task_key)
        try:
            files = (load_bug_log() or {}).get('files', {}) or {}
        except Exception:   # noqa: BLE001
            return []
        out = []
        for f in files.values():
            for b in (f.get('bugs', {}) or {}).values():
                if ck in {canon_key(t) for t in (b.get('tasks') or [])}:
                    out.append({
                        'id': f"{b.get('project', '')}-{b.get('service') + '-' if b.get('service') else ''}{b.get('bug_no', '')}".strip('-'),
                        'summary': b.get('summary', ''),
                        'severity': b.get('severity', ''),
                        'status': b.get('status', ''),
                        'module': b.get('feature', ''),
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
        scope = self._activity_scope()
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
            # Task vừa chuyển DONE trên Jira -> tự gỡ hết nhãn custom (hết ý nghĩa khi đã xong).
            # Bắt được cả đổi qua drawer lẫn đổi thẳng trên Jira (đều lên feed). overlay.pop ->
            # patch gửi customs:[] cho client xoá chip real-time.
            for k in clear_labels_for_done(statuses):
                overlay.pop(k, None)
        merged = sorted(feed + cust_act, key=lambda a: a.get('when') or '', reverse=True)
        merged = _drop_own_activities(merged, email)
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
        if not self._local_only_ok():   # Decision #96: chặn mọi thứ ngoài chính máy này
            self._forbidden()
            return
        # Fail-closed (issue #44): AUTH tắt => toàn server chỉ phục vụ loopback. Request
        # từ máy khác (quên set GOOGLE_*, bind nhầm, đổi tunnel) -> 403 thay vì thành admin.
        if not AUTH_ENABLED and not self._is_loopback():
            self._forbidden()
            return
        if path == '/login':
            if self._autologin_ok():          # Decision #98: chính chủ khỏi login
                self._redirect('/')
                return
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
        self._maybe_refresh_session()   # sliding session (#161): gia hạn cookie khi đang dùng
        # Drive OAuth đã gỡ (#104): Bug Log nguồn Jira, không còn kết nối Google Drive.
        if path.startswith('/uploads/'):
            self._get_uploads(path)
            return
        if path == '/file-preview':
            self._get_file_preview()   # nội dung dựng sẵn để xem trước trong app (#63)
            return
        if path == '/file-view':
            self._get_file_view()      # trang xem toàn màn hình cho "Mở tab mới" (#63)
            return
        if path == '/file-raw':
            self._get_file_raw()       # HTML thô, sandbox, để nhúng iframe (#65)
            return
        if path in ('/today', '/today.html'):
            self._get_today()          # trang chính (Decision #102)
            return
        if path in ('/my-work', '/my-work.html'):
            self._get_my_work()
            return
        if path in ('/docs', '/docs.html'):
            self._get_docs()
            return
        if path in ('/bug-log', '/bug-log.html'):
            self._get_bug_log()
            return
        if path in ('/analytics', '/analytics.html'):
            self._get_analytics()
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
        if path == '/search-parents':
            self._get_search_parents()
            return
        if path == '/parent-subtasks':
            self._get_parent_subtasks()
            return
        if path == '/global-search':
            self._get_global_search()
            return
        if path == '/search-bugs':
            self._get_search_bugs()
            return
        if path == '/search-people':
            self._get_search_people()
            return
        if path in ('/settings', '/settings.html'):
            self._get_settings()
            return
        if path in ('/', '/index.html'):
            self._redirect('/today')     # trang chính = Hôm nay (Decision #102)
            return
        self.send_response(404)
        self.end_headers()

    # ===== GET route handlers (trích từ do_GET — B0/#111) =====
    # _get_uploads -> routes/uploads.py (UploadsMixin, B3/#115)

    def _get_my_work(self):
        # Việc của tôi = trang chính (Decision #97). Chỉ chính chủ (admin) — `/` giờ redirect
        # về đây nên KHÔNG redirect ngược về `/` (sẽ thành vòng lặp).
        if not self._is_admin():
            self._forbidden()
            return
        try:
            data, overlay, bell, stale, notes = self._my_work_bundle(self._wants_fresh())
        except RuntimeError:
            self._html(render_shell_error('mywork', self._user_ctx(),
                                          title='Việc của tôi — QA Workspace'))
            return
        # UI hệt QA member (render_qa_v2), chỉ highlight tab "Việc của tôi" ở sidebar
        self._html(render_qa_v2(data, bell, overlay, self._user_ctx(),
                                nav_active='mywork', stale=stale, notes=notes))

    def _get_today(self):
        # Hôm nay (Decision #102) = cùng bundle với Việc của tôi, chỉ khác cách gom nhóm.
        # Admin-only như /my-work; KHÔNG redirect về `/` khi 403 (`/` lại redirect về đây).
        if not self._is_admin():
            self._forbidden()
            return
        try:
            data, overlay, bell, stale, notes = self._my_work_bundle(self._wants_fresh())
        except RuntimeError:
            self._html(render_today_v2(None, self._bell_activities(), None, self._user_ctx(),
                                       jira_error=True))
            return
        # Bug cache local (#109) — đọc đĩa, 0 call Jira; lỗi -> bỏ qua, /today vẫn hiện.
        try:
            bug_data = load_bug_log()
        except Exception:   # noqa: BLE001 — strip bug là phụ trợ
            bug_data = None
        self._html(render_today_v2(data, bell, overlay, self._user_ctx(),
                                   notes=notes, stale=stale, bug_data=bug_data))

    def _my_work_bundle(self, fresh):
        """Fetch + scope snapshot cho lens "Việc của tôi". Trả `(data, overlay, bell, stale, notes)`.
        Raise RuntimeError khi Jira down (caller tự render lỗi). overlay/bell degrade mềm
        (KV/chuông fail -> None/[]) như hành vi cũ."""
        scope = self._self_username()
        full, stale = fetch_all_shared(force=fresh)
        data = scope_data(full, scope)
        # overlay nhãn custom qua KV; chuông notif qua Jira -> có thể fail (degrade mềm).
        try:
            overlay, _cust_act = load_bundle(scope, ACTIVITY_DAYS)
        except RuntimeError:
            overlay = None
        try:
            bell = self._bell_activities(force=fresh)
        except RuntimeError:
            bell = []
        try:
            notes = load_notes()
        except Exception:   # noqa: BLE001 — ghi chú là phụ trợ, lỗi kho -> bảng vẫn hiện
            notes = {}
        return data, overlay, bell, stale, notes

    def _get_docs(self):
        # tài liệu training: load song song tài liệu và chuông notif (đồng nhất mọi tab)
        try:
            res = run_parallel({'docs': load_docs, 'bell': self._bell_activities})
            # Folder "Quy Trình" (tab HTML) luôn có sẵn; chỉ admin mới persist được
            tree, changed = ensure_process_folder(res['docs'])
            if changed and self._authed():
                save_docs(tree)
            # editable=True -> người đăng nhập được upload/tạo thư mục/sửa.
            self._html(render_docs_page(tree, editable=True,
                                        user=self._user_ctx(), activities=res['bell']))
        except RuntimeError as e:
            self._html(render_error_page(str(e)))

    def _get_bug_log(self):
        # Bug Log (#55): bug từ Excel/Drive (cache bug_log_store) + link app-side (task_link)
        # + chuông notif. Không gọi Jira search (cache đọc local/property) -> nhẹ.
        try:
            res = run_parallel({'bug': load_bug_log,
                                'sources': load_sources, 'bell': self._bell_activities})
            # Popup thay đổi tích luỹ chỉ cho admin (lens quản lý) — non-admin -> None.
            pending = None
            if self._is_admin():
                try:
                    pending = bug_log_unseen(self._seen_key(),
                                             activity=(res['bug'] or {}).get('activity'))
                except Exception:   # noqa: BLE001 — popup là phụ trợ, lỗi -> bỏ qua
                    pending = None
            self._html(render_bug_log_v2(res['bug'],
                                         user=self._user_ctx(), activities=res['bell'],
                                         sources=res['sources'], pending=pending))
        except RuntimeError as e:
            self._html(render_error_page(str(e)))

    def _get_analytics(self):
        # Analytics (#158): gom metric bug (Valid Bug Rate + chart dev/dự án + reopen).
        # Nguồn = cache bug_log_store + backlog (KHÔNG gọi Jira search) + chuông notif.
        try:
            res = run_parallel({
                'bug': load_bug_log,
                'bell': self._bell_activities,
                'backlog': load_backlog,
            })
            self._html(render_analytics_v2(
                res['bug'],
                user=self._user_ctx(),
                activities=res['bell'],
                backlog=res['backlog']
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
                                'overlay': lambda: load_overlay(),
                                'notes': lambda: load_notes() if self._is_admin() else {}})
            detail = res['detail']
            detail['bugs'] = res['bugs']
            # Nhãn nội bộ (custom status overlay) — để drawer mở từ noti (task ngoài
            # bucket TASKS) vẫn hiện nhãn thay vì '—' (đồng nhất với click từ bảng).
            detail['customs'] = values_of((res['overlay'] or {}).get(key))
            # Ghi chú riêng (Decision #101) — chỉ chính chủ; drawer mọi trang đọc từ đây.
            detail['note'] = note_for(key, res['notes']) if res['notes'] else None
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

    def _get_search_parents(self):
        # type-ahead task cha (bất kỳ task, không giới hạn Task-PTSP) cho form tạo sub-task.
        # Read-only PAT chung.
        q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
        try:
            self._json(200, json.dumps(
                {'ok': True, 'results': search_parent_tasks(q)}).encode('utf-8'))
        except RuntimeError:
            self._json(400, b'{"ok":false}')

    def _get_parent_subtasks(self):
        # Sub-task hiện có của 1 task cha (popup 'sub-task đang có' ở form tạo sub-task).
        # Read-only PAT chung.
        key = (parse_qs(urlparse(self.path).query).get('key') or [''])[0]
        try:
            self._json(200, json.dumps(
                {'ok': True, 'results': fetch_subtasks(key)}).encode('utf-8'))
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

    def _get_search_bugs(self):
        # Command palette: tìm bug trong bug log (cache local, 0 call Jira/Drive, 0 PAT).
        q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
        try:
            self._json(200, json.dumps(
                {'ok': True, 'results': search_bugs(q)},
                ensure_ascii=False).encode('utf-8'))
        except Exception:   # noqa: BLE001 — cache hỏng thì trả rỗng, không 500
            self._json(200, b'{"ok":true,"results":[]}')

    def _get_search_people(self):
        # type-ahead user (field Leader) cho form tạo sub-task. Read-only PAT chung.
        q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
        try:
            self._json(200, json.dumps(
                {'ok': True, 'results': search_people(q)}).encode('utf-8'))
        except RuntimeError:
            self._json(400, b'{"ok":false}')

    def _get_settings(self):
        # Cài đặt PAT cá nhân (mã hoá khi lưu) — thao tác Jira ghi đúng tên người dùng
        try:
            self._html(render_settings_page(has_pat(self._user_email()), user=self._user_ctx(),
                                             activities=self._bell_activities()))
        except RuntimeError:
            self._html(render_shell_error('settings', self._user_ctx(),
                                          title='Cài đặt — QA Workspace'))

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

    def do_POST(self):
        # Dispatch mỏng: gate auth/domain rồi route tới method _post_* / _handle_*.
        # Giữ NGUYÊN thứ tự kiểm tra path (zero behavior change — B0b/#112).
        # Fail-closed (issue #44): AUTH tắt + không loopback -> 403 (đã gộp trong _authed).
        if (not self._local_only_ok() or not self._same_origin_ok()
                or not self._authed() or not self._domain_ok()):
            self._json(403, b'{"ok":false,"err":"forbidden"}')
            return
        path = urlparse(self.path).path
        if path == '/dismiss':
            self._post_dismiss()
            return
        if path == '/save-pat':
            self._post_save_pat()
            return
        if path == '/delete-pat':
            self._post_delete_pat()
            return
        if path == '/sync-bug-log':
            self._post_sync_bug_log()
            return
        if path == '/export-bug-log':
            self._post_export_bug_log()
            return
        if path == '/seen-bug-log-changes':
            self._post_seen_bug_log_changes()
            return
        if path == '/set-custom-status':
            self._post_set_custom_status()
            return
        if path == '/set-note':
            self._post_set_note()      # routes/write.py (Decision #101)
            return
        if path in ('/jira-transitions', '/do-transition', '/add-comment',
                         '/duedate-perm', '/set-duedate', '/edit-perms', '/update-issue'):
            self._handle_jira_write()
            return
        if path == '/create-subtask':
            self._handle_create_subtask()
            return
        if path == '/create-subtasks':
            self._handle_create_subtasks()
            return
        if path == '/upload-file':
            self._post_upload_file()
            return
        if path == '/save-docs':
            self._post_save_docs()
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

    def _post_export_bug_log(self):
        """Nhận rows đã lọc từ client (đúng bảng đang xem) -> trả file .xlsx tải về.
        Header cột cố định server-side (8 cột, KHÔNG có liên kết task). Cho MỌI người
        authed (mục đích: dev-lead export). Rows chỉ là chuỗi hiển thị -> KHÔNG chạm
        Jira/Drive/PAT nên an toàn mở cho cả role dev."""
        import re
        from urllib.parse import quote
        from xlsx_export import build_xlsx
        HEADERS = ['ID', 'Mô tả bug', 'Ngày', 'Severity', 'Trạng thái',
                   'Tester', 'Dev in charge']
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not (0 < length <= 5_000_000):
                self._json(400, b'{"ok":false,"msg":"payload"}')
                return
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            raw = payload.get('rows') if isinstance(payload, dict) else None
            if not isinstance(raw, list):
                self._json(400, b'{"ok":false,"msg":"rows"}')
                return
            rows = []
            for r in raw[:20000]:
                if isinstance(r, list):
                    rows.append([('' if c is None else str(c)) for c in r[:len(HEADERS)]])
            fname = re.sub(r'[^\w.\-]+', '_',
                           str((payload.get('filename') if isinstance(payload, dict) else '') or 'bug-log'))[:80]
            fname = fname or 'bug-log'
            if not fname.lower().endswith('.xlsx'):
                fname += '.xlsx'
            data = build_xlsx(HEADERS, rows, sheet_name='Bug Log')
        except (ValueError, json.JSONDecodeError, OSError, UnicodeDecodeError):
            self._json(400, b'{"ok":false,"msg":"loi export"}')
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{quote(fname)}")
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _post_sync_bug_log(self):
        # Trigger thủ công: chạy scan() bug log ngay (admin-only).
        # force=True -> bỏ qua Tầng-1 metadata, ĐỌC LẠI từ Drive cho mọi file dù vừa scan 1 phút
        # trước (user bấm "Đồng bộ ngay" nghĩa là muốn số mới nhất từ source, không phải cache).
        if not self._is_admin():
            self._json(403, b'{"ok":false,"err":"forbidden"}')
            return
        try:
            res = bug_log_scan(force=True)
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

    # _post_upload_file -> routes/uploads.py (UploadsMixin, B3/#115)

    def _post_save_docs(self):
        # Mở cho người đăng nhập (khớp editable=True ở render).
        if not self._authed():
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

    # ===== Test Case (#152) — MỌI QA authed được sửa (do_POST đã gate authed/domain) =====
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
    if LOCAL_ONLY:
        print("  🔒 LOCAL_ONLY: chỉ phục vụ chính máy này (localhost) — request qua tunnel bị 403.")
    if LOCAL_AUTOLOGIN:
        if OWNER_EMAIL:
            print("  🔓 LOCAL_AUTOLOGIN: tự đăng nhập chính chủ — khỏi login Google.")
        else:
            print("  ⚠  LOCAL_AUTOLOGIN bật nhưng không xác định được email chính chủ "
                  "(JIRA_ADMIN_EMAIL có nhiều email, không có <JIRA_SELF_USER>@<domain>) — vẫn login Google.",
                  file=sys.stderr)
    print("  Ctrl+C để stop\n")

    start_bug_log_scheduler()   # daemon thread poll Drive 10p (no-op nếu chưa kết nối Drive)

    # Jira Cloud (#197): resolve trước accountId cho roster (cache .jira_accounts.json) ở nền
    # -> request đầu tiên không phải chờ N call /user/search. No-op khi đã có cache.
    import threading
    from jira_cloud import warm_accounts
    threading.Thread(target=lambda: warm_accounts(list(USERS)),
                     daemon=True).start()

    try:
        # ThreadingHTTPServer (issue #129): mỗi request 1 thread → 1 request chạm Jira
        # treo (read-timeout 30s) KHÔNG còn đơ MỌI user/tab khác như TCPServer
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
