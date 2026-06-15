"""HTML rendering. UI v2 (Stitch) assets live in styles_v2.css / app_v2.js; the legacy
styles.css is still inlined by render_error_page. All assets load per-render (inlined).

All render_* functions return HTML fragments; render_page assembles the full document.

Sau A7 (#110/#86) đây là **package thuần re-export**: mọi định nghĩa đã tách ra
các module con (base/shell/misc/dashboard/docs/roadmap/bug_log/leader_eval). Giữ
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
                         render_error_page, render_shell_error)
# Dashboard v2 (admin team-wide + QA personal lens + render_page dispatcher) tách
# sang render.dashboard; re-export để chỗ gọi không phải đổi import. See issue #106 / #86.
from render.dashboard import (render_page, _bug_metrics_payload,
                              render_admin_v2, render_qa_v2)
# Tài liệu training (tab /docs) tách sang render.docs; re-export để chỗ gọi
# (qa_dashboard.py) không phải đổi import. See issue #107 / #86.
from render.docs import render_docs_page
# Roadmap v2 (tab /roadmap) tách sang render.roadmap; re-export để chỗ gọi
# (qa_dashboard.py) không phải đổi import. See issue #108 / #86.
from render.roadmap import render_roadmap_v2
# Bug Log v2 (tab /bug-log) tách sang render.bug_log; re-export để chỗ gọi
# (qa_dashboard.py) không phải đổi import. See issue #109 / #86.
from render.bug_log import render_bug_log_v2, _bug_log_source_modals
# Đánh giá Task QA cho Leader (tab /leader-eval) tách sang render.leader_eval;
# re-export để chỗ gọi không phải đổi import. See issue #110 / #86 (A7).
from render.leader_eval import render_leader_eval_page

