"""Jira issue field accessors (i_* prefix) and small domain helpers.

Pure functions over the raw issue dicts returned by the Jira API. No network, no state.
"""
import html as html_lib
from datetime import datetime

from config import JIRA_URL, STUCK_DAYS


def parse_date(s):
    if not s:
        return None
    try:
        if 'T' in s:
            return datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S')
        return datetime.strptime(s, '%Y-%m-%d')
    except ValueError:
        return None


def f(issue, key):
    return issue.get('fields', {}).get(key) or issue.get(key)


def i_assignee(issue):
    a = f(issue, 'assignee')
    if not a:
        return 'Unassigned'
    return a.get('name') or a.get('displayName', 'Unknown')


def i_reporter(issue):
    r = f(issue, 'reporter')
    if not r:
        return 'Unknown'
    return r.get('name') or r.get('displayName', 'Unknown')


def i_status(issue):
    s = f(issue, 'status') or {}
    return s.get('name', '')


def i_type(issue):
    t = f(issue, 'issuetype') or {}
    return t.get('name', '')


def i_summary(issue):
    return f(issue, 'summary') or ''


def i_duedate(issue):
    return f(issue, 'duedate')


def i_created(issue):
    return f(issue, 'created')


def i_resolved(issue):
    return f(issue, 'resolutiondate')


def i_updated(issue):
    return f(issue, 'updated')


def i_comment_count(issue):
    c = f(issue, 'comment')
    return c.get('total', 0) if isinstance(c, dict) else 0


def i_priority(issue):
    p = f(issue, 'priority')
    return p.get('name', '') if isinstance(p, dict) else ''


def days_overdue(issue):
    d = parse_date(i_duedate(issue))
    if not d:
        return None
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    delta = (today - d).days
    return delta if delta > 0 else None


def days_since_update(issue):
    d = parse_date(i_updated(issue))
    if not d:
        return None
    return (datetime.now() - d).days


def is_stuck(issue):
    """In-flight (không phải TO DO) mà không cập nhật >= STUCK_DAYS ngày."""
    if i_status(issue).strip().upper() == 'TO DO':
        return False
    d = days_since_update(issue)
    return d is not None and d >= STUCK_DAYS


def esc(s):
    return html_lib.escape(str(s)) if s is not None else ''


def issue_link(issue):
    key = issue['key']
    return f'<a href="{JIRA_URL}/browse/{esc(key)}" target="_blank" class="key">{esc(key)}</a>'


def status_class(name):
    n = (name or '').upper()
    if 'PROGRESS' in n:
        return 'status-progress'
    if 'PEND' in n:
        return 'status-pending'
    if 'DONE' in n or 'CLOSED' in n or 'RESOLVED' in n:
        return 'status-done'
    if 'CANCEL' in n:
        return 'status-cancel'
    return 'status-todo'
