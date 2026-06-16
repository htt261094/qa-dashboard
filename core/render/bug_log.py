"""Bug Log v2 (issue #55) — bug từ Excel/Drive + link ngược Jira task.

Render shell + source card + tab tháng + bảng bug/test-case + metric cards;
bảng render client-side bởi controller `#bugLogData` trong app_v2.js (tab/tick/
link/pager). Modal admin (đổi link file / quản lý list link Drive) trong
`_bug_log_source_modals`.

Tách từ render/__init__.py (issue #109 / #86). Zero behavior change — chỉ di
chuyển định nghĩa, re-export ở __init__ để chỗ gọi không phải đổi import.
"""
from config import normalize_tester
from issues import esc
from task_link import tasks_of
from bug_log_store import POLL_SECONDS as BUG_LOG_POLL_SECONDS
from render.base import _json_script
from render.shell import _document_v2


# ===== Bug Log v2 (issue #55) — bug từ Excel/Drive + link ngược Jira task =====
def render_bug_log_v2(data, links, editable=True, user=None, activities=None, sources=None):
    """Tab Bug Log: bảng bug/test-case (nguồn = cache bug_log_store), tab theo THÁNG
    (mỗi sheet Excel = 1 tháng — Decision #54), cột "Liên kết Task" = link app-side
    do user tự gán (task_link), KHÔNG từ Excel. Toàn bộ bảng render client-side bởi
    controller `#bugLogData` trong app_v2.js (tab/tick/link/pager).

    `data`  = bug_log_store.load_bug_log() = {files:{fid:{project,bugs:{key:bug},...}}, synced_at}
    `links` = task_link.load_links()       = {bugKey: {task,by,at}}
    """
    data = data or {}
    links = links or {}
    is_admin = user[1] if (user and len(user) > 1) else True
    files = data.get('files', {}) or {}
    reopen = data.get('reopen', {}) or {}

    bugs = []
    months = set()
    src_files = []   # file Drive đã scan (name/project/count) — cho source card; KHÁC `sources` param
    for fid, f in files.items():
        src_files.append({'name': f.get('name', '') or '(không tên)',
                          'project': f.get('project', ''), 'count': f.get('count', 0)})
        for key, b in (f.get('bugs', {}) or {}).items():
            month = b.get('month', '') or ''
            months.add(month)
            link = links.get(key) or {}
            bugs.append({
                'key': key,
                'fid': fid,
                'id': f"{b.get('project', '')}-{b.get('service') + '-' if b.get('service') else ''}{b.get('bug_no', '')}".strip('-'),
                'summary': b.get('summary', ''),
                'module': b.get('feature', ''),
                'severity': b.get('severity', ''),
                'status': b.get('status', ''),
                'project': b.get('project', ''),
                'month': month,
                'qa': normalize_tester(b.get('qa_pic', '')),
                'dev': b.get('dev_pic', ''),
                'created': (b.get('created', '') or '')[:10],
                'tasks': tasks_of(link),
            })
    # tháng mới nhất trước (chuỗi 'YYYY-MM' hoặc tên sheet -> sort desc theo chuỗi)
    month_list = sorted((m for m in months if m), reverse=True)

    synced = data.get('synced_at', '') or ''
    synced_disp = synced.replace('T', ' ')[:16] if synced else 'chưa đồng bộ'
    poll_min = max(1, BUG_LOG_POLL_SECONDS // 60)

    # source card: gộp các file Drive nguồn
    if src_files:
        src_names = ' · '.join(esc(s['name']) for s in src_files[:4])
        if len(src_files) > 4:
            src_names += f' +{len(src_files) - 4}'
        total_bugs = len(bugs)
        src_line = f'<b>{src_names}</b> — {total_bugs} bản ghi'
    else:
        src_line = '<b>Chưa kết nối nguồn Drive nào.</b> Vào Cài đặt để kết nối Google Drive.'

    # "Đồng bộ ngay" (thêm lại 2026-06-10): F5 chỉ render cache, không kéo Drive ->
    # nút này POST /sync-bug-log chạy scan() ngay rồi reload. Admin-only (endpoint gate).
    sync_btn = ('<button class="btn btn-ghost" id="blSyncBtn" title="Đọc lại data mới từ Drive ngay">'
                '<span class="material-symbols-rounded mi-sm">sync</span> '
                'Đồng bộ ngay</button>') if is_admin else ''
    # "Quản lý link drive" = modal CRUD list link đã add.
    drive_btn = ('<button class="btn btn-ghost" id="blManageBtn">'
                 '<span class="material-symbols-rounded mi-sm">link</span> '
                 'Quản lý link drive</button>') if editable else ''
    # ✎ trên source card: đổi link file bug -> hệ thống đi theo link load data (single).
    edit_link_btn = ('<button class="bl-src-edit material-symbols-rounded" id="blEditLinkBtn" '
                     'title="Chọn file bug để xem">folder_open</button>') if editable else ''

    # link-to-task bar (chỉ khi editable: cho tick + tạo link)
    linkbar = ''
    if editable:
        linkbar = (
            '<div class="bl-linkbar">'
            '<div class="bl-filter" id="blTesterWrap">'
            '<span class="material-symbols-rounded mi-sm">person_search</span>'
            '<select id="blTesterFilter"><option value="">Tất cả tester</option></select>'
            '</div>'
            '<div class="bl-ta" id="blTaskTA">'
            '<span class="material-symbols-rounded mi-sm">add_link</span>'
            '<div class="bl-ta-field" id="blTaskChips">'
            '<input type="text" id="blTaskInp" placeholder="Tìm task để liên kết (đã tick ở cột trái)…" autocomplete="off" spellcheck="false">'
            '</div>'
            '<div class="bl-ta-res" id="blTaskRes"></div></div>'
            '<button class="bl-linkbtn" id="blLinkBtn" disabled>'
            '<span class="material-symbols-rounded mi-sm">link</span> Liên kết với Task '
            '<span id="blSelCount"></span></button>'
            '</div>'
        )

    th_check = '<th style="width:40px"><input type="checkbox" class="bl-check" id="blCheckAll"></th>' if editable else ''
    content = (
        '<div class="page-head"><div>'
        '<h2 class="page-title">Bug Management</h2>'
        f'<div class="bl-sub"><span class="bl-dot"></span> Đã đồng bộ: {esc(synced_disp)}</div>'
        f'<div class="bl-next" id="blNextSync" data-synced="{esc(synced)}" data-interval="{BUG_LOG_POLL_SECONDS}">'
        f'<span class="material-symbols-rounded mi-sm">autorenew</span> '
        f'Tự đồng bộ lại toàn bộ file mỗi {poll_min} phút</div>'
        '</div><div style="display:flex;gap:10px;align-items:center">'
        f'{sync_btn}{drive_btn}</div></div>'
        # source card (✎ = đổi link file bug, tự sync sau khi lưu)
        '<div class="card bl-source">'
        '<span class="ic material-symbols-rounded">table_view</span>'
        '<div class="bl-src-info"><div class="lbl">NGUỒN DỮ LIỆU: GOOGLE DRIVE</div>'
        f'<div class="fname" id="blSrcLine">{src_line}</div>'
        '<span class="bl-active-file" id="blActiveFile" style="display:none"></span></div>'
        f'{edit_link_btn}</div>'
        # tab tháng
        '<div class="bl-tabs" id="blTabs"></div>'
        + linkbar
        # table
        + '<div class="card"><div class="table-header"><div class="table-title">'
        '<span class="material-symbols-rounded">bug_report</span>'
        '<span>Danh sách Bug / Test Case</span></div>'
        '<div class="bl-count" id="blCount"></div></div>'
        '<div style="overflow-x:auto"><table class="bl-table"><thead><tr>'
        f'{th_check}'
        '<th style="width:110px">ID</th><th style="width:140px">Module</th>'
        '<th>Mô tả bug</th><th style="width:110px;white-space:nowrap">Ngày</th>'
        '<th style="width:140px">Trạng thái</th>'
        '<th style="width:120px">Tester</th><th style="width:130px">Dev in charge</th>'
        '<th style="width:160px">Liên kết Task</th>'
        '</tr></thead><tbody id="blRows"></tbody></table></div>'
        '<div class="pager" id="blPager"></div></div>'
        # metric cards container
        '<div class="metrics-row" style="display: flex; gap: 24px; align-items: flex-start; margin-top: 24px; flex-wrap: wrap;">'

        # metric card 1 (Pie charts)
        '<div class="card metric-card" style="flex: 1; min-width: 400px; margin-top: 0;">'
        '<div class="metric-header">'
        '<div class="table-title"><span>Metric đo bug của Dev theo dự án (Tháng)</span></div>'
        '<div class="metric-filter" style="display:flex; align-items:center; gap:8px;">'
        '<button class="lbtn ghost" id="btnExportMetricChart" title="Export PDF ảnh chart" style="padding: 4px 8px; font-size: 13px;">'
        '<span class="material-symbols-rounded mi-sm">picture_as_pdf</span> Export PDF</button>'
        '<span class="material-symbols-rounded mi-sm">calendar_month</span> <select id="blMetricMonth"></select></div>'
        '</div>'
        '<div id="blMetricCharts" style="padding: 20px; display: flex; gap: 24px; flex-wrap: wrap; justify-content: center;"></div>'
        '</div>'

        # reopen metric card — chất lượng fix của dev (Decision: issue #69)
        '<div class="card metric-card" style="flex: 1; min-width: 400px; margin-top: 0;">'
        '<div class="metric-header">'
        '<div class="table-title"><span>Tỷ lệ Reopen — chất lượng fix của dev (Tháng)</span></div>'
        '<div class="metric-filter"><span class="material-symbols-rounded mi-sm">calendar_month</span> <select id="blReopenMonth"></select></div>'
        '</div>'
        '<div class="bl-reopen-kpi" id="blReopenKpi"></div>'
        '<div style="overflow-x:auto"><table class="bl-table metric-table"><thead><tr id="blReopenHead"></tr></thead><tbody id="blReopenRows"></tbody></table></div>'
        '<div class="bl-reopen-note">Bug đang ở Reopen được tính tối thiểu 1 lần; số dội trước khi bật theo dõi có thể thấp hơn thực tế. '
        'Round-trip Fixed→Reopen→Fixed gọn trong 10 phút có thể bị sót.</div>'
        '</div>'

        '</div>' # end metrics-row
        + (_bug_log_source_modals() if editable else '')
        + _json_script('bugLogData', {
            'bugs': bugs, 'months': month_list, 'editable': bool(editable),
            'syncedAt': synced_disp, 'reopen': reopen,
            'sources': [{'id': s.get('id', ''), 'label': s.get('label', ''), 'service': s.get('service', ''),
                          'name': (files.get(s.get('id', ''), {}) or {}).get('name', '')}
                        for s in (sources or []) if s.get('id')],
        })
    )
    return _document_v2(content, 'buglog', user, activities or [],
                        title='QA Workspace — Bug Log')


def _bug_log_source_modals():
    """2 modal admin của Bug Log:
    - #blEditOv: đổi link 1 file bug (paste link Drive) — ✎ trên source card.
    - #blSrcOv : quản lý list link Drive đã add (thêm/sửa/xoá) — nút "Quản lý link drive".
    Cả hai POST /save-bug-log-sources (full list) -> server rút file id + scan ngay."""
    return (
        # ----- đổi link 1 file (single) -----
        '<div class="overlay" id="blEditOv"><div class="modal">'
        '<div class="modal-head"><span class="material-symbols-rounded">folder_open</span>'
        '<h3>Chọn file bug để xem</h3>'
        '<button type="button" class="x material-symbols-rounded" id="blEditClose">close</button></div>'
        '<div class="modal-body"><p class="modal-note">Chọn 1 file Drive đã thêm để xem riêng dữ liệu của file đó. '
        'Quản lý (thêm/sửa/xoá link) ở “Quản lý link drive”.</p>'
        '<div id="blPickList" class="bl-pick-list"></div></div>'
        '<div class="modal-foot">'
        '<button type="button" class="btn btn-ghost" id="blEditCancel">Đóng</button>'
        '</div></div></div>'
        # ----- quản lý list link -----
        '<div class="overlay" id="blSrcOv"><div class="modal" style="width:620px">'
        '<div class="modal-head"><span class="material-symbols-rounded">link</span>'
        '<h3>Quản lý link drive</h3>'
        '<button type="button" class="x material-symbols-rounded" id="blSrcClose">close</button></div>'
        '<div class="modal-body"><p class="modal-note">Danh sách file Drive nguồn đã thêm. '
        'Sửa/xoá/thêm link rồi bấm Lưu — hệ thống sẽ đồng bộ ngay.</p>'
        '<div id="blSrcList" class="bl-src-list"></div>'
        '<button type="button" class="btn btn-ghost" id="blSrcAdd" style="align-self:flex-start">'
        '<span class="material-symbols-rounded mi-sm">add</span> Thêm link</button></div>'
        '<div class="modal-foot">'
        '<button type="button" class="btn btn-ghost" id="blSrcCancel">Huỷ</button>'
        '<button type="button" class="btn btn-primary" id="blSrcSave">Lưu &amp; đồng bộ</button>'
        '</div></div></div>'
    )
