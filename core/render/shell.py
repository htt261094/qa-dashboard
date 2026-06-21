"""UI v2 (Stitch) shell — sidebar / topbar / modals / `_document_v2`.

Shared chrome wrapping every v2 page (dashboard QA, my-work, roadmap, docs,
bug-log, leader-eval, settings). Page submodules call `_document_v2` to assemble
the full document. Assets inline per-render via render.base. See issue #104 / #86.
"""
import json
from datetime import datetime

from config import JIRA_URL, USERS, CHAT_ENABLED, display_name, username_from_email
from issues import esc

from render.base import load_css_v2, load_js_v2, _json_script


# ===== UI v2 (Stitch) — shell sidebar dùng cho dashboard QA + roadmap
# ===================================================================
_FONTS_V2 = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
    '&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'
    '<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:'
    'opsz,wght,FILL,GRAD@20,400,0,0" rel="stylesheet">'
)
_AV_CLS = ['av-a', 'av-b', 'av-c', 'av-d', 'av-e', 'av-f']


def _avatar(username, name):
    """(init, cls) cho avatar tròn: chữ cái đầu + màu theo index người trong USERS (ổn định)."""
    init = (name or username or '?').strip()[:1].upper() or '?'
    if username in USERS:
        cls = _AV_CLS[USERS.index(username) % len(_AV_CLS)]
    else:
        seed = sum(ord(c) for c in (username or name or 'x'))
        cls = _AV_CLS[seed % len(_AV_CLS)]
    return init, cls


def _conn_error_card(msg='Không thể kết nối tới Jira. Vui lòng thử lại.'):
    """Card lỗi kết nối Jira — dùng inline thay cho vùng nội dung cần Jira (giữ
    skeleton + các block KHÔNG cần Jira xung quanh). Xem render_shell_error (cả
    trang) và render_admin_v2(jira_error=True) (chỉ vùng task, giữ bug-metric)."""
    return ('<div class="conn-error">'
            '<span class="material-symbols-rounded ce-ic">cloud_off</span>'
            f'<div class="ce-msg">{esc(msg)}</div>'
            '<button type="button" class="ce-retry" onclick="location.reload()">'
            '<span class="material-symbols-rounded mi-sm">refresh</span> Thử lại</button>'
            '</div>')


def render_sidebar_v2(active, user):
    is_admin = user[1] if (user and len(user) > 1) else True
    email = user[0] if (user and user[0]) else ''

    def lnk(href, key, icon, label):
        cls = ' class="active"' if key == active else ''
        fill = " style=\"font-variation-settings:'FILL' 1\"" if key == active else ''
        return (f'<a{cls} href="{href}"><span class="material-symbols-rounded"{fill}>{icon}</span> {label}</a>')

    nav = lnk('/', 'dashboard', 'space_dashboard', 'Dashboard')
    if is_admin:
        nav += lnk('/my-work', 'mywork', 'person', 'Việc của tôi')
        nav += lnk('/leader-eval', 'leadereval', 'star', 'Đánh giá')
    nav += lnk('/roadmap', 'roadmap', 'map', 'Roadmap')
    nav += lnk('/bug-log', 'buglog', 'bug_report', 'Bugs')
    nav += lnk('/test-cases', 'testcases', 'checklist', 'Test Case')
    nav += lnk('/analytics', 'analytics', 'monitoring', 'Analytics')
    nav += lnk('/docs', 'docs', 'description', 'Tài liệu')

    uname = username_from_email(email) if (email and '@' in email) else None
    short = display_name(uname) if uname else (email.split('@')[0] if '@' in email else 'Local')
    init = (short[:2] or 'ME').upper()
    role = ('<span class="role-chip admin">Admin</span>' if is_admin
            else '<span class="role-chip">Chỉ xem</span>')
    sub = esc(email) if email else 'Local dev'
    logout = ('<div class="sep"></div>'
              '<a class="danger" href="/logout"><span class="material-symbols-rounded mi-sm">logout</span> Đăng xuất</a>'
              ) if email else ''
    return (
        '<aside class="sidebar">'
        '<div class="brand"><h1>QA Workspace</h1></div>'
        f'<nav class="nav">{nav}</nav>'
        '<div class="nav-foot">'
        '<div class="pmenu" id="pmenu">'
        '<button type="button" id="pmSettings"><span class="material-symbols-rounded mi-sm">settings</span> Setting</button>'
        f'{logout}</div>'
        '<button class="profile" id="profileBtn">'
        f'<span class="av">{esc(init)}</span>'
        f'<span class="who"><b>{esc(short)} {role}</b><small>{sub}</small></span>'
        '<span class="material-symbols-rounded mi-sm">unfold_more</span>'
        '</button></div></aside>'
    )


def render_topbar_v2():
    return (
        '<div class="topbar">'
        '<div class="search"><span class="si material-symbols-rounded mi-sm">search</span>'
        '<input type="text" id="searchInp" placeholder="Tìm task, kế hoạch..."></div>'
        '<div class="top-right">'
        '<button class="topcreate" id="createSubBtn" title="Tạo sub-task QA dưới 1 Task-PTSP">'
        '<span class="material-symbols-rounded mi-sm">add</span> Tạo Sub-task</button>'
        '<button class="iconbtn" id="bellBtn" title="Thông báo">'
        '<span class="material-symbols-rounded mi-lg">notifications</span>'
        '<span class="badge-dot" id="bellDot" style="display:none">0</span></button>'
        '<button class="iconbtn" id="themeBtn" title="Đổi giao diện">'
        '<span class="material-symbols-rounded" id="themeIc">dark_mode</span></button>'
        '</div>'
        '<div class="notif" id="notif">'
        '<div class="notif-head"><h4>Thông báo</h4>'
        '<a class="notif-readall" id="notifReadAll">Đánh dấu tất cả đã đọc</a></div>'
        '<div class="notif-filters">'
        '<button class="nf-tab active" data-nf="all">Tất cả</button>'
        '<button class="nf-tab" data-nf="unread">Chưa đọc</button></div>'
        '<div class="notif-list" id="notifList"></div></div>'
        '</div>'
    )


def _settings_modal_v2(user=None):
    # Drive connection = admin-only (chỉ admin lấy refresh_token đọc bug log). Non-admin
    # chỉ thấy phần PAT. Trạng thái kết nối load lười qua /has-drive (tránh +1 Jira call
    # mỗi lần render shell). IDs prefix `setDrive*` để KHÔNG đụng id nào khác.
    is_admin = bool(user and len(user) > 1 and user[1])
    drive = ''
    if is_admin:
        drive = (
            '<div class="set-drive" id="setDriveSect">'
            '<label class="set-drive-lbl"><span class="material-symbols-rounded mi-sm">cloud</span> '
            'Kết nối Google Drive (Bug Log)</label>'
            '<p class="modal-note">Cấp quyền <b>chỉ đọc</b> để background sync đọc file <code>.xlsx</code> bug log. '
            'Khi Google hỏi, chọn tài khoản <b>@baokim.vn</b>. Token được mã hoá khi lưu.</p>'
            '<div class="set-drive-state" id="setDriveState">Đang kiểm tra…</div>'
            '<div class="set-drive-acts">'
            '<a class="btn btn-ghost" id="setDriveConnect" href="/drive/connect">Kết nối Drive</a>'
            '<button type="button" class="btn btn-danger" id="setDriveDisconnect" style="display:none;margin-right:0">Ngắt kết nối</button>'
            '</div></div>'
        )
    return (
        '<div class="overlay" id="setOverlay">'
        '<div class="modal">'
        '<div class="modal-head"><span class="material-symbols-rounded">settings</span>'
        '<h3>Setting</h3>'
        '<button type="button" class="x material-symbols-rounded" id="setClose">close</button></div>'
        '<div class="modal-body"><p class="modal-note">Thêm Personal Access Token để thao tác Jira '
        '(đổi status, comment) nhân danh chính bạn. Token được mã hoá khi lưu, không hiển thị lại.</p>'
        '<div class="field"><label>Personal Access Token</label>'
        '<div class="inp-wrap"><input type="password" id="patInp" placeholder="Dán PAT của bạn vào đây..." autocomplete="off" spellcheck="false">'
        '<button type="button" class="eye material-symbols-rounded mi-sm" id="patShowBtn">visibility</button></div></div>'
        + drive +
        '</div>'
        '<div class="modal-foot">'
        '<button type="button" class="btn btn-danger" id="patDelBtn">Xoá PAT</button>'
        '<button type="button" class="btn btn-ghost" id="setCancel">Huỷ</button>'
        '<button type="button" class="btn btn-primary" id="patSaveBtn">Lưu</button>'
        '</div></div></div>'
    )


def _subtask_modal_v2():
    """Modal tạo Sub-task QA dưới 1 Task-PTSP (dùng chung mọi trang v2).
    Parent + Leader = type-ahead (gọi /search-parents, /search-people); assignee =
    dropdown 5 QA; start date default hôm nay. JS điều khiển trong app_v2.js."""
    today = datetime.now().strftime('%Y-%m-%d')
    opts = '<option value="">— Không gán —</option>'
    for u in USERS:
        opts += f'<option value="{esc(u)}">{esc(display_name(u))}</option>'
    return (
        '<div class="overlay" id="subOverlay"><div class="modal">'
        '<div class="modal-head"><span class="material-symbols-rounded">add_task</span>'
        '<h3>Tạo Sub-task</h3>'
        '<button type="button" class="x material-symbols-rounded" id="subClose">close</button></div>'
        '<div class="modal-body">'
        '<div class="mfield"><label>Task cha — Task-PTSP *</label>'
        '<div class="typeahead" id="subParentTA">'
        '<input type="text" id="subParentInp" placeholder="Gõ key hoặc tên Task-PTSP…" autocomplete="off" spellcheck="false">'
        '<div class="ta-results" id="subParentRes"></div></div>'
        '<div class="ta-chip" id="subParentChip" style="display:none"></div></div>'
        '<div class="mfield"><label>Tiêu đề *</label>'
        '<input type="text" id="subSummary" placeholder="Nội dung sub-task…" autocomplete="off"></div>'
        '<div class="mfield row2">'
        f'<div><label>Ngày bắt đầu *</label><input type="date" id="subStart" value="{today}"></div>'
        '<div><label>Hạn chót *</label><input type="date" id="subDue"></div>'
        '</div>'
        f'<div class="mfield"><label>Người xử lý</label><select id="subAssignee">{opts}</select></div>'
        '<div class="mfield"><label>Leader</label>'
        '<div class="typeahead" id="subLeaderTA">'
        '<input type="text" id="subLeaderInp" placeholder="Gõ tên leader…" autocomplete="off" spellcheck="false">'
        '<div class="ta-results" id="subLeaderRes"></div></div>'
        '<div class="ta-chip" id="subLeaderChip" style="display:none"></div></div>'
        '</div>'
        '<div class="modal-foot">'
        '<button type="button" class="btn btn-ghost" id="subCancel">Huỷ</button>'
        '<button type="button" class="btn btn-primary" id="subCreate">Tạo sub-task</button>'
        '</div></div></div>'
    )


def _stale_banner(note):
    """Banner OFFLINE: đang phục vụ snapshot KV cũ (Jira không với tới). `note` = mô tả nguồn."""
    return (
        '<div style="background:#fff4e5;border:1px solid #ffb74d;color:#7a4b00;'
        'border-radius:10px;padding:10px 14px;margin:0 0 16px;font-size:13px;'
        'display:flex;gap:8px;align-items:center">'
        '<span style="font-size:16px">🔌</span><span>'
        f'<b>Đang xem OFFLINE</b> — {esc(note)}. '
        'Không đổi được task (đổi trạng thái / tạo sub-task) tới khi có kết nối Jira.'
        '</span></div>')


def _chat_widget():
    """Float chat icon góc dưới-phải + panel chatbot. Render trên MỌI trang v2 (shell).
    Chỉ hiện khi CHAT_ENABLED (có OLLAMA_MODEL). Controller `#chatFab`/`#chatPanel`
    trong app_v2.js — stream từ POST /chat."""
    if not CHAT_ENABLED:
        return ''
    return (
        '<button type="button" class="chat-fab" id="chatFab" title="Trợ lý QA AI" aria-label="Mở chatbot">'
        '<span class="material-symbols-rounded" id="chatFabIc">smart_toy</span></button>'
        '<div class="chat-panel" id="chatPanel" aria-hidden="true">'
        '<div class="chat-head">'
        '<span class="chat-head-ic material-symbols-rounded">smart_toy</span>'
        '<div class="chat-head-tt"><b>Trợ lý QA</b><small>Hỏi về bug, test case, tài liệu…</small></div>'
        '<button type="button" class="chat-clear" id="chatClear" title="Xoá hội thoại">'
        '<span class="material-symbols-rounded mi-sm">delete_sweep</span></button>'
        '<button type="button" class="chat-x material-symbols-rounded" id="chatClose">close</button>'
        '</div>'
        '<div class="chat-body" id="chatBody"></div>'
        '<div class="chat-input">'
        '<textarea id="chatInp" rows="1" placeholder="Nhập câu hỏi… (Enter để gửi)" '
        'autocomplete="off" spellcheck="false"></textarea>'
        '<button type="button" class="chat-send" id="chatSend" title="Gửi">'
        '<span class="material-symbols-rounded">send</span></button>'
        '</div></div>'
    )


def _document_v2(content_inner, active, user, activities, title='QA Suite',
                 stale=False, stale_note=''):
    """Shell sidebar Material-3 cho dashboard QA + roadmap. Inline styles_v2.css + app_v2.js.
    `activities` = feed (đã lọc dismissed) cho chuông notif (embed JSON #qaNotif).
    stale=True -> Jira không với tới, đang phục vụ snapshot KV cũ: banner + window.__stale
    (app_v2.js chặn write /do-transition + /create-subtask)."""
    banner = _stale_banner(stale_note) if stale else ''
    return f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
{_FONTS_V2}
<script>(function(){{try{{var t=localStorage.getItem('qa-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>{load_css_v2()}</style></head>
<body>
<div class="app">{render_sidebar_v2(active, user)}
<div class="main">{render_topbar_v2()}
<div class="content">{banner}{content_inner}</div></div></div>
{_settings_modal_v2(user)}
{_subtask_modal_v2()}
<div class="toast" id="toast"></div>
<div class="drawer-ov" id="drawerOv"></div><aside class="drawer" id="drawer"></aside>
{_chat_widget()}
{_json_script('qaNotif', activities)}
<script>window.__jiraBase={json.dumps(JIRA_URL)};window.__stale={json.dumps(bool(stale))};</script>
<script>{load_js_v2()}</script>
</body></html>"""


def _document_public_v2(content_inner, title='QA Suite'):
    return f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
{_FONTS_V2}
<script>(function(){{try{{var t=localStorage.getItem('qa-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>{load_css_v2()}
.public-main {{ padding: 20px; max-width: 1200px; margin: 0 auto; }}
.public-brand {{ margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--bdr); display: flex; align-items: center; justify-content: space-between; }}
.public-brand h2 {{ margin: 0; font-size: 20px; color: var(--fg); }}
.public-brand button {{ background: transparent; border: none; cursor: pointer; color: var(--fg2); display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; border-radius: 50%; }}
.public-brand button:hover {{ background: var(--bg3); color: var(--fg); }}
</style></head>
<body>
<div class="app public-app">
<div class="main public-main">
<div class="public-brand">
    <h2>{esc(title)}</h2>
    <button class="iconbtn" onclick="document.documentElement.setAttribute('data-theme', document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'); localStorage.setItem('qa-theme', document.documentElement.getAttribute('data-theme'))"><span class="material-symbols-rounded">dark_mode</span></button>
</div>
<div class="content">{content_inner}</div>
</div>
</div>
<div class="toast" id="toast"></div>
<script>window.__stale=false;</script>
<script>{load_js_v2()}</script>
</body></html>"""
