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

from config import JIRA_URL, USERS, PORT, STATE_FILE, display_name, actor_name
from jira_api import fetch_all, fetch_change_authors
from state import load_state, save_state, build_snapshot, compute_activities, clear_pending
from pic import save_pic
from render import render_page, render_report_page, render_error_page

_FIELD_OF = {'status': 'status', 'assignee': 'assignee', 'duedate': 'duedate',
             'priority': 'priority', 'summary': 'summary'}


def _attach_authors(new_acts, data, detected):
    """Stamp each activity with detection time + the author who made the change."""
    issue_by_key = {}
    for bucket in ('active', 'new24', 'done_week'):
        for iss in data[bucket]:
            issue_by_key.setdefault(iss['key'], iss)
    # field changes -> changelog (1 light call for the handful of changed tasks)
    changed_keys = sorted({a['key'] for a in new_acts if a['kind'] not in ('created', 'comment')})
    field_authors = fetch_change_authors(changed_keys)
    for a in new_acts:
        a['detected'] = detected
        k, kind = a['key'], a['kind']
        if kind == 'created':
            iss = issue_by_key.get(k)
            a['author'] = actor_name((iss or {}).get('fields', {}).get('reporter')) if iss else ''
        elif kind == 'comment':
            iss = issue_by_key.get(k)
            cmts = ((iss or {}).get('fields', {}).get('comment') or {}).get('comments') or []
            a['author'] = actor_name(cmts[-1].get('author')) if cmts else ''
        else:
            a['author'] = field_authors.get(k, {}).get(_FIELD_OF.get(kind, ''), '')


def _build_view(data):
    """From a fresh fetch, compute new_keys + accumulated pending activities, and persist state."""
    cur_snapshot = build_snapshot(data)
    prev = load_state()
    first_run = prev is None
    detected = data['fetched_at'].isoformat()

    if first_run:
        prev_keys, pending = set(), []
    else:
        prev_snapshot = prev.get('snapshot') or {}
        prev_pending = prev.get('pending') or []
        if prev_snapshot:
            prev_keys = set(prev_snapshot.keys())
            new_acts = compute_activities(prev_snapshot, cur_snapshot)
        else:
            # legacy state (keys only, no status history): treat new keys as "created"
            prev_keys = set(prev.get('keys', []))
            new_acts = [{'kind': 'created', 'key': k, **cur_snapshot[k]}
                        for k in cur_snapshot if k not in prev_keys]
        _attach_authors(new_acts, data, detected)
        # accumulate (notification-style); newest first; cap to bound state/view
        pending = new_acts + prev_pending
        pending.sort(key=lambda a: (a.get('detected') or '', a.get('updated') or ''), reverse=True)
        pending = pending[:100]

    new_keys = set() if first_run else (set(cur_snapshot) - prev_keys)
    save_state(cur_snapshot, pending)
    return new_keys, first_run, pending


# ===== HTTP server =====
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/report', '/report.html'):
            # read-only weekly report: fresh pull, but do NOT mutate activity state
            try:
                html_out = render_report_page(fetch_all())
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
            new_keys, first_run, pending = _build_view(data)
            html_out = render_page(data, new_keys, first_run, pending)
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
        if self.path == '/clear-activities':
            clear_pending()
            self._json(200, b'{"ok":true}')
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
