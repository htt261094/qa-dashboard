"""Bug Log v2 — bug từ Jira "Bug Testing" (#104) + link native (Relates to Story / parent).

Render shell + source card + tab tháng + bảng bug + filter; bảng render client-side bởi
controller `#bugLogData` trong app_v2.js. Cột "Liên kết" = issue liên quan ĐỌC THẲNG từ Jira
(`bug['tasks']`), KHÔNG còn gắn tay (task_link đã gỡ — #104).
"""
from config import normalize_tester
from issues import esc
from bug_log_store import POLL_SECONDS as BUG_LOG_POLL_SECONDS
from render.base import _json_script
from render.shell import _document_v2


# ===== Bug Log v2 — bug từ Jira "Bug Testing" (#104) =====
def build_bug_log_payload(data, sources=None):
    """Dựng data thuần bug-log từ cache — KHÔNG dựng markup.

    `data`    = bug_log_store.load_bug_log() = {files:{fid:{bugs:{key:bug},...}}, synced_at, reopen}
    `sources` = bug_log_source.load_sources() (optional, cho source card)

    Trả `(bugs, month_list, src_files, synced_disp, synced, reopen)`:
    - bugs       : flat list bug (id/module/severity/status/qa/dev/tasks…). `tasks` = issue liên
                   quan native Jira (parent + Relates) đọc thẳng từ bug dict.
    - month_list : tháng (YYYY-MM) unique, mới nhất trước (tab tháng client-side).
    - src_files  : [{name,project,count}] nguồn đã scan (source card).
    - synced_disp/synced : mốc đồng bộ. reopen: accumulator (embed cho analytics).
    """
    data = data or {}
    files = data.get('files', {}) or {}
    reopen = data.get('reopen', {}) or {}

    bugs = []
    months = set()
    src_files = []
    for fid, f in files.items():
        src_files.append({'name': f.get('name', '') or '(không tên)',
                          'project': f.get('project', ''), 'count': f.get('count', 0)})
        for key, b in (f.get('bugs', {}) or {}).items():
            month = b.get('month', '') or ''
            months.add(month)
            bugs.append({
                'key': key,
                'fid': fid,
                'id': f"{b.get('project', '')}-{b.get('service') + '-' if b.get('service') else ''}{b.get('bug_no', '')}".strip('-'),
                'summary': b.get('summary', ''),
                'module': b.get('feature', ''),
                'severity': b.get('severity', ''),
                'status': b.get('status', ''),
                'project': b.get('project', ''),
                'service': b.get('service', ''),
                'month': month,
                'qa': normalize_tester(b.get('qa_pic', '')),
                'dev': b.get('dev_pic', ''),
                'created': (b.get('created', '') or '')[:10],
                'tasks': list(b.get('tasks', []) or []),   # link native Jira (parent + Relates)
            })
    month_list = sorted((m for m in months if m), reverse=True)

    synced = data.get('synced_at', '') or ''
    synced_disp = synced.replace('T', ' ')[:16] if synced else 'chưa đồng bộ'
    return bugs, month_list, src_files, synced_disp, synced, reopen


def render_bug_log_v2(data, user=None, activities=None, sources=None, pending=None):
    """Tab Bug Log: bảng bug (nguồn = Jira "Bug Testing", cache bug_log_store), tab theo THÁNG
    (tháng tạo), cột "Liên kết" = issue liên quan native Jira (#104). Bảng render client-side
    bởi controller `#bugLogData` trong app_v2.js.

    `data` = bug_log_store.load_bug_log() = {files:{fid:{bugs:{key:bug},...}}, synced_at}
    """
    is_admin = user[1] if (user and len(user) > 1) else True
    (bugs, month_list, src_files,
     synced_disp, synced, reopen) = build_bug_log_payload(data, sources)
    poll_min = max(1, BUG_LOG_POLL_SECONDS // 60)

    # source card: gộp các file Drive nguồn
    if src_files:
        src_names = ' · '.join(esc(s['name']) for s in src_files[:4])
        if len(src_files) > 4:
            src_names += f' +{len(src_files) - 4}'
        total_bugs = len(bugs)
        src_line = f'<b>{src_names}</b> — {total_bugs} bản ghi'
    else:
        src_line = '<b>Chưa lấy được bug nào từ Jira.</b> Bấm “Đồng bộ ngay” để kéo lại.'

    # "Đồng bộ ngay": F5 chỉ render cache, không kéo Jira -> nút này POST /sync-bug-log chạy
    # scan() ngay rồi reload. Admin-only (endpoint gate).
    sync_btn = ('<button class="btn btn-ghost" id="blSyncBtn" title="Kéo lại Bug Testing từ Jira ngay">'
                '<span class="material-symbols-rounded ph-light ph-arrows-clockwise mi-sm"></span> '
                'Đồng bộ ngay</button>') if is_admin else ''
    # Filter lọc-xem (tester/dev/severity/link) — hiện cho MỌI người, chỉ lọc bảng.
    filters_html = (
        '<div class="bl-filter" id="blTesterWrap">'
        '<span class="material-symbols-rounded ph-light ph-user-focus mi-sm"></span>'
        '<select id="blTesterFilter"><option value="">Tất cả tester</option></select>'
        '</div>'
        '<div class="bl-filter" id="blDevWrap">'
        '<span class="material-symbols-rounded ph-light ph-wrench mi-sm"></span>'
        '<select id="blDevFilter"><option value="">Tất cả dev</option></select>'
        '</div>'
        # Lọc theo Severity — ĐÚNG 5 mức field Jira (#104) + "chưa phân loại" (field trống/lạ),
        # option cố định (thang là hằng số field Jira, không build từ data).
        '<div class="bl-filter" id="blSevWrap">'
        '<span class="material-symbols-rounded ph-light ph-gauge mi-sm"></span>'
        '<select id="blSevFilter">'
        '<option value="">Tất cả severity</option>'
        '<option value="blocker">Blocker</option>'
        '<option value="critical">Critical</option>'
        '<option value="high">High</option>'
        '<option value="medium">Medium</option>'
        '<option value="low">Low</option>'
        '<option value="none">Chưa phân loại</option>'
        '</select>'
        '</div>'
        '<div class="bl-filter" id="blLinkWrap">'
        '<span class="material-symbols-rounded ph-light ph-link mi-sm"></span>'
        '<select id="blLinkFilter">'
        '<option value="">Liên kết: tất cả</option>'
        '<option value="linked">Đã liên kết</option>'
        '<option value="unlinked">Chưa liên kết</option>'
        '</select>'
        '</div>'
    )
    # Liên kết bug<->task thủ công đã gỡ (#104): cột "Liên kết" đọc issue liên quan native Jira.
    linkbar = '<div class="bl-linkbar">' + filters_html + '</div>'
    # Export bảng đang xem ra .xlsx. KHÔNG kèm cột liên kết.
    export_btn = ('<button class="btn btn-ghost" id="blExportBtn" title="Xuất bảng đang xem ra Excel">'
                  '<span class="material-symbols-rounded ph-light ph-download-simple mi-sm"></span> '
                  'Export Excel</button>')

    content = (
        '<div class="page-head"><div>'
        '<h2 class="page-title">Bug Management</h2>'
        f'<div class="bl-sub"><span class="bl-dot"></span> Đã đồng bộ: {esc(synced_disp)}</div>'
        f'<div class="bl-next" id="blNextSync" data-synced="{esc(synced)}" data-interval="{BUG_LOG_POLL_SECONDS}">'
        f'<span class="material-symbols-rounded ph-light ph-arrows-clockwise mi-sm"></span> '
        f'Tự đồng bộ từ Jira mỗi {poll_min} phút</div>'
        '</div><div style="display:flex;gap:10px;align-items:center">'
        f'{export_btn}{sync_btn}</div></div>'
        # source card
        '<div class="card bl-source">'
        '<span class="ic material-symbols-rounded ph-light ph-bug-beetle"></span>'
        '<div class="bl-src-info"><div class="lbl">NGUỒN: JIRA — Bug Testing (issuetype 10382)</div>'
        f'<div class="fname" id="blSrcLine">{src_line}</div></div></div>'
        # tab tháng
        '<div class="bl-tabs" id="blTabs"></div>'
        + linkbar
        # thanh tóm tắt: đếm bug tồn đọng (T-1) vs mới trong tháng của tab đang xem
        + '<div class="bl-split" id="blSplitBar" style="display:none"></div>'
        # table
        + '<div class="card"><div class="table-header"><div class="table-title">'
        '<span class="material-symbols-rounded ph-light ph-bug-beetle"></span>'
        '<span>Danh sách Bug / Test Case</span></div>'
        '<div class="bl-count" id="blCount"></div></div>'
        '<div style="overflow-x:auto"><table class="bl-table"><thead><tr>'
        '<th style="width:110px">ID</th><th style="width:140px">Module</th>'
        '<th>Mô tả bug</th><th style="width:110px;white-space:nowrap">Ngày</th>'
        # Severity = ĐÚNG field Jira (Blocker/Critical/High/Medium/Low — #104), cùng thang pie /analytics
        '<th style="width:104px" title="Mức độ nghiêm trọng (field Severity trên Jira). '
        'Field trống hiện —">Severity</th>'
        '<th style="width:140px">Trạng thái</th>'
        '<th style="width:120px">Tester</th><th style="width:130px">Dev in charge</th>'
        '<th style="width:160px" title="Issue liên quan trên Jira (parent + Relates)">Liên kết (Jira)</th>'
        '</tr></thead><tbody id="blRows"></tbody></table></div>'
        '<div class="pager" id="blPager"></div></div>'
        # Các metric (chart bug theo dev/dự án + Tỷ lệ Reopen + Valid Bug Rate) đã
        # chuyển sang màn Analytics (/analytics) — issue #158.
        + (_bug_log_source_modals() if is_admin else '')
        + _json_script('bugLogData', {
            'bugs': bugs, 'months': month_list,
            'syncedAt': synced_disp, 'reopen': reopen,
            # Thay đổi bug-log tích luỹ admin chưa xem (popup tự hiện lúc vào màn). [] khi
            # không có / non-admin -> controller bỏ qua. watermark gửi lại khi báo đã xem.
            'pendingChanges': (pending or {}).get('changes', []),
            'pendingTotal': (pending or {}).get('total', 0),
            'pendingWatermark': (pending or {}).get('watermark', ''),
        })
    )
    return _document_v2(content, 'buglog', user, activities or [],
                        title='QA Workspace — Bug Log')


def _bug_log_source_modals():
    """Popup sau đồng bộ của Bug Log (nguồn Jira — #104, không còn modal quản lý link Drive):
    - #blChgOv : tổng kết thay đổi sau đồng bộ (bug mới / đổi status).
    - #blMissOv: giữ cho tương thích JS (nguồn Jira không có dòng thiếu STT -> không bao giờ hiện)."""
    return (
        # ----- popup tổng kết thay đổi sau đồng bộ (nội dung) -----
        '<div class="overlay" id="blChgOv"><div class="modal bl-pop-modal">'
        '<div class="modal-head"><span class="material-symbols-rounded ph-light ph-git-diff"></span>'
        '<h3>Thay đổi sau đồng bộ</h3>'
        '<button type="button" class="x material-symbols-rounded ph-light ph-x" id="blChgClose"></button></div>'
        '<div class="modal-body"><p class="modal-note" id="blChgSummary"></p>'
        '<div id="blChgList" class="bl-chg-list"></div></div>'
        '<div class="modal-foot">'
        '<button type="button" class="btn btn-primary" id="blChgOk">Đóng &amp; tải lại</button>'
        '</div></div></div>'
        # ----- popup "dòng thiếu STT" (#88) — hiện SONG SONG với popup thay đổi -----
        # Dòng đủ thông tin nhưng chưa đánh STT không có khoá diff -> rơi khỏi mọi metric.
        # Tách popup riêng vì đây là việc phải-làm-tay (mở file đánh lại), khác bản chất với
        # popup thay đổi (chỉ để đọc).
        '<div class="overlay" id="blMissOv"><div class="modal bl-pop-modal">'
        '<div class="modal-head"><span class="material-symbols-rounded ph-light ph-warning-circle"></span>'
        '<h3>Dòng chưa có ID (STT)</h3>'
        '<button type="button" class="x material-symbols-rounded ph-light ph-x" id="blMissClose"></button></div>'
        '<div class="modal-body"><p class="modal-note" id="blMissSummary"></p>'
        '<div id="blMissList" class="bl-miss-list"></div></div>'
        '<div class="modal-foot">'
        '<button type="button" class="btn btn-ghost" id="blMissCopy">Sao chép danh sách</button>'
        '<button type="button" class="btn btn-primary" id="blMissOk">Đã hiểu</button>'
        '</div></div></div>'
    )
