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
from jira_cloud import (basic_auth, split_cred, canon_status,
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
