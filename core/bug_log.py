"""Tải file .xlsx bug log từ Google Drive (unattended) + parse ra rows thô (issue #52).

CHỈ ĐỌC, không sửa file. Tầng đáy của Bug Log (#51): đầu vào cho #53 (normalize) và
chạy trong background thread #54.

Luồng runtime:
  1. refresh_token (giải mã từ drive_token) -> access_token (cache memory ~1h).
  2. GET files/<id>?fields=modifiedTime,md5Checksum  -> check đổi (rẻ, khỏi tải nếu y nguyên).
  3. GET files/<id>?alt=media                        -> tải binary .xlsx khi đổi.
  4. Parse .xlsx bằng stdlib (zipfile + xml.etree) — KHÔNG openpyxl.

Output: fetch_rows() -> (rows: list[dict], meta: {fileId, modifiedTime, md5Checksum}).

OPSEC: access_token/refresh_token = credential -> KHÔNG log; redact token khỏi mọi error
trước khi raise.

Layer: config -> {auth, drive_token, bug_log_source} -> (this). Không cycle.
"""
import datetime
import re
import threading
import time
import unicodedata
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

import requests

from auth import refresh_access_token
from drive_token import load_refresh_token
from bug_log_source import load_sources

_DRIVE_FILES = 'https://www.googleapis.com/drive/v3/files/'

# ----- access_token cache (memory; background thread + handler dùng chung) -----
_tok_lock = threading.Lock()
_access_token = None
_access_exp = 0.0   # epoch giây hết hạn (trừ hao 60s)


def _redact(text, *secrets):
    out = str(text)
    for s in secrets:
        if s:
            out = out.replace(s, '<REDACTED>')
    return out


def _get_access_token(force=False):
    """access_token còn hạn (cache), refresh khi hết. Raise RuntimeError nếu chưa kết nối Drive."""
    global _access_token, _access_exp
    with _tok_lock:
        if not force and _access_token and time.time() < _access_exp:
            return _access_token
        rt = load_refresh_token()
        if not rt:
            raise RuntimeError('Chưa kết nối Drive. Admin vào Cài đặt → "Kết nối Drive".')
        access, expires_in = refresh_access_token(rt)  # redact bên trong auth
        _access_token = access
        _access_exp = time.time() + max(60, expires_in - 60)
        return access


def _drive_get(url, params, token, stream=False):
    """GET Drive API với Bearer token; redact token khỏi error. Trả response (raise nếu !=200)."""
    try:
        r = requests.get(url, params=params,
                         headers={'Authorization': f'Bearer {token}'},
                         timeout=30, stream=stream)
    except requests.RequestException as e:
        raise RuntimeError('Lỗi mạng khi gọi Drive: ' + _redact(e, token))
    if r.status_code == 401:
        raise PermissionError('access_token hết hạn')  # caller refresh + retry 1 lần
    if r.status_code == 404:
        raise RuntimeError('Không tìm thấy file trên Drive (sai id hoặc không có quyền đọc).')
    if r.status_code != 200:
        raise RuntimeError(f'Drive trả HTTP {r.status_code}.')
    return r


def _with_token_retry(fn):
    """Chạy fn(token); nếu 401 -> refresh token rồi thử lại đúng 1 lần."""
    token = _get_access_token()
    try:
        return fn(token)
    except PermissionError:
        token = _get_access_token(force=True)
        try:
            return fn(token)
        except PermissionError:
            raise RuntimeError('Drive từ chối truy cập (401) — token có thể đã bị thu hồi. '
                               'Admin hãy "Kết nối Drive" lại.')


def file_metadata(file_id):
    """{modifiedTime, md5Checksum} — tầng-1 check đổi (rẻ). md5Checksum có thể vắng với
    một số loại file; dựa modifiedTime là đủ."""
    def go(token):
        r = _drive_get(_DRIVE_FILES + file_id,
                       {'fields': 'name,modifiedTime,md5Checksum', 'supportsAllDrives': 'true'},
                       token)
        return r.json()
    return _with_token_retry(go)


def download_file(file_id):
    """Tải binary .xlsx (alt=media)."""
    def go(token):
        r = _drive_get(_DRIVE_FILES + file_id,
                       {'alt': 'media', 'supportsAllDrives': 'true'},
                       token, stream=False)
        return r.content
    return _with_token_retry(go)


# ===== Parse .xlsx — stdlib (zipfile + xml.etree) =====
def _localname(tag):
    return tag.rsplit('}', 1)[-1]


def _col_index(cell_ref):
    """'B7' -> 1 (0-based cột B). Bỏ phần số."""
    letters = re.match(r'[A-Z]+', cell_ref or '')
    if not letters:
        return 0
    idx = 0
    for ch in letters.group(0):
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx - 1


def _read_shared_strings(zf):
    """xl/sharedStrings.xml -> list[str]. Gộp mọi <t> trong mỗi <si> (rich text runs)."""
    out = []
    try:
        data = zf.read('xl/sharedStrings.xml')
    except KeyError:
        return out
    for _ev, el in ET.iterparse(BytesIO(data)):
        if _localname(el.tag) == 'si':
            parts = [t.text or '' for t in el.iter() if _localname(t.tag) == 't']
            out.append(''.join(parts))
            el.clear()
    return out


def _sheet_targets(zf):
    """[(sheet_name, worksheet_path)] theo thứ tự workbook."""
    wb = ET.fromstring(zf.read('xl/workbook.xml'))
    rels_root = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
    # rId -> target path
    rid_target = {}
    for rel in rels_root:
        rid = rel.get('Id')
        tgt = rel.get('Target', '')
        if rid:
            tgt = tgt.lstrip('/')
            if not tgt.startswith('xl/'):
                tgt = 'xl/' + tgt
            rid_target[rid] = tgt
    out = []
    for el in wb.iter():
        if _localname(el.tag) == 'sheet':
            name = el.get('name', '')
            rid = None
            for k, v in el.attrib.items():
                if _localname(k) == 'id':   # r:id
                    rid = v
                    break
            if rid and rid in rid_target:
                out.append((name, rid_target[rid]))
    return out


def _cell_value(c, shared):
    """Giá trị 1 ô <c> -> str (hoặc '' nếu rỗng). Giữ số dạng str (date serial xử lý sau)."""
    t = c.get('t')
    if t == 'inlineStr':
        parts = [el.text or '' for el in c.iter() if _localname(el.tag) == 't']
        return ''.join(parts)
    v = None
    for el in c:
        if _localname(el.tag) == 'v':
            v = el.text
            break
    if v is None:
        return ''
    if t == 's':
        try:
            return shared[int(v)]
        except (ValueError, IndexError):
            return ''
    return v  # number / str formula / boolean — giữ nguyên text


def _read_rows(zf, path, shared):
    """worksheet -> list[list[str]] (mỗi row = list ô theo cột, fill '' ở cột thiếu)."""
    rows = []
    for _ev, row in ET.iterparse(BytesIO(zf.read(path))):
        if _localname(row.tag) != 'row':
            continue
        cells = {}
        maxc = -1
        for c in row:
            if _localname(c.tag) != 'c':
                continue
            ci = _col_index(c.get('r', ''))
            cells[ci] = _cell_value(c, shared)
            maxc = max(maxc, ci)
        rows.append([cells.get(i, '') for i in range(maxc + 1)])
        row.clear()
    return rows


def _serial_to_date(value):
    """Excel serial (epoch 1899-12-30) -> 'YYYY-MM-DD'. Trả str gốc nếu không phải số."""
    s = (value or '').strip()
    if not s:
        return ''
    try:
        serial = float(s)
    except ValueError:
        return s  # đã là chuỗi ngày -> giữ nguyên
    try:
        d = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=serial)
        return d.strftime('%Y-%m-%d')
    except (OverflowError, ValueError):
        return s


_DATA_SHEET_RE = re.compile(r'^(?!template$).+$', re.IGNORECASE)
_BANNER_RE = re.compile(r'AI\s*báo\s*cáo', re.IGNORECASE)


def _parse_sheet(name, rows):
    """1 sheet data -> list[dict] theo cấu trúc file bug log (xem CLAUDE/issue #52).

    r1 = tiêu đề (bỏ), r2 = header, banner "AI báo cáo" (bỏ), data row = `Mô tả bug` non-empty.
    Forward-fill `Chức năng`; `Ngày` serial->date; `Ảnh` tách theo newline."""
    if len(rows) < 3:
        return []
    header = [str(h).strip() for h in rows[1]]  # r2 (index 1)
    # map tên cột -> chỉ số (tên đầu tiên thắng nếu trùng)
    col = {}
    for i, h in enumerate(header):
        if h and h not in col:
            col[h] = i

    out = []
    last_func = ''
    for row in rows[2:]:
        if not any(str(x).strip() for x in row):
            continue
        joined = ' '.join(str(x) for x in row if str(x).strip())
        if _BANNER_RE.search(joined) and sum(1 for x in row if str(x).strip()) <= 1:
            continue  # banner 1 ô
        rec = {}
        for h, i in col.items():
            rec[h] = (row[i].strip() if i < len(row) and isinstance(row[i], str) else
                      (str(row[i]).strip() if i < len(row) else ''))
        # forward-fill Chức năng (merged cell)
        func = rec.get('Chức năng', '')
        if func:
            last_func = func
        else:
            rec['Chức năng'] = last_func
        # data row = Mô tả bug non-empty
        if not rec.get('Mô tả bug', '').strip():
            continue
        # Ngày: Excel serial -> date
        if 'Ngày' in rec:
            rec['Ngày'] = _serial_to_date(rec['Ngày'])
        # Ảnh: nhiều link -> list
        if 'Ảnh' in rec:
            links = [ln.strip() for ln in re.split(r'[\r\n]+', rec['Ảnh']) if ln.strip()]
            rec['Ảnh'] = links
        rec['_sheet'] = name
        out.append(rec)
    return out


def parse_xlsx(data):
    """bytes .xlsx -> list[dict] (gộp mọi sheet tên ^T\\d+$). Raise RuntimeError nếu file hỏng."""
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        raise RuntimeError('File tải về không phải .xlsx hợp lệ.')
    with zf:
        shared = _read_shared_strings(zf)
        out = []
        for name, path in _sheet_targets(zf):
            if not _DATA_SHEET_RE.match(name):
                continue  # bỏ Template & sheet phụ
            try:
                rows = _read_rows(zf, path, shared)
            except KeyError:
                continue
            out.extend(_parse_sheet(name, rows))
        return out


# ===== Normalize (issue #53) — header→field mapping + gộp status + khoá diff =====
#
# Đầu vào = rows thô từ parse_xlsx (dict keyed theo TÊN header gốc + `_sheet`).
# Đầu ra  = {bugs:[...], unmapped:[...]} (xem docstring normalize).
#
# Nguyên tắc:
#   - Map theo TÊN header (chuẩn hoá lower+trim), KHÔNG theo index → chống schema drift.
#   - Gộp 3 cột status (Status tổng / Test status / Dev status) → 1 lifecycle.
#   - Khoá diff = {project}#{month}#{bug_no}; month = tên sheet (STT restart mỗi tháng).
#   - Thiếu/trùng bug_no → đẩy vào `unmapped`, KHÔNG vào diff (best-effort tới khi STT kỷ luật).

def _norm_header(h):
    """Chuẩn hoá tên header để map defensive: trim + gộp khoảng trắng + lower."""
    return re.sub(r'\s+', ' ', str(h or '').strip()).lower()


def _remove_accents(s):
    if not isinstance(s, str):
        return s
    s = s.replace('Đ', 'D').replace('đ', 'd')
    return unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('utf-8')


# normalized header -> field. Cột KHÔNG có ở đây (Urgent, Bug, Bug (T), Team Dev,
# Bug (D), PIC cũ (Dev)) bị bỏ qua. 3 cột status xử lý riêng ở _lifecycle_status.
_FIELD_MAP = {
    'stt': 'bug_no',
    'chức năng': 'feature',
    'mô tả bug': 'summary',
    'ảnh': 'screenshot_urls',
    'severity': 'severity',
    'kết quả mong muốn': 'expected',
    'ngày': 'created',
    'thời gian xử lý bug': 'handle_time',
    'pic (test)': 'qa_pic',
    'pic (dev)': 'dev_pic',
    'note': 'note',
}


def _lifecycle_status(total, test, dev):
    """Gộp 3 status → 1 vòng đời (New→Fixing→Fixed→Closed, nhánh Reopen/Rejected).

    Status tổng = MASTER (QA chốt). Test status chỉ fallback khi Status tổng trống.
    Dev status tô chi tiết (Rejected/Fixed/Fixing) khi Status tổng còn New. Ưu tiên trên→dưới."""
    total = (total or '').strip()
    if not total:
        total = (test or '').strip()   # Test status fallback khi Status tổng trống
    t = total.lower()
    d = (dev or '').strip().lower()
    if t == 'closed':
        return 'Closed'                # QA chốt — thắng cả Rejected
    if t == 'reopen':
        return 'Reopen'
    if t == 'new' and d == 'rejected':
        return 'Rejected'              # dev reject, QA chưa finalize
    if d == 'fixed':
        return 'Fixed'                 # chờ QA retest
    if d == 'fixing':
        return 'Fixing'
    return 'New'


def project_from_filename(filename):
    """Tên file Drive -> mã project (vd 'Logbug_DA6_2026.xlsx' -> 'DA6', 'Bug VĐT' -> 'VĐT').

    Bỏ đuôi + tiền tố 'Logbug'/'Bug log'/'Bug', lấy token mã dự án (chữ+số) đầu tiên."""
    base = re.sub(r'\.[^.]+$', '', filename or '').strip()
    base = re.sub(r'^(log\s*bug|bug\s*log|bug)[\s_-]*', '', base, flags=re.IGNORECASE)
    m = re.search(r'[A-Za-z]+\d+[A-Za-z0-9]*', base)
    if m:
        return m.group(0).upper()
    parts = re.split(r'[\s_-]+', base)
    return (parts[0] if parts else base).strip().upper()


def normalize(rows, project='', service=''):
    """rows thô (parse_xlsx) -> {bugs:[...], unmapped:[...]}.

    bug = {bug_no, month, project, feature, summary, status, severity, qa_pic, dev_pic,
           screenshot_urls, created, note, expected, handle_time, service}.
    - status = _lifecycle_status (gộp 3 cột).
    - month  = tên sheet (rec['_sheet']); created đã là 'YYYY-MM-DD' từ parse.
    - Khoá diff = {project}#{service}#{month}#{bug_no} (nếu có service) hoặc {project}#{month}#{bug_no}.
      Thiếu bug_no -> unmapped (reason 'no_stt');
      trùng khoá -> MỌI dòng cùng khoá vào unmapped (reason 'dup_stt') vì không phân biệt được.
    `project` nên do caller suy từ tên file (project_from_filename)."""
    project = (project or '').strip()
    service = (service or '').strip()
    parsed = []
    for rec in rows:
        month = str(rec.get('_sheet', '')).strip()
        nrec = {_norm_header(k): v for k, v in rec.items() if k != '_sheet'}

        bug = {'month': month, 'project': project}
        for nh, field in _FIELD_MAP.items():
            val = nrec.get(nh, [] if field == 'screenshot_urls' else '')
            if field in ('qa_pic', 'dev_pic') and isinstance(val, str):
                val = _remove_accents(val).strip()
            bug[field] = val
        if not isinstance(bug['screenshot_urls'], list):
            bug['screenshot_urls'] = []

        bug['status'] = _lifecycle_status(
            nrec.get('status', ''), nrec.get('test status', ''), nrec.get('dev status', ''))
        # status_raw = CỘT "Status" gốc trong Excel (đã là công thức gộp dev+test status).
        # Dùng cho metric dashboard "bug theo từng status" — user muốn sát file, KHÔNG gộp
        # lifecycle. Migration-safe: bug cache cũ thiếu field này -> coi như '' (xem #...).
        bug['status_raw'] = str(nrec.get('status', '') or '').strip()

        bug['bug_no'] = str(bug.get('bug_no', '')).strip()
        bug['service'] = service
        base_key = f"{project}#{service}#{month}#{bug['bug_no']}" if service else f"{project}#{month}#{bug['bug_no']}"
        bug['key'] = base_key if bug['bug_no'] else ''
        parsed.append(bug)

    # đếm khoá để bắt trùng (chỉ tính dòng CÓ bug_no)
    key_count = {}
    for b in parsed:
        if b['key']:
            key_count[b['key']] = key_count.get(b['key'], 0) + 1

    bugs, unmapped = [], []
    for b in parsed:
        if not b['bug_no']:
            unmapped.append({**b, 'reason': 'no_stt'})
        elif key_count[b['key']] > 1:
            unmapped.append({**b, 'reason': 'dup_stt'})
        else:
            bugs.append(b)
    return {'bugs': bugs, 'unmapped': unmapped}


# ===== Entry =====
def _resolve_file_id(file_id):
    if file_id:
        return file_id
    sources = load_sources()
    if not sources:
        raise RuntimeError('Chưa cấu hình file Drive nguồn (Quản lý Drive Link).')
    return sources[0]['id']


def fetch_meta(file_id=None):
    """Chỉ lấy metadata (Tầng-1, rẻ) -> meta {fileId, name, modifiedTime, md5Checksum}.

    Dùng để check file có đổi không TRƯỚC khi tải binary (tránh download lãng phí khi
    file y nguyên). file_id=None -> nguồn đầu tiên trong cấu hình."""
    fid = _resolve_file_id(file_id)
    m = file_metadata(fid)
    return {
        'fileId': fid,
        'name': m.get('name', ''),
        'modifiedTime': m.get('modifiedTime', ''),
        'md5Checksum': m.get('md5Checksum', ''),
    }


def fetch_content(file_id=None):
    """Tải binary + parse 1 file bug log -> rows. CHỈ gọi khi đã biết file đổi (Tầng-2)."""
    fid = _resolve_file_id(file_id)
    return parse_xlsx(download_file(fid))


def fetch_rows(file_id=None):
    """Tải + parse 1 file bug log. Trả (rows, meta).

    file_id=None -> lấy nguồn đầu tiên trong cấu hình. Raise RuntimeError (đã redact token)
    nếu chưa kết nối Drive / chưa cấu hình nguồn / file lỗi — caller (#54) bắt để báo mềm.

    Giữ để tương thích; scan() (#54) nay dùng fetch_meta + fetch_content (Tầng-1/Tầng-2)."""
    fid = _resolve_file_id(file_id)
    meta = fetch_meta(fid)
    rows = fetch_content(fid)
    return rows, meta
