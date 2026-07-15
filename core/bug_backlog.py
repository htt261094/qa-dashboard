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
danh bằng FINGERPRINT nội dung (project|service|feature|summary) thay cho key sheet — nên khi
team copy bug tồn sang sheet tháng mới (STT + tên sheet đổi) vẫn match được. Report tháng M
dùng carry[M-1], đối chiếu fp với bug live: còn khớp + mở -> "còn treo"; đã đóng / không tìm
thấy -> "đã xử lý". `months` (theo tháng-tạo, khoá theo key sheet) GIỮ làm fallback cho các
tháng chưa có carry (vd 2026-06/07 — bật tính năng carry sau).

Lưu trữ (`.bug_monthly.json` local = cache + KV/property = sync chéo máy qua remote_store):
  { "months": { "YYYY-MM": { key:  {s,c,p,n,d,sv} } },   # theo tháng-tạo (fallback, key sheet)
    "carry":  { "YYYY-MM": { fp:   {s,c,p,sv,n,d}   } },   # bug MỞ cuối tháng đó (id theo fp)
    "updated": iso }
  s=status(lifecycle) · c=created(YYYY-MM-DD) · p=project · n=bug_no · d=dev_pic · sv=service
  fp = project|service|feature|summary đã _norm (lower/gộp-space/trim).

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
_CHART_V = 4                     # version freeze chart: bump khi đổi cách bucket -> rebuild snapshot cũ
                                 # (v2 = bucket theo SHEET tháng Tn thay vì created date, 2026-07)
                                 # (v3 = áp filter cột "Bug" = Bug/bug ở tầng parse -> rebuild tháng cũ, 2026-07)
                                 # (v4 = reopen bỏ đếm orphan b-None -> rebuild reopen snapshot, 2026-07)
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
# đổi). Fingerprint = project|service|feature|summary (thứ KHÔNG đổi khi copy nguyên nội dung).
# _norm PHẢI khớp y hệt bản JS trong app_v2.js (_bnorm) để match 2 phía: lower + gộp khoảng
# trắng + trim; KHÔNG bỏ dấu (để Python == JS tuyệt đối, tránh lệch NFKD).
def _norm(s):
    return ' '.join((s or '').strip().lower().split())


def fingerprint(b):
    """Fingerprint nội dung của 1 bug = project|service|feature|summary (đã _norm).
    Định danh bền qua việc copy sang sheet tháng mới (STT + tên sheet đổi, key đổi).
    Public: dùng chung cho task_link (link ngược task theo nội dung, không theo key sheet)."""
    return '|'.join((_norm(b.get('project', '')), _norm(b.get('service', '')),
                     _norm(b.get('feature', '')), _norm(b.get('summary', ''))))


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


def _reopen_table(reopen_map, kb, ym):
    """Bảng Tỷ lệ Reopen cho tháng `ym` — replicate renderReopen phía JS (RAW, KHÔNG dedup:
    giữ nguyên semantics live, freeze chỉ để chặn trôi). kb = [(key, bug)] bug tạo trong ym.
    Trả {totalBugs, distinctTotal, devs:{dev:{nb,fx,denom,detail:[{id,summary,reopen,fix}]}}}."""
    bugs_per_dev, bug_by_key = {}, {}
    total_bugs = len(kb)
    for key, b in kb:
        dl = _split_devs(b.get('dev_pic', ''))
        frac = 1.0 / len(dl)
        for d in dl:
            bugs_per_dev[d] = bugs_per_dev.get(d, 0) + frac
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
        dl = _split_devs(dev_str)
        frac = 1.0 / len(dl)
        distinct_total += 1
        for d in dl:
            distinct_per_dev[d] = distinct_per_dev.get(d, 0) + frac
            fix_per_dev[d] = fix_per_dev.get(d, 0) + fx * frac
            detail_per_dev.setdefault(d, []).append({
                'id': _bug_id(b),
                'summary': b.get('summary', ''),
                'reopen': cnt * frac, 'fix': fx * frac,
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
    months, carry, chart = {}, {}, {}
    if cached:
        months.update(cached.get('months', {}) or {})
        carry.update(cached.get('carry', {}) or {})
        chart.update(cached.get('chart', {}) or {})
    if remote:
        months.update(remote.get('months', {}) or {})
        carry.update(remote.get('carry', {}) or {})
        chart.update(remote.get('chart', {}) or {})
    updated = max((cached or {}).get('updated', '') or '',
                  (remote or {}).get('updated', '') or '')
    return {'months': months, 'carry': carry, 'chart': chart, 'updated': updated}


def load_backlog():
    """Data snapshot tháng hiện tại (để render / embed). {months:{}, updated:''} nếu chưa có."""
    return _load()


def archive(cur_bugs, reopen_map=None):
    """Chốt snapshot cho THÁNG HIỆN TẠI + bootstrap tháng quá khứ còn thiếu. Gọi từ scan().

    cur_bugs = {key: bug} — TẤT CẢ bug đang quan sát (mọi tháng). reopen_map (optional) =
    accumulator reopen (để freeze bảng Tỷ lệ Reopen theo tháng). Chỉ ghi khi có thay đổi thật
    (dedup) để đỡ quota KV. Tháng đã đóng băng (< tháng hiện tại, đã có snapshot) KHÔNG bị
    đụng. Soft-fail: remote lỗi -> giữ cache local, lần sau đẩy lại."""
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
        before = json.dumps({'m': months, 'c': carry, 'ch': chart},
                            sort_keys=True, ensure_ascii=False)

        for cm, snap in by_cm.items():
            if cm == now_month:
                months[cm] = snap                    # tháng hiện tại: cập nhật LIVE mỗi scan
            elif cm not in months:
                months[cm] = snap                    # bootstrap 1 lần cho tháng quá khứ thiếu
            # cm < now_month đã có -> ĐÓNG BĂNG, để yên

        carry[now_month] = open_now                  # chỉ tháng hiện tại; quá khứ giữ nguyên

        # chart snapshot (per-dev/dự án + tổng + dải tồn đọng, đã khử trùng fp): tháng hiện
        # tại cập nhật LIVE mỗi scan (đóng băng ở lần scan cuối tháng); tháng quá khứ thiếu ->
        # bootstrap 1 lần từ data hiện tại; tháng quá khứ ĐÃ CÓ -> để yên (KHÔNG trôi khi team
        # sửa/copy sheet tháng sau). Decision #47.
        for cm, kb in bugs_by_sheet.items():
            # tháng hiện tại: LIVE mỗi scan; tháng quá khứ thiếu -> bootstrap 1 lần; đã có nhưng
            # version cũ (_v != _CHART_V, vd snapshot created-based cũ) -> rebuild 1 lần sheet-based.
            if cm == now_month or cm not in chart or (chart.get(cm) or {}).get('_v') != _CHART_V:
                bugs = [b for _, b in kb]
                dd = _dedup_by_fp(bugs)
                blr = prev_month_backlog(cm, live=cur_bugs)
                chart[cm] = {
                    '_v': _CHART_V,
                    'grand': len(dd),
                    'devs': _chart_devs(dd),
                    'valid': _valid_counts(dd),
                    'reopen': _reopen_table(reopen_map, kb, cm),
                    'bl': {'nc': blr['new_count'], 'tot': blr['total'], 'res': blr['resolved'],
                           'so': blr['still_open'], 'prev': blr['prev_month'],
                           'has': blr['has_snapshot']},
                }

        # prune: giữ _MONTHS_CAP tháng gần nhất (cả 3 kho)
        for store in (months, carry, chart):
            for m in sorted(store)[:-_MONTHS_CAP]:
                del store[m]

        after = json.dumps({'m': months, 'c': carry, 'ch': chart},
                           sort_keys=True, ensure_ascii=False)
        if after == before:
            return False                             # không đổi -> khỏi ghi (dedup)

        data['months'] = months
        data['carry'] = carry
        data['chart'] = chart
        data['updated'] = _now_iso()
        atomic_write(BUG_MONTHLY_FILE, json.dumps(data, ensure_ascii=False, indent=2))
        try:
            remote_put(BUG_MONTHLY_PROP, data)
        except RuntimeError:
            pass
        return True


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
    """Tồn đọng T-1 cho báo cáo tháng `report_month` ('YYYY-MM', None=tháng hiện tại).

    Định nghĩa (user chốt 2026-07-10 — xem Decision #46), tính TRỰC TIẾP từ bug live
    (KHÔNG dùng snapshot `months`/`carry` nữa — bản thân việc team copy bug sang sheet
    tháng mới đã là "freeze" tự nhiên rồi). Gom bug TẠO trong T-1 theo FINGERPRINT nội
    dung (khử trùng bản copy T6↔T7), mỗi bug thật xét 1 lần:
      - CÒN TREO (still_open): KHÔNG bản nào Closed/Reject -> nợ chưa dọn.
      - ĐÃ XỬ LÝ (resolved): có bản Closed/Reject VÀ có bản nằm ở sheet tháng T (đã bê
        sang rồi đóng) -> tồn đọng đã giải quyết trong tháng T.
      - đóng gọn NGAY trong T-1 (có bản đóng nhưng KHÔNG bê sang) -> KHÔNG phải tồn đọng.
    total = still_open + resolved.

    Trả dict:
      {report_month, prev_month, has_snapshot,
       total, resolved, still_open,
       new_count,      # bug MỚI phát sinh trong report_month (unique fingerprint)
       bugs: [ {id, project, dev, created, status_now, state} ]  # state∈{open,resolved}
      }
    `live` (optional) = {key:bug} truyền sẵn để tránh đọc lại; None -> tự lấy."""
    if not report_month:
        report_month = datetime.now().strftime('%Y-%m')
    prev = _prev_month(report_month)
    cur_sheet = _cur_month_sheet(report_month)
    live = live if live is not None else _live_bugs()

    def _id(p, sv, n):
        return f"{p}-{sv + '-' if sv else ''}{n}".strip('-')

    # Gom bug tạo trong T-1 theo fingerprint (khử trùng bản copy sang sheet tháng mới).
    groups = {}
    for b in live.values():
        if (b.get('created', '') or '')[:7] == prev:
            groups.setdefault(_fp(b), []).append(b)

    bugs = []
    resolved = still_open = 0
    for group in groups.values():
        any_closed = any(not is_open(x.get('status', '')) for x in group)
        carried = any((x.get('month', '') or '') == cur_sheet for x in group)
        if not any_closed:
            state = 'open'; still_open += 1
            rep = group[0]                            # bản đại diện (còn treo)
        elif carried:
            state = 'resolved'; resolved += 1
            rep = next((x for x in group if not is_open(x.get('status', ''))), group[0])
        else:
            continue                                  # đóng gọn trong T-1, không bê sang
        bugs.append({
            'id': _id(rep.get('project', ''), rep.get('service', ''), rep.get('bug_no', '')),
            'project': rep.get('project', ''), 'dev': rep.get('dev_pic', '') or '',
            'created': (rep.get('created', '') or '')[:10],
            'status_now': rep.get('status', '') or '', 'state': state,
        })
    bugs.sort(key=lambda x: (x['state'] != 'open', x['project'], x['id']))

    # Mới phát sinh trong report_month = số bug thật (unique fingerprint) created trong tháng đó.
    new_fps = {_fp(b) for b in live.values()
               if (b.get('created', '') or '')[:7] == report_month}

    return {
        'report_month': report_month, 'prev_month': prev,
        'has_snapshot': bool(groups),                 # có bug T-1 để tính hay không
        'total': resolved + still_open, 'resolved': resolved, 'still_open': still_open,
        'new_count': len(new_fps), 'bugs': bugs,
    }
