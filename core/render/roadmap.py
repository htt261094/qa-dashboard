"""Roadmap QA Team (tab /roadmap) — plan › task › sub-task, schema Stitch.

Render shell + danh sách kế hoạch + modal sửa; cây render client-side bởi
controller `#rmData`/`#rmMeta` trong app_v2.js.

Tách từ render/__init__.py (issue #108 / #86). Zero behavior change — chỉ di
chuyển định nghĩa, re-export ở __init__ để chỗ gọi không phải đổi import.
"""
from roadmap import RM_STATUSES, RM_PEOPLE
from render.base import _json_script
from render.shell import _document_v2


# ===== Roadmap v2 (plan › task › sub-task, schema Stitch) =====
def render_roadmap_v2(data, editable=True, user=None, activities=None):
    top_actions = ''
    if editable:
        top_actions = '''<div class="rm-top-actions">
            <button class="btn-sec" id="rmToggleMode"><span class="material-symbols-rounded mi-sm">edit</span> Bật chỉnh sửa</button>
            <button class="btn-pri" id="rmAddPlan" style="display:none;"><span class="material-symbols-rounded mi-sm">add_circle</span> Thêm kế hoạch</button>
        </div>'''
    
    banner = '' if editable else '<div class="ro-banner">👁 Chế độ chỉ xem — chỉ quản lý mới chỉnh sửa được.</div>'
    # Bỏ class 'ro' vì client-side JS sẽ chủ động không render các element edit nếu EDIT=false.
    ro = ''
    seg = (
        '<div class="rm-filter"><div class="seg" id="rmSeg">'
        '<button class="active" data-f="all">Tất cả</button>'
        '<button data-f="in_progress">Đang thực hiện</button>'
        '<button data-f="planned">Sắp tới</button>'
        '<button data-f="done">Hoàn thành</button>'
        '</div></div>'
    )
    modal = (
        '<div class="overlay" id="modalOverlay">'
        '<div class="modal">'
        '<div class="modal-head"><span class="material-symbols-rounded" id="modalIcon">edit</span>'
        '<h3 id="modalTitle">Sửa</h3>'
        '<button type="button" class="x material-symbols-rounded" id="modalClose">close</button></div>'
        '<div class="modal-body" id="modalBody"></div>'
        '<div class="modal-foot"><button type="button" class="btn btn-ghost" id="modalCancel">Huỷ</button>'
        '<button type="button" class="btn btn-primary" id="modalSave">Lưu</button></div>'
        '</div></div>'
    )
    rm_meta = {'editable': bool(editable), 'statuses': RM_STATUSES, 'people': RM_PEOPLE}
    content = (
        f'<div class="page-head"><div><h2>Lộ trình QA Team</h2></div>{top_actions}</div>'
        + banner + seg
        + f'<div class="rm-list{ro}" id="rmList2"></div>'
        + modal
        + _json_script('rmData', data or [])
        + _json_script('rmMeta', rm_meta)
    )
    return _document_v2(content, 'roadmap', user, activities or [], title='Roadmap QA Team')
