"""Tài liệu training: cây thư mục + link tới Google Drive. Load/save .docs_config.json.

Cây = list các node. Mỗi node là:
  - folder: {"type": "folder", "name": str, "children": [ ...node... ]}
  - link:   {"type": "link",   "title": str, "url": str}
Edit thật diễn ra ở Google (click link mở tab mới); workspace chỉ giữ đường dẫn + tổ chức.
"""
import json

from config import DOCS_FILE
from remote_store import synced_load, synced_save

DOCS_PROP = 'qa-dashboard-docs'  # Jira user property = kho sync chéo máy

MAX_NODES = 2000  # chặn payload quá lớn / cây lồng vô hạn

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
        return isinstance(name_or_title, str) and isinstance(node.get('url', ''), str)
    if t == 'folder':
        children = node.get('children')
        return (isinstance(node.get('name', ''), str) and isinstance(children, list)
                and all(_valid_node(c, budget) for c in children))
    return False


def valid_tree(data):
    """Validate shape trước khi lưu (chống payload rác / quá sâu)."""
    return isinstance(data, list) and all(_valid_node(n, [MAX_NODES]) for n in data)


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
    try:
        DOCS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        pass


def load_docs():
    """Kho chung = Cloudflare KV (sync chéo máy, không cần VPN); file local = fallback offline.
    Xem remote_store."""
    return synced_load(DOCS_PROP, _read_cache, _write_cache, valid_tree, DOCS_DEFAULT)


def save_docs(data):
    """Local-first: ghi local trước (luôn OK) rồi đẩy KV best-effort. True nếu data đã an toàn
    ở local (kể cả khi KV/VPN down)."""
    return synced_save(DOCS_PROP, data, _write_cache, valid_tree)
