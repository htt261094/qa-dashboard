"""Ghi chú RIÊNG theo task (Decision #101) — checklist cá nhân, lý do đang chờ, link Chat…

Lớp phủ local giống custom status (#21): KHÔNG ghi gì lên Jira, chỉ chính chủ thấy. Kho =
Cloudflare KV `qa-dashboard-task-notes` (local-first, #78) + cache `.task_notes.json`:
  { "notes": { "DA52H26-1252": {"t": "<text>", "at": iso}, ... } }

Lưu theo key THẬT (đúng quy ước #76: canon_key chỉ để so khớp), tra theo canon -> ghi chú
không trượt khi Jira đổi project key sang kỳ nửa năm mới.

Layer: config -> remote_store -> (this). Không cycle.
"""
import json
import threading
from datetime import datetime

from config import SCRIPT_DIR, atomic_write, canon_key
from remote_store import synced_load, synced_save

NOTES_KEY = 'qa-dashboard-task-notes'
CACHE_FILE = SCRIPT_DIR / '.task_notes.json'
MAX_LEN = 5000        # ký tự / ghi chú
MAX_NOTES = 2000      # số task có ghi chú (chống phình KV value)

_lock = threading.Lock()   # autosave gõ liên tục -> nhiều POST chồng nhau, tránh mất chữ


def _read_cache():
    if CACHE_FILE.exists():
        try:
            d = json.loads(CACHE_FILE.read_text(encoding='utf-8'))
            if isinstance(d, dict):
                return d
        except (json.JSONDecodeError, OSError):
            pass
    return None


def _write_cache(data):
    return atomic_write(CACHE_FILE, json.dumps(data, ensure_ascii=False, indent=2))


def _valid(d):
    return isinstance(d, dict) and isinstance(d.get('notes'), dict)


def _load():
    return synced_load(NOTES_KEY, _read_cache, _write_cache, _valid, {'notes': {}})


def load_notes():
    """{KEY: {'t', 'at'}} mọi ghi chú hiện có."""
    return _load().get('notes', {})


def index_by_canon(notes=None):
    """{canon_key: entry} — tra ghi chú cho task live bất kể kỳ của project key."""
    notes = load_notes() if notes is None else notes
    return {canon_key(k): v for k, v in notes.items()}


def note_for(key, notes=None):
    """Entry ghi chú của task `key` (khớp theo canon) hoặc None."""
    if not key:
        return None
    return index_by_canon(notes).get(canon_key(key))


def set_note(key, text):
    """Ghi/xoá ghi chú của `key`. text rỗng (sau strip) -> xoá. Trả entry mới ({} khi xoá),
    None nếu input không hợp lệ hoặc đã chạm trần MAX_NOTES."""
    if not key or not isinstance(text, str):
        return None
    text = text.replace('\r\n', '\n')[:MAX_LEN]
    with _lock:
        data = _load()
        notes = data.setdefault('notes', {})
        ck = canon_key(key)
        # Bỏ entry cũ cùng canon (key kỳ trước) -> mỗi task chỉ 1 ghi chú, lưu theo key mới nhất.
        for k in [k for k in notes if canon_key(k) == ck]:
            notes.pop(k, None)
        if not text.strip():
            synced_save(NOTES_KEY, data, _write_cache, _valid)
            return {}
        if len(notes) >= MAX_NOTES:
            return None
        entry = {'t': text, 'at': datetime.now().isoformat(timespec='seconds')}
        notes[key] = entry
        synced_save(NOTES_KEY, data, _write_cache, _valid)
        return entry
