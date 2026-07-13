"""xlsx_export — build 1 file .xlsx tối giản bằng stdlib (zero-dep).

Dùng cho "Export Excel" bug log (dev lead lấy thông tin). KHÔNG thêm openpyxl —
giữ nguyên tắc minimal-deps (chỉ requests + cryptography). Một .xlsx là 1 zip gồm
vài XML; dùng `zipfile` + `inlineStr` (khỏi sharedStrings) là đủ để Excel/LibreOffice
mở đúng cột. Chỉ ghi text (mọi ô kiểu chuỗi) — không format số/ngày (đủ cho export tra cứu).
"""
import io
import re
import zipfile
from xml.sax.saxutils import escape

# Ký tự KHÔNG hợp lệ trong XML 1.0 (trừ \t \n \r) — Excel từ chối mở nếu dính.
_BAD_XML = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
_CELL_MAX = 32767   # giới hạn 1 ô của Excel


def _clean(v):
    s = '' if v is None else str(v)
    s = _BAD_XML.sub('', s)
    return s[:_CELL_MAX]


def _cell(v):
    return (f'<c t="inlineStr"><is><t xml:space="preserve">'
            f'{escape(_clean(v))}</t></is></c>')


def _row(cells):
    return '<row>' + ''.join(_cell(c) for c in cells) + '</row>'


def build_xlsx(headers, rows, sheet_name='Sheet1'):
    """headers = list[str]; rows = list[list]. Trả bytes của file .xlsx."""
    sheet_name = (_clean(sheet_name) or 'Sheet1')[:31]
    body = _row(headers) + ''.join(_row(r) for r in rows)
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{body}</sheetData></worksheet>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', root_rels)
        z.writestr('xl/workbook.xml', workbook)
        z.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        z.writestr('xl/worksheets/sheet1.xml', sheet_xml)
    return buf.getvalue()
