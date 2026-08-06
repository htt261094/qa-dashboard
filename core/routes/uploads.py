"""UploadsMixin — serve + nhận file upload cho tab Tài liệu (Decision #23).

Tách từ qa_dashboard.py (issue #86 / B3). Zero behavior change: chỉ di chuyển định
nghĩa method, không đổi logic/route/output.

Gom các route file:
- `_get_uploads(path)` — serve file trong uploads/ (GET /uploads/<filename>)
- `_post_upload_file` — nhận upload multipart, lưu vào uploads/ (POST /upload-file, mọi QA authed)
- `_get_file_preview` — JSON nội dung dựng sẵn để xem trước trong app (GET /file-preview)

Mixin dùng các helper dùng chung định nghĩa ở Handler (resolve qua MRO):
`self._is_admin()`, `self._json()`, `self.send_response()`, `self.send_header()`,
`self.end_headers()`, `self.wfile`, `self.rfile`, `self.headers`.

Thư mục lưu file = `config.UPLOADS_DIR` (mặc định `<root>/uploads`, override bằng
env/.env `UPLOADS_DIR`) — trước hardcode path macOS nên upload chết trên host khác
(issue #37 / Decision #23).

Layer rule: KHÔNG import qa_dashboard (tránh vòng import).
"""
import json
import sys

from config import UPLOADS_DIR

# Allowlist đuôi file cho phép upload (issue #47). = hợp của MỌI loại app thật sự
# xử lý: tài liệu Office, ảnh, text, HTML (xem file_preview.*_EXTS + _get_uploads).
# Chặn phần còn lại (.exe/.sh/.php/... ) ngay tại cổng nhận — lớp phòng thủ trước
# cả nosniff/attachment ở khâu serve. So sánh bằng đuôi đã lower().
ALLOWED_UPLOAD_EXTS = {
    # tài liệu
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.xlsm', '.ppt', '.pptx',
    # ảnh
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp',
    # text / dữ liệu
    '.txt', '.md', '.markdown', '.csv', '.tsv', '.json', '.log',
    '.yml', '.yaml', '.xml', '.ini', '.cfg', '.sql',
    # trang HTML (xem qua /file-raw sandbox — Decision #65)
    '.html', '.htm',
}

# Chèn khi `/file-raw?fit=1` (tab "Quy Trình"): file nằm trong origin mờ nên parent KHÔNG
# đọc được scrollHeight -> file tự báo chiều cao lên parent qua postMessage để iframe cao
# bằng nội dung (xem hết trong 1 trang, không cuộn trong khung). Chỉ gửi 1 con số.
_FIT_SNIPPET = """
<script>(function(){
  // Đo ĐÁY NỘI DUNG THẬT, KHÔNG dùng documentElement.scrollHeight: khi iframe đã cao
  // hơn nội dung thì trị số đó = chiều cao KHUNG -> parent set cao thêm -> resize ->
  // báo cao hơn nữa -> phình vô hạn (ratchet). Đáy các con của body không phụ thuộc
  // chiều cao viewport nên vòng lặp tự dừng.
  function h(){
    var d=document.documentElement, b=document.body; if(!b) return 0;
    // Ẩn scrollbar TRONG LÚC ĐO: khi khung còn thấp, nội dung tràn -> có scrollbar dọc ->
    // bề rộng hẹp hơn ~15px -> phần tử scale theo bề rộng (SVG/ảnh) cho số đo thiếu so với
    // trạng thái cuối (không scrollbar). Đo xong trả lại nguyên trạng.
    var prev=d.style.overflowY;
    d.style.overflowY='hidden';
    var sy=window.pageYOffset||0, bottom=0, kids=b.children, i, r;
    for(i=0;i<kids.length;i++){
      r=kids[i].getBoundingClientRect();
      if(r.height||r.width) bottom=Math.max(bottom, r.bottom+sy);
    }
    var cs=getComputedStyle(b);
    var pad=(parseFloat(cs.paddingBottom)||0)+(parseFloat(cs.marginBottom)||0);
    var sh=b.scrollHeight;
    d.style.overflowY=prev;
    if(!bottom) return sh;                           // body rỗng/chỉ có text node
    return Math.ceil(bottom+pad);
  }
  var last=0;
  function send(){
    var v=h();
    if(!v||Math.abs(v-last)<2) return;
    last=v;
    try{ parent.postMessage({__fitHeight:v},'*'); }catch(e){}
  }
  addEventListener('load',send); addEventListener('resize',send);
  if(window.ResizeObserver&&document.body) new ResizeObserver(send).observe(document.body);
  send(); setTimeout(send,120); setTimeout(send,600); setTimeout(send,1600);
  // Chốt an toàn: ResizeObserver/resize có thể KHÔNG được giao (tab ẩn, rAF bị hãm) ->
  // nội dung đổi chiều cao mà khung không đổi theo (thừa/thiếu chỗ trống). Nhịp rẻ, tự
  // dừng khi tab ẩn; `send` chỉ postMessage khi số đo thực sự khác.
  setInterval(function(){ if(!document.hidden) send(); },1500);
  addEventListener('visibilitychange',function(){ if(!document.hidden) send(); });
})();</script>
""".encode('utf-8')


class UploadsMixin:
    def _get_uploads(self, path):
        import os
        from urllib.parse import quote, unquote
        filename = os.path.basename(unquote(path))
        file_path = UPLOADS_DIR / filename
        if not file_path.exists() or not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            return
        ext = file_path.suffix.lower()
        content_type = 'application/octet-stream'
        if ext == '.pdf':
            content_type = 'application/pdf'
        elif ext in ('.xlsx', '.xls'):
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif ext in ('.docx', '.doc'):
            content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp'):
            content_type = f'image/{ext[1:] if ext != ".jpg" else "jpeg"}'
        # CHỈ inline cho pdf + ảnh raster (an toàn). Mọi loại khác (svg, html, text,
        # octet-stream) ép `attachment` -> browser tải về, KHÔNG render trong origin app
        # => không thành XSS. svg CỐ Ý không inline (SVG nhúng được <script>).
        disp = 'inline' if ext in ('.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp') else 'attachment'
        try:
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            # Chặn browser sniff kiểu nội dung (vd đoán octet-stream thành HTML) — issue #47
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Disposition', f"{disp}; filename*=UTF-8''{quote(filename)}")
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _get_file_preview(self):
        """GET /file-preview?f=<filename> -> {ok, kind, html, msg}.

        Chỉ đọc file NẰM TRONG UPLOADS_DIR (basename + resolve check, chống traversal).
        Dùng cho định dạng browser không tự render (docx/xlsx/pptx/text) — PDF/ảnh thì
        client nhúng thẳng /uploads/... nên không gọi vào đây.
        """
        import os
        from urllib.parse import urlparse, parse_qs, unquote

        q = parse_qs(urlparse(self.path).query)
        name = os.path.basename(unquote((q.get('f') or [''])[0]))
        if not name:
            self._json(400, b'{"ok":false,"msg":"thieu ten file"}')
            return
        target = (UPLOADS_DIR / name).resolve()
        try:
            inside = target.parent == UPLOADS_DIR.resolve()
        except OSError:
            inside = False
        if not inside:
            self._json(400, b'{"ok":false,"msg":"duong dan khong hop le"}')
            return
        from file_preview import preview_html
        ok, kind, html = preview_html(target)
        self._json(200, json.dumps({
            'ok': ok, 'kind': kind,
            'html': html if ok else '', 'msg': '' if ok else html,
        }, ensure_ascii=False).encode('utf-8'))

    def _get_file_raw(self):
        """GET /file-raw?f=<filename> -> nội dung HTML THÔ để nhúng iframe (Decision #65).

        Chỉ nhận `.html/.htm`. `/uploads/...` cố ý serve HTML dạng
        `application/octet-stream; attachment` (không render) nên phải có route riêng
        này để xem trước ngay trong app.

        Cách ly bằng `Content-Security-Policy: sandbox` — browser đặt file vào
        **origin mờ (opaque)**: script trong file KHÔNG đọc được cookie/session/DOM của
        app, request về app tính là cross-origin (cookie SameSite=Lax không gửi kèm).
        Vẫn cho `allow-scripts` để report HTML có chart/JS xem được. Client còn bọc
        thêm thuộc tính `sandbox` trên iframe (phòng thủ 2 lớp).
        """
        import os
        from urllib.parse import urlparse, parse_qs, unquote, quote

        q = parse_qs(urlparse(self.path).query)
        name = os.path.basename(unquote((q.get('f') or [''])[0]))
        ext = os.path.splitext(name)[1].lower()
        if not name or ext not in ('.html', '.htm'):
            self.send_response(400)
            self.end_headers()
            return
        target = (UPLOADS_DIR / name).resolve()
        try:
            inside = target.parent == UPLOADS_DIR.resolve()
        except OSError:
            inside = False
        if not inside or not target.exists() or not target.is_file():
            self.send_response(404)
            self.end_headers()
            return
        try:
            from file_preview import MAX_BYTES
            if target.stat().st_size > MAX_BYTES:
                self.send_response(413)
                self.end_headers()
                return
            data = target.read_bytes()
            if (q.get('fit') or [''])[0] == '1':
                data += _FIT_SNIPPET
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Security-Policy',
                             'sandbox allow-scripts allow-popups allow-forms allow-modals')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Disposition',
                             f"inline; filename*=UTF-8''{quote(name)}")
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _post_upload_file(self):
        # Mở cho MỌI QA authed (khớp editable=True ở /docs). Dev bị chặn tự nhiên:
        # /upload-file không trong _DEV_POST_ALLOWED.
        if not self._authed():
            self._json(403, b'{"ok":false,"err":"forbidden"}')
            return
        try:
            import os
            import time
            import re
            from pathlib import Path

            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 25_000_000: # 25MB safety cap (limit is 20MB)
                self._json(400, b'{"ok":false,"msg":"File qua lon (> 20MB)"}')
                return

            body = self.rfile.read(content_length)

            # Parse multipart boundary
            ctype = self.headers.get('Content-Type', '')
            if 'boundary=' not in ctype:
                self._json(400, b'{"ok":false,"msg":"Thieu multipart boundary"}')
                return

            boundary = ctype.split('boundary=')[1].strip()
            boundary_bytes = ('--' + boundary).encode('utf-8')

            # Custom parse multipart
            parts = body.split(boundary_bytes)
            filename = None
            file_data = None
            for part in parts:
                if not part or part == b'--\r\n' or part == b'--':
                    continue
                idx = part.find(b'\r\n\r\n')
                header_end = idx + 4
                if idx == -1:
                    idx = part.find(b'\n\n')
                    header_end = idx + 2
                if idx == -1:
                    continue

                header_part = part[:idx].decode('utf-8', errors='ignore')
                m = re.search(r'filename="([^"]+)"', header_part)
                if m:
                    filename = m.group(1)
                    file_data = part[header_end:]
                    if file_data.endswith(b'\r\n'):
                        file_data = file_data[:-2]
                    elif file_data.endswith(b'\n'):
                        file_data = file_data[:-1]
                    break

            if not filename or file_data is None:
                self._json(400, b'{"ok":false,"msg":"Khong tim thay file trong request"}')
                return

            # Clean filename (prevent directory traversal). basename() không đủ trên
            # Windows nếu tên có ':' (ADS) hoặc separator lạ -> lọc thêm ký tự cấm.
            filename = os.path.basename(filename.replace('\\', '/').split('/')[-1])
            filename = re.sub(r'[<>:"|?*\x00-\x1f]', '_', filename).strip(' .')
            if not filename:
                self._json(400, b'{"ok":false,"msg":"Ten file khong hop le"}')
                return

            # Allowlist đuôi file (issue #47) — từ chối loại không hỗ trợ.
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_UPLOAD_EXTS:
                self._json(400, json.dumps({
                    "ok": False,
                    "msg": "Loai file khong duoc phep. Chi nhan tai lieu Office, anh, "
                           "text va HTML.",
                }).encode('utf-8'))
                return

            # Target path setup
            uploads_dir = UPLOADS_DIR
            uploads_dir.mkdir(parents=True, exist_ok=True)

            # Check collision, append timestamp if duplicate
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            target_path = uploads_dir / filename
            if target_path.exists():
                timestamp = int(time.time())
                filename = f"{stem}_{timestamp}{suffix}"
                target_path = uploads_dir / filename

            # Write file
            target_path.write_bytes(file_data)

            # Return success JSON
            from urllib.parse import quote
            self._json(200, json.dumps({
                "ok": True,
                "filename": filename,
                # quote để link sống được với tên có dấu/khoảng trắng; _get_uploads unquote lại
                "url": f"/uploads/{quote(filename)}"
            }, ensure_ascii=False).encode('utf-8'))

        except Exception as e:
            # KHÔNG trả str(e) cho client (lộ path/lỗi nội bộ) — issue #47.
            # Log chi tiết ra stderr để debug, client chỉ nhận message chung.
            print(f"[upload-file] error: {e!r}", file=sys.stderr)
            self._json(500, b'{"ok":false,"msg":"Loi he thong khi luu file."}')
