"""Analytics (issue #158) — màn hình gom các metric của bug.

Tách metric ra khỏi trang Bugs (`/bug-log`): biểu đồ bug theo dev/dự án + bảng
Tỷ lệ Reopen được chuyển sang đây, kèm chỉ số mới **Valid Bug Rate**
(= Closed / (Tổng bug − Reject)).

Bảng/chart render client-side bởi controller `#analyticsData` trong app_v2.js.
Data nguồn = bug_log_store.load_bug_log() (cache local/property, KHÔNG gọi Jira).
"""
from issues import esc
from render.base import _json_script
from render.shell import _document_v2


def _flatten_bugs(data):
    """data = load_bug_log() = {files:{fid:{bugs:{key:bug}}}, reopen, synced_at}.
    Rút các field metric cần: created/dev/project/status/id/summary/key."""
    bugs = []
    months = set()
    for fid, f in (data.get('files', {}) or {}).items():
        for key, b in (f.get('bugs', {}) or {}).items():
            month = b.get('month', '') or ''
            months.add(month)
            bugs.append({
                'key': key,
                'id': f"{b.get('project', '')}-{b.get('service') + '-' if b.get('service') else ''}{b.get('bug_no', '')}".strip('-'),
                'summary': b.get('summary', ''),
                'status': b.get('status', ''),
                'project': b.get('project', ''),
                'month': month,
                'dev': b.get('dev_pic', ''),
                'created': (b.get('created', '') or '')[:10],
            })
    return bugs, sorted((m for m in months if m), reverse=True)


def render_analytics_v2(data, user=None, activities=None):
    """Trang Analytics: 3 khối metric (Valid Bug Rate · Bug theo dev/dự án · Tỷ lệ Reopen).
    Toàn bộ render client-side bởi controller `#analyticsData` (app_v2.js)."""
    data = data or {}
    bugs, month_list = _flatten_bugs(data)
    reopen = data.get('reopen', {}) or {}

    synced = data.get('synced_at', '') or ''
    synced_disp = synced.replace('T', ' ')[:16] if synced else 'chưa đồng bộ'

    content = (
        '<div class="page-head"><div>'
        '<h2 class="page-title">Analytics</h2>'
        f'<div class="bl-sub"><span class="bl-dot"></span> Dữ liệu bug đồng bộ: {esc(synced_disp)}</div>'
        '</div></div>'

        # ----- KPI Valid Bug Rate -----
        '<div class="card metric-card" style="margin-top:0;">'
        '<div class="metric-header">'
        '<div class="table-title"><span>Valid Bug Rate — tỷ lệ bug hợp lệ đã đóng (Tháng)</span></div>'
        '<div class="metric-filter"><span class="material-symbols-rounded mi-sm">calendar_month</span> '
        '<select id="anValidMonth"></select></div>'
        '</div>'
        '<div class="an-valid" id="anValidBox"></div>'
        '<div class="bl-reopen-note">Valid Bug Rate = Closed / (Tổng bug − Reject). '
        'Bug bị Reject coi như không hợp lệ nên loại khỏi mẫu số.</div>'
        '</div>'

        # ----- metrics row: bar chart + reopen table -----
        '<div class="metrics-row" style="display:flex; gap:24px; align-items:flex-start; margin-top:24px; flex-wrap:wrap;">'

        # bar chart bug theo dev/dự án
        '<div class="card metric-card" style="flex:1; min-width:400px; margin-top:0;">'
        '<div class="metric-header">'
        '<div class="table-title"><span>Bug của Dev theo dự án (Tháng)</span></div>'
        '<div class="metric-filter" style="display:flex; align-items:center; gap:8px;">'
        '<button class="lbtn ghost" id="anExportChart" title="Export PDF ảnh chart" style="padding:4px 8px; font-size:13px;">'
        '<span class="material-symbols-rounded mi-sm">picture_as_pdf</span> Export PDF</button>'
        '<span class="material-symbols-rounded mi-sm">calendar_month</span> <select id="anMetricMonth"></select></div>'
        '</div>'
        '<div id="anMetricCharts" style="padding:20px; display:flex; gap:24px; flex-wrap:wrap; justify-content:center;"></div>'
        '</div>'

        # reopen table
        '<div class="card metric-card" style="flex:1; min-width:400px; margin-top:0;">'
        '<div class="metric-header">'
        '<div class="table-title"><span>Tỷ lệ Reopen — chất lượng fix của dev (Tháng)</span></div>'
        '<div class="metric-filter"><span class="material-symbols-rounded mi-sm">calendar_month</span> <select id="anReopenMonth"></select></div>'
        '</div>'
        '<div class="bl-reopen-kpi" id="anReopenKpi"></div>'
        '<div style="overflow-x:auto"><table class="bl-table metric-table"><thead><tr id="anReopenHead"></tr></thead><tbody id="anReopenRows"></tbody></table></div>'
        '<div class="bl-reopen-note">Bug đang ở Reopen được tính tối thiểu 1 lần; số dội trước khi bật theo dõi có thể thấp hơn thực tế. '
        'Round-trip Fixed→Reopen→Fixed gọn trong 10 phút có thể bị sót.</div>'
        '</div>'

        '</div>'  # end metrics-row
        + _json_script('analyticsData', {
            'bugs': bugs, 'months': month_list, 'reopen': reopen,
            'syncedAt': synced_disp,
        })
    )
    return _document_v2(content, 'analytics', user, activities or [],
                        title='QA Workspace — Analytics')
