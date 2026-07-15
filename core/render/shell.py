"""UI v2 (Stitch) shell — sidebar / topbar / modals / `_document_v2`.

Shared chrome wrapping every v2 page (dashboard QA, my-work, roadmap, docs,
bug-log, leader-eval, settings). Page submodules call `_document_v2` to assemble
the full document. Assets inline per-render via render.base. See issue #104 / #86.
"""
import json
from datetime import datetime

from config import JIRA_URL, USERS, DEV_EMAILS, display_name, username_from_email
from custom_status import CUSTOM_STATUSES
from issues import esc

from render.base import load_css_v2, load_js_v2, _json_script


# ===== UI v2 (Stitch) — shell sidebar dùng cho dashboard QA + roadmap
# ===================================================================
_FONTS_V2 = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400..700'
    '&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'
    '<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>'
    '<link href="https://cdn.jsdelivr.net/npm/@phosphor-icons/web@2.1.1/src/light/style.css" rel="stylesheet">'
    '<link href="https://cdn.jsdelivr.net/npm/@phosphor-icons/web@2.1.1/src/fill/style.css" rel="stylesheet">'
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
            '<span class="material-symbols-rounded ph-light ph-cloud-slash ce-ic"></span>'
            f'<div class="ce-msg">{esc(msg)}</div>'
            '<button type="button" class="ce-retry" onclick="location.reload()">'
            '<span class="material-symbols-rounded ph-light ph-arrow-clockwise mi-sm"></span> Thử lại</button>'
            '</div>')


def render_sidebar_v2(active, user):
    is_admin = user[1] if (user and len(user) > 1) else True
    email = user[0] if (user and user[0]) else ''

    # Phosphor: nav mặc định light; tab đang active dùng fill (đậm nét) thay cho FILL 1 của Material.
    _ph_nav = {'space_dashboard': 'squares-four', 'person': 'user', 'star': 'star', 'map': 'map-trifold',
               'bug_report': 'bug-beetle', 'checklist': 'list-checks', 'monitoring': 'chart-line-up',
               'description': 'file-text'}

    def lnk(href, key, icon, label):
        cls = ' class="active"' if key == active else ''
        wt = 'fill' if key == active else 'light'
        ph = _ph_nav.get(icon, icon)
        return (f'<a{cls} href="{href}"><span class="material-symbols-rounded ph-{wt} ph-{ph}"></span> {label}</a>')

    is_dev = bool(email) and email in DEV_EMAILS and not is_admin
    if is_dev:
        # Role dev (tạm thời): chỉ 2 tab. Trang chính = "Việc của tôi".
        nav = lnk('/my-work', 'mywork', 'person', 'Việc của tôi')
        nav += lnk('/bug-log', 'buglog', 'bug_report', 'Bugs')
    else:
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
            else '<span class="role-chip">Dev</span>' if is_dev
            else '<span class="role-chip">Chỉ xem</span>')
    sub = esc(email) if email else 'Local dev'
    logout = ('<div class="sep"></div>'
              '<a class="danger" href="/logout"><span class="material-symbols-rounded ph-light ph-sign-out mi-sm"></span> Đăng xuất</a>'
              ) if email else ''
    return (
        '<aside class="sidebar" id="sidebar">'
        '<div class="brand"><h1>QA Workspace</h1></div>'
        f'<nav class="nav">{nav}</nav>'
        '<div class="nav-foot">'
        '<div class="pmenu" id="pmenu">'
        '<button type="button" id="pmSettings"><span class="material-symbols-rounded ph-light ph-gear-six mi-sm"></span> Setting</button>'
        f'{logout}</div>'
        '<button class="profile" id="profileBtn">'
        f'<span class="av">{esc(init)}</span>'
        f'<span class="who"><b>{esc(short)} {role}</b><small>{sub}</small></span>'
        '<span class="material-symbols-rounded ph-light ph-arrows-down-up mi-sm"></span>'
        '</button></div></aside>'
    )


def render_topbar_v2():
    return (
        '<div class="topbar">'
        '<button class="iconbtn hamb" id="navToggle" title="Menu" aria-label="Mở menu">'
        '<span class="material-symbols-rounded ph-light ph-list mi-lg"></span></button>'
        '<div class="search"><span class="si material-symbols-rounded ph-light ph-magnifying-glass mi-sm"></span>'
        '<input type="text" id="searchInp" placeholder="Tìm task, kế hoạch...  (Ctrl+K mở bảng lệnh)"></div>'
        '<div class="top-right">'
        '<button class="topcreate" id="createSubBtn" title="Tạo sub-task QA dưới 1 Task-PTSP">'
        '<span class="material-symbols-rounded ph-light ph-plus mi-sm"></span> Tạo Sub-task</button>'
        '<button class="iconbtn" id="bellBtn" title="Thông báo">'
        '<span class="material-symbols-rounded ph-light ph-bell mi-lg"></span>'
        '<span class="badge-dot" id="bellDot" style="display:none">0</span></button>'
        '<button class="iconbtn" id="themeBtn" title="Đổi giao diện">'
        '<span class="material-symbols-rounded ph-light ph-moon" id="themeIc"></span></button>'
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
            '<label class="set-drive-lbl"><span class="material-symbols-rounded ph-light ph-cloud mi-sm"></span> '
            'Kết nối Google Drive (Bug Log)</label>'
            '<p class="modal-note">Cấp quyền <b>chỉ đọc</b> để background sync đọc file <code>.xlsx</code> bug log. '
            'Khi Google hỏi, chọn tài khoản <b>@baokim.vn</b>. Token được mã hoá khi lưu.</p>'
            '<div class="set-drive-state" id="setDriveState"><span class="skel skel-line w60" style="display:inline-block;width:180px"></span></div>'
            '<div class="set-drive-acts">'
            '<a class="btn btn-ghost" id="setDriveConnect" href="/drive/connect">Kết nối Drive</a>'
            '<button type="button" class="btn btn-danger" id="setDriveDisconnect" style="display:none;margin-right:0">Ngắt kết nối</button>'
            '</div></div>'
        )
    return (
        '<div class="overlay" id="setOverlay">'
        '<div class="modal">'
        '<div class="modal-head"><span class="material-symbols-rounded ph-light ph-gear-six"></span>'
        '<h3>Setting</h3>'
        '<button type="button" class="x material-symbols-rounded ph-light ph-x" id="setClose"></button></div>'
        '<div class="modal-body"><p class="modal-note">Thêm Personal Access Token để thao tác Jira '
        '(đổi status, comment) nhân danh chính bạn. Token được mã hoá khi lưu, không hiển thị lại.</p>'
        '<div class="field"><label>Personal Access Token</label>'
        '<div class="inp-wrap"><input type="password" id="patInp" placeholder="Dán PAT của bạn vào đây..." autocomplete="off" spellcheck="false">'
        '<button type="button" class="eye material-symbols-rounded ph-light ph-eye mi-sm" id="patShowBtn"></button></div></div>'
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
        '<div class="modal-head"><span class="material-symbols-rounded ph-light ph-plus-circle"></span>'
        '<h3>Tạo Sub-task</h3>'
        '<button type="button" class="x material-symbols-rounded ph-light ph-x" id="subClose"></button></div>'
        '<div class="modal-body">'
        '<div class="mfield"><label>Task cha — Task-PTSP *</label>'
        '<div class="typeahead" id="subParentTA">'
        '<input type="text" id="subParentInp" placeholder="Gõ key hoặc tên Task-PTSP…" autocomplete="off" spellcheck="false">'
        '<div class="ta-results" id="subParentRes"></div></div>'
        '<div class="ta-chip" id="subParentChip" style="display:none"></div></div>'
        '<div class="mfield"><label>Tiêu đề * <small class="mhint">(mỗi dòng = 1 sub-task)</small></label>'
        '<textarea id="subSummary" rows="4" placeholder="Nội dung sub-task…&#10;Mỗi dòng tạo 1 sub-task riêng" autocomplete="off" spellcheck="false"></textarea>'
        '<div class="mcount" id="subCount"></div></div>'
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


def _palette_modal_v2():
    """Command palette Ctrl+K (dùng chung mọi trang v2). JS điều khiển trong app_v2.js
    (guard #cpOverlay): điều hướng + hành động + tìm task Jira + tìm bug trong bug log."""
    return (
        '<div class="cp-overlay" id="cpOverlay">'
        '<div class="cp-panel">'
        '<div class="cp-inputwrap"><span class="material-symbols-rounded ph-light ph-magnifying-glass mi-sm"></span>'
        '<input type="text" id="cpInput" placeholder="Tìm task, bug, trang, hành động…" '
        'autocomplete="off" spellcheck="false"><kbd>esc</kbd></div>'
        '<div class="cp-list" id="cpList"></div>'
        '<div class="cp-foot"><span><kbd>↑</kbd><kbd>↓</kbd> chọn</span>'
        '<span><kbd>Enter</kbd> mở</span><span><kbd>Esc</kbd> đóng</span></div>'
        '</div></div>'
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


def _auth_banner(note, is_admin=False):
    """Banner khi PAT chung hết hạn/thu hồi (Jira coi request là vô danh). Tách khỏi OFFLINE
    để khỏi đánh lừa thành lỗi mạng. Admin được chỉ dẫn cách sửa; QA chỉ báo + nhờ admin."""
    fix = ('Cập nhật <b>JIRA_PAT</b> trong <code>.env</code> bằng token mới '
           '(Jira → Personal Access Tokens → Create token) rồi restart server.'
           if is_admin else 'Báo admin cấp lại token để khôi phục.')
    return (
        '<div style="background:#fdecea;border:1px solid #e57373;color:#7a1c12;'
        'border-radius:10px;padding:10px 14px;margin:0 0 16px;font-size:13px;'
        'display:flex;gap:8px;align-items:center">'
        '<span style="font-size:16px">🔑</span><span>'
        f'<b>PAT Jira hết hạn</b> — {esc(note)}. {fix} '
        'Đang hiển thị dữ liệu lưu tạm (read-only).'
        '</span></div>')


def _document_v2(content_inner, active, user, activities, title='QA Suite',
                 stale=False, stale_note=''):
    """Shell sidebar Material-3 cho dashboard QA + roadmap. Inline styles_v2.css + app_v2.js.
    `activities` = feed (đã lọc dismissed) cho chuông notif (embed JSON #qaNotif).
    stale=True -> Jira không với tới, đang phục vụ snapshot KV cũ: banner + window.__stale
    (app_v2.js chặn write /do-transition + /create-subtask)."""
    if stale == 'auth':
        _adm = bool(user[1]) if isinstance(user, (tuple, list)) and len(user) > 1 else False
        banner = _auth_banner(stale_note, _adm)
    elif stale:
        banner = _stale_banner(stale_note)
    else:
        banner = ''
    return f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
{_FONTS_V2}
<script>(function(){{try{{var t=localStorage.getItem('qa-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>{load_css_v2()}</style></head>
<body>
<div class="app"><div class="nav-scrim" id="navScrim"></div>{render_sidebar_v2(active, user)}
<div class="main">{render_topbar_v2()}
<div class="content">{banner}{content_inner}</div></div></div>
{_settings_modal_v2(user)}
{_subtask_modal_v2()}
{_palette_modal_v2()}
<div class="drawer-ov" id="drawerOv"></div><aside class="drawer" id="drawer"></aside>
<div class="smenu" id="smenu"></div>
{_json_script('qaNotif', activities)}
<script>window.__jiraBase={json.dumps(JIRA_URL)};window.__stale={json.dumps(bool(stale))};window.__isAdmin={json.dumps(bool(user[1]) if isinstance(user, (tuple, list)) and len(user) > 1 else True)};window.QA_CUSTOM_STATUSES={json.dumps(CUSTOM_STATUSES, ensure_ascii=False)};</script>
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
    <button class="iconbtn" onclick="document.documentElement.setAttribute('data-theme', document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'); localStorage.setItem('qa-theme', document.documentElement.getAttribute('data-theme'))"><span class="material-symbols-rounded ph-light ph-moon"></span></button>
</div>
<div class="content">{content_inner}</div>
</div>
</div>
<script>window.__stale=false;</script>
<script>{load_js_v2()}</script>
</body></html>"""
