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
        return True, ((iss.get('state') or {}).get('name') or canon_state(iss.get('state'))).strip()
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
