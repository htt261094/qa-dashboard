"""Jira REST API access: search, count, changelog authors, and the per-refresh bucket fetch.

PAT is read from config and never logged: network errors are redacted before raising.
"""
import sys
import json
import time
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from config import (JIRA_URL, PAT, USERS, TASK_PTSP_TYPE_ID, actor_name,
                    LEADER_EVAL_NUM_FIELD, LEADER_EVAL_TEXT_FIELD, OFFLINE,
                    SNAPSHOT_CACHE_FILE, atomic_write, JIRA_MAX_CONCURRENT)
from issues import parse_date, i_assignee, i_reporter
from remote_store import remote_get, remote_put

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

# Trần số call Jira REST đồng thời (issue #133). ThreadingHTTPServer (#129) + ThreadPool lồng
# (/ outer 3 + fetch_all 5 + refresh nền/scheduler) có thể nhân số request đồng thời lên rất
# nhanh khi nhiều tab -> nguy cơ nện Jira DC hoặc cạn socket/connection pool. Mọi call đều đi
# qua _SESSION.request (monkeypatch dưới) -> đặt semaphore Ở ĐÂY chặn được TẤT CẢ (search,
# property, picker, myself...), kể cả các đường KHÔNG qua _jira_request. 1 acquire/release bọc
# trọn 1 HTTP call (gồm cả urllib3 retry bên trong _orig_request). Không tự gọi đệ quy trong
# lúc giữ slot -> không deadlock. pool_maxsize của _SESSION đặt khớp để slot có socket dùng.
_jira_gate = threading.BoundedSemaphore(JIRA_MAX_CONCURRENT)


def _request_short_connect(method, url, **kw):
    t = kw.get('timeout')
    if isinstance(t, (int, float)):
        kw['timeout'] = (min(_CONNECT_TIMEOUT, t), t)
    elif t is None:
        kw['timeout'] = (_CONNECT_TIMEOUT, 30)
    # t là tuple sẵn -> tôn trọng caller
    with _jira_gate:
        return _orig_request(method, url, **kw)


_SESSION.request = _request_short_connect

# Retry + tự dọn pool sau VPN reconnect: keep-alive (Decision #13) giữ socket sống lâu; khi VPN
# drop->reconnect, socket cũ trong pool thành chết/blackhole. Với max_retries=0 (mặc định) server
# KẸT cho tới khi restart (issue #139). 2 lớp chống:
#  1) Retry adapter: urllib3 retry trên connection/read error -> tự lấy socket MỚI khi gặp chết.
#  2) reset_pool(): đóng toàn bộ pool (cooldown) khi vẫn fail -> request kế tiếp dựng pool sạch.
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except ImportError:                      # urllib3 quá cũ -> bỏ retry, vẫn còn reset_pool
    Retry = None


def _mount_retries(sess):
    # pool_maxsize khớp trần semaphore (#133): tối đa JIRA_MAX_CONCURRENT call đồng thời ->
    # giữ đủ socket keep-alive cho từng slot, khỏi vừa-tạo-vừa-vứt connection khi vượt 10
    # (mặc định urllib3) lúc nhiều tab cùng fetch.
    _pool_kw = {'pool_connections': JIRA_MAX_CONCURRENT, 'pool_maxsize': JIRA_MAX_CONCURRENT}
    if Retry is not None:
        retry = Retry(total=3, connect=3, read=2, status=0, redirect=0,
                      backoff_factor=0.3, raise_on_status=False,
                      allowed_methods=None)   # None = retry MỌI method (call của ta idempotent: GET/PUT/DELETE)
        adapter = HTTPAdapter(max_retries=retry, **_pool_kw)
    else:
        adapter = HTTPAdapter(**_pool_kw)
    sess.mount('https://', adapter)
    sess.mount('http://', adapter)


_mount_retries(_SESSION)

_POOL_RESET_COOLDOWN = 10                 # giây — chống thrash khi run_parallel fail đồng loạt
_pool_reset_at = 0.0
_pool_reset_lock = threading.Lock()


def reset_pool():
    """Đóng mọi keep-alive socket -> request kế tiếp tự dựng pool MỚI (sạch). Gọi khi gặp lỗi
    mạng: pool có thể đang 'nhiễm' socket chết sau VPN flip. Cooldown để không đóng liên tục."""
    global _pool_reset_at
    with _pool_reset_lock:
        now = time.monotonic()
        if now - _pool_reset_at < _POOL_RESET_COOLDOWN:
            return
        _pool_reset_at = now
    try:
        _SESSION.close()                  # close adapter pools; .request monkeypatch giữ nguyên
        _mount_retries(_SESSION)
    except Exception:
        pass

# In-memory cache: giảm số call Jira khi F5 nhanh hoặc nhiều tab.
# - Trong _CACHE_TTL (fresh): trả ngay.
# - _CACHE_TTL..._CACHE_STALE_TTL (stale): trả NGAY data cũ + refresh nền (SWR) -> chuyển
#   tab không block trên call Jira nặng (feed expand=changelog / fetch_all 5 call).
# - Quá _CACHE_STALE_TTL hoặc miss: tính đồng bộ (raise như cũ nếu Jira lỗi).
_CACHE_TTL = 120        # giây — cửa sổ "tươi"
_CACHE_STALE_TTL = 900  # giây — vẫn phục vụ data cũ trong lúc refresh nền (tối đa 15')
_cache: dict = {}       # key -> (data, set_at_monotonic)
_cache_lock = threading.Lock()
_cache_inflight: set = set()   # key đang refresh nền -> chống stampede (nhiều tab cùng lúc)


def _cache_get(key):
    """Fresh-only get (giữ tương thích caller cũ): (data, True) nếu còn trong TTL."""
    with _cache_lock:
        entry = _cache.get(key)
        if entry and entry[1] + _CACHE_TTL > time.monotonic():
            return entry[0], True
        return None, False


def _cache_set(key, data):
    with _cache_lock:
        _cache[key] = (data, time.monotonic())


def _refresh_async(key, producer):
    """Spawn 1 thread refresh cache cho `key` (dedup theo key). Lỗi nền -> nuốt, giữ stale."""
    with _cache_lock:
        if key in _cache_inflight:
            return
        _cache_inflight.add(key)

    def _run():
        try:
            _cache_set(key, producer())
        except Exception:
            pass   # refresh nền hỏng (Jira down...) -> giữ data stale, thử lại lần sau
        finally:
            with _cache_lock:
                _cache_inflight.discard(key)
    threading.Thread(target=_run, daemon=True).start()


def _cached_swr(key, producer):
    """Stale-while-revalidate. producer() -> data (sẽ được cache).
    fresh -> trả ngay; stale -> trả data cũ NGAY + refresh nền; miss/quá-cũ -> tính đồng bộ."""
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
    if entry:
        data, set_at = entry
        age = now - set_at
        if age < _CACHE_TTL:
            return data                       # fresh
        if age < _CACHE_STALE_TTL:
            _refresh_async(key, producer)     # stale -> làm tươi ở nền, KHÔNG block
            return data
    data = producer()                         # miss/quá cũ -> đồng bộ (raise như cũ nếu lỗi)
    _cache_set(key, data)
    return data

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
        reset_pool()                       # pool có thể nhiễm socket chết (VPN flip) -> dọn cho request kế
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
    # SWR: stale -> trả ngay + refresh nền (chuyển tab KHÔNG block trên call này).
    if scope_user is not None and scope_user not in USERS:
        raise ValueError('unknown scope_user')
    cache_key = f'activity:{days}:{scope_user}'
    result = _cached_swr(
        cache_key, lambda: _compute_activity_feed(days, cap, max_issues, scope_user))
    return result if with_status else result[0]


def _compute_activity_feed(days, cap, max_issues, scope_user):
    """Build (acts[:cap], {key:status}) từ Jira changelog. KHÔNG cache (wrapper SWR lo)."""
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
    return (acts[:cap], statuses)          # tuple: (activities, {key:status})


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
    """Toàn bộ map per-user {email: {activity_id: ts}} từ kho chung (KV, sync không cần VPN).
    Format cũ (flat shared {id: ts}) -> bỏ qua (trả {}), bắt đầu lại per-user.
    remote_get nạp lazy để tránh vòng import (remote_store có thể fallback jira_api)."""
    from remote_store import remote_get
    val = remote_get(_READ_PROP) or {}   # raise RuntimeError nếu kho không với tới
    d = val.get('dismissed') if isinstance(val, dict) else None
    if not isinstance(d, dict) or not d:
        return {}
    # mới = mỗi value là dict (bucket per-user); cũ = value là string ts -> bỏ
    if all(isinstance(v, dict) for v in d.values()):
        return d
    return {}


def _save_read_map(read_map):
    from remote_store import remote_put
    remote_put(_READ_PROP, {'dismissed': read_map, 'updated': datetime.now().isoformat()})


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
    Cache SWR: fresh trong 2 phút; stale -> trả ngay + refresh nền (chuyển tab/F5 KHÔNG
    block trên 5 call Jira), data tươi lại ở lần load kế tiếp.
    """
    if scope_user is not None and scope_user not in USERS:
        raise ValueError('unknown scope_user')
    return _cached_swr(f'fetch_all:{scope_user}', lambda: _compute_fetch_all(scope_user))


def _compute_fetch_all(scope_user):
    """5 call Jira (3 search + 2 count) song song. KHÔNG cache (wrapper SWR lo)."""
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
    return data


# ===== Snapshot chéo máy: Cloudflare KV vừa làm cache CHUNG vừa làm kho OFFLINE =====
# Mục tiêu (kết tiếp Decision cloudflare-kv-store):
#  - Ai có VPN fetch full team -> ghi snapshot KV. Người sau (dù có VPN) thấy KV còn tươi
#    (<_CACHE_TTL) -> view THẲNG, KHÔNG gọi Jira -> 1 lượt full fetch/cửa sổ phục vụ cả team.
#  - Mất VPN -> đọc snapshot KV (cũ mấy cũng lấy) -> caller render READ-ONLY.
#  - hash nội dung trùng bản đã đẩy -> KHÔNG PUT (đỡ quota write Cloudflare).
# 3 tầng: L1 = _cache RAM (key 'fetch_all:None'); L2 = Cloudflare KV (chéo máy, cần internet
# công cộng); L3 = cache đĩa local .snapshot_cache.json (#137 — KV không với tới + RAM lạnh
# vẫn serve được, không ra trang lỗi). Luôn full team (__all__); caller scope_data.
_SNAP_KEY = 'qa-snapshot'
_snap_last_hash = None          # hash payload đã PUT gần nhất (per-process) -> dedup PUT
_snap_hash_lock = threading.Lock()


def _snap_serialize(data):
    """fetch_all data -> dict JSON-able cho KV (fetched_at datetime -> ISO)."""
    d = dict(data)
    fa = d.get('fetched_at')
    d['fetched_at'] = fa.isoformat() if hasattr(fa, 'isoformat') else fa
    return d


def _snap_deserialize(raw):
    """KV dict -> fetch_all data (fetched_at ISO -> datetime; hỏng -> now)."""
    d = dict(raw)
    fa = d.get('fetched_at')
    try:
        d['fetched_at'] = datetime.fromisoformat(fa) if isinstance(fa, str) else datetime.now()
    except (TypeError, ValueError):
        d['fetched_at'] = datetime.now()
    return d


def _snap_age(data):
    """Tuổi snapshot theo giây (lớn vô cực nếu thiếu fetched_at)."""
    fa = data.get('fetched_at')
    if not hasattr(fa, 'timestamp'):
        return float('inf')
    return (datetime.now() - fa).total_seconds()


def _snap_payload_hash(data):
    """Hash phần NỘI DUNG (bỏ fetched_at/fetched_by volatile) để dedup PUT."""
    core = {k: data.get(k) for k in
            ('active', 'new24', 'done_week', 'created_week', 'resolved_week')}
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, default=str).encode('utf-8')).hexdigest()


# L3 = cache đĩa local: KV không với tới (mất internet công cộng) + RAM lạnh (mới restart) ->
# vẫn còn bản snapshot trên đĩa để serve read-only thay vì trang lỗi. Đúng pattern Bug Log.
_snap_file_lock = threading.Lock()


def _snap_read_local():
    """Đọc snapshot serialize (fetched_at = ISO str) từ đĩa. None nếu chưa có/hỏng."""
    if SNAPSHOT_CACHE_FILE.exists():
        try:
            d = json.loads(SNAPSHOT_CACHE_FILE.read_text(encoding='utf-8'))
            if isinstance(d, dict) and 'active' in d:
                return d
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _snap_write_local(payload):
    """Ghi snapshot xuống đĩa atomic (tmp + rename) — không bao giờ để lại file rách."""
    with _snap_file_lock:
        atomic_write(SNAPSHOT_CACHE_FILE, json.dumps(payload, ensure_ascii=False))


def _write_snapshot_async(data):
    """Ghi snapshot ở NỀN: LUÔN ghi đĩa local (L3, rẻ, không dedup) + đẩy KV (hash trùng ->
    bỏ qua PUT đỡ quota; KV lỗi -> nuốt, thử lại sau)."""
    h = _snap_payload_hash(data)
    payload = _snap_serialize(data)

    def _run():
        global _snap_last_hash
        _snap_write_local(payload)          # L3 luôn cập nhật, kể cả khi KV PUT bị dedup/lỗi
        with _snap_hash_lock:
            if h == _snap_last_hash:
                return                      # nội dung y bản đã đẩy -> KHỎI PUT (đỡ quota)
        try:
            remote_put(_SNAP_KEY, payload)
            with _snap_hash_lock:
                _snap_last_hash = h
        except RuntimeError:
            pass                            # KV không với tới -> để lần sau
    threading.Thread(target=_run, daemon=True).start()


def fetch_all_shared(fetched_by=None):
    """Pull full team data qua tầng L1 RAM -> L2 KV(tươi) -> L3 đĩa local -> live fetch -> stale.

    Trả (data, stale): stale=True nghĩa là Jira KHÔNG với tới, đang phục vụ snapshot cũ (KV
    hoặc đĩa local) -> caller render read-only + banner. stale=False = data đủ tươi
    (live/cache/KV-fresh/đĩa-fresh).
    data luôn là FULL team (__all__); caller dùng scope_data() để lọc theo người xem.
    """
    key = 'fetch_all:None'
    # L1 — RAM cache còn tươi -> trả ngay (nhanh nhất, không chạm KV)
    with _cache_lock:
        entry = _cache.get(key)
    if entry and (time.monotonic() - entry[1]) < _CACHE_TTL:
        return entry[0], False
    # L2 — snapshot KV còn tươi -> view thẳng, KHÔNG gọi Jira (tối ưu #1)
    snap = None
    try:
        raw = remote_get(_SNAP_KEY)
        if raw:
            snap = _snap_deserialize(raw)
    except RuntimeError:
        snap = None                          # KV không với tới
    # L3 — KV trống/không với tới -> cache đĩa local (offline + RAM lạnh vẫn có cái để serve)
    if snap is None:
        local_raw = _snap_read_local()
        if local_raw:
            snap = _snap_deserialize(local_raw)
    if snap is not None and _snap_age(snap) < _CACHE_TTL:
        _cache_set(key, snap)
        return snap, False
    # cần data tươi -> live fetch full team
    try:
        data = _compute_fetch_all(None)
    except RuntimeError:
        if snap is not None:
            return snap, True                # mất VPN -> snapshot cũ, read-only
        raise                                # KV cũng trống -> trang lỗi như cũ
    data['fetched_by'] = fetched_by
    _cache_set(key, data)
    _write_snapshot_async(data)              # ghi KV nền + dedup hash (tối ưu #2)
    return data, False


def scope_data(data, scope_user):
    """Lọc full-team data xuống đúng view của 1 người (assignee cho active/done, reporter
    cho new24). scope_user=None -> trả nguyên (admin xem cả team). Bỏ weekly count (chỉ
    admin/team dùng -> không lọc được theo người từ count-only query). KHÔNG mutate `data`."""
    if scope_user is None:
        return data
    out = dict(data)
    out['active'] = [i for i in data.get('active', []) if i_assignee(i) == scope_user]
    out['done_week'] = [i for i in data.get('done_week', []) if i_assignee(i) == scope_user]
    out['new24'] = [i for i in data.get('new24', []) if i_reporter(i) == scope_user]
    out['created_week'] = 0
    out['resolved_week'] = 0
    return out


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
