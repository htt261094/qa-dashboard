"""WriteMixin — ghi THẬT lên Jira bằng PAT cá nhân + nhãn nội bộ.

Tách từ qa_dashboard.py (issue #86 / B2). Zero behavior change: chỉ di chuyển định
nghĩa method, không đổi logic/route/output.

Gom các route ghi (Decision #20/#21/#22):
- `_handle_jira_write` — /jira-transitions · /do-transition · /add-comment (PAT cá nhân)
- `_handle_create_subtask` — /create-subtask (PAT cá nhân, reporter = người đăng nhập)
- `_post_set_custom_status` — /set-custom-status (nhãn nội bộ, không cần PAT)

Mixin dùng các helper dùng chung định nghĩa ở Handler (resolve qua MRO):
`self._user_email()`, `self._reply_json()`, `self._read_json_body()`, `self._json()`.

Layer rule: KHÔNG import qa_dashboard (tránh vòng import).
"""
import re
import json

from config import JIRA_URL
from pat_store import load_user_pat
from custom_status import set_custom_status, is_valid
from jira_write import (get_transitions, do_transition, add_comment, create_subtask,
                        can_edit_duedate, set_duedate)


class WriteMixin:
    def _handle_jira_write(self):
        """Transition / comment THẬT lên Jira bằng PAT cá nhân của người đăng nhập.
        Không có PAT -> từ chối (để KHÔNG ghi nhầm tên tài khoản chung)."""
        pat = load_user_pat(self._user_email())
        if not pat:
            self._reply_json(False, {'ok': False, 'code': 'no_pat',
                'msg': 'Bạn chưa cấu hình PAT. Vào ⚙ Cài đặt để thêm, rồi thử lại.'})
            return
        try:
            payload = self._read_json_body(20_000)
            if not isinstance(payload, dict):
                self._reply_json(False, {'ok': False, 'msg': 'Dữ liệu không hợp lệ.'})
                return
            key = payload.get('key')
            if not isinstance(key, str) or not key:
                self._reply_json(False, {'ok': False, 'msg': 'Thiếu key task.'})
                return
            if self.path == '/jira-transitions':
                # CHỈ trả các transition QA này thật sự đổi được (theo PAT + workflow).
                ok, data = get_transitions(key, pat)
                self._reply_json(ok, {'ok': True, 'transitions': data} if ok else {'ok': False, 'msg': data})
            elif self.path == '/do-transition':
                tid = payload.get('id')
                if not isinstance(tid, (str, int)) or str(tid) == '':
                    self._reply_json(False, {'ok': False, 'msg': 'Thiếu transition id.'})
                    return
                ok, msg = do_transition(key, tid, pat)
                self._reply_json(ok, {'ok': ok, 'msg': msg})
            elif self.path == '/duedate-perm':
                # UI gate: task này người đăng nhập có quyền sửa Due date trên Jira không?
                ok, res = can_edit_duedate(key, pat)
                self._reply_json(ok, {'ok': True, 'canEdit': bool(res)} if ok
                                 else {'ok': False, 'msg': res})
            elif self.path == '/set-duedate':
                due = payload.get('duedate')
                if due is not None and not isinstance(due, str):
                    self._reply_json(False, {'ok': False, 'msg': 'Hạn không hợp lệ.'})
                    return
                ok, msg = set_duedate(key, due or '', pat)
                self._reply_json(ok, {'ok': ok, 'msg': msg})
            else:  # /add-comment
                body = payload.get('body')
                if not isinstance(body, str):
                    self._reply_json(False, {'ok': False, 'msg': 'Thiếu nội dung comment.'})
                    return
                ok, msg = add_comment(key, body[:5000], pat)
                self._reply_json(ok, {'ok': ok, 'msg': msg})
        except (ValueError, json.JSONDecodeError, OSError):
            self._reply_json(False, {'ok': False, 'msg': 'Lỗi xử lý yêu cầu.'})

    def _handle_create_subtask(self):
        """Tạo Sub-task QA dưới 1 Task-PTSP, NHÂN DANH chủ PAT cá nhân (reporter = người
        đăng nhập). Admin + QA member đều dùng được (chỉ cần đã đăng nhập + có PAT)."""
        pat = load_user_pat(self._user_email())
        if not pat:
            self._reply_json(False, {'ok': False, 'code': 'no_pat',
                'msg': 'Bạn chưa cấu hình PAT. Vào ⚙ Cài đặt để thêm, rồi thử lại.'})
            return
        try:
            payload = self._read_json_body(20_000)
            if not isinstance(payload, dict):
                self._reply_json(False, {'ok': False, 'msg': 'Dữ liệu không hợp lệ.'})
                return
            parent = (payload.get('parent') or '').strip()
            summary = payload.get('summary') or ''
            duedate = (payload.get('duedate') or '').strip()
            start_date = (payload.get('startDate') or '').strip()
            assignee = (payload.get('assignee') or '').strip() or None
            leader = (payload.get('leader') or '').strip() or None
            if not re.match(r'^[A-Za-z0-9]+-\d+$', parent):
                self._reply_json(False, {'ok': False, 'msg': 'Task cha không hợp lệ.'})
                return
            datep = r'^\d{4}-\d{2}-\d{2}$'
            if not re.match(datep, duedate) or not re.match(datep, start_date):
                self._reply_json(False, {'ok': False,
                    'msg': 'Ngày phải đúng định dạng YYYY-MM-DD.'})
                return
            ok, res = create_subtask(parent, summary, duedate, start_date,
                                     assignee, leader, pat)
            if ok:
                self._reply_json(True, {'ok': True, 'key': res,
                    'url': f'{JIRA_URL}/browse/{res}', 'msg': f'Đã tạo {res} ✓'})
            else:
                self._reply_json(False, {'ok': False, 'msg': res})
        except (ValueError, json.JSONDecodeError, OSError):
            self._reply_json(False, {'ok': False, 'msg': 'Lỗi xử lý yêu cầu.'})

    def _post_set_custom_status(self):
        # QA toggle nhãn nội bộ cho task (chọn nhiều). Author = người đăng nhập (không cần PAT).
        values = None
        try:
            length = int(self.headers.get('Content-Length', 0))
            if 0 < length <= 20_000:
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                if isinstance(payload, dict):
                    key = payload.get('key')
                    value = payload.get('status', '')
                    summary = payload.get('summary', '')
                    if (isinstance(key, str) and key and isinstance(value, str)
                            and is_valid(value) and isinstance(summary, str)):
                        values = set_custom_status(self._user_email(), key, value, summary[:200])
        except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
            values = None
        if values is not None:
            self._json(200, json.dumps({'ok': True, 'values': values}).encode('utf-8'))
        else:
            self._json(400, b'{"ok":false}')
