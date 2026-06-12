"""Shared low-level render helpers: per-render asset loaders + JSON embedding.

Foundation module imported by the page submodules (shell/misc/dashboard/...).
Assets load per-render so edits hot-reload without restart; output stays self-contained.
"""
import json

from config import ASSETS_DIR


def load_css():
    """Read styles.css per-render (edits hot-reload without restart); inlined into <style>."""
    try:
        return (ASSETS_DIR / 'styles.css').read_text(encoding='utf-8')
    except OSError:
        return ''


def load_css_v2():
    """Read styles_v2.css per-render (shell UI v2 — dashboard QA + roadmap)."""
    try:
        return (ASSETS_DIR / 'styles_v2.css').read_text(encoding='utf-8')
    except OSError:
        return ''


def load_js_v2():
    """Read app_v2.js per-render (shell UI v2)."""
    try:
        return (ASSETS_DIR / 'app_v2.js').read_text(encoding='utf-8')
    except OSError:
        return ''


def _json_script(elem_id, obj):
    """Embed JSON an toàn vào <script type=application/json> (chống đóng tag sớm)."""
    return (f'<script type="application/json" id="{elem_id}">'
            + json.dumps(obj, ensure_ascii=False).replace('</', '<\\/') + '</script>')
