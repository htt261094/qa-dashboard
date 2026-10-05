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
                'service': b.get('service', ''),
                'feature': b.get('feature', ''),
                'month': month,
                'dev': b.get('dev_pic', ''),
                'severity': b.get('severity', '') or '',   # pie severity (#85)
                'created': (b.get('created', '') or '')[:10],
            })
    return bugs, sorted((m for m in months if m), reverse=True)


def render_analytics_v2(data, user=None, activities=None, backlog=None):
    """Trang Analytics (redesign Decision #106) — toàn bộ render client-side bởi `#analyticsData`:
    hàng 4 KPI (Valid · Reject · Reopen · Open) · section Tuổi bug đang mở · 2 cột (chart bug
    theo squad/dev chồng severity | bảng Reopen chất lượng fix + drawer chi tiết) · footer công thức.
    Server chỉ dựng skeleton + id; JS đổ số. Control chung (tháng + Export PDF) nằm ở page-head."""
    data = data or {}
    bugs, month_list = _flatten_bugs(data)
    reopen = data.get('reopen', {}) or {}
    backlog = backlog or {}
    backlog_months = backlog.get('months', {}) or {}
    carry_months = backlog.get('carry', {}) or {}
    chart_months = backlog.get('chart', {}) or {}   # freeze chart tháng đã đóng (Decision #47)

    synced = data.get('synced_at', '') or ''
    synced_disp = synced.replace('T', ' ')[:16] if synced else 'chưa đồng bộ'

    def _kpi_card(cid, title):
        # Card rỗng, JS (renderKpis) đổ badge + số + footer vào .ank-body.
        return (f'<div class="card ank-card" id="{cid}">'
                f'<div class="ank-head"><span class="ank-title">{title}</span>'
                '<span class="ank-badge"></span></div>'
                '<div class="ank-body"></div>'
                '<div class="ank-foot"></div></div>')

    content = (
        # ===== page-head: tiêu đề + sync (trái) · control tháng + Export PDF (phải) =====
        '<div class="page-head an-head">'
        '<div>'
        '<h2 class="page-title">Analytics</h2>'
        f'<div class="bl-sub"><span class="bl-dot"></span> Dữ liệu bug đồng bộ: {esc(synced_disp)}</div>'
        '</div>'
        '<div class="an-ctl">'
        '<div class="an-ctl-month"><select id="anMonth"></select></div>'
        '<button class="an-ctl-export" id="anExport" title="Export PDF biểu đồ bug">'
        '<span class="an-exp-ic"><span class="material-symbols-rounded ph-light ph-file-pdf"></span></span>'
        'Export PDF</button>'
        '</div></div>'

        # ===== hàng 4 KPI =====
        '<div class="ank-row">'
        + _kpi_card('anKpiValid', 'Tỷ lệ Bug Hợp lệ (Valid Rate)')
        + _kpi_card('anKpiReject', 'Tỷ lệ Reject')
        + _kpi_card('anKpiReopen', 'Tỷ lệ Reopen')
        + _kpi_card('anKpiOpen', 'Bug Đang Mở (Open)')
        + '</div>'

        # ===== section: Tuổi bug đang mở =====
        '<div class="card an-sec" id="anAgeSec">'
        '<div class="an-sec-head">'
        '<div><h3 class="an-sec-title">Tuổi bug đang mở '
        '<span class="an-chip-soft">Metric từ Jira</span></h3>'
        '<div class="an-sec-sub">Thời gian tồn đọng của các bug chưa được đóng hoặc giải quyết</div></div>'
        '<div class="an-age-pills" id="anAgePills"></div>'
        '</div>'
        '<div class="an-age-body" id="anAgeDist"></div>'
        '</div>'

        # ===== 2 cột: chart squad/dev | bảng reopen =====
        '<div class="an-grid2">'

        # -- chart bug theo squad & dev, chồng severity --
        '<div class="card an-sec" id="anChartCard">'
        '<div class="an-sec-head an-sec-head-wrap">'
        '<div><h3 class="an-sec-title">Phân bổ Bug theo Squad &amp; Dev '
        '<span class="an-chip-soft" id="anChartSquadBadge"></span></h3>'
        '<div class="an-sec-sub">Bug mới phát sinh trong tháng, nhóm theo squad và lập trình viên</div></div>'
        '<div class="an-chart-stats" id="anChartStats"></div>'
        '</div>'
        '<div class="an-chart-bar">'
        '<div class="an-squad-tabs" id="anSquadTabs"></div>'
        '<div class="an-sev-legend">'
        f'{_sev_legend_html()}'
        '</div></div>'
        '<div id="anMetricCharts" class="an-chart-canvas"></div>'
        '<div id="anBacklogStrip" class="an-backlog"></div>'
        '<div id="anSevStrip" class="an-sevstrip"></div>'
        '</div>'

        # -- bảng Reopen + drawer --
        '<div class="card an-sec" id="anReopenCard">'
        '<div class="an-sec-head">'
        '<div><h3 class="an-sec-title">Tỷ lệ Reopen — Chất lượng fix của Dev '
        '<span class="an-chip-soft" id="anReopenCountBadge"></span></h3>'
        '<div class="an-sec-sub">Đánh giá độ ổn định và chất lượng fix bug qua các đợt QA verify</div></div>'
        '<div class="an-reopen-avg" id="anReopenAvg"></div>'
        '</div>'
        '<div class="an-reopen-tablewrap"><table class="anrt-table">'
        '<thead><tr id="anReopenHead"></tr></thead><tbody id="anReopenRows"></tbody></table></div>'
        '<div class="an-reopen-tip" id="anReopenTip"></div>'
        '<div class="an-reopen-formula">'
        '<strong>Công thức:</strong> Số lần fix = số reopen + 1 (nếu bug đang ở trạng thái đã giao fix '
        'Fixed/Closed). Tỷ lệ reopen = số bug bị reopen / tổng bug dev phụ trách trong tháng. '
        'Chỉ tính bug còn trong dữ liệu; reopen dội trước khi theo dõi có thể bị sót.</div>'
        '</div>'

        '</div>'  # end an-grid2

        # ===== footer công thức =====
        '<div class="an-foot-bar">'
        '<div>Valid Bug Rate = Closed / (Tổng bug − Reject) &nbsp;•&nbsp; '
        'Rejected Bug Rate = Reject / Tổng bug</div>'
        '<div>Jira Bug Intelligence • Đồng bộ thời gian thực</div></div>'

        # ===== drawer chi tiết bug reopen của 1 dev =====
        '<div class="an-drawer" id="anDrawer" aria-hidden="true">'
        '<div class="an-drawer-backdrop" id="anDrawerBackdrop"></div>'
        '<div class="an-drawer-panel" role="dialog" aria-modal="true">'
        '<div class="an-drawer-head">'
        '<div><h3 class="an-drawer-title">Chi tiết Bug bị Reopen '
        '<span class="an-chip-soft" id="anDrawerDev"></span></h3>'
        '<div class="an-sec-sub">Danh sách bug QA trả lại — dữ liệu từ Jira</div></div>'
        '<button class="an-drawer-x" id="anDrawerClose" title="Đóng (Esc)">'
        '<span class="material-symbols-rounded ph-light ph-x"></span></button>'
        '</div>'
        '<div class="an-drawer-body" id="anDrawerBody"></div>'
        '</div></div>'

        + _json_script('analyticsData', {
            'bugs': bugs, 'months': month_list, 'reopen': reopen,
            'syncedAt': synced_disp,
            'backlogMonths': backlog_months,
            'carryMonths': carry_months,
            'chartMonths': chart_months,
        })
    )
    return _document_v2(content, 'analytics', user, activities or [],
                        title='QA Workspace — Analytics')


def _sev_legend_html():
    """Chú thích màu severity cho header chart. Màu khớp SEV_COLOR (JS) — xem Decision #104."""
    items = [('High', '#ff5630'), ('Medium', '#ffab00'), ('Low', '#36b37e')]
    out = ''
    for lbl, col in items:
        out += (f'<span class="an-sev-li"><span class="an-sev-sw" style="background:{col}"></span>{lbl}</span>')
    return out
