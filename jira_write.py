"""Ghi lên Jira NHÂN DANH từng QA — dùng PAT cá nhân của họ (KHÔNG dùng PAT chung),
nên lịch sử Jira ghi đúng tên người thao tác (attribution).

Tách khỏi jira_api (vốn đọc bằng PAT chung + session chia sẻ): mỗi call ở đây gắn
PAT riêng truyền vào. PAT luôn redact trong mọi thông báo lỗi (OPSEC).

Layer: config -> (this). Caller (handler) tự lấy PAT qua pat_store rồi truyền vào.
"""
import requests

from config import JIRA_URL

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
