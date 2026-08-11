# CLAUDE.md

Context cho Claude Code khi làm việc trên project này.

## Project Purpose

Custom HTML dashboard cho team QA Bảo Kim, pull data live từ Jira qua REST API + đọc bug log / test case từ Google Drive. Thay cho Jira native dashboard (xấu, buggy, không merge cell, không conditional formatting).

**User là Acting QA Manager**, quản lý 5 QA trong thời gian QA Manager (Hiền) maternity leave. Dashboard phục vụ briefing hàng ngày + acting management + report tháng cho CTO.

## Tech Stack

- Python 3.8+ (walrus dùng được)
- External deps: **`requests` + `cryptography`** (Fernet mã hoá PAT/Drive token at-rest). Nguyên tắc **minimal-deps** — KHÔNG thêm Flask/FastAPI/openpyxl/PyJWT.
- HTTP server: `http.server.ThreadingHTTPServer` stdlib (Decision #28)
- Server-side render HTML bằng f-string templates, **vanilla JS, KHÔNG framework**
- Asset: `assets/app_v2.js` + `assets/styles_v2.css` (UI v2 "Stitch" sidebar — Decision #19), đọc **per-render** → sửa JS/CSS chỉ cần F5, sửa Python phải **restart app**. `assets/styles.css` chỉ còn `render_error_page` dùng.
- Kho state chéo máy: **Cloudflare Workers KV** (local-first, không cần VPN — Decision #78), fallback Jira user property + cache file local ở root.

## Architecture

```
[Browser / app Android] ←HTTP→ [Python qa_dashboard.py] ←REST+PAT→ [Jira Bảo Kim :8443]
                                (localhost:8080)        ←REST+OAuth→ [Google Drive]
                                                        ←REST+token→ [Cloudflare KV]
```

- F5 = pull data tươi (bypass SWR cache — Decision #26b); click chuyển tab = phục vụ cache SWR
- Notification tự cập nhật qua short-poll 60s (Decision #24); phần còn lại tươi khi F5

## Domain Context — Jira Bảo Kim

### Instance
- URL: `https://jira.baokim.vn:8443` · Data Center 10.7.3 (NOT Cloud, NOT Server)
- Auth: PAT via `Authorization: Bearer <token>` (DC 10.x) · REST `/rest/api/2/search`

### Workflow statuses (CHÍNH XÁC theo case + spacing)
`TO DO` · `In Progress` · `PENDING` · `DONE` · `CANCELLED` (+ `READY PRODUCTION` bên task dev)

Status categories (filter an toàn hơn tên status): `new` → TO DO · `indeterminate` → In Progress/PENDING · `done` → DONE/CANCELLED

### QA team (5 người + 1 manager)

| Username | Display name | Role |
|---|---|---|
| `quangbm` | Quang | QA |
| `nhungnh` | Nhung | QA |
| `phuongct` | Phương | QA |
| `tholt` | Thơ | QA |
| `thanhht1` | Thành | QA (acting manager, admin) |
| `hiennt19` | Hiền | QA Manager (maternity leave) |

Hiền THƯỜNG là reporter task QA team được giao (cô tạo rồi assign).

### Project keys
`PSIT*`, `DA5*`, `DA6*`, `DA2B`… — **KHÔNG hardcode project list**, filter theo `assignee`.
⚠ Jira **đổi project key mỗi kỳ nửa năm** (`DA51H26` → `DA52H26` → `DA51H27`), số issue giữ nguyên → mọi so khớp key phải qua `config.canon_key` (Decision #76).

### Task summary convention
`[QA] <description>` cho task QA. Test case (xlsx): ID | Test Item | Pre-Condition | Step | Expected Output.

---

# Key Decisions & Why

**Cách đọc**: số Decision được **tham chiếu trong comment code** → KHÔNG đánh số lại, không tái sử dụng số cũ. Entry chỉ giữ *quyết định + vì sao + ranh giới*; log verify/smoke-test đã bỏ (nằm trong git history). Decision đã chết/bị thay gom ở mục cuối.

## Nền tảng & kiến trúc

### 1. `http.server` stdlib thay vì Flask
Giảm deps, user không phải cài nhiều. Đánh đổi: không auto-reload/routing decorator. KHÔNG đề xuất chuyển Flask/FastAPI.

### 2. Bearer auth, KHÔNG Basic auth
Jira DC 10.x dùng PAT `Authorization: Bearer`. KHÔNG `email:api_token` Base64 (Cloud convention), KHÔNG cookie auth.

### 13. Session keep-alive + call Jira song song
`requests.Session` dùng chung (`jira_api._SESSION`) tái dùng kết nối TLS; `run_parallel(jobs)` (ThreadPoolExecutor cap 8) chạy các call độc lập đồng thời, re-raise lỗi đầu tiên → handler render trang lỗi như cũ. Áp trong `fetch_all` (5 call) và ở handler (`fetch_all ‖ feed ‖ dismissed`). Pool lồng nhau → đỉnh ~7-8 request đồng thời tới Jira, chấp nhận được (I/O-bound).

### 26. Cache stale-while-revalidate (SWR)
Chuyển tab chậm 6-10s vì mỗi page block trên call Jira nặng (`fetch_activity_feed` chạy mọi tab vì chuông). `_cached_swr(key, producer)`: fresh (`_CACHE_TTL=120s`) → trả ngay · stale (tới `_CACHE_STALE_TTL=900s`) → trả data cũ + refresh nền 1 thread/key (`_cache_inflight` chống stampede) · miss/quá cũ → tính đồng bộ (raise nếu Jira lỗi). Bonus: refresh nền lỗi bị nuốt → giữ stale thay vì trang lỗi.
**Đánh đổi**: page có thể cũ tối đa ~15' nhưng tự tươi ngầm. Knob: 2 hằng số trong `jira_api.py`.

### 26b. "F5 = luôn tươi" — bypass SWR khi user chủ động refresh
Phân biệt bằng header `Cache-Control` của browser: F5 gửi `max-age=0`, Ctrl+F5 gửi `no-cache`, click `<a>` không gửi → `_wants_fresh()`. `force=True` xuyên `_cached_swr` / `fetch_all` / `fetch_activity_feed` / `fetch_all_shared` (bỏ qua cả L1 RAM + L2 KV + L3 đĩa, nhưng snapshot vẫn là fallback offline).
**KHÔNG force**: endpoint poll `/activity-feed` (60s) — poll không phải F5.

### 28. ThreadingHTTPServer — hết đơ toàn cục
`TCPServer` xử lý tuần tự → 1 request ngậm read-timeout 30s là mọi tab đứng hình. Đổi `ThreadingHTTPServer` + `daemon_threads`. An toàn vì `.last_seen.json` đã gỡ (#27), mọi kho ghi đã có lock, và `atomic_write` dùng tmp-name theo pid+thread → last-writer-wins ở mức file hoàn chỉnh.

### 78. Kho sync chéo máy = Cloudflare KV, local-first *(ghi bổ sung 2026-08-10, code: `core/remote_store.py`)*
SUPERSEDES Decision #14 (Jira user property làm kho chung). Jira nằm sau VPN → mất VPN là `save` FAIL, data không lưu nổi. Đổi kho chung sang **Cloudflare Workers KV** (REST api.cloudflare.com, internet công cộng) và đảo nguyên tắc:
- **save**: ghi file local TRƯỚC (luôn thành công) → đẩy KV best-effort → dirty-flag (`.sync_meta.json`) nếu KV không với tới, flush ở lần load/save kế.
- **load**: KV thắng khi với tới được **và** local không dirty; KV rỗng → seed từ local (hoặc Jira 1 lần để migrate); KV chết → dùng local.
Dùng bởi: roadmap · docs · custom-status · PAT · Drive token · task_link · testcase_link · bug backlog. Bỏ trống creds CF (`KV_ENABLED=False`) → fallback Jira property, vẫn local-first.
**Giới hạn**: mô hình 1 instance/lúc (host migration Mac↔Win) → last-write-wins, không timestamp; host ghi local rồi chết trước khi flush + sửa tiếp ở host khác thì mất edit chưa flush.

### 84. Snapshot task chéo máy (L1/L2/L3) + chế độ OFFLINE *(ghi bổ sung 2026-08-10)*
- `fetch_all_shared` 3 tầng: **L1** `_cache` RAM · **L2** Cloudflare KV `qa-snapshot` (ai có VPN fetch full team thì ghi, người sau đọc → 1 lượt fetch phục vụ cả team; dedup PUT theo hash) · **L3** `.snapshot_cache.json` trên đĩa. Mất VPN → đọc snapshot cũ, caller render **read-only** + banner stale.
- `bug_log_offline.py` (+ `start-bug-log-offline.bat`): entry riêng đặt `OFFLINE=1` trước khi import config → không bắt Jira creds, ngắt mọi call Jira property, chỉ phục vụ `/bug-log` + sync Drive. Dùng khi mạng nhà không vào được VPN nhưng vẫn phải chốt report cuối tháng.

## Auth & phân quyền

### 15. Google OAuth login (thay Cloudflare Access)
Golive trên `baokim-qa.com`; Cloudflare Access kẹt ở bước Activate Zero Trust (thẻ VN fail). Mô hình: app redirect sang Google → nhận email đã verify → check `verified_email` + domain `@baokim.vn` → set **session cookie ký HMAC** (TTL 12h). Zero new deps (stdlib `hmac/hashlib/secrets/http.cookies`), dùng userinfo endpoint nên không cần verify JWT.
- `core/auth.py`: `login_url`/`exchange_code`/`email_allowed`/`make_session_token`/`email_from_session`/`make_state_token` (CSRF, TTL 10p). KHÔNG log token.
- `.env`: `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` + `SESSION_SECRET`. Bỏ trống 2 cái đầu = local dev (`AUTH_ENABLED=False`).
- Cookie `HttpOnly; SameSite=Lax; Secure(https)`. `_base_url()` dựng từ `Host` + `X-Forwarded-Proto` để redirect_uri đúng cả prod lẫn localhost.
- Google Cloud: redirect URI = `https://baokim-qa.com/oauth/callback` + `http://localhost:8080/oauth/callback`, consent screen **Internal**.

### 31. AUTH tắt = fail-closed (loopback-only)
Trước: `AUTH_ENABLED=False` → mọi request là admin (fail-**open**) — quên creds / bind nhầm 0.0.0.0 là mất trắng. Giờ AUTH tắt → chỉ request từ **loopback** (`_is_loopback()` đọc `self.client_address[0]`, KHÔNG tin `X-Forwarded-For`) mới là admin, còn lại 403. AUTH bật → giữ nguyên. Server vẫn bind `127.0.0.1` (lớp 1); đây là defense-in-depth lớp 2.

### 45. Role "dev" (hẹp) — chỉ my-work + bug-log
`DEV_EMAILS` (env `JIRA_DEV_EMAIL`) = người không phải QA, không admin. Allowlist `_DEV_GET_ALLOWED` / `_DEV_POST_ALLOWED` trong `do_GET`/`do_POST`: GET ngoài allowlist → redirect `/my-work`, POST → 403. Dev không nằm trong snapshot team nên `/my-work` fetch riêng `fetch_all(scope_user=<dev>)`; bug-log render `editable=False`. Sidebar chỉ 2 tab + chip role "Dev".
⚠ Local dev loopback = admin (#31) → test role dev phải login Google thật.

### 20. PAT cá nhân + ghi Jira đúng tên người
App dùng 1 PAT chung → mọi thao tác ghi mang tên chủ PAT, sai attribution. Mỗi QA dán **PAT cá nhân** ở `/settings`.
- `pat_store.py`: `{email: enc_pat}`; trước khi lưu **verify PAT thuộc đúng người đăng nhập** (`/myself`, so username với local-part email) — chặn dán nhầm PAT người khác.
- `crypto_util.py`: Fernet, khoá derive từ `SESSION_SECRET` qua scrypt (local dev → `.crypto_key`). Chống rò rỉ file at-rest, **không** chống server bị chiếm.
- `jira_write.py`: ghi bằng PAT truyền vào (KHÔNG dùng `_SESSION`/PAT chung); redact PAT mọi lỗi.
- **Không có PAT → từ chối ghi** (`code:no_pat`, UI nhắc vào Cài đặt) thay vì ghi nhầm tên chung. Jira tự enforce quyền.

### 79. Drive OAuth — 1 refresh token của admin *(ghi bổ sung 2026-08-10, code: `core/drive_token.py`)*
Bug log + test case đọc file trên Drive công ty → chỉ cần **1 token đọc của admin**, không phải per-user như PAT. Refresh token mã hoá Fernet, lưu KV `qa-dashboard-drive-token` + cache `.drive_token.json`. Routes `/drive/connect`, `/oauth/drive-callback`, `/has-drive`, `/disconnect-drive`. KHÔNG plaintext, KHÔNG log token.

### 83. API JSON cho app Android + App Links *(ghi bổ sung 2026-08-10)*
`/api/my-work` · `/api/dashboard` · `/api/bug-log` · `/api/analytics` — **cùng nguồn data/scope/overlay/bell như web**, chỉ đổi output HTML → JSON (payload thuần dựng bởi `build_*_payload`, buckets/pager do client lo). Nguyên tắc **1 nguồn chân lý**: sửa logic phải sửa ở `build_*_payload` chứ không nhân bản.
Login mobile: OAuth callback thấy `state.app` + `APP_REDIRECT` → giao token HMAC self-contained qua **App Link** thay vì Set-Cookie; `/.well-known/assetlinks.json` (public, không gate) để Google verify app sở hữu domain. Chưa cấu hình `APP_LINK_*` → trả `[]`, web vẫn chạy.

## Data Jira: fetch, bucket, notification

### 4. JQL dùng `statusCategory != Done` cho bucket active
An toàn hơn `status != "DONE"` nếu workflow thêm status mới; DONE + CANCELLED đều thuộc category Done.

### 4b. Bucket `done_week` dùng `status = "DONE"` (KHÔNG dùng `resolved`)
Workflow Bảo Kim thường không set resolution → `resolutiondate` null → `resolved >= ...` trả rỗng. Từ 2026-07-07 (user yêu cầu) bỏ luôn cửa sổ 3 ngày: JQL `status = "DONE" ORDER BY updated DESC`, `max_results=500`, nhãn KPI "Done". Cột thời gian hiển thị `resolutiondate`, fallback `updated`.
"Vào/Ra tuần" (`resolved_week`) VẪN dùng `status CHANGED TO "DONE" AFTER startOfWeek()` — không đụng.

### 5. Workload threshold: ≥15 / 5–14 / ≤4 = QUÁ TẢI / OK / NHẸ
Từ xlsx tracker gốc của user. **KHÔNG đổi trừ khi user yêu cầu trực tiếp.**

### 5b. Metric quản lý: "Kẹt ≥5 ngày" + "Vào/Ra tuần"
**Kẹt** (`is_stuck`): task in-flight (không phải TO DO) mà `updated` ≥ `STUCK_DAYS`(=5) ngày. **Vào/Ra tuần**: `created >= startOfWeek()` vs `status CHANGED TO "DONE" AFTER startOfWeek()`, dùng `jira_count` (maxResults=0). Vào > Ra → backlog phình, card đỏ.

### 6. Track theo `assignee` cho workload
"Task ai đang phải làm" → assignee. Riêng New-24h dùng **reporter** (ai chủ động tạo task), 5 QA không tính Hiền vì cô tạo là routine.

### 9. Activity Stream = kéo từ Jira changelog, dismiss đồng bộ chéo máy
Trước là diff 2 snapshot local → đổi máy là mất. Giờ **Jira changelog là source of truth**: `fetch_activity_feed(days=7)` JQL `(assignee in QA OR reporter in QA) AND updated >= -7d` + `expand=changelog`; parse histories (status/assignee/duedate/priority/summary) + comment + created. Mỗi activity có **`id` ổn định** (`key#histId#field` / `key#cmt#id` / `key#created`) → máy nào cũng tính ra y hệt, device-independent. Comment kèm snippet ~140 ký tự.
Dismiss lưu `{activity_id: dismissed_at}` per-user (prop `qa-dashboard-read`, prune >14 ngày) → dismiss máy A, máy B thấy mất ngay.
**Giới hạn**: cửa sổ 7 ngày cố định, cap 120 issue/7d (`ACTIVITY_DAYS`).

### 24. Notification real-time qua short-poll JSON
Chọn short-poll thay SSE vì SSE buộc giữ kết nối lâu (thời điểm đó server còn single-thread) — short-poll zero-dep, không đụng kiến trúc.
- `GET /activity-feed` → `{ok, activities, tasks}` = `_bell_activities(with_patch=True)`, poll 60s, **bỏ qua khi `document.hidden`** + poll ngay khi tab visible lại.
- `tasks` = patch `{KEY:{status?,customs}}` lấy từ CHÍNH issue feed đã fetch (~zero call thêm) → `window.__applyTaskPatch` vá `TASKS[].jira/.customs` rồi re-render **chỉ khi thực sự đổi** (tránh flicker + nuốt comment đang gõ). KHÔNG reload trang.
- `localRead{}` giữ "đã đọc" tại máy trong lúc chờ Jira property sync.
**Giới hạn**: trễ tối đa ~60s. Chỉ notification + status Jira + nhãn nội bộ là real-time; workload/donut/KPI/assignee/due vẫn chỉ tươi khi F5.

### 34. Chuông ẩn noti do CHÍNH người login gây ra
`_drop_own_activities(merged, email)` loại activity mà `by == username` hoặc `author == display_name`, gọi ở cả `_bell_activities` và render `/`.
⚠ **Ranh giới có chủ đích**: CHỈ lọc danh sách notification. Phần `tasks` patch (#24) KHÔNG đụng → tự đổi status vẫn thấy bảng cập nhật ngay. ĐỪNG "sửa gọn" bằng cách lọc ở nguồn feed.

### 60. Cổng QA gate — READY PRODUCTION mà thiếu sub-task QA
Kịch bản sai quy trình: task cha (dev) chuyển `READY PRODUCTION` khi chưa có sub-task QA nào (né ghi nhận story point). `_compute_ready_prod_gaps` (SWR cache): quét task ở status đó (cap `READY_PROD_MAX=150`), lấy sub-task theo lô `parent in (...)`, task nào không có sub-task thoả `[QA]*` **và** assignee ∈ USERS → vi phạm. **Chỉ báo khi người chuyển trạng thái cũng là QA** (đúng kịch bản; dev chuyển thì không báo). Activity id `<KEY>#qa-gate` → dismiss được, sửa xong tự biến mất. Best-effort: `block=False`, lỗi → `[]`, không bao giờ treo chuông.
Scope: admin thấy hết, QA/dev chỉ thấy gap do chính mình gây. Config: `READY_PROD_STATUS` / `READY_PROD_PROJECTS` / `READY_PROD_MAX`.

## UI v2 & tương tác

### 19. UI v2 "Stitch" — sidebar Material 3
Redesign toàn app sang sidebar Material 3, vanilla JS + string template. Shell chung `_document_v2(content, active, user, activities, title)` = `render_sidebar_v2` + `render_topbar_v2` (chuông) + drawer dùng chung + modal (settings/sub-task/palette) + nhúng `window.__jiraBase` / `__isAdmin` / `QA_CUSTOM_STATUSES` / `__mentionUsers`. Trang: `render_admin_v2`, `render_qa_v2`, `render_roadmap_v2`, `render_docs_page`, `render_bug_log_v2`, `render_analytics_v2`, `render_testcase_v2`, `render_leader_eval_page`.
UI cũ (topnav, `app.js`, `render_personal`, `render_nav`, filterbar, workload matrix, PIC) đã **xoá hẳn** (cleanup #43).

### 18. Drawer detail ở shell + notification mở detail mọi tab
Drawer từng nằm trong closure `#rows` → chỉ có ở trang có bảng task. Giờ DOM drawer ở shell → mọi trang v2. 2 tầng: (a) drawer "đầy đủ" trong closure `#rows` (dashboard / việc của tôi, có nhãn nội bộ + cờ Overdue/Kẹt); (b) **module fallback dùng chung** đặt SAU closure, guard `#drawer` tồn tại **và** `window.__openDetail` chưa set → chỉ chạy ở Roadmap/Tài liệu/Bug Log/Analytics; fetch `/issue-comments` rồi `synth()` task tối giản.
`fetch_issue_detail` trả thêm `status`/`assignee`/`duedate` để dựng drawer cho task **ngoài mọi bucket** (vd CANCELLED).

### 38. Design tokens + motion + skeleton + View Transitions
Token additive (KHÔNG rename token cũ): spacing `--sp-1..8`, `--r-2xl`, elevation `--e1/e2/e3`, motion `--dur-1/2/3` + `--ease-out/--ease-emphasized`. `tabular-nums` mọi ô số. `@media (prefers-reduced-motion:reduce)` tắt toàn bộ motion.
Cross-page dùng **MPA View Transitions** (`@view-transition{navigation:auto}`) thay vì fetch-soft-nav — vì ~40 IIFE chạy lúc parse, re-init sẽ duplicate handler. Kèm `.nav-progress` bar. Skeleton `.skel-*` thay mọi text "Đang tải…". `animRows()` stagger **chỉ ở thao tác user**, KHÔNG ở poll 60s. Toast stack tối đa 3 (`toast(msg, ok)` giữ signature cũ). Empty state `.empty-state` = icon-circle + title + hint.

### 39. Command palette Ctrl+K + smenu dùng chung
Refactor 2 bản copy status-menu (admin/QA) thành module shared `window.__openSmenu(caret, task, {onChanged})` + `__smSetCustom` + `__smRebind` (xoá ~160 dòng trùng); task object mutate tại chỗ, controller chỉ re-render trong `onChanged`. Caret status có ở **cả 3 drawer** → đổi status/nhãn từ mọi trang.
Palette: Điều hướng + Hành động (filter tức thì) + Task Jira (`/global-search`) + Bug (`/search-bugs`) async debounce 300ms, 2 fetch song song, stale-guard. Đặt module **NGAY SAU** global-search để `stopImmediatePropagation` không đóng nhầm drawer/smenu.
⚠ Match **accent-insensitive**: `norm()` = lower + NFD strip + **`đ→d`** (NFD KHÔNG decompose đ/Đ). Python `_fold` phải parity.
Bulk actions = DEFER (Jira DC không có bulk-transition REST).

### 41. Pager đồng bộ toàn app
4 bảng từng có 4 kiểu pager. Helper shared `pagerHTML(page, pages, total, start, count, unit)` đầu IIFE `app_v2.js` sinh markup chuẩn (summary + nút số + ellipsis `win=1` + mũi tên), `data-pg` = **số trang tuyệt đối**, container bắt click qua delegation. 4 call site (admin / my-work / bug-log / test-cases) đều 1 dòng.

### 35. Đổi Due date inline (bảng + drawer)
2 tầng enforce: **gate UI** = `GET editmeta` bằng PAT cá nhân (`can_edit_duedate` → `'duedate' in fields`); **enforce thật** = `PUT /issue/{key}` bằng PAT cá nhân (Jira tự chặn 403/400). Cả 2 route qua `_handle_jira_write` → không có PAT là từ chối.
Check quyền **lazy lúc bấm** (`ensureDuePerm` cache) để tránh N call editmeta/trang. `dueValHTML(t)` dùng chung cho ô Hạn ở bảng lẫn drawer. Admin tbody row-click bỏ qua khi target trong `.due-cell` (không mở drawer nhầm).

### 56. @-mention trong ô bình luận → markup Jira `[~username]`
Jira DC render `[~username]` thành mention + notify; backend đã parse format này cho cờ mention ở feed.
Controller `mentionAutocomplete` (delegation `input` trên textarea id `^(dtTa|cmtTa)-`) phủ cả 3 drawer lẫn ô inline. Nguồn 2 tầng: roster QA (`window.__mentionUsers`) hiện ngay khi gõ "@"; **≥1 ký tự** → augment TOÀN BỘ user Jira qua `/search-people` (debounce 220ms, merge dedup, cap 10). Keydown bind **capture + stopPropagation** để Enter/Esc không lọt xuống drawer.
⚠ Phụ thuộc quyền **Browse Users** của tài khoản PAT chung — thiếu thì chỉ còn roster QA. Visible text là markup thô (giống editor wiki Jira), không map display→username lúc gửi để tránh sai attribution.

### 87. Custom select `xsel` — thay popup `<select>` native toàn app *(2026-08-11)*
Popup của `<select>` do OS vẽ → không style được: list trắng giữa theme tối, font hệ thống, không bo góc, lệch hẳn ngôn ngữ thị giác v2. Thay bằng **progressive enhancement dùng chung**, KHÔNG sửa 20 chỗ render `<select>` bên Python:
- Module cuối `app_v2.js` (top-level IIFE riêng, ngoài scope shared → có `esc`/`fold` bản riêng) quét mọi `select`, bọc `.xsel` = trigger `.xsel-btn` + menu portal ra `<body>` (`position:fixed`, z-index 1400 → không bị `overflow` của card/bảng cắt, dùng được trong modal/drawer). `<select>` gốc **giữ trong DOM** (ẩn kiểu a11y) làm **nguồn sự thật** → mọi controller cũ đọc `.value`, gán `.innerHTML`, bắt `change` chạy y như trước; form native vẫn submit đúng.
- Đồng bộ ngược 3 kênh vì gán thuộc tính KHÔNG sinh event: (a) `MutationObserver` childList → options build lại từ data (tester/dev/tháng/cây thư mục); (b) attribute `disabled`/`title`; (c) **override property `value`/`selectedIndex` per-element** qua descriptor gốc của `HTMLSelectElement.prototype`. Thêm `sel.focus()` → chuyển sang trigger (native đã ẩn).
- Select sinh động (modal roadmap `mf-*`, `/docs`, palette) bắt bằng `MutationObserver` trên `body` (gộp theo rAF).
- Menu: ô **tìm kiếm khi ≥10 option** (fold không dấu + `đ→d`, parity với `norm()` #39), bàn phím ↑/↓/Home/End/Enter/Esc, tự **lật lên** khi thiếu chỗ dưới, chọn xong `dispatchEvent('change')` **chỉ khi giá trị thực sự đổi**.
- Style theo ngữ cảnh thay vì 1 kiểu duy nhất: `.bl-filter` (ghost, như select không viền cũ) · `.mfield`/`.tc-iwrap`/`.ef` (full-width field) · `.metric-filter` · `.set-input` · `.st-row` · `.bm-sel`. Wrapper mang thêm class `xsel-of-<class đầu của select>` để bám style cũ.
⚠ Bỏ qua khi `multiple` / `size>1` / có `data-noxsel` → cần select native chỗ nào thì gắn `data-noxsel`.
**Giới hạn**: inline `style="width:…"` đặt trên `<select>` không còn tác dụng (nằm trên native đã ẩn) — muốn đổi bề rộng phải style ở CSS cho `.xsel-btn`.

## Tab: Việc của tôi / lens cá nhân

### 17. Tab "Việc của tôi" (`/my-work`) — lens cá nhân cho admin
Admin cũng là 1 QA có task riêng; QA non-admin thì `/` đã auto-scope. `/my-work` admin-only (non-admin → 302 `/`), scope = `_self_username()` (`username_from_email(login) or ADMIN_EMAIL or SELF_USER`). UI **hệt QA member** — tái dùng `render_qa_v2()` với `nav_active='mywork'`.

## Tab: Roadmap & Tài liệu

### 12. Tab "Roadmap" (`/roadmap`) — giai đoạn › mục › sub-task + cảnh báo hạn
KHÔNG suy từ Jira (team làm ở tầng sub-task, fixVersion/epic không nhất quán → roadmap auto sẽ vỡ). Tự author + edit, bố cục theo mốc thời gian.
- Data (`.roadmap_config.json` + KV): list `{phase, items:[item]}`; node = `{title, status, progress, due}`, item thêm `subtasks[]`. Status ∈ {planned, in_progress, done, blocked} (lenient, CSS `rm-st-<value>`). Cap `MAX_PHASES=100` / `MAX_ITEMS=1000`.
- **Edit = popup**, không inline: bấm mục có sub-task = xổ cây, bấm ✎ = popup. Auto-save debounce 600ms POST `/save-roadmap`.
- **% + status của mục có sub-task là TỰ TÍNH**: progress = trung bình; status = all done→done · có blocked→blocked · có in_progress hoặc vài done→in_progress · else planned. 2 ô disable trong popup. Node sửa tay `status='done'` → ép `progress=100`.
- `due_alerts(data, within_days=14)` → block "🗺 Roadmap sắp đến hạn" ở dashboard, tách khỏi feed Jira.
- Đã BỎ field PIC + link (roadmap 1 mình user làm). `/public/roadmap` = bản chỉ-xem không cần login (`render_public_roadmap_v2`).
- Chưa làm: reorder kéo-thả, nhiều tầng sub-task.

### 11. Tab "Tài liệu" (`/docs`) — cây thư mục + link Google Drive
Chốt **KHÔNG build editor Office** (OnlyOffice/Collabora cần Docker → phá kiến trúc minimal-deps). "Edit thật để Google lo", workspace chỉ là **index + mở nhanh**: dán link Drive → click mở/preview. Zero dep, không Google API cho phần này.
Data (`.docs_config.json` + KV): cây đệ quy, node = `folder{type,name,children[]}` hoặc `link{type,title,url}`; `valid_tree` cap `MAX_NODES=2000`. Sửa link = popup; folder rename inline. Chỉ mở link khi `^https?://` (chặn `javascript:`).

### 23. Tài liệu — upload file thật + serve local
POST `/upload-file` → `uploads/`, GET `/uploads/<filename>`. Path dùng **`config.UPLOADS_DIR`** = `SCRIPT_DIR/'uploads'` (bám root, chạy đúng mọi OS; override bằng env `UPLOADS_DIR`) — trước hardcode macOS nên chết trên host Windows (issue #37). Unquote path trước `basename`, POST trả `url` đã `quote` (tên file có dấu/khoảng trắng). Sanitize mạnh cho Windows (strip `\`/`/`, thay `<>:"|?*` + control char, chặn tên rỗng) → chống traversal + ADS.
**Giới hạn**: file upload KHÔNG sync chéo máy (chỉ ở host, `uploads/` gitignore).

### 70. Hardening `/upload-file`
- **Allowlist đuôi** `ALLOWED_UPLOAD_EXTS` (Office/ảnh/text/html) — chặn `.exe/.sh/.php/.js/.zip` tại cổng.
- **`X-Content-Type-Options: nosniff`** khi serve; `inline` CHỈ cho pdf + ảnh raster, còn lại (svg/html/text) ép `attachment`. SVG cố ý không inline (nhúng `<script>` được).
- Bỏ lộ exception ra client (log `repr(e)` ra stderr, client nhận message chung).
**Giới hạn**: allowlist theo đuôi, không magic-byte — lớp chặn XSS thật là khâu serve.

### 63. Viewer tài liệu inline (thay mở tab mới)
Overlay `#fpOverlay` + `openDocPreview(doc)` chọn nhánh theo đuôi: PDF → iframe · ảnh → `<img>` · docx/xlsx/pptx/text → `GET /file-preview` dựng HTML server-side · link Google → iframe bản `/preview` (nhúng được vì browser user đã đăng nhập Google; server KHÔNG chạm Drive API). Header có Tải xuống + Mở tab mới + ×; đóng thì xoá `innerHTML` (gỡ iframe).
`core/file_preview.py` zero-dep: xlsx tái dùng `bug_log.list_sheet_names/read_sheet_rows`; docx = zip + regex `word/document.xml`; pptx = `<a:t>`. **MỌI nội dung qua `issues.esc`** (file người dùng up = untrusted). Cap 25MB / 500 dòng / 40 cột / 800 đoạn / 400k ký tự. Không raise — lỗi → thông báo tiếng Việt.
⚠ Regex phải là `<w:t(?:\s[^>]*)?>` — `<w:t[^>]*>` khớp nhầm `<w:tc>`.
Route `/file-preview` chỉ đọc trong `UPLOADS_DIR` (`basename` + `resolve().parent` check).
**xlsx hiển thị kiểu Excel**: tab sheet ở đáy + chỉ 1 pane hiện + thanh cột A/B/C sticky + cột số dòng sticky; đổi tab qua **delegated listener** (markup nhét bằng `innerHTML` nên không kèm `<script>` được). `.fp-grid-wrap` dùng `overflow-x:scroll` (ép thanh cuộn chiếm chỗ — Chrome/Windows overlay scrollbar ẩn tịt).
**Giới hạn**: preview Office là bản gần đúng để đọc nhanh (mất font/màu/merge phức tạp, bỏ ảnh nhúng). `.doc/.xls/.ppt` cũ + `.zip` → empty-state.

### 65. Xem file HTML trong app — iframe `/file-raw` sandbox
KHÔNG parse lại HTML (bóc text ra `<pre>` là mất hết ý nghĩa) → để browser render nguyên bản, **cách ly bằng origin mờ**.
Route riêng `/file-raw?f=` (chỉ `.html/.htm`, chỉ trong `UPLOADS_DIR`) vì `/uploads/` cố ý serve HTML dạng attachment — đổi `/uploads/` sang `text/html` inline là stored XSS ăn session.
Header `Content-Security-Policy: sandbox allow-scripts allow-popups allow-forms allow-modals` + nosniff + no-store; client bọc thêm `sandbox=` + `referrerpolicy=no-referrer`. **KHÔNG `allow-same-origin`** → `origin === "null"`, cookie/localStorage throw. Cho `allow-scripts` để report có chart xem được — an toàn vì origin mờ + upload đã gate.
Client `fpOpenUrl(u)` map `/uploads/*.html` → `/file-raw` cho cả iframe lẫn "Mở tab mới"; nút Tải xuống vẫn trỏ `/uploads/`.
**Giới hạn**: file phải **self-contained** (CSS/JS/ảnh tương đối sẽ đứt vì chỉ up 1 file lẻ).

### 66. Folder "Quy Trình" — chế độ TAB chỉ nhận HTML
Folder đánh dấu `kind:'process'` (`docs.py`: `ensure_process_folder`, idempotent, folder trùng tên chỉ gắn thêm `kind`). Trong folder: ẩn bảng tài liệu, hiện thanh tab (mỗi file HTML = 1 tab) + host iframe. `procActiveId`/`procShownId` tách nhau để vẽ lại thanh tab **không reload iframe**. Upload trong chế độ này ép `accept='.html,.htm'`.
**Auto-height** (xem full trong trang, 1 scrollbar): sandbox không có `allow-same-origin` → parent không đọc được `scrollHeight` → `/file-raw?fit=1` chèn `_FIT_SNIPPET` để file tự `postMessage({__fitHeight})`; parent chỉ tin khi `e.source === procFrame.contentWindow`, clamp `[320, 40000]`.
⚠ 3 cái bẫy đã sửa, đừng lặp lại: (a) đo bằng `documentElement.scrollHeight` → **ratchet phình vô hạn** (trị đó = chiều cao KHUNG khi khung > nội dung) → phải đo **đáy các con của `body`**; (b) scrollbar lúc đo làm hụt ~30px → ép `html{overflow-y:hidden}` trong lúc đo rồi trả lại; (c) `ResizeObserver` không chạy khi tab ẩn → thêm interval 1.5s + `visibilitychange`.
⚠ `.proc-bar` sticky `top:-20px` — **cột chặt vào `padding-top:20px` của `.content`**, đổi padding phải đổi theo.
UX kiểu Drive: ẩn hẳn khối bảng khi thư mục chỉ có thư mục con (trừ lúc đang tìm kiếm); `.empty-state` 3 ngữ cảnh. Menu `…` trên folder card (đổi tên/xoá) — listener phải bắt ở **capture phase** vì card dùng inline `onclick`. Folder `kind:'process'` chặn xoá (server tự tạo lại).

### 67. Deep-link `/docs` — `?folder=` / `?doc=` + Back/Forward
`?folder=<node id>` = thư mục đang mở · `?doc=<node id>` = tài liệu đang xem (hoặc tab nếu folder là `process`). Chỉ có `?doc=` → tự suy folder cha. Id không tồn tại → về gốc, không lỗi.
`writeUrl(push)` giữ nguyên param lạ; `pushState` cho thao tác user, `replaceState` cho sửa-URL-cho-khớp; `applyUrlState()` dùng cho cả `popstate` lẫn initial render; cờ `urlSuppress` chặn vòng lặp.
"Sao chép link" với file local giờ copy **deep-link tuyệt đối** (trước copy `/uploads/...` tương đối, dán ra ngoài vô dụng); link Drive giữ URL Google.
**Giới hạn**: id node là `d_<ts>`/`f_<ts>` sinh client → khôi phục cây khác thì link cũ đứt (tab Quy Trình có id ổn định `f_proc`).

### 74. `/docs` — mở quyền upload + tạo/sửa thư mục cho MỌI QA authed
`_get_docs` render `editable=True`, `_post_save_docs` + `_post_upload_file` gate `_authed()` thay `_is_admin()`. Dev vẫn bị chặn tự nhiên (không nằm trong allowlist #45) → "authed" ở đây = admin + QA member.

## Tạo sub-task

### 22. Tạo QA sub-task ngay trên dashboard
`jira_write.create_subtask` dùng PAT cá nhân. Config field id: `SUBTASK_TYPE_ID`, `START_DATE_FIELD` (required, default hôm nay), `LEADER_FIELD`, `DEPARTMENT_FIELD`/`BK_TEAM_FIELD` (auto-tick IT / IT-QA). Modal auto-fill prefix `[QA] `; routes `/create-subtask`, `/search-parents`, `/search-people`.

### 57. Parent BẤT KỲ task + auto-gen 2 dòng + due cuối tháng
`search_parent_tasks` dùng **Jira issue picker** (`/issue/picker`, `showSubTasks=false`) → search toàn instance. `_resolve_parent` chỉ chặn khi cha là sub-task (Jira không lồng sub-task), bỏ check Task-PTSP. Chọn cha → sinh 2 dòng `[QA] Viết testcase <cha>` + `[QA] Test <cha>` (bỏ **mọi** tiền tố `[xxxx]` của cha). Hạn chót auto = cuối tháng hiện tại. Bỏ auto-fill Leader = Hiền (field vẫn còn, chọn tay).

### 58. Gán QA RIÊNG từng dòng
Danh sách dòng (ô tiêu đề + dropdown QA riêng + xoá) thay textarea. Payload `items:[{summary,assignee}]`; parent/start/due/leader vẫn chung. Backward-compat: vẫn nhận `summaries:[str]`. Partial-failure → dựng lại dòng lỗi kèm assignee để retry.

### 59. Popup "sub-task đang có" của task cha
Hover chip cha → popup zoom-in list sub-task hiện có (`GET /parent-subtasks`, PAT chung read-only, cap 50, regex chặn key rác khỏi vỡ JQL); click 1 mục → thêm dòng QA tương ứng. Cache theo phiên modal; `hidePop()` delay 180ms để rê chuột kịp.

### 77. Tạo sub-task dưới NHIỀU task cha trong 1 modal
Ô "Thêm task cha" (type-ahead, noChip) → mỗi cha 1 **nhóm** (chip cha + list dòng riêng + nút bỏ nhóm); chọn cha đã có nhóm → không nhân đôi (cuộn tới + flash). Popup hover per-group (`popGroup`) → click item thêm dòng vào ĐÚNG nhóm.
Payload `groups:[{parent,items}]` + start/due/leader chung → `create_subtasks_multi`: verify **mỗi cha đúng 1 lần**, tạo tuần tự; cha verify fail → chỉ item của cha đó vào `failed`. Cap **40** sub-task/lần. Backward-compat payload 1-cha giữ nguyên.

## Bug Log (nguồn Google Drive)

### 25. Sync nhanh: Tầng-1 metadata-first + parallel + poll cấu hình
Gốc rễ cũ: `scan()` gọi `fetch_rows` vốn **tải full + parse rồi mới so unchanged** → tầng-1 chưa từng tiết kiệm gì.
- **A**: tách `fetch_meta()` (rẻ) / `fetch_content()`; `scan()` so `modifiedTime`+`md5` trước, chỉ tải khi đổi.
- **B**: `_scan_one(src, prev)` thuần (không ghi state chung, **tự nuốt mọi lỗi** vì `run_parallel` re-raise lỗi đầu) chạy song song; **merge/diff TUẦN TỰ theo thứ tự `sources`** để không race và giữ thứ tự event.
- **C**: `BUG_LOG_POLL_SECONDS` (default 600, sàn 30s) — chỉ giảm độ trễ, không làm scan nhanh hơn.
- **D**: **"Đồng bộ ngay" = FORCE**, bỏ qua tầng-1 (metadata Drive không đáng tin tức thì: Sheet native không có md5, `modifiedTime` lan truyền trễ). Poll nền vẫn `force=False`.

### 29. Hỗ trợ Google Sheet native (export → xlsx)
Nguồn là Sheet native → `alt=media` trả **403 `fileNotDownloadable`** → soft-fail → cache đóng băng (triệu chứng đánh lừa: reopen vẫn hiện số cũ vì monotonic). `download_file` route theo `mimeType`: Sheet native → `/files/{id}/export?mimeType=<xlsx>` (giữ đa sheet + tên sheet), còn lại `alt=media`. Native Sheet không có `md5Checksum` → change-detection chỉ dựa `modifiedTime`.
**Giới hạn**: `files.export` cap ~10MB.

### 43. Khử noise transition "→ New"
QA tạo bug mới bằng cách copy dòng cũ → dòng mới thừa hưởng status cũ trước khi sửa về `New` → diff bắt transition giả. Bỏ qua **mọi transition có đích = `New`** (vòng đời bug thật không quay lại New; reactivation dùng `Reopen`). Event `log bug` (key lần đầu xuất hiện) và các transition khác giữ nguyên.

### 53. Lọc theo cột "Bug" + reopen chỉ đếm bug còn trong file
Team log lẫn dòng không phải bug → `normalize` chỉ giữ dòng có cột `Bug` = `bug` (sheet KHÔNG có cột Bug → giữ tất cả, backward-compat).
Reopen: bỏ nhánh fallback "bug rời file vẫn tính" — vì `reopen_map` **monotonic, không bao giờ prune** → orphan sẽ phồng tử số trong khi mẫu số đã bỏ. Sửa ở **tầng đọc**, không mutate accumulator.
**D — full attribution**: bug do nhiều dev cùng fix trước chia `1/n` (ra "0.5 lần reopen") → giờ mỗi dev tính **đủ 1**. Hệ quả có chủ đích: `sum(bugs_per_dev) > total_bugs`.

### 73. Cột "Bug" đổi phân loại → lan theo NỘI DUNG
Bug được bê sang sheet tháng mới rồi team bỏ khỏi diện bug (cột Bug trống) — filter #53 chỉ loại dòng tháng mới, dòng cũ vẫn là bug → tồn đọng oan. Giờ gom dòng cùng `summary` chuẩn hoá, lấy phân loại của **tháng mới nhất** áp cho cả nhóm.
⚠ 2 guard chống xoá oan (đều là ca thật): (a) so theo **tháng** chứ không theo từng dòng → 2 dòng trùng nội dung trong CÙNG sheet thì "là bug" thắng; (b) chỉ dòng **có STT** được bỏ phiếu → dòng rác/spill không chi phối.

### 30. Reopen tracker — seed theo trạng thái hiện tại
`_count_reopens` chỉ +1 khi quan sát được transition LIVE `≠Reopen → =Reopen`; bug đã ở Reopen tại baseline thì không bao giờ đếm. `_seed_current_reopens`: bug đang `Reopen` mà chưa có entry → seed `{count:1}` (lower-bound). Idempotent, không double với transition.

### 48. Số lần fix = SUY từ count + trạng thái
Accumulator `fix` undercount vì workflow hay skip status `Fixed` (`Fixing → Closed` thẳng). Giờ suy tại render: `fix = count + (1 nếu status ∈ {Fixed, Closed})` — mỗi lần giao chỉ có 2 kết cục: bị reopen (đã trong count) hoặc chưa bị dội (+1). Parity `_reopen_table` (Python) ↔ `fixDeliv` (JS). Accumulator `fix` thành dead field.

### 61. PLACEHOLDER chuyển nguồn Bug Log sang Jira
Seam duy nhất = `bug_log_store._scan_one(src, prev)`; downstream chỉ phụ thuộc **bug dict** + `.bug_log.json`.
- Source thêm field `provider ∈ {drive, jira}` (thiếu = drive, backward-compat); `valid_sources` nới cho jira.
- `core/bug_source_jira.py` = stub, gate `BUG_LOG_JIRA_ENABLED` (default False → `{bugs:[],pending:True}`, KHÔNG gọi mạng). `_issue_to_bug`/`_fetch_issues` = `NotImplementedError` + bảng mapping field để điền sau.
- UI `/analytics` có 6 card metric rỗng "Chờ dữ liệu Jira" (chốt layout trước).
📌 Khi bật thật: cân nhắc dùng **Jira issue key** làm định danh bền → có thể BỎ toàn bộ logic fingerprint/carry vốn chỉ tồn tại vì Sheet thiếu ID ổn định.

## Bug Log — metric & tồn đọng

### 49. Analytics bucket theo SHEET tháng (Tn), KHÔNG theo created date
Bucket theo created làm bug tồn copy sang sheet T7 (giữ created T6) bị đếm ở T6 (đếm đôi nếu T6 chưa frozen), và bug created-June reopen trong T7 rơi mất khỏi mọi bảng. Giờ `_month_of(b)` / `monthOf(b)` map **tên sheet** → tháng: `T<m><yyyy>` năm tường minh · `T<m>` bare lấy năm từ created · sheet module → fallback created. Áp cho Valid Bug Rate + bug theo dev/dự án + Reopen. **Tồn đọng giữ created-based** (#75).
⚠ Parity Python ↔ JS.

### 47. Freeze metric Analytics cho tháng đã đóng
Số tháng đã đóng cứ trôi mỗi khi team sửa/copy sheet → lệch số đã gửi CTO. Kho `chart["YYYY-MM"]` trong `.bug_monthly.json` giữ `grand/devs/valid/reopen/bl`. `archive()` (gọi mỗi scan) overwrite tháng hiện tại, bootstrap 1 lần cho tháng quá khứ chưa có, **để yên** tháng quá khứ đã có.
Reopen giữ semantics **RAW** (không dedup) — dedup mẫu số mà không dedup tử số sẽ méo tỷ lệ; freeze chỉ chặn trôi. ⚠ Reopen denom lệch có chủ đích so với chart/valid (dedup).
`CHART_V` phải khớp giữa Python (`_CHART_V`) và JS (`frozenFor`) — lệch là nhánh frozen **inert** (đã từng dính, mọi tháng rơi về LIVE).

### 69. Freeze CHỦ ĐỘNG sau khi report gửi CTO
Freeze thụ động (#47) chỉ chốt ở lần scan chót của tháng, không trùng lúc gửi report. `freeze_month(month, live, reopen_map)` ghi cả 3 kho (`months` / `carry` / `chart` + `_frozen`, `frozen_at`) rồi đăng ký `frozen[month]`; `archive()` **bỏ qua mọi tháng có trong `frozen`** (kể cả khi bump `_CHART_V`).
Hook trong `monthly_reporter_chat_app.py` ngay SAU khi Chat gửi thành công và **CHỈ khi `USE_REAL`** (run TEST không freeze). Cờ `--no-freeze` để tắt. Soft-fail.
**Gỡ freeze**: xoá entry tháng đó trong `frozen` của `.bug_monthly.json` **và** KV/property, hoặc gọi lại `freeze_month` để ghi đè.

### 75. Tồn đọng = SHEET-BASED (đọc thẳng sheet tháng, đếm dòng theo created)
SUPERSEDES định nghĩa fingerprint/carry của #33/#36/#46/#62/#68 cho **read-path tồn đọng/mới**.
Bối cảnh: màn Bug và màn Analytics đo 2 định nghĩa khác nhau nên lệch số. User chốt workflow: cuối tháng bê bug chưa xong sang sheet tháng mới, **GIỮ NGUYÊN ngày created** → chính việc bê sang sheet đã là "freeze" tự nhiên, không cần fingerprint/carry.
Định nghĩa thống nhất — trong sheet tháng T, **đếm DÒNG**: `created < tháng-sheet` = **tồn đọng** (status mở = còn treo; Closed/Reject = đã xử lý); `created >= tháng-sheet` = **mới phát sinh** (Closed = đã fix). `total = còn treo + đã xử lý`. KHÔNG dedup (dòng trùng đếm 2 → tín hiệu dọn sheet).
Sửa ở **3 nơi phải parity**: `prev_month_backlog` (Python, cho report CTO) ↔ `computeBacklog` (JS, dải chart) ↔ `splitGroups` (JS, tab Bug).
KHÔNG đụng: Valid Bug Rate + Reopen (vẫn dedup fp + freeze), `task_link` fingerprint.
**Điểm yếu duy nhất**: phụ thuộc team giữ nguyên ngày created khi bê bug — reset về mùng 1 là tồn đọng tụt về 0.

### 54. Fingerprint = `project|service|summary` (BỎ `feature`)
Team đổi tên cột "Chức năng" khi copy bug sang sheet mới trong khi `summary` giữ nguyên 100% → fp đứt → bug đã Closed vẫn bị tính còn treo. `feature` volatile, `summary` là tín hiệu mạnh + ổn định nhất.
Dùng chung cho: chart dedup (#47), `task_link` (#37/#50/#51). `bug_backlog.fingerprint` (Python) ↔ `_fpOf` (JS) — **`_norm`/`_bnorm` phải parity, sửa 1 bên là sửa bên kia**.
`task_link.backfill_fingerprints` **re-stamp khi fp lệch** (không chỉ khi thiếu) → link cũ tự migrate sau 1 lần scan.
**Đánh đổi**: 2 bug khác chức năng nhưng trùng `project+service+summary` bị gộp (hiếm).

### 72. Bug tab — 2 tab "Tồn đọng từ tháng trước" vs "Bug mới trong tháng"
Thanh 2 tab (badge số), bảng chỉ hiện nhóm đang chọn; pager/count/check-all/export Excel đều tính trên nhóm đang xem. State nhớ `localStorage qa-buglog-grp`; nhóm rỗng → **auto lùi sang nhóm còn lại nhưng KHÔNG ghi lại localStorage** (về tháng có tồn đọng thì trở lại tab cũ).
Phân loại theo #75 (created < tháng của tab). ⚠ **Khác chart "Tồn đọng T-1"**: bug tab tính mọi tháng cũ hơn, không lọc status, không dedup → số có thể ≠ chart. Có chủ đích.

### 85. Pie chart Severity ở Analytics + đưa vào report tháng
Thang severity trong file bug log gõ LẪN 2 kiểu chữ cho cùng 1 mức → user chốt quy về **3 mức**: `Major = High` · `Normal = Medium` · `Minor = Low` (Blocker/Critical nếu có gom vào Major). Ô trống / giá trị lạ (`Minior` sai chính tả đã map, còn lại) → `none` **KHÔNG vẽ trong pie** nhưng vẫn hiện thành ghi chú "Chưa phân loại: n/N bug" — bỏ hẳn thì mất mẫu số, CTO tưởng tháng chỉ có ngần ấy bug. **Mẫu số % của pie = bug đã phân loại**, không phải tổng bug tháng.
Tập bug = **y hệt biểu đồ cột** (dòng trong sheet tháng T **và** created trong T — #75) → tổng 2 chart luôn khớp. Tính **LIVE mọi tháng** (không đụng freeze #47/#69 — freeze chỉ áp Valid Bug Rate + Reopen).
Pie render **vào trong `#anMetricCharts`** (không tách card riêng) để tự lọt vào ảnh PNG/PDF mà `monthly_reporter_chat_app.py` chụp gửi CTO; text Chat thêm block "🎚 Mức độ nghiêm trọng" đọc từ `severity_counts()`.
Vẽ bằng **SVG `<path>` arc**, KHÔNG `conic-gradient` — html2canvas không render conic → ảnh gửi CTO sẽ trắng.
⚠ Twin Python↔JS: `_SEV_MAP`/`_SEV_ORDER`/`_SEV_PIE`/`_sev_bucket` (`bug_backlog.py`) ↔ `SEV_MAP`/`SEV_ORDER`/`SEV_PIE`/`sevOf` (`app_v2.js`).
**Bổ sung 2026-08-10 — cột Severity ở bảng `/bug-log`**: thêm cột giữa Ngày và Trạng thái, badge 3 mức cùng bảng màu với pie (đọc chéo 2 màn không lệch). `none` (ô trống / giá trị lạ trong file) hiện `—` mờ, title kèm giá trị thô để biết file gõ gì — KHÔNG ép về Normal. Export Excel thêm cột tương ứng (HEADERS 7 → 8 cột, `none` → ô rỗng). Dropdown **lọc theo severity** (`blSevFilter`) cùng hàng với lọc tester/dev/link — option CỐ ĐỊNH (thang là hằng số, không build từ data), gồm cả "Chưa phân loại". `.bl-table{min-width:1120px}` vì 10 cột làm browser bóp cột "Liên kết Task" xuống ~60px (chữ gãy 3 dòng) — để wrapper `overflow-x:auto` cuộn ngang thay vì bóp. Hằng số `SEV_*` + `sevOf` trong `app_v2.js` đã **hoist ra scope chung** (cạnh `pagerHTML`) vì giờ dùng ở 2 controller (bug-log + analytics) — đừng khai báo lại bản copy trong IIFE.

### 86. Modal "Quản lý link drive" (`/bug-log`) — layout card + link mở thẳng chế độ EDIT
2 màn quản lý nguồn (`/bug-log` và `/test-cases`) trước đó khác hẳn nhau: bug-log là 3 input nằm ngang 1 dòng, test-case là card. Gộp về **layout card của test-case** (`.bl-src-row` từ flex-row → card `surface-low` + border, list `max-height:52vh`, thông số bám theo `.tc-link-item`) nhưng **giữ nguyên phần edit riêng của bug-log**: nhãn + **hậu tố** (`service`, dùng dựng bug id) + link + xoá + "Thêm link". Vẫn 1 nút **"Lưu & đồng bộ"** ở footer (POST full list `/save-bug-log-sources`) chứ KHÔNG per-card như test-case — backend nhận cả list, save từng card cũng phải gom lại.
**Link hiển thị + nút "Mở" = URL Sheets `/edit`**, không phải `drive.google.com/file/d/<id>/view` như trước (`/view` mở viewer chỉ-xem, phải bấm thêm 1 nhịp mới sửa được). `editUrlOf(u, id, name)` chuẩn hoá: link Sheets → ép `/edit` · link Drive / id trần / rỗng → `spreadsheets/d/<id>/edit` khi **tên file không thuộc `_NOT_SHEET`** (`.xls` cũ, pdf, doc…) → phần này vẫn `/view` · link không phải Drive/Sheets → để nguyên, không đoán. Native Sheet lẫn `.xlsx` trên Drive đều mở được bằng URL Sheets `/edit`.
Server không phải đổi: `extract_file_id` bắt `/d/<id>` nên nuốt cả 2 dạng link; store vẫn chỉ lưu **file id** (link chỉ là lớp hiển thị, mỗi lần render dựng lại).

### 45b. Bug Log — filter cho mọi người + Export Excel
Tách `filters_html` (3 dropdown lọc-xem, render cho **tất cả**) khỏi `link_widget` + checkbox column (giữ `editable`-only) → dev cũng lọc được. Dropdown build từ `monthScopeBugs()` (bug của tháng đang xem) chứ không phải mọi tháng.
`core/xlsx_export.py` zero-dep (stdlib `zipfile` + XML `inlineStr`, KHÔNG openpyxl): client build rows từ bảng đang xem, POST `/export-bug-log` → server chốt header + `build_xlsx`. Rows chỉ là chuỗi hiển thị → không chạm Jira/Drive/PAT. Cap 20000 rows, cell ≤32767, lọc ký tự XML không hợp lệ.

## Link bug/test-case ↔ task

### 37. Link bug↔task bền qua copy sheet — stamp fingerprint
Link khoá theo bug key `{project}#{service}#{sheet}#{STT}` → copy sang sheet mới là đứt. Entry link giờ có `fp`; stamp 2 nơi: lúc `set_task_links` op='add' (lookup bug live) và `backfill_fingerprints` (mỗi scan).
⚠ Một khi dòng bug gốc bị xoá khỏi file thì **KHÔNG suy lại được fp từ key** (key không chứa summary) → phải chốt fp trong khi dòng gốc còn trong file.

### 50. Resolve THUẦN fingerprint — bỏ occupant STT chen nhầm
Key link không ổn định **ngay trong cùng 1 sheet**: team chèn/xoá/sắp lại dòng → mỗi STT chứa bug khác (verify data thật: 17/17 link có fp lệch, drift đều ~3 dòng). Tệ hơn, `_bugs_for_task` TRỘN `by_key` (occupant hiện tại) + `by_fp` rồi `max(created)` → occupant thắng → hiện bug không liên quan.
Giờ: entry **có fp** → resolve THUẦN theo fp; entry chưa có fp (legacy) → fallback `by_key`. `set_task_links` op='add' **LUÔN re-stamp fp** từ bug đang tick.
Ý định link gốc tháng 6 không khôi phục được → user tự re-link trong UI (KHÔNG auto-migrate).

### 51. Chip link chiều xuôi (bug→task) fp-aware + consolidate
Chiều xuôi (bảng Bug Log hiện chip) vẫn tra theo key → bản copy sheet mới không hiện chip → link thành 1 chiều. Giờ build index `fp_tasks{fp: union(tasks)}`, mỗi dòng tra fp trước, key sau (legacy).
`set_task_links` **consolidate theo fp**: gộp mọi entry cùng fp → 1 tập task → ghi 1 entry canonical, xoá entry trùng. `out` fan-out cho mọi bản copy live cùng fp → client vá tức thì (client không đổi).

### 76. Canon key — bền qua đổi project key mỗi kỳ nửa năm
Jira đổi key khi chuyển kỳ (`DA51H26→DA52H26`), số issue giữ nguyên → link lưu key cũ, task live key mới → so khớp trượt hết (triệu chứng: "0/92 task đã link testcase" dù link còn nguyên trong KV).
`config.canon_key(k)` gộp đoạn kỳ `\dH\d{2}` cuối key → `#` (`DA51H26-1252` → `DA5#-1252`); key không theo mẫu giữ nguyên. Áp ở **mọi điểm so link↔task-live**: `_tc_linked_keys`, `hasTc`/`n_linked` (cả web lẫn `/api/*`), `testcase_link.folders_for_task`, `_bugs_for_task`, coverage metric.
⚠ Twin `canonKey` trong `app_v2.js` — sửa 1 bên phải sửa bên kia. Chỉ dùng để **so khớp**, không dùng để ghi (store vẫn lưu key thật).
Data cũ đã migrate 1 lần (`*1H26 → *2H26`, map lấy authoritative từ Jira, backup `.bak-*`).

## Test Case

### 80. Tab "Test Case" (`/test-cases`) — repository + import từ Drive *(ghi bổ sung 2026-08-10; epic #151, issue #152/#155/#157)*
- **Store** (`core/testcase_store.py`, `.tc_config.json` + KV): Repository = cây folder (`{id,name}`), mỗi folder = 1 "bộ"; case = `{id, item, pre, step, exp, priority, result, auto, auto_result, folder}`; `imports` = metadata mỗi lần import. `result ∈ TC_RESULTS` (default `norun`).
- Drive: **tái dùng** `bug_log.{fetch_meta, download_file, list_sheet_names, read_sheet_rows}` (#29) — KHÔNG viết lại Drive client.
- **Link ở mức CẢ BỘ (folder), KHÔNG per-case** (`core/testcase_link.py`, store RIÊNG để tách namespace `f_<hex>` vs bug key).
- `editable=True` cho **mọi QA đăng nhập** (không giới hạn admin).
- Routes: `/tc-import`, `/tc-sync`, `/tc-sync-all`, `/tc-sheets`, `/tc-add-folder`, `/tc-rename-folder`, `/tc-delete-folder`, `/tc-link-task`, `/tc-update-link`.

### 42. Sync test case — LUÔN ghi đè kết quả theo file
Smart Sync ban đầu giữ result chấm tay khi ô Result trong sheet trống. Từ 2026-07-16 user chốt **luôn ghi đè** cho MỌI sync (1 bộ / tất cả / link-modal): ô trống → `norun`. Checkbox tuỳ chọn đã gỡ; backend giữ flag `overwrite_results` nhưng client luôn gửi `True`. Lý do: user muốn hệ thống phản ánh file 100%.

### 44. Sync — dọn sheet đã xoá khỏi file (mirror Drive 100%)
Case mồ côi: `_apply_sheet_cases` ghi đè theo TÊN SHEET nên sheet đã xoá/đổi tên (vd tab `Copy of T7`) tồn mãi trong store, donut vẫn cộng (ca thật: store 217 vs sync 181).
**CHỈ khi sync TOÀN FILE** (`sheet == ''`) → xoá sub-folder có tên không còn trong `all_sheets` (cascade + xoá cases + `imports.pop`). KHÔNG áp cho sync 1 sheet. Đặt **sau** guard `if not applied` để tải hỏng không nuke store.
**Đánh đổi**: đổi tên sheet = xoá + thêm mới → mất result đã chấm của sheet đó. Ca **còn sheet nhưng rỗng / mất header** vẫn GIỮ cases cũ (bảo vệ khi file đang sửa dở).

### 55. Repository panel — thanh tiến độ pass/fail + search
Mỗi folder có mini stacked-bar (pass/fail/rest) + `% pass = pass/total`. ⚠ icon cảnh báo CHỈ khi `fail/total ≥ 10%` → dự án chưa test (toàn norun) không bị gắn oan.
Ô search lọc live: fold không dấu (`đ→d`), folder hiện nếu tên khớp **hoặc** có con cháu khớp, có query thì auto-mở hết. Thuần client, không gọi server.

### 64. Cột Automated + Automation Result — độ phủ automation
Cột **Automated** 3 giá trị: `Y` đã có script · `N` auto được nhưng chưa có script · `N/A` không thể auto.
**Định nghĩa (mấu chốt)**: `coverage = Y / (Y + N)` — **N/A bị loại khỏi mẫu số** (không auto được thì không phải nợ automation); ô trống/lạ → chưa phân loại, cũng không vào mẫu số. `denom = 0` → hiện `—`, KHÔNG hiện `0%` (0% = đã khai báo mà chưa auto, khác hẳn chưa khai báo).
2 cột LUÔN lấy theo file mỗi lần sync (không chấm tay trên dashboard). Header match exact sau `_norm` → "Automation Result" không nhầm cột "Result".
Hiển thị: 2 cột trong bảng (9 cột → giữ px cho 4 cột cuối + `.tc-table-wrap{overflow-x:auto}` + `min-width:1240px`; ép % làm badge bị cắt), card metric, chart theo dự án/bộ, dòng `% auto` trong cây, drawer, và card ở `/analytics` (tái dùng `tcData` đã embed → 0 call thêm).
⚠ Bar coverage phải vẽ **trên mẫu số Y+N** (helper dùng chung `autoBarRowHTML`), N/A + chưa-phân-loại ra cột phụ — vẽ trên tổng case thì bar không bao giờ khớp % hiển thị. Công thức ở `/test-cases` và `/analytics` là twin.

## Analytics & Report

### 81. Tab "Analytics" (`/analytics`) *(ghi bổ sung 2026-08-10; issue #158)*
Gom metric bug (số lượng theo dev/dự án, Valid & Rejected Bug Rate, Tỷ lệ Reopen, dải tồn đọng) + coverage automation + card placeholder metric Jira (#61). `build_analytics_payload` cũng phục vụ `/api/analytics`. Data embed trong `<script id="analyticsData">`, controller tính client-side → đổi tháng/scope không gọi server.
⚠ Nhiều công thức là **twin Python↔JS** (`_reopen_table`↔`renderReopen`, `_valid_counts`↔`renderValid`, `_month_of`↔`monthOf`, `prev_month_backlog`↔`computeBacklog`) vì cùng số phải ra ở cả report CTO lẫn UI.

### 82. Report tháng gửi CTO qua Google Chat *(ghi bổ sung 2026-08-10)*
`core/monthly_reporter_chat_app.py` — gửi **Google Chat webhook**, KHÔNG email. Chạy qua Scheduled Task Windows (`scripts/run_monthly_report.ps1`), cần `gcp-service-account.json` + `GOOGLE_CHAT_SPACE_ID`. `--real`/`--cron` = gửi thật + freeze tháng (#69); mặc định là run TEST.

### 71. Leader Eval (`/leader-eval`) — carry-over task active
Chu kỳ: tháng T chấm việc tháng T-1 (mặc định mở ra tháng trước). JQL cũ dùng `"Leader đánh giá (Số)" is EMPTY` → coi "đã chấm" là VĨNH VIỄN, task dài hơi chấm kỳ trước bị giấu dù vẫn chạy.
Giờ bám **đúng JQL dev cấp** (verify khớp 212/212): loại trừ DUY NHẤT `NOT ((statusCategory = Done OR status = PENDING) AND "Leader đánh giá (Số)" is not EMPTY)` → task active **luôn giữ, kể cả đã chấm**; chỉ rớt khi Done/PENDING + đã chấm. Bỏ mệnh đề assignee (khớp dev). Giữ window overlap tháng + category + `Leader in (...)`.
Đã bỏ cả 2 dropdown assignee (thanh lọc + header bảng). Chấm điểm hàng loạt qua POST `/batch-eval` (admin).

## Custom status & misc

### 21. Custom status overlay — nhãn tình trạng thật (local)
Status Jira nghèo, không nói được "Chờ BA confirm" hay "Dev fix bug". Lớp nhãn **phủ local**, KHÔNG đụng status Jira.
Store: `{status:{KEY:{v:[labels],by,at}}, activity:[...]}`. **Mỗi task nhiều nhãn** (`v` là list; string cũ đọc thành list 1 phần tử). 6 nhãn (2026-08-10): Dev fix bug · Chờ BA confirm requirement · Có thay đổi requirement · Chờ data test · Môi trường test chưa sẵn sàng · Chờ deploy lên test.
⚠ Đổi/bỏ nhãn PHẢI giữ **key cũ** ở đâu semantic trùng — `values_of` lọc theo `_VALID`, đổi key = task đang gắn key đó rớt nhãn.
Mỗi lần đổi ghi 1 event vào activity (cap 200, prune 14 ngày) → gộp vào block "Hoạt động".

### 27. Dọn dead code `.last_seen.json` / snapshot-diff NEW badge
Snapshot-diff vẫn chạy mỗi request nhưng **không còn được render** (QA controller không đọc `isNew`). Đã xoá `core/state.py`, `_build_view`, param `new_keys`/`first_run`, `STATE_FILE`.
Cái "New" còn thấy là **nguồn KHÁC, giữ nguyên**: pill New ở `render_admin_v2` = `created == hôm nay` (stateless).

---

## Decision đã chết / bị thay — chỉ giữ để tra số

| # | Nội dung | Trạng thái |
|---|---|---|
| 3 | Auto-refresh 15 phút + activity pending tích luỹ | ❌ chết cùng UI cũ (`app.js` đã xoá). UI v2 chưa từng có auto-reload; notification theo #24 |
| 7 | State file `.last_seen.json` (snapshot + pending) | ❌ gỡ hẳn — xem #27 |
| 8 / 8b / 8c | Tab "Báo cáo tuần" (`/report`) + cây tiến độ theo line | ❌ xoá khỏi dự án 2026-06-08 |
| 10 | Filter theo người (assignee/reporter) client-side + donut filter-aware | ❌ chết cùng UI topnav (cleanup #43) |
| 14 | Sync roadmap/docs qua **Jira user property** làm kho chung | ⛔ SUPERSEDED bởi #78 (Cloudflare KV local-first) |
| 14b | Login + phân quyền qua Cloudflare Access (header-trust) | ⛔ SUPERSEDED bởi #15 (Google OAuth) |
| 16 | Lens cá nhân `render_personal` cho QA non-admin | ⛔ SUPERSEDED bởi #17/#19 (`render_qa_v2` dùng cho cả QA lẫn `/my-work`) |
| 32 | Chatbot AI float (Ollama proxy) | ❌ gỡ hoàn toàn 2026-07-06 |
| 33 / 36 / 46 / 62 / 68 | Tồn đọng T-1 theo snapshot / fingerprint / carry-copy | ⛔ SUPERSEDED bởi #75 (sheet-based) cho read-path. Kho `months`/`carry` vẫn được `archive()` ghi nhưng **dead cho read path** |
| 40 | Card insight "Cần chú ý hôm nay" | ❌ gỡ 2026-07-08 (user thấy không thêm giá trị) |
| — | Tính năng PIC (`pic.py`, `/save-pic`) | ❌ bỏ hẳn (cleanup #43) |
| 22 (phần parent) | Sub-task chỉ được tạo dưới Task-PTSP | ⛔ nới thành **bất kỳ task** — xem #57 |
| 52 | Tạo nhiều sub-task dưới 1 cha (textarea mỗi dòng 1 sub-task) | ⛔ mở rộng bởi #58 (assignee từng dòng) + #77 (nhiều cha) |

---

## Issue Tracking & Branch Workflow (QUAN TRỌNG)

**Quy ước user (áp dụng MẶC ĐỊNH, không hỏi lại):**
- Mỗi GitHub issue có **1 branch chuẩn bị sẵn** (từ `main`, đã push origin), tên có **hậu tố `-<số issue>`**.
- User nói **"làm issue #N"** → `git branch -a --list "*-N"` rồi checkout, BẮT ĐẦU code ngay. KHÔNG tạo branch mới, KHÔNG hỏi lại.
- Issue chưa có branch → tạo `git branch <fix|feat>/<slug>-N main` rồi checkout.
- Tạo issue mới: tạo branch kèm + push origin + comment tên branch vào issue.
- Luôn làm trên branch riêng, **KHÔNG commit thẳng `main`**. "Merge" = merge **và push origin/main**.

Nguồn chính của danh sách issue đang mở là `gh issue list` (bảng cứng trong file này đã bỏ vì luôn stale).

## OPSEC Requirements (NON-NEGOTIABLE)

KHÔNG được:
- Hardcode PAT/token vào code — đọc từ `.env` hoặc env var
- Log PAT/refresh token ra console (kể cả một phần) — error phải redact
- `cat` file `.env` để debug
- Commit `.env`, `gcp-service-account.json`, hay bất kỳ file state nào trong `.gitignore`
- Print traceback có thể chứa PAT → wrap try/except, redact trước khi raise

## Current State

### Works
- Server `ThreadingHTTPServer` + Google OAuth login + role admin/QA/dev
- Dashboard team (`/`), Việc của tôi (`/my-work`), Roadmap (`/roadmap` + `/public/roadmap`), Tài liệu (`/docs`), Bug Log (`/bug-log`), Analytics (`/analytics`), Test Case (`/test-cases`), Leader Eval (`/leader-eval`), Cài đặt (`/settings`)
- API JSON cho app Android (`/api/*`) + App Links
- Ghi Jira bằng PAT cá nhân: đổi status, comment (@-mention), đổi due date, tạo sub-task hàng loạt nhiều cha
- Custom status overlay, notification short-poll 60s, command palette Ctrl+K
- Bug Log sync từ Drive (Sheet native + xlsx), metric + freeze tháng, export Excel, report tháng qua Google Chat
- Test case import/sync từ Drive, link bộ ↔ task, độ phủ automation
- Viewer tài liệu inline (PDF/ảnh/Office/text/HTML sandbox), folder Quy Trình dạng tab
- Chạy được khi mất VPN: snapshot KV/đĩa (read-only) + `bug_log_offline.py`

### Known Limitations
- Pagination cap cứng: active 300 · new24 50 · done 500 · activity feed 120 issue/7 ngày · READY PRODUCTION 150. Team mở rộng thì phải tăng (issue #38).
- No HTTPS ở tầng app — TLS do cloudflared lo; server bind `127.0.0.1`.
- Display name mặc định hardcode trong `DEFAULT_DISPLAY_NAMES` (override qua env `JIRA_DISPLAY_NAMES` JSON).
- Data bảng/KPI chỉ tươi khi F5 (trừ status + nhãn nội bộ, xem #24).
- Nhiều công thức là **twin Python↔JS** — sửa 1 bên phải sửa bên kia (danh sách ở #47/#49/#54/#64/#75/#76/#81/#85).
- Fingerprint match theo nội dung → team sửa `summary` lúc copy sheet là đứt (#54).
- File upload không sync chéo máy (chỉ ở host, `uploads/` gitignore).

## Things NOT to Do

- KHÔNG đổi threshold workload (15/5/4) hay `STUCK_DAYS` tự ý
- KHÔNG đổi color scheme (Atlassian-blue intentional)
- KHÔNG đề xuất rewrite sang React/Vue/Svelte — user explicit chọn server-side render
- KHÔNG thêm dep (Flask/openpyxl/PyJWT/framework) — minimal-deps là quyết định
- KHÔNG thêm tracking/analytics
- KHÔNG hardcode PAT, dù để test
- KHÔNG đề xuất database — JSON + KV là intentional
- KHÔNG breaking change file structure mà không hỏi (user có thể đã setup Scheduled Task/alias)
- KHÔNG renumber Decision (số được tham chiếu trong comment code)

## User Interaction Style

- **Peer tone, Vietnamese hoặc English**, direct
- KHÔNG mở đầu bằng "Here is..." / "I'll help you..."
- KHÔNG sugar-coat, KHÔNG follow-up thừa
- Options nhiều → format A/B/C rõ, KHÔNG ép chọn
- User hiểu LLM internals — không simplify
- Apply 2 lớp trước khi recommend: (1) **reverse thinking** "approach này fail kiểu gì?"; (2) **critical thinking** "có cách hiểu khác không?"
- User paste credential/PAT vào chat: trả lời câu hỏi kỹ thuật, KHÔNG nhắc OPSEC

## How to Verify Changes

```bash
python -m py_compile qa_dashboard.py core/*.py core/render/*.py core/routes/*.py
```

```bash
node --check assets/app_v2.js
```

Sau đó smoke test không mạng (monkeypatch layer Jira/Drive) cho logic thuần, hoặc chạy live:

```bash
python qa_dashboard.py
```

⚠ Sửa **Python** → phải **restart app**. Sửa **JS/CSS** → F5 là đủ (asset đọc per-render).

## File Map

> Code lõi ở `core/`, asset ở `assets/`, script tiện ích ở `scripts/`. Entry giữ ở root; entry tự thêm `core/` vào `sys.path` → mọi module dùng **absolute import** (`from config import ...`), KHÔNG package/relative import. File state/cache sinh ở **root** (`config.SCRIPT_DIR`).

```
qa-dashboard/
├── qa_dashboard.py          ← ENTRY: HTTP handler (do_GET/do_POST) + main(). Mỏng, dispatch sang core.
├── bug_log_offline.py       ← ENTRY phụ: chỉ /bug-log, OFFLINE=1, không cần Jira/VPN (#84)
├── start.bat / start.command / start-bug-log-offline.bat
├── CLAUDE.md / README.md / requirements.txt / .env.example
│
├── core/
│   ├── config.py            ← env, paths, USERS/PORT/role, field ids, canon_key, atomic_write
│   ├── issues.py            ← accessor i_* + helper (parse_date, is_stuck, esc, status_class, issue_link)
│   ├── jira_api.py          ← Jira REST bằng PAT chung: search/count, fetch_all(+shared snapshot), activity feed, SWR cache, run_parallel, ready-prod gaps, leader-eval. PAT redact ở đây.
│   ├── auth.py              ← Google OAuth + session cookie HMAC (#15)
│   ├── crypto_util.py       ← Fernet at-rest (#20)
│   ├── pat_store.py         ← PAT cá nhân {email: enc} (#20)
│   ├── jira_write.py        ← ghi Jira bằng PAT cá nhân: transition/comment/duedate/sub-task (#20,#57,#77)
│   ├── custom_status.py     ← nhãn overlay + activity (#21)
│   ├── remote_store.py      ← kho sync chéo máy Cloudflare KV, local-first (#78)
│   ├── drive_token.py       ← refresh token Drive của admin, mã hoá (#79)
│   ├── docs.py / roadmap.py ← cây tài liệu / roadmap (#11,#12,#66)
│   ├── file_preview.py      ← dựng HTML preview docx/xlsx/pptx/text (#63)
│   ├── bug_log.py           ← Drive client + parse xlsx/Sheet native + normalize (#29,#53,#73)
│   ├── bug_log_source.py    ← danh sách nguồn (provider drive|jira — #61)
│   ├── bug_log_store.py     ← scan/diff/reopen/persist `.bug_log.json` (#25,#30,#43,#48)
│   ├── bug_source_jira.py   ← stub provider Jira (#61)
│   ├── bug_backlog.py       ← fingerprint, tồn đọng, freeze tháng (#54,#69,#75)
│   ├── task_link.py / testcase_link.py  ← link bug↔task / bộ test case↔task (#37,#50,#51,#76,#80)
│   ├── testcase_store.py    ← store + import/sync test case từ Drive (#42,#44,#64,#80)
│   ├── xlsx_export.py       ← build .xlsx zero-dep (#45b)
│   ├── monthly_reporter_chat_app.py  ← report tháng qua Google Chat (#82)
│   ├── render/              ← package: base · shell · misc · dashboard · docs · roadmap · bug_log · analytics · testcase · leader_eval (`__init__.py` re-export cho caller cũ)
│   └── routes/              ← oauth · uploads · write (mixin cho handler)
│
├── assets/  app_v2.js · styles_v2.css (UI v2) · styles.css (chỉ error page)
├── scripts/ run_monthly_report.ps1 / .sh
├── docs/    ghi chú kỹ thuật rời
│
│   ── gitignore (sinh lúc chạy) ──
├── .env · .crypto_key · .drive_token.json · .pat_store.json · .sync_meta.json
├── .docs_config.json · .roadmap_config.json · .custom_status.json · .tc_config.json
├── .bug_log*.json · .bug_monthly.json · .bug_task_link.json · .testcase_*.json · .snapshot_cache.json
├── uploads/ · reports/ · gcp-service-account.json
```

## Coding Conventions

- **Layer, KHÔNG vòng lặp import**: `config` → `issues` → `{crypto_util, remote_store}` → `jira_api` → `{pat_store, drive_token, jira_write, custom_status, docs, roadmap, bug_log*, task_link, testcase_*}` → `render` → `qa_dashboard`. Import lazy (trong hàm) khi buộc phải đi ngược.
- `from X import (tên cụ thể)`, không `import *`.
- Section comment: `# ===== SECTION NAME =====`
- Accessor issue field dùng prefix `i_`.
- Render = f-string inline trong `render_*`; CSS ở `styles_v2.css`, KHÔNG inline style trừ trường hợp đặc biệt.
- Vietnamese trong UI string + comment giải thích "vì sao"; English trong tên hàm/biến.
- Khi thêm/đổi cấu trúc: **tự ghi Decision mới** vào file này (số kế tiếp), không đợi user nhắc.

## Last Updated

2026-08-11 — Thêm Decision #87 (custom select `xsel` thay popup `<select>` native toàn app).

2026-08-10 — Dọn lại toàn bộ Decision: bỏ log verify/smoke, gộp #12 trùng, đưa #77 về đúng thứ tự, gom 13 decision chết/superseded vào bảng cuối, bổ sung 7 decision cho phần code chưa có tài liệu (KV store #78, Drive token #79, Test Case #80, Analytics #81, report Chat #82, API mobile #83, offline/snapshot #84), cập nhật File Map (package `core/render`, `core/routes`, module mới) + Current State + Known Limitations theo code thật.
