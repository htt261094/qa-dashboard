#!/usr/bin/env python3
"""Bug Log standalone (OFFLINE) — chạy riêng phần Bug Log, KHÔNG dính Jira, KHÔNG login.

Bối cảnh: công ty bắt whitelist IP để VPN vào Jira, mạng nhà không có IP tĩnh -> không
vào được Jira. Nhưng Bug Log lấy data từ Google Drive (không cần VPN) + máy này đã có sẵn
cache local (.bug_log.json / .bug_log_source.json / .drive_token.json). Entry này phục vụ
đúng trang /bug-log + sync Drive, để cuối tháng vẫn render được report cho sender gửi CTO.

Đặt OFFLINE=1 TRƯỚC khi import config -> config không bắt JIRA creds + jira_api ngắt mọi
call user-property (fallback cache local tức thì, không treo chờ Jira). Xem Decision tách
Bug Log offline trong CLAUDE.md.

Run: python bug_log_offline.py   ->   http://localhost:<PORT>/bug-log
"""
import os
import sys

# Bật OFFLINE TRƯỚC mọi import core (config đọc env lúc import).
os.environ['OFFLINE'] = '1'

# Core modules ở ./core/ (như qa_dashboard.py) — thêm vào sys.path để `from config import` chạy.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'core'))

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from config import PORT
from bug_log_store import (scan as bug_log_scan, start_scheduler as start_bug_log_scheduler,
                           load_bug_log)
from bug_log_source import load_sources
from task_link import load_links
from render import render_bug_log_v2, render_error_page
from jira_api import run_parallel

# User cố định cho lens admin (không login ở chế độ offline) — (email_hiển_thị, is_admin).
_OFFLINE_USER = ('offline', True)


class Handler(BaseHTTPRequestHandler):
    # ---- helpers ----
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        self._send(200, html.encode('utf-8'), 'text/html; charset=utf-8')

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode('utf-8'),
                   'application/json; charset=utf-8')

    def log_message(self, fmt, *args):  # gọn log — chỉ in path
        sys.stderr.write("[bug-log-offline] %s\n" % (fmt % args))

    # ---- routes ----
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path in ('/', '/bug-log', '/bug-log.html'):
            self._get_bug_log()
        elif path == '/activity-feed':
            # Stub: trang v2 poll feed mỗi 60s. Offline không có chuông -> trả rỗng (JS no-op).
            self._json(200, {'ok': True, 'activities': [], 'tasks': {}})
        else:
            self._json(404, {'ok': False, 'err': 'not_found'})

    def do_POST(self):
        path = self.path.split('?', 1)[0]
        if path == '/sync-bug-log':
            self._post_sync_bug_log()
        else:
            self._json(404, {'ok': False, 'err': 'not_found'})

    def _get_bug_log(self):
        # Bug từ cache Drive (load_bug_log) + link app-side (load_links) + sources. KHÔNG gọi
        # Jira: activities=[] để né chuông notif (vốn fetch Jira changelog).
        try:
            res = run_parallel({'bug': load_bug_log, 'links': load_links, 'sources': load_sources})
            self._html(render_bug_log_v2(res['bug'], res['links'], editable=True,
                                         user=_OFFLINE_USER, activities=[],
                                         sources=res['sources']))
        except Exception as e:   # noqa: BLE001 — render lỗi -> trang lỗi thay vì 500 trần
            self._html(render_error_page(str(e)))

    def _post_sync_bug_log(self):
        # Trigger thủ công: scan() kéo Drive ngay (giống _post_sync_bug_log ở entry chính).
        try:
            res = bug_log_scan()
        except Exception:   # noqa: BLE001 — scan đã redact token; chặn mọi lỗi lạ
            res = {'ok': False, 'errors': ['Lỗi không xác định khi scan.']}
        self._json(200 if res.get('ok') else 400, res)


def main():
    start_bug_log_scheduler()   # daemon thread poll Drive (đọc .drive_token.json local)
    srv = HTTPServer(('127.0.0.1', PORT), Handler)
    print(f"Bug Log OFFLINE đang chạy: http://localhost:{PORT}/bug-log  (Ctrl+C để dừng)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng.")
        srv.shutdown()


if __name__ == '__main__':
    main()
