"""Ghi lên Jira NHÂN DANH từng QA — dùng PAT cá nhân của họ (KHÔNG dùng PAT chung),
nên lịch sử Jira ghi đúng tên người thao tác (attribution).

Tách khỏi jira_api (vốn đọc bằng PAT chung + session chia sẻ): mỗi call ở đây gắn
PAT riêng truyền vào. PAT luôn redact trong mọi thông báo lỗi (OPSEC).

Layer: config -> (this). Caller (handler) tự lấy PAT qua pat_store rồi truyền vào.
"""
import requests

from config import (JIRA_URL, SUBTASK_TYPE_ID, TASK_PTSP_TYPE_ID,
                    START_DATE_FIELD, LEADER_FIELD,
                    LEADER_EVAL_NUM_FIELD, LEADER_EVAL_TEXT_FIELD)

_TIMEOUT = 20


def _err_for(status, pat):
    """Thông báo tiếng Việt theo HTTP status của thao tác ghi."""
    if status == 401:
        return 'PAT của bạn sai hoặc đã hết hạn — vào Cài đặt dán lại.'
    if status == 403:
        return 'PAT không đủ quyền thực hiện thao tác này trên Jira.'
    if status == 404:
        return 'Không tìm thấy task (hoặc bạn không có quyền xem).'
    return f'Jira trả lỗi {status}.'


def _redact(msg, pat):
    return msg.replace(pat, '<REDACTED>') if pat and isinstance(msg, str) else msg


def _headers(pat):
    return {'Authorization': f'Bearer {pat}', 'Accept': 'application/json',
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
            out.append({'id': str(t.get('id')), 'to': to})
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


def create_subtask(parent_key, summary, duedate, start_date,
                   assignee=None, leader=None, pat=None):
    """Tạo Sub-task QA dưới 1 Task-PTSP, NHÂN DANH chủ PAT (reporter = người đăng nhập).

    Field bắt buộc (theo createmeta): summary, duedate, start_date (customfield_10208).
    assignee/leader optional (user-picker -> {'name': username}).
    Trả (True, '<KEY mới>') hoặc (False, '<thông báo lỗi tiếng Việt>')."""
    summary = (summary or '').strip()
    if not summary:
        return False, 'Thiếu tiêu đề sub-task.'
    if not duedate:
        return False, 'Thiếu hạn chót (Due date).'
    if not start_date:
        return False, 'Thiếu ngày bắt đầu (Start date).'
    # 1. Lấy project key từ parent + verify parent đúng là Task-PTSP (không tin client)
    try:
        r = requests.get(f"{JIRA_URL}/rest/api/2/issue/{parent_key}",
                         headers=_headers(pat), params={'fields': 'project,issuetype'},
                         timeout=_TIMEOUT)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)
    if r.status_code != 200:
        return False, _err_for(r.status_code, pat)
    pf = r.json().get('fields', {})
    project_key = (pf.get('project') or {}).get('key')
    ptype = pf.get('issuetype') or {}
    if not project_key:
        return False, 'Không xác định được dự án của task cha.'
    if str(ptype.get('id')) != str(TASK_PTSP_TYPE_ID):
        return False, f'Task cha phải là Task-PTSP (đang là {ptype.get("name") or "?"}).'
    # 2. Build payload + tạo
    fields = {
        'project': {'key': project_key},
        'parent': {'key': parent_key},
        'issuetype': {'id': str(SUBTASK_TYPE_ID)},
        'summary': summary[:250],
        'duedate': duedate,
        START_DATE_FIELD: start_date,
    }
    if assignee:
        fields['assignee'] = {'name': assignee}
    if leader:
        fields[LEADER_FIELD] = {'name': leader}
    try:
        r = requests.post(f"{JIRA_URL}/rest/api/2/issue",
                          headers=_headers(pat), json={'fields': fields}, timeout=_TIMEOUT)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)
    if r.status_code in (200, 201):
        return True, r.json().get('key') or ''
    # Jira 400 -> trả lỗi field cụ thể (vd Leader không tồn tại, due sai định dạng)
    try:
        err = r.json()
        msgs = list((err.get('errors') or {}).values()) + (err.get('errorMessages') or [])
        if msgs:
            return False, _redact('; '.join(str(m) for m in msgs), pat)
    except ValueError:
        pass
    return False, _err_for(r.status_code, pat)


def add_comment(key, body, pat):
    """Thêm comment THẬT (ghi tên chủ PAT). Trả (ok, msg)."""
    body = (body or '').strip()
    if not body:
        return False, 'Comment rỗng.'
    try:
        r = requests.post(f"{JIRA_URL}/rest/api/2/issue/{key}/comment",
                          headers=_headers(pat), json={'body': body}, timeout=_TIMEOUT)
        if r.status_code in (200, 201):
            return True, 'Đã gửi comment lên Jira.'
        return False, _err_for(r.status_code, pat)
    except requests.RequestException as e:
        return False, _redact(f'Lỗi mạng: {e}', pat)


def batch_update_evaluations(keys, num_val, text_val, pat):
    """Cập nhật hàng loạt trường Đánh giá của Leader cho nhiều task.
    num_val (float hoặc None), text_val (str hoặc None). Trả (ok, msg)."""
    if not keys:
        return True, "Không có task nào được chọn."
    fields = {}
    if num_val is not None and str(num_val).strip() != '':
        try:
            fields[LEADER_EVAL_NUM_FIELD] = float(num_val)
        except ValueError:
            return False, "Điểm đánh giá phải là một số."
    if text_val is not None:
        fields[LEADER_EVAL_TEXT_FIELD] = str(text_val).strip()

    if not fields:
        return False, "Không có dữ liệu hợp lệ để cập nhật."

    errors = []
    success_count = 0
    from concurrent.futures import ThreadPoolExecutor, as_completed
    def _update(key):
        try:
            r = requests.put(f"{JIRA_URL}/rest/api/2/issue/{key}",
                             headers=_headers(pat), json={'fields': fields}, timeout=_TIMEOUT)
            if r.status_code in (200, 204):
                return key, True, None
            # Extract specific errors if any
            try:
                err = r.json()
                msgs = list((err.get('errors') or {}).values()) + (err.get('errorMessages') or [])
                if msgs:
                    return key, False, _redact('; '.join(str(m) for m in msgs), pat)
            except ValueError:
                pass
            return key, False, _err_for(r.status_code, pat)
        except requests.RequestException as e:
            return key, False, _redact(f'Lỗi mạng: {e}', pat)

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = [ex.submit(_update, k) for k in keys]
        for fut in as_completed(futs):
            key, ok, msg = fut.result()
            if ok:
                success_count += 1
            else:
                errors.append(f"{key}: {msg}")

    if errors:
        return False, f"Thành công {success_count}/{len(keys)}. Lỗi: " + "; ".join(errors[:3]) + ("..." if len(errors)>3 else "")
    return True, f"Đã cập nhật thành công {success_count} task."
