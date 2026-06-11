"""Snapshot + activity state persisted in .last_seen.json.

snapshot = per-key field values from the last refresh (for diffing).
pending   = accumulated unread activities (notification-style), cleared via "Đã đọc".
"""
import json
from datetime import datetime

from config import STATE_FILE
from issues import (i_status, i_summary, i_assignee, i_type, i_updated, i_created,
                    i_comment_count, i_duedate, i_priority)


def load_state():
    """Return the previous state dict (may contain 'snapshot' and/or legacy 'keys'), or None on first run."""
    if not STATE_FILE.exists():
        return None
    try:
        d = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        return d if isinstance(d, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def load_snapshots():
    """Return {scope_key: snapshot} từ .last_seen.json (baseline NEW-badge theo từng scope).

    Migration-safe: định dạng cũ (1 snapshot phẳng, dùng chung) -> trả {} để mỗi scope
    bắt đầu baseline mới ở lần load kế (không bùng NEW oan)."""
    st = load_state()
    if not isinstance(st, dict):
        return {}
    snaps = st.get('snapshots')
    return snaps if isinstance(snaps, dict) else {}


def save_snapshots(snaps):
    """Ghi map {scope_key: snapshot} (mỗi scope giữ baseline riêng -> admin vs QA không
    ghi đè nhau)."""
    try:
        STATE_FILE.write_text(
            json.dumps({'snapshots': snaps, 'updated': datetime.now().isoformat()},
                       ensure_ascii=False),
            encoding='utf-8',
        )
    except OSError:
        pass


def build_snapshot(data):
    """Map key -> {status, summary, assignee, type, updated, comments, duedate, priority} across all buckets."""
    snap = {}
    for bucket in ('active', 'new24', 'done_week'):
        for issue in data[bucket]:
            k = issue['key']
            if k not in snap:
                snap[k] = {
                    'status': i_status(issue),
                    'summary': i_summary(issue),
                    'assignee': i_assignee(issue),
                    'type': i_type(issue),
                    'updated': i_updated(issue) or i_created(issue) or '',
                    'comments': i_comment_count(issue),
                    'duedate': i_duedate(issue) or '',
                    'priority': i_priority(issue),
                }
    return snap


