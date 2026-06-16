"""Nguồn file bug log trên Drive — list {id, label} (issue #52, UI quản lý ở #55).

KHÔNG hardcode file ID vào .env. Lưu danh sách file Drive nguồn vào Jira property
`qa-dashboard-bug-log-source` (sync chéo máy như docs/roadmap) + cache local
`.bug_log_source.json`. Mỗi entry = {"id": <Drive file id>, "label": <tên hiển thị>}.

Layer: config -> jira_api -> (this). Không cycle.
"""
import json
import re

from config import BUG_LOG_SOURCE_FILE, atomic_write
from remote_store import synced_load, synced_save

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
        if not isinstance(it.get('service', ''), str):
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
    atomic_write(BUG_LOG_SOURCE_FILE, json.dumps(data, ensure_ascii=False, indent=2))


def load_sources():
    """Kho chung = Cloudflare KV (sync chéo máy, không cần VPN); local file = fallback offline.
    [] nếu chưa cấu hình."""
    return synced_load(BUG_LOG_SOURCE_PROP, _read_cache, _write_cache, valid_sources, [])


def save_sources(data):
    """Local-first: ghi local trước (luôn OK) rồi đẩy KV best-effort."""
    return synced_save(BUG_LOG_SOURCE_PROP, data, _write_cache, valid_sources)
