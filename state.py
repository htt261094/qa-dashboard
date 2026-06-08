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


def save_state(snapshot, pending):
    try:
        STATE_FILE.write_text(
            json.dumps({
                'snapshot': snapshot,
                'pending': pending,                # unread activities (notification-style, accumulate)
                'keys': sorted(snapshot.keys()),   # legacy field, kept for readability/compat
                'updated': datetime.now().isoformat(),
            }, ensure_ascii=False),
            encoding='utf-8',
        )
    except OSError:
        pass


def clear_pending():
    """Mark all activities as read: keep snapshot, empty the pending list."""
    st = load_state()
    save_state((st or {}).get('snapshot') or {}, [])
    return True


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


def compute_activities(prev_snapshot, cur_snapshot):
    """Diff two snapshots -> all task changes (status/assignee/due/priority/content/comment), newest first.
    Migration-safe: a field missing in the old snapshot is treated as unchanged (no false alarm)."""
    acts = []
    for k, cur in cur_snapshot.items():
        prev = prev_snapshot.get(k)
        if prev is None:
            acts.append({'kind': 'created', 'key': k, **cur})
            continue
        base = {'key': k, 'summary': cur.get('summary', ''), 'assignee': cur.get('assignee', ''),
                'updated': cur.get('updated', '')}

        def chg(field):  # old value, defaulting to current so a missing prev field = no change
            return prev.get(field, cur.get(field)) != cur.get(field)

        if chg('status'):
            acts.append({**base, 'kind': 'status', 'old': prev.get('status', ''), 'new': cur.get('status', '')})
        if chg('assignee'):
            acts.append({**base, 'kind': 'assignee', 'old': prev.get('assignee', ''), 'new': cur.get('assignee', '')})
        if chg('duedate'):
            acts.append({**base, 'kind': 'duedate', 'old': prev.get('duedate') or '—', 'new': cur.get('duedate') or '—'})
        if chg('priority'):
            acts.append({**base, 'kind': 'priority', 'old': prev.get('priority') or '—', 'new': cur.get('priority') or '—'})
        if chg('summary'):
            acts.append({**base, 'kind': 'summary'})
        prev_c, cur_c = prev.get('comments'), cur.get('comments', 0)
        if prev_c is not None and cur_c > prev_c:
            acts.append({**base, 'kind': 'comment', 'comment_delta': cur_c - prev_c})
    acts.sort(key=lambda a: a.get('updated') or '', reverse=True)
    return acts
