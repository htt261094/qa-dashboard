"""UploadsMixin — serve + nhận file upload cho tab Tài liệu (Decision #23).

Tách từ qa_dashboard.py (issue #86 / B3). Zero behavior change: chỉ di chuyển định
nghĩa method, không đổi logic/route/output.

Gom 2 route file:
- `_get_uploads(path)` — serve file trong uploads/ (GET /uploads/<filename>)
- `_post_upload_file` — nhận upload multipart, lưu vào uploads/ (POST /upload-file, admin-only)

Mixin dùng các helper dùng chung định nghĩa ở Handler (resolve qua MRO):
`self._is_admin()`, `self._json()`, `self.send_response()`, `self.send_header()`,
`self.end_headers()`, `self.wfile`, `self.rfile`, `self.headers`.

Thư mục lưu file = `config.UPLOADS_DIR` (mặc định `<root>/uploads`, override bằng
env/.env `UPLOADS_DIR`) — trước hardcode path macOS nên upload chết trên host khác
(issue #37 / Decision #23).

Layer rule: KHÔNG import qa_dashboard (tránh vòng import).
"""
import json

from config import UPLOADS_DIR


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
        disp = 'inline' if ext in ('.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp') else 'attachment'
        try:
            data = file_path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Disposition', f"{disp}; filename*=UTF-8''{quote(filename)}")
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_response(500)
            self.end_headers()

    def _post_upload_file(self):
        if not self._is_admin():
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
            self._json(500, json.dumps({
                "ok": False,
                "msg": f"Loi he thong: {str(e)}"
            }).encode('utf-8'))
