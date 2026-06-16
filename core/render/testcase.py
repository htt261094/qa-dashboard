"""Quản lý Test Case (tab /test-cases) — UI + persistence.

Shell dùng `_document_v2`: repository panel (cây bộ/folder) + header + Import +
metric cards + bảng duyệt + modal Import từ Google Sheet + drawer chi tiết.

Dữ liệu render client-side bởi controller `#tcData` trong app_v2.js. Store qua
testcase_store.py (local-first + sync KV chéo máy). Folders lưu thật; Import
Google Sheet backend chưa nối (#152).
Phân quyền: nút edit (Import/folder) chỉ hiện khi `editable` (admin).
"""
from render.base import _json_script
from render.shell import _document_v2

# Tập trạng thái kết quả chạy + nhãn — chốt chính thức ở #155/#156. Để đây cho
# controller/JS map class màu; KHÔNG hardcode logic, chỉ là tham chiếu hiển thị.
TC_RESULTS = ['pass', 'fail', 'pending', 'blocked', 'norun']


def _import_modal():
    """Modal Import test case từ Google Sheet (chốt UI; backend nối ở #152)."""
    return """
    <div class="overlay" id="tcImportOverlay" onclick="if(event.target===this)tcCloseImport()">
      <div class="modal">
        <div class="modal-head">
          <span class="tc-gs-ic"><span class="material-symbols-rounded">table_chart</span></span>
          <h3>Nhập Test Case từ Google Sheets</h3>
          <button type="button" class="x material-symbols-rounded" onclick="tcCloseImport()">close</button>
        </div>
        <div class="modal-body">
          <div class="mfield">
            <label>Link Google Sheet</label>
            <div class="tc-iwrap">
              <span class="lead material-symbols-rounded mi-sm">link</span>
              <input type="text" id="tcImpUrl" placeholder="Dán đường dẫn tại đây..." autocomplete="off" spellcheck="false">
            </div>
            <span class="tc-hint">Lưu ý: Sheet của bạn phải ở chế độ công khai hoặc chia sẻ quyền xem cho hệ thống.</span>
          </div>
          <div class="mfield row2">
            <div>
              <label>Chọn Sheet</label>
              <div class="tc-iwrap trailing">
                <select id="tcImpSheet"><option value="">Chọn một trang...</option></select>
                <span class="trail material-symbols-rounded mi-sm">expand_more</span>
              </div>
            </div>
            <div>
              <label>Chọn Folder Test Case</label>
              <div class="tc-iwrap trailing">
                <select id="tcImpFolder"><option value="">Chọn thư mục...</option></select>
                <span class="trail material-symbols-rounded mi-sm">folder_open</span>
              </div>
            </div>
          </div>
          <div class="tc-infobox">
            <span class="material-symbols-rounded">info</span>
            <span><b>Định dạng cột bắt buộc</b>Sheet cần có các tiêu đề: ID, Test Item, Pre-Condition, Step, Expected Output, Priority.</span>
          </div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn-ghost" onclick="tcCloseImport()">Hủy</button>
          <button type="button" class="btn btn-primary" id="tcImpSubmit">
            <span class="material-symbols-rounded mi-sm">download</span> Tiến hành Nhập</button>
        </div>
      </div>
    </div>
    """


def _link_modal():
    """Modal liên kết bộ test case ↔ task Jira (#155) — type-ahead /global-search."""
    return """
    <div class="overlay" id="tcLinkOverlay" onclick="if(event.target===this)tcCloseLink()">
      <div class="modal" style="width:480px">
        <div class="modal-head">
          <span class="material-symbols-rounded">link</span>
          <h3>Liên kết bộ test case với Task</h3>
          <button type="button" class="x material-symbols-rounded" onclick="tcCloseLink()">close</button>
        </div>
        <div class="modal-body">
          <div class="mfield">
            <label>Bộ test case</label>
            <div class="tc-link-folder" id="tcLinkFolderName">—</div>
          </div>
          <div class="mfield">
            <label>Tìm task Jira</label>
            <div class="tc-iwrap">
              <span class="lead material-symbols-rounded mi-sm">search</span>
              <input type="text" id="tcLinkSearch" placeholder="Gõ key / số / tóm tắt task..." autocomplete="off" spellcheck="false">
            </div>
            <div class="tc-link-results" id="tcLinkResults"></div>
          </div>
          <div class="mfield">
            <label>Đã liên kết</label>
            <div class="tc-link-chips" id="tcLinkChips"></div>
          </div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn-ghost" onclick="tcCloseLink()">Đóng</button>
        </div>
      </div>
    </div>
    """


def render_testcase_v2(data=None, editable=True, links=None, user=None, activities=None):
    """Khung trang /test-cases. `data` = {folders:[...], cases:[...]}.
    `links` = {folderId: {tasks:[...]}} link bộ ↔ task Jira (#155)."""
    if activities is None:
        activities = []
    if data is None:
        data = {}
    if links is None:
        links = {}
    folders = data.get('folders') or []
    cases = data.get('cases') or []

    import_btn = ('<button class="btn-pri" id="tcImportBtn">'
                  '<span class="material-symbols-rounded mi-sm">upload</span> Import</button>'
                  ) if editable else ''
    repo_add = ('<button class="tc-repo-add" id="tcAddFolder" title="Thêm bộ / folder">'
                '<span class="material-symbols-rounded">create_new_folder</span></button>'
                ) if editable else ''
    ro_note = ('' if editable else
               '<div class="tc-repo-ro">👁 Chỉ xem — chỉ quản lý mới Import/sửa được.</div>')

    content_inner = f"""
    <div class="tc-shell">

      <!-- Repository panel: cây bộ / folder test case (folders nạp bởi controller #tcData) -->
      <aside class="tc-repo">
        <div class="tc-repo-head"><h3>Repository</h3>{repo_add}</div>
        {ro_note}
        <div class="tc-tree" id="tcTree"><!-- JS render --></div>
      </aside>

      <!-- Khu nội dung chính -->
      <div class="tc-main">
        <div class="page-head">
          <h2 class="page-title">Quản lý Test Case</h2>
          {import_btn}
        </div>

        <!-- Liên kết task Jira theo bộ (#155) — JS render theo folder đang chọn -->
        <div class="tc-linkbar" id="tcLinkBar" style="display:none"><!-- JS render --></div>

        <!-- Metric cards (#153) — JS tính từ cases hiện hành -->
        <div class="tc-metrics" id="tcMetrics"><!-- JS render --></div>

        <!-- Biểu đồ số liệu (#153): donut theo trạng thái + bar theo bộ. Vanilla SVG. -->
        <div class="tc-charts" id="tcCharts"><!-- JS render --></div>

        <!-- Bảng duyệt (#155/#156) -->
        <div class="card">
          <table class="tc-table">
            <colgroup>
              <col style="width:104px"><col style="width:16%"><col style="width:19%">
              <col style="width:22%"><col style="width:22%"><col style="width:136px"><col style="width:96px">
            </colgroup>
            <thead><tr>
              <th>ID</th><th>Test Item</th><th>Pre-Condition</th><th>Step</th>
              <th>Expected Output</th><th>Priority</th><th>Result</th>
            </tr></thead>
            <tbody id="tcBody"><!-- JS render --></tbody>
          </table>
          <div class="pager" id="tcPager" style="display:none">
            <span class="pager-summary" id="tcPagerInfo"></span>
            <div class="pager-nav" id="tcPagerNav"></div>
          </div>
        </div>
      </div>
    </div>

    {_import_modal()}

    {_link_modal()}

    <!-- Modal tạo thư mục/bộ (lưu thật nối ở #152) -->
    <div class="overlay" id="tcFolderOverlay" onclick="if(event.target===this)tcCloseFolder()">
      <div class="modal" style="width:420px">
        <div class="modal-head">
          <span class="material-symbols-rounded">create_new_folder</span>
          <h3>Thêm bộ / thư mục</h3>
          <button type="button" class="x material-symbols-rounded" onclick="tcCloseFolder()">close</button>
        </div>
        <div class="modal-body">
          <div class="mfield"><label>Tên thư mục</label>
            <input type="text" id="tcFolderName" placeholder="VD: Đối Soát B2B" autocomplete="off"></div>
        </div>
        <div class="modal-foot">
          <button type="button" class="btn btn-ghost" onclick="tcCloseFolder()">Hủy</button>
          <button type="button" class="btn btn-primary" id="tcFolderSave">Tạo</button>
        </div>
      </div>
    </div>

    <!-- Drawer chi tiết test case (riêng với drawer task #drawer ở shell) -->
    <div class="drawer-ov" id="tcDrawerOv"></div>
    <aside class="drawer" id="tcDrawer">
      <div class="drawer-head"><span class="tc-id" id="tcdKey"></span>
        <button class="x material-symbols-rounded" id="tcdClose">close</button></div>
      <div class="drawer-body" id="tcdBody"></div>
    </aside>
    """

    content_inner += f"""
    <script>window.QA_TC_EDITABLE={"true" if editable else "false"};</script>
    """
    content_inner += _json_script('tcData', {'folders': folders, 'cases': cases})
    content_inner += _json_script('tcLinks', links)

    return _document_v2(content_inner, 'testcases', user, activities,
                        title='Quản lý Test Case — QA Workspace')
