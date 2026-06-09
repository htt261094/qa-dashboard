"""Nguồn file bug log trên Drive — list {id, label} (issue #52, UI quản lý ở #55).

KHÔNG hardcode file ID vào .env. Lưu danh sách file Drive nguồn vào Jira property
`qa-dashboard-bug-log-source` (sync chéo máy như docs/roadmap) + cache local
`.bug_log_source.json`. Mỗi entry = {"id": <Drive file id>, "label": <tên hiển thị>}.

Layer: config -> jira_api -> (this). Không cycle.
"""
import json
import re

from config import BUG_LOG_SOURCE_FILE
from jira_api import load_property, save_property

BUG_LOG_SOURCE_PROP = 'qa-dashboard-bug-log-source'

MAX_SOURCES = 50
# Drive file id: ký tự alnum + - _ , độ dài hợp lý. Cũng nhận link Drive -> rút id.
_ID_RE = re.compile(r'^[A-Za-z0-9_-]{10,200}$')
_LINK_ID_RE = re.compile(r'/d/([A-Za-z0-9_-]{10,200})')


def extract_file_id(s):
    """Rút Drive file id từ chuỗi: nhận id trần hoặc link /file/d/<id>/... hoặc ?id=<id>."""
    s = (s or '').strip()
    if not s:
        return ''
    m = _LINK_ID_RE.search(s)
    if m:
        return m.group(1)
    m = re.search(r'[?&]id=([A-Za-z0-9_-]{10,200})', s)
    if m:
        return m.group(1)
    return s if _ID_RE.match(s) else ''


def valid_sources(data):
    """list[{id: str hợp lệ, label: str}] và <= MAX_SOURCES."""
    if not isinstance(data, list) or len(data) > MAX_SOURCES:
        return False
    for it in data:
        if not isinstance(it, dict):
            return False
        if not isinstance(it.get('id'), str) or not _ID_RE.match(it['id']):
            return False
        if not isinstance(it.get('label', ''), str):
            return False
    return True


def _read_cache():
    if BUG_LOG_SOURCE_FILE.exists():
        try:
            data = json.loads(BUG_LOG_SOURCE_FILE.read_text(encoding='utf-8'))
            if valid_sources(data):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(data):
    try:
        BUG_LOG_SOURCE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                       encoding='utf-8')
    except OSError:
        pass


def load_sources():
    """Source of truth = Jira property; local file = cache fallback. [] nếu chưa cấu hình."""
    try:
        data = load_property(BUG_LOG_SOURCE_PROP)
        if data is not None and valid_sources(data):
            _write_cache(data)
            return data
    except RuntimeError:
        pass
    cached = _read_cache()
    return cached if cached is not None else []


def save_sources(data):
    """Ghi Jira property (primary) + cache local. Chỉ True khi Jira nhận."""
    if not valid_sources(data):
        return False
    try:
        save_property(BUG_LOG_SOURCE_PROP, data)
    except RuntimeError:
        return False
    _write_cache(data)
    return True
