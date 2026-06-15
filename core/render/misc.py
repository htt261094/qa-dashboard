"""Trang phụ + card lẻ: 403, Settings (PAT + Drive), error page.

Tách từ render/__init__.py (issue #105 / #86). Zero behavior change — chỉ di
chuyển định nghĩa, re-export ở __init__ để chỗ gọi không phải đổi import.
"""
from config import JIRA_URL
from issues import esc
from render.base import load_css
from render.shell import _document_v2, _conn_error_card


def render_403():
    """Trang 403 tối giản — KHÔNG lộ domain/điều kiện được phép (giấu thông tin)."""
    return ('<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><title>403</title>'
            '<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#091e42;'
            'color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}'
            '.b{text-align:center}.c{font-size:64px;font-weight:800;letter-spacing:2px}'
            '.m{color:#a5adba;margin-top:8px}a{color:#85b8ff}</style></head>'
            '<body><div class="b"><div class="c">403</div>'
            '<div class="m">Unauthorized</div>'
            '<p><a href="/logout">Đăng nhập lại</a></p></div></body></html>')


# ===== Settings page (/settings): nhập PAT cá nhân để thao tác Jira ghi đúng tên mình =====
def _render_drive_card(has_drive, auth_enabled):
    """Card 'Kết nối Drive' (admin-only) — lấy refresh_token đọc file bug log (#52)."""
    if not auth_enabled:
        return ('<div class="set-card">'
                '<h2>🔗 Kết nối Google Drive (Bug Log)</h2>'
                '<div class="set-state set-none">⚠ Chưa bật Google OAuth (GOOGLE_CLIENT_ID/SECRET) '
                'nên không kết nối Drive được. Đây là chế độ local dev.</div></div>')
    if has_drive:
        state = ('<div class="set-state set-ok">✓ Đã kết nối Drive. Background sync đọc file bug log '
                 'bằng quyền admin (chỉ đọc).</div>')
        btns = ('<a href="/drive/connect" class="set-btn">Kết nối lại</a>'
                '<button type="button" id="driveDisconnect" class="set-link-del">Ngắt kết nối Drive</button>')
    else:
        state = ('<div class="set-state set-none">⚠ Chưa kết nối Drive. Bug log sync sẽ báo '
                 '"chưa kết nối Drive".</div>')
        btns = '<a href="/drive/connect" class="set-btn">Kết nối Drive</a>'
    # Lưu ý: account chooser luôn hiện (prompt=select_account, auth.py) — chọn ĐÚNG tài
    # khoản @baokim.vn, KHÔNG dùng Gmail cá nhân (sẽ bị domain gate từ chối).
    return (
        '<div class="set-card">'
        '<h2>🔗 Kết nối Google Drive (Bug Log)</h2>'
        f'{state}'
        '<p class="set-note">Cấp quyền <b>chỉ đọc</b> (<code>drive.readonly</code>) bằng tài khoản admin '
        'để background sync tải file <code>.xlsx</code> bug log. Token được mã hoá (AES) trước khi lưu, '
        'không bao giờ lưu dạng thô và không ghi/sửa được file trên Drive.</p>'
        '<p class="set-note">⚠ Khi Google hỏi, hãy <b>chọn tài khoản <code>@baokim.vn</code></b> '
        '(không phải Gmail cá nhân) — tài khoản ngoài domain sẽ bị từ chối.</p>'
        f'<div class="set-form">{btns}</div>'
        '</div>'
    )


def render_settings_page(has_pat, user=None, has_drive=False, auth_enabled=False, activities=None):
    status_line = ('<div class="set-state set-ok">✓ Bạn đã lưu PAT. Thao tác đổi status/comment sẽ ghi đúng tên bạn trên Jira.</div>'
                   if has_pat else
                   '<div class="set-state set-none">⚠ Bạn chưa lưu PAT. Hiện thao tác (nếu có) sẽ mang tên tài khoản chung.</div>')
    jira_base = esc(JIRA_URL)
    inner = (
        '<div class="page-head"><div>'
        '<h2 class="page-title">⚙ Setting — Personal Access Token (PAT)</h2>'
        '<div class="page-sub">PAT giúp dashboard thao tác Jira <strong>nhân danh chính bạn</strong>. '
        'Mã được mã hoá (AES) trước khi lưu, không bao giờ lưu dạng thô.</div>'
        '</div></div>'
        f'<div class="set-wrap">{status_line}'
        '<div class="set-card">'
        '<h2>1. Tạo PAT trên Jira</h2>'
        '<ol class="set-steps">'
        f'<li>Mở <a href="{jira_base}/secure/ViewProfile.jspa" target="_blank" rel="noopener">Hồ sơ Jira của bạn</a> → '
        '<b>Personal Access Tokens</b>.</li>'
        '<li>Bấm <b>Create token</b>, đặt tên (vd "QA Dashboard"), chọn thời hạn.</li>'
        '<li>Copy chuỗi token (chỉ hiện 1 lần).</li>'
        '</ol>'
        '<h2>2. Dán vào đây</h2>'
        '<div class="set-form">'
        '<input type="password" id="patInput" class="set-input" placeholder="Dán PAT của bạn..." autocomplete="off" spellcheck="false">'
        '<button type="button" id="patSave" class="set-btn">Lưu PAT</button>'
        '<button type="button" id="patShow" class="set-btn ghost" title="Hiện/ẩn">👁</button>'
        '</div>'
        + ('<button type="button" id="patDelete" class="set-link-del">Xoá PAT đã lưu</button>' if has_pat else '')
        + '<p class="set-note">⚠ Token được verify thuộc đúng tài khoản của bạn (gọi <code>/myself</code>) trước khi lưu. '
        'PAT của người khác sẽ bị từ chối.</p>'
        '</div>'
        + '</div>'
    )
    return _document_v2(inner, 'settings', user, activities or [], title='Cài đặt — QA Dashboard')


def render_shell_error(active='dashboard', user=None,
                       msg='Không thể kết nối tới Jira. Vui lòng thử lại.',
                       title='QA Workspace'):
    """Lỗi GIỮ NGUYÊN skeleton v2 (sidebar + topbar) — chỉ phần nội dung cần Jira
    đổi sang thông báo lỗi. Dùng khi Jira timeout/không với tới ở các route fetch
    Jira (`/`, /my-work, /leader-eval, /settings). Khác render_error_page (trang
    trắng, mất chrome). Chuông notif rỗng (`[]`) vì Jira đang down."""
    inner = (
        '<div class="page-head"><div>'
        '<h2 class="page-title">Bảng điều khiển</h2></div></div>'
        + _conn_error_card(msg)
    )
    return _document_v2(inner, active, user, [], title=title)


def render_login_page():
    """Màn hình đăng nhập — đứng TRƯỚC khi nhảy sang Google OAuth.

    `/login` render trang này (nút bấm); chỉ khi user bấm "Đăng nhập với Google"
    (-> `/login?go=1`) mới set state cookie + 302 sang Google. Trước đây `/login`
    302 thẳng nên không có màn hình nào hiện ra."""
    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Đăng nhập — QA Dashboard</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;min-height:100vh;
display:flex;align-items:center;justify-content:center;
background:radial-gradient(1200px 600px at 50% -10%,#1c3a6e 0%,#091e42 60%,#06152f 100%);color:#fff}}
.card{{background:#0d2347;border:1px solid #1f3a66;border-radius:16px;padding:40px 36px;
width:360px;max-width:92vw;text-align:center;box-shadow:0 18px 50px rgba(0,0,0,.45)}}
.logo{{width:56px;height:56px;border-radius:14px;margin:0 auto 18px;
background:linear-gradient(135deg,#3b82f6,#60a5fa);display:flex;align-items:center;
justify-content:center;font-size:28px}}
h1{{font-size:20px;margin:0 0 6px}}
.sub{{color:#a5adba;font-size:14px;margin:0 0 28px}}
.gbtn{{display:flex;align-items:center;justify-content:center;gap:12px;width:100%;
padding:12px 16px;border-radius:10px;background:#fff;color:#1f2937;font-size:15px;
font-weight:600;text-decoration:none;border:0;cursor:pointer;transition:filter .15s}}
.gbtn:hover{{filter:brightness(.96)}}
.gico{{width:20px;height:20px;flex:0 0 20px}}
.foot{{color:#6b7a99;font-size:12px;margin-top:22px}}
</style></head>
<body><div class="card">
<div class="logo">✅</div>
<h1>QA Dashboard</h1>
<p class="sub">Đăng nhập bằng tài khoản Bảo Kim để tiếp tục</p>
<a class="gbtn" href="/login?go=1">
<svg class="gico" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>
Đăng nhập với Google</a>
<p class="foot">Chỉ tài khoản @baokim.vn được phép truy cập</p>
</div></body></html>"""


def render_error_page(msg):
    return f"""<!DOCTYPE html><html lang="vi"><head><meta charset="UTF-8"><title>Error</title>
<script>(function(){{try{{var t=localStorage.getItem('qa-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
<style>{load_css()}</style></head>
<body><div class="container"><header><h1>QA Team Dashboard</h1></header>
<div class="error"><strong>Lỗi pull data từ Jira:</strong><br>{esc(msg)}</div>
<p style="color:#6b778c;margin-top:16px">Check JIRA_URL, JIRA_PAT trong file .env. F5 để retry.</p>
</div></body></html>"""
