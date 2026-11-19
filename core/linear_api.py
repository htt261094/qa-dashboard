"""Linear GraphQL API client — read/search/activity/detail + issue normalization.

Thay thế jira_api.py: trả về cùng schema issue dict để core/issues.py, core/status_overlay.py,
core/render/* và qa_dashboard.py dùng lại không cần đổi tầng tính toán.
"""
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    LINEAR_API_KEY, LINEAR_BASE_URL, LINEAR_TEAM_KEYS, LINEAR_EXCLUDED_TEAMS,
    LINEAR_MAX_CONCURRENT, PAT, USERS,
)
from status_overlay import patch_issues as _ov_patch_issues, patch_data as _ov_patch_data

LINEAR_ENDPOINT = 'https://api.linear.app/graphql'
_TIMEOUT = (5, 20)

_SEM = threading.BoundedSemaphore(LINEAR_MAX_CONCURRENT)


class AuthError(RuntimeError):
    """Linear API key thiếu, hết hạn, hoặc bị thu hồi (HTTP 401/403)."""


def _build_session():
    s = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=(429, 502, 503, 504),
        allowed_methods=('POST',),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=LINEAR_MAX_CONCURRENT)
    s.mount('https://', adapter)
    s.mount('http://', adapter)
    return s


_SESSION = _build_session()

_CACHE_LOCK = threading.Lock()
_CACHE = {}  # key -> (ts, val)
_CACHE_TTL = 120
_CACHE_STALE_TTL = 1800

_INFLIGHT_LOCK = threading.Lock()
_INFLIGHT = {}  # key -> threading.Event

_AUTH_ERR_LOCK = threading.Lock()
_LAST_AUTH_ERR = ''


def _redact(msg):
    s = str(msg)
    for secret in (PAT, LINEAR_API_KEY):
        if secret and len(secret) > 6:
            s = s.replace(secret, '***')
    return s


def _headers(token=None):
    tok = (token or LINEAR_API_KEY or '').strip()
    return {
        'Authorization': tok,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }


def gql(query, variables=None, token=None, timeout=_TIMEOUT):
    """Execute a Linear GraphQL query/mutation and return `data` dict."""
    tok = (token or LINEAR_API_KEY or '').strip()
    if not tok:
        raise AuthError('Thiếu LINEAR_API_KEY trong .env')
    payload = {'query': query}
    if variables:
        payload['variables'] = variables
    with _SEM:
        try:
            resp = _SESSION.post(LINEAR_ENDPOINT, json=payload, headers=_headers(tok), timeout=timeout)
        except requests.RequestException as e:
            raise RuntimeError(f'Linear network error: {_redact(e)}') from e
    if resp.status_code in (401, 403):
        raise AuthError(f'Linear auth failed (HTTP {resp.status_code})')
    if resp.status_code >= 400:
        raise RuntimeError(f'Linear HTTP {resp.status_code}: {_redact(resp.text[:300])}')
    try:
        body = resp.json()
    except ValueError as e:
        raise RuntimeError(f'Linear invalid JSON: {e}') from e
    if body.get('errors'):
        msgs = '; '.join(e.get('message', '?') for e in body['errors'])
        if any('authentication' in m.lower() or 'unauthorized' in m.lower() for m in [msgs]):
            raise AuthError(f'Linear auth error: {msgs}')
        raise RuntimeError(f'Linear GraphQL error: {_redact(msgs)}')
    return body.get('data') or {}


def run_parallel(tasks):
    """Run callables concurrently in a thread pool. Supports dict {k: fn} -> {k: res} or list [fn] -> [res]."""
    if not tasks:
        return {} if isinstance(tasks, dict) else []
    workers = min(len(tasks), LINEAR_MAX_CONCURRENT, 8)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        if isinstance(tasks, dict):
            futs = {k: ex.submit(fn) for k, fn in tasks.items()}
            return {k: f.result() for k, f in futs.items()}
        futs = [ex.submit(fn) for fn in tasks]
        return [f.result() for f in futs]


def canon_state(state):
    """Map Linear WorkflowState {name, type} -> board status ('TO DO'|'In Progress'|'PENDING'|'DONE'|'CANCELLED')."""
    if not state:
        return 'TO DO'
    stype = (state.get('type') or '').lower()
    sname = (state.get('name') or '').strip()
    low = sname.lower()
    if stype == 'completed':
        return 'DONE'
    if stype in ('canceled', 'cancelled', 'duplicate'):
        return 'CANCELLED'
    if stype in ('triage', 'backlog', 'unstarted'):
        return 'TO DO'
    if stype == 'started':
        if any(k in low for k in ('review', 'testing', 'ready', 'pending')):
            return 'PENDING'
        return 'In Progress'
    return sname or 'TO DO'


def _norm_user(u):
    if not u:
        return None
    email = (u.get('email') or '').strip()
    local = email.split('@', 1)[0].lower() if '@' in email else ''
    dname = (u.get('displayName') or u.get('name') or local or '').strip()
    return {
        'id': u.get('id', ''),
        'name': dname or local,
        'key': local or dname,
        'displayName': u.get('name') or dname,
        'emailAddress': email,
    }


def _infer_issuetype(node):
    title = (node.get('title') or '').lstrip().lower()
    if title.startswith('[bug]'):
        return 'Bug'
    labels = ((node.get('labels') or {}).get('nodes') or [])
    for lb in labels:
        n = (lb.get('name') or '').strip().lower()
        if n == 'bug':
            return 'Bug'
        if n == 'improvement':
            return 'Improvement'
    if node.get('parent'):
        return 'Sub-task'
    return 'Task'


def normalize_issue(node):
    """Convert Linear Issue node -> Jira-compatible issue dict for core/issues.py & UI."""
    ident = node.get('identifier') or node.get('id') or ''
    url = node.get('url') or f'{LINEAR_BASE_URL}/issue/{ident}'
    comments_obj = node.get('comments') or {}
    c_nodes = comments_obj.get('nodes') or []
    c_total = comments_obj.get('totalCount')
    if c_total is None:
        c_total = len(c_nodes)
    p = node.get('parent')
    parent_obj = {'key': p.get('identifier', ''), 'fields': {'summary': p.get('title', '')}} if p else None
    pr = node.get('project')
    project_obj = {'id': pr.get('id', ''), 'name': pr.get('name', ''), 'url': pr.get('url', '')} if pr else None
    subtasks = [
        {
            'key': c.get('identifier', ''),
            'summary': c.get('title', ''),
            'status': ((c.get('state') or {}).get('name') or canon_state(c.get('state'))).strip(),
            'cat': canon_state(c.get('state')),
        }
        for c in ((node.get('children') or {}).get('nodes') or [])
    ]
    return {
        'key': ident,
        'id': node.get('id', ''),
        'url': url,
        'subtasks': subtasks,
        'fields': {
            'summary': node.get('title') or '',
            'description': node.get('description') or '',
            'status': {
                'name': ((node.get('state') or {}).get('name') or canon_state(node.get('state'))).strip(),
                'category': canon_state(node.get('state')),
            },
            'assignee': _norm_user(node.get('assignee')),
            'reporter': _norm_user(node.get('creator')),
            'duedate': node.get('dueDate') or None,
            'created': node.get('createdAt') or '',
            'resolutiondate': node.get('completedAt') or '',
            'updated': node.get('updatedAt') or '',
            'issuetype': {'name': _infer_issuetype(node)},
            'parent': parent_obj,
            'project': project_obj,
            'comment': {'total': c_total},
            'priority': {'name': node.get('priorityLabel') or 'No priority'},
        },
    }


_ISSUE_FIELDS_GQL = """
  id
  identifier
  title
  priority
  priorityLabel
  dueDate
  createdAt
  updatedAt
  completedAt
  url
  state { id name type }
  assignee { id name displayName email }
  creator { id name displayName email }
  team { id key name }
  project { id name url }
  parent { id identifier title }
  children(first: 20) { nodes { id identifier title state { name type } } }
  labels { nodes { id name } }
  comments(first: 1) { nodes { id } }
"""


def _base_filter(extra=None):
    flt = {}
    if LINEAR_TEAM_KEYS:
        flt['team'] = {'key': {'in': LINEAR_TEAM_KEYS}}
    elif LINEAR_EXCLUDED_TEAMS:
        flt['team'] = {'key': {'nin': LINEAR_EXCLUDED_TEAMS}}
    if USERS:
        flt['assignee'] = {'email': {'in': USERS}}
    if extra:
        flt.update(extra)
    return flt


def _fetch_issues_query(flt, limit=250, max_pages=2):
    query = f"""
    query Issues($first: Int!, $after: String, $filter: IssueFilter) {{
      issues(first: $first, after: $after, orderBy: updatedAt, filter: $filter) {{
        pageInfo {{ hasNextPage endCursor }}
        nodes {{
          {_ISSUE_FIELDS_GQL}
        }}
      }}
    }}
    """
    out = []
    after = None
    page_sz = min(limit, 250)
    for _ in range(max_pages):
        data = gql(query, {'first': page_sz, 'after': after, 'filter': flt})
        conn = data.get('issues') or {}
        nodes = conn.get('nodes') or []
        out.extend(normalize_issue(n) for n in nodes)
        pi = conn.get('pageInfo') or {}
        if len(out) >= limit or not pi.get('hasNextPage') or not pi.get('endCursor'):
            break
        after = pi['endCursor']
    return out[:limit]


def _iso_days_ago(days):
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _compute_fetch_all(scope_user=None):
    since_24h = _iso_days_ago(1)
    since_7d = _iso_days_ago(7)

    active_flt = _base_filter({'state': {'type': {'in': ['triage', 'backlog', 'unstarted', 'started']}}})
    new24_flt = _base_filter({'createdAt': {'gte': since_24h}})
    done_cycle_flt = _base_filter({
        'state': {'type': {'eq': 'completed'}},
        'cycle': {'isActive': {'eq': True}},
    })
    created_week_flt = _base_filter({'createdAt': {'gte': since_7d}})

    active, new24, done_week, created_week = run_parallel([
        lambda: _fetch_issues_query(active_flt, 350, max_pages=2),
        lambda: _fetch_issues_query(new24_flt, 100, max_pages=1),
        lambda: _fetch_issues_query(done_cycle_flt, 350, max_pages=2),
        lambda: _fetch_issues_query(created_week_flt, 150, max_pages=1),
    ])

    data = {
        'active': active,
        'new24': new24,
        'done_week': done_week,
        'done_total': len(done_week),
        'created_week': len(created_week),
        'resolved_week': len(done_week),
        'fetched_at': datetime.now(),
    }
    _ov_patch_data(data)
    if scope_user:
        return scope_data(data, scope_user)
    return data


def _swr_get(key, compute_fn, force=False, block=True):
    now = time.time()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
    if not force and entry:
        ts, val = entry
        if now - ts < _CACHE_TTL:
            return val
        if not block and now - ts < _CACHE_STALE_TTL:
            _trigger_bg_refresh(key, compute_fn)
            return val

    with _INFLIGHT_LOCK:
        ev = _INFLIGHT.get(key)
        if ev is not None:
            is_owner = False
        else:
            ev = threading.Event()
            _INFLIGHT[key] = ev
            is_owner = True

    if not is_owner:
        ev.wait(timeout=25)
        with _CACHE_LOCK:
            entry = _CACHE.get(key)
        if entry:
            return entry[1]
        return compute_fn()

    try:
        val = compute_fn()
        with _CACHE_LOCK:
            _CACHE[key] = (time.time(), val)
        with _AUTH_ERR_LOCK:
            global _LAST_AUTH_ERR
            _LAST_AUTH_ERR = ''
        return val
    except AuthError as e:
        with _AUTH_ERR_LOCK:
            _LAST_AUTH_ERR = str(e)
        if entry:
            return entry[1]
        raise
    finally:
        with _INFLIGHT_LOCK:
            _INFLIGHT.pop(key, None)
        ev.set()


def _trigger_bg_refresh(key, compute_fn):
    with _INFLIGHT_LOCK:
        if key in _INFLIGHT:
            return

    def _run():
        try:
            _swr_get(key, compute_fn, force=True, block=True)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def fetch_all(scope_user=None, force=False):
    key = f'fetch_all:{scope_user or "*"}'
    return _swr_get(key, lambda: _compute_fetch_all(scope_user), force=force, block=True)


def fetch_all_shared(force=False):
    """Return (data_dict, stale: False | 'auth')."""
    try:
        data = fetch_all(scope_user=None, force=force)
        return data, False
    except AuthError:
        with _CACHE_LOCK:
            entry = _CACHE.get('fetch_all:*')
        if entry:
            return entry[1], 'auth'
        raise


def scope_data(data, scope_user):
    if not scope_user or not data:
        return data
    from issues import i_assignee, i_reporter
    su = scope_user.lower()
    out = dict(data)
    out['active'] = [i for i in data.get('active', []) if (i_assignee(i) or '').lower() == su]
    out['done_week'] = [i for i in data.get('done_week', []) if (i_assignee(i) or '').lower() == su]
    out['new24'] = [i for i in data.get('new24', []) if (i_reporter(i) or '').lower() == su]
    out['done_total'] = len(out['done_week'])
    out['created_week'] = 0
    out['resolved_week'] = 0
    return out


def _actor_label(u):
    if not u:
        return '?'
    return (u.get('name') or u.get('displayName') or u.get('email') or '?').strip()


def _compute_activity_feed(days=7, cap=300, max_issues=60, scope_user=None, with_status=False):
    since = _iso_days_ago(days)
    flt = _base_filter({'updatedAt': {'gte': since}})
    query = """
    query Activity($first: Int!, $filter: IssueFilter) {
      issues(first: $first, orderBy: updatedAt, filter: $filter) {
        nodes {
          id
          identifier
          title
          createdAt
          url
          state { id name type }
          creator { id name displayName email }
          assignee { id name displayName email }
          comments(first: 10) {
            nodes {
              id
              body
              createdAt
              user { id name displayName email }
            }
          }
          history(first: 15) {
            nodes {
              id
              createdAt
              actor { id name displayName email }
              fromState { name type }
              toState { name type }
              fromAssignee { name displayName email }
              toAssignee { name displayName email }
              fromDueDate
              toDueDate
              fromPriority
              toPriority
            }
          }
        }
      }
    }
    """
    data = gql(query, {'first': min(max_issues, 80), 'filter': flt})
    nodes = ((data.get('issues') or {}).get('nodes') or [])
    acts = []
    statuses = {}
    for n in nodes:
        key = n.get('identifier') or ''
        summary = n.get('title') or ''
        statuses[key] = ((n.get('state') or {}).get('name') or canon_state(n.get('state'))).strip()
        created_at = n.get('createdAt') or ''
        if created_at >= since:
            acts.append({
                'id': f'{key}#created',
                'kind': 'created',
                'key': key,
                'summary': summary,
                'author': _actor_label(n.get('creator')),
                'when': created_at,
                'assignee': _actor_label(n.get('assignee')) if n.get('assignee') else '',
            })
        for c in ((n.get('comments') or {}).get('nodes') or []):
            when = c.get('createdAt') or ''
            if when < since:
                continue
            body = (c.get('body') or '').strip()
            acts.append({
                'id': f'{key}#cmt#{c.get("id", "")}',
                'kind': 'comment',
                'key': key,
                'summary': summary,
                'author': _actor_label(c.get('user')),
                'when': when,
                'comment_delta': 1,
                'mention': False,
                'body': body[:160],
            })
        for h in ((n.get('history') or {}).get('nodes') or []):
            when = h.get('createdAt') or ''
            if when < since:
                continue
            actor = _actor_label(h.get('actor'))
            hid = h.get('id', '')
            if h.get('toState') and h.get('fromState'):
                acts.append({
                    'id': f'{key}#{hid}#status',
                    'kind': 'status',
                    'key': key,
                    'summary': summary,
                    'author': actor,
                    'when': when,
                    'old': (h['fromState'].get('name') or canon_state(h['fromState'])),
                    'new': (h['toState'].get('name') or canon_state(h['toState'])),
                })
            elif h.get('toAssignee') or h.get('fromAssignee'):
                acts.append({
                    'id': f'{key}#{hid}#assignee',
                    'kind': 'assignee',
                    'key': key,
                    'summary': summary,
                    'author': actor,
                    'when': when,
                    'old': _actor_label(h.get('fromAssignee')) if h.get('fromAssignee') else 'Unassigned',
                    'new': _actor_label(h.get('toAssignee')) if h.get('toAssignee') else 'Unassigned',
                })
            elif h.get('fromDueDate') != h.get('toDueDate'):
                acts.append({
                    'id': f'{key}#{hid}#duedate',
                    'kind': 'duedate',
                    'key': key,
                    'summary': summary,
                    'author': actor,
                    'when': when,
                    'old': h.get('fromDueDate') or '—',
                    'new': h.get('toDueDate') or '—',
                })
    acts.sort(key=lambda a: a.get('when', ''), reverse=True)
    acts = acts[:cap]
    return (acts, statuses) if with_status else acts


def fetch_activity_feed(days=7, cap=300, max_issues=120, scope_user=None,
                        with_status=False, block=True, force=False):
    key = f'activity:{days}:{scope_user or "*"}:{int(with_status)}'
    return _swr_get(
        key,
        lambda: _compute_activity_feed(days=days, cap=cap, max_issues=min(max_issues, 60),
                                       scope_user=scope_user, with_status=with_status),
        force=force,
        block=block,
    )


def _to_local_str(iso_str, fmt='%Y-%m-%d %H:%M'):
    if not iso_str:
        return ''
    try:
        s = iso_str.strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime(fmt)
    except ValueError:
        return iso_str[:16].replace('T', ' ')


def fetch_issue_detail(key):
    query = """
    query IssueDetail($id: String!) {
      issue(id: $id) {
        id
        identifier
        title
        description
        dueDate
        createdAt
        updatedAt
        url
        state { id name type }
        assignee { id name displayName email }
        project { id name url }
        parent { id identifier title }
        labels(first: 20) { nodes { name } }
        children(first: 20) {
          nodes {
            identifier
            title
            state { name type }
            assignee { id name displayName email }
          }
        }
        comments(first: 50) {
          nodes {
            id
            body
            createdAt
            user { id name displayName email }
          }
        }
      }
    }
    """
    data = gql(query, {'id': key})
    n = data.get('issue')
    if not n:
        return {
            'key': key, 'summary': '', 'description': '', 'status': 'TO DO',
            'assignee': 'Unassigned', 'duedate': '', 'updated': '', 'devs': [], 'comments': [],
        }
    norm = normalize_issue(n)
    _ov_patch_issues([norm])
    devs = []
    seen_devs = set()
    subtasks = []
    for ch in ((n.get('children') or {}).get('nodes') or []):
        a = ch.get('assignee')
        if a:
            dn = _actor_label(a)
            if dn not in seen_devs:
                seen_devs.add(dn)
                devs.append(dn)
        subtasks.append({
            'key': ch.get('identifier', ''),
            'summary': ch.get('title', ''),
            'status': ((ch.get('state') or {}).get('name') or canon_state(ch.get('state'))).strip(),
            'assignee': _actor_label(a) if a else 'Unassigned',
        })
    p = n.get('parent')
    parent_info = {'key': p.get('identifier', ''), 'summary': p.get('title', '')} if p else None
    pr = n.get('project')
    project_info = {'name': pr.get('name', ''), 'url': pr.get('url', '')} if pr else None
    cmts = []
    for c in ((n.get('comments') or {}).get('nodes') or []):
        cmts.append({
            'author': _actor_label(c.get('user')),
            'when': _to_local_str(c.get('createdAt'), '%Y-%m-%d %H:%M'),
            'body': c.get('body') or '',
        })
    cmts.reverse()
    asg = n.get('assignee')
    return {
        'key': norm['key'],
        'url': norm['url'],
        'issuetype': _infer_issuetype(n),
        'parent': parent_info,
        'project': project_info,
        'subtasks': subtasks,
        'summary': norm['fields']['summary'],
        'description': n.get('description') or '',
        'status': norm['fields']['status']['name'],
        'assignee': _actor_label(asg) if asg else 'Unassigned',
        'duedate': n.get('dueDate') or '',
        'updated': _to_local_str(n.get('updatedAt'), '%Y-%m-%d %H:%M'),
        'created': _to_local_str(n.get('createdAt'), '%Y-%m-%d %H:%M'),
        'devs': devs,
        'comments': cmts,
    }


def search_parent_tasks(query_str, limit=20):
    q = (query_str or '').strip()
    if not q:
        flt = _base_filter({'state': {'type': {'in': ['triage', 'backlog', 'unstarted', 'started']}}})
        query = """
        query RecentParents($first: Int!, $filter: IssueFilter) {
          issues(first: $first, orderBy: updatedAt, filter: $filter) {
            nodes { identifier title team { key name } }
          }
        }
        """
        data = gql(query, {'first': limit, 'filter': flt})
        nodes = ((data.get('issues') or {}).get('nodes') or [])
    else:
        query = """
        query SearchParents($term: String!, $first: Int!) {
          searchIssues(term: $term, first: $first) {
            nodes { identifier title team { key name } }
          }
        }
        """
        data = gql(query, {'term': q, 'first': limit})
        nodes = ((data.get('searchIssues') or {}).get('nodes') or [])
    return [
        {
            'key': n.get('identifier', ''),
            'summary': n.get('title', ''),
            'project': (n.get('team') or {}).get('key', ''),
            'type': 'Task',
        }
        for n in nodes
        if (n.get('team') or {}).get('key', '').upper() not in LINEAR_EXCLUDED_TEAMS
    ]


def search_parent_ptsp(query_str, limit=20):
    return search_parent_tasks(query_str, limit=limit)


def search_qa_tasks(query_str, limit=20):
    return global_search(query_str, limit=limit)


def global_search(query_str, limit=20):
    q = (query_str or '').strip()
    if not q:
        return []
    query = """
    query GlobalSearch($term: String!, $first: Int!) {
      searchIssues(term: $term, first: $first) {
        nodes {
          identifier
          title
          url
          state { name type }
          assignee { name displayName email }
          team { key name }
          labels { nodes { name } }
        }
      }
    }
    """
    data = gql(query, {'term': q, 'first': limit})
    nodes = ((data.get('searchIssues') or {}).get('nodes') or [])
    out = []
    for n in nodes:
        tkey = (n.get('team') or {}).get('key', '')
        if tkey.upper() in LINEAR_EXCLUDED_TEAMS:
            continue
        ident = n.get('identifier', '')
        out.append({
            'key': ident,
            'summary': n.get('title', ''),
            'status': ((n.get('state') or {}).get('name') or canon_state(n.get('state'))).strip(),
            'assignee': _actor_label(n.get('assignee')) if n.get('assignee') else 'Unassigned',
            'type': _infer_issuetype(n),
            'project': tkey,
            'url': n.get('url') or f'{LINEAR_BASE_URL}/issue/{ident}',
        })
    return out


def search_people(query_str, limit=30):
    q = (query_str or '').strip().lower()
    query = """
    query Users {
      users(first: 100) {
        nodes { id name displayName email active }
      }
    }
    """
    data = gql(query)
    nodes = ((data.get('users') or {}).get('nodes') or [])
    out = []
    for u in nodes:
        if not u.get('active', True):
            continue
        email = (u.get('email') or '').strip()
        dname = (u.get('displayName') or u.get('name') or '').strip()
        full = (u.get('name') or dname).strip()
        if q and q not in email.lower() and q not in dname.lower() and q not in full.lower():
            continue
        out.append({
            'id': u.get('id', ''),
            'name': u.get('id', ''),
            'display': f'{full} ({dname})' if dname and dname.lower() != full.lower() else full,
            'email': email,
        })
        if len(out) >= limit:
            break
    return out


def verify_user_token(token):
    """Verify a Linear API key via `viewer` query. Returns viewer email/name or None."""
    tok = (token or '').strip()
    if not tok:
        return None
    try:
        data = gql('{ viewer { id name email } }', token=tok, timeout=(5, 10))
        v = data.get('viewer') or {}
        return (v.get('email') or v.get('name') or '').strip().lower() or None
    except Exception:
        return None


def fetch_change_authors(keys):
    return {}


def get_active_cycle_info():
    """Return active Linear cycle {'label', 'startsAt', 'endsAt'} (local YYYY-MM-DD), cached 600s."""
    def _fetch():
        try:
            data = gql('{ cycles(first: 10, filter: { isActive: { eq: true } }) { nodes { number name startsAt endsAt team { key } } } }')
            nodes = ((data.get('cycles') or {}).get('nodes') or [])
            candidates = [
                c for c in nodes
                if ((c.get('team') or {}).get('key') or '').upper() not in LINEAR_EXCLUDED_TEAMS
            ]
            # Prefer VA team cycle if present, else first active cycle
            candidates.sort(key=lambda c: (0 if ((c.get('team') or {}).get('key') or '').upper() == 'VA' else 1, c.get('endsAt') or ''))
            if candidates:
                c = candidates[0]
                lbl = str(c['name']) if c.get('name') else (f"Cycle {c['number']}" if c.get('number') is not None else 'Cycle hiện tại')
                return {
                    'label': lbl,
                    'startsAt': _to_local_str(c.get('startsAt'), '%Y-%m-%d'),
                    'endsAt': _to_local_str(c.get('endsAt'), '%Y-%m-%d'),
                }
        except Exception:
            pass
        return {'label': 'Cycle hiện tại', 'startsAt': '', 'endsAt': ''}

    now = time.time()
    with _CACHE_LOCK:
        entry = _CACHE.get('active_cycle_info')
        if entry and now - entry[0] < 600:
            return entry[1]
    val = _fetch()
    with _CACHE_LOCK:
        _CACHE['active_cycle_info'] = (time.time(), val)
    return val


def get_active_cycle_label():
    """Return active Linear cycle label (e.g. 'Cycle 21'), cached 600s."""
    return get_active_cycle_info().get('label', 'Cycle hiện tại')


_READ_PROP = 'qa-dashboard-read'
_DISMISS_LOCK = threading.Lock()


def _dismiss_local_path():
    from config import SCRIPT_DIR
    return SCRIPT_DIR / '.dismissed.json'


def _load_read_map():
    import json
    from config import KV_ENABLED
    if KV_ENABLED:
        from remote_store import remote_get
        val = remote_get(_READ_PROP) or {}
        d = val.get('dismissed') if isinstance(val, dict) else None
        if isinstance(d, dict) and all(isinstance(v, dict) for v in d.values()):
            return d
        return {}
    p = _dismiss_local_path()
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(d, dict):
                return d
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _save_read_map(read_map):
    import json
    from config import KV_ENABLED, atomic_write
    if KV_ENABLED:
        from remote_store import remote_put
        remote_put(_READ_PROP, {'dismissed': read_map, 'updated': datetime.now().isoformat()})
    else:
        atomic_write(_dismiss_local_path(), json.dumps(read_map, ensure_ascii=False))


def load_dismissed(user=None):
    key = (user or '').strip().lower() or 'local'
    with _DISMISS_LOCK:
        return dict(_load_read_map().get(key, {}))


def dismiss_activities(user, ids, prune_days=14):
    if not ids:
        return True
    key = (user or '').strip().lower() or 'local'
    with _DISMISS_LOCK:
        read_map = _load_read_map()
        bucket = dict(read_map.get(key) or {})
        now = datetime.now()
        stamp = now.isoformat()
        for i in ids:
            bucket[i] = stamp
        cutoff = (now - timedelta(days=prune_days)).isoformat()
        read_map[key] = {k: v for k, v in bucket.items() if v >= cutoff}
        _save_read_map(read_map)
    return True
