"""Nguồn Bug Log = JQL Jira "Bug Testing" (Decision #104; trước là file Drive #52).

Lưu danh sách nguồn vào Cloudflare KV `qa-dashboard-bug-log-source` (sync chéo máy) + cache
local `.bug_log_source.json`. Mỗi entry = {"id", "label", "provider":"jira", "query": <JQL>}.
Mặc định (chưa cấu hình) = 1 nguồn Jira toàn bộ Bug Testing (xem load_sources).

Layer: config -> remote_store -> (this). Không cycle.
"""
import json

from config import BUG_LOG_SOURCE_FILE, atomic_write
from remote_store import synced_load, synced_save

BUG_LOG_SOURCE_PROP = 'qa-dashboard-bug-log-source'

MAX_SOURCES = 50


def valid_sources(data):
    """list[{id, label, service?, provider?, query}] và <= MAX_SOURCES. Nguồn Jira (#104):
    `id` = chuỗi non-empty <=500, `query` = JQL <=2000. Entry Drive cũ (nếu còn trong cache) bị
    coi là KHÔNG hợp lệ -> load bỏ qua, dùng default Jira."""
    if not isinstance(data, list) or len(data) > MAX_SOURCES:
        return False
    for it in data:
        if not isinstance(it, dict):
            return False
        if (it.get('provider') or 'jira') != 'jira':
            return False
        if not isinstance(it.get('label', ''), str) or not isinstance(it.get('service', ''), str):
            return False
        if not isinstance(it.get('id'), str) or not (0 < len(it['id']) <= 500):
            return False
        q = it.get('query', '')
        if not isinstance(q, str) or len(q) > 2000:
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
    return atomic_write(BUG_LOG_SOURCE_FILE, json.dumps(data, ensure_ascii=False, indent=2))


def _default_jira_source():
    """Nguồn Bug Log mặc định sau cut-over Drive->Jira (#104): toàn bộ issue type Bug Testing.
    Chia theo squad (= project.key) ở tầng hiển thị, chưa lọc project ở JQL."""
    from config import BUG_TESTING_JQL
    return [{'provider': 'jira', 'id': 'bug-testing', 'label': 'Bug Testing',
             'service': '', 'query': BUG_TESTING_JQL}]


def load_sources():
    """Kho chung = Cloudflare KV (sync chéo máy, không cần VPN); local file = fallback offline.
    Chưa cấu hình gì -> mặc định 1 nguồn Jira Bug Testing (#104), KHÔNG còn rỗng/Drive."""
    srcs = synced_load(BUG_LOG_SOURCE_PROP, _read_cache, _write_cache, valid_sources, [])
    return srcs or _default_jira_source()


def save_sources(data):
    """Local-first: ghi local trước (luôn OK) rồi đẩy KV best-effort."""
    return synced_save(BUG_LOG_SOURCE_PROP, data, _write_cache, valid_sources)
