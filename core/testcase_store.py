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
import difflib

from config import TESTCASE_FILE, atomic_write
from remote_store import synced_load, synced_save
from bug_log_source import extract_file_id
from bug_log import (fetch_meta, download_file, list_sheet_names, read_sheet_rows)

import json

TC_PROP = 'qa-dashboard-testcases'  # khoá KV / Jira property = kho sync chéo máy

MAX_FOLDERS = 100
MAX_CASES = 50000           # chặn payload quá lớn (KV có hỗ trợ GZIP tự động nên mức 50k là an toàn)
TC_RESULTS = ('pass', 'fail', 'impact', 'norun')
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
    'impact': 'impact',
    'norun': 'norun', 'no run': 'norun', 'not run': 'norun', 'chưa chạy': 'norun', 'chua chay': 'norun', 'untested': 'norun',
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
        result_cols = []
        for field, syns in _HEADER_SYNONYMS.items():
            for ci, cell in enumerate(norm_cells):
                if cell in syns:
                    if field == 'result':
                        if ci not in result_cols:
                            result_cols.append(ci)
                    elif field not in colmap:
                        colmap[field] = ci
                        break
        
        if result_cols:
            colmap['result'] = result_cols

        if sum(1 for f in _REQUIRED_FOR_HEADER if f in colmap) >= 2:
            # Check thêm dòng bên dưới (sub-header) cho các field còn thiếu (vd: 'result' của Round 1)
            for offset in (1, 2):
                if ridx + offset < len(rows):
                    sub_norm_cells = [_norm(c) for c in rows[ridx + offset]]
                    for field, syns in _HEADER_SYNONYMS.items():
                        if field == 'result':
                            for ci, cell in enumerate(sub_norm_cells):
                                if cell in syns and ci not in result_cols:
                                    result_cols.append(ci)
                        elif field not in colmap:
                            for ci, cell in enumerate(sub_norm_cells):
                                if cell in syns:
                                    colmap[field] = ci
                                    break
            if result_cols:
                colmap['result'] = sorted(result_cols)
            return ridx, colmap
    return None, {}


def parse_testcase_rows(rows):
    """rows thô (1 sheet) -> (cases, skipped, total, missing_id_rows).

    cases = list {id, item, pre, step, exp, priority, result='norun'} (CHƯA gắn folder).
    - total   = số dòng dữ liệu (sau header) có nội dung.
    - skipped = số dòng bị bỏ vì thiếu dữ liệu bắt buộc khác (item/expected) NHƯNG cũng không có ID/nội dung.
    - missing_id_rows = list số dòng (1-based theo sheet) CÓ nội dung (mô tả/expected/step) NHƯNG thiếu ID.
      Caller dùng cái này để CHẶN import + báo lỗi thiếu ID.
    Raise RuntimeError nếu không nhận diện được hàng tiêu đề (sai convention cột)."""
    hidx, col = _find_header(rows)
    if hidx is None:
        raise RuntimeError('Không tìm thấy hàng tiêu đề (cần các cột: ID, Test Item, '
                           'Pre-Condition, Step, Expected Output).')

    module_code = ''
    for r in rows[:hidx]:
        for i, cell_val in enumerate(r):
            if _norm(cell_val) == 'module code':
                if i + 1 < len(r):
                    module_code = str(r[i+1]).strip()
                break
        if module_code:
            break

    def cell(row, field):
        ci = col.get(field)
        if ci is None:
            return ''
        
        if isinstance(ci, list):
            # Lấy cột cuối cùng (bên phải nhất) có dữ liệu
            for idx in reversed(ci):
                if idx < len(row):
                    s = str(row[idx]).strip() if not isinstance(row[idx], str) else row[idx].strip()
                    s = re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]+', '', s)
                    if s:
                        return s
            return ''

        if ci >= len(row):
            return ''
        s = str(row[ci]).strip() if not isinstance(row[ci], str) else row[ci].strip()
        return re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]+', '', s)

    cases, skipped, total, missing_id_rows = [], 0, 0, []
    last_item = ''
    last_pre = ''

    for offset, row in enumerate(rows[hidx + 1:]):
        if not any(re.sub(r'[\u200b\u200c\u200d\u200e\u200f\ufeff]+', '', str(x)).strip() for x in row):
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
        step_val = cell(row, 'step')

        # Rule theo yêu cầu user: Nếu có khai báo Module Code, ID phải có dạng [ModuleCode-Số]
        # (VD: [VCN-01], VCN-01, [Funtion1-137]). Nếu không khớp regex -> skip dòng rác này.
        if module_code and cid:
            pattern = r'^\[?\s*' + re.escape(module_code.lower()) + r'\s*-\s*[a-zA-Z0-9_.]+\s*\]?$'
            if not re.match(pattern, cid.lower().strip()):
                skipped += 1
                continue

        if not cid:
            # - Nếu có item_raw VÀ có thêm thông tin khác (pre/step/exp) -> user tạo test case mới nhưng quên ID -> Chặn để nhắc
            # (Nếu chỉ có item_raw mà không có gì khác -> đây là group header gõ vào cột Item -> bỏ qua)
            if item_raw and (pre_raw or step_val or exp_val):
                missing_id_rows.append(hidx + 1 + offset + 1)
            # - Nếu KHÔNG có item_raw nhưng có step/exp -> do text dài bị tràn dòng (spill over) hoặc merge ô ID/Item 
            # -> Nối tiếp nội dung vào test case liền trước
            elif cases and (pre_raw or step_val or exp_val):
                if pre_raw:
                    cases[-1]['pre'] = (cases[-1]['pre'] + '\n' + pre_raw).strip()
                if step_val:
                    cases[-1]['step'] = (cases[-1]['step'] + '\n' + step_val).strip()
                if exp_val:
                    cases[-1]['exp'] = (cases[-1]['exp'] + '\n' + exp_val).strip()
                
                r_val = cell(row, 'result')
                if r_val:
                    cases[-1]['result'] = _norm_result(r_val)
                    
                p_val = cell(row, 'priority')
                if p_val:
                    cases[-1]['priority'] = _norm_priority(p_val)
            else:
                skipped += 1
            continue

        # Có ID nhưng hoàn toàn KHÔNG CÓ nội dung thực tế (không có item_raw, không step, không exp)
        # -> Đây thường là dòng phân nhóm (group header) do user gõ nhầm vào cột ID (hoặc ô merge)
        if cid and not item_raw and not step_val and not exp_val:
            skipped += 1
            continue

        # Có ID và có nội dung: Hợp lệ để import kể cả khi khuyết step hoặc expected.

        r_val = cell(row, 'result')
        cases.append({
            'id': cid,
            'item': item_val,
            'pre': pre_val,
            'step': step_val,
            'exp': exp_val,
            'priority': _norm_priority(cell(row, 'priority')),
            'result': _norm_result(r_val) if r_val else '',
        })

    # Đánh lại số thứ tự ID cho liền mạch (fix lỗi nhảy số do có dòng note của QA)
    if module_code and cases:
        pad = 2
        m = re.search(r'-(\d+)', cases[0]['id'])
        if m:
            pad = max(2, len(m.group(1)))
        has_bracket = '[' in cases[0]['id']

        for idx, c in enumerate(cases):
            new_num = str(idx + 1).zfill(pad)
            if has_bracket:
                c['id'] = f"[{module_code}-{new_num}]"
            else:
                c['id'] = f"{module_code}-{new_num}"

    return cases, skipped, total, missing_id_rows


# Sheet template — bỏ qua khi import cả file (không chọn sheet cụ thể). So khớp lower+strip.
TEMPLATE_SHEETS = {'cover', 'guide', 'result', 'function 1'}


def _is_template_sheet(name):
    return (name or '').strip().lower() in TEMPLATE_SHEETS


def _get_content_sig(c):
    return f"{c.get('item','')}||{c.get('pre','')}||{c.get('step','')}||{c.get('exp','')}"


def _apply_sheet_cases(data, parent_folder_id, sheet, new_cases):
    """Ghi đè cases của sub-folder (theo tên sheet) trong parent. Mutates `data`. Trả count.

    GIỮ result đã chấm bằng Smart Sync (Sequence Alignment + Fuzzy Match + ID Fallback)."""
    sub_folder = next((f for f in data['folders']
                       if f.get('parent_id') == parent_folder_id and f.get('name') == sheet), None)
    if not sub_folder:
        sub_id = 'f_' + format(int(time.time() * 1000) + len(data['folders']), 'x')
        sub_folder = {'id': sub_id, 'name': sheet, 'parent_id': parent_folder_id}
        data['folders'].append(sub_folder)
    target_folder_id = sub_folder['id']

    old_cases = [c for c in data['cases'] if c.get('folder') == target_folder_id]
    data['cases'] = [c for c in data['cases'] if c.get('folder') != target_folder_id]

    # Khởi tạo dữ liệu phục vụ Smart Sync
    old_sigs = [_get_content_sig(c) for c in old_cases]
    new_sigs = [_get_content_sig(c) for c in new_cases]
    mapped_old_indices = set()
    updated_result_count = 0

    # Pass 1: Structural Sequence Alignment (LCS)
    sm = difflib.SequenceMatcher(None, old_sigs, new_sigs)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal' or (tag == 'replace' and (i2 - i1) == (j2 - j1)):
            for i, j in zip(range(i1, i2), range(j1, j2)):
                r = old_cases[i].get('result', 'norun')
                r_norm = r if r in TC_RESULTS else 'norun'
                parsed = new_cases[j].get('result', '')
                if parsed:
                    if parsed != r_norm:
                        updated_result_count += 1
                    new_cases[j]['result'] = parsed
                else:
                    new_cases[j]['result'] = r_norm
                mapped_old_indices.add(i)
                new_cases[j]['_mapped'] = True

    # Pass 2: Fuzzy String Matching cho các case bị rớt lại (sửa typo làm hỏng khối equal/replace)
    old_unmapped_indices = set(range(len(old_cases))) - mapped_old_indices
    for j, c in enumerate(new_cases):
        if c.get('_mapped'): continue
        best_i, best_ratio = -1, 0.8  # Threshold 80% độ tương đồng
        for i in old_unmapped_indices:
            ratio = difflib.SequenceMatcher(None, new_sigs[j], old_sigs[i]).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_i = i
        if best_i != -1:
            r = old_cases[best_i].get('result', 'norun')
            r_norm = r if r in TC_RESULTS else 'norun'
            parsed = c.get('result', '')
            if parsed:
                if parsed != r_norm:
                    updated_result_count += 1
                c['result'] = parsed
            else:
                c['result'] = r_norm
            mapped_old_indices.add(best_i)
            old_unmapped_indices.remove(best_i)
            c['_mapped'] = True

    # Pass 3: ID Match Fallback (trường hợp sửa hẳn nội dung nhưng vẫn giữ được ID)
    old_unmapped = {old_cases[i]['id']: old_cases[i] for i in old_unmapped_indices}
    for c in new_cases:
        if c.get('_mapped'):
            del c['_mapped']
            continue
        parsed = c.get('result', '')
        old_c = old_unmapped.get(c['id'])
        r = old_c.get('result', 'norun') if old_c else 'norun'
        r_norm = r if r in TC_RESULTS else 'norun'
        
        if parsed:
            if old_c and parsed != r_norm:
                updated_result_count += 1
            c['result'] = parsed
        else:
            c['result'] = r_norm

    for c in new_cases:
        c['folder'] = target_folder_id
    data['cases'].extend(new_cases)
    return len(new_cases), updated_result_count


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
    """Import test case vào folder = mỗi sheet GHI ĐÈ 1 sub-folder cùng tên.

    `sheet` rỗng -> import CẢ FILE (mọi sheet trừ template: Cover/Guide/Result/Function 1).
    GIỮ result đã chấm theo case id (re-import nội dung không mất công chấm).
    Trả dict {ok, count, skipped, msg}. CHẶN toàn bộ import nếu BẤT KỲ sheet nào có dòng thiếu ID."""
    folder_id = (folder_id or '').strip()
    data = load_testcases()
    folder = next((f for f in data['folders'] if f.get('id') == folder_id), None)
    if folder is None:
        return {'ok': False, 'msg': 'Thư mục đích không tồn tại.'}

    fid = extract_file_id(url)
    if not fid:
        return {'ok': False, 'msg': 'Link Google Sheet không hợp lệ.'}
    sheet = (sheet or '').strip()

    try:
        meta = fetch_meta(fid)
        content = download_file(fid, meta.get('mimeType', ''))
        all_sheets = list_sheet_names(content)
        if sheet:
            if sheet not in all_sheets:
                return {'ok': False, 'msg': f'Sheet "{sheet}" không có trong file.'}
            target_sheets = [sheet]
        else:
            target_sheets = [s for s in all_sheets if not _is_template_sheet(s)]
            if not target_sheets:
                return {'ok': False, 'msg': 'Không có sheet nào để import '
                                            '(đã bỏ qua các sheet template).'}
        # parse từng sheet TRƯỚC khi ghi -> validate toàn bộ rồi mới apply (all-or-nothing)
        parsed = []        # (sheet, cases, skipped, missing_id_rows)
        no_header = []     # sheet không có cột yêu cầu -> coi như data fake, BỎ QUA (import cả file)
        for s in target_sheets:
            rows = read_sheet_rows(content, s)
            if not sheet and _find_header(rows)[0] is None:
                no_header.append(s)
                continue
            cases_s, skipped_s, _total_s, missing_s = parse_testcase_rows(rows)
            parsed.append((s, cases_s, skipped_s, missing_s))
    except RuntimeError as e:
        return {'ok': False, 'msg': str(e)}   # bug_log đã redact token

    # Có dòng mang nội dung (step/expected) nhưng thiếu ID ở BẤT KỲ sheet -> CHẶN cả import.
    err_sheets = [(s, miss) for (s, _c, _sk, miss) in parsed if miss]
    if err_sheets:
        lines = []
        for s, miss in err_sheets:
            preview = ', '.join(str(r) for r in miss[:10])
            more = f' …(+{len(miss) - 10} dòng)' if len(miss) > 10 else ''
            lines.append(f'• Sheet "{s}": {len(miss)} dòng thiếu ID (dòng {preview}{more})')
        return {'ok': False, 'missing_id_rows': True,
                'msg': 'Import thất bại — thiếu ID:\n' + '\n'.join(lines)
                       + '\nBổ sung cột ID rồi import lại.'}

    # Apply mọi sheet hợp lệ (mutate data trong RAM, chỉ lưu khi qua hết check).
    applied, empty_sheets, total_skipped, total_count = [], [], 0, 0
    total_updated_results = 0
    for s, cases_s, skipped_s, _miss in parsed:
        total_skipped += skipped_s
        if not cases_s:
            empty_sheets.append(s)
            continue
        cnt, upd = _apply_sheet_cases(data, folder_id, s, cases_s)
        total_count += cnt
        total_updated_results += upd
        applied.append(s)

    if not applied:
        return {'ok': False, 'msg': 'Không có test case hợp lệ trong '
                + ('sheet đã chọn.' if sheet
                   else 'các sheet (đã bỏ qua template / sheet không đúng định dạng).')}

    if len(data['cases']) > MAX_CASES:
        return {'ok': False, 'msg': f'Vượt quá tối đa {MAX_CASES} test case toàn hệ thống.'}

    data.setdefault('imports', {})[folder_id] = {
        'url': url, 'fileId': fid,
        'sheet': sheet if sheet else '(toàn bộ file)',
        'at': time.strftime('%Y-%m-%d %H:%M'), 'by': by_email or '',
        'count': total_count,
    }
    if not save_testcases(data):
        return {'ok': False, 'msg': 'Không lưu được (KV/local lỗi).'}

    if sheet:
        msg = f'Đã import {total_count} test case vào "{folder.get("name")}"'
        extra = []
        if total_skipped:
            extra.append(f'bỏ {total_skipped} dòng thiếu dữ liệu bắt buộc')
        if total_updated_results > 0:
            extra.append(f'cập nhật kết quả cho {total_updated_results} test case')
        if extra:
            msg += ' (' + ', '.join(extra) + ').'
        else:
            msg += '.'
    else:
        msg = f'Đã import {len(applied)} sheet · {total_count} test case vào "{folder.get("name")}".'
        extra = []
        if no_header:
            extra.append(f'bỏ qua {len(no_header)} sheet không đúng định dạng')
        if empty_sheets:
            extra.append(f'bỏ qua {len(empty_sheets)} sheet rỗng')
        if total_skipped:
            extra.append(f'bỏ {total_skipped} dòng thiếu dữ liệu bắt buộc')
        if total_updated_results > 0:
            extra.append(f'cập nhật kết quả cho {total_updated_results} test case')
        if extra:
            msg += ' (' + ', '.join(extra) + ').'
    return {'ok': True, 'count': total_count, 'skipped': total_skipped, 'msg': msg}
