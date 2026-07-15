"""xlsx_export — build 1 file .xlsx tối giản bằng stdlib (zero-dep).

Dùng cho "Export Excel" bug log (dev lead lấy thông tin) + Excel chi tiết Reopen trong
report tháng. KHÔNG thêm openpyxl — giữ nguyên tắc minimal-deps (chỉ requests + cryptography).
Một .xlsx là 1 zip gồm vài XML; dùng `zipfile` + `inlineStr` (khỏi sharedStrings) là đủ để
Excel/LibreOffice mở đúng cột. Chỉ ghi text (mọi ô kiểu chuỗi).

Tuỳ chọn `wrap`/`col_widths` (thêm 2026-07): bật wrap text + set độ rộng cột (cần styles.xml)
để cột mô tả dài KHÔNG tràn sang ô bên cạnh. Không truyền -> output y hệt bản cũ (không có
styles part) -> caller cũ (bug log export) không đổi hành vi.
"""
import io
import re
import zipfile
from xml.sax.saxutils import escape

# Ký tự KHÔNG hợp lệ trong XML 1.0 (trừ \t \n \r) — Excel từ chối mở nếu dính.
_BAD_XML = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
_CELL_MAX = 32767   # giới hạn 1 ô của Excel

_MAIN_NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

# styles.xml: 3 cellXfs — 0=mặc định, 1=wrap+top (body), 2=bold+wrap+top (header).
_STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<styleSheet xmlns="{_MAIN_NS}">'
    '<fonts count="2">'
    '<font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font>'
    '</fonts>'
    '<fills count="2">'
    '<fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill>'
    '</fills>'
    '<borders count="1"><border/></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="3">'
    '<xf xfId="0"/>'
    '<xf xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>'
    '<xf xfId="0" fontId="1" applyFont="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>'
    '</cellXfs>'
    '</styleSheet>'
)


def _clean(v):
    s = '' if v is None else str(v)
    s = _BAD_XML.sub('', s)
    return s[:_CELL_MAX]


def _cell(v, s=None):
    sattr = f' s="{s}"' if s is not None else ''
    return (f'<c t="inlineStr"{sattr}><is><t xml:space="preserve">'
            f'{escape(_clean(v))}</t></is></c>')


def _row(cells, s=None):
    return '<row>' + ''.join(_cell(c, s) for c in cells) + '</row>'


def build_xlsx(headers, rows, sheet_name='Sheet1', col_widths=None, wrap=False):
    """headers = list[str]; rows = list[list]. Trả bytes của file .xlsx.

    col_widths = list số (độ rộng cột theo ký tự, None/0 = bỏ qua cột đó).
    wrap = True -> wrap text + căn trên cho mọi ô (cột dài xuống dòng, không tràn).
    Không truyền cả hai -> giữ output cũ (không styles part)."""
    sheet_name = (_clean(sheet_name) or 'Sheet1')[:31]
    use_styles = bool(wrap or col_widths)
    hdr_s = 2 if use_styles else None
    body_s = 1 if use_styles else None
    body = _row(headers, hdr_s) + ''.join(_row(r, body_s) for r in rows)

    cols_xml = ''
    if col_widths:
        parts = [f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>'
                 for i, w in enumerate(col_widths, start=1) if w]
        if parts:
            cols_xml = '<cols>' + ''.join(parts) + '</cols>'

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{_MAIN_NS}">'
        f'{cols_xml}<sheetData>{body}</sheetData></worksheet>'
    )
    styles_override = ('<Override PartName="/xl/styles.xml" ContentType="application/vnd.'
                       'openxmlformats-officedocument.spreadsheetml.styles+xml"/>') if use_styles else ''
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        f'{styles_override}'
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
        f'<workbook xmlns="{_MAIN_NS}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    styles_rel = ('<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
                  'officeDocument/2006/relationships/styles" Target="styles.xml"/>') if use_styles else ''
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        f'{styles_rel}'
        '</Relationships>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', root_rels)
        z.writestr('xl/workbook.xml', workbook)
        z.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        z.writestr('xl/worksheets/sheet1.xml', sheet_xml)
        if use_styles:
            z.writestr('xl/styles.xml', _STYLES_XML)
    return buf.getvalue()
