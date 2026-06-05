"""Tài liệu training: cây thư mục + link tới Google Drive. Load/save .docs_config.json.

Cây = list các node. Mỗi node là:
  - folder: {"type": "folder", "name": str, "children": [ ...node... ]}
  - link:   {"type": "link",   "title": str, "url": str}
Edit thật diễn ra ở Google (click link mở tab mới); workspace chỉ giữ đường dẫn + tổ chức.
"""
import json

from config import DOCS_FILE

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
        return isinstance(node.get('title', ''), str) and isinstance(node.get('url', ''), str)
    if t == 'folder':
        children = node.get('children')
        return (isinstance(node.get('name', ''), str) and isinstance(children, list)
                and all(_valid_node(c, budget) for c in children))
    return False


def valid_tree(data):
    """Validate shape trước khi lưu (chống payload rác / quá sâu)."""
    return isinstance(data, list) and all(_valid_node(n, [MAX_NODES]) for n in data)


def load_docs():
    if DOCS_FILE.exists():
        try:
            data = json.loads(DOCS_FILE.read_text(encoding='utf-8'))
            if valid_tree(data):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return DOCS_DEFAULT


def save_docs(data):
    if not valid_tree(data):
        return False
    try:
        DOCS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return True
    except OSError:
        return False
