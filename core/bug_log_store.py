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

from config import BUG_LOG_FILE, BUG_LOG_POLL_SECONDS, atomic_write
from jira_api import run_parallel
# Metrics (reopen/metrics/activity) dùng union-merge MONOTONIC chéo máy -> KHÔNG dùng local-first
# LWW của synced_* (sẽ làm tụt count). Chỉ đổi backend Jira->KV qua remote_get/remote_put, GIỮ
# nguyên merge-before-write. KV value tới 25MB (Jira ~32KB) nên light-split ít khi cần nhưng giữ.
from remote_store import remote_get as load_property, remote_put as save_property
from bug_log import fetch_meta, fetch_content, normalize, project_from_filename, _redact
from bug_log_source import load_sources
from drive_token import has_drive_token, load_refresh_token

BUG_LOG_PROP = 'qa-dashboard-bug-log'

POLL_SECONDS = BUG_LOG_POLL_SECONDS   # nhịp poll Drive (giây), cấu hình qua .env (default 600)
_STARTUP_DELAY = 20         # đợi server lên + đỡ chậm khởi động trước lần scan đầu
_ACT_CAP = 200
_ACT_PRUNE_DAYS = 14
_PROP_MAX_BYTES = 30_000    # Jira property ~32KB; vượt -> chỉ sync bản nhẹ (không kèm bugs)

# scan() chạy từ daemon thread VÀ từ POST /sync-bug-log -> serialize để không đua ghi cache.
_scan_lock = threading.Lock()
# _write_cache chạy từ daemon scan VÀ từ HTTP render (_load_data mỗi request) -> serialize để
# 2 thread không đua ghi cùng .json.tmp (đua -> file rách -> _read_cache trả None -> mất floor).
_cache_lock = threading.Lock()


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
    """Ghi atomic (tmp + rename) để không bao giờ để lại file rách. Serialize qua _cache_lock
    (daemon scan + HTTP render cùng ghi 1 tmp).

    RATCHET monotonic: union accumulator (reopen/metrics/activity) với bản ĐANG nằm trên đĩa
    TRƯỚC khi ghi -> cache local là SÀN không bao giờ tụt. Vì sao cần: Cloudflare KV
    eventually-consistent -> 1 GET stale/rỗng ngay sau PUT có thể khiến `data` mang reopen={};
    nếu cứ thế đè đĩa thì count đã đếm được (reopen chỉ bắt transition LIVE, không tái tạo
    được) mất vĩnh viễn. Union max ở đây bảo đảm chỉ THÊM, không xoá -> mọi read stale/đua ghi
    không thể clobber. Mutate `data` tại chỗ để caller (_load_data) trả về bản đã ratchet."""
    with _cache_lock:
        prev = _read_cache()
        if prev:
            data['reopen'] = _merge_reopen(data.get('reopen', {}), prev.get('reopen', {}))
            data['metrics'] = _merge_metrics(data.get('metrics', {}), prev.get('metrics', {}))
            data['activity'] = _merge_activity(data.get('activity', []), prev.get('activity', []))
        atomic_write(BUG_LOG_FILE, json.dumps(data, ensure_ascii=False, indent=2))


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
    """Sync lên Jira property (full nếu vừa, nhẹ nếu to). Trả True nếu Jira nhận.

    MERGE-before-write: union accumulator (reopen/metrics/activity) với property HIỆN TẠI
    trên Jira NGAY TRƯỚC khi ghi -> không bao giờ đè mất entry mà host khác vừa thêm. Đây
    là cái chốt chống clobber: kể cả khi baseline lúc load đọc property hụt (RuntimeError ->
    rơi về cache cũ thiếu entry), bước re-read này kéo lại các entry còn trên Jira trước khi
    save. Write chỉ thành công khi Jira đang sống -> read ngay trước đó gần như chắc cũng
    sống -> entry host khác được khôi phục. Read hụt ở đây -> bỏ qua, vẫn an toàn vì union
    lúc load là lớp bảo vệ thứ hai. Mutate `data` tại chỗ để caller ghi cache khớp property."""
    try:
        cur = load_property(BUG_LOG_PROP)
        if isinstance(cur, dict) and 'files' in cur:
            data['reopen'] = _merge_reopen(data.get('reopen', {}), cur.get('reopen', {}))
            data['metrics'] = _merge_metrics(data.get('metrics', {}), cur.get('metrics', {}))
            data['activity'] = _merge_activity(data.get('activity', []), cur.get('activity', []))
    except RuntimeError:
        pass
    payload = data
    if len(json.dumps(data, ensure_ascii=False).encode('utf-8')) > _PROP_MAX_BYTES:
        payload = _light(data)
    try:
        save_property(BUG_LOG_PROP, payload)
        return True
    except RuntimeError:
        return False


# ===== Union-merge accumulator chéo máy (max per key) — chống clobber =====
# reopen/metrics đều MONOTONIC (chỉ tăng) nên gộp bằng max theo key vừa an toàn vừa
# idempotent: host có view cũ chỉ có thể THÊM entry, KHÔNG bao giờ xoá entry host khác.
# (Thay mô hình cũ "thay nguyên cục, last-write-wins" — chính chỗ làm count tụt 6->5 khi
#  2 host thay phiên + 1 host đọc property hụt rồi ghi đè bản thiếu.)
def _merge_reopen(a, b):
    """Union 2 reopen-map theo key. count/fix lấy max; metadata (last/dev/project/month)
    lấy từ entry có `last` mới hơn."""
    out = {}
    for key in set(a) | set(b):
        ea, eb = a.get(key), b.get(key)
        if ea is None:
            out[key] = dict(eb); continue
        if eb is None:
            out[key] = dict(ea); continue
        base = dict(ea if (ea.get('last', '') >= eb.get('last', '')) else eb)
        base['count'] = max(int(ea.get('count', 0)), int(eb.get('count', 0)))
        base['fix'] = max(int(ea.get('fix', 1)), int(eb.get('fix', 1)))
        out[key] = base
    return out


def _merge_metrics(a, b):
    """Union lịch sử metric (fid -> month -> [snapshot]). Gộp snapshot theo mốc `at`
    (dedup), sort tăng dần, cắt còn `_METRIC_HISTORY_CAP` mốc gần nhất mỗi sheet."""
    out = {}
    for fid in set(a) | set(b):
        fa, fb = a.get(fid, {}), b.get(fid, {})
        fm = {}
        for month in set(fa) | set(fb):
            seen = {}
            for snap in list(fa.get(month, [])) + list(fb.get(month, [])):
                at = snap.get('at', '')
                seen.setdefault(at, snap)
            merged = sorted(seen.values(), key=lambda s: s.get('at', ''))
            fm[month] = merged[-_METRIC_HISTORY_CAP:] if len(merged) > _METRIC_HISTORY_CAP else merged
        out[fid] = fm
    return out


def _merge_activity(a, b):
    """Union activity theo `id` (mỗi event có id ổn định), sort mới->cũ, prune+cap."""
    seen = {}
    for ev in list(a) + list(b):
        i = ev.get('id')
        if i and i not in seen:
            seen[i] = ev
    merged = sorted(seen.values(), key=lambda e: e.get('when', ''), reverse=True)
    return _prune_activity(merged)


def _load_data():
    """Source of truth = Jira property; cache local = fallback. Accumulator (reopen/metrics/
    activity) UNION-merge từ CẢ property + cache (max per key) -> chéo máy không mất count.

    Cấu trúc `files`/`bugs` (cần full để dò transition lúc scan) lấy từ nguồn FULL: property
    full > cache > property light. Property bản nhẹ (light) bỏ `bugs` để < ~32KB nhưng vẫn
    mang reopen/metrics/activity -> khi light thì bugs lấy từ cache, accumulator vẫn union.

    Vì sao union thay vì lấy thẳng property: trước đây full-property branch trả nguyên prop
    (vứt accumulator cache) còn fallback khi property đọc hụt lại trả nguyên cache cũ -> 2
    host thay phiên + 1 lần đọc property timeout là đủ để bản thiếu ghi đè bản đủ (count
    6->5). Union max đảm bảo entry chỉ tăng, host nào có count cao hơn sẽ tự chữa lại property
    ở lần sync kế (qua merge-before-write trong `_sync_property`).

    Đánh đổi (giữ nguyên hướng A cũ): nếu CÙNG một transition được CẢ hai máy quan sát thì
    count có thể +1 dư cho đúng bug đó. Chấp nhận để KHÔNG mất dữ liệu; idempotent tuyệt đối
    cần gắn id transition (việc lớn hơn — chưa làm). Union max KHÔNG làm chỗ này tệ hơn (lấy
    max chứ không cộng)."""
    prop = None
    try:
        d = load_property(BUG_LOG_PROP)
        if isinstance(d, dict) and 'files' in d:
            prop = d
    except RuntimeError:
        pass
    cached = _read_cache()

    # Base cấu trúc (files/bugs): nguồn FULL freshest -> property full > cache > property light.
    if prop is not None and not prop.get('light'):
        base = dict(prop)
    elif cached is not None:
        base = dict(cached)
    elif prop is not None:
        base = dict(prop)              # chỉ có light (chưa có cache full) -> bugs thiếu, chịu
    else:
        return _empty()
    if base.get('light') and cached is not None:
        base['files'] = cached.get('files', {})   # light + có cache full -> lấy bugs từ cache
    base.pop('light', None)

    # Union accumulator từ cả 2 nguồn (max) — không phụ thuộc nguồn nào làm base.
    cr = cached.get('reopen', {}) if cached else {}
    pr = prop.get('reopen', {}) if prop else {}
    base['reopen'] = _merge_reopen(cr, pr)
    base['metrics'] = _merge_metrics(cached.get('metrics', {}) if cached else {},
                                     prop.get('metrics', {}) if prop else {})
    base['activity'] = _merge_activity(cached.get('activity', []) if cached else [],
                                       prop.get('activity', []) if prop else [])
    base['synced_at'] = max((cached or {}).get('synced_at', '') or '',
                            (prop or {}).get('synced_at', '') or '',
                            base.get('synced_at', '') or '')
    _write_cache(base)   # cache = truth đã graft -> sống cả khi Jira tạm hỏng
    return base


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


def _seed_current_reopens(reopen_map, cur_bugs):
    """Hướng A (#146): bug ĐANG ở status 'Reopen' mà chưa có entry -> seed count=1, fix=1.

    Lý do: bug ở trạng thái Reopen tất phải đã Fixed >=1 lần rồi bị QA dội -> đếm tối thiểu 1.
    Bù cho transition bị lỡ TRƯỚC khi bật theo dõi / sau khi accumulator bị reset (mà
    _count_reopens transition-based không bắt được). Chạy MỖI scan trên TẤT CẢ bug hiện tại
    (kể cả file Tầng-1 skip) -> tự chữa ngay, không cần file đổi.

    Idempotent + KHÔNG double với transition: chỉ seed khi `key not in reopen_map` -> entry
    do transition (count chính xác) hoặc seed trước đó đều không bị đè. Lower-bound: KHÔNG
    tái tạo được số dội thật trước khi theo dõi (bug dội 3 lần -> hiện 1). Trả số entry seed."""
    hits = 0
    for key, b in cur_bugs.items():
        if (b.get('status') or '') == 'Reopen' and key not in reopen_map:
            reopen_map[key] = {
                'count': 1, 'fix': 1, 'last': _now_iso(),
                'dev': b.get('dev_pic', '') or '',
                'project': b.get('project', '') or '',
                'month': b.get('month', '') or '',
            }
            hits += 1
    return hits


def _prune_activity(activity):
    cutoff = (datetime.now() - timedelta(days=_ACT_PRUNE_DAYS)).isoformat()
    return [a for a in activity if a.get('when', '') >= cutoff][:_ACT_CAP]


# ===== scan() — tầng-1 metadata check -> tầng-2 fetch+diff =====
def _scan_one(src, prev):
    """Xử lý 1 file Drive — PHẦN THUẦN (không ghi state chung) để chạy song song an toàn.

    Tầng-1: chỉ lấy metadata; nếu (modifiedTime, md5) y lần trước -> 'unchanged', KHÔNG tải.
    Tầng-2 (chỉ khi đổi): tải binary + parse + normalize. Trả dict cho merge tuần tự ở scan().
    Bắt MỌI lỗi vào 'error' (không raise) -> 1 file hỏng không kéo sập cả lượt scan."""
    fid = src.get('id')
    if not fid:
        return None
    try:
        meta = fetch_meta(fid)   # Tầng-1: rẻ, không tải binary
        unchanged = (prev.get('modifiedTime') == meta.get('modifiedTime')
                     and prev.get('md5Checksum') == meta.get('md5Checksum')
                     and 'bugs' in prev
                     and prev.get('_version') == 4)
        if unchanged:
            return {'fid': fid, 'unchanged': True, 'count': len(prev.get('bugs', {}))}
        # Tầng-2: chỉ tới đây mới tải + parse + normalize (file đã đổi). Truyền mimeType từ
        # Tầng-1 để download_file biết native Sheet (->/export) vs .xlsx (->alt=media), không
        # gọi metadata lần nữa.
        rows = fetch_content(fid, mime_type=meta.get('mimeType', ''))
        project = project_from_filename(src.get('label', '') or meta.get('name', ''))
        norm = normalize(rows, project=project, service=src.get('service', ''))
        cur_bugs = {b['key']: b for b in norm['bugs'] if b.get('key')}
        return {'fid': fid, 'meta': meta, 'project': project,
                'norm': norm, 'cur_bugs': cur_bugs}
    except Exception as e:   # noqa: BLE001 — soft-fail per-file (RuntimeError + lỗi lạ)
        return {'fid': fid, 'error': _safe(e)}


def scan():
    """Quét tất cả nguồn Drive 1 lượt. Trả dict tổng kết:
       {ok, synced_at, count, changed, unmapped, errors}.

    Tầng-1: nếu file (modifiedTime,md5) y lần trước -> bỏ qua tải. Tầng-2: tải+parse+
    normalize -> diff -> gom event. Ghi cache + sync property 1 lần ở cuối.

    Các file fetch+parse SONG SONG (_scan_one, không đụng state chung); MERGE/diff chạy
    TUẦN TỰ theo đúng thứ tự `sources` -> không race, thứ tự activity event ổn định.
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

        # PHẦN THUẦN — fetch + parse song song (I/O mạng Drive). Key = index để KHÔNG gộp
        # nhầm khi 2 nguồn trùng id; _scan_one tự bắt lỗi nên run_parallel không re-raise.
        jobs = {str(i): (lambda s=src, p=files.get(src.get('id'), {}): _scan_one(s, p))
                for i, src in enumerate(sources)}
        parallel = run_parallel(jobs) if jobs else {}

        # MERGE TUẦN TỰ theo thứ tự sources (giữ nguyên thứ tự activity event như bản cũ).
        for i, src in enumerate(sources):
            r = parallel.get(str(i))
            if not r:
                continue
            if r.get('error'):
                result['errors'].append(r['error'])
                continue
            fid = r['fid']
            if r.get('unchanged'):
                result['count'] += r.get('count', 0)   # vẫn cộng để tổng kết đúng thực tế
                continue
            # Tầng-2 đã làm trong _scan_one; ở đây chỉ diff + ghi state chung
            prev = files.get(fid, {})
            meta, norm, cur_bugs = r['meta'], r['norm'], r['cur_bugs']
            new_events.extend(_diff_events(prev.get('bugs', {}), cur_bugs))
            if _count_reopens(reopen, prev.get('bugs', {}), cur_bugs):
                dirty = True
            if _update_metrics(metrics, fid, _metric_snapshot(cur_bugs)):
                dirty = True
            files[fid] = {
                'modifiedTime': meta.get('modifiedTime', ''),
                'md5Checksum': meta.get('md5Checksum', ''),
                'name': meta.get('name', ''),
                'project': r['project'],
                'bugs': cur_bugs,
                'count': len(cur_bugs),
                'unmapped': len(norm['unmapped']),
                'scanned_at': _now_iso(),
                '_version': 4,   # 4: _lifecycle_status tin cột master (Reject→Rejected). 3: +status_raw
            }
            result['count'] += len(cur_bugs)
            result['unmapped'] += len(norm['unmapped'])
            dirty = True

        # Hướng A (#146): seed reopen cho bug đang ở Reopen nhưng thiếu entry (transition bị
        # lỡ / sau reset accumulator). Chạy trên MỌI bug hiện tại (gồm file Tầng-1 skip) ->
        # tự chữa ngay kể cả khi không file nào đổi. Idempotent (chỉ seed key chưa có).
        all_cur_bugs = {}
        for f in files.values():
            all_cur_bugs.update(f.get('bugs', {}))
        if _seed_current_reopens(reopen, all_cur_bugs):
            dirty = True

        if new_events:
            data['activity'] = _prune_activity(new_events + activity)
            result['changed'] = len(new_events)
        # synced_at = mốc "vừa quét xong" — cập nhật MỖI lần scan chạy trót lọt (kể cả
        # khi không file nào đổi, Tầng-1 skip hết) để UI "Đã đồng bộ" luôn tươi sau khi
        # bấm nút / auto-sync. Luôn ghi cache local (rẻ, nguồn render). CHỈ sync property
        # lên Jira khi có thay đổi thật (tránh ghi property mỗi 10p chỉ vì đổi timestamp).
        data['synced_at'] = _now_iso()
        if dirty or new_events:
            # _sync_property merge accumulator remote vào `data` (chống clobber) RỒI ghi
            # property. Ghi cache SAU đó để cache khớp đúng cái vừa đẩy lên Jira.
            if not _sync_property(data):
                result['errors'].append('Không sync được lên Jira (giữ cache local).')
            _write_cache(data)
        else:
            _write_cache(data)   # chỉ bump synced_at, không đụng property
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
