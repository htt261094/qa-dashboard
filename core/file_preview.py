"""Preview nội dung file upload NGAY trong app (không mở tab mới) — Decision #63.

PDF/ảnh trình duyệt tự render (client nhúng thẳng `/uploads/...`), nên module này
chỉ lo các định dạng browser KHÔNG đọc được:

- `.xlsx/.xlsm` -> bảng HTML (tái dùng parser zero-dep của bug_log: `list_sheet_names`
  + `read_sheet_rows`, KHÔNG thêm openpyxl)
- `.docx`       -> đoạn văn + bảng, trích từ `word/document.xml` (zip + regex, stdlib)
- `.pptx`       -> text từng slide (`ppt/slides/slideN.xml`)
- text thuần (`.txt/.md/.csv/.json/.log/...`) -> `<pre>`, `.csv` thành bảng

Preview là bản GẦN ĐÚNG để đọc nhanh: mất định dạng (font/màu/merge cell phức tạp),
ảnh nhúng trong file bị bỏ. Cần bản gốc thì tải xuống / mở tab mới.

Layer: config -> bug_log/issues -> this. KHÔNG import qa_dashboard (tránh vòng import).
"""
import re
import zipfile
from io import BytesIO
from pathlib import Path

from issues import esc

# Cap để 1 file to không nuốt RAM / dựng HTML khổng lồ treo browser.
MAX_BYTES = 25_000_000     # bỏ qua file > 25MB (bằng cap upload)
MAX_ROWS = 500             # số dòng tối đa mỗi sheet/bảng
MAX_COLS = 40
MAX_BLOCKS = 800           # số đoạn văn (docx) / slide-line (pptx)
MAX_TEXT_CHARS = 400_000

TEXT_EXTS = {'.txt', '.md', '.markdown', '.csv', '.tsv', '.json', '.log',
             '.yml', '.yaml', '.xml', '.ini', '.cfg', '.sql'}
# Client tự nhúng, server không cần parse
NATIVE_EXTS = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'}
# Trình duyệt render được nhưng phải qua route `/file-raw` (sandbox) — Decision #65.
# KHÔNG dựng lại HTML ở đây: mất CSS/layout thì preview vô nghĩa.
RAW_EXTS = {'.html', '.htm'}


def _truncated(html, note):
    return html + f'<p class="fp-note">{esc(note)}</p>'


def _table_html(rows, caption=''):
    """rows: list[list[str]] -> bảng HTML (dòng đầu làm header)."""
    rows = [r for r in rows if any((c or '').strip() for c in r)]
    if not rows:
        return '<p class="fp-empty">Sheet trống.</p>'
    cut_rows = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    ncol = min(max(len(r) for r in rows), MAX_COLS)
    head, body = rows[0], rows[1:]

    def cells(r, tag):
        out = []
        for i in range(ncol):
            v = r[i] if i < len(r) else ''
            out.append(f'<{tag}>{esc(str(v))}</{tag}>')
        return ''.join(out)

    html = ['<div class="fp-table-wrap">']
    if caption:
        html.append(f'<div class="fp-sheet-name">{esc(caption)}</div>')
    html.append('<table class="fp-table"><thead><tr>')
    html.append(cells(head, 'th'))
    html.append('</tr></thead><tbody>')
    for r in body:
        html.append('<tr>' + cells(r, 'td') + '</tr>')
    html.append('</tbody></table></div>')
    out = ''.join(html)
    if cut_rows:
        out = _truncated(out, f'Chỉ hiển thị {MAX_ROWS} dòng đầu — tải file để xem đầy đủ.')
    return out


# ===== xlsx =====
def _xlsx_html(data):
    from bug_log import list_sheet_names, read_sheet_rows
    names = list_sheet_names(data)
    if not names:
        return '<p class="fp-empty">File không có sheet nào.</p>'
    parts = []
    for name in names:
        try:
            rows = read_sheet_rows(data, name)
        except Exception:
            continue
        parts.append(_table_html(rows, caption=name))
    if not parts:
        return '<p class="fp-empty">Không đọc được nội dung sheet.</p>'
    return ''.join(parts)


# ===== docx =====
_W_P = re.compile(r'<w:p[ >].*?</w:p>|<w:p/>', re.DOTALL)
# ⚠ `<w:t[^>]*>` khớp nhầm CẢ `<w:tc>` (ô bảng) -> lọt markup thô vào text.
# Bắt buộc sau `w:t` là '>' hoặc khoảng trắng (vd `<w:t xml:space="preserve">`).
_W_T = re.compile(r'<w:t(?:\s[^>]*)?>(.*?)</w:t>', re.DOTALL)
_W_TBL = re.compile(r'<w:tbl(?:\s[^>]*)?>.*?</w:tbl>', re.DOTALL)
_W_TR = re.compile(r'<w:tr(?:\s[^>]*)?>.*?</w:tr>', re.DOTALL)
_W_TC = re.compile(r'<w:tc(?:\s[^>]*)?>.*?</w:tc>', re.DOTALL)
_W_STYLE = re.compile(r'w:val="(Heading[1-6]|Title)"')
_XML_ENT = (('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&apos;', "'"), ('&amp;', '&'))


def _xml_text(chunk):
    """Gộp mọi <w:t>/<a:t> trong chunk thành 1 chuỗi (đã giải entity XML)."""
    s = ''.join(_W_T.findall(chunk))
    for a, b in _XML_ENT:
        s = s.replace(a, b)
    return s.strip()


def _docx_html(data):
    with zipfile.ZipFile(BytesIO(data)) as zf:
        try:
            xml = zf.read('word/document.xml').decode('utf-8', errors='replace')
        except KeyError:
            raise RuntimeError('Không phải file .docx hợp lệ (thiếu word/document.xml).')

    blocks, count = [], 0
    # Tách bảng ra trước rồi xử đoạn văn ở phần còn lại, giữ đúng thứ tự xuất hiện.
    pos = 0
    for m in _W_TBL.finditer(xml):
        blocks.extend(_docx_paragraphs(xml[pos:m.start()]))
        rows = []
        for tr in _W_TR.finditer(m.group(0)):
            rows.append([_xml_text(tc.group(0)) for tc in _W_TC.finditer(tr.group(0))])
        if rows:
            blocks.append(_table_html(rows))
        pos = m.end()
    blocks.extend(_docx_paragraphs(xml[pos:]))

    blocks = [b for b in blocks if b]
    if not blocks:
        return '<p class="fp-empty">File không có nội dung văn bản.</p>'
    count = len(blocks)
    out = ''.join(blocks[:MAX_BLOCKS])
    if count > MAX_BLOCKS:
        out = _truncated(out, f'Chỉ hiển thị {MAX_BLOCKS} đoạn đầu — tải file để xem đầy đủ.')
    return f'<div class="fp-doc">{out}</div>'


def _docx_paragraphs(xml_chunk):
    out = []
    for p in _W_P.finditer(xml_chunk):
        raw = p.group(0)
        txt = _xml_text(raw)
        if not txt:
            continue
        st = _W_STYLE.search(raw)
        if st:
            lvl = 2 if st.group(1) == 'Title' else min(int(st.group(1)[-1]) + 1, 6)
            out.append(f'<h{lvl}>{esc(txt)}</h{lvl}>')
        else:
            out.append(f'<p>{esc(txt)}</p>')
    return out


# ===== pptx =====
_A_T = re.compile(r'<a:t>(.*?)</a:t>', re.DOTALL)
_SLIDE_NAME = re.compile(r'^ppt/slides/slide(\d+)\.xml$')


def _pptx_html(data):
    with zipfile.ZipFile(BytesIO(data)) as zf:
        slides = []
        for n in zf.namelist():
            m = _SLIDE_NAME.match(n)
            if m:
                slides.append((int(m.group(1)), n))
        slides.sort()
        if not slides:
            raise RuntimeError('Không phải file .pptx hợp lệ (không thấy slide).')
        parts = []
        for idx, name in slides:
            xml = zf.read(name).decode('utf-8', errors='replace')
            lines = []
            for t in _A_T.findall(xml):
                for a, b in _XML_ENT:
                    t = t.replace(a, b)
                t = t.strip()
                if t:
                    lines.append(t)
            body = ''.join(f'<p>{esc(l)}</p>' for l in lines[:MAX_BLOCKS]) or \
                '<p class="fp-empty">(slide không có text)</p>'
            parts.append(f'<div class="fp-slide"><div class="fp-slide-no">Slide {idx}</div>{body}</div>')
    return ''.join(parts)


# ===== text / csv =====
def _text_html(data, ext):
    txt = data.decode('utf-8', errors='replace')
    cut = len(txt) > MAX_TEXT_CHARS
    txt = txt[:MAX_TEXT_CHARS]
    if ext in ('.csv', '.tsv'):
        sep = '\t' if ext == '.tsv' else ','
        import csv as _csv
        try:
            rows = list(_csv.reader(txt.splitlines(), delimiter=sep))
            return _table_html(rows)
        except Exception:
            pass  # hỏng thì rơi về text thuần
    out = f'<pre class="fp-pre">{esc(txt)}</pre>'
    return _truncated(out, 'Nội dung bị cắt bớt — tải file để xem đầy đủ.') if cut else out


# ===== entry =====
def preview_html(path):
    """Path file trong uploads -> (ok, kind, html_or_msg).

    kind: 'html' (nội dung đã dựng) | 'native' (client tự nhúng) |
          'raw' (client nhúng qua /file-raw, sandbox) | 'unsupported'.
    KHÔNG raise: lỗi parse trả về ok=False + thông báo tiếng Việt cho UI.
    """
    path = Path(path)
    ext = path.suffix.lower()
    if ext in NATIVE_EXTS:
        return True, 'native', ''
    if ext in RAW_EXTS:
        return True, 'raw', ''
    if not path.exists() or not path.is_file():
        return False, 'unsupported', 'Không tìm thấy file.'
    size = path.stat().st_size
    if size > MAX_BYTES:
        return False, 'unsupported', 'File quá lớn để xem trước — tải xuống để mở.'
    try:
        data = path.read_bytes()
        if ext in ('.xlsx', '.xlsm'):
            return True, 'html', _xlsx_html(data)
        if ext == '.docx':
            return True, 'html', _docx_html(data)
        if ext == '.pptx':
            return True, 'html', _pptx_html(data)
        if ext in TEXT_EXTS:
            return True, 'html', _text_html(data, ext)
    except RuntimeError as e:
        return False, 'unsupported', str(e)
    except Exception:
        return False, 'unsupported', 'Không đọc được nội dung file này.'
    return False, 'unsupported', 'Định dạng này chưa xem trước được — tải xuống để mở.'
