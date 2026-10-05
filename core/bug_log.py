"""Đọc sheet .xlsx bằng stdlib (zipfile + xml.etree) — KHÔNG openpyxl.

Phần nguồn Bug Log từ Google Drive đã gỡ (cut-over sang Jira "Bug Testing" — Decision #104).
Module này giờ CHỈ còn primitive đọc .xlsx thô, dùng bởi `file_preview.py` để xem trước file
.xlsx người dùng upload ở tab Tài liệu (#63). Zero network, zero Drive.

API public: list_sheet_names(data) · read_sheet_rows(data, sheet_name).
"""
import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET


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
    """Giá trị 1 ô <c> -> str (hoặc '' nếu rỗng). Giữ số dạng str."""
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
    return v


def _read_rows(zf, path, shared):
    """worksheet -> list[list[str]] (mỗi row = list ô theo cột, fill '' ở cột thiếu; pad dòng
    trống để chỉ số khớp số dòng Excel)."""
    rows = []
    current_row = 1
    for _ev, row in ET.iterparse(BytesIO(zf.read(path))):
        if _localname(row.tag) != 'row':
            continue
        r_attr = row.get('r')
        if r_attr:
            try:
                row_idx = int(r_attr)
                while current_row < row_idx:
                    rows.append([])
                    current_row += 1
            except ValueError:
                pass
        cells = {}
        maxc = -1
        for c in row:
            if _localname(c.tag) != 'c':
                continue
            ci = _col_index(c.get('r', ''))
            cells[ci] = _cell_value(c, shared)
            maxc = max(maxc, ci)
        rows.append([cells.get(i, '') for i in range(maxc + 1)])
        current_row += 1
        row.clear()
    return rows


# ===== API public — dùng bởi file_preview (#63) =====
def list_sheet_names(data):
    """bytes .xlsx -> [tên sheet] theo thứ tự workbook. Raise RuntimeError nếu file hỏng."""
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        raise RuntimeError('File tải về không phải .xlsx hợp lệ.')
    with zf:
        return [name for name, _path in _sheet_targets(zf)]


def read_sheet_rows(data, sheet_name):
    """bytes .xlsx + tên sheet -> list[list[str]] (rows thô). Raise nếu file hỏng / không thấy sheet."""
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        raise RuntimeError('File tải về không phải .xlsx hợp lệ.')
    with zf:
        shared = _read_shared_strings(zf)
        for name, path in _sheet_targets(zf):
            if name == sheet_name:
                try:
                    return _read_rows(zf, path, shared)
                except KeyError:
                    raise RuntimeError('Không đọc được nội dung sheet đã chọn.')
        raise RuntimeError(f'Không tìm thấy sheet "{sheet_name}" trong file.')
