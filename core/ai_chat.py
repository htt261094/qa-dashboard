"""Chatbot AI hỏi-đáp số liệu bug log (Decision: tool-use, KHÔNG RAG).

Kiến trúc: LLM CHỈ làm 2 việc — (1) dịch câu hỏi tiếng Việt -> gọi đúng tool,
(2) diễn đạt kết quả. Việc đếm/lọc THẬT là `query_bugs` chạy local trên bug_log
-> số luôn ĐÚNG (do code tính, không phải LLM đoán). Ra Cloudflare chỉ là câu hỏi
+ con số kết quả nhỏ, KHÔNG phải cả bug log (OPSEC nhẹ).

Provider SWAP-ĐƯỢC: chỉ `_call_llm()` chạm Cloudflare Workers AI. Đổi sang Claude
sau = sửa 1 hàm này, phần tool + loop giữ nguyên.
"""
import json
import sys
import time

import requests

from config import (CF_ACCOUNT_ID, CF_AI_TOKEN, WORKERS_AI_MODEL,
                    AI_CHAT_ENABLED)
import bug_log_store

_TIMEOUT = 60                 # 70b cold-start có thể >30s; client bỏ cuộc ở 75s
_MAX_TOOL_ROUNDS = 4          # chặn loop vô hạn nếu LLM cứ gọi tool
_LIST_CAP = 30                # mode=list trả tối đa bao nhiêu bug


def _redact(s):
    """Xoá token khỏi mọi chuỗi lỗi trước khi log/raise (OPSEC)."""
    t = (s or '')
    if CF_AI_TOKEN:
        t = t.replace(CF_AI_TOKEN, '<REDACTED>')
    return t


# ===== Dữ liệu nguồn =====
def _all_bugs():
    """Mọi bug hiện tại từ cache bug_log (gộp các file). [] nếu chưa scan."""
    data = bug_log_store.load_bug_log() or {}
    out = []
    for f in (data.get('files') or {}).values():
        bugs = f.get('bugs') or []
        # bugs có thể là dict {key: bug} (cache) hoặc list — chuẩn hoá về list dict.
        items = bugs.values() if isinstance(bugs, dict) else bugs
        out.extend(b for b in items if isinstance(b, dict))
    return out


# ===== Tool: query_bugs — 1 hàm tham số hoá phủ phần lớn câu hỏi =====
def query_bugs(dev=None, qa=None, severity=None, status=None,
               project=None, month=None, mode='count'):
    """Đếm / liệt kê / nhóm bug theo bộ lọc bất kỳ. Filter None = bỏ qua.

    mode: 'count' (đếm) | 'list' (liệt kê) | 'group' (nhóm theo dev rồi đếm).
    dev/qa/severity/project = khớp chứa (không phân biệt hoa thường);
    status = khớp đúng; month = khớp đúng tên sheet/tháng.
    """
    bugs = _all_bugs()

    def _has(field, val):
        return val is None or str(val).lower() in str(field or '').lower()

    def match(b):
        if not _has(b.get('dev_pic'), dev):
            return False
        if not _has(b.get('qa_pic'), qa):
            return False
        if not _has(b.get('severity'), severity):
            return False
        if not _has(b.get('project'), project):
            return False
        if status is not None and str(status).lower() != str(b.get('status') or '').lower():
            return False
        if month is not None and str(month).strip().lower() != str(b.get('month') or '').strip().lower():
            return False
        return True

    sel = [b for b in bugs if match(b)]
    flt = {k: v for k, v in (('dev', dev), ('qa', qa), ('severity', severity),
                             ('status', status), ('project', project),
                             ('month', month)) if v is not None}

    if mode == 'group':
        groups = {}
        for b in sel:
            key = (b.get('dev_pic') or '(chưa gán)').strip() or '(chưa gán)'
            groups[key] = groups.get(key, 0) + 1
        ranked = sorted(groups.items(), key=lambda kv: kv[1], reverse=True)
        return {'total': len(sel), 'filters': flt,
                'groups': [{'dev': k, 'count': n} for k, n in ranked]}

    if mode == 'list':
        rows = [{'project': b.get('project'), 'bug_no': b.get('bug_no'),
                 'summary': (b.get('summary') or '')[:120],
                 'severity': b.get('severity'), 'status': b.get('status'),
                 'dev': b.get('dev_pic'), 'qa': b.get('qa_pic'),
                 'month': b.get('month')} for b in sel[:_LIST_CAP]]
        return {'count': len(sel), 'shown': len(rows), 'filters': flt, 'bugs': rows}

    return {'count': len(sel), 'filters': flt}


# Spec gửi cho LLM (định dạng OpenAI/Workers AI function-calling).
TOOLS = [{
    'name': 'query_bugs',
    'description': (
        'Đếm, liệt kê hoặc nhóm bug trong bug log QA theo bộ lọc. '
        'Dùng tool này cho MỌI câu hỏi về số lượng bug, bug của dev nào, '
        'bug theo severity/status/dự án/tháng. KHÔNG tự bịa số — luôn gọi tool.'),
    'parameters': {
        'type': 'object',
        'properties': {
            'dev': {'type': 'string', 'description': 'Tên dev (PIC Dev) cần lọc, vd "Phương".'},
            'qa': {'type': 'string', 'description': 'Tên QA (PIC Test) cần lọc.'},
            'severity': {'type': 'string', 'description': 'Mức độ bug (giá trị thật: Major, Medium, Normal, Minor, Low). Không có mức "critical".'},
            'status': {'type': 'string', 'description': 'Trạng thái vòng đời: New, Fixing, Fixed, Reopen, Closed, Rejected.'},
            'project': {'type': 'string', 'description': 'Mã dự án, vd "DA6", "DA5".'},
            'month': {'type': 'string', 'description': 'Tháng (tên sheet trong file), vd "5", "Tháng 5".'},
            'mode': {'type': 'string', 'enum': ['count', 'list', 'group'],
                     'description': 'count=đếm tổng; list=liệt kê bug; group=nhóm theo dev rồi đếm (cho câu "ai nhiều bug nhất").'},
        },
        'required': [],
    },
}]

_DISPATCH = {'query_bugs': query_bugs}


def _data_hint():
    """Từ điển giá trị THẬT trong bug log -> nhồi vào prompt để model lọc đúng
    (vd biết severity là 'Major'/'Minor' chứ không phải 'critical'; project có những mã nào)."""
    bugs = _all_bugs()
    seen = {'severity': set(), 'status': set(), 'project': set()}
    for b in bugs:
        for f in seen:
            v = (b.get(f) or '').strip()
            if v:
                seen[f].add(v)
    def _fmt(s):
        return ', '.join(sorted(s)) or '(không có)'
    return ("Giá trị có thật trong dữ liệu (dùng ĐÚNG các giá trị này khi lọc):\n"
            f"- severity: {_fmt(seen['severity'])}\n"
            f"- status: {_fmt(seen['status'])}\n"
            f"- project (mã dự án): {_fmt(seen['project'])}\n"
            "Nếu người dùng dùng từ khác (vd 'critical', 'nghiêm trọng'), ánh xạ về giá trị gần nhất "
            "có thật ở trên; nếu không có thì nói rõ là dữ liệu không có mức đó.")

_SYSTEM = (
    "Bạn là trợ lý nội bộ của team QA Bảo Kim, trả lời bằng TIẾNG VIỆT, ngắn gọn. "
    "Bạn CHỈ trả lời câu hỏi về bug log QA (số lượng bug, bug theo dev/QA/severity/status/dự án/tháng). "
    "Quy tắc BẮT BUỘC:\n"
    "1. Mọi con số PHẢI lấy từ kết quả tool query_bugs. TUYỆT ĐỐI không tự bịa hay ước lượng số.\n"
    "2. Nếu không tool nào trả lời được câu hỏi, nói thẳng: 'Mình chưa hỗ trợ câu hỏi này.' — đừng đoán.\n"
    "3. Câu hỏi ngoài phạm vi bug log (chuyện phiếm, viết email...) -> từ chối lịch sự.\n"
    "4. Trả lời dựa đúng vào con số tool trả về, nêu rõ bộ lọc đã dùng nếu cần."
)


# ===== Provider: Cloudflare Workers AI (điểm SWAP duy nhất) =====
def _log(msg):
    print(f"[chat] {msg}", file=sys.stderr, flush=True)


def _call_llm(messages):
    """Gọi Workers AI 1 lượt. Trả (text, tool_calls). Raise RuntimeError đã redact."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/{WORKERS_AI_MODEL}"
    t0 = time.time()
    try:
        r = requests.post(url,
                          headers={'Authorization': f'Bearer {CF_AI_TOKEN}'},
                          json={'messages': messages, 'tools': TOOLS},
                          timeout=_TIMEOUT)
        _log(f"Workers AI HTTP {r.status_code} sau {time.time()-t0:.1f}s")
        if r.status_code >= 400:
            # Lộ lý do thật từ Cloudflare (body chứa errors) thay vì nuốt.
            try:
                j = r.json()
                detail = json.dumps(j.get('errors') or j.get('messages') or j,
                                    ensure_ascii=False)[:400]
            except ValueError:
                detail = (r.text or '')[:400]
            _log(f"LỖI body: {_redact(detail)}")
            raise RuntimeError(_redact(f"Workers AI HTTP {r.status_code}: {detail}"))
        body = r.json()
    except requests.RequestException as e:
        _log(f"LỖI gọi Workers AI sau {time.time()-t0:.1f}s: {_redact(str(e))}")
        raise RuntimeError(_redact(f"Lỗi gọi Workers AI: {e}")) from None
    except ValueError:
        raise RuntimeError("Workers AI trả về không phải JSON.") from None

    if not body.get('success', True):
        raise RuntimeError(_redact(f"Workers AI lỗi: {body.get('errors')}"))
    res = body.get('result') or {}
    return res.get('response', '') or '', res.get('tool_calls') or []


def ask(question, history=None):
    """Hỏi-đáp 1 lượt. history = [{role, content}, ...] (tuỳ chọn).

    Trả {ok, answer, tool_calls} hoặc {ok:False, error}. tool_calls = list
    {name, arguments} đã chạy -> client hiện minh bạch "đã dùng tool gì".
    """
    if not AI_CHAT_ENABLED:
        return {'ok': False, 'error': 'Chatbot chưa cấu hình (thiếu CF_ACCOUNT_ID / CF_AI_TOKEN trong .env).'}
    q = (question or '').strip()
    if not q:
        return {'ok': False, 'error': 'Câu hỏi rỗng.'}

    messages = [{'role': 'system', 'content': _SYSTEM + '\n\n' + _data_hint()}]
    messages.extend(history or [])
    messages.append({'role': 'user', 'content': q})

    _log(f"Q: {q[:80]} (model={WORKERS_AI_MODEL})")
    used = []
    try:
        for rnd in range(_MAX_TOOL_ROUNDS):
            text, calls = _call_llm(messages)
            _log(f"round {rnd+1}: tool_calls={[c.get('name') for c in calls]} text={(text or '')[:60]!r}")
            if not calls:
                _log("-> trả lời (không gọi thêm tool)")
                return {'ok': True, 'answer': text or '(không có câu trả lời)', 'tool_calls': used}
            # Ghi lại assistant đã yêu cầu gọi tool, rồi chèn kết quả tool.
            messages.append({'role': 'assistant', 'content': text, 'tool_calls': calls})
            for c in calls:
                name = c.get('name') or ''
                args = c.get('arguments') or c.get('parameters') or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                fn = _DISPATCH.get(name)
                result = fn(**args) if fn else {'error': f'không có tool {name}'}
                used.append({'name': name, 'arguments': args})
                messages.append({'role': 'tool', 'name': name,
                                 'content': json.dumps(result, ensure_ascii=False)})
        # Hết vòng mà vẫn đòi tool -> chốt 1 lượt không tool.
        text, _ = _call_llm(messages + [{'role': 'system',
                            'content': 'Trả lời dứt điểm từ dữ liệu đã có, không gọi thêm tool.'}])
        return {'ok': True, 'answer': text or '(không có câu trả lời)', 'tool_calls': used}
    except RuntimeError as e:
        return {'ok': False, 'error': str(e)}
    except Exception:   # noqa: BLE001 — chặn mọi traceback rò token
        return {'ok': False, 'error': 'Lỗi không xác định khi xử lý chatbot.'}
