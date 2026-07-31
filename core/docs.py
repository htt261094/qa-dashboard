"""Tài liệu training: cây thư mục + link tới Google Drive. Load/save .docs_config.json.

Cây = list các node. Mỗi node là:
  - folder: {"type": "folder", "name": str, "children": [ ...node... ]}
  - link:   {"type": "link",   "title": str, "url": str}
Edit thật diễn ra ở Google (click link mở tab mới); workspace chỉ giữ đường dẫn + tổ chức.
"""
import json
import re

from config import DOCS_FILE, UPLOADS_DIR, atomic_write
from remote_store import synced_load, synced_save

DOCS_PROP = 'qa-dashboard-docs'  # Jira user property = kho sync chéo máy

# ===== Folder "Quy Trình" — chế độ TAB, chỉ nhận file HTML (Decision #66) =====
# Folder mang `kind: 'process'` được render khác hẳn: không phải bảng tài liệu mà là
# thanh tab, mỗi file HTML = 1 tab xem nội dung ngay trong app (iframe /file-raw).
PROCESS_KIND = 'process'
PROCESS_FOLDER_NAME = 'Quy Trình'

# Seed lần đầu: chỉ thêm node nếu file thật đã có trong uploads/ (tránh tab chết)
_PROCESS_SEED = [
    ('Quy trình Automation với AI', 'quy-trinh-automation-ai-flow.html'),
    ('Workflow Git cho QA', 'git-workflow-qa.html'),
]

MAX_NODES = 2000  # chặn payload quá lớn / cây lồng vô hạn

# Chỉ cho http(s) hoặc file đã upload local; chặn javascript:/data: (stored XSS — issue #46)
_URL_OK = re.compile(r'^(https?://|/uploads/)', re.IGNORECASE)


def _url_ok(url):
    return url == '' or bool(_URL_OK.match(url))

DOCS_DEFAULT = [
    {'type': 'folder', 'name': 'Training QA', 'children': [
        {'type': 'folder', 'name': 'Onboarding', 'children': []},
        {'type': 'link', 'title': 'Ví dụ: Quy trình test (Google Doc)', 'url': 'https://docs.google.com/'},
    ]},
    {'type': 'folder', 'name': 'Template test case', 'children': []},
]


def _valid_node(node, budget):
    budget[0] -= 1
    if budget[0] < 0 or not isinstance(node, dict):
        return False
    t = node.get('type')
    if t == 'link':
        name_or_title = node.get('name') if 'name' in node else node.get('title')
        url = node.get('url', '')
        return (isinstance(name_or_title, str) and isinstance(url, str)
                and _url_ok(url))
    if t == 'folder':
        children = node.get('children')
        return (isinstance(node.get('name', ''), str) and isinstance(children, list)
                and all(_valid_node(c, budget) for c in children))
    return False


def valid_tree(data):
    """Validate shape trước khi lưu (chống payload rác / quá sâu)."""
    return isinstance(data, list) and all(_valid_node(n, [MAX_NODES]) for n in data)


def _has_process_folder(tree):
    return any(isinstance(n, dict) and n.get('type') == 'folder'
               and (n.get('kind') == PROCESS_KIND or n.get('name') == PROCESS_FOLDER_NAME)
               for n in tree)


def ensure_process_folder(tree):
    """Đảm bảo cây có folder "Quy Trình" (kind=process) ở gốc. Trả (tree, changed).

    Folder đã tồn tại theo TÊN (tạo tay từ UI trước đó) thì chỉ gắn thêm `kind` —
    không tạo folder trùng tên, không đụng children.
    """
    if not isinstance(tree, list):
        return tree, False
    changed = False
    for n in tree:
        if (isinstance(n, dict) and n.get('type') == 'folder'
                and n.get('name') == PROCESS_FOLDER_NAME and n.get('kind') != PROCESS_KIND):
            n['kind'] = PROCESS_KIND
            changed = True
    if _has_process_folder(tree):
        return tree, changed

    children = []
    for title, fname in _PROCESS_SEED:
        try:
            exists = (UPLOADS_DIR / fname).exists()
        except OSError:
            exists = False
        if exists:
            children.append({'id': 'd_proc_' + fname.replace('.', '_'), 'type': 'link',
                             'name': title, 'ts': None, 'url': '/uploads/' + fname})
    tree.append({'id': 'f_proc', 'type': 'folder', 'name': PROCESS_FOLDER_NAME,
                 'kind': PROCESS_KIND, 'color': 'purple', 'children': children})
    return tree, True


def _read_cache():
    if DOCS_FILE.exists():
        try:
            data = json.loads(DOCS_FILE.read_text(encoding='utf-8'))
            if valid_tree(data):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(data):
    return atomic_write(DOCS_FILE, json.dumps(data, ensure_ascii=False, indent=2))


def load_docs():
    """Kho chung = Cloudflare KV (sync chéo máy, không cần VPN); file local = fallback offline.
    Xem remote_store."""
    return synced_load(DOCS_PROP, _read_cache, _write_cache, valid_tree, DOCS_DEFAULT)


def save_docs(data):
    """Local-first: ghi local trước (luôn OK) rồi đẩy KV best-effort. True nếu data đã an toàn
    ở local (kể cả khi KV/VPN down)."""
    return synced_save(DOCS_PROP, data, _write_cache, valid_tree)
