"""SQLite làm kho BỀN cho vòng đời reopen của Bug Log (sub của #54/#69).

Vì sao tồn tại: counter reopen cũ (`_count_reopens` trong bug_log_store) diff theo
snapshot JSON trong `.bug_log.json`. Snapshot đó (1) bị strip khi sync lên Jira property
(data > ~32KB -> bản `_light` bỏ `bugs`), (2) reset baseline khi đổi host -> lần scan đầu
trên host mới thấy MỌI bug là "mới" nên KHÔNG chứng kiến transition `... -> Reopen` ->
counter về 0. Hệ quả thực tế: bug đang ở Reopen (vd DA6-28) mà metric báo 0%.

Cách giải (Decision option A, 2026-06-12):
  - `bug_status`   = trạng thái GẦN NHẤT mỗi bug (baseline để diff) — bền tại local DB,
                     KHÔNG bị property strip. Sống sót restart; đổi host thì pull file .db.
  - `status_event` = append-only MỌI lần status đổi (audit + recompute được, không mong manh
                     như 2 counter). "Mỗi sync thấy đổi status thì lưu DB" đúng nghĩa.
  - `reopen_state` = counter {count(reopen), fix} mỗi bug — nguồn cho metric. Export ra dict
                     y shape `reopen` cũ -> render + mirror property KHÔNG đổi.

Cross-host (option A): reopen counts vẫn mirror lên Jira property (nhỏ, vừa 32KB) qua
`data['reopen']` như cũ. Host mới: `import_reopen()` nạp counts từ property vào DB MỘT lần
(không ghi đè key đã có) -> không reset; full lịch sử event nằm ở .db (mang theo nếu cần audit).

Seed (user chốt 2026-06-12): bug LẦN ĐẦU thấy trong DB mà đang ở 'Reopen' và CHƯA có trong
reopen_state -> khởi tạo count=1, fix=1. Bắt được các reopen "có sẵn" lúc bật/đổi host thay
vì mù tới khi có reopen MỚI.

Giới hạn (cố hữu, SQLite KHÔNG sửa): vẫn lấy mẫu mỗi POLL_SECONDS -> round-trip
Fixed->Reopen->Fixed gọn trong 1 cửa sổ vẫn sót. Đổi host = copy .db thủ công (hoặc dựa
property mirror cho counts).

Ghi CHỈ trong scan() (đã serialize bởi _scan_lock ở bug_log_store) -> 1 writer, mở/đóng
connection mỗi call là đủ an toàn. Reader (render) đọc cache JSON, không đụng DB.

Layer: config -> (this). Không phụ thuộc module khác trong app -> không cycle.
"""
import sqlite3
from datetime import datetime

from config import BUG_LOG_DB


def _now_iso():
    return datetime.now().isoformat()


def _conn():
    conn = sqlite3.connect(str(BUG_LOG_DB))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')   # bền hơn khi ghi giữa chừng bị ngắt
    conn.executescript(
        'CREATE TABLE IF NOT EXISTS bug_status('
        ' file_id TEXT, key TEXT, status TEXT, project TEXT, month TEXT, dev TEXT, at TEXT,'
        ' PRIMARY KEY(file_id, key));'
        'CREATE TABLE IF NOT EXISTS status_event('
        ' id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, project TEXT, month TEXT, dev TEXT,'
        ' from_status TEXT, to_status TEXT, at TEXT);'
        'CREATE INDEX IF NOT EXISTS ix_event_key ON status_event(key);'
        'CREATE TABLE IF NOT EXISTS reopen_state('
        ' key TEXT PRIMARY KEY, count INTEGER, fix INTEGER, last TEXT,'
        ' dev TEXT, project TEXT, month TEXT);'
    )
    return conn


def _upsert_reopen(cur, key, ent):
    cur.execute(
        'INSERT INTO reopen_state(key,count,fix,last,dev,project,month) VALUES(?,?,?,?,?,?,?)'
        ' ON CONFLICT(key) DO UPDATE SET count=excluded.count, fix=excluded.fix,'
        ' last=excluded.last, dev=excluded.dev, project=excluded.project, month=excluded.month',
        (key, int(ent.get('count', 0)), int(ent.get('fix', 1)), ent.get('last', ''),
         ent.get('dev', ''), ent.get('project', ''), ent.get('month', '')))


def import_reopen(reopen_map):
    """Nạp counts từ property-mirror (dict {key:{count,fix,...}}) vào reopen_state cho key
    CHƯA có trong DB. Idempotent — KHÔNG ghi đè key đã tồn tại (DB là nguồn đang chạy; chỉ
    điền chỗ trống lúc host mới có DB rỗng). No-op nếu reopen_map rỗng."""
    if not reopen_map:
        return
    conn = _conn()
    cur = conn.cursor()
    have = {r['key'] for r in cur.execute('SELECT key FROM reopen_state')}
    for key, ent in reopen_map.items():
        if key in have or not isinstance(ent, dict):
            continue
        _upsert_reopen(cur, key, ent)
    conn.commit()
    conn.close()


def apply_file(file_id, cur_bugs):
    """Diff cur_bugs (={key:bug}) vs baseline DB của file -> ghi status_event + cập nhật
    reopen_state, rồi upsert baseline. Trả số "hit" (lần đụng counter) để caller set dirty.

    - key MỚI với DB + status=='Reopen' + chưa có reopen_state -> seed count=1, fix=1.
    - status đổi (witnessed): ghi event. -> 'Reopen': reopen +1 (tạo entry fix=1 nếu chưa có).
      -> 'Fixed' & key đã trong reopen_state: fix +1 (bug chưa từng reopen không tính)."""
    hits = 0
    now = _now_iso()
    conn = _conn()
    cur = conn.cursor()
    prev = {r['key']: r['status'] for r in
            cur.execute('SELECT key, status FROM bug_status WHERE file_id=?', (file_id,))}
    rstate = {r['key']: {'count': r['count'], 'fix': r['fix'], 'last': r['last'],
                         'dev': r['dev'], 'project': r['project'], 'month': r['month']}
              for r in cur.execute('SELECT * FROM reopen_state')}

    def _event(key, frm, to, dev, project, month):
        cur.execute('INSERT INTO status_event(key,project,month,dev,from_status,to_status,at)'
                    ' VALUES(?,?,?,?,?,?,?)', (key, project, month, dev, frm, to, now))

    for key, b in cur_bugs.items():
        cs = (b.get('status') or '')
        ps = prev.get(key)   # None = lần đầu thấy trong DB
        dev = b.get('dev_pic', '') or ''
        project = b.get('project', '') or ''
        month = b.get('month', '') or ''

        if ps is None:
            if cs == 'Reopen' and key not in rstate:
                # Seed: đang Reopen sẵn, không quan sát được transition -> coi như 1 vòng reopen.
                ent = {'count': 1, 'fix': 1, 'last': now,
                       'dev': dev, 'project': project, 'month': month}
                rstate[key] = ent
                _upsert_reopen(cur, key, ent)
                _event(key, '(seed)', 'Reopen', dev, project, month)
                hits += 1
        elif ps != cs:
            _event(key, ps, cs, dev, project, month)
            if cs == 'Reopen':
                ent = rstate.get(key) or {'count': 0, 'fix': 1}
                ent['count'] = int(ent.get('count', 0)) + 1
                ent['fix'] = max(1, int(ent.get('fix', 1)))
                ent.update(last=now, dev=dev, project=project, month=month)
                rstate[key] = ent
                _upsert_reopen(cur, key, ent)
                hits += 1
            elif cs == 'Fixed' and key in rstate:
                ent = rstate[key]
                ent['fix'] = int(ent.get('fix', 1)) + 1
                ent.update(last=now, dev=dev, project=project, month=month)
                _upsert_reopen(cur, key, ent)
                hits += 1

        cur.execute('INSERT INTO bug_status(file_id,key,status,project,month,dev,at)'
                    ' VALUES(?,?,?,?,?,?,?) ON CONFLICT(file_id,key) DO UPDATE SET'
                    ' status=excluded.status, project=excluded.project, month=excluded.month,'
                    ' dev=excluded.dev, at=excluded.at',
                    (file_id, key, cs, project, month, dev, now))

    conn.commit()
    conn.close()
    return hits


def reopen_dict():
    """Export reopen_state -> {key:{count,fix,last,dev,project,month}} (shape `reopen` cũ
    cho render client-side + mirror Jira property)."""
    conn = _conn()
    out = {}
    for r in conn.execute('SELECT * FROM reopen_state'):
        out[r['key']] = {'count': r['count'], 'fix': r['fix'], 'last': r['last'],
                         'dev': r['dev'], 'project': r['project'], 'month': r['month']}
    conn.close()
    return out
