"""WriteMixin — ghi THẬT lên Jira bằng PAT cá nhân + nhãn nội bộ.

Tách từ qa_dashboard.py (issue #86 / B2). Zero behavior change: chỉ di chuyển định
nghĩa method, không đổi logic/route/output.

Gom các route ghi (Decision #20/#21/#113):
- `_handle_jira_write` — /jira-transitions · /do-transition · /add-comment (PAT cá nhân)
- `_handle_create_issue` — /create-issue (tạo task createmeta-động, Decision #113)
- `_post_set_custom_status` — /set-custom-status (nhãn nội bộ, không cần PAT)
- `_post_set_note` — /set-note (ghi chú riêng theo task, Decision #101)

Mixin dùng các helper dùng chung định nghĩa ở Handler (resolve qua MRO):
`self._user_email()`, `self._reply_json()`, `self._read_json_body()`, `self._json()`.

Layer rule: KHÔNG import qa_dashboard (tránh vòng import).
"""
import re
import json
from urllib.parse import urlparse, parse_qs

from config import JIRA_URL
from pat_store import load_user_pat
from custom_status import set_custom_status, is_valid
from task_notes import set_note
from status_overlay import record as record_status
from jira_write import (get_transitions, do_transition, get_issue_status, add_comment,
                        can_edit_duedate, set_duedate, get_editmeta_fields, update_issue,
                        list_projects, create_issuetypes, create_fields, create_issue)

_KEY_RE = re.compile(r'^[A-Za-z][A-Za-z0-9]*-\d+$')
_PROJ_RE = re.compile(r'^[A-Za-z][A-Za-z0-9]*$')


class WriteMixin:
    def _handle_jira_write(self):
        """Transition / comment THẬT lên Jira bằng PAT cá nhân của người đăng nhập.
        Không có PAT -> từ chối (để KHÔNG ghi nhầm tên tài khoản chung)."""
        pat = load_user_pat(self._user_email())
        if not pat:
            self._reply_json(False, {'ok': False, 'code': 'no_pat',
                'msg': 'Bạn chưa cấu hình API token Jira. Vào ⚙ Cài đặt để thêm, rồi thử lại.'})
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
                res = {'ok': ok, 'msg': msg}
                if ok:
                    # Decision #90: chốt status MỚI ngay tại đây để mọi lần render sau
                    # (cache SWR / index Jira chưa kịp) không dội status cũ về.
                    # Ưu tiên đọc lại từ Jira (GET /issue -> không lag index); fail thì
                    # dùng tên đích client gửi kèm.
                    sok, name = get_issue_status(key, pat)
                    to = payload.get('to')
                    new_st = name if (sok and name) else (to if isinstance(to, str) else '')
                    if new_st:
                        record_status(key, new_st)
                        res['status'] = new_st
                self._reply_json(ok, res)
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
                    # Jira Cloud (#197): user-picker ghi bằng accountId.
                    from jira_cloud import user_ref
                    ref = user_ref(assignee.strip())
                    if not ref:
                        self._reply_json(False, {'ok': False, 'msg': f'Không tìm thấy tài khoản Jira của "{assignee.strip()}".'})
                        return
                    fields['assignee'] = ref
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

    # ===== Tạo task độc lập — createmeta-động (Decision #113) =====
    def _create_pat_or_fail(self):
        """Load PAT cá nhân, trả pat hoặc None (đã tự reply lỗi no_pat)."""
        pat = load_user_pat(self._user_email())
        if not pat:
            self._reply_json(False, {'ok': False, 'code': 'no_pat',
                'msg': 'Bạn chưa cấu hình API token Jira. Vào ⚙ Cài đặt để thêm, rồi thử lại.'})
            return None
        return pat

    def _get_create_projects(self):
        # Dropdown chọn dự án khi tạo task (PAT cá nhân -> đúng project user tạo được).
        pat = self._create_pat_or_fail()
        if not pat:
            return
        q = (parse_qs(urlparse(self.path).query).get('q') or [''])[0]
        ok, res = list_projects(q, pat)
        self._reply_json(ok, {'ok': True, 'results': res} if ok else {'ok': False, 'msg': res})

    def _get_create_issuetypes(self):
        # Issue type user được tạo trong 1 project (createmeta).
        pat = self._create_pat_or_fail()
        if not pat:
            return
        proj = (parse_qs(urlparse(self.path).query).get('project') or [''])[0].strip()
        if not _PROJ_RE.match(proj):
            self._reply_json(False, {'ok': False, 'msg': 'Project không hợp lệ.'})
            return
        ok, res = create_issuetypes(proj, pat)
        self._reply_json(ok, {'ok': True, 'results': res} if ok else {'ok': False, 'msg': res})

    def _get_create_fields(self):
        # Field động của (project, issuetype) — FE render widget theo required + schema.
        pat = self._create_pat_or_fail()
        if not pat:
            return
        qs = parse_qs(urlparse(self.path).query)
        proj = (qs.get('project') or [''])[0].strip()
        type_id = (qs.get('type') or [''])[0].strip()
        if not _PROJ_RE.match(proj) or not type_id.isdigit():
            self._reply_json(False, {'ok': False, 'msg': 'Tham số không hợp lệ.'})
            return
        ok, res = create_fields(proj, type_id, pat)
        self._reply_json(ok, {'ok': True, 'fields': res} if ok else {'ok': False, 'msg': res})

    def _handle_create_issue(self):
        """Tạo 1 issue bất kỳ (project + issuetype + field động), NHÂN DANH chủ PAT."""
        pat = self._create_pat_or_fail()
        if not pat:
            return
        try:
            payload = self._read_json_body(80_000)
            if not isinstance(payload, dict):
                self._reply_json(False, {'ok': False, 'msg': 'Dữ liệu không hợp lệ.'})
                return
            proj = (payload.get('project') or '').strip()
            type_id = str(payload.get('type') or '').strip()
            if not _PROJ_RE.match(proj) or not type_id.isdigit():
                self._reply_json(False, {'ok': False, 'msg': 'Thiếu dự án hoặc loại task hợp lệ.'})
                return
            parent = (payload.get('parent') or '').strip()
            if parent and not _KEY_RE.match(parent):
                self._reply_json(False, {'ok': False, 'msg': 'Task cha không hợp lệ.'})
                return
            raw = payload.get('fields')
            if not isinstance(raw, dict):
                raw = {}
            ok, res = create_issue(proj, type_id, raw, parent or None, pat)
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

    def _post_set_note(self):
        # Ghi chú riêng theo task (Decision #101) — chỉ chính chủ, không chạm Jira, không cần PAT.
        if not self._is_admin():
            self._json(403, b'{"ok":false}')
            return
        entry = None
        try:
            payload = self._read_json_body(40_000)
            if isinstance(payload, dict):
                key, text = payload.get('key'), payload.get('text', '')
                if (isinstance(key, str) and re.fullmatch(r'[A-Z][A-Z0-9]*-\d+', key)
                        and isinstance(text, str)):
                    entry = set_note(key, text)
        except (ValueError, json.JSONDecodeError, RuntimeError, OSError):
            entry = None
        if entry is None:
            self._json(400, b'{"ok":false}')
            return
        self._json(200, json.dumps({'ok': True, 'note': entry or None},
                                   ensure_ascii=False).encode('utf-8'))
