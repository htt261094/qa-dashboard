"""Jira REST API access: search, count, changelog authors, and the per-refresh bucket fetch.

PAT is read from config and never logged: network errors are redacted before raising.
"""
import sys
from datetime import datetime

from config import JIRA_URL, PAT, USERS, actor_name

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library missing. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

_DEFAULT_FIELDS = ('summary,status,assignee,reporter,duedate,created,'
                   'resolutiondate,updated,issuetype,comment,priority')


def _jira_request(jql, max_results, fields=_DEFAULT_FIELDS, expand=None):
    params = {'jql': jql, 'fields': fields, 'maxResults': max_results}
    if expand:
        params['expand'] = expand
    try:
        resp = requests.get(
            f"{JIRA_URL}/rest/api/2/search",
            headers={'Authorization': f'Bearer {PAT}', 'Accept': 'application/json'},
            params=params,
            timeout=30,
        )
        if resp.status_code == 401:
            raise RuntimeError("Jira 401 — PAT sai hoặc hết hạn")
        if resp.status_code == 403:
            raise RuntimeError("Jira 403 — PAT không đủ quyền")
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        msg = str(e).replace(PAT, '<REDACTED>')
        raise RuntimeError(f"Network error: {msg}")


def jira_search(jql, max_results=300):
    return _jira_request(jql, max_results).get('issues', [])


def jira_count(jql):
    """Cheap count: maxResults=0 returns only the total, no issue payload."""
    return _jira_request(jql, 0, fields='summary').get('total', 0)


def fetch_change_authors(keys):
    """For the given changed issue keys, return {key: {field: latest_author}} from changelog (1 light call)."""
    if not keys:
        return {}
    jql = 'key in (' + ','.join(keys) + ')'
    out = {}
    for issue in _jira_request(jql, len(keys), fields='summary', expand='changelog').get('issues', []):
        m = {}
        for h in (issue.get('changelog', {}) or {}).get('histories', []):  # oldest->newest: overwrite => latest wins
            who = actor_name(h.get('author'))
            for it in h.get('items', []):
                fid = it.get('fieldId') or it.get('field')
                if fid in ('status', 'assignee', 'duedate', 'priority', 'summary'):
                    m[fid] = who
        out[issue['key']] = m
    return out


def fetch_all():
    """Pull the 3 task buckets + 2 weekly counts. ~5 Jira calls per refresh."""
    user_list = ', '.join(USERS)
    return {
        'active': jira_search(
            f"assignee in ({user_list}) AND statusCategory != Done ORDER BY duedate ASC",
            max_results=300,
        ),
        'new24': jira_search(
            f"reporter in ({user_list}) AND created >= -24h ORDER BY created DESC",
            max_results=50,
        ),
        'done_week': jira_search(
            f'assignee in ({user_list}) AND status CHANGED TO "DONE" AFTER -3d ORDER BY updated DESC',
            max_results=100,
        ),
        # weekly inflow vs outflow (count-only, cheap)
        'created_week': jira_count(f"assignee in ({user_list}) AND created >= startOfWeek()"),
        'resolved_week': jira_count(f'assignee in ({user_list}) AND status CHANGED TO "DONE" AFTER startOfWeek()'),
        'fetched_at': datetime.now(),
    }
