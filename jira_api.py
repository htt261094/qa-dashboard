"""Jira REST API access: search, count, changelog authors, and the per-refresh bucket fetch.

PAT is read from config and never logged: network errors are redacted before raising.
"""
import sys
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from config import JIRA_URL, PAT, USERS, actor_name
from issues import parse_date

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library missing. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

# Session dùng chung -> tái dùng kết nối (keep-alive), khỏi bắt tay TLS mỗi call.
# urllib3 connection pool thread-safe nên share được giữa các thread của run_parallel.
_SESSION = requests.Session()

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


def fetch_activity_feed(days=7, cap=300, max_issues=120, scope_user=None):
    """Reconstruct activity từ Jira changelog/comment trong `days` ngày gần nhất.

    Nguồn = Jira (source of truth), KHÔNG phụ thuộc .last_seen.json → máy nào mở cũng
    thấy y hệt. Mỗi activity có `id` ổn định (key#histId#field / key#cmt#id / key#created)
    để dismiss đồng bộ chéo máy. Trả list dict {id, kind, key, summary, author, when, old, new}.

    scope_user=None -> toàn team; 'quangbm' -> chỉ activity liên quan user đó (QA thường).
    Cache TTL 2 phút (call nặng nhất vì expand=changelog).
    """
    cache_key = f'activity:{days}:{scope_user}'
    cached, hit = _cache_get(cache_key)
    if hit:
        return cached
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
    for iss in issues:
        key = iss['key']
        f = iss.get('fields', {})
        summary = f.get('summary') or ''
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
    result = acts[:cap]
    _cache_set(cache_key, result)
    return result


def fetch_issue_detail(key):
    """Chi tiết 1 issue cho drawer/comment panel: {key, summary, description, comments:[...]}.
    1 call read-only bằng PAT chung. comments mới->cũ, body rút gọn ~600 ký tự."""
    data = _jira_request(f'key = {key}', 1, fields='summary,description,comment')
    issues = data.get('issues') or []
    if not issues:
        return {'key': key, 'summary': '', 'description': '', 'comments': []}
    f = issues[0].get('fields', {})
    comments = []
    for c in ((f.get('comment') or {}).get('comments') or []):
        comments.append({'author': actor_name(c.get('author')),
                         'when': c.get('created'),
                         'body': _comment_snippet(c.get('body'), 600)})
    comments.reverse()  # mới nhất lên đầu
    return {'key': key, 'summary': f.get('summary') or '',
            'description': _comment_snippet(f.get('description'), 1200),
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


_LINE_FIELDS = _DEFAULT_FIELDS + ',parent,issuelinks'


def _parent_key(issue):
    """Immediate parent key. Native `parent` field first (Sub-task -> Task-PTSP),
    rồi issue-link `is child of` (Task-PTSP -> Task -> Story). None nếu là gốc."""
    fields = issue.get('fields', {})
    p = fields.get('parent')
    if p and p.get('key'):
        return p['key']
    for link in (fields.get('issuelinks') or []):
        t = link.get('type') or {}
        if link.get('inwardIssue') and t.get('inward') == 'is child of':
            return link['inwardIssue']['key']
    return None


def _last_week_window(now=None):
    """[Thứ 2 tuần trước, Thứ 2 tuần này) — cửa sổ báo cáo tuần."""
    now = now or datetime.now()
    this_mon = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return this_mon - timedelta(days=7), this_mon


def fetch_lines(max_results=500, max_depth=8, now=None):
    """QA tasks tuần trước (+ mọi task In Progress/PENDING) gom theo line gốc qua 'is child of'.

    Filter: updated trong cửa sổ tuần trước HOẶC đang In Progress/PENDING (việc dở luôn liệt kê).
    Returns {'qa_issues', 'root_of', 'known', 'window': (start, end)}.
    Calls: 1 (QA tasks) + 1 per ancestry level (usually 1-3). Used only by /report.
    """
    user_list = ', '.join(USERS)
    start, end = _last_week_window(now)
    s, e = start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')
    jql = (f'assignee in ({user_list}) AND ('
           f'status in ("In Progress", "PENDING") '
           f'OR (updated >= "{s}" AND updated < "{e}")) ORDER BY updated DESC')
    qa = jira_search(jql, max_results=max_results, fields=_LINE_FIELDS)
    known = {i['key']: i for i in qa}
    frontier = {pk for i in qa if (pk := _parent_key(i))}
    depth = 0
    while frontier and depth < max_depth:
        need = [k for k in frontier if k not in known]
        if not need:
            break
        for off in range(0, len(need), 200):  # JQL 'key in (...)' batch cap
            chunk = need[off:off + 200]
            for i in jira_search('key in (' + ','.join(chunk) + ')',
                                 max_results=len(chunk), fields=_LINE_FIELDS):
                known[i['key']] = i
        frontier = {pk for k in need if k in known and (pk := _parent_key(known[k]))}
        depth += 1

    parent_of = {k: _parent_key(iss) for k, iss in known.items()}
    return {'qa_issues': qa, 'parent_of': parent_of, 'known': known, 'window': (start, end)}


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
