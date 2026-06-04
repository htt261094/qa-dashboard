"""Jira REST API access: search, count, changelog authors, and the per-refresh bucket fetch.

PAT is read from config and never logged: network errors are redacted before raising.
"""
import sys
import json
from datetime import datetime, timedelta

from config import JIRA_URL, PAT, USERS, actor_name
from issues import parse_date

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


def jira_search(jql, max_results=300, fields=_DEFAULT_FIELDS):
    return _jira_request(jql, max_results, fields=fields).get('issues', [])


def jira_count(jql):
    """Cheap count: maxResults=0 returns only the total, no issue payload."""
    return _jira_request(jql, 0, fields='summary').get('total', 0)


# ===== Activity feed (kéo thẳng từ Jira changelog — device-independent) =====
_ACT_FIELDS = {'status', 'assignee', 'duedate', 'priority', 'summary'}


def _comment_snippet(body, n=140):
    """Rút gọn nội dung comment: gộp xuống dòng/khoảng trắng, cắt ~n ký tự."""
    if not body:
        return ''
    s = ' '.join(str(body).split())
    return s if len(s) <= n else s[:n].rstrip() + '…'


def fetch_activity_feed(days=7, cap=300, max_issues=120):
    """Reconstruct activity từ Jira changelog/comment trong `days` ngày gần nhất.

    Nguồn = Jira (source of truth), KHÔNG phụ thuộc .last_seen.json → máy nào mở cũng
    thấy y hệt. Mỗi activity có `id` ổn định (key#histId#field / key#cmt#id / key#created)
    để dismiss đồng bộ chéo máy. Trả list dict {id, kind, key, summary, author, when, old, new}.
    """
    user_list = ', '.join(USERS)
    start = datetime.now() - timedelta(days=days)
    jql = (f"(assignee in ({user_list}) OR reporter in ({user_list})) "
           f"AND updated >= -{days}d ORDER BY updated DESC")
    issues = _jira_request(jql, max_issues, expand='changelog',
                           fields='summary,status,assignee,reporter,issuetype,created,comment').get('issues', [])
    acts = []
    for iss in issues:
        key = iss['key']
        f = iss.get('fields', {})
        summary = f.get('summary') or ''
        cr = parse_date(f.get('created'))
        if cr and cr >= start:
            acts.append({'id': f'{key}#created', 'kind': 'created', 'key': key, 'summary': summary,
                         'author': actor_name(f.get('reporter')), 'when': f.get('created')})
        for h in (iss.get('changelog', {}) or {}).get('histories', []):
            hc = parse_date(h.get('created'))
            if not hc or hc < start:
                continue
            who = actor_name(h.get('author'))
            for it in h.get('items', []):
                fid = (it.get('fieldId') or it.get('field') or '').lower().replace(' ', '')
                if fid not in _ACT_FIELDS:
                    continue
                a = {'id': f"{key}#{h.get('id')}#{fid}", 'kind': fid, 'key': key,
                     'summary': summary, 'author': who, 'when': h.get('created')}
                if fid == 'duedate':
                    a['old'] = (it.get('fromString') or '')[:10] or '—'
                    a['new'] = (it.get('toString') or '')[:10] or '—'
                elif fid in ('status', 'priority'):
                    a['old'] = it.get('fromString') or '—'
                    a['new'] = it.get('toString') or '—'
                elif fid == 'assignee':
                    a['old'] = it.get('from') or ''
                    a['new'] = it.get('to') or ''
                acts.append(a)
        for c in ((f.get('comment') or {}).get('comments') or []):
            cc = parse_date(c.get('created'))
            if not cc or cc < start:
                continue
            acts.append({'id': f"{key}#cmt#{c.get('id')}", 'kind': 'comment', 'key': key,
                         'summary': summary, 'author': actor_name(c.get('author')),
                         'when': c.get('created'), 'comment_delta': 1,
                         'body': _comment_snippet(c.get('body'))})
    acts.sort(key=lambda a: a.get('when') or '', reverse=True)
    return acts[:cap]


# ===== Dismiss state lưu ở Jira user property (shared cross-device) =====
_READ_PROP = 'qa-dashboard-read'
_USERNAME = None


def _auth_headers(extra=None):
    h = {'Authorization': f'Bearer {PAT}', 'Accept': 'application/json'}
    if extra:
        h.update(extra)
    return h


def _current_username():
    global _USERNAME
    if _USERNAME is None:
        try:
            r = requests.get(f"{JIRA_URL}/rest/api/2/myself", headers=_auth_headers(), timeout=15)
            r.raise_for_status()
            _USERNAME = r.json().get('name') or r.json().get('key')
        except requests.RequestException as e:
            raise RuntimeError(f"Network error: {str(e).replace(PAT, '<REDACTED>')}")
    return _USERNAME


def load_dismissed():
    """{activity_id: dismissed_at_iso} từ Jira user property. {} nếu chưa có."""
    try:
        r = requests.get(f"{JIRA_URL}/rest/api/2/user/properties/{_READ_PROP}",
                         headers=_auth_headers(), params={'username': _current_username()}, timeout=15)
        if r.status_code == 404:
            return {}
        r.raise_for_status()
        val = r.json().get('value') or {}
        d = val.get('dismissed') if isinstance(val, dict) else None
        return d if isinstance(d, dict) else {}
    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {str(e).replace(PAT, '<REDACTED>')}")


def save_dismissed(dismissed):
    body = json.dumps({'dismissed': dismissed, 'updated': datetime.now().isoformat()})
    try:
        requests.put(f"{JIRA_URL}/rest/api/2/user/properties/{_READ_PROP}",
                     headers=_auth_headers({'Content-Type': 'application/json'}),
                     params={'username': _current_username()}, data=body, timeout=15)
    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {str(e).replace(PAT, '<REDACTED>')}")


def dismiss_activities(ids, prune_days=14):
    """Thêm ids vào set đã-dismiss (Jira), prune entry cũ hơn prune_days. Cross-device."""
    if not ids:
        return True
    dismissed = load_dismissed()
    now = datetime.now()
    stamp = now.isoformat()
    for i in ids:
        dismissed[i] = stamp
    cutoff = (now - timedelta(days=prune_days)).isoformat()
    dismissed = {k: v for k, v in dismissed.items() if v >= cutoff}
    save_dismissed(dismissed)
    return True


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


_LINE_FIELDS = _DEFAULT_FIELDS + ',parent,issuelinks'


def _parent_key(issue):
    """Immediate parent key. Native `parent` field first (Sub-task -> Task-PTSP),
    rồi issue-link `is child of` (Task-PTSP -> Task -> Story). None nếu là gốc."""
    fields = issue.get('fields', {})
    p = fields.get('parent')
    if p and p.get('key'):
        return p['key']
    for link in (fields.get('issuelinks') or []):
        t = link.get('type') or {}
        if link.get('inwardIssue') and t.get('inward') == 'is child of':
            return link['inwardIssue']['key']
    return None


def _last_week_window(now=None):
    """[Thứ 2 tuần trước, Thứ 2 tuần này) — cửa sổ báo cáo tuần."""
    now = now or datetime.now()
    this_mon = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return this_mon - timedelta(days=7), this_mon


def fetch_lines(max_results=500, max_depth=8, now=None):
    """QA tasks tuần trước (+ mọi task In Progress/PENDING) gom theo line gốc qua 'is child of'.

    Filter: updated trong cửa sổ tuần trước HOẶC đang In Progress/PENDING (việc dở luôn liệt kê).
    Returns {'qa_issues', 'root_of', 'known', 'window': (start, end)}.
    Calls: 1 (QA tasks) + 1 per ancestry level (usually 1-3). Used only by /report.
    """
    user_list = ', '.join(USERS)
    start, end = _last_week_window(now)
    s, e = start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')
    jql = (f'assignee in ({user_list}) AND ('
           f'status in ("In Progress", "PENDING") '
           f'OR (updated >= "{s}" AND updated < "{e}")) ORDER BY updated DESC')
    qa = jira_search(jql, max_results=max_results, fields=_LINE_FIELDS)
    known = {i['key']: i for i in qa}
    frontier = {pk for i in qa if (pk := _parent_key(i))}
    depth = 0
    while frontier and depth < max_depth:
        need = [k for k in frontier if k not in known]
        if not need:
            break
        for off in range(0, len(need), 200):  # JQL 'key in (...)' batch cap
            chunk = need[off:off + 200]
            for i in jira_search('key in (' + ','.join(chunk) + ')',
                                 max_results=len(chunk), fields=_LINE_FIELDS):
                known[i['key']] = i
        frontier = {pk for k in need if k in known and (pk := _parent_key(known[k]))}
        depth += 1

    parent_of = {k: _parent_key(iss) for k, iss in known.items()}
    return {'qa_issues': qa, 'parent_of': parent_of, 'known': known, 'window': (start, end)}


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
