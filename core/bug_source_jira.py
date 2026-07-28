"""Nguồn bug từ Jira — PLACEHOLDER (Decision #61).

Bối cảnh: hiện bug log kéo từ Google Sheet trên Drive (`bug_log.py` -> `normalize` ->
`bug` dict -> `.bug_log.json`). Sắp tới team sẽ log bug TRỰC TIẾP trên Jira. Module này là
lớp nguồn 'jira' song song với 'drive', cắm vào cùng seam `bug_log_store._scan_one`.

TRẠNG THÁI: STUB. Model bug trên Jira CHƯA chốt (issue type "Bug" riêng? sub-task [QA]?
JQL? project/board?). Khi `config.BUG_LOG_JIRA_ENABLED=False` (mặc định) module HOÀN TOÀN
inert -> KHÔNG gọi Jira, trả rỗng -> luồng Drive production không bị đụng.

Khi công bố model: điền `_fetch_issues()` + `_issue_to_bug()` để trả về ĐÚNG `bug` dict mà
downstream (bug_log_store/bug_backlog/task_link/render) đang tiêu thụ — KHÔNG đổi schema.

Layer: config -> (this). Lazy-import jira_api CHỈ khi fetch thật (giữ layer sạch, tránh cost
khi provider không dùng).
"""
import config


# ===== bug dict — schema downstream đang phụ thuộc (bug_log.normalize) =====
# Mọi tầng sau (store/backlog/task_link/render/analytics) chỉ đọc các key này. Nguồn Jira PHẢI
# xuất ra y hệt tên key. Bảng mapping dự kiến (điền khi model Jira công bố):
#
#   bug dict key    | Jira field (dự kiến)              | Ghi chú
#   ----------------|----------------------------------|-----------------------------------------
#   project         | issue.fields.project.key         | vd DA6, CB24
#   service         | src['service'] (từ source config)| hoặc component Jira
#   bug_no          | issue.key phần số / customfield  | STT hiển thị
#   feature         | component / epic / customfield   | "Chức năng"
#   summary         | issue.fields.summary             |
#   status          | map(issue.fields.status.name)    | -> lifecycle New/Fixing/Fixed/Closed/Reopen/Rejected
#   status_raw      | issue.fields.status.name         | giữ nguyên text Jira cho metric
#   severity        | issue.fields.priority.name / cf  |
#   created         | issue.fields.created[:10]        | 'YYYY-MM-DD'
#   month           | theo created / sprint            | thay tên tab sheet 'Tn'
#   qa_pic          | reporter / QA assignee           | tên đã bỏ dấu
#   dev_pic         | assignee                         | tên đã bỏ dấu
#   handle_time     | changelog created->resolved      | Jira ĐO ĐƯỢC (Sheet không) — metric mới
#   expected        | customfield "Kết quả mong muốn"  | có thể rỗng
#   note            | customfield / comment            | có thể rỗng
#   screenshot_urls | attachments                      | list[str]
#   key             | issue.key (ỔN ĐỊNH)              | dùng làm khoá diff — xem ghi chú dưới
#
# ĐỊNH DANH: Jira issue key ỔN ĐỊNH (khác Sheet — STT/tên sheet đổi khi copy). Khi bật, cân
# nhắc dùng issue key làm `key` + định danh cho reopen/task_link -> có thể BỎ logic carry/
# copy-sheet của bug_backlog (`fingerprint`, `_dedup_by_fp`, `backfill_fingerprints`,
# `_seed_current_reopens`) vốn chỉ tồn tại vì Sheet thiếu ID ổn định. (Chỉ ghi chú, chưa làm.)

_EMPTY_RESULT = {'bugs': [], 'unmapped': [], 'meta': {}, 'pending': True, 'error': None}


def _issue_to_bug(issue, service=''):
    """Map 1 Jira issue -> bug dict (schema ở trên). STUB: chưa parse thật.

    Điền khi model Jira công bố. Phải trả dict đủ 13+ key mà downstream dùng, đặc biệt:
    'key' (ổn định), 'status' (lifecycle), 'status_raw', 'month', 'created', 'project',
    'service', 'summary'. Xem bảng mapping đầu file.
    """
    raise NotImplementedError('bug_source_jira._issue_to_bug: chờ chốt model bug trên Jira')


def _fetch_issues(src):
    """Kéo issue bug từ Jira theo source (JQL/project/board). STUB.

    Khi làm thật: lazy-import jira_api ở ĐÂY (không ở top-level) rồi gọi search với expand
    changelog để tính handle_time/reopen. PAT redact do jira_api lo.
    """
    raise NotImplementedError('bug_source_jira._fetch_issues: chờ chốt model bug trên Jira')


def scan_source(src):
    """Quét 1 nguồn bug Jira -> cùng "hình dạng" mà bug_log_store._scan_one cần để merge.

    Trả: {bugs: list[bug dict], unmapped: list, meta: dict, pending: bool, error: str|None}.

    - config.BUG_LOG_JIRA_ENABLED=False (mặc định) -> pending=True, bugs=[], KHÔNG gọi mạng.
      Store coi đây là no-op (không đụng cache) -> placeholder hoàn toàn vô hại.
    - True (tương lai) -> _fetch_issues + _issue_to_bug. Bọc try/except -> soft-fail per-source
      (giống nhánh Drive), KHÔNG raise ra scan().
    """
    if not config.BUG_LOG_JIRA_ENABLED:
        return dict(_EMPTY_RESULT)
    service = (src or {}).get('service', '') or ''
    try:
        issues = _fetch_issues(src)
        bugs = [_issue_to_bug(it, service=service) for it in issues]
        return {'bugs': bugs, 'unmapped': [], 'meta': {'count': len(bugs)},
                'pending': False, 'error': None}
    except NotImplementedError:
        # Bật toggle nhưng chưa cắm fetch -> vẫn coi là pending (inert), không làm sập scan.
        return dict(_EMPTY_RESULT)
    except Exception as e:  # noqa: BLE001 — soft-fail per-source
        return {'bugs': [], 'unmapped': [], 'meta': {}, 'pending': False,
                'error': f'Jira bug source lỗi: {type(e).__name__}'}
