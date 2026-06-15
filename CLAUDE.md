# CLAUDE.md

Context for Claude Code khi làm việc trên project này.

## Project Purpose

Custom HTML dashboard cho team QA Bảo Kim, pull data live từ Jira qua REST API. Thay thế cho Jira native dashboard (xấu, buggy, không merge cell được, không có conditional formatting).

**User là Acting QA Manager**, đang quản lý 5 QA trong thời gian QA Manager (Hiền) maternity leave. Dashboard này phục vụ briefing hàng ngày + acting management.

## Tech Stack

- Python 3.8+ (walrus operator dùng được)
- External deps: `requests` + `cryptography` (Fernet — mã hoá PAT cá nhân at-rest, thêm 2026-06-08, xem Decision #20). KHÔNG còn "chỉ 1 dep". Vẫn giữ nguyên tắc tối thiểu — KHÔNG thêm Flask/web-framework.
- Local HTTP server: `http.server` stdlib (KHÔNG Flask — quyết định giữ deps tối thiểu)
- Server-side render HTML với string templates
- **Vanilla JS, KHÔNG framework** (React/Vue/Svelte). JS/CSS chính: `app_v2.js`/`styles_v2.css` (UI Stitch sidebar — Decision #19), đọc per-render. UI cũ topnav đã GỠ (cleanup #43): `app.js` đã XOÁ; chỉ còn `styles.css` (nạp bởi `render_error_page` qua `load_css`). `load_*()` inline vào `<script>`/`<style>` lúc render (sửa F5 thấy ngay, output tự chứa).
- State persistence: file JSON local (`.last_seen.json` cho NEW badge) + **Jira user property làm kho sync chéo máy** (roadmap/docs/dismiss/PAT/custom-status — xem Decision #14, #20, #21)

## Architecture

```
[Browser] ←HTTP→ [Python qa_dashboard.py] ←REST API+PAT→ [Jira Bảo Kim]
                 (localhost:8080)                         (jira.baokim.vn:8443)
                       ↓
                .last_seen.json (track new tasks between refreshes)
```

- F5 trong browser = pull fresh Jira data
- Refresh thủ công (user explicitly chose this over auto-refresh 15min)
- Mỗi lần refresh: compare current task keys vs `.last_seen.json` → diff = highlight NEW badge
- First run: skip highlight (avoid all-NEW noise), save baseline

## Domain Context — Jira Bảo Kim

### Instance
- URL: `https://jira.baokim.vn:8443`
- Version: Data Center 10.7.3 (NOT Cloud, NOT Server)
- Auth: PAT via `Authorization: Bearer <token>` header (DC 10.x convention)
- REST API: `/rest/api/2/search`

### Workflow statuses (CHÍNH XÁC theo case + spacing)
- `TO DO` (caps + space — không phải "To Do" hay "Todo")
- `In Progress`
- `PENDING` (all caps)
- `DONE` (all caps)
- `CANCELLED`

### Status categories (dùng cái này để filter, an toàn hơn status name)
- `new` → tương đương TO DO
- `indeterminate` → In Progress, PENDING
- `done` → DONE, CANCELLED

### QA team (5 người + 1 manager)

| Username | Display name | Role |
|---|---|---|
| `quangbm` | Quang | QA |
| `nhungnh` | Nhung | QA |
| `phuongct` | Phương | QA |
| `tholt` | Thơ | QA |
| `thanhht1` | Thành | QA (acting manager) |
| `hiennt19` | Hiền | QA Manager (maternity leave) |

Hiền THƯỜNG là reporter trong các task QA team được giao — vì cô tạo task rồi assign cho team.

### Project keys (QA team hiện đang làm)
- `PSIT1H26`, `DA51H26`, `DA61H26`, `DA2B` (và có thể thêm)
- Không hardcode project list — filter theo `assignee` an toàn hơn

### Task summary convention
- Bảo Kim format: `[QA] <description>` cho task QA
- Test case format (xlsx): 5 cột — ID | Test Item | Pre-Condition | Step | Expected Output

## Key Decisions & Why

### 1. http.server stdlib thay vì Flask
- Lý do: giảm deps, user không phải install nhiều thứ
- Trade-off: ít feature (no auto-reload, no routing decorator) — chấp nhận
- KHÔNG đề xuất chuyển sang Flask/FastAPI trừ khi có feature thật sự cần

### 2. Bearer auth, KHÔNG Basic auth
- Jira DC 10.x dùng PAT với `Authorization: Bearer <token>`
- KHÔNG dùng `email:api_token` Base64 (đó là Jira Cloud convention)
- KHÔNG dùng cookie auth

### 3. Auto-refresh 15 phút (default ON, có toggle pause) + Activity notification
- Ban đầu chọn manual; 2026-06-04 user đổi ý → bật auto-refresh 15p
- Implement bằng JS `setTimeout(location.reload, 15*60*1000)`, KHÔNG dùng `<meta refresh>` (cần pause được)
- Toggle "Auto 15p: ON/OFF" ở header, nhớ qua localStorage `qa-autorefresh` (default ON)
- Vì auto reload phá trạng thái UI (expand/pagination), Activity Stream chuyển sang **notification**: `pending` lưu server-side, tích luỹ qua mỗi refresh, KHÔNG reset — chỉ clear khi bấm "Đã đọc" (POST `/clear-activities`)
- Mỗi refresh = 5 Jira call (3 search active/new24/done_week + 2 count created/resolved week). 15p = ~20 call/giờ/tab — chấp nhận được

### 4. JQL dùng `statusCategory != Done` thay vì `status != "DONE"` (cho bucket active)
- An toàn hơn nếu workflow thêm status mới (vd: ON HOLD, BLOCKED)
- DONE + CANCELLED đều thuộc category Done → 1 filter ăn cả 2

### 4b. Bucket `done_week` dùng `status CHANGED TO "DONE" AFTER -3d`, KHÔNG dùng `resolved`
- Workflow Bảo Kim thường KHÔNG set resolution → `resolutiondate` null → `resolved >= ...` trả RỖNG (bug cũ)
- `status CHANGED TO "DONE"` bắt theo lịch sử chuyển trạng thái, không phụ thuộc resolution
- Window = 3 ngày (`AFTER -3d`), order by `updated DESC`. Tên hiển thị: "Done (3 ngày)"
- Cột thời gian hiển thị `resolutiondate`, fallback `updated` nếu null
- KHÔNG đổi lại sang `resolved`/`startOfWeek()` trừ khi user yêu cầu

### 5. Workload threshold: ≥15 / 5–14 / ≤4
- Định nghĩa: QUÁ TẢI / OK / NHẸ
- Dựa trên xlsx tracker ban đầu của user (`jira_tasks_tracker.xlsx`)
- KHÔNG đổi threshold trừ khi user yêu cầu trực tiếp

### 5b. Metric quản lý: "Kẹt ≥5 ngày" + "Vào/Ra tuần"
- **Kẹt** (`is_stuck`): task in-flight (KHÔNG phải TO DO) mà `updated` ≥ `STUCK_DAYS` (=5) ngày → đang stalled/blocked. Hiển thị KPI card + cột "Xd kẹt" đỏ trong workload khi expand. KHÔNG đổi 5 trừ khi user yêu cầu.
- **Vào/Ra tuần**: `created >= startOfWeek()` vs `status CHANGED TO "DONE" AFTER startOfWeek()`. Vào > Ra → card đỏ (backlog phình). Dùng `jira_count` (maxResults=0, chỉ lấy `total`, không kéo issue).
- Hệ quả: fetch_all giờ **5 Jira call** (3 search + 2 count) thay vì 3.

### 6. Track theo `assignee` (không phải `reporter`) cho workload
- Câu hỏi đúng: "task ai đang phải làm" → assignee
- Câu hỏi cho New 24h: "ai chủ động tạo task" → reporter (5 QA, NOT including Hiền vì cô tạo là routine, không reflect proactivity)

### 7. State file `.last_seen.json` lưu cùng folder script
- Đơn giản, không cần DB
- Reset bằng `rm .last_seen.json`
- Format: `{"snapshot": {key: {...}}, "pending": [...activities chưa đọc...], "keys": [...], "updated": "..."}`
- `snapshot` per key track: status, summary, assignee, type, updated, comments, duedate, priority
- Activity diff bắt MỌI thay đổi: status / assignee (reassign) / duedate / priority / summary (nội dung) / comment mới / tạo mới. **Gom theo task id, mỗi action 1 dòng** (không inline)
- **Tác giả (AI đổi)**: field changes lấy từ Jira changelog (`fetch_change_authors`, 1 call `expand=changelog` CHỈ cho task vừa đổi — nhẹ); comment author từ field `comment.comments[-1]`; created author = reporter. `actor_name()` map QA username → tên ngắn, người khác → displayName
- Migration-safe: field mới thiếu ở snapshot cũ → coi như không đổi (`prev.get(f, cur.get(f))`), tránh báo giả hàng loạt
- `pending` = notification tích luỹ (clear bằng "Đã đọc"); cap 100, sort theo `detected` desc; lưu cả `author`; `keys` legacy
- fields fetch thêm `comment`,`priority`. Mỗi refresh: 5 call + (nếu có task đổi) 1 call changelog. Description KHÔNG track (nặng) → "đổi nội dung" = đổi summary thôi
- Tự migrate: state cũ chỉ có `keys` → lần refresh đầu sau nâng cấp chỉ show "tạo mới", không có false status-change

### 8. Tab "Báo cáo tuần" = đã xoá khỏi dự án (2026-06-08)
- Đã gỡ hoàn toàn route `/report`, `fetch_lines()`, logic render và các file liên quan.

### 8b. Report — "🌳 Tiến độ test theo line dự án" = đã xoá khỏi dự án (2026-06-08)
- Đã gỡ cùng với logic của weekly report.

### 8c. Report — đã GỠ các phần khác
- Đã xoá toàn bộ route và logic.

### 9. Activity Stream — kéo từ Jira changelog + dismiss đồng bộ chéo máy (2026-06-05)
- **Bối cảnh / vì sao đổi**: cũ activity = diff 2 snapshot local trong `.last_seen.json` → đổi device là mất `pending`, miss update. SUPERSEDES mô hình pending tích luỹ ở Decision #3/#7.
- **Nguồn = Jira changelog (source of truth)**: `jira_api.fetch_activity_feed(days=7)` — JQL `(assignee in QA OR reporter in QA) AND updated >= -7d`, `expand=changelog`. Parse `changelog.histories` (item field status/assignee/duedate/priority/summary, lọc `created >= now-7d`) + comment + sự kiện created. Mỗi activity có **`id` ổn định** (`key#histId#field` / `key#cmt#id` / `key#created`) → máy nào cũng tính ra y hệt. Device-independent: mở lên thấy đủ 7 ngày, không cần state local.
- **Comment có snippet nội dung**: activity kind=comment kèm `body` (rút gọn ~140 ký tự qua `_comment_snippet`, full ở `title` hover) — đỡ phải mở issue để đọc. Render: `act-cmt-body`.
- **Dismiss đồng bộ = Jira user property** (`qa-dashboard-read`, đã verify PAT ghi được): `load_dismissed()`/`save_dismissed()`/`dismiss_activities(ids)` lưu `{activity_id: dismissed_at}` vào property của user (`/rest/api/2/user/properties`). Prune entry > 14 ngày. 2 máy cùng đọc 1 property → dismiss ở máy A, máy B thấy mất ngay.
- **Wiring**: `do_GET /` = `fetch_all()` + `fetch_activity_feed()` + `load_dismissed()`, lọc `unread = feed - dismissed`. POST `/dismiss` `{ids:[...]}` (thay `/clear-activities` cũ). Nút "✓ Đã đọc hết" gom mọi `data-actid` đang hiện; nút ✕ mỗi dòng bỏ 1 mục (`dismissActivity`/`postDismiss` trong app.js).
- **Paging activity**: `setupActListPaging` (app.js) phân trang **5 issue (act-group)/trang** trên `.act-list`, dùng style `.pager` sẵn có (KHÁC `setupPaginate` vốn chỉ chạy cho table rows). `measure()` đo trang cao nhất → khoá `min-height` cho `.act-list` để pager Prev/Next KHÔNG nhảy khi đổi trang (mỗi page số dòng khác nhau). Dismiss xoá group → `list._pgRender()` đo lại + vẽ lại. Render tất cả group (bỏ cap 60 cũ).
- **`.last_seen.json` giờ CHỈ còn** giữ snapshot cho NEW badge (`new_keys`) — `_build_view` đơn giản hoá, không còn `compute_activities`/`_attach_authors`/pending. `state.compute_activities`/`clear_pending` thành dead code (giữ lại, không xoá).
- **Calls thêm ở `/`**: +1 search (`expand=changelog`, nặng hơn, cap 120 issue) +1 GET property (+1 GET /myself lần đầu, memoized). Window/cap đổi trong `ACTIVITY_DAYS` (qa_dashboard) / params `fetch_activity_feed`.
- **Giới hạn**: cửa sổ 7 ngày cố định (issue im >7d không lên feed); cap 120 issue đổi/7d; comment cũ trong window có thể sót nếu issue quá nhiều comment.

### 10. Filter theo người (assignee/reporter) — client-side, dashboard `/` (2026-06-05)
- **Bối cảnh**: cần nhìn nhanh "1 QA đang ôm những gì" mà không phải mở Jira. Là "Likely Next #3", làm **client-side JS** (không reload, không thêm Jira call).
- **Thanh filter** (`render_filterbar`) đặt ngay trên grid 2 cột: dropdown chọn người (theo `USERS`) + nút "Bỏ lọc". **KHÔNG có toggle mode** — luôn lọc khớp **assignee HOẶC reporter** (user yêu cầu bỏ phân biệt 2026-06-05). Nhớ qua `localStorage qa-filter` (`{user}`) → **sống sót auto-reload 15p**.
- **Mấu chốt = pagination filter-aware**: `setupPaginate` (app.js) cũ cắt trang theo TOÀN BỘ `tbody>tr`. Nếu chỉ `display:none` dòng không khớp thì pager đếm sai → trang trống. Đã refactor: mỗi `render()` lọc `allRows.filter(rowMatch)` rồi mới phân trang → số trang/"x/y" tính trên tập đã lọc. `box._pgRefilter()` để controller gọi lại khi đổi filter. Dòng KHÔNG mang `data-assignee/reporter` → luôn hiện.
- **Data nguồn**: mỗi `<tr>` người (`_attn_row`, new24, done) mang `data-assignee`/`data-reporter` = **username** (qua `_person_attrs`); workload `<details>` mang `data-user` (workload luôn theo assignee). `rowMatch` = `assignee===user || reporter===user`.
- **Badge count theo filter** (`updateCounts`): header `.count` (Done/New24), `.tab-count` (Attention, tính cả tab ẩn), Workload "N active" đều cập nhật theo số đã lọc. **Phải loại `.pager-filler`** khi đếm (không có data-attr → `rowMatch` trả true → phồng số).
- **Phạm vi lọc**: Workload (thu về đúng người, auto-expand) + Attention tabs + New24 + Done + **donut "issue per status"**. **Activity stream + donut "per assignee" KHÔNG lọc** (số tổng) — chủ ý.
- **Donut status filter-aware** (2026-06-05): data active (`{s,a,r}` + jiraUrl + base + palette) nhúng `<script id="qaChartData">` ở `render_charts`; card status mang `data-chart="status"`. JS `updateStatusDonut()` đếm lại **CHỈ theo assignee** (`it.a===user`, KHÔNG reporter — donut status = việc đang nằm trên tay người đó, user chốt 2026-06-05) rồi `_buildDonut()` vẽ lại SVG + legend (link Jira regenerate kèm `AND assignee = user`). Đây là điểm **lệch luật có chủ đích** so với bảng/filter chung (vốn assignee||reporter). Donut "per assignee" giữ `data-chart="assignee"`, không đụng.
- **KHÔNG gọi `layout()` khi filter**: `layout()` resize donut theo chiều cao cột → filter làm block nhảy size (user phàn nàn 2026-06-05). Bỏ gọi trong `apply()` → donut giữ size set lúc load, chỉ đổi nội dung. `layout()` vẫn chạy ở `window.load`/`resize`.
- `@media print` ẩn `.filterbar`. KHÔNG đụng `/report`.

### 11. Tab "Tài liệu" (`/docs`) — cây thư mục + link Google Drive (2026-06-05)
- **Bối cảnh / quyết định gốc**: user muốn workspace lưu tài liệu training. Chốt **KHÔNG build editor Office** (WYSIWYG .docx/.xlsx/.pptx cần OnlyOffice/Collabora chạy Docker → phá kiến trúc minimal-deps/local). Thay vào đó: **edit thật để Google lo**, workspace chỉ là **index + mở nhanh**. Luồng: user up file lên Drive → copy link → dán vào `/docs` → click mở tab mới view/edit ở Google. Zero dep, không Google API/OAuth (tránh thêm credential + OPSEC surface).
- **Route riêng** `/docs` (top nav tab thứ 3, cạnh Tổng quan / Báo cáo tuần). **KHÔNG gọi Jira** — chỉ đọc/ghi JSON local. Dùng shell chung `_document()`.
- **Data model** (`.docs_config.json`): cây = list node đệ quy. Node = `folder {type,name,children[]}` hoặc `link {type,title,url}`. Folder lồng nhau tuỳ ý. Validate shape khi lưu (`docs.valid_tree`, cap `MAX_NODES=2000` chống payload rác/đệ quy vô hạn).
- **Module `docs.py`** (layer cạnh `pic.py`): `DOCS_DEFAULT`, `load_docs`/`save_docs`, `valid_tree`. Pattern y hệt pic.
- **Render** (`render_docs_page` + `_doc_node_html` đệ quy): folder = `<details open>` (collapse được) với tên `contenteditable` + nút ＋📁/＋🔗/×; link = **`<a class="doc-title" target=_blank>`** (bấm tên = mở tab Google) + url chip + nút ✎. Templates `docFolderTpl`/`docLinkTpl` để JS clone.
- **Sửa link = popup, KHÔNG inline** (user yêu cầu 2026-06-05): bấm **tên tài liệu → mở tab mới** edit ở Google; bấm **✎ → popup** (`#docmOverlay`) sửa tên + link + nút Xoá. `applyLink()` ghi cả `textContent`/`href`/`data-url`/url-chip. Add link mới → tạo node rỗng + mở popup luôn; Huỷ khi node mới chưa có url → tự xoá node rỗng. Folder vẫn rename inline (`contenteditable`).
- **JS** (app.js, IIFE guard `#docTree`): add thư mục gốc/con, add link (popup), sửa link (popup), xoá folder (confirm nếu có con), rename folder inline → **auto-save** debounce 600ms POST `/save-docs`. `collect()` đệ quy DOM→JSON (dùng `:scope >`). Mở link chỉ khi `^https?://` (chặn `javascript:`).
- **Backend**: GET `/docs` → `render_docs_page(load_docs())`; POST `/save-docs` (cap 1MB) → `valid_tree` rồi `save_docs`. `.docs_config.json` đã vào `.gitignore`.
- **Giới hạn**: copy-link thủ công (đánh đổi để zero-dep); view/edit-được hay không do **quyền share Google** quyết, workspace không can thiệp; file KHÔNG ở Google thì up Drive trước (hoặc để dành file-vault sau).

### 12. Tab "Roadmap" (`/roadmap`) — giai đoạn theo mốc thời gian + tracking (2026-06-05)
- **Bối cảnh / quyết định gốc**: user muốn làm roadmap cho team ngay trên workspace, theo dõi + chỉnh tay. Chốt **KHÔNG suy từ Jira** (team làm tầng sub-task, fixVersion/epic không chắc nhất quán → roadmap auto sẽ vỡ). Tự author + edit, lưu local JSON, giống pattern docs/PIC. Bố cục **theo mốc thời gian** (user chọn).
- **Route riêng** `/roadmap` (top nav tab, cạnh Báo cáo tuần / Tài liệu). KHÔNG gọi Jira. Shell chung `_document()`.
- **Data model** (`.roadmap_config.json`): list giai đoạn `{phase: str, items: [item]}`. item = `{title, status, pic, progress(int 0-100), url}`. Status ∈ {planned, in_progress, done, blocked} (lenient: lưu str bất kỳ, CSS `rm-st-<value>`). Validate `valid_roadmap` (cap `MAX_PHASES=100`, `MAX_ITEMS=500`, progress 0-100).
- **Module `roadmap.py`**: `RM_STATUSES`, `RM_PEOPLE`(=PIC_PEOPLE), `ROADMAP_DEFAULT`, `load/save/valid_roadmap`.
- **Render** (`render_roadmap_page` + `_rm_phase_html`/`_rm_item_html`): giai đoạn = `<details open>` collapse, tên `contenteditable`, header có thanh tóm tắt **"x/y xong"** (đếm status=done) + bar. Mỗi mục 1 dòng: select status (badge màu) + tiêu đề `contenteditable` + select PIC + ô % + bar + ↗ mở link + 🔗 sửa link + × xoá. Templates `rmPhaseTpl`/`rmItemTpl`.
- **JS** (app.js, IIFE guard `#rmList`): add giai đoạn/mục, xoá (confirm nếu giai đoạn có mục), đổi status (cập nhật class badge + tóm tắt), đổi PIC/%, sửa link (prompt), rename inline → **auto-save** debounce 600ms POST `/save-roadmap`. `%` đổi → cập nhật bar live. Link chỉ mở khi `^https?://`.
- **Backend**: GET `/roadmap` → `render_roadmap_page(load_roadmap())`; POST `/save-roadmap` (cap 1MB, `valid_roadmap`). `.roadmap_config.json` vào `.gitignore`.
- **Chưa làm (v2 nếu cần)**: reorder kéo-thả mục/giai đoạn; mốc hạn (target date) per-mục; gắn nhiều link; group theo theme thay vì thời gian.

### 12. Tab "Roadmap" (`/roadmap`) — giai đoạn › mục › sub-task + cảnh báo hạn (2026-06-05)
- **Bối cảnh / quyết định gốc**: user muốn roadmap cho team ngay trên workspace, tự theo dõi + chỉnh tay. Chốt **KHÔNG suy từ Jira** (team làm tầng sub-task, fixVersion/epic không chắc nhất quán). Tự author + edit, lưu local JSON, pattern docs/PIC. Bố cục **theo mốc thời gian** (user chọn).
- **Route riêng** `/roadmap` (top nav, cạnh Báo cáo tuần / Tài liệu). KHÔNG gọi Jira. Shell chung `_document()`.
- **Cây 3 tầng**: giai đoạn (`phase`) › mục (`item`) › **sub-task** (`subtasks[]`). Data model (`.roadmap_config.json`): list `{phase, items:[item]}`; node (item/sub) = `{title, status, progress(int 0-100), due('YYYY-MM-DD'|'')}`; item thêm `subtasks:[leaf]`. Validate `valid_roadmap` (cap `MAX_PHASES=100`, `MAX_ITEMS=1000`). Status ∈ {planned, in_progress, done, blocked} (lenient, CSS `rm-st-<value>`).
- **Module `roadmap.py`**: `RM_STATUSES`, `ROADMAP_DEFAULT`, `load/save/valid_roadmap`, `due_alerts(data, within_days=14)`.
- **Edit = popup, KHÔNG inline** (giống docs link, user yêu cầu): **bấm mục có sub-task = xổ cây** (`<details>`); **bấm ✎ = popup** (`#rmmOverlay`) sửa tên/trạng thái/%/hạn + nút Xoá. Phase: ✎ popup chỉ tên + xoá (ẩn field status/%/hạn). Mỗi node mang `data-status`/`data-progress`/`data-due`; `paintNode()` đồng bộ badge/bar/%/due-chip từ data-*; `collect()` đọc data-* + `.rm-title`. **Đã BỎ field PIC + link** (roadmap 1 mình user làm).
- **Due date + cảnh báo**: mỗi node có hạn. `render_roadmap_alerts()` (dashboard `/`) liệt kê node **chưa Done + hạn ≤ 14 ngày** (gồm quá hạn), block riêng "🗺 Roadmap sắp đến hạn" đặt **trên** activity feed — **tách khỏi feed Jira** (user yêu cầu). `render_page(..., roadmap_data=load_roadmap())`.
- **JS** (app.js, IIFE guard `#rmList`): add giai đoạn/mục/sub-task (mở popup ngay), sửa/xoá qua popup, đổi % cập nhật bar live, "x/y xong" đếm item Done → **auto-save** debounce 600ms POST `/save-roadmap`. `e.preventDefault()` trên nút trong `<summary>` để không toggle nhầm.
- **Backend**: GET `/roadmap`; POST `/save-roadmap` (cap 1MB, `valid_roadmap`). `.roadmap_config.json` vào `.gitignore`. Migration-safe: data schema cũ (có `pic`/`url`, thiếu `due`/`subtasks`) vẫn validate + load (field thừa bỏ qua, thiếu → default).
- **% + status mục tự tính từ sub-task** (2026-06-05): mục **có sub-task** → `progress` = **trung bình %** (`_rm_item_progress`), `status` = **suy ra** (`_rm_item_status`): all done→done · có blocked→blocked · có in_progress hoặc vài done→in_progress · else planned (blocked ưu tiên hơn in_progress). Cả 2 ô trong popup **disable** + note "Tự tính theo sub-task". Mục **không sub-task** → sửa tay. JS `recalcItem()` (gồm `deriveStatus()`) chạy khi add/sửa/xoá sub-task → cập nhật `data-status`/`data-progress` + `paintNode` + `updateSummary`.
- **Done → auto 100%** (2026-06-05): node sửa tay (sub-task / mục không sub-task) khi `status='done'` → `progress=100` tự động (live trong popup qua `syncLocks()` + ép lại lúc save). Ô % khóa khi Done (note "Done = 100%").
- **Chưa làm (v2)**: reorder kéo-thả; nhiều tầng sub-task.

### 13. Tăng tốc load: Session keep-alive + call Jira song song (2026-06-05)
- **Bối cảnh**: web load chậm dần. Nguyên nhân = **call Jira REST tuần tự qua mạng**. `/` = `fetch_all` (5 call) + `fetch_activity_feed` (1, nặng vì `expand=changelog`) + `load_dismissed` (1-2) ≈ 7-8 round-trip nối đuôi. Render string thì nhanh — bottleneck là I/O mạng.
- **Fix 1 — `requests.Session` dùng chung** (`jira_api._SESSION`): tái dùng kết nối TCP/TLS (keep-alive) thay vì bắt tay HTTPS mỗi call. Mọi `_SESSION.get/put` thay cho `requests.get/put` (4 chỗ). urllib3 pool thread-safe → share giữa thread OK.
- **Fix 2 — `run_parallel(jobs)`** (`ThreadPoolExecutor`, cap 8 worker): chạy các call **độc lập** đồng thời, re-raise lỗi đầu tiên (RuntimeError) để `do_GET` render trang lỗi như cũ. Áp dụng: (a) trong `fetch_all` — 5 call song song; (b) `/` — `fetch_all` ‖ `feed` ‖ `dismissed`. Thời gian ≈ call chậm nhất thay vì tổng → giảm mạnh.
- **Lồng pool**: `/` outer 3 worker, trong đó `fetch_all` spawn pool 5 → đỉnh ~7-8 request đồng thời tới Jira DC (chấp nhận được). I/O-bound nên GIL không cản.
- **KHÔNG đổi**: server vẫn single-thread (`TCPServer`) cho việc nhận request (tránh race ghi `.last_seen.json`); chỉ song song hoá *call ra Jira* trong 1 request. KHÔNG cache `fetch_all` (giữ "F5 = data tươi"). Nếu cần thêm: cân nhắc `ThreadingHTTPServer` (đa request) nhưng phải xử lý race file state trước.

### 14. Sync roadmap + tài liệu qua Jira property (2026-06-05)
- **Bối cảnh**: roadmap (`.roadmap_config.json`) + tài liệu (`.docs_config.json`) là data **tự soạn, KHÔNG có trên Jira**, lưu local → đổi máy mất sync. Cùng class với dismiss (Decision #9).
- **Sync = Jira user property** (mượn Jira làm kho key-value chung, KHÔNG cần data liên quan Jira): generic `jira_api.load_property(key, default)` / `save_property(key, value)`. `roadmap.py` dùng prop `qa-dashboard-roadmap`, `docs.py` dùng `qa-dashboard-docs`. **Jira = source of truth**, file local = **cache fallback** khi Jira lỗi (`_read_cache`/`_write_cache`). `save_*` chỉ trả `True` khi Jira nhận (raise→False, tránh mất data thầm lặng); `load_*` ưu tiên Jira, hỏng mới đọc cache, cuối cùng DEFAULT.
- **Layering**: `roadmap.py`/`docs.py` giờ import `jira_api` (vẫn không cycle: jira_api chỉ import config+issues). Hệ quả: load roadmap/docs giờ **có gọi Jira** (mỗi `/`, `/roadmap`, `/docs` +1 GET property).
- **Giới hạn sync**: Jira property có giới hạn dung lượng (~32KB) — roadmap/docs vài KB thì ổn, phình to (gần MAX_NODES/MAX_ITEMS) mới lo. Concurrent edit 2 máy = last-write-wins (hợp vì chỉ admin sửa).

### 14b. Login + phân quyền qua Cloudflare Access (2026-06-05)
- **Mô hình**: Cloudflare lo **authenticate** (login + gate domain `@baokim.vn`) ở Zero Trust dashboard — KHÔNG phải code. App chỉ **đọc identity** Cloudflare gắn vào header `Cf-Access-Authenticated-User-Email` rồi phân quyền. App dùng **1 PAT chung** → PAT không phân biệt người, lock CHỈ enforce được bằng header này.
- **Config** (`.env`, đọc ở config.py): `JIRA_ADMIN_EMAIL` (role admin = được edit roadmap/docs; vd `thanhht1@baokim.vn`), `JIRA_ALLOWED_DOMAIN` (vd `baokim.vn`, defense-in-depth ở tầng app). Cả 2 rỗng = không khoá (local dev).
- **Handler** (qa_dashboard): `_user_email()` đọc header; `_domain_ok()` chặn 403 nếu email không thuộc domain (chỉ khi có header + có cấu hình); `_is_admin()` so email với ADMIN_EMAIL; `_user_ctx()=(email,is_admin)` cho nav chip. Local (không header) → mọi check True (chính bạn).
- **Enforce**: `do_GET`/`do_POST` chặn 403 nếu `not _domain_ok()`. POST `/save-roadmap` + `/save-docs` chặn 403 nếu `not _is_admin()`. GET `/roadmap` `/docs` truyền `editable=_is_admin()` → render class `.ro` (CSS ẩn nút edit) + banner "chỉ xem" + JS tắt `contenteditable`. **Server 403 là lock thật, ẩn UI chỉ là UX.**
- **Nav chip**: `render_nav(active, user)` hiện `👤 email + badge Admin/Chỉ xem` (chỉ khi qua Access). Thread `user` qua cả 4 page render fn (KHÔNG dùng global — an toàn nếu sau đổi ThreadingHTTPServer).
- **⚠ An toàn chỉ khi ingress DUY NHẤT là Cloudflare Access** (server bind `127.0.0.1`, chỉ cloudflared với tới). Chạm thẳng port (không qua Access) → không header → bị coi là local/admin. Đây là mô hình **header-trust**; muốn chắc hơn thì verify JWT `Cf-Access-Jwt-Assertion` (cần thêm dep PyJWT+cryptography — CHƯA làm, giữ minimal-deps).
- **Cloudflare runbook** (làm ở Zero Trust dashboard, KHÔNG phải code): tạo Tunnel `cloudflared` trỏ `http://localhost:8080` → tạo Access Application cho hostname → policy Allow `emails ending in @baokim.vn` (OTP/Google) → app tự nhận admin theo `JIRA_ADMIN_EMAIL`.

### 15. Golive: Google OAuth login thay Cloudflare Access (2026-06-06)
- **Bối cảnh / vì sao đổi**: golive trên domain `baokim-qa.com` (mua ở Cloudflare). Tunnel `cloudflared` (→ `127.0.0.1:8080`) chạy OK, nhưng **Cloudflare Access kẹt ở bước Activate Zero Trust Free** — thẻ VN fail "unexpected error processing payment" liên tục. SUPERSEDES Decision #14b (header-trust `Cf-Access-Authenticated-User-Email`).
- **Mô hình mới = OAuth Google ngay trong app** (baokim.vn chạy Google Workspace): app redirect sang Google → nhận email **đã verify** → check `verified_email` + `endswith('@'+ALLOWED_DOMAIN)` → set **session cookie ký HMAC**. Không cần thẻ, không cần Zero Trust, **zero new deps** (stdlib `hmac/hashlib/secrets/http.cookies` + `requests` sẵn có). Chắc hơn header-trust: bỏ điểm yếu "chạm thẳng port = admin".
- **Module `auth.py`** (cùng layer `jira_api`, import `config` + `requests`, không cycle): `login_url`/`exchange_code`/`email_allowed` (OAuth), `make_session_token`/`email_from_session` (cookie HMAC `b64(json).sig`, TTL 12h), `make_state_token`/`state_valid` (CSRF, TTL 10p). KHÔNG log token. Dùng userinfo endpoint (`/oauth2/v2/userinfo`) → KHÔNG cần verify JWT crypto.
- **Config** (`.env`): `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` + `SESSION_SECRET` (bắt buộc khi bật, random `token_urlsafe(48)`). `AUTH_ENABLED = bool(CLIENT_ID and SECRET)`. **Bỏ trống cả hai = local dev**: không bắt login, mọi request = admin (giữ nguyên flow cũ). `config.py` exit nếu AUTH bật mà thiếu SESSION_SECRET.
- **Handler** (qa_dashboard): routes public `/login` (→ Google), `/oauth/callback` (đổi code → verify domain → set session cookie → `/`), `/logout`. `_user_email()` đọc session cookie TRƯỚC, fallback header CF (vẫn để tương thích). `_authed()` gate mọi route khác → chưa login = 302 `/login`. `do_POST` chặn 403 nếu `not _authed()`. `_is_admin()`: AUTH bật mà chưa login → KHÔNG admin (khác local dev). `_base_url()` dựng từ `Host` + `X-Forwarded-Proto` (cloudflared set https) để ra `redirect_uri` đúng cho cả prod lẫn localhost.
- **Cookie**: `HttpOnly; SameSite=Lax; Secure` (khi https); session `qa_session` Max-Age 12h, state `qa_oauth_state` Max-Age 10p (clear sau callback).
- **Google Cloud setup** (user, 1 lần): Credentials → Create OAuth client ID → Web application → Authorized redirect URIs = `https://baokim-qa.com/oauth/callback` + `http://localhost:8080/oauth/callback`. Consent screen nên đặt **User Type = Internal** (chỉ @baokim.vn) = thêm lớp gate ở Google.
- **Giới hạn**: domain gate phụ thuộc `verified_email=true` từ Google (luôn true với Workspace). Session 12h cố định. Golive vẫn cần `cloudflared` + python app cùng chạy (auto-start launchd — CHƯA làm). Cloudflare Access có thể quay lại nếu sau hết kẹt thẻ, nhưng không cần nữa.

### 16. Dashboard `/` — lens cá nhân cho QA non-admin (2026-06-06)
- **Bối cảnh**: dashboard `/` vốn là lens quản lý (workload matrix, donut per-assignee, KPI Vào/Ra, New24-by-reporter) = các widget **so sánh giữa người**. Khi QA non-admin đăng nhập, data đã auto-scope về chính họ (`do_GET` scope=username, Decision #10/#15) → các widget so-sánh thu về 1 người = vô nghĩa/thừa. User muốn QA chỉ thấy "to-do của tôi".
- **Tách nhánh trong `render_page`** theo `is_admin` (KHÔNG route mới): admin/local → layout cũ y nguyên; non-admin → `render_personal()`. Header h1 đổi "QA Team Dashboard" ↔ "QA Dashboard — Việc của tôi".
- **`render_personal()`** dựng: `render_kpis_personal` (5 KPI cá nhân: Active của tôi / Overdue / Kẹt / Due tuần / Done — bỏ Vào/Ra + New24) → `eqrow-3` (⚠ Overdue · 📅 Due tuần · ⏳ Kẹt, mỗi cái 1 `.section` riêng thay vì tabbed) → `eqrow-2` (🔵 Đang làm | 🔔 Hoạt động) → `eqrow-2` (📋 TO DO của tôi | ✅ Done). **Đang làm** = In Progress + PENDING (lossless), **TO DO** = phần còn lại. Bảng KHÔNG cột Assignee (đều là mình). Sort mọi bảng theo due date (overdue→gần→none).
- **Bỏ với QA**: Workload Matrix, donut (cả status & assignee), KPI Vào/Ra, New24-by-reporter, filterbar, roadmap-alerts (đã ẩn từ trước).
- **CSS `.eqrow`** (styles.css): grid `align-items:stretch` + `.section{display:flex;flex-direction:column}` + `.pager{margin-top:auto}` → các block trong hàng cao bằng nhau, pager dính đáy, KHÔNG dùng `table{flex:1}` (sẽ giãn row — đã dính bug). Accent viền trái `.prio-overdue/dueweek/stuck`.
- **Pagination**: mọi block bảng mang `data-paginate="5"` → `setupPaginate` (app.js) sẵn có lo (filler row giữ chiều cao 5 dòng dù trang cuối thiếu); activity dùng `setupActListPaging` sẵn có. **KHÔNG viết JS mới**. `rowMatch` trả true khi không filter, `layout()` bail khi không có `.grid-2col` → cả hai không vướng nhánh QA.
- **Mockup**: `example.html` (link `styles.css` thật) — preview lens này trước khi code. Giữ lại để tham chiếu UI.
- **Giới hạn**: phân biệt admin/QA dựa `is_admin` từ `_user_ctx()` (Decision #15). Local dev (không login) = admin → luôn thấy lens quản lý; muốn xem thử lens QA phải login bằng tài khoản QA hoặc test qua `render_page(..., user=(email, False))`.

### 17. Tab "Việc của tôi" (`/my-work`) — lens cá nhân cho ADMIN (2026-06-08)
- **Bối cảnh**: admin xem `/` là lens quản lý toàn team (Decision #16). Nhưng admin (Thành, acting manager) cũng là 1 QA có task riêng → cần xem việc của CHÍNH MÌNH mà không lẫn cả team. QA non-admin đã có sẵn (dashboard `/` auto-scope), thiếu mỗi admin → thêm route riêng.
- **Route `/my-work`** (admin-only; non-admin → 302 `/` vì `/` của họ đã là lens cá nhân rồi). Fetch giống `/` nhưng **scope = username của chính admin** (`_self_username()`: `username_from_email(login) or username_from_email(ADMIN_EMAIL) or SELF_USER`). Local dev (chưa login) fallback `SELF_USER` (config `JIRA_SELF_USER`, default `thanhht1`).
- **UI = HỆT QA member** (user chốt 2026-06-08): tái dùng thẳng `render_qa_v2()` (sidebar Stitch v2 — bảng + tabs + KPI + drawer), KHÔNG dùng topnav cũ/`render_personal`. `render_qa_v2` thêm param `nav_active='dashboard'` → `/my-work` truyền `'mywork'` để sidebar highlight đúng tab; mọi thứ khác y chang. (`render_personal` lại thành dead code như sau Decision #16.)
- **Baseline NEW badge** (`_build_view`) dùng scope_key = `thanhht1`, tách khỏi `__all__` (dashboard team) → không giẫm baseline nhau.
- **Nav**: tab "Việc của tôi" thêm vào `render_sidebar_v2` (sidebar v2) **và** `render_nav` (topnav cũ — admin `/`, `/docs` vẫn dùng), CHỈ hiện khi `is_admin`. Active key = `mywork`.
- **Giới hạn**: scope theo `SELF_USER` config nên nếu admin đổi người thì phải sửa `.env`.

### 18. Drawer detail dùng chung ở shell + notification mở detail mọi tab (2026-06-09)
- **Bối cảnh**: drawer detail (panel chi tiết task + comment) cũ nằm TRONG closure `#rows` (app_v2.js), nên CHỈ có ở trang có bảng task (Dashboard, Việc của tôi). Bấm notification ở Roadmap/Tài liệu → `window.__openDetail` undefined → chỉ toast/nhảy Jira, KHÔNG mở được detail tại chỗ. User muốn mở drawer ngay ở mọi tab cho tiện.
- **DOM drawer chuyển lên shell** `_document_v2` (render.py): `#drawerOv` + `#drawer` giờ ở shell → MỌI trang v2 có sẵn. Bỏ DOM trùng khỏi `render_admin_v2` + `render_qa_v2` (giữ `#smenu` — status menu vẫn riêng của trang bảng). Tránh duplicate ID.
- **2 tầng drawer** (app_v2.js):
  - Dashboard / Việc của tôi: drawer "đầy đủ" trong closure `#rows` (có nhãn nội bộ + cờ Overdue/Kẹt lấy từ TASKS). Set `window.__openDetail` trước.
  - **Module fallback dùng chung** (đặt SAU closure `#rows`): guard `#drawer` tồn tại **và** `window.__openDetail` CHƯA set → chỉ chạy ở Roadmap/Tài liệu. Nhận `key` → fetch `/issue-comments` → `synth()` dựng task tối giản (key/status/assignee/hạn/mô tả/comment + gửi comment) → render. Đóng bằng ×/click nền/Esc. KHÔNG đụng trang có bảng (đã return sớm) nên không double-bind `dt-send`.
- **`fetch_issue_detail` (jira_api) trả thêm `status`/`assignee`/`duedate`** — để dựng được drawer cho task KHÔNG nằm trong bucket nào (vd CANCELLED: không thuộc `active` vì statusCategory=Done, không thuộc `done_week` vì chỉ bắt CHANGED TO "DONE"). Trước đó `openDetail` gặp task ngoài bucket → `taskByKey` undefined → bấm noti CANCELLED không mở gì (bug đã fix: cache vào `EXTRA{}` + synthTask trong cả 2 closure `#rows`).
- **`window.__jiraBase` nhúng ở shell** `_document_v2` (từ `JIRA_URL`) cho MỌI trang v2 — trước chỉ set trong closure `#rows` từ `TASKS[0].jiraUrl`, nên Roadmap/Tài liệu thiếu → click noti chết. Closure `#rows` khi TASKS rỗng giờ fallback về global thay vì ép `''`.
- **Bảng admin `/` (render_admin_v2) tách cột Date → Due Date + Updated**, sort theo Updated giảm dần (mới nhất trước). **New Tasks & TO DO: cột Updated hiển thị Created Date** (`upd_src = i_created if (isNew or st=='TO DO') else i_updated`, cắt `[:10]`). app_v2.js admin branch: `filtered()` thêm `.sort` theo `updated`, row thêm cell, filler/colspan 5→6.

### 19. UI v2 "Stitch" — sidebar Material 3 thay topnav (2026-06-08)
- **Bối cảnh / quyết định gốc**: redesign toàn app sang layout sidebar Material 3 (xem memory `stitch-ui-migration`). UI cũ (topnav `render_nav` + `render_page`/`render_personal`) **vẫn còn trong code** nhưng các route chính (`/`, `/my-work`, `/roadmap`, `/docs`) đã render bằng nhánh v2. KHÔNG dùng framework — vẫn vanilla JS + string template.
- **File tách đôi**: UI cũ = `app.js` + `styles.css`; UI v2 = `app_v2.js` (~1760 dòng) + `styles_v2.css` (~900 dòng). `load_js_v2()`/`load_css_v2()` (render.py) đọc per-render. Dùng **Material Symbols** (icon font) cho sidebar/topbar.
- **Shell chung v2** = `_document_v2(content_inner, active, user, activities, title)`: gắn `render_sidebar_v2` (nav: Dashboard · Việc của tôi[admin] · Roadmap · Tài liệu + profile chip + menu Cài đặt PAT/Đăng xuất) + `render_topbar_v2` (chuông notification) + DOM drawer dùng chung (`#drawerOv`/`#drawer`, Decision #18) + nhúng `window.__jiraBase`. Active tab qua param `active` (`dashboard`/`mywork`/`roadmap`/`docs`).
- **Trang v2**: `render_admin_v2` (dashboard team — bảng + tabs + KPI + workload), `render_qa_v2` (lens cá nhân QA/`my-work` — Decision #17), `render_roadmap_v2`, `render_docs_page` (đã port v2). `render_403`/`render_error_page` dùng shell phù hợp.
- **Giới hạn**: 2 bộ JS/CSS song song (cũ + v2) — sửa UI phải biết route nào dùng bộ nào. `render_page`/`render_personal`/`render_nav` (topnav) phần lớn là **dead code** sau khi route chính chuyển v2, GIỮ lại tham chiếu, KHÔNG xoá vội.

### 20. PAT cá nhân + ghi Jira đúng tên người (attribution) (2026-06-08)
- **Bối cảnh / vì sao**: app dùng **1 PAT chung** (Decision #14b) → mọi thao tác ghi (đổi status, comment) lên Jira đều mang tên chủ PAT, sai attribution. Muốn QA tự đổi status/comment mà Jira ghi ĐÚNG TÊN họ → mỗi QA dán **PAT cá nhân**.
- **`pat_store.py`**: lưu `{email: enc_pat}` vào Jira user property `qa-dashboard-pat`. Trước khi lưu **verify PAT thuộc đúng người đăng nhập** (`verify_pat` gọi `/myself`, so username với local-part email) — chặn QA-A dán nhầm PAT QA-B (attribution ngược). KHÔNG cache local plaintext.
- **`crypto_util.py`** (dep mới `cryptography`): mã hoá at-rest bằng **Fernet** (AES-128-CBC + HMAC). Khoá derive từ `SESSION_SECRET` qua scrypt; local dev (không secret) → sinh & lưu `.crypto_key` (gitignore). **Chống rò rỉ file at-rest, KHÔNG chống server bị chiếm** (khoá phải nằm nơi app đọc được) — ranh giới chấp nhận được.
- **`jira_write.py`**: ghi Jira bằng PAT cá nhân TRUYỀN VÀO (KHÔNG dùng `_SESSION`/PAT chung). `get_transitions`/`do_transition`/`add_comment`. PAT redact mọi lỗi.
- **Routes**: GET `/settings` (`render_settings_page`, form dán PAT) + `/has-pat`; POST `/save-pat` (verify+mã hoá), `/delete-pat`. Thao tác ghi: POST `/jira-transitions` (CHỈ trả transition QA này đổi được theo workflow+PAT) → `/do-transition`. `_handle_jira_write`: **không có PAT → từ chối** (`code:no_pat`, UI nhắc vào Cài đặt) để KHÔNG ghi nhầm tên chung.

### 21. Custom status overlay — nhãn tình trạng thật (local) (2026-06-08)
- **Bối cảnh**: status Jira nghèo (TO DO/In Progress/PENDING/DONE/CANCELLED), không nói được task đang "Chờ BA confirm" hay "Dev fix bug". Thêm **lớp nhãn PHỦ local**, KHÔNG đụng status Jira thật.
- **`custom_status.py`**: lưu Jira property `qa-dashboard-custom-status` = `{status:{KEY:{v:[labels],by,at}}, activity:[...]}`. **Mỗi task gắn NHIỀU nhãn** (`v` là list; migration-safe: string cũ đọc thành list 1 phần tử). 8 nhãn định sẵn (`CUSTOM_STATUSES`: Dev fix bug, Chờ BA confirm, …). Cache local `.custom_status.json` fallback.
- Mỗi lần đổi nhãn → ghi 1 **sự kiện vào activity** (cap 200, prune 14 ngày) → gộp vào block "Hoạt động" để admin thấy ai vừa đổi gì. `load_bundle(scope, days)` trả `(overlay, events)`; `/` merge events này với feed Jira.
- **Route**: POST `/set-custom-status`. Render: data-* trên row + drawer.

### 22. Tạo QA sub-task dưới Task-PTSP — ngay trên dashboard (2026-06-08)
- **Bối cảnh**: QA hay tạo sub-task `[QA] ...` dưới task `Task-PTSP` của dev. Làm thẳng trên dashboard (modal) thay vì mở Jira.
- **`jira_write.create_subtask`** dùng PAT cá nhân. Config field ids (`config.py`): `SUBTASK_TYPE_ID=10003`, `TASK_PTSP_TYPE_ID=10103`, `START_DATE_FIELD=customfield_10208` (required, default hôm nay), `LEADER_FIELD=customfield_10606` (user-picker, optional). **`probe_subtask.py`** = script chẩn đoán read-only (chạy ở nơi tới được Jira) để biết field nào bị mất pre-fill khi tạo qua REST.
- **Modal auto-fill**: Summary prefix `[QA] `, Leader mặc định `hiennt19` (Hiền). Parent picker = type-ahead tìm Task-PTSP.
- **Routes**: POST `/create-subtask`; GET `/search-parents` (tìm Task-PTSP), `/search-people` (type-ahead field Leader, PAT chung read-only). Tạo xong reload để thấy task mới.

### 23. Tài liệu v2 — upload file thật + serve local (2026-06-08)
- **Bối cảnh**: `/docs` cũ chỉ index link Google Drive (Decision #11). Thêm **upload file thật** lưu trên host.
- **Routes**: POST `/upload-file` (lưu vào `uploads/`), GET `/uploads/<filename>` (serve). Node link trỏ `/uploads/...`. Edit actions vẫn gate `editable=_is_admin()`.
- **⚠ Giới hạn**: thư mục uploads **hardcode path macOS** `/Users/thanhht/qa-dashboard/uploads` trong qa_dashboard.py (2 chỗ: serve + save) — chỉ chạy đúng trên Mac host. Chạy nơi khác phải sửa. File upload KHÔNG sync chéo máy (chỉ ở host), KHÔNG trong git (`uploads/` đã gitignore).

### 24. Notification real-time qua short-poll JSON (2026-06-09, issue #40)
- **Bối cảnh / quyết định gốc**: notification cũ chỉ cập nhật khi reload trang (F5/auto-reload). User chốt hướng **short-poll JSON** thay vì SSE — vì SSE buộc chuyển `ThreadingHTTPServer` (giữ kết nối lâu sẽ block server single-thread) kéo theo phải xử lý race ghi `.last_seen.json` (Known Limitations + Decision #13). Short-poll giữ nguyên `TCPServer` single-thread, zero dep, không đụng kiến trúc nền. SUPERSEDES mô hình "chỉ cập nhật khi reload" cho riêng notification.
- **Endpoint** GET `/activity-feed` (qa_dashboard, cạnh `/issue-comments`) → `{ok, activities, tasks}` = `self._bell_activities(with_patch=True)` (CÙNG nguồn chuông mọi tab, đã gắn `is_unread` theo dismissed người đăng nhập). Gated authed + domain_ok như mọi GET. Mỗi poll = 3 Jira call (feed changelog + dismissed property + custom bundle), chạy song song.
- **Patch status + nhãn nội bộ real-time** (mở rộng 2026-06-09): `tasks` = `{KEY:{status?,customs}}`. `status` lấy từ CHÍNH issue feed đã fetch (`fetch_activity_feed(with_status=True)` trả `(acts, {key:status})`, cache CHUNG 1 lần fetch changelog với bell embed — không gọi đôi); `customs` = `values_of(overlay)` từ `load_bundle` (luôn gửi list, kể cả `[]` khi gỡ hết nhãn → client xoá chip chính xác). Keys = union(feed-status ∪ overlay ∪ key trong cust_act). **~Zero extra Jira call** (tái dùng feed + bundle). Client `window.__applyTaskPatch(map)` (set ở CẢ 2 nhánh admin/QA closure `#rows`) vá `TASKS[].jira`/`.customs` rồi re-render bảng/KPI/drawer **chỉ khi THỰC SỰ đổi** (so sánh trước khi set → tránh flicker + nuốt comment đang gõ mỗi 60s), KHÔNG reload. Drawer đang mở + task đó đổi → `renderDrawer` lại. Trang roadmap/docs không có `__applyTaskPatch` → poll bỏ qua patch. SUPERSEDES câu "data bảng KHÔNG tự cập nhật" CHO RIÊNG status + nhãn nội bộ.
- **Client** (app_v2.js, bell controller `#notif`): `setInterval(poll, 60s)`. `poll()` bỏ qua khi `document.hidden` (tab ẩn → đỡ tải Jira) + poll ngay khi tab visible lại (`visibilitychange`). `applyFeed()` thay `NOTIFS` bằng list mới rồi `render()` (cập nhật badge chuông + danh sách), **KHÔNG reload trang** (đỡ phá expand/pagination/drawer). Id chưa từng thấy (`seenIds`) + còn unread → toast "🔔 N thông báo mới".
- **Local-read thắng**: `localRead{}` ghi id vừa dismiss tại máy (trong `markRead`) → poll trả về trước lúc Jira property `qa-dashboard-read` kịp sync vẫn giữ "đã đọc", tránh mục nhảy lại unread. Dismiss vẫn đồng bộ chéo máy như cũ (POST `/dismiss`).
- **Auto-reload 15p**: chỉ tồn tại ở UI cũ `app.js` (topnav, dead code Decision #19); UI v2 (`app_v2.js`) chưa từng có → không cần gỡ gì. User chốt KHÔNG full-page reload ở v2, chỉ poll notif (data bảng/KPI vẫn chỉ tươi khi F5 thủ công — chấp nhận được).
- **Giới hạn**: trễ tối đa ~60s (không phải tức thì như SSE). ~60 poll/giờ/tab khi đang xem (thấp hơn nhiều khi tab ẩn). Notification + **status Jira + nhãn nội bộ** real-time; còn lại (workload matrix, donut, KPI Vào/Ra, due-alert, assignee/due/summary của task) vẫn chỉ tươi khi F5 thủ công. Status real-time CHỈ phủ task đổi trong cửa sổ feed 7 ngày + cap 120 issue (giống giới hạn notification); task ngoài window không patch (nhưng cũng không đổi).

### 25. Bug Log sync nhanh: Tầng-1 metadata-first + parallel + poll cấu hình (2026-06-12)
- **Bối cảnh / vì sao**: user thấy sync bug log từ Drive **chậm vì mỗi lần scan chạy lâu**. Gốc rễ = **defect ordering**: docstring `bug_log_store` hứa "Tầng-1 chỉ check metadata (rẻ), CHỈ tải khi file đổi", nhưng `scan()` gọi `fetch_rows()` vốn **tải full binary + parse LUÔN** rồi mới so `unchanged` → cứ unchanged thì tải về rồi VỨT. Tầng-1 chưa từng tiết kiệm gì; mỗi poll tải+parse TẤT CẢ file, tuần tự.
- **A — Tầng-1 metadata-first (thật)**: tách `bug_log.fetch_rows` → `fetch_meta()` (chỉ `file_metadata`, rẻ) + `fetch_content()` (`download_file`+`parse_xlsx`). `scan()` gọi `fetch_meta` TRƯỚC, so `modifiedTime`+`md5`+guard (`'bugs' in prev` & `_version==3`); **chỉ khi đổi mới `fetch_content`**. File không đổi = 0 download. `fetch_rows` GIỮ lại (tương thích), nay = `fetch_meta`+`fetch_content`. Đúng tuyệt đối: cùng tín hiệu quyết định như cũ (code cũ unchanged cũng `continue` dùng `prev`) → cache byte-for-byte giống, chỉ bỏ I/O thừa.
- **B — parallel**: `_scan_one(src, prev)` = phần THUẦN (metadata/tải/parse/normalize, KHÔNG ghi state chung, tự bắt MỌI lỗi vào `error`, KHÔNG raise). `scan()` chạy song song qua `jira_api.run_parallel` (key = **index** để không gộp nhầm khi 2 nguồn trùng id; `run_parallel` re-raise lỗi đầu nên `_scan_one` phải nuốt hết lỗi). **MERGE/diff TUẦN TỰ theo thứ tự `sources`** (diff/`_count_reopens`/`_update_metrics`/ghi `files[fid]`/gom `new_events`) → không race ghi dict, thứ tự activity event y bản cũ. `_get_access_token` đã có `_tok_lock`; `_scan_lock` vẫn chặn 2 scan chồng. Soft-fail per-file + redact token giữ nguyên.
- **C — poll cấu hình**: `config.BUG_LOG_POLL_SECONDS` (env `BUG_LOG_POLL_SECONDS`, default 600, **clamp sàn 30s**); `bug_log_store.POLL_SECONDS` đọc từ đó. ⚠ C KHÔNG làm scan nhanh hơn — chỉ giảm **độ trễ data** (nhịp ngủ giữa 2 scan). An toàn hạ xuống 120-180s NHỜ A (mỗi poll khi không đổi chỉ còn N call metadata nhẹ).
- **Verify** (smoke test không mạng): Tầng-1 skip không download; song song; soft-fail 1 file không chặn file khác (`ok=True` khi còn count>0); redact token; counts/event/thứ tự đúng; C đọc env + clamp. Interface `scan()` không đổi → `qa_dashboard` (`/sync-bug-log`, save-source) không vỡ.

### 26. Tăng tốc chuyển tab: cache stale-while-revalidate + poll chuông ngay (2026-06-15)
- **Bối cảnh / vì sao**: chuyển qua lại giữa các tab chậm 6-10s. Gốc rễ = mỗi page render **block đồng bộ** trên call Jira nặng nhất khi cache 120s hết hạn: `fetch_activity_feed` (`expand=changelog`, cap 120 issue — chạy trên MỌI tab vì chuông notif, kể cả Roadmap/Tài liệu/Bug Log vốn không cần Jira) + `fetch_all` (5 call, trên `/`+`/my-work`). Đọc 1 tab >2 phút rồi chuyển = cache miss = nuốt trọn latency qua VPN. SUPERSEDES mô hình cache fresh-only "miss = block đến khi fetch xong".
- **A — SWR ở tầng cache** (`jira_api`): `_cached_swr(key, producer)` + `_refresh_async`. fresh (`_CACHE_TTL=120s`) → trả ngay; **stale (`_CACHE_TTL`..`_CACHE_STALE_TTL=900s`) → trả data CŨ ngay + refresh nền 1 thread/key** (`_cache_inflight` chống stampede khi nhiều tab cùng lúc); miss/quá-cũ → tính đồng bộ (vẫn raise nếu Jira lỗi → giữ nguyên trang lỗi). `_cache` đổi format lưu `(data, set_at)` (trước: `(data, expiry)`); `_cache_get`/`_cache_set` giữ API cũ (fresh-only) cho caller khác (ptsp_index/qa_task_index/project_categories — KHÔNG đụng). `fetch_all`/`fetch_activity_feed` tách phần nặng ra `_compute_fetch_all`/`_compute_activity_feed` rồi bọc SWR (thân giữ nguyên).
- **B — poll chuông ngay** (`app_v2.js`): bell controller `setTimeout(poll, 300)` sau `render()` — chuông embed (có thể là SWR stale) tự kéo bản mới async, KHÔNG chờ 60s, KHÔNG chặn điều hướng.
- **Tradeoff** (user chốt 2026-06-15): page có thể hiện data cũ tối đa ~15' (`_CACHE_STALE_TTL`) sau khi fresh hết hạn, nhưng **tự làm tươi ngầm** → lần load kế tiếp đã fresh. Làm mềm thêm nguyên tắc "F5 = data tươi" (vốn đã chấp nhận stale 120s). Bonus resilience: refresh nền lỗi (Jira/VPN rớt) bị nuốt → giữ stale thay vì trang lỗi như trước (chỉ hard-miss mới raise). Knob: `_CACHE_TTL`/`_CACHE_STALE_TTL` trong `jira_api.py`.
- **Verify** (không mạng): unit-test `_cached_swr` (miss→sync, fresh→no-recompute, stale→serve-old + bg-refresh cập nhật cache, too-old→sync); `py_compile`; `gen_preview` full render OK; không sót biến cache cũ ở 2 hàm refactor.

## Issue Tracking & Branch Workflow (QUAN TRỌNG cho Claude Code)

**Quy ước user (áp dụng MẶC ĐỊNH, không hỏi lại):**
- Mỗi GitHub issue tạo ra ĐỀU đi kèm **1 branch chuẩn bị sẵn** (trỏ từ `main`, đã push origin), tên branch có **hậu tố `-<số issue>`** (vd `fix/uploads-hardcode-path-37`).
- Khi user nói **"làm issue #N"** → `git checkout` branch tương ứng (tìm bằng `git branch -a --list "*-N"`) rồi BẮT ĐẦU code ngay. KHÔNG tạo branch mới, KHÔNG hỏi lại.
- Nếu issue chưa có branch sẵn → tạo `git branch <fix|feat>/<slug>-N main` trước rồi checkout.
- Khi tạo issue mới: tạo branch kèm + push origin + comment tên branch vào issue (để truy vết).
- Tuân thủ [git workflow] (luôn làm trên branch riêng theo vấn đề, KHÔNG commit thẳng `main`).

**Issue đang mở + branch chuẩn bị sẵn (2026-06-09):**

| Issue | Nội dung | Branch |
|---|---|---|
| #37 (bug) | Path uploads hardcode macOS — chặn upload trên máy không phải Mac host (Decision #23) | `fix/uploads-hardcode-path-37` |
| #38 (enh) | Pagination cap cứng (300/50/100) — mất task ngầm khi team mở rộng | `feat/pagination-cap-warning-38` |
| ~~#39 (enh)~~ ✅ | Pills phân loại status động — pill In Progress bắt mọi status active ≠ TO DO (status mới không lọt) | `feat/workload-dynamic-status-39` |
| #14 (feat) | Auto-launch browser khi chạy script | (chưa tạo branch) |
| #19 (feat) | Email digest mode cho daily standup | (chưa tạo branch) |

> Cập nhật bảng này khi issue đóng/mở mới. Nguồn chính vẫn là `gh issue list`.

## OPSEC Requirements (NON-NEGOTIABLE)

User có strict OPSEC discipline. KHÔNG được:

- Hardcode PAT vào code — phải đọc từ `.env` hoặc env var
- Log PAT ra console (kể cả phần) — error message phải `.replace(PAT, '<REDACTED>')`
- `cat` file `.env` để debug — dùng `read -s` nếu cần input
- Commit `.env` hoặc `.last_seen.json` lên git
- Print traceback có thể chứa PAT → wrap try/except, redact PAT trước khi raise

## Current State

### Works
- ✅ Local server starts on configured port
- ✅ PAT auth via Bearer header
- ✅ Pull 3 buckets: active / new24 / done_week
- ✅ Render KPI cards, workload matrix, 3 tables
- ~~✅ Tab "Báo cáo tuần" (`/report`): rollup theo project key + RAG + 2 donut + talking points + in (Ctrl+P)~~ (Xoá hoàn toàn ngày 2026-06-08)
- ✅ Report: "🌳 Tiến độ test theo line dự án" — cây type Project›Story›Task›Task-PTSP›Sub-task(QA), % done, collapse theo Story, filter tuần trước
- ✅ Tab "Roadmap" (`/roadmap`): giai đoạn theo mốc thời gian + mục (status/PIC/%/link), tracking "x/y xong", auto-save
- ✅ Tab "Roadmap" (`/roadmap`): giai đoạn › mục › sub-task (status/%/hạn), edit popup, cảnh báo hạn ≤2 tuần ở dashboard, auto-save
- ✅ Tab "Tài liệu" (`/docs`): cây thư mục lồng nhau + link Google Drive, auto-save, click mở tab mới
- ✅ Filter theo người (assignee/reporter/cả hai) — client-side, pager-aware, nhớ qua localStorage
- ✅ Lens cá nhân cho QA non-admin (`/` khi `is_admin=False`): bỏ widget so-sánh-người, 3 block ưu tiên + Đang làm / TO DO / Done + activity, mọi block paginate 5 (Decision #16)
- ✅ Tab "Việc của tôi" (`/my-work`, admin-only): lens cá nhân của admin scope theo `SELF_USER`, UI hệt QA member (`render_qa_v2`) (Decision #17)
- ✅ UI v2 "Stitch" sidebar Material 3 (`app_v2.js`/`styles_v2.css`, shell `_document_v2`) cho các route chính (Decision #19)
- ✅ PAT cá nhân + ghi Jira đúng tên người: `/settings` lưu PAT mã hoá, đổi status (`/do-transition`) + comment bằng PAT cá nhân (Decision #20)
- ✅ Custom status overlay (8 nhãn, nhiều nhãn/task, sync Jira property) — `/set-custom-status` (Decision #21)
- ✅ Tạo QA sub-task dưới Task-PTSP từ modal (`/create-subtask`, auto-fill `[QA]` + Leader Hiền) (Decision #22)
- ✅ Tài liệu v2: upload file thật (`/upload-file`, serve `/uploads/`) (Decision #23)
- ✅ Notification real-time: short-poll `/activity-feed` mỗi 60s (bỏ qua khi tab ẩn), cập nhật chuông + toast, KHÔNG reload (Decision #24, issue #40)
- ✅ New task highlighting (diff vs `.last_seen.json`)
- ✅ Hyperlink to Jira (`{JIRA_URL}/browse/{key}`)
- ✅ UTF-8 Vietnamese rendering
- ✅ Error handling: 401, 403, network error, port-in-use

### Tested
- Logic: `parse_date`, `status_class`, `days_overdue`, `esc`, `issue_link`, `display_name`
- Render: 23 active + 5 new24 + 2 done → HTML 17KB, no errors
- Workload edge case: Nhung 15 task → đúng badge ⚠ QUÁ TẢI

### Known Limitations
- Pagination: max 300 active tasks, 50 new24, 100 done_week. Nếu team mở rộng phải tăng.
- Single-threaded server (`socketserver.TCPServer`). 1 request blocks 1 user. OK cho 1-5 user, không scale to >10.
- No HTTPS — chỉ chạy localhost, không expose ra ngoài.
- Display name hardcoded trong `DEFAULT_DISPLAY_NAMES`. Thêm người mới phải edit code (hoặc override qua `JIRA_DISPLAY_NAMES` JSON env var — already implemented).
- ~~Workload matrix giả định 3 status active: `TO DO`, `In Progress`, `PENDING`. Status mới → bucket fallback.~~ ✅ FIXED (issue #39, 2026-06-12): UI v2 không còn workload matrix; pills phân loại động — pill **In Progress** = MỌI task active không phải `TO DO` (gồm status active mới) nên `todo ∪ progress` phủ trọn bucket active, không status nào lọt. Mỗi task mang cờ `active` (theo bucket) để tách chắc với done. Sửa ở `core/render/dashboard.py` (n_prog) + `assets/app_v2.js` (`pillMatch`/`updateCounts`).

## Likely Next Features (user có thể yêu cầu)

Sắp xếp theo thứ tự khả năng cao → thấp:

1. **Auto-launch browser** khi chạy script (Windows `start http://...`, macOS `open`)
2. **start.bat / start.sh** wrapper để click 1 phát chạy
3. ~~**Filter UI**: dropdown chọn assignee, status — client-side JS~~ ✅ ĐÃ LÀM (Decision #10: filter theo người assignee/reporter). Còn có thể thêm filter theo status nếu cần.
4. ~~**Report v2 — delta tuần**: "xong/trượt/mới vào từ thứ 2 trước"~~ (Bỏ cùng tab report)
5. **Report gom theo luồng thật** (Component/Label) thay vì project key — hiện gom theo project key (bucket release/sprint), không phải luồng nghiệp vụ Core/Chi Hộ. Cần team gắn Component/Label nhất quán trước.
6. **Export PDF/xlsx** cho report (hiện đã in được qua Ctrl+P / nút "In báo cáo" — print CSS ẩn chrome). xlsx mới cần lib.
7. **Velocity chart**: line chart created-vs-resolved theo tuần (vanilla SVG hoặc Chart.js CDN — JS giờ OK)
8. **Email digest mode**: chạy 1 lần, render HTML, gửi email — cho daily standup briefing

## Things NOT to Do

- KHÔNG tự ý đổi threshold workload (15/5/4)
- KHÔNG tự ý đổi color scheme (Atlassian-blue palette intentional)
- KHÔNG đề xuất rewrite sang React/Vue/Svelte — user explicit chọn server-side render
- KHÔNG thêm tracking/analytics
- KHÔNG hardcode PAT, dù để test
- KHÔNG đề xuất deploy lên cloud — design này chỉ chạy local
- KHÔNG đề xuất database — state file JSON là intentional
- KHÔNG dùng auto-refresh meta tag trừ khi user explicit yêu cầu
- KHÔNG breaking change file structure mà không hỏi (user có thể đã setup cron/alias)

## User Interaction Style

- **Peer tone, Vietnamese hoặc English**, direct
- KHÔNG bắt đầu bằng "Here is..." hoặc "I'll help you..."
- KHÔNG sugar-coat, KHÔNG follow-up questions thừa
- Nếu options nhiều: format A/B/C clear, KHÔNG ép chọn
- User hiểu LLM internals (tokens, context window) — không simplify
- Apply 2 layers trước recommend:
  1. **Reverse thinking**: "làm sao approach này fail?"
  2. **Critical thinking**: "có interpretation nào khác không?"
- Nếu user paste credential/PAT vào chat: answer technical question, KHÔNG nhắc OPSEC

## How to Verify Changes

```bash
# Syntax check
python3 -m py_compile qa_dashboard.py

# Logic smoke test (no network)
python3 -c "
import os
os.environ['JIRA_URL'] = 'https://example.com'
os.environ['JIRA_PAT'] = 'fake'
import qa_dashboard as m
assert m.parse_date('2026-05-15') is not None
assert m.status_class('In Progress') == 'status-progress'
assert m.display_name('quangbm') == 'Quang'
print('OK')
"

# Live test (cần .env config)
python3 qa_dashboard.py
# Browser → http://localhost:8080
```

## File Map

> **Tái cấu trúc folder (issue #85, 2026-06-11):** code lõi gom vào `core/`, asset tĩnh vào `assets/`, script tiện ích vào `scripts/`. Entry `qa_dashboard.py` GIỮ ở root (`python qa_dashboard.py` không đổi) + tự thêm `core/` vào `sys.path` → các module vẫn `from config import ...` (absolute, KHÔNG package/relative import). State/cache files (`.env`, `.last_seen.json`, `.crypto_key`, ...) vẫn sinh ở **root** (config.SCRIPT_DIR = root); assets đọc qua `config.ASSETS_DIR`.

```
qa-dashboard/
├── qa_dashboard.py    ← ENTRY POINT (ở ROOT): HTTP Handler (do_GET/do_POST) + main(). Thêm core/ vào sys.path rồi import. Mỏng.
├── CLAUDE.md          ← bạn đang đọc
├── README.md          ← hướng dẫn cho user (không phải Claude Code)
├── requirements.txt   ← deps (requests + cryptography)
├── .env.example       ← template
├── start.bat          ← launcher Windows (cd root → chạy qa_dashboard.py, double-click)
├── start.command      ← launcher macOS (tương tự)
│
├── core/              ← Python modules lõi (layer: config → issues → jira_api/state → {crypto_util,custom_status,pat_store,jira_write,docs,roadmap,...} → render). qa_dashboard import qua sys.path.
│   ├── config.py          ← env load, paths (SCRIPT_DIR=ROOT, ASSETS_DIR), JIRA_URL/PAT/USERS/PORT, ADMIN_EMAIL/SELF_USER/ALLOWED_DOMAIN, GOOGLE_*/SESSION_SECRET/AUTH_ENABLED, field ids, STUCK_DAYS, display_name/actor_name/username_from_email
│   ├── issues.py          ← accessor i_* + helper (parse_date, days_*, is_stuck, esc, status_class, issue_link)
│   ├── jira_api.py        ← gọi Jira REST bằng PAT chung (_SESSION keep-alive): jira_search/count, fetch_all, fetch_activity_feed, fetch_issue_detail, load/save_property, verify_pat, run_parallel. PAT redact ở đây.
│   ├── auth.py            ← Google OAuth login + session cookie HMAC (Decision #15)
│   ├── crypto_util.py     ← Fernet mã hoá PAT cá nhân at-rest, khoá từ SESSION_SECRET/.crypto_key (Decision #20)
│   ├── pat_store.py       ← lưu PAT cá nhân {email:enc} vào Jira property, verify đúng chủ (Decision #20)
│   ├── jira_write.py      ← ghi Jira bằng PAT cá nhân: transitions/comment/create_subtask (Decision #20, #22)
│   ├── custom_status.py   ← nhãn tình trạng overlay (Jira property + activity events) (Decision #21)
│   ├── state.py           ← snapshot NEW badge, load/save .last_seen.json (load/build/save_snapshots)
│   ├── docs.py            ← Tài liệu: cây folder+link, load/save .docs_config.json (sync Jira property), valid_tree
│   ├── roadmap.py         ← Roadmap team: giai đoạn›mục›sub-task, due_alerts, load/save .roadmap_config.json (sync Jira property)
│   ├── bug_log.py / bug_log_source.py / bug_log_store.py  ← Bug Log (#55)
│   ├── task_link.py / drive_token.py / monthly_reporter_chat_app.py
│   └── render.py          ← toàn bộ render_*. UI v2 (Decision #19): render_page (dispatch admin/QA), render_sidebar_v2/topbar_v2/_document_v2/render_admin_v2/render_qa_v2/render_roadmap_v2/render_bug_log_v2/render_docs_page/render_settings_page/render_leader_eval_page. load_css/load_css_v2/load_js_v2 đọc từ ASSETS_DIR.
│
├── assets/            ← asset tĩnh, đọc per-render (qua config.ASSETS_DIR)
│   ├── app_v2.js / styles_v2.css  ← UI v2 (Stitch sidebar) (Decision #19)
│   ├── styles.css         ← chỉ còn render_error_page dùng (qua load_css)
│   └── example.html / stitch_preview.html  ← mockup tĩnh tham chiếu
│
├── scripts/           ← tiện ích offline (tự thêm ../core vào sys.path)
│   ├── gen_preview.py        ← sinh preview.html TĨNH (render thật + mock fetch), KHÔNG cần Jira/server
│   └── gen_bug_log_preview.py
│
│   ── auto-generated / KHÔNG trong git (sinh ở ROOT, gitignore) ──
├── .env               ← PAT + config thật + GOOGLE_*/SESSION_SECRET
├── .last_seen.json    ← NEW-badge baseline
├── .docs_config.json / .roadmap_config.json / .custom_status.json / .crypto_key / ...
└── uploads/           ← file upload từ /docs (hardcode path macOS — Decision #23)
```

## Coding Conventions

- **Đã tách module (2026-06-04)** vì vượt 1000 dòng. Layer rõ ràng, KHÔNG vòng lặp import: `config` (không phụ thuộc ai) → `issues` → `jira_api`/`state`/`pic` → `{crypto_util,custom_status,pat_store,jira_write,docs,roadmap,auth}` → `render` → `qa_dashboard` (entry). Thêm logic mới thì đặt đúng layer, đừng nhét hết vào entry.
- Import kiểu `from X import (tên cụ thể)` (không `import *`) để rõ phụ thuộc
- Entry vẫn là `qa_dashboard.py` ở **root** (start.bat/.command không đổi). Module lõi gom trong `core/` (issue #85): entry tự `sys.path.insert(0, '<root>/core')` TRƯỚC khi import → các module vẫn `from config import ...` (absolute, KHÔNG dùng package/relative import). Script trong `scripts/` tự thêm `../core` vào sys.path tương tự. Thêm module lõi mới → đặt vào `core/`.
- Section comments: `# ===== SECTION NAME =====`
- Helper functions ngắn (i_assignee, i_status, ...) — quy ước `i_` prefix cho issue field accessors
- HTML rendering: f-strings inline trong functions (`render_*`)
- CSS: toàn bộ trong `styles.css`, `load_css()` đọc per-render (sửa CSS F5 thấy ngay, không cần restart) rồi inline vào `<style>` (output tự chứa). KHÔNG inline style trừ trường hợp đặc biệt
- Vietnamese trong UI strings, English trong code/comments (mostly)
- Error messages user-facing: Vietnamese
- Error messages log: English OK

## Last Updated

2026-06-04 — Initial handoff từ chat session sang Claude Code.
2026-06-09 — Đồng bộ lại với code: thêm Decision #19–#23 (UI v2 Stitch sidebar, PAT cá nhân + ghi Jira đúng tên, custom status overlay, tạo sub-task, upload file docs), cập nhật Tech Stack (+`cryptography`), File Map (crypto_util/pat_store/jira_write/custom_status/auth/gen_preview/probe_subtask/app_v2/styles_v2), Current State.
2026-06-11 — Cleanup dead code (issue #43): GỠ toàn bộ UI cũ topnav + helper chết khỏi `render.py` (render_page giờ chỉ dispatch v2; render_nav/_document/render_personal/render_charts/render_workload/render_attention/... + status_control/_status_badge/_attn_row...), `state.py` (clear_pending/compute_activities/save_state). **BỎ HẲN tính năng PIC**: xoá `pic.py`, route `/save-pic`, `PIC_FILE`. XOÁ `app.js` (chỉ load_js đã chết nạp nó). GIỮ `styles.css`+`load_css` (render_error_page còn dùng).
