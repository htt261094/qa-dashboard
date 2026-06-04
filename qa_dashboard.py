#!/usr/bin/env python3
"""QA Team Dashboard for Jira (Bảo Kim) — entry point.

Local web server on http://localhost:<PORT>. F5 = fresh pull from Jira.
Layered modules: config -> issues -> {jira_api, state, pic} -> render -> (this file).
Run: python qa_dashboard.py
"""
import http.server
import socketserver
import json
import sys
from datetime import datetime

from config import JIRA_URL, USERS, PORT, STATE_FILE, display_name
from jira_api import fetch_all, fetch_lines, fetch_activity_feed, load_dismissed, dismiss_activities
from state import load_state, save_state, build_snapshot
from pic import save_pic
from render import render_page, render_report_page, render_error_page

ACTIVITY_DAYS = 7  # cửa sổ activity feed kéo từ Jira changelog


def _build_view(data):
    """Snapshot diff CHỈ để highlight task mới (new_keys). Activity giờ kéo từ Jira feed
    (device-independent), không còn dùng local diff/pending."""
    cur_snapshot = build_snapshot(data)
    prev = load_state()
    first_run = prev is None
    if first_run:
        prev_keys = set()
    else:
        prev_snapshot = prev.get('snapshot') or {}
        prev_keys = set(prev_snapshot.keys()) if prev_snapshot else set(prev.get('keys', []))
    new_keys = set() if first_run else (set(cur_snapshot) - prev_keys)
    save_state(cur_snapshot, [])  # pending bỏ trống — không còn tích luỹ local
    return new_keys, first_run


# ===== HTTP server =====
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/report', '/report.html'):
            # read-only weekly report: fresh pull, but do NOT mutate activity state
            try:
                html_out = render_report_page(fetch_all(), fetch_lines())
            except RuntimeError as e:
                html_out = render_error_page(str(e))
            self._html(html_out)
            return
        if self.path not in ('/', '/index.html'):
            self.send_response(404)
            self.end_headers()
            return
        try:
            data = fetch_all()
            new_keys, first_run = _build_view(data)
            feed = fetch_activity_feed(days=ACTIVITY_DAYS)
            dismissed = load_dismissed()
            unread = [a for a in feed if a['id'] not in dismissed]
            html_out = render_page(data, new_keys, first_run, unread, ACTIVITY_DAYS)
        except RuntimeError as e:
            html_out = render_error_page(str(e))
        self._html(html_out)

    def _html(self, html_out):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        self.wfile.write(html_out.encode('utf-8'))

    def do_POST(self):
        if self.path == '/dismiss':
            ok = False
            try:
                length = int(self.headers.get('Content-Length', 0))
                if 0 < length <= 100_000:
                    payload = json.loads(self.rfile.read(length).decode('utf-8'))
                    ids = payload.get('ids') if isinstance(payload, dict) else None
                    if isinstance(ids, list) and all(isinstance(x, str) for x in ids):
                        ok = dismiss_activities(ids[:500])
            except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
                ok = False
            self._json(200 if ok else 400, b'{"ok":true}' if ok else b'{"ok":false}')
            return
        if self.path != '/save-pic':
            self.send_response(404)
            self.end_headers()
            return
        ok = False
        try:
            length = int(self.headers.get('Content-Length', 0))
            if 0 < length <= 200_000:
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                # minimal shape validation: list of {group, rows:[{flow, pic}]}
                if isinstance(payload, list) and all(
                    isinstance(g, dict) and 'group' in g and isinstance(g.get('rows'), list)
                    for g in payload
                ):
                    ok = save_pic(payload)
        except (ValueError, json.JSONDecodeError, OSError):
            ok = False
        self._json(200 if ok else 400, b'{"ok":true}' if ok else b'{"ok":false}')

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
