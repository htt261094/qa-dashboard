"""UI v2 (Stitch) shell — sidebar / topbar / modals / `_document_v2`.

Shared chrome wrapping every v2 page (my-work, docs, bug-log, analytics,
settings). Page submodules call `_document_v2` to assemble
the full document. Assets inline per-render via render.base. See issue #104 / #86.
"""
import json

from config import (LINEAR_BASE_URL, USERS, LOCAL_AUTOLOGIN, OWNER_EMAIL, display_name,
                    username_from_email)
from custom_status import CUSTOM_STATUSES
from issues import esc

from render.base import load_css_v2, load_js_v2, _json_script


# ===== UI v2 (Stitch) — shell sidebar dùng chung mọi trang
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


def _conn_error_card(msg='Không thể kết nối tới Linear. Vui lòng thử lại.'):
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
    _ph_nav = {'today': 'sun-horizon', 'person': 'user', 'bug_report': 'bug-beetle', 'monitoring': 'chart-line-up',
               'description': 'file-text'}

    def lnk(href, key, icon, label):
        cls = ' class="active"' if key == active else ''
        wt = 'fill' if key == active else 'light'
        ph = _ph_nav.get(icon, icon)
        return (f'<a{cls} href="{href}"><span class="material-symbols-rounded ph-{wt} ph-{ph}"></span> {label}</a>')

    # Dashboard dùng riêng 1 người (Decision #97): chỉ còn lens cá nhân + bug/tài liệu.
    nav = lnk('/today', 'today', 'today', 'Hôm nay')   # trang chính (Decision #102)
    from linear_api import get_active_cycle_label
    nav += lnk('/my-work', 'mywork', 'person', get_active_cycle_label())
    nav += lnk('/bug-log', 'buglog', 'bug_report', 'Bugs')
    nav += lnk('/analytics', 'analytics', 'monitoring', 'Analytics')
    nav += lnk('/docs', 'docs', 'description', 'Tài liệu')

    uname = username_from_email(email) if (email and '@' in email) else None
    short = display_name(uname) if uname else (email.split('@')[0] if '@' in email else 'Local')
    init = (short[:2] or 'ME').upper()
    role = ('<span class="role-chip admin">Admin</span>' if is_admin
            else '<span class="role-chip">Chỉ xem</span>')
    sub = esc(email) if email else 'Local dev'
    logout = ('<div class="sep"></div>'
              '<a class="danger" href="/logout"><span class="material-symbols-rounded ph-light ph-sign-out mi-sm"></span> Đăng xuất</a>'
              ) if (email and not (LOCAL_AUTOLOGIN and email == OWNER_EMAIL)) else ''
    # Auto-login chính chủ (Decision #98): đăng xuất xong vẫn tự vào lại -> ẩn nút cho khỏi lừa.
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
    # Card "Kết nối Drive" đã gỡ (#104): Bug Log nguồn Jira "Bug Testing", không còn Google Drive.
    drive = ''
    return (
        '<div class="overlay" id="setOverlay">'
        '<div class="modal">'
        '<div class="modal-head"><span class="material-symbols-rounded ph-light ph-gear-six"></span>'
        '<h3>Setting</h3>'
        '<button type="button" class="x material-symbols-rounded ph-light ph-x" id="setClose"></button></div>'
        '<div class="modal-body"><p class="modal-note">Thêm Linear API key để thao tác Linear '
        '(đổi status, comment) nhân danh chính bạn. Tạo tại '
        '<a href="https://linear.app/settings/api" target="_blank" rel="noopener">'
        'linear.app → Settings → API</a>. Token được mã hoá khi lưu, không hiển thị lại.</p>'
        '<div class="field"><label>Linear API key</label>'
        '<div class="inp-wrap"><input type="password" id="patInp" placeholder="Dán lin_api_... vào đây..." autocomplete="off" spellcheck="false">'
        '<button type="button" class="eye material-symbols-rounded ph-light ph-eye mi-sm" id="patShowBtn"></button></div></div>'
        + drive +
        # Thông báo desktop (Decision #103) — quyền do browser giữ theo origin, state ở localStorage.
        '<div class="set-drive" id="setNotifSect">'
        '<label class="set-drive-lbl"><span class="material-symbols-rounded ph-light ph-bell-ringing mi-sm"></span> '
        'Thông báo desktop</label>'
        '<p class="modal-note">Hiện thông báo của Windows khi có noti mới (được nhắc, đổi status, comment) '
        'lúc bạn KHÔNG đang xem dashboard. Giữ ít nhất 1 tab dashboard mở (có thể thu nhỏ).</p>'
        '<div class="set-drive-state" id="setNotifState"></div>'
        '<div class="set-drive-acts"><button type="button" class="btn btn-ghost" id="setNotifBtn">Bật thông báo</button></div>'
        '</div>'
        '</div>'
        '<div class="modal-foot">'
        '<button type="button" class="btn btn-danger" id="patDelBtn">Xoá token</button>'
        '<button type="button" class="btn btn-ghost" id="setCancel">Huỷ</button>'
        '<button type="button" class="btn btn-primary" id="patSaveBtn">Lưu</button>'
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


def _auth_banner(note, is_admin=False):
    """Banner khi API token chung hết hạn/thu hồi (Jira coi request là vô danh) — đang hiện bản
    RAM cũ. Admin được chỉ dẫn cách sửa; QA chỉ báo + nhờ admin."""
    fix = ('Cập nhật <b>LINEAR_API_KEY</b> trong <code>.env</code> bằng key mới '
           '(linear.app → Settings → API) rồi restart server.'
           if is_admin else 'Báo admin cấp lại key để khôi phục.')
    return (
        '<div style="background:#fdecea;border:1px solid #e57373;color:#7a1c12;'
        'border-radius:10px;padding:10px 14px;margin:0 0 16px;font-size:13px;'
        'display:flex;gap:8px;align-items:center">'
        '<span style="font-size:16px">🔑</span><span>'
        f'<b>Linear API key hết hạn</b> — {esc(note)}. {fix} '
        'Đang hiển thị dữ liệu lưu tạm.'
        '</span></div>')


def _document_v2(content_inner, active, user, activities, title='QA Suite',
                 stale=False, stale_note=''):
    """Shell sidebar Material-3 dùng chung mọi trang. Inline styles_v2.css + app_v2.js.
    `activities` = feed (đã lọc dismissed) cho chuông notif (embed JSON #qaNotif).
    stale='auth' -> token Jira chung hết hạn, đang phục vụ bản RAM cũ: banner đỏ."""
    if stale == 'auth':
        _adm = bool(user[1]) if isinstance(user, (tuple, list)) and len(user) > 1 else False
        banner = _auth_banner(stale_note, _adm)
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
{_palette_modal_v2()}
<div class="drawer-ov" id="drawerOv"></div><aside class="drawer" id="drawer"></aside>
<div class="smenu" id="smenu"></div>
{_json_script('qaNotif', activities)}
<script>window.__linearBase={json.dumps(LINEAR_BASE_URL)};window.__jiraBase=window.__linearBase;window.__isAdmin={json.dumps(bool(user[1]) if isinstance(user, (tuple, list)) and len(user) > 1 else True)};window.QA_CUSTOM_STATUSES={json.dumps(CUSTOM_STATUSES, ensure_ascii=False)};window.__mentionUsers={json.dumps([{'name': u, 'display': display_name(u)} for u in USERS], ensure_ascii=False)};</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script>{load_js_v2()}</script>
</body></html>"""

