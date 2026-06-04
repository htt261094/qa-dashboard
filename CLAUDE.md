# CLAUDE.md

Context for Claude Code khi làm việc trên project này.

## Project Purpose

Custom HTML dashboard cho team QA Bảo Kim, pull data live từ Jira qua REST API. Thay thế cho Jira native dashboard (xấu, buggy, không merge cell được, không có conditional formatting).

**User là Acting QA Manager**, đang quản lý 5 QA trong thời gian QA Manager (Hiền) maternity leave. Dashboard này phục vụ briefing hàng ngày + acting management.

## Tech Stack

- Python 3.8+ (walrus operator dùng được)
- Only external dep: `requests`
- Local HTTP server: `http.server` stdlib (KHÔNG Flask — quyết định giữ deps tối thiểu)
- Server-side render HTML với string templates
- **Vanilla JS inline** cho phần interactive (chart hover %, pagination 5/trang). OK dùng JS thoải mái — chỉ KHÔNG dùng framework (React/Vue/Svelte). Inline `<script>` trong `render_page`, không cần file .js riêng.
- State persistence: 1 file JSON local (`.last_seen.json`)

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

### 8. Tab "Báo cáo tuần" = route riêng `/report`, KHÔNG phải in-page tab
- 2 view tách bạch: **Dashboard `/`** (operational, live, theo người) vs **Report `/report`** (theo project key, RAG, để họp/in). Top nav (`render_nav`) link giữa 2 — chuyển tab = full reload (re-pull Jira, chấp nhận như design auto-refresh).
- `/report` **read-only**: gọi `fetch_all()` nhưng KHÔNG `_build_view` (không đụng `.last_seen.json`/activities). Chỉ `/` mới update state.
- Shell chung `_document(inner)` (css/theme-init/fab/pic-modal/js) cho cả 2 page — tránh lặp boilerplate.
- Report gom theo **project key** (parse `key.rsplit('-',1)[0]`, không thêm Jira call). RAG tự suy: overdue|kẹt→🔴, TO DO≥½→🟡, else→🟢. Có 2 donut (theo dự án / theo status), bảng rollup + comp-bar CSS (không SVG, print tốt), section "Điểm cần lưu ý" liệt kê overdue+kẹt theo dự án = talking points họp.
- **In**: nút "🖨 In báo cáo" → `window.print()`; `@media print` ẩn nav/fab/modal/auto-btn → in ra chỉ nội dung report. KHÔNG dùng lib PDF.
- Delta "tuần trước vs tuần này" = **v2 chưa làm** (cần baseline đóng băng, xem Likely Next Features #4).

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
- ✅ Tab "Báo cáo tuần" (`/report`): rollup theo project key + RAG + 2 donut + talking points + in (Ctrl+P)
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
- Workload matrix giả định 3 status active: `TO DO`, `In Progress`, `PENDING`. Status mới → bucket fallback.

## Likely Next Features (user có thể yêu cầu)

Sắp xếp theo thứ tự khả năng cao → thấp:

1. **Auto-launch browser** khi chạy script (Windows `start http://...`, macOS `open`)
2. **start.bat / start.sh** wrapper để click 1 phát chạy
3. **Filter UI**: dropdown chọn assignee, status — client-side JS
4. **Report v2 — delta tuần**: "xong/trượt/mới vào từ thứ 2 trước" — cần baseline đóng băng (file `.weekly_baseline.json` chốt đầu tuần) rồi so với hiện tại. Route `/report` đã có, chỉ thêm cột delta.
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

```
qa-dashboard/
├── CLAUDE.md          ← bạn đang đọc
├── README.md          ← hướng dẫn cho user (không phải Claude Code)
├── start.sh           ← launcher macOS/Linux (check python/.env/requests → mở browser → run)
├── start.bat          ← launcher Windows (tương tự, double-click chạy được)
├── preview.html       ← mockup tĩnh để xem UI (KHÔNG có backend — save PIC sẽ fail, by design)
│
│   ── Python modules (layer: config → issues → {jira_api,state,pic} → render → entry) ──
├── qa_dashboard.py    ← ENTRY POINT: HTTP Handler (do_GET/do_POST) + main(). Mỏng.
├── config.py          ← env load, paths, JIRA_URL/PAT/USERS/PORT, DEFAULT_DISPLAY_NAMES, STUCK_DAYS, display_name/actor_name
├── issues.py          ← accessor i_* + helper (parse_date, days_*, is_stuck, esc, status_class, issue_link)
├── jira_api.py        ← gọi Jira REST (jira_search/count, fetch_change_authors, fetch_all). PAT redact ở đây.
├── state.py           ← snapshot/activities, load/save .last_seen.json, compute_activities
├── pic.py             ← PIC_DEFAULT + load/save .pic_config.json
├── render.py          ← toàn bộ render_* + load_css/load_js. 2 page: render_page (dashboard `/`) + render_report_page (`/report`), shell chung _document() + render_nav()
├── styles.css         ← toàn bộ CSS; load_css() đọc per-render, inline vào <style>
├── app.js             ← toàn bộ JS; load_js() đọc per-render, inline vào <script>
├── .env.example       ← template
├── .env               ← (KHÔNG có trong git) PAT + config thật
├── .gitignore         ← phải có .env và .last_seen.json
└── .last_seen.json    ← auto-generated, state tracking
```

## Coding Conventions

- **Đã tách module (2026-06-04)** vì vượt 1000 dòng. Layer rõ ràng, KHÔNG vòng lặp import: `config` (không phụ thuộc ai) → `issues` → `jira_api`/`state`/`pic` → `render` → `qa_dashboard` (entry). Thêm logic mới thì đặt đúng layer, đừng nhét hết vào entry.
- Import kiểu `from X import (tên cụ thể)` (không `import *`) để rõ phụ thuộc
- Entry vẫn là `qa_dashboard.py` (start.sh/.bat không đổi). Chạy `python qa_dashboard.py` → tự thêm script dir vào sys.path nên import sibling chạy được
- Section comments: `# ===== SECTION NAME =====`
- Helper functions ngắn (i_assignee, i_status, ...) — quy ước `i_` prefix cho issue field accessors
- HTML rendering: f-strings inline trong functions (`render_*`)
- CSS: toàn bộ trong `styles.css`, `load_css()` đọc per-render (sửa CSS F5 thấy ngay, không cần restart) rồi inline vào `<style>` (output tự chứa). KHÔNG inline style trừ trường hợp đặc biệt
- Vietnamese trong UI strings, English trong code/comments (mostly)
- Error messages user-facing: Vietnamese
- Error messages log: English OK

## Last Updated

2026-06-04 — Initial handoff từ chat session sang Claude Code.
