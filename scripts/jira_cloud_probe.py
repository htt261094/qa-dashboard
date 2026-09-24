"""Dò cấu hình Jira Cloud rồi đối chiếu với hằng số trong core/config.py (issue #197, Decision #94).

Chạy lại mỗi khi IT đổi cấu hình Jira (chuyển tiếp project, gộp field "Start date (migrated)",
đổi option Department/BK Team...). CHỈ ĐỌC — không tạo/sửa gì trên Jira. Không in token.

    .venv\\Scripts\\python.exe scripts\\jira_cloud_probe.py            # mọi project
    .venv\\Scripts\\python.exe scripts\\jira_cloud_probe.py DA52H26 SIT1   # chỉ vài project

Mục in ra:
  1. Tài khoản của token chung (/myself).
  2. accountId của roster (USERS + Hiền) — so với cache .jira_accounts.json.
  3. Field custom theo tên -> id, đánh dấu ✗ nếu lệch config.
  4. Issue type Sub-task / Task-PTSP.
  5. Tên status liên quan workflow QA.
  6. Từng project: type sub-task, field bắt buộc, field config thiếu trên màn tạo, option IT / IT-QA.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'core'))

import requests  # noqa: E402

import config  # noqa: E402
from config import JIRA_URL, USERS  # noqa: E402
from jira_cloud import auth_headers, account_id, MAIL_DOMAIN  # noqa: E402

H = auth_headers()
TIMEOUT = 30

# (tên field trên Jira Cloud, hằng số config tương ứng)
FIELDS = [
    ('Start date (migrated)', 'START_DATE_FIELD'),
    ('Leader', 'LEADER_FIELD'),
    ('Department', 'DEPARTMENT_FIELD'),
    ('BK Team', 'BK_TEAM_FIELD'),
    ('Leader đánh giá (Số)', 'LEADER_EVAL_NUM_FIELD'),
    ('Leader đánh giá (text)', 'LEADER_EVAL_TEXT_FIELD'),
]
QA_STATUSES = ('to do', 'in progress', 'pending', 'done', 'cancelled', 'canceled',
               config.READY_PROD_STATUS.lower())


def get(path, **params):
    """GET JSON; lỗi mạng/HTTP -> (None, mô tả) thay vì raise để chạy tiếp project khác."""
    err = ''
    for _ in range(3):                    # mạng tới Atlassian đôi khi ConnectTimeout -> thử lại
        try:
            r = requests.get(f'{JIRA_URL}{path}', headers=H, params=params or None, timeout=TIMEOUT)
            break
        except requests.RequestException as e:
            err = type(e).__name__
    else:
        return None, f'{err} (lỗi mạng, chạy lại sau)'
    if r.status_code == 404:
        return None, 'HTTP 404 (không có hoặc thiếu quyền)'
    if r.status_code != 200:
        return None, f'HTTP {r.status_code}'
    try:
        return r.json(), ''
    except ValueError:
        return None, 'không phải JSON'


def mark(ok):
    return '✓' if ok else '✗'


def section(title):
    print(f'\n===== {title} =====')


def main(only_projects):
    print(f'Jira: {JIRA_URL}')

    section('1. Token chung')
    me, err = get('/rest/api/2/myself')
    if not me:
        print(f'✗ /myself lỗi: {err} — kiểm tra JIRA_EMAIL / JIRA_API_TOKEN trong .env')
        return 1
    print(f"{me.get('emailAddress')} · {me.get('displayName')} · {me.get('accountId')}")

    section('2. accountId roster')
    for u in list(USERS) + ['hiennt19']:
        acc = account_id(u)
        print(f'{mark(bool(acc))} {u:10} {acc or "KHÔNG resolve được (" + u + "@" + MAIL_DOMAIN + ") — khai JIRA_ACCOUNT_IDS"}')

    section('3. Field custom (tên -> id) so với config')
    fields, err = get('/rest/api/2/field')
    by_name = {}
    for f in fields or []:
        if f.get('custom'):
            by_name.setdefault(f['name'], []).append(f['id'])
    if not fields:
        print(f'✗ /field lỗi: {err}')
    for name, const in FIELDS:
        cfg = getattr(config, const)
        ids = by_name.get(name, [])
        print(f'{mark(cfg in ids)} {const:24} config={cfg:18} Jira "{name}" = {ids or "KHÔNG CÓ"}')
    # field "Start date" gốc của Cloud — nếu IT gộp data về đây thì phải đổi START_DATE_FIELD
    print(f'  (tham khảo) "Start date" gốc Cloud = {by_name.get("Start date", [])}')

    section('4. Issue type')
    types, err = get('/rest/api/2/issuetype')
    for t in types or []:
        if t['name'] in ('Sub-task', 'Subtask', 'Task-PTSP'):
            tag = ''
            if t['id'] == config.SUBTASK_TYPE_ID:
                tag = '  <- SUBTASK_TYPE_ID'
            elif t['id'] == config.TASK_PTSP_TYPE_ID:
                tag = '  <- TASK_PTSP_TYPE_ID'
            print(f"  {t['id']:6} {t['name']:10} subtask={t.get('subtask')}{tag}")
    ptsp = [t['id'] for t in types or [] if t['name'] == 'Task-PTSP']
    print(f'{mark(config.TASK_PTSP_TYPE_ID in ptsp)} TASK_PTSP_TYPE_ID={config.TASK_PTSP_TYPE_ID}')

    section('5. Status workflow QA (app chuẩn hoá về tên DC qua canon_status)')
    sts, err = get('/rest/api/2/status')
    for s in sorted({(s['name'], s['statusCategory']['key']) for s in sts or []}):
        if s[0].lower() in QA_STATUSES:
            print(f'  {s[0]:18} {s[1]}')

    section('6. Createmeta sub-task theo project')
    projs, err = get('/rest/api/2/project/search', maxResults=200)
    keys = [p['key'] for p in (projs or {}).get('values', [])]
    if only_projects:
        keys = [k for k in keys if k in only_projects] or list(only_projects)
    want = {getattr(config, c) for _, c in FIELDS if c not in ('LEADER_EVAL_NUM_FIELD', 'LEADER_EVAL_TEXT_FIELD')}
    ok_projects = []
    for pk in keys:
        meta, err = get(f'/rest/api/2/issue/createmeta/{pk}/issuetypes', maxResults=100)
        if not meta:
            print(f'✗ {pk:10} createmeta lỗi: {err}')
            continue
        tlist = meta.get('issueTypes') or meta.get('values') or []
        subs = [(t['id'], t['name']) for t in tlist if t.get('subtask')]
        if not any(t[0] == config.SUBTASK_TYPE_ID for t in subs):
            print(f'✗ {pk:10} KHÔNG có sub-task {config.SUBTASK_TYPE_ID}, chỉ có {subs}')
            continue
        fm, err = get(f'/rest/api/2/issue/createmeta/{pk}/issuetypes/{config.SUBTASK_TYPE_ID}', maxResults=200)
        if not fm:
            print(f'✗ {pk:10} createmeta sub-task lỗi: {err}')
            continue
        fdict = {x['fieldId']: x for x in (fm.get('fields') or fm.get('values') or [])}
        req = sorted(k for k, x in fdict.items() if x.get('required'))
        missing = sorted(want - set(fdict))

        def opt(fid, value):
            return [a.get('id') for a in fdict.get(fid, {}).get('allowedValues', []) if a.get('value') == value]
        it = opt(config.DEPARTMENT_FIELD, 'IT')
        itqa = opt(config.BK_TEAM_FIELD, 'IT-QA')
        opt_ok = (config.SUBTASK_DEPARTMENT_ID in it) and (config.SUBTASK_BK_TEAM_ID in itqa)
        # App điền được: summary/parent/project/issuetype/duedate/start date/department/bk team
        fillable = {'summary', 'parent', 'project', 'issuetype', 'duedate', 'reporter', 'assignee'} | want
        unfillable = sorted(set(req) - fillable)
        good = not missing and opt_ok and not unfillable
        if good:
            ok_projects.append(pk)
        print(f'{mark(good)} {pk:10} bắt buộc={req}')
        if missing:
            print(f'             thiếu trên màn tạo (app đang gửi -> Jira 400): {missing}')
        if not opt_ok:
            print(f'             option IT={it} (config {config.SUBTASK_DEPARTMENT_ID}) · '
                  f'IT-QA={itqa} (config {config.SUBTASK_BK_TEAM_ID})')
        if unfillable:
            print(f'             bắt buộc nhưng app KHÔNG điền: {unfillable}')

    print(f'\nTạo sub-task QA chạy được ở {len(ok_projects)}/{len(keys)} project: {", ".join(ok_projects) or "—"}')
    return 0


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass
    sys.exit(main(set(sys.argv[1:])))
