"""Analytics (issue #158) — màn hình gom các metric của bug.

Tách metric ra khỏi trang Bugs (`/bug-log`): biểu đồ bug theo dev/dự án + bảng
Tỷ lệ Reopen được chuyển sang đây, kèm chỉ số mới **Valid Bug Rate**
(= Closed / (Tổng bug − Reject)).

Bảng/chart render client-side bởi controller `#analyticsData` trong app_v2.js.
Data nguồn = bug_log_store.load_bug_log() (cache local/property, KHÔNG gọi Jira).
"""
from issues import esc
from task_link import tasks_of
from bug_backlog import (_month_of, _dedup_by_fp, _chart_devs, _valid_counts,
                         _reopen_table, prev_month_backlog, _YM_RE)
from render.base import _json_script
from render.shell import _document_v2


def _cross_metrics(links, tc_links, tc_cases):
    """KPI chéo Task×TC×Bug (KHÔNG theo tháng) — port renderCrossMetrics phía JS (app_v2.js).

    - Coverage = task-có-TC / tổng-task-có-hoạt-động (bug hoặc tc).
    - Density  = tổng-bug-liên-kết / tổng-task-có-hoạt-động.
    - Execution= (Pass+Fail)/Tổng-case · PassRate = Pass/(Pass+Fail).
    Trả counts + pct đã suy sẵn (None khi mẫu số 0) → app chỉ hiển thị (D3)."""
    linked, tc_set, bug_set = set(), set(), set()
    total_bug_linked = 0
    for v in (links or {}).values():
        ts = tasks_of(v)
        if ts:
            total_bug_linked += 1
        for t in ts:
            linked.add(t)
            bug_set.add(t)
    for v in (tc_links or {}).values():
        for t in tasks_of(v):
            linked.add(t)
            tc_set.add(t)
    total_tasks = len(linked)
    tasks_with_tc = len(tc_set)

    p = f = norun = 0
    for c in (tc_cases or []):
        r = c.get('result') or 'norun'
        if r == 'pass':
            p += 1
        elif r == 'fail':
            f += 1
        if r == 'norun':
            norun += 1
    total = len(tc_cases or [])
    executed = total - norun
    return {
        'coverage': {'tasksWithTc': tasks_with_tc, 'totalTasks': total_tasks,
                     'pct': (tasks_with_tc / total_tasks * 100) if total_tasks else None},
        'density': {'totalBugs': total_bug_linked, 'totalTasks': total_tasks,
                    'value': (total_bug_linked / total_tasks) if total_tasks else None},
        'execution': {'total': total, 'executed': executed, 'norun': norun,
                      'pass': p, 'fail': f,
                      'execPct': (executed / total * 100) if total else None,
                      'passRate': (p / executed * 100) if executed else None},
    }


def build_analytics_payload(data, testcases=None, links=None, tc_links=None, backlog=None):
    """Dựng metric analytics ĐÃ TÍNH SẴN cho client mobile (E0.4/android #12) — KHÔNG markup.

    Nguồn chân lý DUY NHẤT: đẩy toàn bộ math đang ở JS (`renderValid`/`renderReopen`/
    `renderMetric`/`renderCrossMetrics`/`computeBacklog` + dedup fingerprint) về backend
    (D3 — app Kotlin chỉ chọn tháng + hiển thị, KHÔNG re-derive). Tái dùng đúng các twin
    parity-verified ở `bug_backlog.py` (đã "PHẢI khớp" bản JS).

    KHÁC web (render_analytics_v2 vẫn embed data thô, JS tự tính client-side): API tính
    LIVE mọi tháng từ cache hiện tại (freeze `chart` là tối ưu chống-trôi riêng của web;
    API phản ánh state cache ngay lúc gọi). Bug đa-dev chia phân số như JS.

    Trả dict: `{syncedAt, months, crossMetrics, metrics}` với
      metrics[ym] = {grand, chart:{dev:{proj:count}}, valid:{total,reject,closed,validPct,rejectPct},
                     reopen:{totalBugs,distinctTotal,devs}, backlog:{prev,total,resolved,stillOpen,newCount,hasSnapshot,bugs}}.
    """
    data = data or {}
    reopen_map = data.get('reopen', {}) or {}
    tc_data = testcases or {}

    synced = data.get('synced_at', '') or ''
    synced_disp = synced.replace('T', ' ')[:16] if synced else 'chưa đồng bộ'

    # Bug thô {key: bug} (giữ field dev_pic/status/… cho các twin — KHÁC _flatten_bugs).
    live = {}
    for f in (data.get('files', {}) or {}).values():
        for k, b in (f.get('bugs', {}) or {}).items():
            live[k] = b

    # Bucket theo SHEET-tháng 'YYYY-MM' (khớp archive()/monthOf JS); bỏ tháng rác không hợp lệ.
    by_month = {}
    for k, b in live.items():
        ym = _month_of(b)
        if _YM_RE.match(ym):
            by_month.setdefault(ym, []).append((k, b))

    metrics = {}
    for ym, kb in by_month.items():
        bugs = [b for _, b in kb]
        dd = _dedup_by_fp(bugs)                       # bug THẬT của tháng (khử bản copy)
        vc = _valid_counts(dd)
        denom = vc['total'] - vc['reject']
        blr = prev_month_backlog(ym, live=live)
        metrics[ym] = {
            'grand': len(dd),
            'chart': _chart_devs(dd),
            'valid': {**vc,
                      'validPct': (vc['closed'] / denom * 100) if denom > 0 else None,
                      'rejectPct': (vc['reject'] / vc['total'] * 100) if vc['total'] else None},
            'reopen': _reopen_table(reopen_map, kb, ym),
            'backlog': {'prev': blr['prev_month'], 'total': blr['total'],
                        'resolved': blr['resolved'], 'stillOpen': blr['still_open'],
                        'newCount': blr['new_count'], 'hasSnapshot': blr['has_snapshot'],
                        'bugs': blr['bugs']},
        }

    return {
        'syncedAt': synced_disp,
        'months': sorted(by_month, reverse=True),     # mới nhất trước (picker tháng)
        'crossMetrics': _cross_metrics(links, tc_links, tc_data.get('cases', [])),
        'metrics': metrics,
    }


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
                'created': (b.get('created', '') or '')[:10],
            })
    return bugs, sorted((m for m in months if m), reverse=True)


def render_analytics_v2(data, user=None, activities=None, testcases=None, links=None,
                        tc_links=None, backlog=None):
    """Trang Analytics: 3 khối metric (Valid Bug Rate · Bug theo dev/dự án · Tỷ lệ Reopen)
    + Tồn đọng T-1 vs Mới phát sinh. Toàn bộ render client-side bởi `#analyticsData`."""
    data = data or {}
    bugs, month_list = _flatten_bugs(data)
    reopen = data.get('reopen', {}) or {}
    backlog = backlog or {}
    backlog_months = backlog.get('months', {}) or {}
    carry_months = backlog.get('carry', {}) or {}
    chart_months = backlog.get('chart', {}) or {}   # freeze chart tháng đã đóng (Decision #47)
    
    tc_data = testcases or {}
    tc_cases = tc_data.get('cases', [])
    tc_folders = tc_data.get('folders', [])
    links = links or {}
    tc_links = tc_links or {}

    synced = data.get('synced_at', '') or ''
    synced_disp = synced.replace('T', ' ')[:16] if synced else 'chưa đồng bộ'

    content = (
        '<div class="page-head"><div>'
        '<h2 class="page-title">Analytics</h2>'
        f'<div class="bl-sub"><span class="bl-dot"></span> Dữ liệu bug đồng bộ: {esc(synced_disp)}</div>'
        '</div></div>'

        # ----- KPI Testcases & Tasks -----
        '<div class="metrics-row" style="display:flex; gap:24px; align-items:stretch; margin-top:0; flex-wrap:wrap;">'
        
        # Test Coverage
        '<div class="card metric-card" style="flex:1; min-width:300px; margin-top:0;">'
        '<div class="metric-header"><div class="table-title"><span>Test Coverage (Độ phủ TC)</span></div></div>'
        '<div class="an-valid" id="anTcCoverageBox"></div>'
        '<div class="bl-reopen-note">Tỷ lệ task có test case / Tổng số task có hoạt động (bug/tc)</div>'
        '</div>'
        
        # Test Execution
        '<div class="card metric-card" style="flex:1; min-width:300px; margin-top:0;">'
        '<div class="metric-header"><div class="table-title"><span>Test Execution & Pass Rate</span></div></div>'
        '<div class="an-valid" id="anTcExecutionBox" style="display:flex; gap:32px;"></div>'
        '<div class="bl-reopen-note">Tiến độ chạy = (Pass+Fail)/Tổng · Pass Rate = Pass/(Pass+Fail)</div>'
        '</div>'
        
        # Bug Density
        '<div class="card metric-card" style="flex:1; min-width:300px; margin-top:0;">'
        '<div class="metric-header"><div class="table-title"><span>Bug Density (Mật độ Bug / Task)</span></div></div>'
        '<div class="an-valid" id="anBugDensityBox"></div>'
        '<div class="bl-reopen-note">Tổng bug / Tổng số task có hoạt động (bug/tc)</div>'
        '</div>'
        
        '</div>' # end metrics-row

        # ----- KPI Valid Bug Rate -----
        '<div class="card metric-card" style="margin-top:24px;">'
        '<div class="metric-header">'
        '<div class="table-title"><span>Valid & Rejected Bug Rate (Tháng)</span></div>'
        '<div class="metric-filter"><span class="material-symbols-rounded ph-light ph-calendar-dots mi-sm"></span> '
        '<select id="anValidMonth"></select></div>'
        '</div>'
        '<div class="an-valid" id="anValidBox" style="display:flex; gap:32px;"></div>'
        '<div class="bl-reopen-note">Valid Bug Rate = Closed / (Tổng bug − Reject) · Rejected Bug Rate = Reject / Tổng bug. '
        'Bug bị Reject coi như không hợp lệ nên loại khỏi mẫu số của Valid Bug Rate.</div>'
        '</div>'

        # ----- metrics row: bar chart + reopen table -----
        '<div class="metrics-row" style="display:flex; gap:24px; align-items:flex-start; margin-top:24px; flex-wrap:wrap;">'

        # bar chart bug theo dev/dự án
        '<div class="card metric-card" style="flex:1; min-width:400px; margin-top:0;">'
        '<div class="metric-header">'
        '<div class="table-title"><span>Bug của Dev theo dự án (Tháng)</span></div>'
        '<div class="metric-filter" style="display:flex; align-items:center; gap:8px;">'
        '<button class="lbtn ghost" id="anExportChart" title="Export PDF ảnh chart" style="padding:4px 8px; font-size:13px;">'
        '<span class="material-symbols-rounded ph-light ph-file-pdf mi-sm"></span> Export PDF</button>'
        '<span class="material-symbols-rounded ph-light ph-calendar-dots mi-sm"></span> <select id="anMetricMonth"></select></div>'
        '</div>'
        '<div id="anMetricCharts" style="padding:20px; display:flex; gap:24px; flex-wrap:wrap; justify-content:center;"></div>'
        '</div>'

        # reopen table
        '<div class="card metric-card" style="flex:1; min-width:400px; margin-top:0;">'
        '<div class="metric-header">'
        '<div class="table-title"><span>Tỷ lệ Reopen — chất lượng fix của dev (Tháng)</span></div>'
        '<div class="metric-filter"><span class="material-symbols-rounded ph-light ph-calendar-dots mi-sm"></span> <select id="anReopenMonth"></select></div>'
        '</div>'
        '<div class="bl-reopen-kpi" id="anReopenKpi"></div>'
        '<div style="overflow-x:auto"><table class="bl-table metric-table"><thead><tr id="anReopenHead"></tr></thead><tbody id="anReopenRows"></tbody></table></div>'
        '<div class="bl-reopen-note">Số lần fix = số lần reopen + 1 nếu bug đang ở trạng thái đã giao fix (Fixed/Closed) — mỗi lần reopen là 1 lần fix bị QA trả lại. '
        'Số reopen dội trước khi bật theo dõi, hoặc round-trip gọn trong 1 nhịp quét, có thể bị sót.</div>'
        '</div>'

        '</div>'  # end metrics-row

        + _json_script('analyticsData', {
            'bugs': bugs, 'months': month_list, 'reopen': reopen,
            'syncedAt': synced_disp,
            'tcData': {'cases': tc_cases, 'folders': tc_folders},
            'bugLinks': links, 'tcLinks': tc_links,
            'backlogMonths': backlog_months,
            'carryMonths': carry_months,
            'chartMonths': chart_months,
        })
    )
    return _document_v2(content, 'analytics', user, activities or [],
                        title='QA Workspace — Analytics')
