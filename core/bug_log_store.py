"""Background scheduler + cache + diff cho Bug Log (issue #54, sub của #51).

Daemon thread poll Drive mỗi 10 phút (gần real-time). Tầng-1 chỉ check metadata
(modifiedTime/md5) — rẻ; CHỈ tải+parse+normalize khi file đổi. Diff snapshot trước vs
sau theo khoá `{project}#{month}#{bug_no}` -> danh sách thay đổi (bug mới / status đổi /
xoá) + sinh activity events. Ghi cache atomic + sync Jira property (cross-machine).

⚠ Poll bắt STATE chứ không bắt TRANSITION: nhiều lần đổi gọn trong 1 cửa sổ 10p chỉ
thấy đầu vs cuối (round-trip Fixed→Reopen→Fixed bị sót). Rút interval chỉ giảm xác suất.

Lỗi mềm: fetch/parse/sync lỗi -> GIỮ cache cũ + log (đã redact token), KHÔNG sập app.

Lưu trữ (`.bug_log.json` local = full; Jira property = full hoặc bản nhẹ nếu > ~32KB):
  {
    "files": { "<fileId>": {modifiedTime, md5Checksum, name, project,
                            bugs: {key: bug}, count, scanned_at} },
    "activity": [ {id,key,summary,by,author,when,new,kind}, ... ],   # cap + prune
    "synced_at": iso
  }

Layer: config -> {jira_api, bug_log, bug_log_source, drive_token} -> (this). Không cycle.
"""
import json
import sys
import threading
import time
from datetime import datetime, timedelta

from config import BUG_LOG_FILE
from jira_api import load_property, save_property
from bug_log import fetch_rows, normalize, project_from_filename, _redact
from bug_log_source import load_sources
from drive_token import has_drive_token, load_refresh_token

BUG_LOG_PROP = 'qa-dashboard-bug-log'

POLL_SECONDS = 10 * 60      # 10 phút (issue chốt 2026-06-09)
_STARTUP_DELAY = 20         # đợi server lên + đỡ chậm khởi động trước lần scan đầu
_ACT_CAP = 200
_ACT_PRUNE_DAYS = 14
_PROP_MAX_BYTES = 30_000    # Jira property ~32KB; vượt -> chỉ sync bản nhẹ (không kèm bugs)

# scan() chạy từ daemon thread VÀ từ POST /sync-bug-log -> serialize để không đua ghi cache.
_scan_lock = threading.Lock()


def _now_iso():
    return datetime.now().isoformat()


# ===== Lưu trữ (cache local full + Jira property full/nhẹ) =====
def _empty():
    return {'files': {}, 'activity': [], 'reopen': {}, 'metrics': {}, 'synced_at': ''}


def _read_cache():
    if BUG_LOG_FILE.exists():
        try:
            d = json.loads(BUG_LOG_FILE.read_text(encoding='utf-8'))
            if isinstance(d, dict) and 'files' in d:
                return d
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(data):
    """Ghi atomic (tmp + rename) để không bao giờ để lại file rách."""
    tmp = BUG_LOG_FILE.with_suffix('.json.tmp')
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(BUG_LOG_FILE)
    except OSError:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass


def _light(data):
    """Bản nhẹ cho Jira property khi full vượt ~32KB: bỏ `bugs` rows, giữ meta + activity."""
    files = {}
    for fid, f in data.get('files', {}).items():
        files[fid] = {k: v for k, v in f.items() if k != 'bugs'}
    return {'files': files, 'activity': data.get('activity', []),
            'reopen': data.get('reopen', {}),
            'metrics': data.get('metrics', {}),   # counts nhỏ -> giữ cả ở bản nhẹ
            'synced_at': data.get('synced_at', ''), 'light': True}


def _sync_property(data):
    """Sync lên Jira property (full nếu vừa, nhẹ nếu to). Trả True nếu Jira nhận."""
    payload = data
    if len(json.dumps(data, ensure_ascii=False).encode('utf-8')) > _PROP_MAX_BYTES:
        payload = _light(data)
    try:
        save_property(BUG_LOG_PROP, payload)
        return True
    except RuntimeError:
        return False


_ACCUM_KEYS = ('reopen', 'metrics', 'activity')   # accumulator sync chéo máy (truth = property)


def _load_data():
    """Source of truth = Jira property; fallback cache local.

    Property bản nhẹ (light) bỏ `bugs` rows để < ~32KB nhưng GIỮ reopen/metrics/activity.
    Khi đó: `bugs` rows lấy từ cache local (full — cần cho render + làm prev-snapshot dò
    transition), NHƯNG reopen/metrics/activity là **accumulator sync chéo máy** nên LẤY TỪ
    PROPERTY (truth). Nhờ vậy đổi host qua lại (Win<->Mac) KHÔNG mất count dù máy nhận còn
    cache cũ — trước đây `_load_data` trả thẳng cache local nên reopen máy kia ghi lên
    property bị bỏ, count bị reset/mất (bug bounce-host).

    Đánh đổi (hướng A): nếu CÙNG một transition được CẢ hai máy quan sát (cache lệch nhau
    lúc handoff) thì reopen có thể +1 dư cho đúng bug đó. Chấp nhận để KHÔNG mất dữ liệu;
    muốn idempotent tuyệt đối cần gắn id transition (việc lớn hơn — chưa làm)."""
    prop = None
    try:
        d = load_property(BUG_LOG_PROP)
        if isinstance(d, dict) and 'files' in d:
            prop = d
    except RuntimeError:
        pass
    cached = _read_cache()
    if prop is not None and not prop.get('light'):
        _write_cache(prop)
        return prop
    # property nhẹ -> bugs từ cache local, accumulator từ property (truth chéo máy)
    if cached is not None:
        if prop is not None:
            merged = dict(cached)
            for k in _ACCUM_KEYS:
                if k in prop:
                    merged[k] = prop[k]
            # synced_at lấy mốc mới hơn để "Đã đồng bộ" không lùi khi máy kia vừa sync
            merged['synced_at'] = max(cached.get('synced_at', '') or '',
                                      prop.get('synced_at', '') or '')
            _write_cache(merged)   # cache thành truth đã graft -> sống cả khi Jira tạm hỏng
            return merged
        return cached
    if prop is not None:
        return prop
    return _empty()


def load_bug_log():
    """Dữ liệu bug log hiện tại (để render / debug). {} cấu trúc rỗng nếu chưa scan."""
    return _load_data()


def load_bug_log_activity(scope_user=None, days=7):
    """Activity events bug log (shape ~ feed item, kind='bug_log'). scope_user=None -> tất cả."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    out = []
    for a in _load_data().get('activity', []):
        if a.get('when', '') < cutoff:
            continue
        if scope_user and a.get('by') != scope_user:
            continue
        item = dict(a)
        item['kind'] = 'bug_log'
        out.append(item)
    return out


# ===== Diff snapshot trước vs sau (theo khoá {project}#{month}#{bug_no}) =====
def _diff_events(prev_bugs, cur_bugs):
    """(prev, cur) dict keyed theo bug['key'] -> list activity event (mới nhất trước).

    - key mới  -> 'log bug'  (author = qa_pic)
    - status đổi -> 'Status X → Y'
    - key mất  -> 'xoá bug'
    Field khác KHÔNG sinh event (giữ feed gọn — chủ yếu quan tâm vòng đời status)."""
    events = []
    now = datetime.now()
    stamp = now.strftime('%Y%m%d%H%M%S%f')
    iso = now.isoformat()

    def label(b):
        return f"{b.get('project', '')}#{b.get('bug_no', '')}".strip('#')

    for key, b in cur_bugs.items():
        old = prev_bugs.get(key)
        author = (b.get('qa_pic') or '').strip()
        summ = (b.get('summary') or '')[:200]
        if old is None:
            events.append({
                'id': f"{key}#bnew#{stamp}", 'key': key, 'summary': summ,
                'by': author, 'author': author or '?', 'when': iso,
                'new': f"log bug {label(b)}",
            })
        elif (old.get('status') or '') != (b.get('status') or ''):
            events.append({
                'id': f"{key}#bstat#{stamp}", 'key': key, 'summary': summ,
                'by': author, 'author': author or '?', 'when': iso,
                'new': f"Status {label(b)}: {old.get('status') or '?'} → {b.get('status') or '?'}",
            })
    for key, b in prev_bugs.items():
        if key not in cur_bugs:
            author = (b.get('qa_pic') or '').strip()
            events.append({
                'id': f"{key}#bdel#{stamp}", 'key': key, 'summary': (b.get('summary') or '')[:200],
                'by': author, 'author': author or '?', 'when': iso,
                'new': f"xoá bug {label(b)}",
            })
    return events


# ===== Metric snapshot + lịch sử thay đổi (per file, per sheet/tháng) =====
# Dashboard admin (#...) cần: Tổng bug + bug theo từng status (cột "Status" gốc trong
# Excel), chọn theo file + sheet, và "track change sau mỗi lần sync". Ta chụp 1 snapshot
# counts mỗi lần file đổi rồi nối vào lịch sử -> UI vẽ dòng lịch sử + delta giữa các mốc.
_METRIC_HISTORY_CAP = 40   # số mốc lưu mỗi (file, sheet); cũ nhất bị cắt


def _metric_snapshot(cur_bugs):
    """{key:bug} -> {month: {'total': n, 'statuses': {raw_status: count}}}.

    raw_status = bug['status_raw'] (cột "Status" gốc); rỗng -> nhãn '(trống)'."""
    out = {}
    for b in cur_bugs.values():
        month = (b.get('month') or '').strip()
        raw = (b.get('status_raw') or '').strip() or '(trống)'
        m = out.setdefault(month, {'total': 0, 'statuses': {}})
        m['total'] += 1
        m['statuses'][raw] = m['statuses'].get(raw, 0) + 1
    return out


def _update_metrics(metrics, fid, snap):
    """Nối snapshot vào lịch sử metric của file. CHỈ thêm mốc mới khi counts ĐỔI so với
    mốc gần nhất của (file, sheet) -> lịch sử chỉ gồm các lần thực sự thay đổi. Cắt còn
    `_METRIC_HISTORY_CAP` mốc gần nhất mỗi sheet. Trả True nếu có ghi gì mới."""
    fm = metrics.setdefault(fid, {})
    changed = False
    iso = _now_iso()
    for month, cur in snap.items():
        hist = fm.setdefault(month, [])
        last = hist[-1] if hist else None
        if last and last.get('total') == cur['total'] and last.get('statuses') == cur['statuses']:
            continue
        hist.append({'at': iso, 'total': cur['total'], 'statuses': cur['statuses']})
        if len(hist) > _METRIC_HISTORY_CAP:
            del hist[:-_METRIC_HISTORY_CAP]
        changed = True
    return changed


# ===== Đếm vòng đời reopen/fix tích luỹ (theo transition status giữa 2 snapshot) =====
def _count_reopens(reopen_map, prev_bugs, cur_bugs):
    """Cập nhật counter reopen + số lần fix cho mỗi bug, theo transition status.

    Entry `reopen_map[key]` = {count(reopen), fix, last, dev, project, month}. CHỈ tạo
    entry khi bug bị reopen (tập bug 'có vấn đề' — giữ map nhỏ, an toàn property ~32KB).

    - prev.status != 'Reopen' & cur.status == 'Reopen' → reopen +1. Tạo entry nếu chưa có,
      khởi tạo `fix=1` (lần fix TRƯỚC khi bị dội đầu tiên — reopen tất phải có 1 fix trước đó).
    - prev.status != 'Fixed' & cur.status == 'Fixed' & key ĐÃ trong map → fix +1 (lần fix lại
      sau khi bị dội). Bug chưa từng reopen không tính (không nằm trong bảng reopen).
    - Chỉ xét key có ở CẢ prev và cur (key mới đã ở Reopen/Fixed = trước khi bật tracking →
      bỏ, không quan sát được transition). Trả số hit để caller set dirty."""
    hits = 0
    for key, cur in cur_bugs.items():
        prev = prev_bugs.get(key)
        if prev is None:
            continue
        ps = prev.get('status') or ''
        cs = cur.get('status') or ''

        def _touch(ent):
            ent['last'] = _now_iso()
            ent['dev'] = cur.get('dev_pic', '') or ''
            ent['project'] = cur.get('project', '') or ''
            ent['month'] = cur.get('month', '') or ''

        if ps != 'Reopen' and cs == 'Reopen':
            ent = reopen_map.get(key)
            if ent is None:
                ent = {'count': 0, 'fix': 1}   # fix gốc (trước khi bị dội)
                reopen_map[key] = ent
            ent['count'] = int(ent.get('count', 0)) + 1
            _touch(ent)
            hits += 1
        elif ps != 'Fixed' and cs == 'Fixed' and key in reopen_map:
            ent = reopen_map[key]
            ent['fix'] = int(ent.get('fix', 1)) + 1
            _touch(ent)
            hits += 1
    return hits


def _prune_activity(activity):
    cutoff = (datetime.now() - timedelta(days=_ACT_PRUNE_DAYS)).isoformat()
    return [a for a in activity if a.get('when', '') >= cutoff][:_ACT_CAP]


# ===== scan() — tầng-1 metadata check -> tầng-2 fetch+diff =====
def scan():
    """Quét tất cả nguồn Drive 1 lượt. Trả dict tổng kết:
       {ok, synced_at, count, changed, unmapped, errors}.

    Tầng-1: nếu file (modifiedTime,md5) y lần trước -> bỏ qua tải. Tầng-2: tải+parse+
    normalize -> diff -> gom event. Ghi cache + sync property 1 lần ở cuối.
    Lỗi 1 file KHÔNG chặn file khác; lỗi chung -> giữ cache cũ."""
    with _scan_lock:
        result = {'ok': True, 'synced_at': '', 'count': 0, 'changed': 0,
                  'unmapped': 0, 'errors': []}
        if not has_drive_token():
            result['ok'] = False
            result['errors'].append('Chưa kết nối Drive.')
            return result
        try:
            sources = load_sources()
        except RuntimeError as e:
            result['ok'] = False
            result['errors'].append(_safe(e))
            return result
        if not sources:
            result['ok'] = False
            result['errors'].append('Chưa cấu hình file Drive nguồn.')
            return result

        data = _load_data()
        files = data.setdefault('files', {})
        activity = data.setdefault('activity', [])
        reopen = data.setdefault('reopen', {})
        metrics = data.setdefault('metrics', {})
        new_events = []
        dirty = False

        for src in sources:
            fid = src.get('id')
            if not fid:
                continue
            prev = files.get(fid, {})
            try:
                rows, meta = fetch_rows(fid)
            except RuntimeError as e:
                result['errors'].append(_safe(e))
                continue
            # Tầng-1: không đổi -> bỏ qua (vẫn cộng count để tổng kết phản ánh thực tế)
            unchanged = (prev.get('modifiedTime') == meta.get('modifiedTime')
                         and prev.get('md5Checksum') == meta.get('md5Checksum')
                         and 'bugs' in prev
                         and prev.get('_version') == 3)
            if unchanged:
                result['count'] += len(prev.get('bugs', {}))
                continue
            # Tầng-2: normalize + diff
            project = project_from_filename(src.get('label', '') or meta.get('name', ''))
            norm = normalize(rows, project=project, service=src.get('service', ''))
            cur_bugs = {b['key']: b for b in norm['bugs'] if b.get('key')}
            new_events.extend(_diff_events(prev.get('bugs', {}), cur_bugs))
            if _count_reopens(reopen, prev.get('bugs', {}), cur_bugs):
                dirty = True
            if _update_metrics(metrics, fid, _metric_snapshot(cur_bugs)):
                dirty = True
            files[fid] = {
                'modifiedTime': meta.get('modifiedTime', ''),
                'md5Checksum': meta.get('md5Checksum', ''),
                'name': meta.get('name', ''),
                'project': project,
                'bugs': cur_bugs,
                'count': len(cur_bugs),
                'unmapped': len(norm['unmapped']),
                'scanned_at': _now_iso(),
                '_version': 3,   # 3: thêm bug['status_raw'] + seed metric snapshot
            }
            result['count'] += len(cur_bugs)
            result['unmapped'] += len(norm['unmapped'])
            dirty = True

        if new_events:
            data['activity'] = _prune_activity(new_events + activity)
            result['changed'] = len(new_events)
        # synced_at = mốc "vừa quét xong" — cập nhật MỖI lần scan chạy trót lọt (kể cả
        # khi không file nào đổi, Tầng-1 skip hết) để UI "Đã đồng bộ" luôn tươi sau khi
        # bấm nút / auto-sync. Luôn ghi cache local (rẻ, nguồn render). CHỈ sync property
        # lên Jira khi có thay đổi thật (tránh ghi property mỗi 10p chỉ vì đổi timestamp).
        data['synced_at'] = _now_iso()
        _write_cache(data)
        if dirty or new_events:
            if not _sync_property(data):
                result['errors'].append('Không sync được lên Jira (giữ cache local).')
        result['synced_at'] = data.get('synced_at', '')
        result['ok'] = not result['errors'] or result['count'] > 0
        return result


def _safe(exc):
    """Redact token khỏi message lỗi (fetch_rows đã redact, đây là lớp chắn cuối)."""
    rt = None
    try:
        rt = load_refresh_token()
    except Exception:
        rt = None
    return _redact(exc, rt) if rt else str(exc)


# ===== Daemon thread =====
def _loop():
    time.sleep(_STARTUP_DELAY)
    while True:
        try:
            res = scan()
            if res.get('changed'):
                _log(f"scan: {res['changed']} thay đổi, {res['count']} bug, "
                     f"{res['unmapped']} unmapped")
            for err in res.get('errors', []):
                _log('scan warn: ' + err)
        except Exception as e:   # noqa: BLE001 — daemon KHÔNG được chết vì 1 lỗi lạ
            _log('scan error: ' + _safe(e))
        time.sleep(POLL_SECONDS)


def _log(msg):
    sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] [bug-log] {msg}\n")


def start_scheduler():
    """Khởi động daemon thread poll Drive. Gọi 1 lần trong main(). daemon=True -> tắt theo
    process chính. No-op an toàn nếu chưa kết nối Drive (scan tự bỏ qua mỗi vòng)."""
    t = threading.Thread(target=_loop, name='bug-log-scan', daemon=True)
    t.start()
    return t
