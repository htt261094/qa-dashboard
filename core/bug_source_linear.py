"""Nguồn Bug Log từ Linear (prefix [Bug], bỏ team VC, chia theo QA Thuyết, Nhàn & Thành)."""
from config import (
    BUG_LOG_LINEAR_ENABLED, LINEAR_TEAM_KEYS, LINEAR_EXCLUDED_TEAMS,
    normalize_tracked_dev,
)
from linear_api import gql


_SEV_MAP = {
    'sev:blocker': 'Blocker',
    'sev:critical': 'Critical',
    'sev:major': 'High',
    'sev:minor': 'Medium',
    'sev:cosmetic': 'Low',
}


def _bug_lifecycle(state):
    if not state:
        return 'New'
    stype = (state.get('type') or '').lower()
    sname = (state.get('name') or '').strip().lower()
    if stype == 'completed':
        return 'Closed'
    if stype in ('canceled', 'cancelled', 'duplicate'):
        return 'Rejected'
    if stype == 'started':
        return 'Fixing'
    if 'reopen' in sname:
        return 'Reopen'
    return 'New'


def _sprint_state(cycle):
    if not cycle:
        return ''
    if cycle.get('completedAt'):
        return 'closed'
    if cycle.get('startsAt') and cycle.get('endsAt'):
        return 'active'
    return 'future'


_TRACKED_QA = ('Thuyết', 'Nhàn', 'Thành')


def _qa_person(labels, creator):
    """Map QA owner to 'Thuyết', 'Nhàn' or 'Thành' (from qa:* label or creator), else creator displayName."""
    for lb in labels:
        low = lb.lower()
        if low.startswith('qa:'):
            who = low.split(':', 1)[1].strip()
            if 'thuyet' in who or 'thuyết' in who:
                return 'Thuyết'
            if 'nhan' in who or 'nhàn' in who:
                return 'Nhàn'
            if 'thanh' in who or 'thành' in who:
                return 'Thành'
            return lb.split(':', 1)[1].strip()
    cr = creator or {}
    raw = ' '.join([
        (cr.get('displayName') or ''),
        (cr.get('name') or ''),
        (cr.get('email') or ''),
    ]).lower()
    if 'thuyet' in raw or 'thuyết' in raw:
        return 'Thuyết'
    if 'nhan' in raw or 'nhàn' in raw:
        return 'Nhàn'
    if 'thanh' in raw or 'thành' in raw:
        return 'Thành'
    return (cr.get('displayName') or cr.get('name') or '').strip()


def _issue_to_bug(n):
    ident = n.get('identifier') or ''
    team_key = (n.get('team') or {}).get('key') or ''
    bug_no = ident.split('-', 1)[1] if '-' in ident else ident
    labels = [((lb.get('name') or '').strip()) for lb in ((n.get('labels') or {}).get('nodes') or [])]

    severity = ''
    caused_by = ''
    has_bug_label = False
    has_caused_by = False
    reopen_count = 0
    for lb in labels:
        low = lb.lower()
        if low == 'bug':
            has_bug_label = True
        if low in _SEV_MAP:
            severity = _SEV_MAP[low]
        elif low.startswith('caused-by:'):
            has_caused_by = True
            caused_by = lb.split(':', 1)[1].strip()
        elif low == 'reopen' or low.startswith('reopen:'):
            reopen_count += 1

    qa_pic = _qa_person(labels, n.get('creator'))
    asg = n.get('assignee') or {}
    raw_dev = (asg.get('displayName') or asg.get('name') or caused_by or '').strip()
    dev_pic = normalize_tracked_dev(raw_dev, asg.get('email') or '')

    created = (n.get('createdAt') or '')[:10]
    updated = (n.get('updatedAt') or '')[:10]
    month = created[:7] if len(created) >= 7 else ''

    state = n.get('state') or {}
    cycle = n.get('cycle') or {}
    parent = n.get('parent') or {}
    tasks = [parent['identifier']] if parent.get('identifier') else []

    return {
        'key': ident,
        'url': n.get('url') or '',
        'project': team_key,
        'service': '',
        'feature': (n.get('project') or {}).get('name') or '',
        'bug_no': bug_no,
        'summary': n.get('title') or '',
        'status': _bug_lifecycle(state),
        'status_raw': state.get('name') or '',
        'severity': severity,
        'created': created,
        'updated': updated,
        'month': month,
        'qa_pic': qa_pic,
        'dev_pic': dev_pic,
        'screenshot_urls': [],
        'note': '',
        'expected': '',
        'handle_time': '',
        'reopen_count': reopen_count,
        'tasks': tasks,
        'labels': labels,
        'has_bug_label': has_bug_label,
        'has_caused_by': has_caused_by,
        'caused_by': caused_by,
        'sprint_state': _sprint_state(cycle),
        'sprint': cycle.get('name') or (f"Cycle {cycle.get('number')}" if cycle.get('number') else ''),
        'cycle_starts_at': (cycle.get('startsAt') or '')[:10],
    }


def scan_source(src):
    if not BUG_LOG_LINEAR_ENABLED:
        return {'bugs': [], 'unmapped': [], 'meta': {'count': 0, 'query': 'disabled'}, 'pending': False, 'error': None}

    flt = {
        'or': [
            {'title': {'containsIgnoreCase': '[Bug]'}},
            {'labels': {'some': {'name': {'eqIgnoreCase': 'Bug'}}}},
        ]
    }
    if LINEAR_TEAM_KEYS:
        flt['team'] = {'key': {'in': LINEAR_TEAM_KEYS}}
    elif LINEAR_EXCLUDED_TEAMS:
        flt['team'] = {'key': {'nin': LINEAR_EXCLUDED_TEAMS}}

    gql_q = """
    query BugIssues($first: Int!, $after: String, $filter: IssueFilter) {
      issues(first: $first, after: $after, orderBy: updatedAt, filter: $filter) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          identifier
          title
          createdAt
          updatedAt
          url
          state { name type }
          team { key name }
          project { id name }
          assignee { name displayName email }
          creator { name displayName email }
          parent { identifier }
          cycle { number name startsAt endsAt completedAt }
          labels(first: 20) { nodes { name } }
        }
      }
    }
    """
    bugs = []
    after = None
    try:
        for _ in range(10):  # up to 1000 bugs
            data = gql(gql_q, {'first': 100, 'after': after, 'filter': flt})
            conn = data.get('issues') or {}
            nodes = conn.get('nodes') or []
            for n in nodes:
                tkey = ((n.get('team') or {}).get('key') or '').upper()
                if tkey in LINEAR_EXCLUDED_TEAMS:
                    continue
                title = (n.get('title') or '').lstrip().lower()
                lbls = [((lb.get('name') or '').strip().lower()) for lb in ((n.get('labels') or {}).get('nodes') or [])]
                if not (title.startswith('[bug]') or 'bug' in lbls):
                    continue
                b = _issue_to_bug(n)
                if b['qa_pic'] not in _TRACKED_QA or not b['dev_pic']:
                    continue
                bugs.append(b)
            pi = conn.get('pageInfo') or {}
            if not pi.get('hasNextPage') or not pi.get('endCursor'):
                break
            after = pi['endCursor']
        return {
            'bugs': bugs,
            'unmapped': [],
            'meta': {'count': len(bugs), 'query': 'prefix:[Bug]'},
            'pending': False,
            'error': None,
        }
    except Exception as e:
        return {
            'bugs': [],
            'unmapped': [],
            'meta': {'count': 0, 'query': 'prefix:[Bug]'},
            'pending': False,
            'error': str(e),
        }
