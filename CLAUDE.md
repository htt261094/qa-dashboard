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
- State persistence: **Jira user property làm kho sync chéo máy** (roadmap/docs/dismiss/PAT/custom-status — xem Decision #14, #20, #21). `.last_seen.json` (NEW-badge snapshot-diff) đã GỠ — xem Decision #27.

## Architecture

```
[Browser] ←HTTP→ [Python qa_dashboard.py] ←REST API+PAT→ [Jira Bảo Kim]
                 (localhost:8080)                         (jira.baokim.vn:8443)
```

- F5 trong browser = pull fresh Jira data
- Refresh thủ công (user explicitly chose this over auto-refresh 15min)
- "New" badge (admin dashboard) = task `created == hôm nay` (stateless, tính server-side mỗi render — KHÔNG còn snapshot-diff)

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
- **UPDATE 2026-07-07 (user yêu cầu)**: bỏ cửa sổ 3 ngày → hiển thị **TẤT CẢ** task done. JQL đổi sang `status = "DONE" ORDER BY updated DESC` (current-state filter, không còn `CHANGED TO ... AFTER -3d`), `max_results` 100→500. Nhãn KPI "Done (3 ngày)"→"Done". Vào/Ra tuần (`resolved_week`) VẪN dùng `status CHANGED TO "DONE" AFTER startOfWeek()` — không đụng.
- **BUGFIX cùng ngày**: lens cá nhân (`render_qa_v2` — dùng cho `/my-work` + QA `/`) trước CHỈ build `tasks` từ bucket `active` → KPI "Done" có SỐ nhưng bấm vào không ra dòng nào. Đã: (a) thêm done tasks (`data['done_week']`) vào list `tasks`; (b) `matchFilter` (closure QA app_v2.js) thêm nhánh `done` (=jira DONE) + đổi default `all` = **non-done** (trước `return true`); (c) KPI Done bấm giờ `setFilter('done')` thay vì reset về `all`.
- Cột thời gian hiển thị `resolutiondate`, fallback `updated` nếu null
- KHÔNG đổi lại sang `resolved`/`startOfWeek()`/window thời gian trừ khi user yêu cầu

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

### 7. State file `.last_seen.json` lưu cùng folder script — ❌ ĐÃ GỠ (xem Decision #27)
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
- **Mockup**: ban đầu có `example.html` (link `styles.css` thật) để preview lens này trước khi code — đã XOÁ cùng toàn bộ file preview/generator (2026-06-16, không còn dùng).
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

### 26b. "F5 = luôn tươi" — ép bypass SWR khi user chủ động refresh (2026-07-01)
- **Bối cảnh / vì sao**: SWR (#26) đổi status Jira KHÔNG hiện ngay — triệu chứng "F5 nhiều lần mới cập nhật". Gốc rễ: trong cửa sổ stale (`_CACHE_TTL`..`_CACHE_STALE_TTL`), F5 lần đầu trả data CŨ ngay + refresh nền → phải F5 lần 2 mới thấy mới; trong cửa sổ fresh (<120s) thì F5 bao nhiêu lần cũng cũ. User chốt hướng: **F5/hard-reload = ép data tươi**, còn **click chuyển tab = giữ SWR nhanh** (không đánh đổi tốc độ điều hướng).
- **Cách phân biệt** = header `Cache-Control` của browser: F5 (soft) gửi `max-age=0`, Ctrl+F5 (hard) gửi `no-cache`; click thẻ `<a>` KHÔNG gửi → `_wants_fresh()` (qa_dashboard) đọc header, chỉ True khi có 1 trong 2 chuỗi đó.
- **Plumbing**: thêm `force` (default False, tương thích ngược) xuyên `_cached_swr(...,force)` (bỏ qua fresh/stale, tính đồng bộ ngay; block=False + Jira lỗi → trả entry cũ/`_SWR_NOT_READY` thay vì raise) → `fetch_activity_feed(...,force)` / `fetch_all(...,force)`; `fetch_all_shared(...,force)` bỏ qua fresh-serve của L1 RAM + L2 KV + L3 đĩa, đi thẳng live fetch (snap vẫn giữ làm fallback offline → mất VPN vẫn read-only, không trang lỗi). Handler `/` + `/my-work` truyền `force=self._wants_fresh()` vào `fetch_all_shared` + feed + `_bell_activities(force=...)`.
- **KHÔNG force**: endpoint poll `/activity-feed` (60s) gọi `_bell_activities(with_patch=True)` KHÔNG truyền force → giữ SWR rẻ (poll không phải F5). Bug log table (`load_bug_log()` đọc `.bug_log.json` local) vốn đã tươi mỗi F5 (không qua SWR Jira) → không đụng.
- **Tradeoff**: F5 lúc cache stale chậm hơn ~1-2s (chờ live fetch qua VPN) — user chấp nhận để đổi lấy "F5 chắc chắn ra data mới". Chuyển tab vẫn nhanh như #26.
- **Verify** (không mạng): `py_compile` qa_dashboard + jira_api OK; unit-test `_cached_swr` force (miss→sync, fresh→no-recompute, force→recompute-dù-fresh, cache=bản mới sau force, force+raise+block→raise, force+raise+block=False→entry cũ/sentinel) 7 ca pass.

### 27. Dọn dead code `.last_seen.json` / snapshot-diff NEW badge (2026-06-16, issue #134)
- **Bối cảnh / vì sao**: yêu cầu v1 = reload dashboard thì highlight task mới lọt bucket bằng snapshot-diff (`.last_seen.json`). Từ khi chuyển UI v2 + notification (Decision #19/#24), cơ chế này **không còn được render** nhưng vẫn chạy mỗi request: `_build_view` (qa_dashboard) đọc+ghi `.last_seen.json` qua `state.load/build/save_snapshots`, tính `new_keys`, truyền xuyên `render_page` → `render_qa_v2` gắn `isNew` mỗi task → **QA controller (`app_v2.js` closure `#rows`) KHÔNG đọc `isNew`** (matchFilter chỉ overdue/stuck/dueweek/all; rowHTML không render badge nào). SUPERSEDES Decision #7 (state file) + phần "snapshot NEW badge" của Decision #9/#16/#17.
- **Cái "New" còn thấy KHÔNG đụng tới**: pill "New" ở `render_admin_v2` = `isNew = created == hôm nay` (stateless, không đọc file) + admin controller `app_v2.js` đọc `t.isNew`. Đây là nguồn KHÁC, GIỮ nguyên.
- **Đã xoá**: `core/state.py` (toàn bộ module); `_build_view` + import `state` + `STATE_FILE` import & dòng print trong `qa_dashboard.py`; param `new_keys`/`first_run` xuyên `render_page`/`render_admin_v2`/`render_qa_v2`; field `isNew` ở `render_qa_v2` (chỉ QA lens — admin giữ); `STATE_FILE` trong `config.py`; entry `.last_seen.json` trong `.gitignore`. Cập nhật `gen_preview.py` (bỏ arg `new_keys`).
- **Lợi**: bớt 1 file state + 1 module + 1 lượt đọc+ghi file mỗi request; bớt 1 mối lo atomic-write của #128.
- **Verify**: `py_compile` qa_dashboard + config + dashboard + gen_preview OK; `gen_preview.py` render đủ (admin `render_admin_v2` + personal `render_qa_v2`) không lỗi.

### 28. ThreadingHTTPServer — hết đơ-toàn-cục khi 1 request chậm (2026-06-16, issue #129)
- **Bối cảnh / vì sao**: `socketserver.TCPServer` xử lý request TUẦN TỰ. Mỗi tab poll `/activity-feed` mỗi 60s, mỗi load `/` chạm Jira. Khi Jira/VPN treo, 1 request ngậm tới read-timeout 30s (`jira_api`) → MỌI user/tab khác **đứng hình suốt 30s**. Với 5 QA + nhiều tab, đây là nguyên nhân "web đơ" dễ xảy ra nhất. SUPERSEDES "Single-threaded server" ở Known Limitations + lý do giữ TCPServer ở Decision #13/#24.
- **Đổi**: `socketserver.TCPServer` → `http.server.ThreadingHTTPServer` + `server.daemon_threads = True` (main()). Mỗi request 1 thread → request chậm KHÔNG chặn request khác. `ThreadingHTTPServer` là subclass `TCPServer` → `with` context manager + xử lý OSError port-in-use giữ NGUYÊN. Bỏ `import socketserver`.
- **Vì sao giờ an toàn (trước thì không)**: lý do cũ giữ single-thread = tránh race ghi `.last_seen.json`. Giờ (a) `.last_seen.json` + `state.py` đã GỠ hẳn (Decision #27); (b) mọi kho ghi đã có lock: `_cache_lock`/`_pool_reset_lock`/`_snap_*_lock` (jira_api), `_scan_lock`/`_tok_lock` (bug_log), `_meta_lock` (remote_store/KV); (c) **`atomic_write` (#128)** giờ dùng **tmp-name DUY NHẤT theo pid+thread** (`config.py`) → 2 thread cùng ghi 1 path mỗi đứa 1 `.tmp` riêng, `os.replace` của ai người nấy atomic, last-writer-wins ở mức file HOÀN CHỈNH (không bao giờ cụt/torn). Các memoize không khoá còn lại (`_USERNAME`, `_cache` recompute) là idempotent → race vô hại.
- **PHẢI sau #128** (atomic write) — đã merge. Item #4 issue (semaphore trần call Jira đồng thời) tách issue riêng, CHƯA làm.
- **Verify** (không mạng): `py_compile` qa_dashboard + config OK; stress 8 thread × 50 ghi đồng thời cùng 1 path → file luôn JSON hợp lệ, 0 tmp sót; import entry OK, `ThreadingHTTPServer` là subclass `TCPServer`.

### 29. Bug Log hỗ trợ Google Sheet native (export → xlsx) (2026-06-16, issue #144)
- **Bối cảnh / vì sao**: nguồn bug log trên Drive là **Google Sheet native** (không phải .xlsx up lên). `download_file` cũ tải bằng `alt=media` — chỉ chạy với file nhị phân; native Sheet → Drive trả **403 `fileNotDownloadable`** → `_scan_one` soft-fail → cache đóng băng, bug mới/status/**reopen** không bao giờ update. Triệu chứng đánh lừa: reopen vẫn hiện số CŨ (monotonic, cached) nên tưởng còn chạy. Trước đó chạy được vì nguồn KHI ẤY là .xlsx thật; tới khi file bị convert/đổi sang Sheet native thì mọi scan 403.
- **Đổi** (`bug_log.py`): `file_metadata`/`fetch_meta` lấy thêm `mimeType`. `download_file(file_id, mime_type=None)`: `mimeType == application/vnd.google-apps.spreadsheet` → gọi `/files/{id}/export?mimeType=<xlsx>` (Drive convert Sheet→xlsx, đa sheet + giữ tên sheet → `parse_xlsx`/month detection không đổi); còn lại giữ `alt=media`. `export` KHÔNG nhận `alt`/`supportsAllDrives`. `_scan_one` truyền `meta['mimeType']` xuống `fetch_content` → KHÔNG thêm call Jira/Drive. `mime_type=None` → tự lấy metadata (1 call) để route.
- **Change-detection**: native Sheet không có `md5Checksum` (luôn '') → `unchanged` dựa `modifiedTime` (đã sẵn tolerant, docstring cũ). Không đổi logic `unchanged`.
- **Giới hạn**: `files.export` cap ~10MB (bug log nhỏ, ổn). Nếu nguồn config trỏ NHẦM sang 1 Sheet KHÁC file đang sửa thì vẫn "không update" — lỗi cấu hình nguồn, không phải bug này.
- **Verify** (không mạng): `py_compile` bug_log + bug_log_store OK; smoke monkeypatch `_drive_get` → native route `/export?mimeType=xlsx` (không alt/supportsAllDrives), xlsx route `alt=media`, `mime_type=None` tự lấy meta rồi route đúng.

### 30. Reopen tracker — seed theo trạng thái hiện tại (2026-06-16, issue #146)
- **Bối cảnh / vì sao**: bảng "Tỷ lệ Reopen" rỗng dù file có bug đang ở status Reopen. `_count_reopens` chỉ +1 khi quan sát được **transition LIVE** `≠Reopen → =Reopen` giữa 2 snapshot. Bug đã ở Reopen sẵn tại baseline (hoặc sau khi accumulator reopen/metrics bị **reset về 0** — vd lần restart sau merge #144/#145, mọi metric seed lại cùng 1 mốc) thì cú nhảy không được chứng kiến → 0 entry. KHÔNG phải bug KV/save (persistence chạy đúng — đã verify từ `.bug_log.json`: file vẫn rescan, metric status đúng `Reopen:N`, chỉ `reopen` map rỗng).
- **Fix (hướng A)**: `_seed_current_reopens(reopen_map, cur_bugs)` — bug đang status `'Reopen'` mà `key not in reopen_map` → seed `{count:1, fix:1}` (lower-bound: Reopen tất phải Fixed ≥1 lần trước). Gọi trong `scan()` SAU vòng xử lý file, trên **TẤT CẢ bug hiện tại** gộp từ `files[*]['bugs']` (gồm file Tầng-1 skip) → tự chữa ngay, không cần file đổi; set `dirty=True` để persist.
- **Không double / idempotent**: chỉ seed khi chưa có entry → transition (count chính xác) hoặc seed cũ không bị đè. `_count_reopens` GIỮ NGUYÊN, vẫn cộng tiếp các lần dội Fixed→Reopen sau seed. `_merge_reopen` lấy max nên seed=1 không hạ count cao hơn ở host/KV khác.
- **Giới hạn**: không tái tạo số dội thật trước khi theo dõi (dội 3 lần → hiện 1); bug đã rời Reopen (Closed) trước khi seed thì không bắt. Note dưới bảng sửa lại cho khớp ("Bug đang ở Reopen được tính tối thiểu 1 lần...").
- **Verify** (không mạng): `py_compile` bug_log_store + render/bug_log OK; unit-test seed Reopen-only + idempotent + KHÔNG double với transition + transition tăng tiếp sau seed; chạy trên `.bug_log.json` thật → seed 18 entry (đúng 6 bug DA6 28/57/59/63/64/65 + DA5/ERP/VĐT).

### 31. AUTH tắt = fail-closed (loopback-only) thay vì fail-open admin (2026-06-18, issue #44)
- **Bối cảnh / vì sao**: khi `AUTH_ENABLED=False` (chưa set `GOOGLE_CLIENT_ID/SECRET` — local dev, hoặc LỠ quên lúc golive), code cũ cho MỌI request là admin (`_authed`/`_is_admin` trả True vô điều kiện). Mô hình an toàn dựa HOÀN TOÀN vào "bind 127.0.0.1 + chỉ cloudflared+OAuth phía trước"; chỉ 1 sai lệch (quên creds, bind nhầm 0.0.0.0, chạy máy khác, đổi tunnel) là rơi về "ai chạm port cũng là admin" — fail-**open**, không lớp chặn thứ 2.
- **Đổi = fail-closed theo loopback**: AUTH tắt → CHỈ request từ loopback (`127.0.0.0/8` hoặc `::1`) mới được coi là chính chủ/admin; request từ máy khác → **403**. AUTH bật → giữ nguyên (phải có email session/header).
- **Tín hiệu tin cậy = `self.client_address[0]`** (peer TCP thật), KHÔNG phải header `X-Forwarded-For`/`Host` (client bịa được; peer TCP thì không). Helper `_is_loopback()` dùng `ipaddress.ip_address(...).is_loopback`, quy `::ffff:127.0.0.1` (IPv4-mapped) về IPv4 trước khi check.
- **Wiring** (`qa_dashboard.py`): `_authed()` AUTH-tắt → `return self._is_loopback()` (thay `True`); `_is_admin()` nhánh no-email → `(not AUTH_ENABLED) and self._is_loopback()`; gate đầu `do_GET` (`if not AUTH_ENABLED and not _is_loopback(): _forbidden()` — 403 cứng cho cả `/login` vì login bất khả khi AUTH tắt) + `do_POST` (qua `_authed()`). `main()` in cảnh báo to lúc khởi động khi AUTH tắt.
- **KHÔNG đổi**: server vẫn bind `127.0.0.1` (mitigation lớp 1 vẫn còn); local dev loopback giữ nguyên trải nghiệm admin. Đây là **defense-in-depth lớp 2** — nếu lớp 1 sai (bind 0.0.0.0) thì loopback-check vẫn chặn. Chưa làm item #3 issue (verify JWT `Cf-Access-Jwt-Assertion`) — fallback header CF vẫn header-trust, nhưng prod đi qua OAuth session là chính.
- **Verify** (không mạng): `py_compile` OK; `_is_loopback` đúng cho `127.0.0.1`/`::1`/`::ffff:127.0.0.1`=True, `192.168.*`/`10.*`/`0.0.0.0`/rác=False; với AUTH tắt giả lập → loopback `authed=admin=True`, non-loopback `authed=admin=False`.

### 32. Chatbot AI float — proxy LLM local Ollama + context team — ❌ ĐÃ GỠ (2026-07-06)
- User quyết định bỏ tính năng chatbot. Đã xoá hoàn toàn: `core/chat.py` (module riêng), config `OLLAMA_URL`/`OLLAMA_MODEL`/`OLLAMA_KEEP_ALIVE`/`CHAT_ENABLED` (`config.py`), route `POST /chat` + `_post_chat` + prewarm thread (`qa_dashboard.py`), `_chat_widget()` + call site trong shell (`core/render/shell.py`), controller IIFE + `md()` markdown renderer + `scrapePage()` trong `assets/app_v2.js`, toàn bộ CSS `.chat-*` trong `assets/styles_v2.css`, block env mẫu trong `.env.example`.
- KHÔNG đụng `core/monthly_reporter_chat_app.py` — đó là report tháng gửi qua **Google Chat webhook**, tên trùng "chat" nhưng là tính năng khác hẳn (xem memory "Report Google Chat only").
- Cần **restart app** để route/import Python gỡ có hiệu lực (JS/CSS hot-reload per-render đã sạch ngay).

### 33. Bug tồn đọng T-1 vs mới phát sinh — snapshot status per-bug theo tháng (2026-07-02)
- **Bối cảnh / vì sao**: report tháng cần tách rõ **bug MỚI phát sinh trong tháng** vs **bug TỒN ĐỌNG từ tháng liền trước (T-1)** — nợ cũ mang sang. User chốt **CHỈ T-1** (không cộng dồn nợ các tháng cũ hơn) và **hướng B** (chốt theo mốc thời gian, xử lý lâu dài) thay vì tính created-date-hiện-trạng nhất thời (hướng A undercount phần nợ cũ đã dọn trong tháng).
- **Vì sao B**: "bug nào còn MỞ tại thời điểm chuyển tháng" KHÔNG tái tạo được từ status hiện tại (status đổi liên tục) → phải CHỐT snapshot per-bug theo tháng.
- **Module `core/bug_backlog.py`**: snapshot mỗi tháng = trạng thái các bug **TẠO trong tháng đó** (không cần ảnh toàn hệ thống vì chỉ cần T-1). Lưu `{months:{"YYYY-MM":{key:{s,c,p,n,d,sv}}}}` vào `.bug_monthly.json` local + KV/property qua `remote_store` (prop `qa-dashboard-bug-monthly`). `is_open` = status ∉ {Closed, Rejected/Reject} (Fixed = vẫn mở, QA chưa close). `prev_month_backlog(report_month)` = compute dùng chung (total/still_open/resolved/removed/new_count + list).
- **Freeze tự động**: `archive(cur_bugs)` gọi từ `bug_log_store.scan()` (sau `all_cur_bugs`, lazy-import, soft-fail) — mỗi scan GHI ĐÈ snapshot của **tháng hiện tại** (theo wall-clock) = bug tạo trong tháng đó; tháng trước KHÔNG bị đụng → tự đóng băng ở lần scan cuối của tháng. Dedup: chỉ ghi KV khi months đổi (JSON compare).
- **Bootstrap 1 lần**: tháng quá khứ chưa có snapshot → seed từ data hiện tại (status hôm nay). ⚠ **Tháng 6→7 (đợt đầu) là GẦN ĐÚNG** (dùng status hiện tại thay vì đúng 30/06, lệch ~ngày chạy); **từ tháng 8 trở đi chính xác tuyệt đối** (freeze đúng mốc chuyển tháng).
- **Hiển thị 2 chỗ** (thể hiện TRỰC QUAN, KHÔNG list chi tiết bug — user chốt; card Analytics đứng riêng ĐÃ BỎ vì thừa/rối): (a) **dải tóm tắt tồn đọng chèn TRONG `#anMetricCharts`** (theo tháng của `#anMetricMonth`) = dòng "N mới · Tồn đọng T-1: M (còn treo/đã xử lý)" + `compBar` (Mới phát sinh · Tồn đọng còn treo · Tồn đọng đã xử lý) → nằm trong ẢNH report export gửi CTO (trước chart chỉ có bug mới); (b) report Google Chat — `monthly_reporter_chat_app.py` gọi `prev_month_backlog` thêm dòng số vào text. Controller trong analytics IIFE (`app_v2.js`): `computeBacklog(ym)`/`compBar` dùng bởi `renderMetric`, data embed `analyticsData.backlogMonths`.
- **2 nhóm (user chốt, không 3): Còn vs Đã xử lý** — `is_open` = status ∈ {New/Fixing/Fixed/Reopen}; **Đã xử lý = đã đóng (Closed/Reject) HOẶC không còn trong file** (gộp "removed" vào resolved, KHÔNG tách nhóm xám). → `total = still_open + resolved` LUÔN khớp mọi tháng. ⚠ `is_open` là XƯƠNG SỐNG ảnh hưởng tháng sau (mở tháng này = tồn đọng T-1 tháng sau) → KHÔNG đổi tuỳ tiện (đặc biệt `Fixed` giữ = "còn", QA chưa close vẫn là nợ). Việc gộp "không còn" chỉ là DISPLAY lúc đọc, KHÔNG đụng snapshot/is_open → zero tác động chuỗi tháng sau.
- **Giới hạn**: chỉ T-1 (theo yêu cầu); bug thiếu `created` / created tương lai bị loại khỏi snapshot; bug bị xoá khỏi file sau đó gộp vào "đã xử lý" (không dựng lại được là đóng hay xoá). `_MONTHS_CAP=24`. Cần **restart app** để archive hook + route mới chạy (JS/CSS hot-reload per-render).
- **Verify** (không mạng): `py_compile` bug_backlog/bug_log_store/analytics/qa_dashboard/monthly_reporter OK; smoke E2E stub remote+live → bootstrap tạo snapshot T-1, tồn đọng=3 (Closed loại), progress resolved/still_open đúng sau khi 1 bug carried được close, new_count đúng, dedup=False khi không đổi, **freeze**: snapshot T-1 giữ 'Fixing' dù live đã 'Closed'; render analytics embed `backlogMonths` OK.

### 34. Bell notification — ẩn noti do CHÍNH người login gây ra (2026-07-02)
- **Bối cảnh / vì sao**: user tự tạo task / đổi status / comment rồi thấy lại noti của chính mình trong chuông — nhiễu, vô nghĩa. Áp cho CẢ admin lẫn member.
- **Cách làm** (`qa_dashboard.py`): helper `_drop_own_activities(merged, email)` — map email login → username (`username_from_email`) + tên rút gọn (`display_name`), loại activity mà `by == username` (custom-status events có field `by`) HOẶC `author == tên rút gọn` (feed Jira chỉ có `author`, resolve QA username về đúng `display_name` qua `actor_name`). Gọi ngay sau khi `merged` được sort, TRƯỚC khi gán `is_unread`, ở **2 nguồn chuông**: `_bell_activities()` (poll `/activity-feed` + tab my-work/docs/roadmap/bug-log) và render canonical `/` trong `_get_dashboard()`.
- **RANH GIỚI có chủ đích**: CHỈ lọc **danh sách notification** (`merged`). Phần `tasks` patch (status Jira + nhãn custom real-time, Decision #24) KHÔNG đụng → tự đổi status vẫn thấy bảng/drawer/KPI cập nhật ngay, chỉ không nhận noti của mình. ⚠ ĐỪNG "sửa gọn" bằng cách lọc luôn ở nguồn feed/patch — sẽ mất real-time patch.
- **Giới hạn**: không xác định được người login (local dev / email không khớp QA nào → `username_from_email` trả None) → giữ nguyên toàn bộ. System event (`by='system'`, tự gỡ nhãn khi DONE) không bị ảnh hưởng. Cần **restart app** (code Python, không hot-reload).
- **Verify** (không mạng): `py_compile` OK; smoke `_drop_own_activities` — login thanhht1: lọc đúng noti mình (author='Thành' và by='thanhht1'), giữ người khác + system; email rỗng: giữ tất cả.

### 35. Đổi Due date inline (bảng + drawer) — gate theo QUYỀN Jira, ghi bằng PAT cá nhân (2026-07-03)
- **Bối cảnh / vì sao**: user muốn đổi hạn task ngay trên workspace nhưng phải TÔN TRỌNG quyền Jira — ai được sửa trên Jira thì cho, không thì không. Cùng class với đổi status/comment (Decision #20): ghi bằng **PAT cá nhân** → Jira tự attribution + tự enforce quyền. Bổ sung (cùng ngày): user chốt **đổi được NGAY trên bảng dashboard**, không cần mở drawer chi tiết.
- **2 tầng enforce (backend)**:
  - **Gate UI** = `GET editmeta` bằng PAT cá nhân (`jira_write.can_edit_duedate`): Jira trả tập field CHÍNH user hiện tại được sửa trên issue đó (đã tính Edit Issues permission + field/workflow config). `'duedate' in fields` → được sửa. Route POST `/duedate-perm` → `{ok, canEdit}`.
  - **Enforce thật** = `PUT /issue/{key} {fields:{duedate}}` bằng PAT cá nhân (`jira_write.set_duedate`): không đủ quyền → Jira 403/400, KHÔNG ghi được. Route POST `/set-duedate`. `duedate=''`/None → xoá hạn (`null`). Cả 2 route đi qua `_handle_jira_write` (WriteMixin) nên **không có PAT → từ chối `no_pat`** (nhắc vào Cài đặt) như các thao tác ghi khác.
- **UI (`app_v2.js`)** — helper DÙNG CHUNG ở outer scope, áp cho CẢ ô Hạn trong **bảng** (admin `render_admin_v2` + QA `render_qa_v2`/my-work) LẪN **drawer** (admin/QA/fallback roadmap-docs):
  - `dueValHTML(t)` = cụm `<span class="due-cell" data-act="due-edit">` (ngày + bút ✎ hiện khi hover) — nhúng vào cột Due Date của bảng + ô "Hạn chót" của drawer.
  - **Check quyền LAZY lúc BẤM** (không hỏi trước từng dòng → tránh N call editmeta/trang): `ensureDuePerm(key)` cache `DUE_PERM`; bấm ô → nếu `true` mở input date + Lưu/Huỷ (`dueEditor`), nếu `'no_pat'` → mở modal Cài đặt, nếu không có quyền → toast "không có quyền".
  - `due-save` → POST `/set-duedate` → `window.__applyDuePatch(key,val)` (mỗi branch cập nhật TASKS/CUR qua `recomputeDue` + renderRows/KPI) + `dueAfterChange` (drawer thì re-render drawer, bảng thì `window.__rerenderRows`). KHÔNG reload.
  - **Chống mở drawer nhầm**: admin tbody row-click bỏ qua khi target trong `.due-cell` (`if(e.target.closest('.due-cell')) return;`); QA/fallback dùng data-act delegation nên không đụng.
  - CSS `.due-cell/.due-pen/.due-input/.lbtn.due-btn` trong `styles_v2.css`.
- **Giới hạn**: affordance ✎ hiện cho MỌI người (không eager-hỏi quyền); quyền chỉ kiểm khi bấm (lazy) → người không đủ quyền bấm sẽ bị toast từ chối (enforce thật ở `/set-duedate` vẫn chặn tuyệt đối). Chưa có PAT → không sửa được. Bảng/KPI cập nhật client gần đúng theo `recomputeDue`; số chuẩn tuyệt đối chỉ sau F5. Cần **restart app** (route Python mới; JS/CSS hot-reload per-render).
- **Verify** (không mạng): `py_compile` qa_dashboard/jira_write/routes.write OK; import `set_duedate`/`can_edit_duedate` OK; bracket-balance `app_v2.js` ngang HEAD.

### 36. Tồn đọng T-1 định danh theo FINGERPRINT nội dung (bền qua copy sang sheet tháng mới) (2026-07-07)
- **Bối cảnh / vì sao**: Decision #33 chốt snapshot theo THÁNG TẠO, khoá theo `key` sheet = `{project}#{service}#{sheet}#{STT}`. Khi team copy bug tồn sang sheet tháng mới (mùng 1–3), `sheet` + `STT` đổi → `key` đổi hoàn toàn → bug đã copy không match snapshot cũ → đếm nhầm "không còn trong file / đã xử lý". User chốt: **định danh bug theo NỘI DUNG, không theo STT/sheet**. Đây là nguyên nhân gốc khiến số tồn đọng lệch, KHÔNG phải bug KV/persistence.
- **Kho mới `carry`** (`bug_backlog.py`, cạnh `months` cũ trong `.bug_monthly.json` + prop `qa-dashboard-bug-monthly`): `carry["YYYY-MM"]` = **TẤT CẢ bug đang MỞ cuối tháng đó** (is_open = status ∉ {Closed, Reject}, bất kể tháng tạo) = nợ mang sang tháng sau. Mỗi bug khoá bằng **fingerprint** `_fp` = `project|service|feature|summary` đã `_norm` (lower + gộp khoảng trắng + trim, **KHÔNG bỏ dấu** để Python == JS tuyệt đối). Report tháng M dùng `carry[M-1]`, đối chiếu fp với bug live: có bản live cùng fp còn mở → "còn treo"; đã đóng / không tìm thấy → "đã xử lý". Match sheet-agnostic nên bug còn ở sheet cũ HAY đã sang sheet mới đều bắt được (giải quyết giai đoạn mùng 1–3).
- **Freeze**: `archive()` (gọi mỗi scan từ `bug_log_store.scan`) overwrite `carry[now_month]` mỗi lần = bug mở hiện tại; tháng < now_month KHÔNG đụng → tự đóng băng ở lần scan CHÓT của tháng. ⚠ Cần app chạy + scan quanh cuối tháng để carry sát mốc (giống caveat #33). Dedup: chỉ ghi khi `{months,carry}` đổi.
- **`prev_month_backlog` + client `computeBacklog` (app_v2.js)**: ưu tiên `carry[prev]` (fp-match); **fallback** về `months[prev]` (key-based cũ) khi tháng đó CHƯA có carry → **2026-06/07 giữ nguyên số cũ (gần đúng)**, số chuẩn tuyệt đối từ **báo cáo T8** (chốt cuối T7 là carry đầu tiên). `_fp` phía JS (`_bnorm`/`_fpOf`) phải khớp Python — sửa 1 bên PHẢI sửa bên kia. Embed thêm `carryMonths` + field `service`/`feature` vào `analyticsData` (`_flatten_bugs`).
- **Ranh giới**: match theo nội dung → nếu team SỬA chữ mô tả/chức năng lúc copy thì fp đứt (coi như bug mới, tồn đọng cũ thành "đã xử lý"). Copy nguyên văn thì bền. Nhiều bản live cùng fp (dup lúc chuyển sheet) → còn treo nếu BẤT KỲ bản nào còn mở. Cần **restart app** để archive ghi carry (JS/CSS hot-reload per-render).
- **Verify** (không mạng): `py_compile` bug_backlog + analytics OK; smoke fp-match (copy sheet đổi key vẫn còn-treo, 1 close→đã-xử-lý, 1 gone→đã-xử-lý, new_count đúng) + fallback months khi thiếu carry + `archive` chỉ ghi bug mở vào `carry[now]` + đóng băng tháng quá khứ nguyên vẹn; `_norm` parity với JS; bracket-balance `app_v2.js` ngang HEAD.

### 37. Link bug↔task bền qua copy sang sheet mới — resolve theo FINGERPRINT, bản mới nhất thắng (2026-07-07)
- **Bối cảnh / vì sao**: link bug↔task (`task_link.py`) khoá theo **bug key** = `{project}#{service}#{sheet}#{STT}`. Drawer của task hiển thị "Bug liên quan" bằng cách tra ngược `links` → lấy bug theo đúng key (`_bugs_for_task`, qa_dashboard). Khi team copy bug tồn sang sheet tháng mới, `sheet`+`STT` đổi → key đổi → link cũ trỏ dòng tháng cũ: dòng cũ bị xoá → task MẤT bug; dòng cũ còn → task hiện **status CŨ**, không phản ánh việc dev fix/đóng bug ở dòng THÁNG MỚI. CÙNG nguyên nhân gốc Decision #36 (khoá STT/sheet không bền qua copy) nhưng cho lớp **link ngược task**.
- **User chốt**: (a) khi cả 2 bản còn trong file → task phản ánh **bản MỚI NHẤT** (created lớn nhất); (b) cơ chế **read-time resolve** (non-destructive, KHÔNG mutate kho link — khác lựa chọn "migrate key").
- **Fingerprint dùng chung**: public hoá `bug_backlog.fingerprint(bug)` (= `_fp` cũ: `project|service|feature|summary` đã `_norm`) làm single source of truth. `task_link` + `qa_dashboard` import từ đây (KHÔNG nhân bản `_norm`). Không cycle: `bug_backlog` không import `task_link`.
- **Stamp fp vào link entry** (`task_link.py`): entry giờ có `fp` (ngoài `tasks/by/at`). ⚠ Một khi dòng bug gốc bị xoá khỏi file thì KHÔNG suy lại fp từ key (key không chứa summary/feature) → PHẢI chốt fp trong khi dòng gốc còn trong file. 2 nơi stamp: (1) `set_task_links` op='add' — lookup bug live (`_live_bug_index`, lazy `load_bug_log`) tính fp lúc tạo link; (2) `backfill_fingerprints(cur_bugs)` gọi từ `bug_log_store.scan()` (cạnh `archive`, soft-fail) — stamp cho MỌI link cũ đang thiếu fp khi key còn khớp bug hiện tại. `fp_of(link_val)` = helper đọc fp (migration-safe: link cũ string/thiếu fp → '').
- **Read-time resolve** (`_bugs_for_task`, qa_dashboard): build `by_key` + `by_fp` từ bug live; mỗi entry link tới task → gom candidate = bug cùng key HOẶC cùng fp → chọn `max(created)` (bản mới nhất) → lấy status bản đó. Dedupe theo fp bug đã resolve (nhiều entry trỏ cùng bug). fp rỗng (chưa backfill) → vẫn resolve theo key như cũ (không hồi quy).
- **Ranh giới / chưa làm**: (a) CHỈ sửa drawer task (`_bugs_for_task`). **Bảng Bug Log** (`render_bug_log_v2`) vẫn hiện chip link theo key thật → dòng copy tháng mới CHƯA hiện chip (tránh rối edit theo key); nếu cần đồng bộ chip sau thì fp-aware cả render + set. (b) Team SỬA nội dung lúc copy → fp đứt (giống #36). (c) Cần **restart app** + ≥1 scan khi dòng gốc còn trong file để backfill fp cho link cũ (dòng tháng cũ thường giữ làm history → có thời gian). JS/CSS hot-reload; drawer render server-side nên KHÔNG cần đụng `app_v2.js`.
- **Verify** (không mạng): `py_compile` qa_dashboard/task_link/bug_backlog/bug_log_store OK; smoke: fp bằng nhau qua copy (STT/status đổi) + khác khi sửa summary; resolve chọn bản tháng mới đã Closed khi cả 2 còn; resolve qua fp khi dòng cũ bị xoá; `fp_of` migration-safe (string cũ/thiếu fp → '').

### 38. UI overhaul đợt 1 — design tokens + motion + skeleton + View Transitions (2026-07-07)
- **Bối cảnh**: user yêu cầu overhaul toàn app (đẹp + mượt + thông minh), plan 3 nhánh đã duyệt. Nhánh 1 = visual/motion (nhánh 2 = command palette + quick actions, nhánh 3 = insight "Cần chú ý hôm nay" — làm sau). Branch `feat/ui-overhaul-visual`.
- **Token refresh (`styles_v2.css` :root, ADDITIVE — KHÔNG rename token cũ)**: spacing `--sp-1..8`; radius thêm `--r-2xl` (drawer/modal), `--r-lg` .5→.625rem; elevation scale `--e1/e2/e3` (`--shadow` = alias `--e2`; dark có inset top-highlight); motion `--dur-1/2/3` + `--ease-out/--ease-emphasized`; `--primary-hover` (GIỮ `#0052cc` primary); light `--canvas`→`#f5f6f8`; dark tăng contrast `--outline-variant`→`#313d4f`, `--divider`→`#26303f`. Dark badge `b-critical/b-high` → tinted bg + colored text (hết chói).
- **Typography**: font stack thêm `"Segoe UI"` fallback (host Windows); `_FONTS_V2` (shell.py) → Inter variable `wght@400..700`; `tabular-nums` mọi ô số (số không nhảy khi re-render); page-title 32→28px.
- **Motion**: `@media (prefers-reduced-motion: reduce)` tắt toàn bộ; sidebar active = pill `::before` animate + `view-transition-name:nav-active` (morph qua trang); badge chuông `.pulse` khi unread TĂNG; theme toggle bọc `document.startViewTransition` (fallback class `theme-anim` 350ms) — `applyTheme(t, animate)` chỉ animate khi user bấm, KHÔNG lúc load.
- **Cross-page = MPA View Transitions API** (`@view-transition{navigation:auto}`; sidebar/topbar có view-transition-name riêng → chrome đứng yên, content fade 180ms). CHỌN thay vì fetch-soft-nav vì ~40 inner IIFE chạy lúc parse + document-level listener → re-init sẽ duplicate handler. Firefox bỏ qua vô hại. Kèm **`.nav-progress`** bar 2.5px (shared IIFE): hiện khi click `.nav a`/`.pmenu a`, reset trên `pageshow` (bfcache).
- **Skeleton** (`.skel` shimmer + `.skel-line/badge/av/block/row`, helper `skelDrawer()/skelComments()`): thay MỌI text "Đang tải…" ở drawer (3 chỗ), comment history (4), global-search dropdown, status menu (2), Drive check (shell).
- **Row stagger**: `animRows(tbody)` + CSS `tbody.anim tr` nth-child 1-8 delay 0-140ms, exclude `.pager-filler`/`.tc-filler`. `renderRows(anim)` admin + QA: **anim=true CHỈ ở thao tác user** (pill/filter/search/pager/initial), KHÔNG ở `__applyTaskPatch` poll 60s (tránh nhấp nháy). Bug-log/docs/test-cases gọi vô điều kiện (chỉ render khi user thao tác).
- **QA table thêm filler rows** (7 cột) giống admin → pager không nhảy trang cuối.
- **Toast rewrite**: `toast(msg, ok)` GIỮ signature (~40 call site không đổi) nhưng stack tối đa 3 trong `#toastWrap` (JS tự tạo; đã GỠ `<div id="toast">` khỏi cả 2 shell), icon check_circle/error, tự huỷ 2.6s.
- **Empty states**: pattern `.empty-state` = `.es-ic` icon-circle 64px + `.es-title` + `.es-hint`. Áp: bảng admin (FIX luôn colspan 6→7 vốn lệch sẵn), bảng QA, bug-log tháng rỗng, leader-eval.
- **KHÔNG đụng**: `styles.css` (legacy error page), threshold workload, poll 60s, palette Atlassian blue.
- **Verify**: py_compile OK; bracket-balance app_v2.js ngang HEAD; render tĩnh admin+QA (script scratchpad, pattern gen_preview cũ) → 0 lỗi console, dark/light đúng token mới, stagger/filler/progress-bar chạy. ⚠ shell.py + leader_eval.py đổi → cần **restart app** (JS/CSS hot-reload per-render).

### 39. Command palette Ctrl+K + quick actions mọi nơi (smenu dùng chung) (2026-07-07)
- **Bối cảnh**: nhánh 2 của overhaul (plan đã duyệt). Branch `feat/smart-palette-actions` (stack trên `feat/ui-overhaul-visual` — cùng đụng app_v2.js).
- **Refactor smenu dùng chung (nền tảng, XOÁ ~160 dòng duplicate)**: 2 bản copy smenu (admin/QA controller) lift thành module shared trong app_v2.js: `window.__openSmenu(caret, task, {onChanged})` + `window.__smSetCustom(t, key, val, onChanged)` + `window.__smRebind()` (bám lại caret sau rebuild bảng — thay 2 khối rebind cũ). Module own: render/position menu, fetch `/jira-transitions`, `/do-transition`, `/set-custom-status`, inflight, click-outside/scroll/Esc close (bind 1 lần). **Task obj mutate tại chỗ** (t.jira/t.customs/t.canCustom — giờ transition cũng cập nhật canCustom) → controller chỉ cần re-render trong `onChanged(kind, key, payload)` (admin: counts+rows+KPI+drawer; QA: rows+drawer; fallback: drawer). PAT model giữ nguyên (no_pat → mở Settings modal).
- **`#smenu` + `QA_CUSTOM_STATUSES` + `window.__isAdmin` chuyển lên shell** `_document_v2` (mọi trang v2 có; GỠ khỏi render_admin_v2/render_qa_v2 — hết duplicate ID). `__isAdmin` = UI hint gate command admin-only; server route vẫn là enforce thật.
- **Drawer caret status ở CẢ 3 drawer renderer** (admin/QA/fallback) → đổi status/nhãn từ drawer trên MỌI trang (roadmap/docs/bug-log/analytics). `synthTask`/`synth` giờ derive `canCustom` từ status fetch (trước hardcode false). ⚠ Giới hạn fallback: customs ban đầu không có trên trang ngoài dashboard (`/issue-comments` không trả overlay) — checkmark nhãn chỉ đúng sau lần đổi đầu.
- **Command palette Ctrl+K** (`_palette_modal_v2` shell + module JS đặt NGAY SAU global-search — TRƯỚC các Esc handler khác để `stopImmediatePropagation` không đóng nhầm drawer/smenu): 4 nhóm — **Điều hướng** (mirror sidebar, admin-only entries theo `__isAdmin`) + **Hành động** (Tạo Sub-task / đổi theme / Cài đặt PAT / Sync bug log[admin]) filter tức thì; **Task Jira** (`/global-search` reuse, cap 8) + **Bug** (`/search-bugs` MỚI) async 300ms debounce, 2 fetch song song, stale-guard seq. Enter task → `__openDetail` (drawer tại chỗ mọi trang); Enter bug → `/bug-log?bug=<key>`. Match **accent-insensitive**: `norm()` = lower + NFD strip combining + **`đ→d`** (NFD KHÔNG decompose đ/Đ — bug đã dính lúc verify, "danh gia" không match "Đánh giá"; Python `_fold` phải parity — sửa 1 bên PHẢI sửa bên kia).
- **`GET /search-bugs`** (qa_dashboard → `bug_log_store.search_bugs(q, limit=10)`): scan cache local (`_load_data`), match fold trên id hiển thị (`project-service-bug_no`) + summary + feature, sort created desc. **0 call Jira/Drive, 0 PAT**; handler nuốt mọi lỗi → trả rỗng (không 500). Query <2 ký tự → [].
- **Deep-link `/bug-log?bug=<key>`** (copy pattern `?folder=` test-cases): set activeFid theo bug (validate SOURCES) + curMonth + clear filter (cả select DOM) + nhảy đúng trang → `row-flash` highlight 2.2s + scrollIntoView. Row bug-log giờ mang `data-bug`. Không tìm thấy → toast.
- **Row hover actions**: ~~admin — `.row-acts` overlay góc phải cell Updated (mở drawer + mở Jira)~~ **ĐÃ GỠ (2026-07-08, user yêu cầu)** — thừa: bấm dòng đã mở drawer detail, bấm ID (`.cell-key`) đã ra link Jira. Xoá `.row-acts`/`.ra-btn`/`.cell-acts` khỏi `app_v2.js` (cột Updated về `<td class="cell-date">` thường) + CSS. QA — nút "Xem chi tiết" cạnh nút bình luận (delegation data-act="detail" sẵn có) GIỮ nguyên.
- **Bulk actions = DEFER** (Jira DC không có bulk-transition REST; N call tuần tự + transition set khác nhau per workflow + partial-failure UX đắt — team 5 người không đáng. `__openSmenu`/`smDoTransition` chính là primitive nếu sau cần).
- **Verify**: py_compile OK; bracket-balance ngang HEAD (false positive docs breadcrumb quen thuộc); preview tĩnh admin+QA — Ctrl+K mở/đóng, filter không dấu ("danh gia"→"Đánh giá"), ↑↓/Esc, smenu mở+toggle từ row caret + drawer caret cả 2 lens, row-acts hiện, 0 lỗi console; smoke `search_bugs('thanh toan')` trên cache thật ra 5 bug đúng; `_fold` parity test. ⚠ Route + shell đổi → cần **restart app**.

### 40. Insight "Cần chú ý hôm nay" — server-computed, dashboard admin (2026-07-07) — ❌ ĐÃ GỠ (2026-07-08)
- **GỠ HẲN (2026-07-08, user yêu cầu)**: user thấy card insight không thêm giá trị cho admin (dashboard đã đủ thông tin để nhìn ra việc cần làm). Đã xoá: `core/insights.py`; `_insights_block` + param `insights` xuyên `render_page`/`render_admin_v2` + call site (`core/render/dashboard.py`); import + wiring `compute_insights` (`qa_dashboard.py`); IIFE collapse + `qa-ins-collapsed` (`assets/app_v2.js`); CSS `.ins-*` (`assets/styles_v2.css`). Cần **restart app**. Mô tả bên dưới giữ làm lịch sử.
- **Bối cảnh**: nhánh 3 (cuối) của overhaul. Branch `feat/smart-insights` (stack trên `feat/smart-palette-actions`).
- **`core/insights.py`** — pure function `compute_insights(data, buglog) -> [{icon, severity: crit|warn|info, text, keys(≤3), href}]`, 0 network 0 state (triết lý issues.py). Input = data đã fetch ở `/` + cache bug log → **0 Jira call thêm**. Constants: `WORKLOAD_HIGH=15/WORKLOAD_LOW=4` (Decision #5, KHÔNG đổi), `REOPEN_ALERT=2`, `MAX_ITEMS=8`. 6 rule:
  1. Quá hạn (crit) — top 3 keys theo ngày quá hạn (business days).
  2. Sắp tới hạn (warn) — due hôm nay/ngày làm việc kế, **EXCLUDE task đã quá hạn** (không đếm đôi).
  3. Kẹt ≥ STUCK_DAYS (warn) — top 3 theo days_since_update.
  4. Quá tải per person (crit khi ≥15 active, 1 item/người) + info "nhẹ việc, cân nhắc chia lại" khi có người ≤4 TRONG KHI có người quá tải.
  5. Bug reopen ≥2 lần THÁNG HIỆN TẠI (warn, cap 3, sort count desc) — `href=/bug-log?bug=<key>` với key **PHẢI `quote(key, safe='')`** (key chứa `#` → không quote là browser cắt thành fragment; bug đã dính lúc verify. Palette JS dùng encodeURIComponent sẵn — parity).
  6. Backlog trend: vào > ra tuần (warn nếu chênh ≥5, else info; cả hai =0 → skip).
  Rank crit→warn→info; MỌI rule bọc `safe()` → lỗi là skip rule, KHÔNG BAO GIỜ vỡ render.
- **Wiring** (`_get_dashboard`): `insights = compute_insights(data, buglog) if scope is None else []` (CHỈ lens quản lý; QA non-admin + `/my-work` không có) → `render_page(..., insights=)` → `render_admin_v2` (kw default None; nhánh jira_error return sớm không đụng). `insights=None` → không render block (caller khác không vỡ); `[]` → dòng ✓ "Không có gì cần chú ý".
- **Render** (`_insights_block`, dashboard.py): card giữa page-head và status pills. Item = icon + text + chip: `[data-key]` mở drawer (delegation trong admin controller → `openDetail`), `[href]` = link thường (reopen → bug-log deep-link #39). **Collapse, KHÔNG per-item dismiss** (dismiss cần server state per-day mà item tự tính lại mỗi load — không đáng): `#insToggle` toggle class + `localStorage qa-ins-collapsed`.
- **CSS**: `.ins-card/.ins-head/.ins-item.sev-{crit,warn,info,ok}` (border-left + tinted bg theo severity), `.ins-chip` mono pill. JS ~15 dòng trong admin branch.
- **Verify**: py_compile OK; unit test 6 rule (quá tải 16 task→crit + nhẹ việc info, defensive data rác không raise, cap 8, sắp-hạn exclude quá hạn, reopen chỉ tháng hiện tại + cap 3 + href quoted không còn `#`, backlog warn khi chênh ≥5); render preview tĩnh: 6 item đúng severity, chip mở drawer đúng key, collapse persist localStorage, href encoded. ⚠ Cần **restart app** (module + wiring Python mới).

### 41. Pager đồng bộ toàn app — helper `pagerHTML` dùng chung (2026-07-08)
- **Bối cảnh / vì sao**: 4 bảng có pagination nhưng 4 kiểu khác nhau: Dashboard admin (numbered + ellipsis + range) · Việc của tôi/QA (`.pinfo` + chỉ `‹Trước/Sau›`, KHÔNG số trang) · Bug Log (numbered nhưng render MỌI số, không ellipsis, chỉ "trang X/Y") · Test Cases (numbered + ellipsis, DOM-build từng nút + listener riêng). User yêu cầu **đồng bộ toàn webapp** và chốt **GIỮ nút số trang** (không hạ về kiểu Trước/Sau của Việc-của-tôi) → chuẩn hoá LÊN kiểu numbered polished của admin.
- **Cách làm**: thêm helper shared `pagerHTML(page, pages, total, start, count, unit)` ở đầu IIFE ngoài cùng `app_v2.js` (cạnh `esc`/`$`/`readJSON`) → sinh MARKUP chuẩn: `<span class="pager-summary">N–M / total <unit> · trang X/Y</span>` + `.pager-nav` (nút số `.pager-page` + ellipsis `…` với `win=1` + mũi tên `.pager-btn`). `data-pg` = **số trang TUYỆT ĐỐI**; container bắt click qua delegation (`if(!b||b.disabled) return; page=parseInt(data-pg)||1`).
- **4 call site** đều 1 dòng `container.innerHTML = pagerHTML(...)`: admin (`unit='task'`, hành vi y hệt trước — đây là bản gốc trích ra), QA/my-work (`'task'`, **đổi click từ delta `curPage+=` sang tuyệt đối** + thêm nút số), Bug Log (`'bản ghi'`, hiện cả khi 1 trang, thêm range+ellipsis), Test Cases (`'test case'`, bỏ DOM-build + per-button listener → 1 listener delegated bind 1 lần trên `#tcPager`).
- **Template đổi**: `core/render/testcase.py` — `#tcPager` bỏ 2 con `#tcPagerInfo`/`#tcPagerNav` (giờ `pagerHTML` ghi thẳng vào `#tcPager`). ⚠ Đổi template Python → cần **restart app** cho trang Test Cases; JS pager (dashboard/my-work/bug-log) hot-reload theo F5 (load_js_v2 đọc per-render).
- **KHÔNG đụng CSS**: dùng lại nguyên `.pager-summary/.pager-nav/.pager-page/.pager-btn/.pager-ellipsis` (styles_v2.css ~674) mà admin/bug-log/test-cases đã dùng → My-Work giờ khớp y hệt. `.pinfo` + `.pager button` cũ thành dead CSS (vô hại, giữ lại). Filler rows của từng bảng KHÔNG đụng.
- **Verify** (không mạng): `node --check app_v2.js` + `ast.parse testcase.py` OK; unit-test `pagerHTML` (1 trang; p1/7 `*1* 2 … 7`; p4/7 `1 … 3 *4* 5 … 7`; p7/7 `1 … 6 *7*`; range trang cuối lẻ đúng). Chưa chạy live browser (cần VPN+PAT).

### 42. Test Case sync — chế độ "ghi đè cả kết quả" (ô Result trống → norun) (2026-07-08)
- **Bối cảnh / vì sao**: Smart Sync (`_apply_sheet_cases`, testcase_store.py) CỐ Ý giữ result đã chấm tay khi ô Result trong sheet để TRỐNG (bảo vệ công chấm khi re-import nội dung). Hệ quả: user xoá kết quả trong Google Sheet rồi sync lại → dashboard KHÔNG đổi (ô trống = giữ cũ). User muốn 1 chế độ đảo lại để phản ánh việc xoá kết quả.
- **Cách làm**: thêm flag `overwrite_results` (default False, tương thích ngược) xuyên `_apply_sheet_cases(...,overwrite_results)` → `import_cases(...,overwrite_results)` → routes `/tc-sync` + `/tc-sync-all` (đọc `overwrite_results` từ body). Khi True: ô Result trống ép `'norun'` (thay vì giữ `r_norm` cũ) ở CẢ 3 pass Smart Sync (LCS align / fuzzy / ID fallback); ô Result CÓ giá trị vẫn luôn theo sheet (không đổi). `updated_result_count` cộng cả lần reset về norun.
- **Phạm vi (user chốt)**: áp cho **Sync 1 bộ** (nút sync trong cây) + **Sync tất cả**. KHÔNG áp cho Import thủ công (modal Import) — import mới folder rỗng không có result cũ để bảo vệ.
- **UI** (`app_v2.js` + `core/render/testcase.py`): modal xác nhận dùng chung `#tcSyncOverlay` (checkbox `#tcSyncOverwrite`, mặc định BỎ chọn = giữ kết quả) mở bởi cả nút sync-per-folder lẫn `#tcSyncAllBtn`. `doTcSync(fid, overwrite)` / `doTcSyncAll(overwrite)` truyền `overwrite_results` vào body. `openSyncModal(mode, fid)` có fallback gọi thẳng (giữ hành vi cũ) nếu template chưa có modal (chưa restart). Đường link-modal (`update_import_url` → `doTcSync(fid)`) giữ default = không ghi đè.
- **Giới hạn**: nếu team xoá NGUYÊN DÒNG test case (không phải chỉ ô Result) thì dòng đó biến mất sau sync bất kể flag — flag chỉ chi phối ô Result trống. Cần **restart app** (route đọc body + template modal mới); JS hot-reload theo F5.
- **Verify** (không mạng): `py_compile` qa_dashboard/testcase_store/render.testcase + `node --check app_v2.js` OK; smoke `_apply_sheet_cases`: keep-mode giữ pass/fail (updated=0), overwrite-mode reset norun (updated=2), overwrite vẫn theo sheet khi ô có giá trị. Chưa chạy live browser (cần VPN+PAT+Drive).

### 43. Bug Log changelog — khử noise transition "→ New" (copy-paste tạo bug mới) (2026-07-09)
- **Bối cảnh / vì sao**: changelog bug-log (`_diff_events`, bug_log_store.py) sinh event "Status X → Y" theo diff status giữa 2 lần scan, khoá theo STT (`{project}#{service}#{month}#{bug_no}`). QA hay tạo bug mới bằng cách **copy dòng bug cũ ở trên xuống dòng mới rồi sửa lại nội dung**. Dòng mới thừa hưởng status của bug được copy (vd `Closed`) trước khi bị sửa về `New` → nếu 2 sự kiện rơi vào 2 cửa sổ scan khác nhau, diff bắt được **transition giả** `Closed → New` (hoặc `<status bất kỳ> → New`) → feed/chuông/popup "sau đồng bộ" đầy noise.
- **Fix**: trong `_diff_events`, **bỏ qua mọi transition có đích = `'New'`** (thêm điều kiện `and (b.get('status') or '') != 'New'` ở nhánh status-change). Lý do đúng: vòng đời bug thật KHÔNG bao giờ quay lại `New` (New chỉ là trạng thái khởi đầu; reactivation dùng `Reopen`) → mọi `→ New` là artifact copy-paste.
- **KHÔNG đụng**: event `log bug` (khi key lần đầu xuất hiện, `old is None`) VẪN giữ — đó là bug mới thật, đáng lên feed. Event `xoá bug` + các transition hợp lệ khác (New→Fixing, Closed→Reopen, …) không đổi.
- **Đánh đổi**: bug bị QA sửa nhầm rồi reset về `New` sẽ không lên feed — hiếm, user coi mọi `→ New` là noise nên chấp nhận. Giới hạn: nếu artifact copy-paste kết thúc ở status KHÁC `New` (vd copy bug Closed rồi để nguyên Fixing) thì không khử được — nhưng bug mới luôn khởi đầu ở `New` nên `→ New` là chữ ký tin cậy.
- **Verify** (không mạng): `py_compile` OK; smoke `_diff_events`: new bug→giữ `log bug`; `Closed→New`/`Fixing→New`→rỗng (suppressed); `New→Fixing`/`Closed→Reopen`→giữ.

### 44. Test Case sync — dọn sheet đã xoá khỏi file (mirror Drive 100%) (2026-07-09)
- **Bối cảnh / vì sao**: donut "Tổng số TC" (đếm `data['cases']`) > số báo khi sync (`total_count`). Gốc rễ = **case mồ côi**: `_apply_sheet_cases` ghi đè cases THEO TÊN SHEET, nhưng CHỈ chạy cho sheet đang có trong file. Sheet đã **XOÁ / ĐỔI TÊN** khỏi file Google (vd tab duplicate `"Copy of T7"`) thì sub-folder + cases cũ của nó KHÔNG bao giờ bị đụng → tồn mãi trong store, donut vẫn cộng. Ca thật: Chi Hộ store 217 vs sync 181 = 36 case mồ côi trong sheet `Copy of T7`. Reload không chữa (data thật trong store, không phải stale render). User chốt **hệ thống phải phản ánh Drive giống 100%**.
- **Fix** (`core/testcase_store.py`, trong `import_cases`, SAU guard `if not applied` + check MAX_CASES): **CHỈ khi sync TOÀN FILE** (`sheet == ''`) → xoá mọi sub-folder trực thuộc `folder_id` mà **tên KHÔNG còn trong `all_sheets`** (danh sách tab hiện tại của file), cascade n-level (phòng folder con) + xoá cases + `imports.pop`. KHÔNG áp cho **sync 1 sheet** (chỉ đồng bộ đúng sheet đó, không được đụng sheet khác). Đặt sau `if not applied` → tải hỏng/không sheet nào hợp lệ thì return sớm, KHÔNG nuke store.
- **Trả về + báo cáo**: dict thêm `removed_sheets`/`removed_cases`; msg (sync 1 bộ) + modal sync-all (`_post_tc_sync_all`, qa_dashboard) liệt kê sheet đã dọn + tổng case dọn.
- **Đánh đổi**: **đổi tên sheet = coi như xoá + thêm mới** → mất result đã chấm của sheet đó (Smart Sync giữ result theo NỘI DUNG trong cùng sub-folder, nhưng sub-folder khoá theo TÊN sheet nên đổi tên = đứt). User chấp nhận để mirror tuyệt đối. Giới hạn CHƯA xử (giữ hành vi cũ, bảo vệ): **sheet còn trong file nhưng rỗng** (`empty_sheets`) hoặc **mất header** (`no_header`) → cases cũ VẪN giữ (không mirror về 0) — tránh mất grading khi file đang sửa dở/tải lỗi transient. Nếu sau cần mirror cả 2 ca này thì phải cân nhắc lại risk.
- **Verify** (không mạng): `py_compile` qa_dashboard + testcase_store OK; smoke offline (monkeypatch Drive layer): (1) file xoá `Copy of T7` → sub-folder + 36 orphan bay, T7 refresh, `removed_sheets=['Copy of T7']`; (2) sync 1 sheet `T7` → KHÔNG đụng `Copy of T7`; (3) whole-file còn đủ sheet → xoá 0. ⚠ Cần **restart app** (route + store Python đổi; JS/CSS hot-reload).

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
- ✅ New badge (admin dashboard): task `created == hôm nay`, stateless (KHÔNG còn `.last_seen.json` — Decision #27)
- ✅ Hyperlink to Jira (`{JIRA_URL}/browse/{key}`)
- ✅ UTF-8 Vietnamese rendering
- ✅ Error handling: 401, 403, network error, port-in-use

### Tested
- Logic: `parse_date`, `status_class`, `days_overdue`, `esc`, `issue_link`, `display_name`
- Render: 23 active + 5 new24 + 2 done → HTML 17KB, no errors
- Workload edge case: Nhung 15 task → đúng badge ⚠ QUÁ TẢI

### Known Limitations
- Pagination: max 300 active tasks, 50 new24, 100 done_week. Nếu team mở rộng phải tăng.
- ~~Single-threaded server (`socketserver.TCPServer`). 1 request blocks 1 user.~~ ✅ FIXED (issue #129, 2026-06-16): đổi `ThreadingHTTPServer` + `daemon_threads` — request chậm không còn đơ tab khác (Decision #28). An toàn vì stores đã có lock + `atomic_write` tmp-name theo thread.
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
│   ├── docs.py            ← Tài liệu: cây folder+link, load/save .docs_config.json (sync Jira property), valid_tree
│   ├── roadmap.py         ← Roadmap team: giai đoạn›mục›sub-task, due_alerts, load/save .roadmap_config.json (sync Jira property)
│   ├── bug_log.py / bug_log_source.py / bug_log_store.py  ← Bug Log (#55)
│   ├── task_link.py / drive_token.py / monthly_reporter_chat_app.py
│   └── render.py          ← toàn bộ render_*. UI v2 (Decision #19): render_page (dispatch admin/QA), render_sidebar_v2/topbar_v2/_document_v2/render_admin_v2/render_qa_v2/render_roadmap_v2/render_bug_log_v2/render_docs_page/render_settings_page/render_leader_eval_page. load_css/load_css_v2/load_js_v2 đọc từ ASSETS_DIR.
│
├── assets/            ← asset tĩnh, đọc per-render (qua config.ASSETS_DIR)
│   ├── app_v2.js / styles_v2.css  ← UI v2 (Stitch sidebar) (Decision #19)
│   └── styles.css         ← chỉ còn render_error_page dùng (qua load_css)
│
├── scripts/           ← tiện ích offline (tự thêm ../core vào sys.path)
│   └── run_monthly_report.sh
│
│   ── auto-generated / KHÔNG trong git (sinh ở ROOT, gitignore) ──
├── .env               ← PAT + config thật + GOOGLE_*/SESSION_SECRET
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
