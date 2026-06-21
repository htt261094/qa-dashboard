"""Chatbot trợ lý QA — proxy LLM local (Ollama) + phủ TOÀN BỘ dữ liệu workspace (Decision #32).

Mô hình: browser nói chuyện với app (đã qua OAuth/domain gate), app stream tiếp sang
Ollama chạy CÙNG host (`localhost:11434`). KHÔNG bao giờ expose Ollama ra ngoài (không auth).

Để chatbot trả lời được MỌI câu hỏi về dữ liệu trên web mà KHÔNG nhồi nguyên >10K bản ghi
vào prompt (chậm + model 7B loãng), dùng 2 lớp:
  1. **Summary** (`build_context`): số liệu tổng hợp mọi nguồn (bug log, test case, roadmap,
     tài liệu, task Jira) — trả lời câu hỏi đếm/tỷ lệ/xu hướng.
  2. **Retrieval** (`retrieve`): mini-RAG keyword-overlap trên index gộp mọi bản ghi thô →
     mỗi câu hỏi kéo đúng các bản ghi liên quan (1 bug/case/mục cụ thể) vào prompt.
Cả raw-data lẫn index cache in-process TTL ngắn → KHÔNG nện Jira/KV/Drive mỗi tin nhắn.

Layer: config -> issues -> {bug_log_store, docs, roadmap, testcase_store, jira_api} ->
(this) -> qa_dashboard. Lazy-import các nguồn để soft-fail độc lập + không bắt buộc Jira.
"""
import json
import re
import threading
import time

import requests

from config import OLLAMA_URL, OLLAMA_MODEL, CHAT_ENABLED

# ===== Persona =====
_SYSTEM_BASE = (
    "Bạn là trợ lý AI của team QA Bảo Kim, nhúng trong QA Workspace (dashboard nội bộ kéo "
    "dữ liệu từ Jira + bug log Google Drive). Trả lời bằng tiếng Việt, ngắn gọn, đi thẳng "
    "vào việc, phong cách đồng nghiệp.\n"
    "BẠN CÓ CÁC CÔNG CỤ (tools) để truy vấn dữ liệu CHÍNH XÁC — HÃY DÙNG chúng thay vì tự "
    "suy đoán, vì bạn KHÔNG tự nhớ hết được dữ liệu:\n"
    "  • count_bugs — đếm số bug theo dự án/tháng/trạng thái/người (QA hoặc dev fix).\n"
    "  • count_testcases — đếm test case theo bộ/kết quả chạy.\n"
    "  • count_tasks — đếm task Jira theo người làm/trạng thái.\n"
    "  • find_records — tìm bản ghi cụ thể (1 bug/test case/task/mục roadmap/tài liệu) theo "
    "từ khoá hoặc mã (vd DA6#T6#59).\n"
    "QUY TẮC BẮT BUỘC: Mọi câu hỏi về SỐ LƯỢNG (bao nhiêu, tổng, đếm) → PHẢI gọi count_* và "
    "dùng đúng con số trả về. Mọi câu hỏi về 1 bản ghi/chi tiết cụ thể → gọi find_records. "
    "TUYỆT ĐỐI KHÔNG tự bịa/ước lượng/nội suy con số. Nếu tool trả 0 hoặc rỗng thì nói thẳng "
    "là không có, đừng đoán. Câu chào hỏi/chung chung thì trả lời thẳng, KHÔNG cần gọi tool.\n"
    "Phần 'DỮ LIỆU TỔNG HỢP' bên dưới chỉ là tổng quan để định hướng — số liệu chi tiết LẤY "
    "TỪ TOOL. CÁCH TRÌNH BÀY: diễn giải gọn, súc tích, đúng trọng tâm; list dài thì nêu vài "
    "mục tiêu biểu + tổng số; KHÔNG gọi dữ liệu là 'snapshot'. Markdown nhẹ cho dễ đọc."
)

# ===== Raw data load (cached) =====
_DATA_TTL = 90
_data_cache = {'at': 0.0, 'raw': None, 'index': None}
_data_lock = threading.Lock()


def _created_month(s):
    """Ngày tạo -> 'YYYY-MM' (ISO YYYY-MM-DD hoặc DD/MM/YYYY). '' nếu không nhận ra."""
    s = (s or '').strip()
    if len(s) >= 7 and s[:4].isdigit() and s[4] == '-':
        return s[:7]
    parts = s.split('/')
    if len(parts) == 3 and parts[2][:4].isdigit() and len(parts[2][:4]) == 4:
        return f'{parts[2][:4]}-{parts[1].zfill(2)}'
    return ''


def _load_bugs():
    try:
        from bug_log_store import load_bug_log
        d = load_bug_log()
    except Exception:   # noqa: BLE001
        return [], {}
    files = d.get('files', {}) if isinstance(d, dict) else {}
    bugs = []
    for f in files.values():
        b = f.get('bugs', {})
        bugs.extend(b.values() if isinstance(b, dict) else (b or []))
    reopen = d.get('reopen', {}) if isinstance(d, dict) else {}
    return bugs, reopen


def _load_cases():
    try:
        from testcase_store import load_testcases
        d = load_testcases()
    except Exception:   # noqa: BLE001
        return [], []
    if not isinstance(d, dict):
        return [], []
    return d.get('folders', []), d.get('cases', [])


def _load_docs_tree():
    try:
        from docs import load_docs
        t = load_docs()
        return t if isinstance(t, list) else []
    except Exception:   # noqa: BLE001
        return []


def _load_roadmap():
    try:
        from roadmap import load_roadmap
        r = load_roadmap()
        return r if isinstance(r, list) else []
    except Exception:   # noqa: BLE001
        return []


def _load_tasks():
    """Task Jira (full team) — CHỈ đọc cache có sẵn, KHÔNG bao giờ trigger fetch live.

    Chat phải snappy + KHÔNG phụ thuộc VPN/Jira: peek L1 RAM cache của fetch_all (dashboard
    giữ ấm) trước; rỗng/cũ -> đọc snapshot đĩa local (nhanh, không mạng). Cả 2 hụt -> {} (bỏ
    qua mảng task, các mảng khác vẫn đủ). KHÔNG gọi fetch_all_shared() vì nó có thể nện KV/
    Jira đồng bộ (block ~10s khi mất mạng)."""
    try:
        from jira_api import _cache_get, _snap_read_local, _snap_deserialize
        data, ok = _cache_get('fetch_all:None')
        if ok and isinstance(data, dict):
            return data
        raw = _snap_read_local()
        if raw:
            snap = _snap_deserialize(raw)
            if isinstance(snap, dict):
                return snap
    except Exception:   # noqa: BLE001 — KHÔNG để chat chết vì Jira/VPN
        pass
    return {}


def _load_all(force=False):
    now = time.time()
    if not force:
        with _data_lock:
            if _data_cache['raw'] is not None and (now - _data_cache['at'] < _DATA_TTL):
                return _data_cache['raw'], _data_cache['index']
    bugs, reopen = _load_bugs()
    folders, cases = _load_cases()
    raw = {
        'bugs': bugs, 'reopen': reopen,
        'folders': folders, 'cases': cases,
        'docs': _load_docs_tree(), 'roadmap': _load_roadmap(),
        'tasks': _load_tasks(),
    }
    index = _build_index(raw)
    with _data_lock:
        _data_cache.update(at=now, raw=raw, index=index)
    return raw, index


# ===== Summaries =====
def _fmt_counts(d, top=None):
    items = sorted(d.items(), key=lambda kv: -kv[1])
    if top:
        items = items[:top]
    return ', '.join(f'{k}: {v}' for k, v in items)


def _bug_summary(raw):
    bugs, reopen = raw['bugs'], raw['reopen']
    if not bugs:
        return ''
    by_project, by_status, by_qa, by_dev, by_cmonth = {}, {}, {}, {}, {}
    for b in bugs:
        by_project[b.get('project') or '?'] = by_project.get(b.get('project') or '?', 0) + 1
        by_status[b.get('status') or '?'] = by_status.get(b.get('status') or '?', 0) + 1
        qa = b.get('qa_pic') or ''
        if qa:
            by_qa[qa] = by_qa.get(qa, 0) + 1
        dev = b.get('dev_pic') or ''
        if dev:
            by_dev[dev] = by_dev.get(dev, 0) + 1
        cm = _created_month(b.get('created'))
        if cm:
            by_cmonth[cm] = by_cmonth.get(cm, 0) + 1
    reopened = sorted(((k, v.get('count', 0)) for k, v in reopen.items() if v.get('count', 0) > 0),
                      key=lambda kv: -kv[1])
    lines = [
        '## BUG LOG (đồng bộ từ Google Drive)',
        f'- Tổng số bug: {len(bugs)}',
        f'- Theo dự án: {_fmt_counts(by_project)}',
        f'- Theo trạng thái: {_fmt_counts(by_status)}',
    ]
    if by_cmonth:
        lines.append('- Bug phát sinh theo tháng (ngày tạo): '
                     + ', '.join(f'{k}: {by_cmonth[k]}' for k in sorted(by_cmonth)))
    if by_qa:
        lines.append(f'- Theo QA phụ trách: {_fmt_counts(by_qa)}')
    if by_dev:
        lines.append(f'- Theo dev fix (top 15): {_fmt_counts(by_dev, top=15)}')
    if reopened:
        lines.append(f'- Bug từng bị Reopen ({len(reopened)} bug): '
                     + '; '.join(f'{k} ({c} lần)' for k, c in reopened[:8]))
    return '\n'.join(lines)


def _testcase_summary(raw):
    folders, cases = raw['folders'], raw['cases']
    if not folders and not cases:
        return ''
    fname = {f.get('id'): f.get('name', '?') for f in folders}
    by_result, by_folder = {}, {}
    for c in cases:
        r = c.get('result') or 'norun'
        by_result[r] = by_result.get(r, 0) + 1
        fn = fname.get(c.get('folder'), '?')
        by_folder[fn] = by_folder.get(fn, 0) + 1
    lines = ['## TEST CASE',
             f'- Số bộ (folder): {len(folders)} | Tổng test case: {len(cases)}']
    if by_result:
        lines.append(f'- Theo kết quả chạy: {_fmt_counts(by_result)}')
    if by_folder:
        lines.append(f'- Theo bộ (top 25): {_fmt_counts(by_folder, top=25)}')
    return '\n'.join(lines)


def _roadmap_summary(raw):
    rm = raw['roadmap']
    if not rm:
        return ''
    n_phase = len(rm)
    n_task = n_sub = n_sub_done = 0
    phase_lines = []
    for p in rm:
        if not isinstance(p, dict):
            continue
        tasks = p.get('tasks', []) or []
        n_task += len(tasks)
        for t in tasks:
            subs = (t.get('subs', []) or []) if isinstance(t, dict) else []
            n_sub += len(subs)
            n_sub_done += sum(1 for s in subs if isinstance(s, dict) and s.get('done'))
        st = p.get('status') or '?'
        due = p.get('due') or ''
        phase_lines.append(f'  · {p.get("title", "?")} (trạng thái: {st}'
                           + (f', hạn {due}' if due else '') + ')')
    lines = ['## ROADMAP',
             f'- {n_phase} giai đoạn, {n_task} đầu việc, {n_sub} sub-task ({n_sub_done} đã xong)',
             'Các giai đoạn:'] + phase_lines
    return '\n'.join(lines)


def _docs_summary(raw):
    tree = raw['docs']
    if not tree:
        return ''
    out = []

    def walk(nodes, depth):
        for n in nodes:
            if not isinstance(n, dict):
                continue
            if n.get('type') == 'folder':
                out.append(f'{"  " * depth}- 📁 {n.get("name", "")}')
                walk(n.get('children', []), depth + 1)
            else:
                out.append(f'{"  " * depth}- 📄 {n.get("title") or n.get("name") or "(không tên)"}')

    walk(tree, 0)
    if not out:
        return ''
    return '## TÀI LIỆU (cây thư mục)\n' + '\n'.join(out[:120])


def _task_summary(raw):
    data = raw['tasks']
    active = data.get('active', []) if isinstance(data, dict) else []
    if not isinstance(data, dict) or not (active or data.get('done_week') or data.get('new24')):
        return ''
    try:
        from issues import i_assignee_name, days_overdue, is_stuck, i_status
    except Exception:   # noqa: BLE001
        return ''
    by_assignee, by_status = {}, {}
    overdue = stuck = 0
    for it in active:
        nm = i_assignee_name(it) or 'Chưa gán'
        by_assignee[nm] = by_assignee.get(nm, 0) + 1
        st = i_status(it) or '?'
        by_status[st] = by_status.get(st, 0) + 1
        if (days_overdue(it) or 0) > 0:
            overdue += 1
        if is_stuck(it):
            stuck += 1
    lines = ['## TASK JIRA (toàn team, dữ liệu hiện tại)',
             f'- Đang mở (active): {len(active)} | Quá hạn: {overdue} | Kẹt ≥5 ngày: {stuck}',
             f'- Done tuần này: {len(data.get("done_week", []))} | Mới tạo 24h: {len(data.get("new24", []))}']
    if by_assignee:
        lines.append(f'- Active theo người: {_fmt_counts(by_assignee)}')
    if by_status:
        lines.append(f'- Active theo trạng thái: {_fmt_counts(by_status)}')
    return '\n'.join(lines)


def build_context(force=False):
    """Số liệu tổng hợp mọi nguồn cho system prompt. Mỗi phần soft-fail độc lập."""
    raw, _idx = _load_all(force=force)
    parts = [p for p in (_bug_summary(raw), _task_summary(raw), _testcase_summary(raw),
                         _roadmap_summary(raw), _docs_summary(raw)) if p]
    return '\n\n'.join(parts) if parts else '(Workspace chưa có dữ liệu.)'


# ===== Retrieval index (mini-RAG keyword overlap) =====
# Mỗi record: 'text' = CHỈ giá trị thật (lowercase) để tìm kiếm — KHÔNG nhồi nhãn cố định
# ('trạng thái', 'nội dung'…) vì nhãn xuất hiện ở MỌI dòng -> từ khoá generic trong câu hỏi
# match tất cả, dìm chết mã định danh. 'line' = bản hiển thị (có nhãn) nhét vào prompt.
def _idx_add(idx, kind, line, *values):
    text = ' '.join(str(v) for v in values if v).lower()
    idx.append({'kind': kind, 'text': text, 'line': line})


def _build_index(raw):
    idx = []
    fname = {f.get('id'): f.get('name', '?') for f in raw['folders']}

    for b in raw['bugs']:
        key = b.get('key', '')
        line = (f"[BUG {key}] dự án={b.get('project','')} tháng={b.get('month','')} | "
                f"trạng thái={b.get('status','')} | QA phụ trách={b.get('qa_pic','')} | "
                f"dev fix={b.get('dev_pic','')} | tính năng={b.get('feature','')} | "
                f"nội dung: {b.get('summary','')}")
        if b.get('expected'):
            line += f" | mong đợi: {b.get('expected')}"
        if b.get('created'):
            line += f" | ngày tạo={b.get('created')}"
        if b.get('note'):
            line += f" | ghi chú: {b.get('note')}"
        _idx_add(idx, 'bug', line, key, b.get('project'), b.get('month'), b.get('status'),
                 b.get('qa_pic'), b.get('dev_pic'), b.get('feature'), b.get('summary'),
                 b.get('expected'), b.get('note'), b.get('created'))

    for c in raw['cases']:
        fn = fname.get(c.get('folder'), '?')
        line = (f"[TESTCASE bộ={fn}] {c.get('item','')} "
                f"(ưu tiên={c.get('priority','')}, kết quả={c.get('result','')})")
        _idx_add(idx, 'testcase', line, fn, c.get('item'), c.get('priority'), c.get('result'),
                 c.get('pre'), c.get('step'), c.get('exp'))

    def walk_rm(nodes, trail):
        for n in nodes:
            if not isinstance(n, dict):
                continue
            title = n.get('title', '')
            path = ' > '.join(trail + [title])
            done = ' [xong]' if n.get('done') else ''
            st = f" status={n.get('status')}" if n.get('status') else ''
            due = f" hạn={n.get('due')}" if n.get('due') else ''
            pic = f" pic={n.get('pic')}" if n.get('pic') else ''
            desc = f" — {n.get('desc')}" if n.get('desc') else ''
            line = f"[ROADMAP] {path}{st}{due}{pic}{done}{desc}"
            _idx_add(idx, 'roadmap', line, path, n.get('status'), n.get('due'),
                     n.get('pic'), n.get('desc'))
            walk_rm(n.get('tasks', []) or n.get('subs', []) or [], trail + [title])

    walk_rm(raw['roadmap'], [])

    def walk_docs(nodes, trail):
        for n in nodes:
            if not isinstance(n, dict):
                continue
            if n.get('type') == 'folder':
                walk_docs(n.get('children', []), trail + [n.get('name', '')])
            else:
                title = n.get('title') or n.get('name') or ''
                path = ' > '.join(trail + [title])
                line = f"[TÀI LIỆU] {path} ({n.get('url','')})"
                _idx_add(idx, 'doc', line, path, n.get('url'))

    walk_docs(raw['docs'], [])

    tasks = raw['tasks']
    if isinstance(tasks, dict):
        try:
            from issues import i_assignee_name, i_status, i_summary, i_duedate
            seen = set()
            for bucket in ('active', 'new24', 'done_week'):
                for it in tasks.get(bucket, []):
                    k = it.get('key', '')
                    if k in seen:
                        continue
                    seen.add(k)
                    line = (f"[TASK {k}] trạng thái={i_status(it)} | "
                            f"người làm={i_assignee_name(it) or 'chưa gán'} | "
                            f"hạn={i_duedate(it) or '-'} | nội dung: {i_summary(it)}")
                    _idx_add(idx, 'task', line, k, i_status(it), i_assignee_name(it),
                             i_duedate(it), i_summary(it))
        except Exception:   # noqa: BLE001
            pass
    return idx


# ===== Lọc bug (dùng chung cho tool count_bugs) =====
def _filter_bugs(bugs, project=None, month=None, status=None, person=None, role=None):
    """Lọc full bugs theo điều kiện (None = bỏ qua). So khớp lỏng (substring, không phân biệt
    hoa thường) cho người/dự án/trạng thái vì model gõ tự do. month = int 1-12 (khớp cả tab
    tháng `T<n>` lẫn ngày tạo). role ∈ {'qa','dev',None}."""
    pj = (project or '').strip().lower()
    st = (status or '').strip().lower()
    pe = (person or '').strip().lower()

    def match(b):
        if pj and pj not in (b.get('project') or '').lower():
            return False
        if st and st not in (b.get('status') or '').lower():
            return False
        if pe:
            qa = (b.get('qa_pic') or '').lower()
            dev = (b.get('dev_pic') or '').lower()
            if role == 'qa':
                hit = pe in qa
            elif role == 'dev':
                hit = pe in dev
            else:
                hit = pe in qa or pe in dev
            if not hit:
                return False
        if month:
            bm = b.get('month', '')
            cm = _created_month(b.get('created'))
            cmn = int(cm[5:7]) if cm else None
            if not (bm == f'T{month}' or cmn == month):
                return False
        return True

    return [b for b in bugs if match(b)]


_STOP = {'là', 'có', 'của', 'và', 'cho', 'thì', 'mà', 'các', 'những', 'một', 'bao', 'nhiêu',
         'gì', 'nào', 'không', 'với', 'được', 'này', 'đó', 'ở', 'trong', 'theo', 'bị', 'đã',
         'thế', 'sao', 'về', 'cái', 'bạn', 'mình', 'tôi', 'team', 'hãy', 'liệt', 'kê',
         'nội', 'dung', 'trạng', 'thái', 'đang', 'ai', 'như', 'và', 'hay', 'thông', 'tin'}


def _tokens(q):
    raw = re.split(r'[^0-9a-zA-ZÀ-ỹ#]+', (q or '').lower())
    return [t for t in raw if len(t) >= 2 and t not in _STOP]


# Từ khoá trong câu hỏi -> loại bản ghi user đang nhắm (boost mạnh đúng loại đó).
# CHỈ dùng để phát hiện loại — KHÔNG tính như từ khoá nội dung (nếu không "case"/"test"
# sẽ match mọi test case, dìm mất từ phân biệt như "iccp").
_KIND_HINTS = {
    'bug': 'bug', 'lỗi': 'bug', 'defect': 'bug',
    'test': 'testcase', 'testcase': 'testcase', 'case': 'testcase', 'bộ': 'testcase', 'tc': 'testcase',
    'task': 'task', 'việc': 'task', 'subtask': 'task',
    'roadmap': 'roadmap', 'lộ': 'roadmap', 'trình': 'roadmap', 'giai': 'roadmap', 'đoạn': 'roadmap',
    'tài': 'doc', 'liệu': 'doc', 'doc': 'doc', 'document': 'doc',
}
_KIND_BONUS = 10


def retrieve(query, k=18, budget=4000, only_kind=None):
    """Top-k bản ghi liên quan câu hỏi. Token định danh (có '#' hoặc chứa số) +5; bản ghi
    đúng LOẠI mà câu hỏi nhắm (bug/test case/task/roadmap/tài liệu) +10. '' nếu không khớp.
    only_kind != None -> CHỈ tìm trong loại đó (cho tool find_records)."""
    _raw, index = _load_all()
    toks = _tokens(query)
    if not toks or not index:
        return ''
    want_kinds = {only_kind} if only_kind else {_KIND_HINTS[t] for t in toks if t in _KIND_HINTS}
    content = [t for t in toks if t not in _KIND_HINTS]
    if not content:
        content = toks   # tool truyền query thuần (vd 1 mã) -> dùng nguyên token
    weights = [(t, 5 if ('#' in t or any(c.isdigit() for c in t)) else 1) for t in content]
    scored = []
    for d in index:
        if only_kind and d['kind'] != only_kind:
            continue
        text = d['text']
        score = sum(w for t, w in weights if t in text)
        if not score:
            continue
        if d['kind'] in want_kinds:
            score += _KIND_BONUS
        scored.append((score, d['line']))
    if not scored:
        return ''
    scored.sort(key=lambda x: -x[0])
    out, used = [], 0
    for _s, line in scored[:k]:
        if used + len(line) + 1 > budget:
            break
        out.append(line)
        used += len(line) + 1
    return '\n'.join(out)


# ===== Gọi Ollama (stream) =====
MAX_HISTORY = 16
MAX_MSG_LEN = 8000


def _sanitize(messages):
    out = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role, content = m.get('role'), m.get('content')
        if role not in ('user', 'assistant') or not isinstance(content, str):
            continue
        c = content.strip()
        if c:
            out.append({'role': role, 'content': c[:MAX_MSG_LEN]})
    return out[-MAX_HISTORY:]


def _system_prompt():
    # CHỈ tổng quan để định hướng — số liệu/chi tiết model LẤY QUA TOOL (không nhồi nguyên data).
    return _SYSTEM_BASE + '\n\n===== DỮ LIỆU TỔNG HỢP (tổng quan) =====\n' + build_context()


# ===== Tools (function calling) =====
TOOLS = [
    {'type': 'function', 'function': {
        'name': 'count_bugs',
        'description': 'Đếm CHÍNH XÁC số bug trong bug log theo điều kiện. Dùng cho mọi câu '
                       'hỏi "có bao nhiêu bug…". Trả về số đếm + phân bố trạng thái.',
        'parameters': {'type': 'object', 'properties': {
            'project': {'type': 'string', 'description': 'Mã dự án, vd DA6, DA5, VĐT, RETAIL, CB, ERP'},
            'month': {'type': 'integer', 'description': 'Tháng 1-12 (theo tab tháng hoặc ngày tạo)'},
            'status': {'type': 'string', 'description': 'Trạng thái: New, Fixing, Fixed, Reopen, Closed, Rejected'},
            'person': {'type': 'string', 'description': 'Tên QA hoặc dev, vd PhucTV, Quang, NhungNH'},
            'role': {'type': 'string', 'enum': ['qa', 'dev'], 'description': "person là 'qa' hay 'dev'; bỏ trống = khớp cả hai"},
        }},
    }},
    {'type': 'function', 'function': {
        'name': 'count_testcases',
        'description': 'Đếm CHÍNH XÁC số test case theo bộ (folder) và/hoặc kết quả chạy.',
        'parameters': {'type': 'object', 'properties': {
            'folder': {'type': 'string', 'description': 'Tên bộ test case, vd ICCP, Watchlist, Leadgen'},
            'result': {'type': 'string', 'enum': ['pass', 'fail', 'impact', 'norun'], 'description': 'Kết quả chạy'},
        }},
    }},
    {'type': 'function', 'function': {
        'name': 'count_tasks',
        'description': 'Đếm CHÍNH XÁC số task Jira (đang mở) theo người làm và/hoặc trạng thái.',
        'parameters': {'type': 'object', 'properties': {
            'assignee': {'type': 'string', 'description': 'Tên người làm, vd Nhung, Quang, Phương'},
            'status': {'type': 'string', 'description': 'Trạng thái Jira, vd In Progress, TO DO, PENDING'},
        }},
    }},
    {'type': 'function', 'function': {
        'name': 'find_records',
        'description': 'Tìm các bản ghi CỤ THỂ theo từ khoá hoặc mã (vd DA6#T6#59). Dùng khi '
                       'hỏi chi tiết 1 mục, hoặc liệt kê vài mục khớp. Trả về danh sách bản ghi.',
        'parameters': {'type': 'object', 'properties': {
            'query': {'type': 'string', 'description': 'Từ khoá hoặc mã cần tìm'},
            'kind': {'type': 'string', 'enum': ['bug', 'testcase', 'task', 'roadmap', 'doc'],
                     'description': 'Giới hạn loại bản ghi; bỏ trống = tìm mọi loại'},
        }, 'required': ['query']},
    }},
]


def _tool_count_bugs(args, raw):
    bugs = raw['bugs']
    month = args.get('month')
    try:
        month = int(month) if month not in (None, '') else None
    except (ValueError, TypeError):
        month = None
    hit = _filter_bugs(bugs, project=args.get('project'), month=month,
                       status=args.get('status'), person=args.get('person'), role=args.get('role'))
    cond = {k: v for k, v in (('dự án', args.get('project')), ('tháng', month),
            ('trạng thái', args.get('status')), ('người', args.get('person'))) if v}
    by_status = {}
    for b in hit:
        by_status[b.get('status') or '?'] = by_status.get(b.get('status') or '?', 0) + 1
    keys = [b.get('key', '') for b in hit][:30]
    return json.dumps({'điều_kiện': cond, 'số_bug': len(hit),
                       'theo_trạng_thái': by_status, 'mã_bug_mẫu': keys}, ensure_ascii=False)


def _tool_count_testcases(args, raw):
    cases, folders = raw['cases'], raw['folders']
    fname = {f.get('id'): f.get('name', '') for f in folders}
    fq = (args.get('folder') or '').strip().lower()
    rq = (args.get('result') or '').strip().lower()
    hit = [c for c in cases
           if (not fq or fq in fname.get(c.get('folder'), '').lower())
           and (not rq or (c.get('result') or 'norun').lower() == rq)]
    by_folder = {}
    for c in hit:
        fn = fname.get(c.get('folder'), '?')
        by_folder[fn] = by_folder.get(fn, 0) + 1
    cond = {k: v for k, v in (('bộ', args.get('folder')), ('kết quả', args.get('result'))) if v}
    return json.dumps({'điều_kiện': cond, 'số_test_case': len(hit),
                       'theo_bộ': dict(sorted(by_folder.items(), key=lambda kv: -kv[1])[:15])},
                      ensure_ascii=False)


def _tool_count_tasks(args, raw):
    data = raw['tasks']
    active = data.get('active', []) if isinstance(data, dict) else []
    if not active:
        return json.dumps({'lưu_ý': 'Chưa có dữ liệu task Jira sẵn (cần dashboard tải).',
                           'số_task': 0}, ensure_ascii=False)
    try:
        from issues import i_assignee_name, i_status
    except Exception:   # noqa: BLE001
        return json.dumps({'số_task': 0}, ensure_ascii=False)
    aq = (args.get('assignee') or '').strip().lower()
    sq = (args.get('status') or '').strip().lower()
    hit = [it for it in active
           if (not aq or aq in (i_assignee_name(it) or '').lower())
           and (not sq or sq in (i_status(it) or '').lower())]
    cond = {k: v for k, v in (('người làm', args.get('assignee')), ('trạng thái', args.get('status'))) if v}
    return json.dumps({'điều_kiện': cond, 'số_task_đang_mở': len(hit)}, ensure_ascii=False)


def _tool_find_records(args, raw):
    query = args.get('query') or ''
    kind = args.get('kind') or None
    res = retrieve(query, k=15, budget=4000, only_kind=kind)
    return res or 'Không tìm thấy bản ghi nào khớp.'


_TOOL_FN = {
    'count_bugs': _tool_count_bugs,
    'count_testcases': _tool_count_testcases,
    'count_tasks': _tool_count_tasks,
    'find_records': _tool_find_records,
}


def _dispatch_tool(name, args):
    if not isinstance(args, dict):
        args = {}
    fn = _TOOL_FN.get(name)
    if not fn:
        return json.dumps({'lỗi': f'không có tool {name}'}, ensure_ascii=False)
    try:
        raw, _idx = _load_all()
        return fn(args, raw)
    except Exception:   # noqa: BLE001 — tool lỗi KHÔNG được làm vỡ chat
        return json.dumps({'lỗi': 'tool xử lý lỗi'}, ensure_ascii=False)


MAX_TOOL_ROUNDS = 4
_OPTIONS = {'temperature': 0.3, 'num_ctx': 16384}


def _ollama_chat(msgs, stream, tools=None):
    payload = {'model': OLLAMA_MODEL, 'messages': msgs, 'stream': stream,
               'think': False, 'options': _OPTIONS}
    if tools:
        payload['tools'] = tools
    return requests.post(f'{OLLAMA_URL}/api/chat', json=payload,
                         stream=stream, timeout=(10, 180))


def chat_stream(messages):
    """Generator yield text trả lời. Vòng tool-calling (non-stream) trước: model gọi count_*/
    find_records để lấy số liệu CHÍNH XÁC; xong thì stream câu trả lời cuối. Lỗi -> yield câu
    báo tiếng Việt, KHÔNG raise (đã/ sắp stream 200)."""
    if not CHAT_ENABLED:
        yield '⚠️ Chatbot chưa được bật (thiếu cấu hình OLLAMA_MODEL).'
        return
    history = _sanitize(messages)
    if not history:
        yield 'Bạn muốn hỏi gì nào?'
        return
    msgs = [{'role': 'system', 'content': _system_prompt()}] + history
    try:
        used_tools = False
        for _ in range(MAX_TOOL_ROUNDS):
            r = _ollama_chat(msgs, stream=False, tools=TOOLS)
            r.raise_for_status()
            m = (r.json() or {}).get('message') or {}
            tcs = m.get('tool_calls')
            if not tcs:
                if not used_tools:
                    # Không cần tool (chào hỏi / trả lời từ tổng quan) -> trả thẳng.
                    yield m.get('content') or '…'
                    return
                break   # đã dùng tool -> xuống dưới stream câu trả lời cuối
            used_tools = True
            msgs.append({'role': 'assistant', 'content': m.get('content') or '', 'tool_calls': tcs})
            for tc in tcs:
                fn = tc.get('function') or {}
                args = fn.get('arguments')
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (ValueError, json.JSONDecodeError):
                        args = {}
                result = _dispatch_tool(fn.get('name'), args)
                msgs.append({'role': 'tool', 'tool_name': fn.get('name'), 'content': result})
        # Câu trả lời cuối (đã có kết quả tool trong msgs) — stream, KHÔNG kèm tools nữa.
        resp = _ollama_chat(msgs, stream=True, tools=None)
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, json.JSONDecodeError):
                continue
            chunk = (obj.get('message') or {}).get('content', '')
            if chunk:
                yield chunk
            if obj.get('done'):
                break
    except requests.exceptions.ConnectionError:
        yield ('\n\n⚠️ Không kết nối được tới LLM (Ollama). Kiểm tra Ollama đã chạy trên '
               'máy host chưa (`ollama serve`).')
    except requests.exceptions.Timeout:
        yield '\n\n⚠️ LLM phản hồi quá lâu (timeout). Thử lại với câu ngắn hơn nhé.'
    except Exception:   # noqa: BLE001
        yield '\n\n⚠️ Có lỗi khi gọi LLM. Thử lại sau.'
