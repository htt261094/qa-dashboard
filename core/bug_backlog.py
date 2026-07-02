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

Lưu trữ (`.bug_monthly.json` local = cache + KV/property = sync chéo máy qua remote_store):
  { "months": { "YYYY-MM": { key: {s,c,p,n,d,sv} } }, "updated": iso }
  s=status(lifecycle) · c=created(YYYY-MM-DD) · p=project · n=bug_no · d=dev_pic · sv=service

Layer: config -> {remote_store} -> (this); bug_log_store nạp LAZY (tránh cycle: bug_log_store
import module này để gọi archive()). Không cycle.
"""
import json
import threading
from datetime import datetime

from config import BUG_MONTHLY_FILE, atomic_write
from remote_store import remote_get, remote_put

BUG_MONTHLY_PROP = 'qa-dashboard-bug-monthly'
_MONTHS_CAP = 24                 # giữ tối đa 24 tháng gần nhất
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


# ===== Lưu trữ (cache local + remote KV/property qua remote_store) =====
def _read_cache():
    if BUG_MONTHLY_FILE.exists():
        try:
            d = json.loads(BUG_MONTHLY_FILE.read_text(encoding='utf-8'))
            if isinstance(d, dict) and 'months' in d:
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
        if isinstance(d, dict) and 'months' in d:
            remote = d
    except RuntimeError:
        pass
    cached = _read_cache()
    months = {}
    if cached:
        months.update(cached.get('months', {}) or {})
    if remote:
        months.update(remote.get('months', {}) or {})
    updated = max((cached or {}).get('updated', '') or '',
                  (remote or {}).get('updated', '') or '')
    return {'months': months, 'updated': updated}


def load_backlog():
    """Data snapshot tháng hiện tại (để render / embed). {months:{}, updated:''} nếu chưa có."""
    return _load()


def archive(cur_bugs):
    """Chốt snapshot cho THÁNG HIỆN TẠI + bootstrap tháng quá khứ còn thiếu. Gọi từ scan().

    cur_bugs = {key: bug} — TẤT CẢ bug đang quan sát (mọi tháng). Chỉ ghi khi có thay đổi
    thật (dedup) để đỡ quota KV. Tháng đã đóng băng (< tháng hiện tại, đã có snapshot) KHÔNG
    bị đụng. Soft-fail: remote lỗi -> giữ cache local, lần sau đẩy lại."""
    now_month = datetime.now().strftime('%Y-%m')
    # Gom bug live theo THÁNG TẠO (created), bỏ bug thiếu created / created ở tương lai.
    by_cm = {}
    for key, b in cur_bugs.items():
        cm = (b.get('created', '') or '')[:7]
        if len(cm) == 7 and cm <= now_month:
            by_cm.setdefault(cm, {})[key] = _rec(b)

    with _lock:
        data = _load()
        months = data.get('months', {}) or {}
        before = json.dumps(months, sort_keys=True, ensure_ascii=False)

        for cm, snap in by_cm.items():
            if cm == now_month:
                months[cm] = snap                    # tháng hiện tại: cập nhật LIVE mỗi scan
            elif cm not in months:
                months[cm] = snap                    # bootstrap 1 lần cho tháng quá khứ thiếu
            # cm < now_month đã có -> ĐÓNG BĂNG, để yên

        # prune: giữ _MONTHS_CAP tháng gần nhất
        keys = sorted(months)
        for m in keys[:-_MONTHS_CAP]:
            del months[m]

        after = json.dumps(months, sort_keys=True, ensure_ascii=False)
        if after == before:
            return False                             # không đổi -> khỏi ghi (dedup)

        data['months'] = months
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


def prev_month_backlog(report_month=None, live=None):
    """Tồn đọng T-1 cho báo cáo tháng `report_month` ('YYYY-MM', None=tháng hiện tại).

    Trả dict:
      {report_month, prev_month, has_snapshot,
       total,          # số bug tồn đọng từ T-1 (mở cuối T-1)
       resolved,       # nay ĐÃ rời trạng thái mở: đã đóng HOẶC không còn trong file (gộp)
       still_open,     # nay VẪN mở
       new_count,      # bug MỚI phát sinh trong report_month (theo created)
       bugs: [ {id, project, dev, created, status_prev, status_now, state} ]  # state∈{open,resolved}
      }
    2 nhóm (còn / đã xử lý) -> total = still_open + resolved LUÔN khớp; bug "không còn trong
    file" gộp vào resolved (không dựng được là đóng hay xoá, nhưng đều = hết treo).
    `live` (optional) = {key:bug} truyền sẵn để tránh đọc lại; None -> tự lấy."""
    if not report_month:
        report_month = datetime.now().strftime('%Y-%m')
    prev = _prev_month(report_month)
    snap_prev = _load().get('months', {}).get(prev)
    live = live if live is not None else _live_bugs()

    def _id(p, sv, n):
        return f"{p}-{sv + '-' if sv else ''}{n}".strip('-')

    bugs = []
    resolved = still_open = 0
    for key, rec in (snap_prev or {}).items():
        if not is_open(rec.get('s', '')):
            continue                                 # cuối T-1 đã đóng -> không phải tồn đọng
        b = live.get(key)
        if b is not None and is_open(b.get('status', '')):
            state = 'open'; still_open += 1; status_now = b.get('status', '') or ''
        else:                                        # đã đóng HOẶC không còn trong file -> đã xử lý
            state = 'resolved'; resolved += 1; status_now = (b.get('status', '') if b else '') or ''
        bugs.append({
            'id': _id(rec.get('p', ''), rec.get('sv', ''), rec.get('n', '')),
            'project': rec.get('p', ''),
            'dev': (b.get('dev_pic', '') if b else rec.get('d', '')) or '',
            'created': rec.get('c', ''),
            'status_prev': rec.get('s', ''),
            'status_now': status_now,
            'state': state,
        })
    bugs.sort(key=lambda x: (x['state'] != 'open', x['project'], x['id']))

    new_count = sum(1 for b in live.values()
                    if (b.get('created', '') or '')[:7] == report_month)

    return {
        'report_month': report_month, 'prev_month': prev,
        'has_snapshot': snap_prev is not None,
        'total': len(bugs), 'resolved': resolved, 'still_open': still_open,
        'new_count': new_count, 'bugs': bugs,
    }
