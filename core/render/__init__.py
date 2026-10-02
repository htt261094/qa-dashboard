"""HTML rendering. UI v2 (Stitch) assets live in styles_v2.css / app_v2.js; the legacy
styles.css is still inlined by render_error_page. All assets load per-render (inlined).

All render_* functions return HTML fragments; render_page assembles the full document.

Sau A7 (#110/#86) đây là **package thuần re-export**: mọi định nghĩa đã tách ra
các module con (base/shell/misc/dashboard/docs/bug_log/analytics). Giữ
import lại ở đây để chỗ gọi (qa_dashboard.py, scripts) không phải đổi import.
"""
# Shared low-level helpers extracted to render.base; re-exported so existing callers
# (`from render import load_css, _json_script, ...`) keep working. See issue #103 / #86.
from render.base import load_css, load_css_v2, load_js_v2, _json_script
# Shell chrome (sidebar/topbar/modals/_document_v2) extracted to render.shell;
# re-exported so existing callers keep working. See issue #104 / #86.
from render.shell import (_FONTS_V2, _AV_CLS, _avatar, _conn_error_card,
                          render_sidebar_v2, render_topbar_v2, _settings_modal_v2,
                          _subtask_modal_v2, _document_v2)
# Trang phụ (403/settings/drive card/error) tách sang render.misc; re-export để
# chỗ gọi (qa_dashboard.py) không phải đổi import. See issue #105 / #86.
from render.misc import (render_403, _render_drive_card, render_settings_page,
                         render_error_page, render_shell_error, render_login_page)
# Lens cá nhân "Việc của tôi" (render.dashboard) — dashboard team đã gỡ (Decision #97).
from render.dashboard import render_qa_v2, build_my_work_payload
# Trang chính "Hôm nay" (Decision #102).
from render.today import render_today_v2, build_today_groups
# Tài liệu training (tab /docs) tách sang render.docs; re-export để chỗ gọi
# (qa_dashboard.py) không phải đổi import. See issue #107 / #86.
from render.docs import render_docs_page, render_file_view_page
# Bug Log v2 (tab /bug-log) tách sang render.bug_log; re-export để chỗ gọi
# (qa_dashboard.py) không phải đổi import. See issue #109 / #86.
from render.bug_log import (render_bug_log_v2, _bug_log_source_modals,
                            build_bug_log_payload)
# Analytics v2 (tab /analytics) — gom metric bug + Valid Bug Rate. See issue #158.
from render.analytics import render_analytics_v2
