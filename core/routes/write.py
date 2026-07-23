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
                        create_subtasks, can_edit_duedate, set_duedate,
                        get_editmeta_fields, update_issue)


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
            elif self.path == '/edit-perms':
                # UI gate cho form Sửa task: field nào (title/assignee/due) user được sửa.
                ok, res = get_editmeta_fields(key, pat)
                if not ok:
                    self._reply_json(False, {'ok': False, 'msg': res})
                else:
                    self._reply_json(True, {'ok': True, 'fields': {
                        'summary': 'summary' in res,
                        'assignee': 'assignee' in res,
                        'duedate': 'duedate' in res}})
            elif self.path == '/update-issue':
                # Sửa title/assignee/due bằng PAT cá nhân. Chỉ gửi field client thực sự đổi.
                fields = {}
                summary = payload.get('summary')
                if isinstance(summary, str):
                    s = summary.strip()
                    if not s:
                        self._reply_json(False, {'ok': False, 'msg': 'Tiêu đề không được rỗng.'})
                        return
                    fields['summary'] = s[:250]
                assignee = payload.get('assignee')
                if isinstance(assignee, str) and assignee.strip():
                    fields['assignee'] = {'name': assignee.strip()}
                due = payload.get('duedate')
                if isinstance(due, str):
                    d = due.strip()
                    if d and not re.match(r'^\d{4}-\d{2}-\d{2}$', d):
                        self._reply_json(False, {'ok': False, 'msg': 'Ngày phải đúng định dạng YYYY-MM-DD.'})
                        return
                    fields['duedate'] = d or None
                if not fields:
                    self._reply_json(False, {'ok': False, 'msg': 'Không có thay đổi nào.'})
                    return
                ok, msg = update_issue(key, fields, pat)
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

    def _handle_create_subtasks(self):
        """Tạo NHIỀU Sub-task QA dưới CÙNG 1 Task-PTSP (verify cha 1 lần, tạo tuần tự).
        Partial-failure: trả cả created lẫn failed để FE báo rõ."""
        pat = load_user_pat(self._user_email())
        if not pat:
            self._reply_json(False, {'ok': False, 'code': 'no_pat',
                'msg': 'Bạn chưa cấu hình PAT. Vào ⚙ Cài đặt để thêm, rồi thử lại.'})
            return
        try:
            payload = self._read_json_body(50_000)
            if not isinstance(payload, dict):
                self._reply_json(False, {'ok': False, 'msg': 'Dữ liệu không hợp lệ.'})
                return
            parent = (payload.get('parent') or '').strip()
            # items = [{summary, assignee}] (assignee RIÊNG mỗi dòng). Tương thích ngược:
            # payload cũ gửi `summaries` (list str) + `assignee` chung.
            raw = payload.get('items')
            if not isinstance(raw, list):
                summaries = payload.get('summaries')
                shared_a = (payload.get('assignee') or '').strip()
                raw = ([{'summary': s, 'assignee': shared_a} for s in summaries
                        if isinstance(s, str)] if isinstance(summaries, list) else [])
            duedate = (payload.get('duedate') or '').strip()
            start_date = (payload.get('startDate') or '').strip()
            leader = (payload.get('leader') or '').strip() or None
            if not re.match(r'^[A-Za-z0-9]+-\d+$', parent):
                self._reply_json(False, {'ok': False, 'msg': 'Task cha không hợp lệ.'})
                return
            # Chuẩn hoá + cap 30 sub-task/lần để tránh loạt call nặng
            items = []
            for it in raw:
                if isinstance(it, dict) and isinstance(it.get('summary'), str) and it['summary'].strip():
                    a = it.get('assignee')
                    items.append({'summary': it['summary'],
                                  'assignee': a if isinstance(a, str) else ''})
                elif isinstance(it, str) and it.strip():
                    items.append({'summary': it, 'assignee': ''})
            items = items[:30]
            if not items:
                self._reply_json(False, {'ok': False, 'msg': 'Thiếu tiêu đề sub-task.'})
                return
            datep = r'^\d{4}-\d{2}-\d{2}$'
            if not re.match(datep, duedate) or not re.match(datep, start_date):
                self._reply_json(False, {'ok': False,
                    'msg': 'Ngày phải đúng định dạng YYYY-MM-DD.'})
                return
            ok, res = create_subtasks(parent, items, duedate, start_date, leader, pat)
            if not ok and not isinstance(res.get('created'), list):
                # Lỗi sớm (verify cha / thiếu field) -> chỉ có msg
                self._reply_json(False, {'ok': False, 'msg': res.get('msg', 'Lỗi tạo sub-task.')})
                return
            created = res.get('created', [])
            failed = res.get('failed', [])
            for c in created:
                c['url'] = f"{JIRA_URL}/browse/{c.get('key','')}"
            self._reply_json(bool(created),
                {'ok': bool(created), 'created': created, 'failed': failed})
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
