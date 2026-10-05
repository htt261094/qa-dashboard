"""Nguồn bug từ Jira — issue type "Bug Testing" (Decision #104, trước là placeholder #61).

Team log bug trực tiếp trên Jira Cloud bằng issue type **Bug Testing** (id `10382`) thay vì đổ
vào Google Sheet trên Drive. Module này là lớp nguồn `provider='jira'`, cắm vào cùng seam
`bug_log_store._scan_one` -> trả về `bug` dict Y HỆT schema mà downstream (store/backlog/
task_link/render/analytics) đang tiêu thụ, KHÔNG đổi tên key.

Khác Drive ở chỗ Jira có thứ Sheet không có -> đơn giản hoá được:
  - `issue.key` ỔN ĐỊNH -> làm khoá diff/reopen trực tiếp, KHỎI fingerprint/carry.
  - `changelog` đầy đủ -> đếm reopen CHÍNH XÁC (transition `-> Reopened`), không suy từ diff poll.
  - `created` thật -> month = tháng tạo (không còn tab sheet `Tn`).

Lifecycle: workflow Bug Testing (TRIAGE/Open/Reopened/In Progress/TESTING/REJECTED/Done) KHÔNG
nằm trong `jira_cloud.canon_status` -> map lifecycle RIÊNG ở đây (`_bug_lifecycle`).

Layer: config -> (this); lazy-import `jira_api` CHỈ khi fetch thật (giữ layer sạch). PAT redact
do jira_api lo. Toggle `config.BUG_LOG_JIRA_ENABLED` (mặc định BẬT từ #104).
"""
import config


# ===== bug dict — schema downstream đang phụ thuộc (khớp bug_log.normalize) =====
# Mọi tầng sau chỉ đọc các key dưới. Nguồn Jira PHẢI xuất ra y hệt tên key.
#   key(=issue.key, ỔN ĐỊNH) · project(=squad SIT1-4) · service/feature('' — bỏ, #104) ·
#   bug_no(phần số của key) · summary · status(lifecycle) · status_raw · severity(field Severity) ·
#   created('YYYY-MM-DD') · month('YYYY-MM' theo created) · qa_pic(reporter) · dev_pic(assignee) ·
#   screenshot_urls(attachments) · note/expected/handle_time('') · reopen_count(từ changelog — thêm).

_EMPTY_RESULT = {'bugs': [], 'unmapped': [], 'meta': {}, 'pending': True, 'error': None}

# Bug Testing status -> vòng đời nội bộ (New/Fixing/Fixed/Closed/Reopen/Rejected). So lowercase
# để ăn cả tên gốc lẫn tên đã canon ('Done' -> 'DONE'). Status lạ -> giữ nguyên (hiếm).
_LIFECYCLE = {
    'triage': 'New', 'open': 'New', 'to do': 'New',
    'in progress': 'Fixing', 'testing': 'Fixing',
    'reopened': 'Reopen',
    'rejected': 'Rejected', 'reject': 'Rejected',
    'done': 'Closed',
}


def _bug_lifecycle(status_name):
    """Tên status Bug Testing -> vòng đời nội bộ. Không map được -> giữ nguyên text."""
    return _LIFECYCLE.get((status_name or '').strip().lower(), (status_name or '').strip())


def _reopen_count(issue):
    """Số lần bug bị dội lại = số transition status có đích 'Reopened' trong changelog.
    Chính xác tuyệt đối (Jira giữ đủ lịch sử) — thay accumulator diff-poll của nguồn Drive."""
    n = 0
    for h in ((issue.get('changelog') or {}).get('histories') or []):
        for it in (h.get('items') or []):
            if (it.get('field') or '').lower() == 'status' \
                    and (it.get('toString') or '').strip().lower() == 'reopened':
                n += 1
    return n


def _user_name(u):
    """user object (đã normalize: gắn name=username) -> username nội bộ, '' nếu trống."""
    return (u or {}).get('name', '') if isinstance(u, dict) else ''


def _severity(fields):
    """Field Severity (select) -> value string. None/trống -> '' (-> 'none' ở _sev_bucket)."""
    sv = fields.get(config.BUG_SEVERITY_FIELD)
    if isinstance(sv, dict):
        return sv.get('value') or sv.get('name') or ''
    return sv if isinstance(sv, str) else ''


def _issue_to_bug(issue):
    """1 Jira Bug Testing issue (đã normalize) -> bug dict khớp schema bug_log.normalize."""
    f = issue.get('fields') or {}
    key = issue.get('key', '') or ''
    created = (f.get('created') or '')[:10]
    status_raw = ((f.get('status') or {}).get('name') or '').strip()
    bug_no = key.rsplit('-', 1)[-1] if '-' in key else key
    return {
        'key': key,
        'project': (f.get('project') or {}).get('key', '') or '',   # = squad (SIT1-4)
        'service': '', 'feature': '',                                # bỏ (#104)
        'bug_no': bug_no,
        'summary': f.get('summary', '') or '',
        'status': _bug_lifecycle(status_raw),
        'status_raw': status_raw,
        'severity': _severity(f),
        'created': created,
        'month': created[:7],                                        # tháng tạo (không còn tab Tn)
        'qa_pic': _user_name(f.get('reporter')),                     # QA log bug = reporter
        'dev_pic': _user_name(f.get('assignee')),                    # dev fix = assignee
        'screenshot_urls': [a.get('content') for a in (f.get('attachment') or [])
                            if isinstance(a, dict) and a.get('content')],
        'note': '', 'expected': '', 'handle_time': '',              # chưa map (Stage 2 — handle_time)
        'reopen_count': _reopen_count(issue),                        # thêm: tính reopen trực tiếp
    }


_FIELDS = ('summary,status,project,created,resolutiondate,updated,reporter,assignee,attachment,'
           + config.BUG_SEVERITY_FIELD)
_MAX_ISSUES = 3000   # trần an toàn; Bug Testing còn ít, nới sau nếu cần


def _fetch_issues(src):
    """Kéo Bug Testing từ Jira theo JQL của source. Lazy-import jira_api (giữ layer sạch).

    JQL = src['query'] (mặc định config.BUG_TESTING_JQL). expand=changelog để đếm reopen.
    jira_api._jira_request lo phân trang nextPageToken + normalize + retry + redact PAT."""
    from jira_api import _jira_request   # lazy
    jql = (src or {}).get('query', '') or config.BUG_TESTING_JQL
    return _jira_request(jql, _MAX_ISSUES, fields=_FIELDS, expand='changelog').get('issues', [])


def scan_source(src):
    """Quét 1 nguồn bug Jira -> {bugs, unmapped, meta, pending, error} (shape _scan_one cần).

    - BUG_LOG_JIRA_ENABLED=False -> pending (inert, không gọi mạng).
    - Jira lỗi -> soft-fail per-source (error string đã redact), KHÔNG raise ra scan()."""
    if not config.BUG_LOG_JIRA_ENABLED:
        return dict(_EMPTY_RESULT)
    try:
        issues = _fetch_issues(src)
        bugs = [_issue_to_bug(it) for it in issues if it.get('key')]
        return {'bugs': bugs, 'unmapped': [],
                'meta': {'count': len(bugs), 'query': (src or {}).get('query', '')},
                'pending': False, 'error': None}
    except Exception as e:  # noqa: BLE001 — soft-fail per-source (jira_api đã redact PAT trong message)
        return {'bugs': [], 'unmapped': [], 'meta': {}, 'pending': False,
                'error': f'Jira bug source lỗi: {type(e).__name__}: {e}'}
