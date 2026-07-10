"""Tài liệu training (tab /docs) — cây folder + link Google Drive + upload file thật.

Render shell + modals (tạo thư mục / thêm link Drive / tải lên), cây render
client-side bởi controller `#docsData` trong app_v2.js.

Tách từ render/__init__.py (issue #107 / #86). Zero behavior change — chỉ di
chuyển định nghĩa, re-export ở __init__ để chỗ gọi không phải đổi import.
"""
from render.base import _json_script
from render.shell import _document_v2


# ===== Tài liệu training (tab /docs): cây folder + link Google Drive =====
def render_docs_page(tree, editable=True, user=None, activities=None):
    if activities is None:
        activities = []
    
    action_buttons_html = ""
    if editable:
        action_buttons_html = """
          <button class="btn-sec" onclick="openModal('folderModal')">
            <span class="material-symbols-rounded ph-light ph-folder-plus"></span>
            Tạo thư mục
          </button>
          <button class="btn-pri" onclick="openModal('uploadModal')">
            <span class="material-symbols-rounded ph-light ph-upload-simple"></span>
            Tải lên tài liệu
          </button>
          <button class="btn-sec" onclick="openModal('linkModal')">
            <span class="material-symbols-rounded ph-light ph-link"></span>
            Thêm link Drive
          </button>
        """

    ro_banner = ""
    if not editable:
        ro_banner = '<div style="margin: 0 32px 16px; padding: 12px 16px; background: var(--surface-variant); color: var(--on-surface-variant); border-radius: 8px; font-size: 13px; display: flex; align-items: center; gap: 8px;"><span class="material-symbols-rounded ph-light ph-info" style="color: var(--primary);"></span>👁 Chế độ chỉ xem — chỉ quản lý mới chỉnh sửa được.</div>'

    content_inner = f"""
    <div class="content">
      <div class="content-header">
        <div>
          <h2 class="page-title">Tài liệu QA</h2>
        </div>
        <div class="action-buttons">
          {action_buttons_html}
        </div>
      </div>
      
      {ro_banner}

      <div class="breadcrumbs" id="breadcrumbs" style="display:none">
        <a onclick="navigateBackToRoot()">Tài liệu QA</a>
        <span class="separator">/</span>
        <span class="current" id="currentBreadcrumb">Thư mục</span>
      </div>

      <!-- Folders Section -->
      <div id="foldersSection">
        <div class="section-title-row">
          <h3>Thư mục</h3>
        </div>
        <div class="folder-grid" id="folderGrid"></div>
      </div>

      <!-- Documents List Section -->
      <div>
        <div class="section-title-row">
          <h3 id="tableTitle">Tài liệu gần đây</h3>
          <a class="view-all-link" id="viewAllDocs" onclick="navigateBackToRoot()">Xem tất cả <span class="material-symbols-rounded ph-light ph-caret-right"></span></a>
        </div>
        
        <div class="table-card">
          <table class="doc-table">
            <thead>
              <tr>
                <th>Tên tài liệu</th>
                <th style="width: 180px">Ngày sửa</th>
                {"<th class='action-col'>Hành động</th>" if editable else ""}
              </tr>
            </thead>
            <tbody id="docTableBody">
              <!-- JS renders rows here -->
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ===== Floating Context Menu ===== -->
    <div class="context-menu" id="contextMenu">
      {"" if not editable else '<button onclick="editDoc()"><span class="material-symbols-rounded ph-light ph-pencil-simple mi-sm"></span>Sửa đổi</button>'}
      <button onclick="openLink()"><span class="material-symbols-rounded ph-light ph-arrow-square-out mi-sm"></span>Mở link</button>
      <button onclick="copyDocLink()"><span class="material-symbols-rounded ph-light ph-copy mi-sm"></span>Sao chép link</button>
      {"<div class='divider'></div>" if editable else ""}
      {"" if not editable else '<button class="danger" onclick="deleteDoc()"><span class="material-symbols-rounded ph-light ph-trash mi-sm"></span>Xoá tài liệu</button>'}
    </div>

    <!-- ===== Processing Status Toast ===== -->
    <div class="bottom-toast" id="bottomToast">
      <span class="material-symbols-rounded ph-light ph-check-circle icon-success"></span>
      <span class="toast-text" id="bottomToastText">Đang xử lý yêu cầu...</span>
    </div>
    """

    if editable:
        content_inner += """
    <!-- ===== MODAL: TẠO THƯ MỤC ===== -->
    <div class="overlay" id="folderModal" onclick="if(event.target===this)closeModal('folderModal')">
      <div class="modal">
        <div class="modal-head">
          <span class="material-symbols-rounded ph-light ph-folder-plus"></span>
          <h3>Tạo thư mục mới</h3>
          <button class="x material-symbols-rounded ph-light ph-x" onclick="closeModal('folderModal')"></button>
        </div>
        <div class="modal-body">
          <div class="mfield">
            <label for="folderNameInp">Tên thư mục</label>
            <input type="text" id="folderNameInp" placeholder="Nhập tên thư mục..." autocomplete="off">
          </div>
          <div class="mfield" id="folderParentField">
            <label for="folderParentSel">Thư mục cha</label>
            <select id="folderParentSel">
              <option value="root">Thư mục gốc (Root)</option>
            </select>
          </div>
          <div class="mfield">
            <label>Màu sắc</label>
            <div class="color-picker" id="folderColorPicker">
              <div class="color-opt blue selected" data-color="blue" onclick="selectColor(this)"></div>
              <div class="color-opt orange" data-color="orange" onclick="selectColor(this)"></div>
              <div class="color-opt green" data-color="green" onclick="selectColor(this)"></div>
              <div class="color-opt purple" data-color="purple" onclick="selectColor(this)"></div>
            </div>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-ghost" onclick="closeModal('folderModal')">Huỷ</button>
          <button class="btn btn-primary" onclick="createFolder()">Tạo thư mục</button>
        </div>
      </div>
    </div>

    <!-- ===== MODAL: THÊM LINK DRIVE ===== -->
    <div class="overlay" id="linkModal" onclick="if(event.target===this)closeModal('linkModal')">
      <div class="modal">
        <div class="modal-head">
          <span class="material-symbols-rounded ph-light ph-link"></span>
          <h3>Thêm link tài liệu Google Drive</h3>
          <button class="x material-symbols-rounded ph-light ph-x" onclick="closeModal('linkModal')"></button>
        </div>
        <div class="modal-body">
          <div class="mfield">
            <label for="linkTitleInp">Tên tài liệu</label>
            <input type="text" id="linkTitleInp" placeholder="Nhập tên tài liệu..." autocomplete="off">
          </div>
          <div class="mfield">
            <label for="linkUrlInp">Đường dẫn Google Drive</label>
            <input type="text" id="linkUrlInp" placeholder="https://docs.google.com/..." autocomplete="off">
          </div>
          <div class="mfield">
            <label for="linkFolderSel">Thư mục</label>
            <select id="linkFolderSel">
            </select>
          </div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-ghost" onclick="closeModal('linkModal')">Huỷ</button>
          <button class="btn btn-primary" onclick="addDriveLink()">Lưu tài liệu</button>
        </div>
      </div>
    </div>

    <!-- ===== MODAL: TẢI LÊN TÀI LIỆU ===== -->
    <div class="overlay" id="uploadModal" onclick="if(event.target===this)closeModal('uploadModal')">
      <div class="modal">
        <div class="modal-head">
          <span class="material-symbols-rounded ph-light ph-upload-simple"></span>
          <h3>Tải lên tài liệu</h3>
          <button class="x material-symbols-rounded ph-light ph-x" onclick="closeModal('uploadModal')"></button>
        </div>
        <div class="modal-body">
          <div class="dropzone" id="dropzone" onclick="document.getElementById('fileInput').click()">
            <span class="material-symbols-rounded ph-light ph-cloud-arrow-up icon"></span>
            <div class="text">Kéo thả tệp tin hoặc Click để chọn tệp tải lên</div>
            <div class="hint" style="font-size: 11px; color: var(--on-surface-variant); margin-top: 4px;">Hỗ trợ .pdf, .xlsx, .docx, .png (tối đa 20MB)</div>
            <input type="file" id="fileInput" onchange="handleFileSelect(event)">
          </div>
          
          <div class="mfield" id="uploadForm" style="display:none">
            <label for="uploadFolderSel">Lưu vào thư mục</label>
            <select id="uploadFolderSel">
            </select>
          </div>

          <div class="progress-wrap" id="progressWrap" style="display:none">
            <div class="progress-bar"><i id="progressPercent" style="width: 0%"></i></div>
            <div class="progress-text">
              <span id="uploadFileName">tailieu.pdf</span>
              <span id="uploadPercentage">0%</span>
            </div>
          </div>
        </div>
        <div class="modal-foot" id="uploadModalFoot">
          <button class="btn btn-ghost" onclick="closeModal('uploadModal')">Huỷ</button>
          <button class="btn btn-primary" id="uploadBtn" onclick="performRealUpload()" disabled>Bắt đầu tải lên</button>
        </div>
      </div>
    </div>
    """

    content_inner += f"""
    <script>
      window.QA_DOCS_EDITABLE = {"true" if editable else "false"};
    </script>
    """

    content_inner += _json_script('docsData', tree)

    return _document_v2(content_inner, 'docs', user, activities, title='Tài liệu QA')
