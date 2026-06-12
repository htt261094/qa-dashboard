"""Jira REST API access: search, count, changelog authors, and the per-refresh bucket fetch.

PAT is read from config and never logged: network errors are redacted before raising.
"""
import sys
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from config import (JIRA_URL, PAT, USERS, TASK_PTSP_TYPE_ID, actor_name,
                    LEADER_EVAL_NUM_FIELD, LEADER_EVAL_TEXT_FIELD, OFFLINE)
from issues import parse_date

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library missing. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

# Session dùng chung -> tái dùng kết nối (keep-alive), khỏi bắt tay TLS mỗi call.
# urllib3 connection pool thread-safe nên share được giữa các thread của run_parallel.
_SESSION = requests.Session()

# Connect-timeout ngắn cho MỌI call qua _SESSION: khi Jira/VPN down (route blackhole),
# bước TCP connect không có short timeout sẽ treo 15-30s/call -> nhiều call nối nhau làm
# trang (kể cả tab non-Jira, vì chuông notif) treo cả phút + block server single-thread.
# Bọc _SESSION.request ép connect-timeout = _CONNECT_TIMEOUT, GIỮ read-timeout caller truyền
# (số đơn -> (connect, read); None -> mặc định). Fail nhanh -> chuông fail mềm gần như tức thì.
_CONNECT_TIMEOUT = 5  # giây — Jira nội bộ qua VPN connect <1s lúc khoẻ; down thì bỏ sau 5s
_orig_request = _SESSION.request


def _request_short_connect(method, url, **kw):
    t = kw.get('timeout')
    if isinstance(t, (int, float)):
        kw['timeout'] = (min(_CONNECT_TIMEOUT, t), t)
    elif t is None:
        kw['timeout'] = (_CONNECT_TIMEOUT, 30)
    # t là tuple sẵn -> tôn trọng caller
    return _orig_request(method, url, **kw)


_SESSION.request = _request_short_connect

# In-memory cache với TTL 2 phút: giảm số call Jira khi F5 nhanh hoặc nhiều tab.
_CACHE_TTL = 120  # giây
_cache: dict = {}
_cache_lock = threading.Lock()


def _cache_get(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and entry[1] > time.monotonic():
            return entry[0], True
        return None, False


def _cache_set(key, data):
    with _cache_lock:
        _cache[key] = (data, time.monotonic() + _CACHE_TTL)

_DEFAULT_FIELDS = ('summary,status,assignee,reporter,duedate,created,'
                   'resolutiondate,updated,issuetype,comment,priority')


def run_parallel(jobs):
    """jobs = {name: callable() -> value}. Chạy đồng thời (I/O mạng), trả {name: value}.
    Re-raise lỗi đầu tiên (RuntimeError) để do_GET render trang lỗi như cũ."""
    results = {}
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(jobs)))) as ex:
        fut_name = {ex.submit(fn): name for name, fn in jobs.items()}
        for fut in as_completed(fut_name):
            results[fut_name[fut]] = fut.result()
    return results


def _jira_request(jql, max_results, fields=_DEFAULT_FIELDS, expand=None):
    params = {'jql': jql, 'fields': fields, 'maxResults': max_results}
    if expand:
        params['expand'] = expand
    try:
        resp = _SESSION.get(
            f"{JIRA_URL}/rest/api/2/search",
            headers={'Authorization': f'Bearer {PAT}', 'Accept': 'application/json'},
            params=params,
            timeout=30,
        )
        if resp.status_code == 401:
            raise RuntimeError("Jira 401 — PAT sai hoặc hết hạn")
        if resp.status_code == 403:
            raise RuntimeError("Jira 403 — PAT không đủ quyền")
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        msg = str(e).replace(PAT, '<REDACTED>')
        raise RuntimeError(f"Network error: {msg}")


def jira_search(jql, max_results=300, fields=_DEFAULT_FIELDS):
    return _jira_request(jql, max_results, fields=fields).get('issues', [])


def jira_count(jql):
    """Cheap count: maxResults=0 returns only the total, no issue payload."""
    return _jira_request(jql, 0, fields='summary').get('total', 0)


# ===== Activity feed (kéo thẳng từ Jira changelog — device-independent) =====
_ACT_FIELDS = {'status', 'assignee', 'duedate', 'priority', 'summary'}


def _comment_snippet(body, n=140):
    """Rút gọn nội dung comment: gộp xuống dòng/khoảng trắng, cắt ~n ký tự."""
    if not body:
        return ''
    s = ' '.join(str(body).split())
    return s if len(s) <= n else s[:n].rstrip() + '…'


def fetch_activity_feed(days=7, cap=300, max_issues=120, scope_user=None, with_status=False):
    """Reconstruct activity từ Jira changelog/comment trong `days` ngày gần nhất.

    Nguồn = Jira (source of truth), KHÔNG phụ thuộc .last_seen.json → máy nào mở cũng
    thấy y hệt. Mỗi activity có `id` ổn định (key#histId#field / key#cmt#id / key#created)
    để dismiss đồng bộ chéo máy. Trả list dict {id, kind, key, summary, author, when, old, new}.

    scope_user=None -> toàn team; 'quangbm' -> chỉ activity liên quan user đó (QA thường).
    Cache TTL 2 phút (call nặng nhất vì expand=changelog).

    with_status=True -> trả (acts, {key: status_name}) lấy từ CHÍNH issue đã fetch (zero
    extra call) để client vá status real-time (Decision #24). Default False giữ tương thích.
    """
    # Cache độc lập với with_status (luôn lưu tuple (acts, statuses)) -> bell embed (no patch)
    # và poll (patch) DÙNG CHUNG 1 lần fetch changelog (call nặng nhất), không gọi đôi.
    cache_key = f'activity:{days}:{scope_user}'
    cached, hit = _cache_get(cache_key)
    if hit:
        return cached if with_status else cached[0]
    if scope_user is not None and scope_user not in USERS:
        raise ValueError('unknown scope_user')
    start = datetime.now() - timedelta(days=days)
    fallback = None
    if scope_user:
        # Mô hình "watching": QA watch task nào thì thấy MỌI hoạt động trên task đó
        # (PM đổi duedate, người khác comment...). Assignee/reporter thường auto-watch
        # nên watcher là superset. watcher=<người khác> có thể vướng "Manage Watchers"
        # permission của PAT chung -> fallback assignee/reporter để feed không vỡ.
        who = f"watcher = {scope_user}"
        fallback = f"(assignee = {scope_user} OR reporter = {scope_user})"
    else:
        user_list = ', '.join(USERS)
        who = f"(assignee in ({user_list}) OR reporter in ({user_list}))"
    _flds = 'summary,status,assignee,reporter,issuetype,created,comment'

    def _run(clause):
        jql = f"{clause} AND updated >= -{days}d ORDER BY updated DESC"
        return _jira_request(jql, max_issues, expand='changelog', fields=_flds).get('issues', [])

    try:
        issues = _run(who)
    except RuntimeError:
        if fallback is None:
            raise
        issues = _run(fallback)  # PAT không query được watcher người khác -> dùng assignee/reporter
    acts = []
    statuses = {}
    for iss in issues:
        key = iss['key']
        f = iss.get('fields', {})
        summary = f.get('summary') or ''
        statuses[key] = (f.get('status') or {}).get('name') or ''
        cr = parse_date(f.get('created'))
        if cr and cr >= start:
            # Task tạo kèm assignee -> Jira KHÔNG ghi changelog 'assignee' (set lúc tạo, không phải đổi).
            # Lấy assignee hiện tại gắn vào event created để feed hiện "tạo mới + giao cho ai".
            created_act = {'id': f'{key}#created', 'kind': 'created', 'key': key, 'summary': summary,
                           'author': actor_name(f.get('reporter')), 'when': f.get('created')}
            if f.get('assignee'):
                created_act['assignee'] = actor_name(f.get('assignee'))
            acts.append(created_act)
        for h in (iss.get('changelog', {}) or {}).get('histories', []):
            hc = parse_date(h.get('created'))
            if not hc or hc < start:
                continue
            author_obj = h.get('author') or {}
            who = actor_name(author_obj)
            for it in h.get('items', []):
                fid = (it.get('fieldId') or it.get('field') or '').lower().replace(' ', '')
                if fid not in _ACT_FIELDS:
                    continue
                a = {'id': f"{key}#{h.get('id')}#{fid}", 'kind': fid, 'key': key,
                     'summary': summary, 'author': who, 'when': h.get('created')}
                if fid == 'duedate':
                    a['old'] = (it.get('fromString') or '')[:10] or '—'
                    a['new'] = (it.get('toString') or '')[:10] or '—'
                elif fid in ('status', 'priority'):
                    a['old'] = it.get('fromString') or '—'
                    a['new'] = it.get('toString') or '—'
                elif fid == 'assignee':
                    # Tự giao task cho CHÍNH MÌNH = nhiễu -> bỏ. Chỉ giữ khi giao cho người khác.
                    # So danh tính người đổi (author) vs assignee mới qua key/name/displayName
                    # (author hiển thị tên ngắn, assignee có thể là displayName -> không so chuỗi đã resolve).
                    to_key, to_str = it.get('to'), it.get('toString')
                    if to_key and (to_key == author_obj.get('key')
                                   or to_key == author_obj.get('name')
                                   or (to_str and to_str == author_obj.get('displayName'))):
                        continue
                    # Jira DC: from/to = user KEY (account mới = "JIRAUSER10220" ẩn danh),
                    # fromString/toString = tên hiển thị. Resolve qua actor_name để QA ra tên
                    # ngắn (key == username) và người khác ra displayName, KHÔNG lòi key thô.
                    a['old'] = (actor_name({'name': it.get('from'), 'displayName': it.get('fromString')})
                                if it.get('from') else 'Chưa giao')
                    a['new'] = (actor_name({'name': to_key, 'displayName': to_str})
                                if to_key else 'Chưa giao')
                acts.append(a)
        for c in ((f.get('comment') or {}).get('comments') or []):
            cc = parse_date(c.get('created'))
            if not cc or cc < start:
                continue
            raw = c.get('body') or ''
            # Mention = body chứa token [~username] của người đang xem (Jira DC markup).
            mention = bool(scope_user) and f'[~{scope_user}]'.lower() in raw.lower()
            acts.append({'id': f"{key}#cmt#{c.get('id')}", 'kind': 'comment', 'key': key,
                         'summary': summary, 'author': actor_name(c.get('author')),
                         'when': c.get('created'), 'comment_delta': 1,
                         'mention': mention, 'body': _comment_snippet(raw)})
    acts.sort(key=lambda a: a.get('when') or '', reverse=True)
    result = (acts[:cap], statuses)        # luôn cache tuple; non-patch caller lấy result[0]
    _cache_set(cache_key, result)
    return result if with_status else result[0]


def _ptsp_index():
    """Toàn bộ Task-PTSP (key+summary+project), cache TTL 2 phút. 1 call/2p; mọi keystroke
    của type-ahead filter in-memory. JQL không wildcard được trên key -> phải fetch rồi lọc
    substring trong Python (gõ '2717' khớp PSIT1H26-2717)."""
    cached, hit = _cache_get('ptsp_index')
    if hit:
        return cached
    issues = _jira_request(f'issuetype = {TASK_PTSP_TYPE_ID} ORDER BY updated DESC',
                           1000, fields='summary,project').get('issues', [])
    idx = [{'key': i['key'], 'summary': (i.get('fields', {}).get('summary') or ''),
            'project': (i.get('fields', {}).get('project') or {}).get('key') or ''}
           for i in issues]
    _cache_set('ptsp_index', idx)
    return idx


def search_parent_ptsp(query, limit=20):
    """Tìm Task-PTSP làm parent cho sub-task (form tạo sub-task). Read-only, PAT chung.
    Khớp substring trên key HOẶC summary (case-insensitive) — gõ '2717' ra mọi key chứa
    2717, không cần gõ đủ 'PSIT1H26-2717'. Trả [{key, summary, project}]."""
    q = (query or '').strip().lower()
    if len(q) < 2:
        return []
    out = []
    for it in _ptsp_index():
        if q in it['key'].lower() or q in it['summary'].lower():
            out.append(it)
            if len(out) >= limit:
                break
    return out


def _qa_task_index():
    """Toàn bộ task assignee là QA team (key+summary+project+assignee+status), cache TTL 2 phút.
    Cho ô tìm task ở Bug Log: QA muốn link bug tới CHÍNH task QA đang làm (KHÔNG phải Task-PTSP
    của dev). 1 call/2p; lọc substring in-memory như _ptsp_index. ORDER BY updated DESC."""
    cached, hit = _cache_get('qa_task_index')
    if hit:
        return cached
    jql = f"assignee in ({','.join(USERS)}) ORDER BY updated DESC"
    issues = _jira_request(jql, 1000, fields='summary,project,assignee,status').get('issues', [])
    idx = []
    for i in issues:
        f = i.get('fields', {}) or {}
        asg = f.get('assignee') or {}
        idx.append({'key': i['key'], 'summary': f.get('summary') or '',
                    'project': (f.get('project') or {}).get('key') or '',
                    'assignee': asg.get('displayName') or asg.get('name') or '',
                    'status': (f.get('status') or {}).get('name') or ''})
    _cache_set('qa_task_index', idx)
    return idx


def search_qa_tasks(query, limit=20):
    """Tìm task của QA team để link bug (Bug Log linkbar). Khớp substring trên key HOẶC summary
    (case-insensitive). Trả [{key, summary, project, assignee, status}]."""
    q = (query or '').strip().lower()
    if len(q) < 2:
        return []
    out = []
    for it in _qa_task_index():
        if q in it['key'].lower() or q in it['summary'].lower():
            out.append(it)
            if len(out) >= limit:
                break
    return out


def search_people(query, limit=15):
    """Tìm user Jira theo username/tên hiển thị (dropdown Leader). Read-only, PAT chung.
    Trả [{name, display}] (chỉ user active)."""
    q = (query or '').strip()
    if len(q) < 2:
        return []
    try:
        r = _SESSION.get(f"{JIRA_URL}/rest/api/2/user/search", headers=_auth_headers(),
                         params={'username': q, 'maxResults': limit}, timeout=15)
        r.raise_for_status()
        users = r.json()
    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {str(e).replace(PAT, '<REDACTED>')}")
    out = []
    for u in users or []:
        if u.get('active') is False:
            continue
        out.append({'name': u.get('name') or u.get('key') or '',
                    'display': u.get('displayName') or u.get('name') or ''})
    return out


def global_search(query, limit=20):
    """Quick-search TOÀN Jira cho thanh search topbar (gần như search top-nav Jira).
    Khớp theo key, theo SỐ (vd '5125' -> DA61H26-5125, DA51H26-5125...) hoặc text trong
    summary — dùng Jira issue picker (autocomplete native, 1 call) lấy danh sách key, rồi
    1 call `key in (...)` lấy status/assignee/type cho dropdown. Read-only PAT chung.
    Trả [{key, summary, status, assignee, type, project, url}] theo thứ tự picker (match tốt nhất trước)."""
    q = (query or '').strip()
    if len(q) < 2:
        return []
    keys = []
    try:
        r = _SESSION.get(f"{JIRA_URL}/rest/api/2/issue/picker", headers=_auth_headers(),
                         params={'query': q, 'currentJQL': '', 'showSubTasks': 'true',
                                 'showSubTaskParent': 'true'}, timeout=15)
        r.raise_for_status()
        for sec in (r.json().get('sections') or []):
            for it in (sec.get('issues') or []):
                k = it.get('key')
                if k and k not in keys:
                    keys.append(k)
    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {str(e).replace(PAT, '<REDACTED>')}")
    if not keys:
        return []
    keys = keys[:limit]
    order = {k: n for n, k in enumerate(keys)}
    jql = f"key in ({','.join(keys)})"
    issues = _jira_request(jql, limit,
                           fields='summary,status,assignee,issuetype,project').get('issues', [])
    rows = []
    for i in issues:
        f = i.get('fields', {}) or {}
        asg = f.get('assignee') or {}
        rows.append({'key': i['key'], 'summary': f.get('summary') or '',
                     'status': (f.get('status') or {}).get('name') or '',
                     'assignee': asg.get('displayName') or asg.get('name') or '',
                     'type': (f.get('issuetype') or {}).get('name') or '',
                     'project': (f.get('project') or {}).get('key') or '',
                     'url': f"{JIRA_URL}/browse/{i['key']}"})
    rows.sort(key=lambda row: order.get(row['key'], 999))
    return rows


def _devs_in_charge(parent_key):
    """Dev phụ trách = assignee của CÁC sub-task dưới Task-PTSP cha, LOẠI người trong QA list.
    QA task của ta là 1 sub-task của parent này; các sub-task khác do dev làm. Trả list tên
    hiển thị (dedupe, giữ thứ tự). 1 call search. Lỗi -> [] (đừng làm hỏng cả drawer)."""
    if not parent_key:
        return []
    try:
        subs = _jira_request(f'parent = {parent_key}', 50, fields='assignee').get('issues', [])
    except RuntimeError:
        return []
    devs, seen = [], set()
    for it in subs:
        asg = (it.get('fields') or {}).get('assignee') or {}
        name = asg.get('name') or ''
        if not name or name in USERS:        # rỗng hoặc là QA -> bỏ
            continue
        disp = asg.get('displayName') or name
        if disp not in seen:
            seen.add(disp)
            devs.append(disp)
    return devs


def fetch_issue_detail(key):
    """Chi tiết 1 issue cho drawer/comment panel:
    {key, summary, description, status, assignee, duedate, updated, devs, comments:[...]}.
    status/assignee/duedate để drawer dựng được CẢ task không nằm trong bucket (vd CANCELLED).
    updated = ngày update; devs = dev phụ trách (assignee non-QA của sub-task anh em dưới
    Task-PTSP cha). 1 call read-only + (nếu có parent) 1 call lấy dev. comments mới->cũ."""
    data = _jira_request(f'key = {key}', 1,
                         fields='summary,description,comment,status,assignee,duedate,updated,parent,created')
    issues = data.get('issues') or []
    if not issues:
        return {'key': key, 'summary': '', 'description': '', 'status': '',
                'assignee': '', 'duedate': '', 'updated': '', 'devs': [], 'comments': []}
    f = issues[0].get('fields', {})
    comments = []
    for c in ((f.get('comment') or {}).get('comments') or []):
        comments.append({'author': actor_name(c.get('author')),
                         'when': c.get('created'),
                         'body': _comment_snippet(c.get('body'), 600)})
    comments.reverse()  # mới nhất lên đầu
    st = (f.get('status') or {}).get('name') or ''
    asg = f.get('assignee') or {}
    parent_key = (f.get('parent') or {}).get('key') or ''
    return {'key': key, 'summary': f.get('summary') or '',
            'description': _comment_snippet(f.get('description'), 1200),
            'status': st,
            'assignee': asg.get('displayName') or asg.get('name') or '',
            'duedate': f.get('duedate') or '',
            'updated': (f.get('updated') or '')[:10],
            'created': (f.get('created') or '')[:10],
            'devs': _devs_in_charge(parent_key),
            'comments': comments}


# ===== Dismiss state lưu ở Jira user property, TÁCH theo người đăng nhập (email) =====
_READ_PROP = 'qa-dashboard-read'
_USERNAME = None


def _auth_headers(extra=None):
    h = {'Authorization': f'Bearer {PAT}', 'Accept': 'application/json'}
    if extra:
        h.update(extra)
    return h


def _current_username():
    global _USERNAME
    if _USERNAME is None:
        try:
            r = _SESSION.get(f"{JIRA_URL}/rest/api/2/myself", headers=_auth_headers(), timeout=15)
            r.raise_for_status()
            _USERNAME = r.json().get('name') or r.json().get('key')
        except requests.RequestException as e:
            raise RuntimeError(f"Network error: {str(e).replace(PAT, '<REDACTED>')}")
    return _USERNAME


def _ukey(user):
    """Khoá dismiss theo người đăng nhập (email). Local dev (chưa login) -> 'local'."""
    return (user or '').strip().lower() or 'local'


def _load_read_map():
    """Toàn bộ map per-user {email: {activity_id: ts}} từ Jira property.
    Format cũ (flat shared {id: ts}) -> bỏ qua (trả {}), bắt đầu lại per-user."""
    try:
        r = _SESSION.get(f"{JIRA_URL}/rest/api/2/user/properties/{_READ_PROP}",
                         headers=_auth_headers(), params={'username': _current_username()}, timeout=15)
        if r.status_code == 404:
            return {}
        r.raise_for_status()
        val = r.json().get('value') or {}
        d = val.get('dismissed') if isinstance(val, dict) else None
        if not isinstance(d, dict) or not d:
            return {}
        # mới = mỗi value là dict (bucket per-user); cũ = value là string ts -> bỏ
        if all(isinstance(v, dict) for v in d.values()):
            return d
        return {}
    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {str(e).replace(PAT, '<REDACTED>')}")


def _save_read_map(read_map):
    body = json.dumps({'dismissed': read_map, 'updated': datetime.now().isoformat()})
    try:
        _SESSION.put(f"{JIRA_URL}/rest/api/2/user/properties/{_READ_PROP}",
                     headers=_auth_headers({'Content-Type': 'application/json'}),
                     params={'username': _current_username()}, data=body, timeout=15)
    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {str(e).replace(PAT, '<REDACTED>')}")


def load_dismissed(user=None):
    """{activity_id: dismissed_at_iso} RIÊNG của người đăng nhập. {} nếu chưa có."""
    return _load_read_map().get(_ukey(user), {})


def dismiss_activities(user, ids, prune_days=14):
    """Thêm ids vào bucket dismiss CỦA RIÊNG user (theo email), prune entry cũ.
    Người khác không bị ảnh hưởng. Cross-device cho cùng 1 user."""
    if not ids:
        return True
    read_map = _load_read_map()
    key = _ukey(user)
    bucket = read_map.get(key) or {}
    now = datetime.now()
    stamp = now.isoformat()
    for i in ids:
        bucket[i] = stamp
    cutoff = (now - timedelta(days=prune_days)).isoformat()
    read_map[key] = {k: v for k, v in bucket.items() if v >= cutoff}
    _save_read_map(read_map)
    return True


def load_property(key, default=None):
    """Đọc JSON value từ Jira user property `key` (kho shared cross-device). default nếu 404."""
    if OFFLINE:
        raise RuntimeError('offline')   # ngắt mọi call Jira -> caller fallback cache local
    try:
        r = _SESSION.get(f"{JIRA_URL}/rest/api/2/user/properties/{key}",
                         headers=_auth_headers(), params={'username': _current_username()}, timeout=15)
        if r.status_code == 404:
            return default
        r.raise_for_status()
        return r.json().get('value', default)
    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {str(e).replace(PAT, '<REDACTED>')}")


def save_property(key, value):
    """Ghi JSON value vào Jira user property `key`. Raise nếu Jira từ chối/lỗi mạng."""
    if OFFLINE:
        raise RuntimeError('offline')   # ngắt ghi Jira -> caller giữ cache local
    try:
        r = _SESSION.put(f"{JIRA_URL}/rest/api/2/user/properties/{key}",
                         headers=_auth_headers({'Content-Type': 'application/json'}),
                         params={'username': _current_username()}, data=json.dumps(value), timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {str(e).replace(PAT, '<REDACTED>')}")


def verify_pat(candidate_pat):
    """Gọi /myself bằng PAT ứng viên -> trả Jira username (field 'name') nếu hợp lệ, None nếu sai/hết hạn.
    Dùng để xác thực PAT thuộc đúng người trước khi lưu. KHÔNG đụng _SESSION (header Auth khác)."""
    if not candidate_pat or not isinstance(candidate_pat, str):
        return None
    try:
        r = requests.get(f"{JIRA_URL}/rest/api/2/myself",
                         headers={'Authorization': f'Bearer {candidate_pat}', 'Accept': 'application/json'},
                         timeout=15)
        if r.status_code == 200:
            return r.json().get('name') or r.json().get('key')
        return None
    except requests.RequestException:
        return None


def fetch_change_authors(keys):
    """For the given changed issue keys, return {key: {field: latest_author}} from changelog (1 light call)."""
    if not keys:
        return {}
    jql = 'key in (' + ','.join(keys) + ')'
    out = {}
    for issue in _jira_request(jql, len(keys), fields='summary', expand='changelog').get('issues', []):
        m = {}
        for h in (issue.get('changelog', {}) or {}).get('histories', []):  # oldest->newest: overwrite => latest wins
            who = actor_name(h.get('author'))
            for it in h.get('items', []):
                fid = it.get('fieldId') or it.get('field')
                if fid in ('status', 'assignee', 'duedate', 'priority', 'summary'):
                    m[fid] = who
        out[issue['key']] = m
    return out





def fetch_all(scope_user=None):
    """Pull the 3 task buckets + 2 weekly counts. 5 Jira calls — chạy SONG SONG.

    scope_user=None  -> toàn team (admin).
    scope_user='quangbm' -> CHỈ task của user đó (QA thường xem phần mình). Lọc ngay
    ở JQL nên Jira không trả data người khác (server-side, không lộ qua page source).
    Cache TTL 2 phút: F5 liên tiếp trong 2p trả cache, tránh spam Jira.
    """
    cache_key = f'fetch_all:{scope_user}'
    cached, hit = _cache_get(cache_key)
    if hit:
        return cached
    if scope_user is not None and scope_user not in USERS:
        raise ValueError('unknown scope_user')
    if scope_user:
        a_clause = f'assignee = {scope_user}'
        rep_clause = f'reporter = {scope_user}'
    else:
        user_list = ', '.join(USERS)
        a_clause = f'assignee in ({user_list})'
        rep_clause = f'reporter in ({user_list})'
    data = run_parallel({
        'active': lambda: jira_search(
            f"{a_clause} AND statusCategory != Done ORDER BY duedate ASC", max_results=300),
        'new24': lambda: jira_search(
            f"{rep_clause} AND created >= -24h ORDER BY created DESC", max_results=50),
        'done_week': lambda: jira_search(
            f'{a_clause} AND status CHANGED TO "DONE" AFTER -3d ORDER BY updated DESC', max_results=100),
        # weekly inflow vs outflow (count-only, cheap)
        'created_week': lambda: jira_count(f"{a_clause} AND created >= startOfWeek()"),
        'resolved_week': lambda: jira_count(
            f'{a_clause} AND status CHANGED TO "DONE" AFTER startOfWeek()'),
    })
    data['fetched_at'] = datetime.now()
    _cache_set(cache_key, data)
    return data


def fetch_project_categories():
    """Fetch project categories from Jira for filtering."""
    cache_key = 'project_categories'
    cached, hit = _cache_get(cache_key)
    if hit:
        return cached
    try:
        r = _SESSION.get(f"{JIRA_URL}/rest/api/2/projectCategory", headers=_auth_headers(), timeout=15)
        if r.status_code == 200:
            cats = r.json()
            _cache_set(cache_key, cats)
            return cats
        return []
    except Exception:
        return []


def fetch_leader_eval_tasks(category, leader, sel_assignees, year, month):
    import calendar
    _, last_day = calendar.monthrange(year, month)
    start_str = f"{year}-{month:02d}-01"
    end_str = f"{year}-{month:02d}-{last_day}"
    
    parts = []
    if category:
        parts.append(f'category = "{category}"')
        
    parts.append('type in (Task, Sub-task)')
    parts.append('NOT ((statusCategory = Done OR status = PENDING) AND "Leader đánh giá (text)" is not EMPTY)')
    parts.append(f'("Start date" <= "{end_str}" AND duedate >= "{start_str}")')
    
    if leader:
        parts.append(f'Leader = "{leader}"')
        parts.append(f'assignee != "{leader}"')
        
    if sel_assignees:
        incl = ', '.join(f'"{a}"' for a in sel_assignees)
        parts.append(f'assignee in ({incl})')
        
    jql = " AND ".join(parts) + " ORDER BY priority DESC, updated DESC"
    fields = f"{_DEFAULT_FIELDS},{LEADER_EVAL_NUM_FIELD},{LEADER_EVAL_TEXT_FIELD},project"
    return jira_search(jql, max_results=500, fields=fields)
