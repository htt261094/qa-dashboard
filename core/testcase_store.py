"""Bộ test case import từ Google Drive — store + parse + ghi đè (issue #152, epic #151).

Tầng NỀN cho mảng quản lý test case (B–E phụ thuộc store + schema ở đây).

Mô hình:
  - **Repository** = list folder phẳng `{id, name}`. Mỗi folder = 1 "bộ" test case.
  - **cases** = list `{id, item, pre, step, exp, priority, result, folder}`.
      result ∈ TC_RESULTS (mặc định 'norun'); sheet KHÔNG có cột Result -> trạng thái
      chạy chấm tay sau (#155/#156). Import lại GIỮ result cũ theo case id (xem import_cases).
  - **imports** = metadata mỗi lần import theo folder `{folder_id: {url, fileId, sheet, at, by, count}}`.

Drive: TÁI DÙNG bug_log.{fetch_meta, download_file, list_sheet_names, read_sheet_rows}
(Decision #29) — KHÔNG viết lại Drive client. Hỗ trợ Google Sheet native (export->xlsx)
lẫn .xlsx thật như Bug Log.

Sync chéo máy: Cloudflare KV (local-first, không cần VPN) qua remote_store; file local
`.testcase_config.json` = fallback offline (giống docs/roadmap, Decision #14/cloudflare-kv-sync).

Import = **GHI ĐÈ toàn bộ** cases của folder đó (không merge/append) — user xác nhận ở UI.

OPSEC: token/PAT redact trong bug_log; module này không chạm credential trực tiếp.

Layer: config -> {jira_api} -> {bug_log, bug_log_source, remote_store} -> (this) -> render.
Không cycle.
"""
import re
import time

from config import TESTCASE_FILE, atomic_write
from remote_store import synced_load, synced_save
from bug_log_source import extract_file_id
from bug_log import (fetch_meta, download_file, list_sheet_names, read_sheet_rows)

import json

TC_PROP = 'qa-dashboard-testcases'  # khoá KV / Jira property = kho sync chéo máy

MAX_FOLDERS = 100
MAX_CASES = 5000            # chặn payload quá lớn (KV ~ vài chục KB an toàn)
TC_RESULTS = ('pass', 'fail', 'pending', 'blocked', 'norun')
_PRIORITIES = ('critical', 'high', 'medium', 'low')

TC_DEFAULT = {'folders': [], 'cases': [], 'imports': {}}


# ===== Validate shape (trước khi lưu) =====
def _valid_folder(f):
    return (isinstance(f, dict) and isinstance(f.get('id', ''), str) and f.get('id')
            and isinstance(f.get('name', ''), str)
            and (f.get('parent_id') is None or isinstance(f.get('parent_id'), str)))


def _valid_case(c):
    return (isinstance(c, dict)
            and isinstance(c.get('id', ''), str)
            and all(isinstance(c.get(k, ''), str) for k in ('item', 'pre', 'step', 'exp', 'folder'))
            and isinstance(c.get('priority', ''), str)
            and isinstance(c.get('result', ''), str))


def valid_store(data):
    """{folders:[...], cases:[...], imports:{...}} đúng shape + trong cap."""
    if not isinstance(data, dict):
        return False
    folders = data.get('folders')
    cases = data.get('cases')
    imports = data.get('imports', {})
    if not isinstance(folders, list) or len(folders) > MAX_FOLDERS:
        return False
    if not isinstance(cases, list) or len(cases) > MAX_CASES:
        return False
    if not isinstance(imports, dict):
        return False
    return all(_valid_folder(f) for f in folders) and all(_valid_case(c) for c in cases)


# ===== Local cache (fallback offline) =====
def _read_cache():
    if TESTCASE_FILE.exists():
        try:
            data = json.loads(TESTCASE_FILE.read_text(encoding='utf-8'))
            if valid_store(data):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(data):
    atomic_write(TESTCASE_FILE, json.dumps(data, ensure_ascii=False, indent=2))


def load_testcases():
    """Kho chung = Cloudflare KV (sync chéo máy); file local = fallback offline."""
    return synced_load(TC_PROP, _read_cache, _write_cache, valid_store, TC_DEFAULT)


def save_testcases(data):
    """Local-first: ghi local trước (luôn OK) rồi đẩy KV best-effort. True nếu data đã an
    toàn ở local (kể cả khi KV/VPN down)."""
    return synced_save(TC_PROP, data, _write_cache, valid_store)


# ===== Folder (repository) =====
def add_folder(name):
    """Thêm 1 bộ/folder mới. Trả (ok, data|msg). id sinh tự động."""
    name = (name or '').strip()
    if not name:
        return False, 'Chưa nhập tên thư mục.'
    data = load_testcases()
    if len(data.get('folders', [])) >= MAX_FOLDERS:
        return False, f'Đã đạt tối đa {MAX_FOLDERS} thư mục.'
    fid = 'f_' + format(int(time.time() * 1000), 'x')
    # tránh trùng id nếu add liên tiếp trong cùng mili-giây
    existing = {f.get('id') for f in data['folders']}
    while fid in existing:
        fid += 'x'
    data['folders'].append({'id': fid, 'name': name})
    if not save_testcases(data):
        return False, 'Không lưu được (KV/local lỗi).'
    return True, data


def delete_folder(folder_id):
    """Xoá 1 folder + toàn bộ cases + metadata import của nó. (Kèm cả folder con)"""
    folder_id = (folder_id or '').strip()
    data = load_testcases()
    if not any(f.get('id') == folder_id for f in data['folders']):
        return False, 'Không tìm thấy thư mục.'
    
    # Tìm tất cả ID của folder con (để xoá cascade)
    to_delete = {folder_id}
    # Lặp để quét n-level cascade
    while True:
        added = False
        for f in data['folders']:
            if f.get('parent_id') in to_delete and f.get('id') not in to_delete:
                to_delete.add(f.get('id'))
                added = True
        if not added:
            break

    data['folders'] = [f for f in data['folders'] if f.get('id') not in to_delete]
    data['cases'] = [c for c in data['cases'] if c.get('folder') not in to_delete]
    for fid in to_delete:
        data.get('imports', {}).pop(fid, None)
        
    if not save_testcases(data):
        return False, 'Không lưu được (KV/local lỗi).'
    return True, data


def rename_folder(folder_id, new_name):
    """Đổi tên folder. Trả (ok, data|msg)."""
    folder_id = (folder_id or '').strip()
    new_name = (new_name or '').strip()
    if not new_name:
        return False, 'Chưa nhập tên thư mục mới.'
    data = load_testcases()
    folder = next((f for f in data['folders'] if f.get('id') == folder_id), None)
    if not folder:
        return False, 'Không tìm thấy thư mục.'
    folder['name'] = new_name
    if not save_testcases(data):
        return False, 'Không lưu được (KV/local lỗi).'
    return True, data


# ===== Parse sheet test case (convention 5/6 cột) =====
# Map TÊN header (chuẩn hoá lower+trim) -> field, defensive với schema drift + đa ngôn ngữ.
# ID là cột BẮT BUỘC; dòng thiếu ID bị skip (report số lượng). Priority tuỳ chọn.
_HEADER_SYNONYMS = {
    'id': ('id', 'test case id', 'tc id', 'testcase id', 'case id', 'mã', 'ma', 'stt'),
    'item': ('test item', 'item', 'mục test', 'muc test', 'test case', 'testcase',
             'tên test', 'ten test', 'name', 'title', 'tiêu đề', 'tieu de'),
    'pre': ('pre-condition', 'precondition', 'pre condition', 'pre',
            'điều kiện', 'dieu kien', 'tiền điều kiện', 'tien dieu kien'),
    'step': ('step', 'steps', 'các bước', 'cac buoc', 'bước', 'buoc', 'thao tác', 'thao tac'),
    'exp': ('expected output', 'expected result', 'expected', 'output',
            'kết quả mong muốn', 'ket qua mong muon', 'kết quả', 'ket qua', 'mong muốn'),
    'priority': ('priority', 'mức độ', 'muc do', 'độ ưu tiên', 'do uu tien',
                 'ưu tiên', 'uu tien', 'severity'),
    'result': ('result', 'kết quả thực tế', 'ket qua thuc te', 'kết quả', 'ket qua', 'status', 'trạng thái', 'trang thai', 'actual result', 'actual'),
}
_REQUIRED_FOR_HEADER = ('id', 'item')  # 1 hàng được coi là header khi có >=2 trong các cột chính

# Giá trị priority -> chuẩn hoá {critical, high, medium, low}.
_PRI_MAP = {
    'critical': 'critical', 'nghiêm trọng': 'critical', 'nghiem trong': 'critical',
    'blocker': 'critical', 'urgent': 'critical', '1': 'critical',
    'high': 'high', 'cao': 'high', '2': 'high',
    'medium': 'medium', 'trung bình': 'medium', 'trung binh': 'medium',
    'normal': 'medium', 'tb': 'medium', '3': 'medium',
    'low': 'low', 'thấp': 'low', 'thap': 'low', 'minor': 'low', '4': 'low',
}

_RESULT_MAP = {
    'pass': 'pass', 'passed': 'pass', 'ok': 'pass', 'đạt': 'pass', 'dat': 'pass',
    'fail': 'fail', 'failed': 'fail', 'lỗi': 'fail', 'loi': 'fail', 'không đạt': 'fail', 'khong dat': 'fail', 'ng': 'fail', 'not ok': 'fail',
    'pending': 'pending', 'chờ': 'pending', 'cho': 'pending', 'chờ fix': 'pending',
    'blocked': 'blocked', 'block': 'blocked',
    'norun': 'norun', 'no run': 'norun', 'chưa chạy': 'norun', 'chua chay': 'norun', 'untested': 'norun',
}


def _norm(s):
    return re.sub(r'\s+', ' ', str(s or '').strip()).lower()


def _norm_priority(v):
    return _PRI_MAP.get(_norm(v), 'medium')


def _norm_result(v):
    return _RESULT_MAP.get(_norm(v), 'norun')


def _find_header(rows):
    """Tìm hàng tiêu đề + map {field: col_index}. Trả (header_row_idx, colmap) hoặc (None, {})."""
    for ridx, row in enumerate(rows[:20]):   # header thường ở đầu file
        norm_cells = [_norm(c) for c in row]
        colmap = {}
        for field, syns in _HEADER_SYNONYMS.items():
            for ci, cell in enumerate(norm_cells):
                if cell in syns and field not in colmap:
                    colmap[field] = ci
                    break
        
        if sum(1 for f in _REQUIRED_FOR_HEADER if f in colmap) >= 2:
            # Check thêm dòng bên dưới (sub-header) cho các field còn thiếu (vd: 'result' của Round 1)
            for offset in (1, 2):
                if ridx + offset < len(rows):
                    sub_norm_cells = [_norm(c) for c in rows[ridx + offset]]
                    for field, syns in _HEADER_SYNONYMS.items():
                        if field not in colmap:
                            for ci, cell in enumerate(sub_norm_cells):
                                if cell in syns:
                                    colmap[field] = ci
                                    break
            return ridx, colmap
    return None, {}


def parse_testcase_rows(rows):
    """rows thô (1 sheet) -> (cases, skipped, total).

    cases = list {id, item, pre, step, exp, priority, result='norun'} (CHƯA gắn folder).
    - total   = số dòng dữ liệu (sau header) có nội dung.
    - skipped = số dòng bị bỏ vì THIẾU ID.
    Raise RuntimeError nếu không nhận diện được hàng tiêu đề (sai convention cột)."""
    hidx, col = _find_header(rows)
    if hidx is None:
        raise RuntimeError('Không tìm thấy hàng tiêu đề (cần các cột: ID, Test Item, '
                           'Pre-Condition, Step, Expected Output).')

    def cell(row, field):
        ci = col.get(field)
        if ci is None or ci >= len(row):
            return ''
        return str(row[ci]).strip() if not isinstance(row[ci], str) else row[ci].strip()

    cases, skipped, total = [], 0, 0
    last_item = ''
    last_pre = ''
    
    for row in rows[hidx + 1:]:
        if not any(str(x).strip() for x in row):
            continue   # dòng trống
        total += 1
        cid = cell(row, 'id')
        
        # Forward-fill cho các cột thường bị merge (Item, Pre-condition)
        item_raw = cell(row, 'item')
        if item_raw:
            last_item = item_raw
        item_val = item_raw or last_item
        
        pre_raw = cell(row, 'pre')
        if pre_raw:
            last_pre = pre_raw
        pre_val = pre_raw or last_pre

        exp_val = cell(row, 'exp')
        
        if not cid or not item_val or not exp_val:
            skipped += 1
            continue   # thiếu dữ liệu bắt buộc -> bỏ (báo số lượng)
            
        r_val = cell(row, 'result')
        cases.append({
            'id': cid,
            'item': item_val,
            'pre': pre_val,
            'step': cell(row, 'step'),
            'exp': exp_val,
            'priority': _norm_priority(cell(row, 'priority')),
            'result': _norm_result(r_val) if r_val else '',
        })
    return cases, skipped, total


# ===== Drive: list sheet + import =====
def fetch_sheets(url):
    """url/id Drive -> {fileId, name, sheets:[...]}. Dùng cho dropdown chọn sheet.

    Raise RuntimeError (đã redact token trong bug_log) nếu link sai / chưa kết nối Drive /
    file hỏng."""
    fid = extract_file_id(url)
    if not fid:
        raise RuntimeError('Link Google Sheet không hợp lệ — kiểm tra lại.')
    meta = fetch_meta(fid)
    content = download_file(fid, meta.get('mimeType', ''))
    return {'fileId': fid, 'name': meta.get('name', ''),
            'sheets': list_sheet_names(content)}


def import_cases(folder_id, url, sheet, by_email=''):
    """Import 1 sheet vào folder = GHI ĐÈ toàn bộ cases của folder đó.

    GIỮ result đã chấm theo case id (re-import sheet đã sửa nội dung không mất công chấm).
    Trả dict {ok, count, skipped, total, msg}. Soft-fail per-row (thiếu ID -> skip + report)."""
    folder_id = (folder_id or '').strip()
    data = load_testcases()
    folder = next((f for f in data['folders'] if f.get('id') == folder_id), None)
    if folder is None:
        return {'ok': False, 'msg': 'Thư mục đích không tồn tại.'}

    fid = extract_file_id(url)
    if not fid:
        return {'ok': False, 'msg': 'Link Google Sheet không hợp lệ.'}
    sheet = (sheet or '').strip()
    if not sheet:
        return {'ok': False, 'msg': 'Chưa chọn sheet.'}

    try:
        meta = fetch_meta(fid)
        content = download_file(fid, meta.get('mimeType', ''))
        rows = read_sheet_rows(content, sheet)
        new_cases, skipped, total = parse_testcase_rows(rows)
    except RuntimeError as e:
        return {'ok': False, 'msg': str(e)}   # bug_log đã redact token

    if not new_cases:
        return {'ok': False, 'msg': f'Không có test case hợp lệ trong sheet (bỏ {skipped} '
                                    f'dòng thiếu dữ liệu bắt buộc trên {total} dòng).'}

    # Tự động tạo hoặc lấy folder con theo tên sheet
    sub_folder = next((f for f in data['folders'] if f.get('parent_id') == folder_id and f.get('name') == sheet), None)
    if not sub_folder:
        sub_id = 'f_' + format(int(time.time() * 1000) + len(data['folders']), 'x')
        sub_folder = {'id': sub_id, 'name': sheet, 'parent_id': folder_id}
        data['folders'].append(sub_folder)
    
    target_folder_id = sub_folder['id']

    # GIỮ result cũ theo case id trong CHÍNH sub folder này (ghi đè nội dung, không mất kết quả chạy)
    prev_result = {c['id']: c.get('result', 'norun')
                   for c in data['cases'] if c.get('folder') == target_folder_id}
    
    # ghi đè: bỏ hết cases cũ của sub folder, thay bằng cases mới
    data['cases'] = [c for c in data['cases'] if c.get('folder') != target_folder_id]
    for c in new_cases:
        c['folder'] = target_folder_id
        parsed_result = c.get('result', '')
        r = prev_result.get(c['id'], 'norun')
        if parsed_result:
            c['result'] = parsed_result
        else:
            c['result'] = r if r in TC_RESULTS else 'norun'
    data['cases'].extend(new_cases)

    if len(data['cases']) > MAX_CASES:
        return {'ok': False, 'msg': f'Vượt quá tối đa {MAX_CASES} test case toàn hệ thống.'}

    data.setdefault('imports', {})[folder_id] = {
        'url': url, 'fileId': fid, 'sheet': sheet,
        'at': time.strftime('%Y-%m-%d %H:%M'), 'by': by_email or '',
        'count': len(new_cases),
    }
    if not save_testcases(data):
        return {'ok': False, 'msg': 'Không lưu được (KV/local lỗi).'}
    return {'ok': True, 'count': len(new_cases), 'skipped': skipped, 'total': total,
            'msg': f'Đã import {len(new_cases)} test case vào "{folder.get("name")}"'
                   + (f' (bỏ {skipped} dòng thiếu dữ liệu bắt buộc).' if skipped else '.')}
