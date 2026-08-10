"""Snapshot status per-bug chốt theo tháng — phân biệt bug TỒN ĐỌNG (T-1) vs MỚI phát sinh.

Bối cảnh (hướng B, xử lý lâu dài thay vì tính nhất thời): report tháng cần tách rõ
  - bug MỚI phát sinh trong tháng đang report, và
  - bug TỒN ĐỌNG từ tháng liền trước (T-1) — nợ cũ mang sang, CHỈ T-1, không cộng dồn
    các tháng cũ hơn.

Muốn biết "bug nào còn mở tại thời điểm chuyển tháng" thì phải CHỐT trạng thái theo mốc
thời gian — không tái tạo được từ status hiện tại (status thay đổi liên tục). Module này
chốt mỗi tháng 1 snapshot = trạng thái các bug ĐƯỢC TẠO trong tháng đó, đóng băng khi
sang tháng mới → snapshot['YYYY-MM'] = status cuối tháng của bug tạo trong tháng đó.

Report tháng M:
  - Tồn đọng T-1 = snapshot[M-1] lọc các bug đang MỞ (New/Fixing/Fixed/Reopen).
  - Mới phát sinh trong M = bug live có created ∈ M.

Freeze tự động: mỗi scan ghi đè snapshot của THÁNG HIỆN TẠI (theo wall-clock) = trạng thái
bug tạo trong tháng đó; các tháng trước KHÔNG bị đụng nữa → tự đóng băng ở lần scan cuối
của tháng đó. Bootstrap 1 lần: tháng quá khứ chưa có snapshot → seed từ data hiện tại (gần
đúng, dùng status hôm nay); từ tháng kế tiếp trở đi là chính xác tuyệt đối.

Tồn đọng T-1 CHÍNH XÁC (từ 2026-08 trở đi) dùng `carry` thay cho `months`: mỗi tháng chốt
1 snapshot TẤT CẢ bug đang MỞ (bất kể tạo tháng nào) = nợ mang sang tháng sau, mỗi bug định
danh bằng FINGERPRINT nội dung (project|service|summary — Decision #54) thay cho key sheet — nên khi
team copy bug tồn sang sheet tháng mới (STT + tên sheet đổi) vẫn match được. Report tháng M
dùng carry[M-1], đối chiếu fp với bug live: còn khớp + mở -> "còn treo"; đã đóng / không tìm
thấy -> "đã xử lý". `months` (theo tháng-tạo, khoá theo key sheet) GIỮ làm fallback cho các
tháng chưa có carry (vd 2026-06/07 — bật tính năng carry sau).

Lưu trữ (`.bug_monthly.json` local = cache + KV/property = sync chéo máy qua remote_store):
  { "months": { "YYYY-MM": { key:  {s,c,p,n,d,sv} } },   # theo tháng-tạo (fallback, key sheet)
    "carry":  { "YYYY-MM": { fp:   {s,c,p,sv,n,d}   } },   # bug MỞ cuối tháng đó (id theo fp)
    "updated": iso }
  s=status(lifecycle) · c=created(YYYY-MM-DD) · p=project · n=bug_no · d=dev_pic · sv=service
  fp = project|service|summary đã _norm (lower/gộp-space/trim). Bỏ feature — Decision #54.

Layer: config -> {remote_store} -> (this); bug_log_store nạp LAZY (tránh cycle: bug_log_store
import module này để gọi archive()). Không cycle.
"""
import json
import re
import threading
from datetime import datetime

from config import BUG_MONTHLY_FILE, atomic_write
from remote_store import remote_get, remote_put

BUG_MONTHLY_PROP = 'qa-dashboard-bug-monthly'
_MONTHS_CAP = 24                 # giữ tối đa 24 tháng gần nhất
_CHART_V = 6                     # version freeze chart: bump khi đổi cách bucket -> rebuild snapshot cũ
                                 # (v2 = bucket theo SHEET tháng Tn thay vì created date, 2026-07)
                                 # (v3 = áp filter cột "Bug" = Bug/bug ở tầng parse -> rebuild tháng cũ, 2026-07)
                                 # (v4 = reopen bỏ đếm orphan b-None -> rebuild reopen snapshot, 2026-07)
                                 # (v5 = reopen full attribution: bug nhiều dev tính đủ 1/dev, không chia 1/n, 2026-07)
                                 # (v6 = bl thêm nown/nf/no: bug mới đã fix, KHÔNG gộp tồn đọng T-1, 2026-07)
# 'đã đóng' = Closed / Rejected (Reject); còn lại (New/Fixing/Fixed/Reopen/'') = đang MỞ.
_CLOSED = {'closed', 'rejected', 'reject'}
_lock = threading.Lock()


def _now_iso():
    return datetime.now().isoformat()


def is_open(status):
    """True nếu status tính là ĐANG MỞ (tồn đọng). Closed/Rejected -> đóng."""
    return (status or '').strip().lower() not in _CLOSED


def _prev_month(month):
    """'YYYY-MM' -> tháng liền trước 'YYYY-MM'."""
    y, m = int(month[:4]), int(month[5:7])
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def _rec(b):
    """1 bug -> record snapshot gọn (chỉ field cần cho báo cáo tồn đọng)."""
    return {
        's': b.get('status', '') or '',
        'c': (b.get('created', '') or '')[:10],
        'p': b.get('project', '') or '',
        'n': str(b.get('bug_no', '') or ''),
        'd': b.get('dev_pic', '') or '',
        'sv': b.get('service', '') or '',
    }


# ===== Fingerprint theo NỘI DUNG (định danh bền qua việc copy sang sheet tháng mới) =====
# key sheet cũ = {project}#{service}#{sheet}#{STT} -> đổi khi copy sang tháng mới (sheet + STT
# đổi). Fingerprint = project|service|summary (thứ KHÔNG đổi khi copy nguyên nội dung).
# CỐ Ý BỎ `feature` (Decision #54, 2026-07-16): team hay đổi tên cột "Chức năng" khi bê bug
# tồn sang sheet tháng mới (vd 'Nhập file'->'Lọc kỳ tháng', 'Danh sách đối chiếu công nợ ngày'
# ->'BBĐS ngày') -> fp đứt -> bug đã Closed ở T7 vẫn bị đếm là tồn đọng oan. summary là tín
# hiệu mạnh + ổn định nhất; feature volatile nên loại. _norm PHẢI khớp y hệt bản JS trong
# app_v2.js (_bnorm) để match 2 phía: lower + gộp khoảng trắng + trim; KHÔNG bỏ dấu (để Python
# == JS tuyệt đối, tránh lệch NFKD).
def _norm(s):
    return ' '.join((s or '').strip().lower().split())


def fingerprint(b):
    """Fingerprint nội dung của 1 bug = project|service|summary (đã _norm). CỐ Ý KHÔNG gồm
    `feature` (Decision #54) vì cột "Chức năng" hay bị đổi lúc copy sang sheet tháng mới.
    Định danh bền qua việc copy sang sheet tháng mới (STT + tên sheet đổi, key đổi).
    Public: dùng chung cho task_link (link ngược task theo nội dung, không theo key sheet)."""
    return '|'.join((_norm(b.get('project', '')), _norm(b.get('service', '')),
                     _norm(b.get('summary', ''))))


def _fp(b):
    return fingerprint(b)


# ===== Aggregate cho chart "Bug của Dev theo dự án" (freeze tháng đã đóng — Decision #47) =====
_DEV_SPLIT = re.compile(r'[,;+&/]')
_YM_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')   # 'YYYY-MM' hợp lệ (loại created rác DD/MM/YYYY)

# Tháng của bug theo tên SHEET (Tn) — chính sách mới 2026-07: team log bug theo đúng sheet
# tháng T, KHÔNG theo created date. Map tên sheet -> 'YYYY-MM'. PHẢI khớp monthOf() phía JS.
_T_SHEET_Y = re.compile(r'^T(\d{1,2})(\d{4})$')   # 'T12026' -> tháng 1 / năm 2026 (năm tường minh)
_T_SHEET = re.compile(r'^T(\d{1,2})$')            # 'T7' -> tháng 7, năm lấy từ created


def _month_of(b):
    """Tháng của bug theo tên SHEET (Tn) -> 'YYYY-MM'. 'Tn' bare lấy năm từ created (T7 bug
    created tháng 6 vẫn thuộc T7); 'Tn<yyyy>' có năm tường minh; sheet module/không phải Tn
    -> fallback created date. PHẢI khớp monthOf() phía JS (app_v2.js)."""
    mo = (b.get('month', '') or '').strip()
    m = _T_SHEET_Y.match(mo)
    if m:
        mm = int(m.group(1))
        if 1 <= mm <= 12:
            return f"{int(m.group(2)):04d}-{mm:02d}"
    m = _T_SHEET.match(mo)
    if m:
        mm = int(m.group(1))
        if 1 <= mm <= 12:
            cr = b.get('created', '') or ''
            yy = cr[:4] if len(cr) >= 4 and cr[:4].isdigit() else datetime.now().strftime('%Y')
            return f"{yy}-{mm:02d}"
    cr = b.get('created', '') or ''
    return cr[:7] if len(cr) >= 7 else ''


def _dedup_by_fp(bugs):
    """List bug -> giữ 1 bản đại diện / fingerprint (created MỚI NHẤT thắng — khớp
    dedupByFp phía JS). Dùng để đếm bug THẬT của 1 tháng (khử bản copy sang sheet khác)."""
    by = {}
    for b in bugs:
        f = _fp(b)
        p = by.get(f)
        if p is None or (b.get('created', '') or '') >= (p.get('created', '') or ''):
            by[f] = b
    return list(by.values())


def _split_devs(s):
    """'A,B' -> ['A','B']; rỗng -> ['Chưa gán'] (khớp split JS renderMetric/renderReopen)."""
    dl = [x.strip() for x in _DEV_SPLIT.split((s or '').strip()) if x.strip()]
    return dl or ['Chưa gán']


def _chart_devs(bugs):
    """{dev: {project: count}} — bug đa-dev chia phân số (1/n), khớp renderMetric phía JS."""
    devs = {}
    for b in bugs:
        dl = _split_devs(b.get('dev_pic', ''))
        frac = 1.0 / len(dl)
        proj = (b.get('project', '') or '').strip() or 'Khác'
        for d in dl:
            devs.setdefault(d, {})
            devs[d][proj] = devs[d].get(proj, 0) + frac
    return devs


def _bug_id(b):
    """Id hiển thị = project-[service-]bug_no (khớp _flatten_bugs phía render/JS)."""
    p, sv, n = (b.get('project', '') or '', b.get('service', '') or '',
                b.get('bug_no', '') or '')
    return f"{p}-{sv + '-' if sv else ''}{n}".strip('-')


_RE_REJECT = re.compile(r'reject', re.I)          # khớp isReject JS: /reject/i
_RE_CLOSED = re.compile(r'closed|đã đóng', re.I)  # khớp isClosed JS: /closed|đã đóng/i


def _valid_counts(bugs):
    """Valid Bug Rate counts trên tập ĐÃ dedup fp: {total, reject, closed}. Rate suy ở client."""
    return {
        'total': len(bugs),
        'reject': sum(1 for b in bugs if _RE_REJECT.search(b.get('status', '') or '')),
        'closed': sum(1 for b in bugs if _RE_CLOSED.search(b.get('status', '') or '')),
    }


# ===== Severity — pie chart Analytics + report CTO (Decision #85) =====
# Các file bug log dùng LẪN 2 thang chữ cho cùng 1 mức (team đổi cách gõ theo thời điểm), nên
# user chốt 2026-08-10 quy về ĐÚNG 3 mức: Major=High · Normal=Medium · Minor=Low.
# Blocker/Critical (nếu ai đó gõ) gom vào Major — thang chỉ có 3 bậc, đây là bậc cao nhất.
# Ô trống + giá trị lạ + sai chính tả không map được -> 'none' (Chưa phân loại): KHÔNG vẽ trong
# pie (user chốt pie chỉ 3 mức) nhưng vẫn trả về để hiển thị/report thành ghi chú — bỏ hẳn thì
# mẫu số biến mất, CTO tưởng tháng đó chỉ có ngần ấy bug.
# PHẢI khớp SEV_MAP/SEV_ORDER/SEV_PIE/sevOf phía JS (app_v2.js) — twin Python↔JS.
_SEV_ORDER = ('major', 'normal', 'minor', 'none')
_SEV_PIE = ('major', 'normal', 'minor')      # mức được vẽ trong pie
_SEV_LABEL = {
    'major': 'Major (High)', 'normal': 'Normal (Medium)', 'minor': 'Minor (Low)',
    'none': 'Chưa phân loại',
}
_SEV_MAP = {
    'major': 'major', 'high': 'major', 'cao': 'major',
    'blocker': 'major', 'critical': 'major', 'crit': 'major',
    'nghiêm trọng': 'major', 'nghiem trong': 'major',
    'normal': 'normal', 'medium': 'normal', 'trung bình': 'normal', 'trung binh': 'normal',
    'minor': 'minor', 'minior': 'minor', 'low': 'minor', 'thấp': 'minor', 'thap': 'minor',
    'trivial': 'minor',
}


def _sev_bucket(raw):
    """Giá trị cột Severity thô -> 1 trong _SEV_ORDER. Trống/không map được -> 'none'."""
    return _SEV_MAP.get(_norm(raw), 'none')


def severity_counts(report_month=None, live=None):
    """Phân bố severity của bug MỚI PHÁT SINH trong tháng `report_month` ('YYYY-MM').

    Cùng tập bug với biểu đồ cột "Bug của Dev theo dự án" (dòng nằm trong sheet tháng T VÀ
    created trong T — Decision #75) để `total` khớp "Tổng số bug" của bar chart, tránh lặp lại
    vụ 2 màn đo 2 định nghĩa. Đếm DÒNG, KHÔNG dedup fp, tính LIVE mọi tháng (bar chart cũng
    LIVE — freeze #47/#69 chỉ áp cho Valid Bug Rate + Reopen).
    PHẢI khớp sevCounts() phía JS (app_v2.js).

    Trả {month, total, classified, counts:{bucket:n}, order, pie, labels}:
      total      = mọi bug mới trong tháng
      classified = total − counts['none'] = mẫu số của % trong pie."""
    if not report_month:
        report_month = datetime.now().strftime('%Y-%m')
    live = live if live is not None else _live_bugs()
    counts = {k: 0 for k in _SEV_ORDER}
    total = 0
    for b in live.values():
        if _month_of(b) != report_month:
            continue
        if (b.get('created', '') or '')[:7] != report_month:
            continue
        counts[_sev_bucket(b.get('severity', ''))] += 1
        total += 1
    return {'month': report_month, 'total': total,
            'classified': total - counts['none'], 'counts': counts,
            'order': list(_SEV_ORDER), 'pie': list(_SEV_PIE), 'labels': dict(_SEV_LABEL)}


def _reopen_table(reopen_map, kb, ym):
    """Bảng Tỷ lệ Reopen cho tháng `ym` — replicate renderReopen phía JS (RAW, KHÔNG dedup:
    giữ nguyên semantics live, freeze chỉ để chặn trôi). kb = [(key, bug)] bug tạo trong ym.
    Trả {totalBugs, distinctTotal, devs:{dev:{nb,fx,denom,detail:[{id,summary,reopen,fix}]}}}."""
    bugs_per_dev, bug_by_key = {}, {}
    total_bugs = len(kb)
    for key, b in kb:
        # Full attribution: bug do NHIỀU dev cùng fix -> mỗi dev tính ĐỦ 1 (KHÔNG chia phân
        # số 1/n) -> số nguyên, dễ đọc (user chốt 2026-07-15: "để thẳng là 6 bug"). Hệ quả:
        # sum(bugs_per_dev) có thể > total_bugs (bug chung đếm cho cả 2) — chấp nhận.
        for d in _split_devs(b.get('dev_pic', '')):
            bugs_per_dev[d] = bugs_per_dev.get(d, 0) + 1
        if key:
            bug_by_key[key] = b
    distinct_per_dev, fix_per_dev, detail_per_dev, distinct_total = {}, {}, {}, 0
    for key, r in (reopen_map or {}).items():
        cnt = float(r.get('count') or 0)
        if cnt <= 0:
            continue
        b = bug_by_key.get(key)
        # CHỈ đếm bug CÒN trong current bugs của tháng. Entry orphan (bug đã rời file: bị
        # xoá, đổi tên sheet, HOẶC bị filter cột "Bug") -> BỎ, để tử số/mẫu số cùng trên
        # một tập bug thật (data clean, filter-consistent). Bỏ nhánh fallback b-None cũ
        # (Decision #48/#30) -> reopen_map monotonic vẫn giữ lịch sử nhưng KHÔNG hiển thị
        # cho bug không còn hiện diện.
        if b is None:
            continue
        dev_str = (b.get('dev_pic', '') or '') or 'Chưa gán'
        # Số lần fix = SUY từ count + trạng thái hiện tại, KHÔNG đọc accumulator `fix` cũ
        # (accumulator đếm transition vào status literal 'Fixed' — team hay skip Fixing→Closed
        # nên undercount, đẻ ra ca vô lý "2 reopen 1 fix"). Mỗi reopen = 1 fix bị QA trả lại;
        # +1 nếu bug đang ở trạng thái đã-giao-fix.
        fx = cnt + (1.0 if (b.get('status', '') or '') in ('Fixed', 'Closed') else 0.0)
        distinct_total += 1
        # Full attribution (như mẫu số): mỗi dev cùng fix bug này tính ĐỦ số reopen/fix,
        # KHÔNG chia phân số -> chi tiết hiện số nguyên "N lần reopen · M lần fix".
        for d in _split_devs(dev_str):
            distinct_per_dev[d] = distinct_per_dev.get(d, 0) + 1
            fix_per_dev[d] = fix_per_dev.get(d, 0) + fx
            detail_per_dev.setdefault(d, []).append({
                'id': _bug_id(b),
                'summary': b.get('summary', ''),
                'reopen': cnt, 'fix': fx,
            })
    devs = {d: {'nb': distinct_per_dev[d], 'fx': fix_per_dev.get(d, 0),
                'denom': bugs_per_dev.get(d, 0), 'detail': detail_per_dev.get(d, [])}
            for d in distinct_per_dev}
    return {'totalBugs': total_bugs, 'distinctTotal': distinct_total, 'devs': devs}


def _carry_rec(b):
    """Record cho carry snapshot (định danh theo fp; giữ field để hiển thị + id)."""
    return {
        's': b.get('status', '') or '',
        'c': (b.get('created', '') or '')[:10],
        'p': b.get('project', '') or '',
        'sv': b.get('service', '') or '',
        'n': str(b.get('bug_no', '') or ''),
        'd': b.get('dev_pic', '') or '',
    }


# ===== Lưu trữ (cache local + remote KV/property qua remote_store) =====
def _read_cache():
    if BUG_MONTHLY_FILE.exists():
        try:
            d = json.loads(BUG_MONTHLY_FILE.read_text(encoding='utf-8'))
            if isinstance(d, dict) and ('months' in d or 'carry' in d):
                return d
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _load():
    """Union tháng từ remote + cache (remote thắng khi trùng key; tháng chỉ-có-ở-cache vẫn
    giữ để không mất snapshot đã đóng băng). remote không với tới -> chỉ cache."""
    remote = None
    try:
        d = remote_get(BUG_MONTHLY_PROP)
        if isinstance(d, dict) and ('months' in d or 'carry' in d):
            remote = d
    except RuntimeError:
        pass
    cached = _read_cache()
    months, carry, chart, frozen = {}, {}, {}, {}
    if cached:
        months.update(cached.get('months', {}) or {})
        carry.update(cached.get('carry', {}) or {})
        chart.update(cached.get('chart', {}) or {})
        frozen.update(cached.get('frozen', {}) or {})
    if remote:
        months.update(remote.get('months', {}) or {})
        carry.update(remote.get('carry', {}) or {})
        chart.update(remote.get('chart', {}) or {})
        frozen.update(remote.get('frozen', {}) or {})
    updated = max((cached or {}).get('updated', '') or '',
                  (remote or {}).get('updated', '') or '')
    return {'months': months, 'carry': carry, 'chart': chart, 'frozen': frozen,
            'updated': updated}


def load_backlog():
    """Data snapshot tháng hiện tại (để render / embed). {months:{}, updated:''} nếu chưa có."""
    return _load()


def _chart_entry(kb, ym, reopen_map, live, frozen_at=None):
    """Dựng 1 entry `chart[ym]` từ bug của SHEET tháng ym. kb = [(key, bug)].
    frozen_at (iso) -> đánh dấu snapshot CHỐT CỨNG (freeze_month), archive() sẽ không đụng nữa."""
    bugs = [b for _, b in kb]
    dd = _dedup_by_fp(bugs)
    blr = prev_month_backlog(ym, live=live)
    entry = {
        '_v': _CHART_V,
        'grand': len(dd),
        'devs': _chart_devs(dd),
        'valid': _valid_counts(dd),
        'reopen': _reopen_table(reopen_map, kb, ym),
        'bl': {'nc': blr['new_count'], 'tot': blr['total'], 'res': blr['resolved'],
               'so': blr['still_open'], 'prev': blr['prev_month'],
               'has': blr['has_snapshot'],
               # bug mới (đã loại fp tồn đọng T-1): tổng / đã fix / chưa fix
               'nown': blr['new_own'], 'nf': blr['new_fixed'],
               'no': blr['new_open']},
    }
    if frozen_at:
        entry['_frozen'] = True
        entry['frozen_at'] = frozen_at
    return entry


def archive(cur_bugs, reopen_map=None):
    """Chốt snapshot cho THÁNG HIỆN TẠI + bootstrap tháng quá khứ còn thiếu. Gọi từ scan().

    cur_bugs = {key: bug} — TẤT CẢ bug đang quan sát (mọi tháng). reopen_map (optional) =
    accumulator reopen (để freeze bảng Tỷ lệ Reopen theo tháng). Chỉ ghi khi có thay đổi thật
    (dedup) để đỡ quota KV. Tháng đã đóng băng (< tháng hiện tại, đã có snapshot) KHÔNG bị
    đụng. Tháng đã CHỐT CỨNG qua freeze_month() (có trong `frozen`) cũng KHÔNG bị đụng, kể cả
    khi vẫn là tháng hiện tại. Soft-fail: remote lỗi -> giữ cache local, lần sau đẩy lại."""
    now_month = datetime.now().strftime('%Y-%m')
    # `months` (dùng cho backlog T-1) vẫn theo THÁNG TẠO (created) — Decision #46 giữ nguyên.
    # `chart` (Valid/dev/reopen) bucket theo SHEET tháng (Tn) — chính sách mới 2026-07.
    by_cm = {}
    bugs_by_sheet = {}                               # {ym: [(key, bug)]} theo SHEET, cho chart snapshot
    for key, b in cur_bugs.items():
        cm = (b.get('created', '') or '')[:7]
        if len(cm) == 7 and cm <= now_month:
            by_cm.setdefault(cm, {})[key] = _rec(b)
        sm = _month_of(b)                            # tháng theo sheet Tn
        if _YM_RE.match(sm) and sm <= now_month:
            bugs_by_sheet.setdefault(sm, []).append((key, b))

    # carry: TẤT CẢ bug đang MỞ hiện tại (bất kể tháng tạo), định danh theo fp -> nợ mang sang.
    # Overwrite carry[now_month] mỗi scan (hội tụ về trạng thái cuối tháng ở lần scan chót);
    # tháng < now_month đã chốt -> KHÔNG đụng (đóng băng). fp trùng -> bug sau đè (dedup nội dung).
    open_now = {}
    for b in cur_bugs.values():
        if is_open(b.get('status', '')):
            open_now[_fp(b)] = _carry_rec(b)

    with _lock:
        data = _load()
        months = data.get('months', {}) or {}
        carry = data.get('carry', {}) or {}
        chart = data.get('chart', {}) or {}
        frozen = data.get('frozen', {}) or {}        # {ym: iso} tháng đã chốt cứng -> bất khả xâm phạm
        before = json.dumps({'m': months, 'c': carry, 'ch': chart, 'f': frozen},
                            sort_keys=True, ensure_ascii=False)

        for cm, snap in by_cm.items():
            if cm in frozen:
                continue                             # đã chốt cứng -> không đụng
            if cm == now_month:
                months[cm] = snap                    # tháng hiện tại: cập nhật LIVE mỗi scan
            elif cm not in months:
                months[cm] = snap                    # bootstrap 1 lần cho tháng quá khứ thiếu
            # cm < now_month đã có -> ĐÓNG BĂNG, để yên

        if now_month not in frozen:
            carry[now_month] = open_now              # chỉ tháng hiện tại; quá khứ giữ nguyên

        # chart snapshot (per-dev/dự án + tổng + dải tồn đọng, đã khử trùng fp): tháng hiện
        # tại cập nhật LIVE mỗi scan (đóng băng ở lần scan cuối tháng); tháng quá khứ thiếu ->
        # bootstrap 1 lần từ data hiện tại; tháng quá khứ ĐÃ CÓ -> để yên (KHÔNG trôi khi team
        # sửa/copy sheet tháng sau). Decision #47.
        for cm, kb in bugs_by_sheet.items():
            if cm in frozen:
                continue                             # đã chốt cứng -> KHÔNG rebuild, kể cả khi bump _CHART_V
            # tháng hiện tại: LIVE mỗi scan; tháng quá khứ thiếu -> bootstrap 1 lần; đã có nhưng
            # version cũ (_v != _CHART_V, vd snapshot created-based cũ) -> rebuild 1 lần sheet-based.
            if cm == now_month or cm not in chart or (chart.get(cm) or {}).get('_v') != _CHART_V:
                chart[cm] = _chart_entry(kb, cm, reopen_map, cur_bugs)

        # prune: giữ _MONTHS_CAP tháng gần nhất (cả 4 kho)
        for store in (months, carry, chart, frozen):
            for m in sorted(store)[:-_MONTHS_CAP]:
                del store[m]

        after = json.dumps({'m': months, 'c': carry, 'ch': chart, 'f': frozen},
                           sort_keys=True, ensure_ascii=False)
        if after == before:
            return False                             # không đổi -> khỏi ghi (dedup)

        data['months'] = months
        data['carry'] = carry
        data['chart'] = chart
        data['frozen'] = frozen
        data['updated'] = _now_iso()
        atomic_write(BUG_MONTHLY_FILE, json.dumps(data, ensure_ascii=False, indent=2))
        try:
            remote_put(BUG_MONTHLY_PROP, data)
        except RuntimeError:
            pass
        return True


def freeze_month(month=None, live=None, reopen_map=None):
    """CHỐT CỨNG số liệu tháng `month` ('YYYY-MM', None = tháng hiện tại) — gọi SAU khi report
    tháng đã gửi xong (xem hook trong monthly_reporter_chat_app.py).

    Vì sao cần: `archive()` overwrite snapshot tháng HIỆN TẠI mỗi lần scan, nên số chỉ "tự đóng
    băng" ở lần scan chót của tháng — không trùng với thời điểm gửi report. Freeze tại đúng lúc
    gửi => số trên dashboard KHỚP số đã gửi CTO, và team copy bug sang sheet tháng sau (đổi
    STT/created/sheet — Decision #36/#46/#62) cũng không làm trôi nữa.

    Ghi cả 3 kho cho tháng đó: `months` (bug tạo trong tháng, cho backlog T-1 của tháng sau),
    `carry` (bug đang MỞ = nợ mang sang), `chart` (grand/dev/valid/reopen/dải tồn đọng) + đăng ký
    `frozen[month]` => archive() sau này BỎ QUA tháng này (kể cả khi bump _CHART_V).

    Gọi lại trên tháng đã freeze thì GHI ĐÈ (freeze là lệnh tường minh — chạy lại report thì số
    chốt lại theo lần chạy sau). Trả dict tóm tắt để log."""
    month = month or datetime.now().strftime('%Y-%m')
    if not _YM_RE.match(month):
        raise ValueError(f'month phải dạng YYYY-MM (nhận: {month!r})')
    live = live if live is not None else _live_bugs()
    if reopen_map is None:
        try:
            from bug_log_store import load_bug_log
            reopen_map = (load_bug_log() or {}).get('reopen', {}) or {}
        except Exception:      # noqa: BLE001 — thiếu reopen chỉ làm bảng Reopen rỗng, không chặn freeze
            reopen_map = {}

    kb = [(k, b) for k, b in live.items() if _month_of(b) == month]     # theo SHEET tháng
    snap_months = {k: _rec(b) for k, b in live.items()
                   if (b.get('created', '') or '')[:7] == month}       # theo THÁNG TẠO
    open_now = {_fp(b): _carry_rec(b) for b in live.values()
                if is_open(b.get('status', ''))}
    at = _now_iso()

    with _lock:
        data = _load()
        months = data.get('months', {}) or {}
        carry = data.get('carry', {}) or {}
        chart = data.get('chart', {}) or {}
        frozen = data.get('frozen', {}) or {}

        months[month] = snap_months
        carry[month] = open_now
        chart[month] = _chart_entry(kb, month, reopen_map, live, frozen_at=at)
        frozen[month] = at

        for store in (months, carry, chart, frozen):
            for m in sorted(store)[:-_MONTHS_CAP]:
                del store[m]

        data['months'], data['carry'] = months, carry
        data['chart'], data['frozen'] = chart, frozen
        data['updated'] = at
        atomic_write(BUG_MONTHLY_FILE, json.dumps(data, ensure_ascii=False, indent=2))
        try:
            remote_put(BUG_MONTHLY_PROP, data)
        except RuntimeError:
            pass

    ch = chart[month]
    return {'month': month, 'frozen_at': at, 'grand': ch['grand'],
            'valid': ch['valid'], 'bl': ch['bl'],
            'carry_open': len(open_now), 'months_bugs': len(snap_months)}


# ===== Compute cho báo cáo (tồn đọng T-1 vs mới phát sinh) =====
def _live_bugs():
    """{key: bug} tất cả bug hiện tại (lazy-import để tránh cycle với bug_log_store)."""
    out = {}
    try:
        from bug_log_store import load_bug_log
        for f in (load_bug_log() or {}).get('files', {}).values():
            for k, b in (f.get('bugs', {}) or {}).items():
                out[k] = b
    except Exception:      # noqa: BLE001 — báo cáo không được sập vì bug-log lỗi
        pass
    return out


def _cur_month_sheet(report_month):
    """Tên sheet team đổ bug của THÁNG BÁO CÁO vào = 'T' + số tháng (2026-07 -> 'T7').
    Dùng làm tín hiệu "bug T-1 đã bị BÊ SANG tháng T" (carried): team copy bug còn mở
    cuối tháng trước sang sheet tháng này để theo dõi tiếp."""
    return 'T' + str(int(report_month[5:7]))


def prev_month_backlog(report_month=None, live=None):
    """Tồn đọng cho báo cáo tháng `report_month` ('YYYY-MM', None=tháng hiện tại).

    Định nghĩa SHEET-BASED (user chốt 2026-08-07 — xem Decision #75). Đọc THẲNG sheet của
    tháng T (bucket theo `_month_of` = tên sheet Tn), đếm DÒNG, tách theo `created`:
      - TỒN ĐỌNG (mang sang từ tháng trước): dòng có `created` < tháng của sheet. Trong đó
        status mở = CÒN TREO (still_open); Closed/Reject = ĐÃ XỬ LÝ (resolved).
      - MỚI PHÁT SINH: dòng có `created` == (hoặc >) tháng của sheet.
    total = still_open + resolved = số dòng tồn đọng.

    Vì team bê bug chưa xử lý xong sang sheet tháng mới (GIỮ NGUYÊN ngày created), chính cái
    sheet đã là source-of-truth — KHÔNG cần fingerprint/carry/dedup qua nhiều sheet nữa. Cả
    màn Bug (splitGroups) + Analytics (computeBacklog JS) + report này đọc CÙNG 1 sheet, CÙNG
    quy tắc -> số liệu KHÔNG thể lệch. PHẢI khớp computeBacklog phía JS (app_v2.js).

    Trả dict (giữ nguyên keys cũ để caller/embed không vỡ):
      {report_month, prev_month, has_snapshot,
       total, resolved, still_open,
       new_count,      # = new_own (số dòng mới phát sinh trong sheet)
       new_own, new_fixed, new_open,   # bug mới: tổng / đã fix (Closed) / chưa fix
       bugs: [ {id, project, dev, created, status_now, state} ]  # state∈{open,resolved}
      }
    `live` (optional) = {key:bug} truyền sẵn để tránh đọc lại; None -> tự lấy."""
    if not report_month:
        report_month = datetime.now().strftime('%Y-%m')
    prev = _prev_month(report_month)
    live = live if live is not None else _live_bugs()

    def _id(p, sv, n):
        return f"{p}-{sv + '-' if sv else ''}{n}".strip('-')

    # Dòng thuộc SHEET của tháng T (bucket theo tên sheet Tn -> khớp monthOf JS).
    rows = [b for b in live.values() if _month_of(b) == report_month]
    back, fresh = [], []
    for b in rows:
        (back if (b.get('created', '') or '')[:7] < report_month else fresh).append(b)

    bugs = []
    resolved = still_open = 0
    for b in back:
        if is_open(b.get('status', '')):
            state = 'open'; still_open += 1
        else:
            state = 'resolved'; resolved += 1
        bugs.append({
            'id': _id(b.get('project', ''), b.get('service', ''), b.get('bug_no', '')),
            'project': b.get('project', ''), 'dev': b.get('dev_pic', '') or '',
            'created': (b.get('created', '') or '')[:10],
            'status_now': b.get('status', '') or '', 'state': state,
        })
    bugs.sort(key=lambda x: (x['state'] != 'open', x['project'], x['id']))

    # Mới phát sinh = số DÒNG trong sheet có created trong tháng T. Đã fix = trong đó Closed.
    new_own = len(fresh)
    new_fixed = sum(1 for b in fresh if _RE_CLOSED.search(b.get('status', '') or ''))

    return {
        'report_month': report_month, 'prev_month': prev,
        'has_snapshot': bool(rows),                   # sheet có dòng nào để tính hay không
        'total': resolved + still_open, 'resolved': resolved, 'still_open': still_open,
        'new_count': new_own, 'bugs': bugs,
        'new_own': new_own, 'new_fixed': new_fixed, 'new_open': new_own - new_fixed,
    }
