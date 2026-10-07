"""Ghi lên Jira NHÂN DANH từng QA — dùng API token cá nhân của họ (KHÔNG dùng token chung),
nên lịch sử Jira ghi đúng tên người thao tác (attribution).

Tách khỏi jira_api (vốn đọc bằng token chung + session chia sẻ): mỗi call ở đây gắn
credential riêng truyền vào. Jira Cloud (#197): tham số `pat` giữ tên cũ cho caller nhưng giờ
là credential 'email:api_token' (Basic auth) do pat_store trả về. Luôn redact trong mọi thông
báo lỗi (OPSEC). User-picker ghi bằng accountId, mention '[~username]' -> '[~accountid:X]'.

Layer: config -> jira_cloud -> (this). Caller (handler) tự lấy credential qua pat_store.
"""
import re

import requests

from config import JIRA_URL
from jira_cloud import (basic_auth, split_cred, canon_status, user_ref,
                        mentions_to_accounts)

_TIMEOUT = 20


def _err_for(status, pat):
    """Thông báo tiếng Việt theo HTTP status của thao tác ghi."""
    if status == 401:
        return 'API token Jira của bạn sai hoặc đã hết hạn — vào Cài đặt dán lại.'
    if status == 403:
        return 'Tài khoản Jira của bạn không đủ quyền thực hiện thao tác này.'
    if status == 404:
        return 'Không tìm thấy task (hoặc bạn không có quyền xem).'
    return f'Jira trả lỗi {status}.'


def _redact(msg, pat):
    if not pat or not isinstance(msg, str):
        return msg
    _, token = split_cred(pat)
    for secret in (pat, token):
        if secret:
            msg = msg.replace(secret, '<REDACTED>')
    return msg


def _headers(pat):
    """`pat` = credential 'email:api_token' (Jira Cloud Basic auth, #197)."""
    email, token = split_cred(pat)
    return {'Authorization': basic_auth(email or '', token or ''), 'Accept': 'application/json',
            'Content-Type': 'application/json'}


def get_transitions(key, pat):
    """Các transition khả dụng của task NGAY LÚC NÀY (theo workflow Jira).
    Trả (True, [{'id','to'}]) hoặc (False, msg). `to` = tên status đích sẽ chuyển sang."""
    try:
        r = requests.get(f"{JIRA_URL}/rest/api/2/issue/{key}/transitions",
                         headers=_headers(pat), timeout=_TIMEOUT)
        if r.status_code != 200:
            return False, _err_for(r.status_code, pat)
        out = []
        for t in r.json().get('transitions', []):
            to = (t.get('to') or {}).get('name') or t.get('name') or '?'
            out.append({'id': str(t.get('id')), 'to': canon_status(to)})   # tên DC (#197)
        return True, out
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)


def do_transition(key, transition_id, pat):
    """Thực hiện chuyển status THẬT. Trả (ok, msg)."""
    try:
        r = requests.post(f"{JIRA_URL}/rest/api/2/issue/{key}/transitions",
                          headers=_headers(pat),
                          json={'transition': {'id': str(transition_id)}}, timeout=_TIMEOUT)
        if r.status_code in (200, 204):
            return True, 'Đã đổi status trên Jira.'
        if r.status_code == 400:
            return False, 'Transition không hợp lệ cho task này (workflow đã đổi). F5 thử lại.'
        return False, _err_for(r.status_code, pat)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)


def get_issue_status(key, pat):
    """Đọc status hiện tại qua GET /issue/{key} (Decision #90).

    KHÔNG đi qua `/search` nên KHÔNG dính lag index Lucene -> ngay sau transition đã trả
    đúng status mới. Trả (ok, name)."""
    try:
        r = requests.get(f"{JIRA_URL}/rest/api/2/issue/{key}", headers=_headers(pat),
                         params={'fields': 'status'}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return False, _err_for(r.status_code, pat)
        name = ((r.json().get('fields') or {}).get('status') or {}).get('name') or ''
        return True, canon_status(name)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)


def transition_to_status(key, target_name, pat):
    """Đổi sang status có TÊN = target_name, CHỈ KHI nó nằm trong transition khả dụng
    (workflow Jira). Không khớp -> (False, msg liệt kê status cho phép). Đây là điểm
    enforce 'chọn status có trên Jira mới đổi Jira'."""
    ok, data = get_transitions(key, pat)
    if not ok:
        return False, data
    tname = (target_name or '').strip().lower()
    match = next((t for t in data if t['to'].strip().lower() == tname), None)
    if not match:
        avail = ', '.join(t['to'] for t in data) or '(không có)'
        return False, f'Không chuyển sang "{target_name}" — không nằm trong bước kế tiếp của workflow. Cho phép: {avail}.'
    return do_transition(key, match['id'], pat)


# ===== TẠO TASK ĐỘC LẬP — createmeta-động (Decision #113) =====
# Đọc + ghi đều bằng API token CÁ NHÂN (PAT): field bắt buộc + quyền tạo khớp đúng cái user
# thật sẽ tạo được (token chung có thể khác quyền). Form render field theo đúng createmeta của
# từng project+issuetype, nên "mở" như dialog Create của Jira thay vì bộ field cố định QA.

# Widget FE dựng được -> field hiện trên form. Loại dưới đây không có widget (binary/phức tạp)
# -> ẩn, KHÔNG gửi: nếu Jira bắt buộc thì POST sẽ 400 với tên field cụ thể (báo rõ cho user).
_UNSUPPORTED_SCHEMA = {'attachment', 'issuelink', 'issuelinks', 'timetracking', 'worklog',
                       'comments-page', 'sd-approvals', 'any'}
_UNSUPPORTED_ARRAY_ITEMS = {'json', 'any', 'attachment', 'worklog'}


def _createmeta(project_key, pat, type_id=None, with_fields=False):
    """Đọc createmeta kiểu LEGACY (`?projectKeys=&expand=projects.issuetypes[.fields]`).

    Instance baokim.atlassian.net KHÔNG bật endpoint granular mới
    (`/createmeta/{p}/issuetypes/{id}` trả 404 'No endpoint') nên dùng endpoint classic này —
    vẫn 200 và trả đủ issuetypes + fields. Trả (True, project_dict) hoặc (False, msg)."""
    expand = 'projects.issuetypes.fields' if with_fields else 'projects.issuetypes'
    params = {'projectKeys': project_key, 'expand': expand}
    if type_id:
        params['issuetypeIds'] = str(type_id)
    try:
        r = requests.get(f"{JIRA_URL}/rest/api/2/issue/createmeta",
                         headers=_headers(pat), params=params, timeout=_TIMEOUT)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)
    if r.status_code != 200:
        return False, _err_for(r.status_code, pat)
    projs = (r.json() or {}).get('projects') or []
    if not projs:
        return False, 'Bạn không có quyền tạo issue trong dự án này (hoặc dự án không tồn tại).'
    return True, projs[0]


def list_projects(query, pat, limit=50):
    """Project user (theo PAT) thấy + tạo được issue, cho dropdown chọn dự án.
    Trả (True, [{key, name, id}]) hoặc (False, msg)."""
    try:
        r = requests.get(f"{JIRA_URL}/rest/api/2/project/search", headers=_headers(pat),
                         params={'query': (query or '').strip(), 'maxResults': limit,
                                 'orderBy': 'name', 'action': 'create'}, timeout=_TIMEOUT)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)
    if r.status_code != 200:
        return False, _err_for(r.status_code, pat)
    out = []
    for p in (r.json() or {}).get('values') or []:
        out.append({'key': p.get('key') or '', 'name': p.get('name') or '',
                    'id': str(p.get('id') or '')})
    return True, out


def create_issuetypes(project_key, pat):
    """Issue type user được tạo trong project này (createmeta). Trả (True, [{id,name,subtask}])."""
    ok, proj = _createmeta(project_key, pat)
    if not ok:
        return False, proj
    out = []
    for t in proj.get('issuetypes') or []:
        out.append({'id': str(t.get('id') or ''), 'name': t.get('name') or '',
                    'subtask': bool(t.get('subtask'))})
    return True, out


def _norm_allowed(av):
    """Chuẩn hoá 1 allowedValue -> {id, label}. Jira dùng key khác nhau theo loại field."""
    label = (av.get('value') or av.get('name') or av.get('label')
             or av.get('key') or '')
    return {'id': str(av.get('id') or av.get('key') or av.get('value') or ''),
            'label': str(label)}


def create_fields(project_key, type_id, pat):
    """Field trên màn Create của (project, issuetype) — đúng tập Jira hiện, kèm required +
    schema để FE render widget. Loại field không có widget -> gắn supported=False (FE ẩn).
    Trả (True, [field_meta...]) hoặc (False, msg). field_meta:
      {id, name, required, type, items, custom, system, allowedValues:[{id,label}], hasDefault}."""
    ok, proj = _createmeta(project_key, pat, type_id=type_id, with_fields=True)
    if not ok:
        return False, proj
    its = proj.get('issuetypes') or []
    if not its:
        return False, 'Loại task không hợp lệ cho dự án này.'
    fmap = its[0].get('fields') or {}   # {fieldId: meta}
    out = []
    for fid, f in fmap.items():
        sc = f.get('schema') or {}
        system = sc.get('system') or ''
        ftype = sc.get('type') or ''
        items = sc.get('items') or ''
        # project/issuetype đã chọn ở trên; reporter = chủ token -> không đưa vào form.
        if system in ('project', 'issuetype', 'reporter'):
            continue
        supported = (ftype not in _UNSUPPORTED_SCHEMA
                     and not (ftype == 'array' and items in _UNSUPPORTED_ARRAY_ITEMS))
        # parent luôn giữ (FE render ô Task cha riêng) dù schema là issuelink.
        if system == 'parent':
            supported = True
        out.append({
            'id': fid,
            'name': f.get('name') or fid,
            'required': bool(f.get('required')),
            'type': ftype,
            'items': sc.get('items') or '',
            'custom': bool(sc.get('custom')),
            'system': system,
            'allowedValues': [_norm_allowed(a) for a in (f.get('allowedValues') or [])],
            'hasDefault': bool(f.get('hasDefaultValue')),
            'supported': supported,
        })
    return True, out


def _coerce_field(meta, value):
    """Ép giá trị client gửi về shape payload Jira theo schema. Trả (ok, coerced|msg).
    coerced=None nghĩa 'bỏ trống' (không gửi field)."""
    t = meta.get('type') or ''
    items = meta.get('items') or ''
    if value is None or value == '' or value == []:
        return True, None
    if t == 'string':
        return True, str(value)
    if t == 'number':
        try:
            s = str(value)
            return True, (float(s) if '.' in s else int(s))
        except (TypeError, ValueError):
            return False, f'"{meta.get("name")}" phải là số.'
    if t == 'date':
        return True, str(value)[:10]
    if t == 'datetime':
        return True, str(value)
    if t == 'user':
        ref = user_ref(str(value))
        if not ref:
            return False, f'Không tìm thấy tài khoản Jira cho "{meta.get("name")}".'
        return True, ref
    if t in ('option', 'priority', 'resolution', 'securitylevel', 'version',
             'component', 'group', 'option-with-child'):
        if t == 'group':
            return True, {'name': str(value)}
        return True, {'id': str(value)}
    if t == 'array':
        vals = value if isinstance(value, list) else [value]
        vals = [v for v in vals if v not in (None, '')]
        if not vals:
            return True, None
        if items == 'user':
            refs = []
            for v in vals:
                ref = user_ref(str(v))
                if not ref:
                    return False, f'Không tìm thấy tài khoản Jira cho "{meta.get("name")}".'
                refs.append(ref)
            return True, refs
        if items == 'group':
            return True, [{'name': str(v)} for v in vals]
        if items in ('option', 'version', 'component'):
            return True, [{'id': str(v)} for v in vals]
        if items == 'string':   # labels và tương tự
            return True, [str(v) for v in vals]
        return True, [str(v) for v in vals]
    # loại khác (vd string đặc biệt) -> gửi nguyên
    return True, value


def create_issue(project_key, type_id, raw_fields, parent_key=None, pat=None):
    """Tạo issue bất kỳ (project + issuetype + field động theo createmeta), NHÂN DANH chủ PAT.

    `raw_fields` = {fieldId: value} client gửi. Fetch lại createmeta để biết schema + required,
    ép từng field về shape Jira, validate required, rồi POST. parent_key (optional) cho subtask.
    Trả (True, '<KEY>') hoặc (False, '<lỗi tiếng Việt>')."""
    if not project_key or not type_id:
        return False, 'Thiếu dự án hoặc loại task.'
    ok, metas = create_fields(project_key, type_id, pat)
    if not ok:
        return False, metas
    fields = {'project': {'key': project_key}, 'issuetype': {'id': str(type_id)}}
    raw_fields = raw_fields if isinstance(raw_fields, dict) else {}
    missing, parent_meta = [], None
    for m in metas:
        fid = m['id']
        # parent (sub-task) xử lý riêng ở dưới qua parent_key — KHÔNG đi qua vòng coerce.
        if fid == 'parent' or m.get('system') == 'parent':
            parent_meta = m
            continue
        if not m.get('supported'):
            continue
        c_ok, coerced = _coerce_field(m, raw_fields.get(fid))
        if not c_ok:
            return False, coerced
        if coerced is None:
            # required mà trống + không có default -> chặn sớm (báo đẹp thay vì 400 trần)
            if m.get('required') and not m.get('hasDefault'):
                missing.append(m.get('name') or fid)
            continue
        if fid == 'summary' and isinstance(coerced, str):
            coerced = coerced[:250]
        fields[fid] = coerced
    if missing:
        return False, 'Thiếu field bắt buộc: ' + ', '.join(missing) + '.'
    if parent_key:
        if parent_meta:
            fields['parent'] = {'key': parent_key}
        # type không nhận parent -> bỏ qua parent_key, không gây 400
    elif parent_meta and parent_meta.get('required') and not parent_meta.get('hasDefault'):
        return False, 'Loại task này là sub-task — hãy chọn task cha.'
    try:
        r = requests.post(f"{JIRA_URL}/rest/api/2/issue",
                          headers=_headers(pat), json={'fields': fields}, timeout=_TIMEOUT)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)
    if r.status_code in (200, 201):
        return True, r.json().get('key') or ''
    try:
        err = r.json()
        msgs = list((err.get('errors') or {}).values()) + (err.get('errorMessages') or [])
        if msgs:
            return False, _redact('; '.join(str(m) for m in msgs), pat)
    except ValueError:
        pass
    return False, _err_for(r.status_code, pat)


def can_edit_duedate(key, pat):
    """Task này người dùng (theo PAT cá nhân) CÓ được sửa Due date không?

    Dùng /editmeta — Jira trả đúng tập field mà CHÍNH user hiện tại được sửa trên issue này
    (đã tính permission Edit Issues + cấu hình field/workflow). 'duedate' có mặt = được sửa.
    Trả (True, bool) hoặc (False, msg). Đây là gate cho UI; enforce thật vẫn ở set_duedate."""
    try:
        r = requests.get(f"{JIRA_URL}/rest/api/2/issue/{key}/editmeta",
                         headers=_headers(pat), timeout=_TIMEOUT)
        if r.status_code != 200:
            return False, _err_for(r.status_code, pat)
        fields = (r.json() or {}).get('fields') or {}
        return True, ('duedate' in fields)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)


def set_duedate(key, duedate, pat):
    """Đổi Due date THẬT bằng PAT cá nhân -> Jira tự enforce quyền (không đủ quyền = 403/400).
    duedate = 'YYYY-MM-DD' để đặt, '' hoặc None để xoá hạn. Trả (ok, msg)."""
    duedate = (duedate or '').strip()
    if duedate and not re.match(r'^\d{4}-\d{2}-\d{2}$', duedate):
        return False, 'Ngày phải đúng định dạng YYYY-MM-DD.'
    try:
        r = requests.put(f"{JIRA_URL}/rest/api/2/issue/{key}",
                         headers=_headers(pat),
                         json={'fields': {'duedate': duedate or None}}, timeout=_TIMEOUT)
        if r.status_code in (200, 204):
            return True, ('Đã đổi hạn trên Jira.' if duedate else 'Đã xoá hạn trên Jira.')
        # 400 -> field lỗi cụ thể (vd không có quyền sửa field, giá trị sai)
        if r.status_code == 400:
            try:
                err = r.json()
                msgs = list((err.get('errors') or {}).values()) + (err.get('errorMessages') or [])
                if msgs:
                    return False, _redact('; '.join(str(m) for m in msgs), pat)
            except ValueError:
                pass
            return False, 'Jira từ chối cập nhật hạn (400).'
        return False, _err_for(r.status_code, pat)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)


def get_editmeta_fields(key, pat):
    """Tập field mà CHÍNH user (theo PAT cá nhân) được sửa trên issue này (theo /editmeta —
    đã tính Edit Issues permission + field/workflow config). Trả (True, set(field_ids))
    hoặc (False, msg). Gate cho UI form sửa; enforce thật vẫn ở update_issue."""
    try:
        r = requests.get(f"{JIRA_URL}/rest/api/2/issue/{key}/editmeta",
                         headers=_headers(pat), timeout=_TIMEOUT)
        if r.status_code != 200:
            return False, _err_for(r.status_code, pat)
        fields = (r.json() or {}).get('fields') or {}
        return True, set(fields.keys())
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)


def update_issue(key, fields, pat):
    """PUT cập nhật field issue bằng PAT cá nhân -> Jira tự enforce quyền (không đủ = 403/400).
    `fields` = dict field-id -> value đã build sẵn (summary/assignee/duedate...). Trả (ok, msg)."""
    if not fields:
        return False, 'Không có gì để cập nhật.'
    try:
        r = requests.put(f"{JIRA_URL}/rest/api/2/issue/{key}",
                         headers=_headers(pat), json={'fields': fields}, timeout=_TIMEOUT)
        if r.status_code in (200, 204):
            return True, 'Đã cập nhật task trên Jira.'
        if r.status_code == 400:
            try:
                err = r.json()
                msgs = list((err.get('errors') or {}).values()) + (err.get('errorMessages') or [])
                if msgs:
                    return False, _redact('; '.join(str(m) for m in msgs), pat)
            except ValueError:
                pass
            return False, 'Jira từ chối cập nhật (400).'
        return False, _err_for(r.status_code, pat)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)


def add_comment(key, body, pat):
    """Thêm comment THẬT (ghi tên chủ token). Trả (ok, msg)."""
    body = (body or '').strip()
    if not body:
        return False, 'Comment rỗng.'
    try:
        r = requests.post(f"{JIRA_URL}/rest/api/2/issue/{key}/comment",
                          headers=_headers(pat), json={'body': mentions_to_accounts(body)},
                          timeout=_TIMEOUT)
        if r.status_code in (200, 201):
            return True, 'Đã gửi comment lên Jira.'
        return False, _err_for(r.status_code, pat)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)
