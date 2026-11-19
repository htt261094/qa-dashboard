"""Linear GraphQL write operations — transitions, comments, due date, edit, create issue."""
from linear_api import gql, canon_state


def _resolve_issue_uuid(key, pat):
    data = gql('query($id: String!) { issue(id: $id) { id identifier } }', {'id': key}, token=pat)
    iss = data.get('issue')
    return iss['id'] if iss else None


def get_transitions(key, pat):
    """Return (True, [{'id': state_id, 'to': canon_name, 'rawName': state_name}, ...])."""
    try:
        data = gql(
            """
            query($id: String!) {
              issue(id: $id) {
                id
                team {
                  states {
                    nodes { id name type position }
                  }
                }
              }
            }
            """,
            {'id': key},
            token=pat,
        )
        iss = data.get('issue')
        if not iss:
            return False, f'Không tìm thấy issue {key}'
        states = ((iss.get('team') or {}).get('states') or {}).get('nodes') or []
        states = sorted(states, key=lambda s: s.get('position', 0))
        out = [
            {'id': s['id'], 'to': s.get('name') or canon_state(s), 'rawName': s.get('name', '')}
            for s in states
        ]
        return True, out
    except Exception as e:
        return False, str(e)


def do_transition(key, transition_id, pat):
    try:
        issue_id = _resolve_issue_uuid(key, pat)
        if not issue_id:
            return False, f'Không tìm thấy issue {key}'
        data = gql(
            """
            mutation($id: String!, $stateId: String!) {
              issueUpdate(id: $id, input: { stateId: $stateId }) {
                success
              }
            }
            """,
            {'id': issue_id, 'stateId': str(transition_id)},
            token=pat,
        )
        ok = bool((data.get('issueUpdate') or {}).get('success'))
        return (True, 'OK') if ok else (False, 'Linear issueUpdate failed')
    except Exception as e:
        return False, str(e)


def get_issue_status(key, pat):
    try:
        data = gql(
            'query($id: String!) { issue(id: $id) { state { name type } } }',
            {'id': key},
            token=pat,
        )
        iss = data.get('issue')
        if not iss:
            return False, f'Không tìm thấy issue {key}'
        return True, canon_state(iss.get('state'))
    except Exception as e:
        return False, str(e)


def transition_to_status(key, target_name, pat):
    ok, trs = get_transitions(key, pat)
    if not ok:
        return False, trs
    want = (target_name or '').strip().lower()
    for t in trs:
        if (t.get('rawName') or '').lower() == want or (t.get('to') or '').lower() == want:
            return do_transition(key, t['id'], pat)
    return False, f'Không tìm thấy trạng thái "{target_name}" trên {key}'


def list_projects(query_str, pat, limit=50):
    """In Linear, issues belong to a Team — return Teams as project options."""
    try:
        data = gql('{ teams(first: 50) { nodes { id key name } } }', token=pat)
        nodes = ((data.get('teams') or {}).get('nodes') or [])
        q = (query_str or '').strip().lower()
        out = []
        for t in nodes:
            if q and q not in (t.get('key') or '').lower() and q not in (t.get('name') or '').lower():
                continue
            out.append({'key': t.get('key', ''), 'name': t.get('name', ''), 'id': t.get('id', '')})
            if len(out) >= limit:
                break
        return True, out
    except Exception as e:
        return False, str(e)


def create_issuetypes(team_key, pat):
    """Linear doesn't have Jira issue types; provide standard labels as types."""
    return True, [
        {'id': 'Task', 'name': 'Task', 'subtask': False},
        {'id': 'Bug', 'name': 'Bug', 'subtask': False},
        {'id': 'Improvement', 'name': 'Improvement', 'subtask': False},
    ]


def create_fields(team_key, type_id, pat):
    return True, [
        {
            'id': 'summary', 'name': 'Tiêu đề (Title)', 'required': True,
            'type': 'string', 'items': '', 'custom': '', 'system': 'summary',
            'allowedValues': [], 'hasDefault': False, 'supported': True,
        },
        {
            'id': 'description', 'name': 'Mô tả (Description)', 'required': False,
            'type': 'string', 'items': '', 'custom': '', 'system': 'description',
            'allowedValues': [], 'hasDefault': False, 'supported': True,
        },
        {
            'id': 'assignee', 'name': 'Người phụ trách (Assignee)', 'required': False,
            'type': 'user', 'items': '', 'custom': '', 'system': 'assignee',
            'allowedValues': [], 'hasDefault': False, 'supported': True,
        },
        {
            'id': 'priority', 'name': 'Độ ưu tiên (Priority)', 'required': False,
            'type': 'option', 'items': '', 'custom': '', 'system': 'priority',
            'allowedValues': [
                {'id': '1', 'label': 'Urgent'},
                {'id': '2', 'label': 'High'},
                {'id': '3', 'label': 'Medium'},
                {'id': '4', 'label': 'Low'},
                {'id': '0', 'label': 'No priority'},
            ],
            'hasDefault': True, 'supported': True,
        },
        {
            'id': 'duedate', 'name': 'Hạn (Due date)', 'required': False,
            'type': 'date', 'items': '', 'custom': '', 'system': 'duedate',
            'allowedValues': [], 'hasDefault': False, 'supported': True,
        },
    ]


def create_issue(team_key, type_id, raw_fields, parent_key=None, pat=None):
    try:
        teams_data = gql('{ teams(first: 50) { nodes { id key } } }', token=pat)
        teams = ((teams_data.get('teams') or {}).get('nodes') or [])
        team_id = next((t['id'] for t in teams if t['key'].upper() == (team_key or '').upper()), None)
        if not team_id:
            return False, f'Không tìm thấy team {team_key}'

        title = (raw_fields.get('summary') or '').strip()
        if not title:
            return False, 'Thiêu tiêu đề (summary)'

        inp = {'teamId': team_id, 'title': title}
        if raw_fields.get('description'):
            inp['description'] = str(raw_fields['description'])
        if raw_fields.get('duedate'):
            inp['dueDate'] = str(raw_fields['duedate'])
        if raw_fields.get('priority') not in (None, ''):
            p = raw_fields['priority']
            if isinstance(p, dict):
                p = p.get('id')
            try:
                inp['priority'] = int(p)
            except (TypeError, ValueError):
                pass
        if raw_fields.get('assignee'):
            asg = raw_fields['assignee']
            if isinstance(asg, dict):
                asg = asg.get('id') or asg.get('name')
            if asg:
                inp['assigneeId'] = str(asg)
        if parent_key:
            pid = _resolve_issue_uuid(parent_key, pat)
            if pid:
                inp['parentId'] = pid

        if type_id in ('Bug', 'Improvement'):
            lbl_data = gql('{ issueLabels(first: 100) { nodes { id name } } }', token=pat)
            lbls = ((lbl_data.get('issueLabels') or {}).get('nodes') or [])
            lid = next((l['id'] for l in lbls if l['name'].lower() == type_id.lower()), None)
            if lid:
                inp['labelIds'] = [lid]

        res = gql(
            """
            mutation($input: IssueCreateInput!) {
              issueCreate(input: $input) {
                success
                issue { id identifier url }
              }
            }
            """,
            {'input': inp},
            token=pat,
        )
        created = res.get('issueCreate') or {}
        if not created.get('success') or not created.get('issue'):
            return False, 'Linear issueCreate failed'
        return True, created['issue']['identifier']
    except Exception as e:
        return False, str(e)


def can_edit_duedate(key, pat):
    return True, True


def set_duedate(key, duedate, pat):
    try:
        issue_id = _resolve_issue_uuid(key, pat)
        if not issue_id:
            return False, f'Không tìm thấy issue {key}'
        res = gql(
            """
            mutation($id: String!, $dueDate: TimelessDate) {
              issueUpdate(id: $id, input: { dueDate: $dueDate }) {
                success
              }
            }
            """,
            {'id': issue_id, 'dueDate': duedate or None},
            token=pat,
        )
        ok = bool((res.get('issueUpdate') or {}).get('success'))
        return (True, 'OK') if ok else (False, 'Linear issueUpdate failed')
    except Exception as e:
        return False, str(e)


def get_editmeta_fields(key, pat):
    return True, {'summary', 'assignee', 'duedate', 'description'}


def update_issue(key, fields, pat):
    try:
        issue_id = _resolve_issue_uuid(key, pat)
        if not issue_id:
            return False, f'Không tìm thấy issue {key}'
        inp = {}
        if 'summary' in fields:
            inp['title'] = fields['summary']
        if 'description' in fields:
            inp['description'] = fields['description']
        if 'duedate' in fields:
            inp['dueDate'] = fields['duedate'] or None
        if 'assignee' in fields:
            asg = fields['assignee']
            if isinstance(asg, dict):
                asg = asg.get('id') or asg.get('accountId') or asg.get('name')
            inp['assigneeId'] = asg or None
        if not inp:
            return False, 'Không có trường hợp lệ để cập nhật'
        res = gql(
            """
            mutation($id: String!, $input: IssueUpdateInput!) {
              issueUpdate(id: $id, input: $input) {
                success
              }
            }
            """,
            {'id': issue_id, 'input': inp},
            token=pat,
        )
        ok = bool((res.get('issueUpdate') or {}).get('success'))
        return (True, 'OK') if ok else (False, 'Linear issueUpdate failed')
    except Exception as e:
        return False, str(e)


def add_comment(key, body, pat):
    try:
        issue_id = _resolve_issue_uuid(key, pat)
        if not issue_id:
            return False, f'Không tìm thấy issue {key}'
        res = gql(
            """
            mutation($issueId: String!, $body: String!) {
              commentCreate(input: { issueId: $issueId, body: $body }) {
                success
              }
            }
            """,
            {'issueId': issue_id, 'body': body},
            token=pat,
        )
        ok = bool((res.get('commentCreate') or {}).get('success'))
        return (True, 'OK') if ok else (False, 'Linear commentCreate failed')
    except Exception as e:
        return False, str(e)
