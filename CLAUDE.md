# CLAUDE.md

Context cho Claude Code khi làm việc trên project này.

## Project Purpose

Custom HTML dashboard **dùng riêng cho 1 người** (`thanhht1`, chạy trên chính máy host — Decision #96/#97), pull data live từ Jira qua REST API + đọc bug log từ Google Drive. Thay cho Jira native dashboard (xấu, buggy, không merge cell, không conditional formatting).

**User là QA sub-lead** (từ ~2026-10-06; trước là Acting QA Manager), đang commit **30% effort hands-on vào 1 squad** + phần còn lại review cấp leader cùng 1 leader khác. Từ 2026-10-02 dashboard chỉ còn việc của chính user (Việc của tôi · Bug Log · Analytics · Tài liệu); dashboard team, roadmap, test case, đánh giá leader, app Android đã gỡ (#97). Phần tự gửi report tháng cho CTO cũng đã gỡ (#100) — Analytics vẫn giữ nguyên để xem số.

## Tech Stack

- Python 3.8+ (walrus dùng được)
- External deps: **`requests` + `cryptography`** (Fernet mã hoá PAT/Drive token at-rest). Nguyên tắc **minimal-deps** — KHÔNG thêm Flask/FastAPI/openpyxl/PyJWT.
- HTTP server: `http.server.ThreadingHTTPServer` stdlib (Decision #28)
- Server-side render HTML bằng f-string templates, **vanilla JS, KHÔNG framework**
- Asset: `assets/app_v2.js` + `assets/styles_v2.css` (UI v2 "Stitch" sidebar — Decision #19), đọc **per-render** → sửa JS/CSS chỉ cần F5, sửa Python phải **restart app**. `assets/styles.css` chỉ còn `render_error_page` dùng.
- Kho state chéo máy: **Cloudflare Workers KV** (local-first, không cần VPN — Decision #78), fallback Jira user property + cache file local ở root.

## Architecture

```
[Browser / app Android] ←HTTP→ [Python qa_dashboard.py] ←REST+API token→ [Jira Cloud baokim.atlassian.net]
                                (localhost:8080)        ←REST+OAuth→ [Google Drive]
                                                        ←REST+token→ [Cloudflare KV]
```

- F5 = pull data tươi (bypass SWR cache — Decision #26b); click chuyển tab = phục vụ cache SWR
- Notification tự cập nhật qua short-poll 60s (Decision #24); phần còn lại tươi khi F5

## Domain Context — Jira Bảo Kim

### Instance
- URL: `https://baokim.atlassian.net` · **Jira Cloud** (chuyển từ Data Center 10.7.3 `jira.baokim.vn:8443` — Decision #94)
- Auth: `Authorization: Basic base64(email:api_token)` · REST `/rest/api/2/search/jql` (search cũ đã bị gỡ, trả 410)
- Identity = `accountId` (không còn username) → dịch ở biên qua `core/jira_cloud.py`, app vẫn dùng username nội bộ

### Workflow statuses (CHÍNH XÁC theo case + spacing)
`TO DO` · `In Progress` · `PENDING` · `DONE` · `CANCELLED` (+ `READY PRODUCTION` bên task dev)
⚠ Đây là tên **sau khi `jira_cloud.canon_status` chuẩn hoá** — Cloud trả `To Do`/`Done`/`Pending`, changelog migrate giữ `TO DO`/`DONE`. Code Python/JS so tên DC ở trên (Decision #94).

Status categories (filter an toàn hơn tên status): `new` → TO DO · `indeterminate` → In Progress/PENDING · `done` → DONE/CANCELLED

### QA team (5 người + 1 manager)
⚠ App chỉ **tracking task của `thanhht1`** (`config.USERS = [SELF_USER]`, #97). Bảng dưới còn là ngữ cảnh domain: tên tester/dev vẫn xuất hiện trong Bug Log/Analytics (nguồn file Drive của cả team), Hiền vẫn là Leader/reporter.

| Username | Display name | Role |
|---|---|---|
| `quangbm` | Quang | QA |
| `nhungnh` | Nhung | QA |
| `phuongct` | Phương | QA |
| `tholt` | Thơ | QA |
| `thanhht1` | Thành | QA sub-lead (admin, 30% effort 1 squad) |
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

### 99. Autostart lúc logon — Scheduled Task + pythonw *(2026-10-02, issue #198, code: `scripts/install_autostart.ps1`)*
2 task cho user hiện tại: **"QA Dashboard"** (AtLogOn → `pythonw.exe qa_dashboard.py`, restart 3 lần/1′, không giới hạn thời gian chạy, `-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries` — thiếu là Windows bỏ qua trigger im lặng khi chạy pin) + **"QA Dashboard Window"** (AtLogOn, trễ 20s → Edge/Chrome `--app=http://localhost:<PORT>/`, cửa sổ riêng). Kèm shortcut Desktop. `-Uninstall` gỡ sạch, `-NoWindow` bỏ task cửa sổ.
- Python ưu tiên **`.venv\Scripts\pythonw.exe`** của repo: Python hệ thống trên máy này THIẾU `cryptography` → server chết ngay lúc import. Script check `import requests, cryptography` trước khi đăng ký.
- pythonw không có console → `sys.stdout/stderr = None` → `log_message` crash mỗi request. Entry tự đổ cả 2 ra `reports/dashboard.log` (line-buffered) khi phát hiện `None`.
- `.ps1` **ASCII-only** (PS 5.1 đọc file không-BOM theo ANSI). URL phải `localhost` (không `127.0.0.1`) vì OAuth redirect URI (#96).
- ⚠ **User tự chạy** trong terminal của họ: `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_autostart.ps1` — đừng chạy qua Claude Code (container MSIX, xem CLAUDE.md user-level).

### 13. Session keep-alive + call Jira song song
`requests.Session` dùng chung (`jira_api._SESSION`) tái dùng kết nối TLS; `run_parallel(jobs)` (ThreadPoolExecutor cap 8) chạy các call độc lập đồng thời, re-raise lỗi đầu tiên → handler render trang lỗi như cũ. Áp trong `fetch_all` (5 call) và ở handler (`fetch_all ‖ feed ‖ dismissed`). Pool lồng nhau → đỉnh ~7-8 request đồng thời tới Jira, chấp nhận được (I/O-bound).

### 26. Cache stale-while-revalidate (SWR)
Chuyển tab chậm 6-10s vì mỗi page block trên call Jira nặng (`fetch_activity_feed` chạy mọi tab vì chuông). `_cached_swr(key, producer)`: fresh (`_CACHE_TTL=120s`) → trả ngay · stale (tới `_CACHE_STALE_TTL=900s`) → trả data cũ + refresh nền 1 thread/key (`_cache_inflight` chống stampede) · miss/quá cũ → tính đồng bộ (raise nếu Jira lỗi). Bonus: refresh nền lỗi bị nuốt → giữ stale thay vì trang lỗi.
**Đánh đổi**: page có thể cũ tối đa ~15' nhưng tự tươi ngầm. Knob: 2 hằng số trong `jira_api.py`.

### 26b. "F5 = luôn tươi" — bypass SWR khi user chủ động refresh
Phân biệt bằng header `Cache-Control` của browser: F5 gửi `max-age=0`, Ctrl+F5 gửi `no-cache`, click `<a>` không gửi → `_wants_fresh()`. `force=True` xuyên `_cached_swr` / `fetch_all` / `fetch_activity_feed` / `fetch_all_shared` (bỏ qua cache SWR RAM).
**KHÔNG force**: endpoint poll `/activity-feed` (60s) — poll không phải F5.

### 28. ThreadingHTTPServer — hết đơ toàn cục
`TCPServer` xử lý tuần tự → 1 request ngậm read-timeout 30s là mọi tab đứng hình. Đổi `ThreadingHTTPServer` + `daemon_threads`. An toàn vì `.last_seen.json` đã gỡ (#27), mọi kho ghi đã có lock, và `atomic_write` dùng tmp-name theo pid+thread → last-writer-wins ở mức file hoàn chỉnh.

### 78. Kho sync chéo máy = Cloudflare KV, local-first *(ghi bổ sung 2026-08-10, code: `core/remote_store.py`)*
SUPERSEDES Decision #14 (Jira user property làm kho chung). Jira nằm sau VPN → mất VPN là `save` FAIL, data không lưu nổi. Đổi kho chung sang **Cloudflare Workers KV** (REST api.cloudflare.com, internet công cộng) và đảo nguyên tắc:
- **save**: ghi file local TRƯỚC (luôn thành công) → đẩy KV best-effort → dirty-flag (`.sync_meta.json`) nếu KV không với tới, flush ở lần load/save kế.
- **load**: KV thắng khi với tới được **và** local không dirty; KV rỗng → seed từ local (hoặc Jira 1 lần để migrate); KV chết → dùng local.
Dùng bởi: docs · custom-status · PAT · Drive token · task_link · bug backlog (roadmap/testcase gỡ ở #97, key KV cũ còn nguyên). Bỏ trống creds CF (`KV_ENABLED=False`) → fallback Jira property, vẫn local-first.
**Giới hạn**: mô hình 1 instance/lúc (host migration Mac↔Win) → last-write-wins, không timestamp; host ghi local rồi chết trước khi flush + sửa tiếp ở host khác thì mất edit chưa flush.

### 95. Gỡ mọi phần xử lý mất VPN (snapshot L2/L3 + chế độ OFFLINE) *(2026-10-02)*
SUPERSEDES #84. Jira Cloud (#94) đi qua internet công cộng, không còn VPN/whitelist IP → toàn bộ cơ chế "sống khi mất VPN" thành gánh nặng:
- **Snapshot task**: bỏ L2 Cloudflare KV `qa-snapshot` + L3 `.snapshot_cache.json` + dedup hash. `fetch_all_shared(force)` giờ chỉ là `fetch_all(None)` (SWR RAM #26) — chỉ còn 1 host (Windows) nên snapshot chéo máy không phục vụ ai. Jira lỗi mạng → trang lỗi / vùng task báo lỗi như mọi call Jira khác (SWR vẫn phục vụ data cũ tới 900s).
- **Giữ `'auth'`**: token chung hết hạn (`JiraAuthError`) → phục vụ bản RAM cuối cùng (bất kể tuổi) + banner đỏ "API token hết hạn"; chưa có bản RAM (vừa restart) → trang lỗi. Return vẫn là `(data, stale)` với `stale ∈ {False, 'auth'}`; `/api/*` giữ key `stale` cho app Android.
- **Bỏ read-only**: gỡ `window.__stale` + guard `JIRA_WRITE` trong `postJSON` — write dùng token cá nhân nên token chung chết không chặn ghi.
- **Bỏ chế độ OFFLINE**: xoá `bug_log_offline.py`, `start-bug-log-offline.bat`, `config.OFFLINE` (+ dummy Jira creds) và các nhánh `if OFFLINE` trong `jira_api`/`jira_cloud`/`qa_dashboard.main`.
- **Report tháng** *(đã gỡ — #100)* (`scripts/run_monthly_report.{ps1,sh}`): dựng `qa_dashboard.py` (thay `bug_log_offline.py`) trên port riêng 8077; reporter vào `/analytics` bằng cookie phiên admin ký `SESSION_SECRET` (đã có sẵn). Probe sẵn sàng bằng `/.well-known/assetlinks.json` (public, không gọi Jira) vì `/analytics` redirect login khi AUTH bật.
**Giữ nguyên có chủ đích** (bảo vệ khi mạng/Jira chập chờn nói chung, không riêng VPN): connect-timeout 5s, circuit breaker #160, retry + `reset_pool`, chuông best-effort `block=False`, KV local-first #78 (kho sync, không phải tính năng VPN).

## Auth & phân quyền

### 15. Google OAuth login (thay Cloudflare Access)
Golive trên `baokim-qa.com`; Cloudflare Access kẹt ở bước Activate Zero Trust (thẻ VN fail). Mô hình: app redirect sang Google → nhận email đã verify → check `verified_email` + domain `@baokim.vn` → set **session cookie ký HMAC** (TTL 12h). Zero new deps (stdlib `hmac/hashlib/secrets/http.cookies`), dùng userinfo endpoint nên không cần verify JWT.
- `core/auth.py`: `login_url`/`exchange_code`/`email_allowed`/`make_session_token`/`email_from_session`/`make_state_token` (CSRF, TTL 10p). KHÔNG log token.
- `.env`: `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` + `SESSION_SECRET`. Bỏ trống 2 cái đầu = local dev (`AUTH_ENABLED=False`).
- Cookie `HttpOnly; SameSite=Lax; Secure(https)`. `_base_url()` dựng từ `Host` + `X-Forwarded-Proto` để redirect_uri đúng cả prod lẫn localhost.
- Google Cloud: redirect URI = `https://baokim-qa.com/oauth/callback` + `http://localhost:8080/oauth/callback`, consent screen **Internal**.

### 31. AUTH tắt = fail-closed (loopback-only)
Trước: `AUTH_ENABLED=False` → mọi request là admin (fail-**open**) — quên creds / bind nhầm 0.0.0.0 là mất trắng. Giờ AUTH tắt → chỉ request từ **loopback** (`_is_loopback()` đọc `self.client_address[0]`, KHÔNG tin `X-Forwarded-For`) mới là admin, còn lại 403. AUTH bật → giữ nguyên. Server vẫn bind `127.0.0.1` (lớp 1); đây là defense-in-depth lớp 2.

### 97. Dashboard dùng riêng 1 người — gỡ tracking người khác + dashboard team / roadmap / test case / đánh giá / API mobile *(2026-10-02)*
User chốt (sau #96): dashboard là **của riêng mình**, không quản lý team qua đây nữa, bỏ app Android.
- **Roster** `config.USERS = [SELF_USER]` — **bỏ qua `JIRA_USERS` trong `.env`** để không vô tình kéo lại task người khác. Mọi JQL `assignee/reporter in (USERS)` (bucket, activity feed #9, warm accountId) tự thu về task của mình; không phải sửa từng chỗ.
- **Gỡ trang**: dashboard team `/` (`render_admin_v2`, workload #5, pill/KPI admin, card Metric Bug) → `/` redirect `/my-work` · Roadmap `/roadmap` + `/public/roadmap` (#12) · Test Case `/test-cases` + mọi `/tc-*` (#80/#42/#44/#55/#64/#91) · Đánh giá `/leader-eval` + `/batch-eval` (#71) · API mobile `/api/*` + `/.well-known/assetlinks.json` + Bearer token + OAuth `state.app`/`APP_REDIRECT` (#83) · role dev `JIRA_DEV_EMAIL` (#45). Module xoá: `roadmap.py`, `testcase_store.py`, `testcase_link.py`, `render/{roadmap,testcase,leader_eval}.py`; `build_dashboard_payload`/`build_analytics_payload`/`_cross_metrics` cũng đi theo (chỉ phục vụ API).
- **Ăn theo**: drawer bỏ mục "Bộ test case liên quan"; bảng Việc của tôi bỏ cờ `hasTc` + note "🔗 x/y task đã link bộ test case"; Analytics bỏ 4 card Test Coverage / Execution / Bug Density / Automation Coverage (đều dựa test case). CSS: gỡ rule mà class/id chỉ còn ở code đã xoá (so source HEAD vs sau khi xoá).
- `/my-work` giờ là trang chính *(từ #102 trang chính là `/today`, `/` redirect về đó)*, **admin-only → 403** (không redirect về `/` vì `/` lại redirect về `/my-work` → vòng lặp).
**Giữ nguyên có chủ đích**: Bug Log + Analytics vẫn đủ bug cả team (user chọn); Tài liệu; tạo sub-task (#22/#57/#58/#77 — dropdown QA giờ chỉ còn mình); custom status #21; chuông #24.
**Data KHÔNG xoá**: `.roadmap_config.json`, `.tc_config.json`, `.testcase_*.json` + key KV tương ứng vẫn nằm nguyên — chỉ gỡ code. Muốn khôi phục: revert commit của #97. `remote_store` không còn ai đọc các key đó.

### 96. LOCAL_ONLY — dashboard chỉ phục vụ chính máy host *(2026-10-02, code: `qa_dashboard.py:_local_only_ok`)*
User chốt dashboard thành **của riêng mình**: không dùng trên điện thoại, đã bỏ app Android. Server bind `127.0.0.1` từ trước nên LAN không vào được, nhưng **tunnel cloudflared** (`baokim-qa.com`) cũng tới app từ `127.0.0.1` → `_is_loopback()` không phân biệt được người ngồi trước máy với người trên internet.
- `config.LOCAL_ONLY` (env `LOCAL_ONLY`, **mặc định BẬT**, `0/false/no` để tắt). Gate `_local_only_ok()` chạy **đầu tiên** ở `do_GET`/`do_POST` (trước cả `/login`, `/public/roadmap`, `assetlinks`), 3 điều kiện: (1) peer TCP loopback; (2) KHÔNG mang header tunnel (`Cf-Connecting-IP`/`Cf-Ray`/`Cf-Visitor`/`Cdn-Loop`/`X-Forwarded-For` — Cloudflare edge + cloudflared luôn gắn, browser gõ localhost không bao giờ gửi); (3) `Host` ∈ `localhost`/`127.0.0.1`/`[::1]` (chặn DNS rebinding). Thiếu 1 → 403.
- **Giữ Google OAuth** (không tắt AUTH): tắt AUTH thì identity rỗng → PAT tra theo key `'local'` thay vì email → mất token cá nhân đã lưu. Thay vào đó LOCAL_ONLY **bỏ qua `PUBLIC_BASE_URL`** (domain chết khi tắt tunnel) → redirect_uri suy từ Host = `http://localhost:<PORT>/oauth/callback` (đã đăng ký sẵn, #15). Suy từ Host an toàn vì gate (3) đã ép Host loopback. (`APP_REDIRECT` đã gỡ hẳn ở #97.)
- Gate ở app là lớp chặn **dù tunnel lỡ còn chạy**; tắt tunnel cloudflared là việc của user (ngoài app).
**Ranh giới**: phải mở bằng `http://localhost:8080` (KHÔNG `127.0.0.1`) vì Google chỉ nhận redirect URI đã đăng ký. Muốn mở lại domain: `LOCAL_ONLY=0` + bật tunnel — `PUBLIC_BASE_URL` trong `.env` vẫn còn nguyên.

### 98. Auto-login chính chủ + chặn CSRF cho mọi POST *(2026-10-02, issue #198, code: `qa_dashboard.py:_user_email/_same_origin_ok`)*
Dashboard 1 người, đã có LOCAL_ONLY (#96) → login Google chỉ là thao tác thừa. Request **đã qua `_local_only_ok`** + không có session cookie → identity = `config.OWNER_EMAIL` (= `<SELF_USER>@<ALLOWED_DOMAIN>` nếu nằm trong `JIRA_ADMIN_EMAIL`, else admin duy nhất; nhiều admin không đoán được → `''` = tắt, KHÔNG chọn bừa vì `ADMIN_EMAILS` là set). Identity vẫn là **email** (không phải `'local'`) → API token cá nhân lưu theo email (#20) dùng tiếp, 0 migrate.
- `config.LOCAL_AUTOLOGIN` = `LOCAL_ONLY and AUTH_ENABLED` và env `LOCAL_AUTOLOGIN` không phải `0/false/no` (mặc định BẬT). `/login` → redirect `/`; sidebar ẩn "Đăng xuất" (đăng xuất xong vẫn tự vào lại).
- ⚠ **Bỏ cookie = mất lớp SameSite=Lax chống CSRF**: trang web lạ đang mở (hoặc HTML upload chạy trong iframe sandbox `/file-raw` #65, origin `null`) POST tới `localhost:8080` mang `Host: localhost` → gate #96 KHÔNG chặn. Nên `do_POST` thêm `_same_origin_ok()` chạy **trước** `_authed`: `Sec-Fetch-Site` có mặt mà ∉ {`same-origin`,`none`} → 403; `Origin` có mặt mà netloc ≠ `Host` (gồm `null`) → 403. Thiếu cả 2 header (curl/script local) → cho qua: tiến trình trên chính máy ngoài mô hình đe doạ (đọc được `.env` rồi). Áp **cả khi tắt auto-login** (defense-in-depth).
**Ranh giới**: GET không cần check — đọc cross-origin bị CORS chặn, DNS rebinding đã bị Host check (#96); GET có side-effect duy nhất (`/drive/connect`, `/oauth/drive-callback`) cần state HMAC nên không giả được. Cookie phiên vẫn thắng nếu có (report/test cũ vẫn chạy).

### 94. Chuyển Jira Data Center → Jira Cloud — dịch ở biên *(2026-09-25, issue #197, code: `core/jira_cloud.py`)*
SUPERSEDES Decision #2 (Bearer PAT). Công ty chuyển sang `https://baokim.atlassian.net`. 3 khác biệt gốc, mọi thứ khác kéo theo:
1. **Auth** = `Basic base64(email:api_token)`. `.env`: `JIRA_EMAIL` + `JIRA_API_TOKEN` (thay `JIRA_PAT`; config vẫn export `PAT` = token chung vì nhiều module import để redact). Token classic (không scoped) → gọi thẳng site URL.
2. **Identity = accountId**, không còn `name`. Chọn **dịch ở biên**, KHÔNG đổi khoá nội bộ: app vẫn dùng username (= local-part email) → mọi store (custom_status, task_link, testcase_link, pat_store, dismissed, KV) giữ nguyên, 0 migrate.
   - ĐỌC: `normalize()` duyệt mọi response search → gắn `name`/`key` = username vào user object (từ `emailAddress`, fallback map; không có email → `accountid:<id>`), đổi `from`/`to` của changelog assignee sang username, đổi mention `[~accountid:X]` → `[~username]` trong body/description. Nhờ vậy `i_*`, `actor_name`, #34, #60, cờ mention #9, JS (twin) **không đổi**.
   - GHI/JQL: `jql_user`/`jql_users` (JQL `assignee in ("<accountId>")`), `user_ref` (payload `{'accountId':…}` cho assignee/Leader), `mentions_to_accounts` (comment). Map username↔accountId resolve lazy qua `/user/search?query=<u>@<domain>`, cache `.jira_accounts.json` (gitignore), override env `JIRA_ACCOUNT_IDS`, warm nền lúc khởi động. `jql_users` bỏ qua người không resolve được, chỉ raise khi không ai resolve được (JQL user lạ = Cloud trả 400).
3. **Search**: `/rest/api/2/search` bị gỡ (410) → `/rest/api/2/search/jql` phân trang `nextPageToken` (không `total`, ≤100/trang); `jira_count` → `POST /rest/api/2/search/approximate-count` (KPI Done/Vào-Ra tuần có thể trễ vài giây). Giữ **v2** (không lên v3) vì v2 trả comment/description dạng wiki string, v3 là ADF.
- **Tên status**: `canon_status` đưa `To Do/Done/Pending/Canceled` về tên DC ở MỌI chỗ đọc (status object, changelog, transitions, `get_issue_status`) → ~40 chỗ so sánh Python + JS giữ nguyên. Status lạ giữ nguyên.
- **Field id đổi hết** (config): sub-task `10008`, Task-PTSP `10348`, Start date = `customfield_10305` "Start date (migrated)" (REQUIRED; field "Start date" 10015 mới của Cloud trống), Leader `10318`, Department `10315`(IT=`10314`), BK Team `10306`(IT-QA=`10332`), điểm `10317`, text `10309`. JQL tham chiếu field qua `jql_cf()` (`cf[10305]`) vì tên field trên Cloud có bản trùng.
- **Token cá nhân (#20)**: lưu credential `email:token` (chính là cặp Basic) đã mã hoá; user chỉ dán token, email = email login. Verify = `/myself` bằng Basic(email login, token) → Cloud buộc email khớp chủ token nên thành công = đúng người (bỏ so username/local-part). PAT DC cũ trong kho (không có `email:`) → `load_user_pat` trả None → UI nhắc dán lại, không migrate.
- 429 (rate limit Cloud) → retry theo `Retry-After` (cap 10s, 2 lần) ngay trong `_request_short_connect`.
- Project key GIỮ NGUYÊN sau migrate (DA52H26, PSIT2H26…) → link bug/testcase ↔ task trong KV không trượt, không phải migrate.
- **Migrate CHƯA XONG (2026-09-25)**: IT mới chuyển đủ screen cho DA52H26/DA62H26/DA72H26/DA102H26/PSIT2H26 — CRS/D8TN/DAIT2026/DEMOIT/SIT* thiếu field custom trên màn tạo sub-task, AM/PT/PTSP dùng type sub-task khác → tạo sub-task ở đó Jira trả 400. Cố ý CHƯA làm createmeta-aware (cấu hình còn đổi). Khi IT báo xong: chạy `scripts/jira_cloud_probe.py` (chỉ đọc) đối chiếu field/type/option/createmeta với config rồi mới quyết.
**Giới hạn**: privacy ẩn email → người đó không resolve được → khai `JIRA_ACCOUNT_IDS`. Changelog assignee của người ngoài roster chưa từng gặp hiện `accountid:<id>` trong `from/to` (UI vẫn hiện displayName qua `fromString/toString`). API token Cloud hết hạn tối đa 1 năm → banner đỏ "API token hết hạn" (`'auth'`, #95). Offline mode/snapshot #84 đã gỡ ở #95.

### 92. Gỡ tin header `Cf-Access-Authenticated-User-Email` — auth bypass *(2026-09-14, code: `qa_dashboard.py:_user_email`)*
`_user_email` có nhánh fallback cuối tin **header trần** `Cf-Access-Authenticated-User-Email` do client gửi. Header đó CHỈ đáng tin khi **Cloudflare Access** ngồi trước tự set + strip header giả — nhưng CF Access đã bỏ (#15), tunnel hiện tại là **plain cloudflared KHÔNG strip**. Hệ quả: `curl -H "Cf-Access-Authenticated-User-Email: thanhht1@baokim.vn" .../settings` → thành **admin**, bypass toàn bộ Google OAuth (`_authed`/`_is_admin` khi AUTH bật chỉ cần email hợp lệ, không đòi loopback; email bịa vẫn qua `_domain_ok`). Là backdoor sống, không phải rủi ro lý thuyết — verify bằng curl trên origin.
Fix: **bỏ hẳn** nhánh CF header → identity CHỈ từ Bearer token (mobile) hoặc session cookie, cả hai đều là **token HMAC do app ký** (`email_from_session`). Rủi ro gỡ = 0 vì không có CF Access nào set header đó hợp lệ nữa. Đây là phần còn sót của issue #44 (khuyến nghị #3 hoãn khi đóng #44 — chỉ làm fail-closed #31).
**Ranh giới**: nếu sau này bật lại CF Access thật thì phải verify JWT `Cf-Access-Jwt-Assertion` (chữ ký), KHÔNG quay lại tin header trần.

### 20. PAT cá nhân + ghi Jira đúng tên người
App dùng 1 PAT chung → mọi thao tác ghi mang tên chủ PAT, sai attribution. Mỗi QA dán **PAT cá nhân** ở `/settings`.
- `pat_store.py`: `{email: enc_pat}`; trước khi lưu **verify PAT thuộc đúng người đăng nhập** (`/myself`, so username với local-part email) — chặn dán nhầm PAT người khác.
- `crypto_util.py`: Fernet, khoá derive từ `SESSION_SECRET` qua scrypt (local dev → `.crypto_key`). Chống rò rỉ file at-rest, **không** chống server bị chiếm.
- `jira_write.py`: ghi bằng PAT truyền vào (KHÔNG dùng `_SESSION`/PAT chung); redact PAT mọi lỗi.
- **Không có PAT → từ chối ghi** (`code:no_pat`, UI nhắc vào Cài đặt) thay vì ghi nhầm tên chung. Jira tự enforce quyền.

### 79. Drive OAuth — 1 refresh token của admin *(⛔ GỠ HẲN ở #104 — Bug Log nguồn Jira; `drive_token.py` + luồng connect/callback đã xoá)*
Bug log + test case đọc file trên Drive công ty → chỉ cần **1 token đọc của admin**, không phải per-user như PAT. Refresh token mã hoá Fernet, lưu KV `qa-dashboard-drive-token` + cache `.drive_token.json`. Routes `/drive/connect`, `/oauth/drive-callback`, `/has-drive`, `/disconnect-drive`. KHÔNG plaintext, KHÔNG log token.

## Data Jira: fetch, bucket, notification

### 4. JQL dùng `statusCategory != Done` cho bucket active
An toàn hơn `status != "DONE"` nếu workflow thêm status mới; DONE + CANCELLED đều thuộc category Done.

### 4b. Bucket `done_week` dùng `status = "DONE"` (KHÔNG dùng `resolved`)
Workflow Bảo Kim thường không set resolution → `resolutiondate` null → `resolved >= ...` trả rỗng. Từ 2026-07-07 (user yêu cầu) bỏ luôn cửa sổ 3 ngày: JQL `status = "DONE" ORDER BY updated DESC`, `max_results=500`, nhãn KPI "Done". Cột thời gian hiển thị `resolutiondate`, fallback `updated`.
"Vào/Ra tuần" (`resolved_week`) VẪN dùng `status CHANGED TO "DONE" AFTER startOfWeek()` — không đụng.

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

## UI v2 & tương tác

### 19. UI v2 "Stitch" — sidebar Material 3
Redesign toàn app sang sidebar Material 3, vanilla JS + string template. Shell chung `_document_v2(content, active, user, activities, title)` = `render_sidebar_v2` + `render_topbar_v2` (chuông) + drawer dùng chung + modal (settings/sub-task/palette) + nhúng `window.__jiraBase` / `__isAdmin` / `QA_CUSTOM_STATUSES` / `__mentionUsers`. Trang: `render_qa_v2` (Việc của tôi), `render_docs_page`, `render_bug_log_v2`, `render_analytics_v2`, `render_settings_page` (dashboard team/roadmap/test case/leader eval đã gỡ — #97).
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

## Tab: Tài liệu

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
**Bổ sung 2026-09-17 — nút "Mở tab mới" = trang `/file-view` toàn màn hình**: `/uploads/` chỉ serve `inline` cho **pdf + ảnh raster**, mọi loại khác ép `attachment` (#70) → nút "Mở tab mới" (và menu "Mở link") trỏ thẳng `/uploads/...` với docx/xlsx/pptx/text là **tải file về**, không xem được gì. Thêm route **`/file-view?f=`** (`routes/uploads._get_file_view` + `render_file_view_page`): shell mỏng (thanh tiêu đề + nút Tải xuống) bọc chính nội dung `file_preview.preview_html`, chiếm trọn viewport — KHÔNG sidebar, KHÔNG overlay. JS tách `fpTabUrl` khỏi `fpOpenUrl` (cái sau vẫn chỉ dùng cho `src` iframe): html → `/file-raw` (#65) · pdf/ảnh → `/uploads/` (browser render inline) · còn lại → `/file-view`. KHÔNG dùng deep-link `/docs?doc=` cho việc này: tab mới sẽ chỉ là bản sao trang app kèm nền mờ, không phải chế độ đọc full-screen. Trang tự mang lại listener đổi sheet xlsx (markup `file_preview` không kèm script) + snippet theme `qa-theme`.

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

### 104. CUT-OVER Bug Log: Google Drive → Jira "Bug Testing" *(2026-10-05, issue #198, code: `core/bug_source_jira.py`)*
REALIZES #61 (bật `provider='jira'` thật) + SUPERSEDES #75 (tồn đọng sheet-based → created-based) + gỡ nhánh Drive khỏi đường chính. User chốt: QA log bug **trực tiếp trên Jira** bằng issue type **Bug Testing (10382)**, **bỏ hẳn Google Drive**, data Drive cũ (tháng 10) không đáng tin → xoá (`scripts/reset_bug_log.py`, chạy 1 lần).
- **Nguồn**: `bug_log_source.load_sources()` rỗng → mặc định 1 source Jira `{provider:'jira', id:'bug-testing', query:config.BUG_TESTING_JQL}` (`issuetype = 10382 ORDER BY created DESC`, chưa lọc project). `config.BUG_LOG_JIRA_ENABLED` mặc định **BẬT**.
- **Map** (`bug_source_jira._issue_to_bug`, khớp schema `bug_log.normalize`): `key`=issue.key (ỔN ĐỊNH) · `project`=project.key (= **squad** SIT1-4, user chốt chia theo squad không theo dự án) · `service`/`feature`=`''` (bỏ) · `bug_no`=phần số của key · `status`=`_bug_lifecycle(status_raw)` (map RIÊNG: TRIAGE/Open→New, In Progress/TESTING→Fixing, Reopened→Reopen, REJECTED→Rejected, Done→Closed — vì status Bug Testing NGOÀI `jira_cloud.canon_status`) · `severity`=field **Severity** `customfield_10404` (Blocker/Critical/High→Major, Medium→Normal, Low→Minor qua `_sev_bucket`; null→none) · `qa_pic`=reporter, `dev_pic`=assignee · `month`=created[:7] · `reopen_count`=đếm changelog `toString=='Reopened'`.
- **Reopen CHÍNH XÁC từ changelog** (`bug_log_store._apply_jira_reopens`): set `reopen_map[key]` thẳng từ `reopen_count` mỗi scan, KHÔNG dùng accumulator diff-poll / seed / fingerprint-carry (chỉ chạy cho nhánh Drive nếu còn). `_jira_request(expand='changelog')` lo phân trang + normalize.
- **Backlog CREATED-BASED** (thay #75 sheet-based): tồn đọng tháng T = bug `created < T` **còn mở tới giờ** (gom từ mọi tháng); mới = `created ∈ T`. 'Nợ cũ đã xử lý' (resolved) = 0 (không suy được chính xác theo lịch sử). Twin: `bug_backlog.prev_month_backlog` ↔ `computeBacklog` + `splitGroups` (JS). `_dedup_by_fp`/`dedupByFp` dedup theo **key** (không fp) → không gộp nhầm bug trùng summary.
- **Gỡ Drive**: route `/drive/connect`, `/oauth/drive-callback`, `/has-drive`, `/disconnect-drive`, `/save-bug-log-sources`; card "Kết nối Drive" (modal Setting + /settings); UI "Quản lý link drive" + picker file. bug id ở bảng = **link** `{JIRA_URL}/browse/{key}`.
- **Drive dead code** (đã dọn ở follow-up cùng ngày — xem mục bổ sung cuối Decision này).
- **Ranh giới / còn lại**: field Severity đã lên create screen (user xác nhận 2026-10-05); `handle_time` để `''` (điền sau từ changelog); backlog của THÁNG QUÁ KHỨ dùng status LIVE nên chỉ gần đúng (không snapshot per-tháng). Jira Cloud identity/status qua `jira_cloud` (#94).

**Bổ sung 2026-10-05 (cùng #104, follow-up):**
- **Severity = ĐÚNG field Jira** (Blocker/Critical/High/Medium/Low), KHÔNG convert 3 mức như #85. `_sev_bucket` chỉ lowercase + khớp 5 mức (lạ/trống → none, không vẽ pie). Twin `_SEV_ORDER/_SEV_PIE/_SEV_LABEL/_sev_bucket` (Python) ↔ `SEV_ORDER/SEV_PIE/SEV_LABEL/SEV_COLOR/sevOf` (JS) — bỏ `_SEV_MAP`. Badge bảng + filter 5 mức; màu inline qua `SEV_COLOR`. SUPERSEDES #85.
- **Cột "Liên kết" = link native Jira**, GỠ HẲN liên kết tay (task_link): `bug_source_jira._related_keys` đọc `parent` + mọi `issuelinks` (vd Relates to Story) → `bug['tasks']`. Xoá `core/task_link.py`, route `/link-task` + `/search-tasks`, widget tick+link bar + checkbox column + 2 popup link. `_bugs_for_task` (chiều ngược, drawer) đọc `bug['tasks']` + canon_key. SUPERSEDES #37/#50/#51/#54(fp cho link).
- **Bảng bug**: BỎ cột "Module" (service/feature đã bỏ); cột "Trạng thái" hiện ĐÚNG status Jira (`status_raw`: Open/TRIAGE/Reopened/In Progress/TESTING/REJECTED/Done) qua `JST` map màu badge, KHÔNG map lifecycle. `bug['status']` (lifecycle) VẪN giữ cho logic tồn đọng/mở (splitGroups/computeBacklog); chỉ phần HIỂN THỊ dùng `statusRaw`. Export Excel bỏ cột Module.
- **Gỡ sạch Drive dead code**: `core/drive_token.py` xoá; `core/bug_log.py` còn MỖI `list_sheet_names`/`read_sheet_rows` (+ primitive xlsx) cho `file_preview`; `bug_log_store` bỏ nhánh Drive (`_count_reopens`/`_seed_current_reopens`/`_missing_id_rows`/Tầng-1 metadata/gate has_drive_token); `auth.py` bỏ `drive_login_url`/`exchange_code_tokens`/`refresh_access_token`/`DRIVE_SCOPE`/`DRIVE_STATE_COOKIE`; `bug_log_source` jira-only (bỏ `extract_file_id`/provider drive). Còn sót dormant: JS popup `#blMissOv` (missing-STT, luôn rỗng — để yên vì chung máy với popup thay đổi); `activeFid`/`SOURCES` trong JS bug-log (luôn ''/[]). `DRIVE_TOKEN_FILE` gỡ khỏi config.

### 108. Trang `/bug-log` chia tab theo SQUAD + Backlog (bỏ lăng kính tháng) *(2026-10-05, code: IIFE BUG LOG trong `app_v2.js` + `core/render/bug_log.py`)*
SUPERSEDES #72/#75 (2 tab tồn đọng/mới theo tháng) cho màn Bug Log — nối tiếp #107 (Analytics đã theo active sprint). User chốt: đang quản lý theo sprint → màn Bug Log cũng bỏ tab tháng, chia **5 tab**: 4 tab squad **CỐ ĐỊNH** `SIT1..SIT4` + 1 tab **Backlog**.
- **Tab squad** = bug `sprintState==='active'` (`isActive`) của đúng squad đó, **MỌI status** (user chốt "tất cả bug trong sprint", KHÔNG lọc Closed/Rejected). `squadOf(b)` = `b.project` nếu ∈ SIT1-4, else `'Khác'`.
- **Tab Backlog** = bug **NGOÀI** active sprint (future + backlog #107) **và CÒN MỞ** (`bugOpen`: bỏ Closed/Rejected — backlog là việc chờ xử lý, không lôi bug cũ đã đóng). Bên trong chia tiếp theo squad bằng **section-header row** (`tr.bl-section`, chèn khi squad đổi so dòng liền trước trong danh sách đầy đủ → đúng cả khi phân trang); `'Khác'` (project lạ) xuống cuối (`squadRank`).
- Sort: tab squad = created mới→cũ; Backlog = theo squadRank rồi created mới→cũ.
- Badge tab + bảng đều áp filter tester/dev/severity (đổi filter gọi `renderTabs()+render()`). Tab nhớ qua `localStorage qa-buglog-tab`. Export Excel theo tab đang xem (`bug-log_<squad|backlog>.xlsx`). Deep-link `?bug=` suy tab chứa bug (active→squad, else backlog) rồi tính trang.
- **Payload**: `render/bug_log.py` thêm `sprintState`/`sprint` vào mỗi bug của `bugLogData` (lấy từ `bug['sprint_state']`/`['sprint']` do `bug_source_jira` gắn — #107).
- **Gỡ**: toàn bộ lăng kính tháng trong IIFE bug-log — `curMonth`/`MONTHS` tab, `splitGroups`/`setGroup`/`tabYm`/`_sheetMY`/`monthScopeBugs`/`monthBugs`/`availMonths`/`FULL_MONTH_YEARS`, element `#blSplitBar`. `activeFid`/`SOURCES`/`MONTHS` còn khai báo nhưng dead (giữ no-op).
**Ranh giới**: bug active-sprint có project NGOÀI SIT1-4 (`'Khác'`) không có tab → không hiện ở màn này (user chốt 4 squad cố định; hiện data chỉ có SIT1-4). Twin Python month-based (`prev_month_backlog`/`splitGroups` cũ) giờ **không còn caller JS** ở màn Bug Log — thành dead giống #107 đã làm với Analytics.

### 88. Sau đồng bộ = 2 popup song song (thay đổi file | dòng thiếu STT) *(2026-08-14)*
Dòng bug **có đủ thông tin nhưng chưa đánh STT** rơi vào `unmapped` (#25/normalize) → không có khoá diff → không vào `bugs`, không vào activity, không vào bất kỳ metric nào. Trước đây chỉ còn lại con số `unmapped` trong log stderr → team không biết mà sửa. Giờ tách **2 popup hiện song song** sau mỗi lần sync:
- **Popup 1** `#blChgOv` — thay đổi file (giữ nguyên hành vi cũ).
- **Popup 2** `#blMissOv` — list dòng thiếu STT: file › sheet › **số dòng Excel** + mô tả + ngày/status/QA/dev, kèm nút "Sao chép danh sách".

Chi tiết:
- `_parse_sheet` gắn `rec['_row']` = **số dòng Excel thật** (`enumerate(rows[2:], start=3)`; `_read_rows` đã pad dòng trống nên chỉ số khớp file). `normalize` **pop `_row` khỏi bug**, chỉ đính vào entry `unmapped` → dict bug lưu cache/diff không đổi hình dạng.
- "Đủ thông tin" (`bug_log_store._missing_id_rows`) = `reason=='no_stt'` **và** có `summary` **và** ≥1 field nghiệp vụ đã điền (`created`/`status_raw`/`qa_pic`/`dev_pic`/`severity`) → loại dòng ghi chú/spill. Dòng **trùng** STT (`dup_stt`) KHÔNG vào popup này (ca khác).
- Lưu **per-file** (`files[fid]['missing']`, cap 60) → `scan()` gom từ MỌI file kể cả file Tầng-1 vừa skip, nên popup luôn nêu đủ hiện trạng chứ không chỉ file vừa đổi.
- **CHỈ sheet tháng HIỆN TẠI** (`_sheet_ym(sheet, created) == now`): tháng cũ đã chốt/gửi report, nhắc lại chỉ làm nhiễu. Lọc lúc **dựng result**, KHÔNG lọc lúc lưu → sang tháng mới mà file bị Tầng-1 skip cũng không đọng lại dòng tháng trước. `_version` bump 4→5 (1 lượt re-parse để seed). `_light()` (property Jira ~32KB) **bỏ** `missing` — dựng lại được từ file.
- Reload chỉ chạy khi **cả hai** popup đã đóng (`popOpen{chg,miss}` + `finishPops`) — đóng popup này không cướp mất popup kia; watermark "đã xem" vẫn ack đúng 1 lần.
- Layout: body`.bl-pair` → 1 lớp nền mờ duy nhất (popup 2 `background:transparent; pointer-events:none`, panel `auto`), 2 panel chia đôi màn hình; <1100px thì xếp trên/dưới.

## Bug Log — metric & tồn đọng

### 49. Analytics bucket theo SHEET tháng (Tn), KHÔNG theo created date
Bucket theo created làm bug tồn copy sang sheet T7 (giữ created T6) bị đếm ở T6 (đếm đôi nếu T6 chưa frozen), và bug created-June reopen trong T7 rơi mất khỏi mọi bảng. Giờ `_month_of(b)` / `monthOf(b)` map **tên sheet** → tháng: `T<m><yyyy>` năm tường minh · `T<m>` bare lấy năm từ created · sheet module → fallback created. Áp cho Valid Bug Rate + bug theo dev/dự án + Reopen. **Tồn đọng giữ created-based** (#75).
⚠ Parity Python ↔ JS.

### 47. Freeze metric Analytics cho tháng đã đóng
Số tháng đã đóng cứ trôi mỗi khi team sửa/copy sheet → lệch số đã gửi CTO. Kho `chart["YYYY-MM"]` trong `.bug_monthly.json` giữ `grand/devs/valid/reopen/bl`. `archive()` (gọi mỗi scan) overwrite tháng hiện tại, bootstrap 1 lần cho tháng quá khứ chưa có, **để yên** tháng quá khứ đã có.
Reopen giữ semantics **RAW** (không dedup) — dedup mẫu số mà không dedup tử số sẽ méo tỷ lệ; freeze chỉ chặn trôi. ⚠ Reopen denom lệch có chủ đích so với chart/valid (dedup).
`CHART_V` phải khớp giữa Python (`_CHART_V`) và JS (`frozenFor`) — lệch là nhánh frozen **inert** (đã từng dính, mọi tháng rơi về LIVE).

### 69. Freeze CHỦ ĐỘNG sau khi report gửi CTO *(hook tự gọi đã gỡ cùng reporter — #100)*
Freeze thụ động (#47) chỉ chốt ở lần scan chót của tháng, không trùng lúc gửi report. `freeze_month(month, live, reopen_map)` ghi cả 3 kho (`months` / `carry` / `chart` + `_frozen`, `frozen_at`) rồi đăng ký `frozen[month]`; `archive()` **bỏ qua mọi tháng có trong `frozen`** (kể cả khi bump `_CHART_V`).
~~Hook trong `monthly_reporter_chat_app.py` sau khi Chat gửi thành công~~ — gỡ ở #100. `freeze_month` giờ KHÔNG còn caller tự động (gọi tay khi cần chốt số); tháng đã có trong `frozen` vẫn được `archive()` để yên như cũ.
**Gỡ freeze**: xoá entry tháng đó trong `frozen` của `.bug_monthly.json` **và** KV/property, hoặc gọi lại `freeze_month` để ghi đè.

### 75. Tồn đọng = SHEET-BASED (đọc thẳng sheet tháng, đếm dòng theo created)
⛔ SUPERSEDED bởi #104 (cut-over Jira: tồn đọng CREATED-BASED) — mục dưới chỉ còn cho ngữ cảnh/nguồn Drive cũ đã gỡ.
SUPERSEDES định nghĩa fingerprint/carry của #33/#36/#46/#62/#68 cho **read-path tồn đọng/mới**.
Bối cảnh: màn Bug và màn Analytics đo 2 định nghĩa khác nhau nên lệch số. User chốt workflow: cuối tháng bê bug chưa xong sang sheet tháng mới, **GIỮ NGUYÊN ngày created** → chính việc bê sang sheet đã là "freeze" tự nhiên, không cần fingerprint/carry.
Định nghĩa thống nhất — trong sheet tháng T, **đếm DÒNG**: `created < tháng-sheet` = **tồn đọng** (status mở = còn treo; Closed/Reject = đã xử lý); `created >= tháng-sheet` = **mới phát sinh** (Closed = đã fix). `total = còn treo + đã xử lý`. KHÔNG dedup (dòng trùng đếm 2 → tín hiệu dọn sheet).
Sửa ở **3 nơi phải parity**: `prev_month_backlog` (Python) ↔ `computeBacklog` (JS, dải chart) ↔ `splitGroups` (JS, tab Bug).
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

### 85. Pie chart Severity ở Analytics
Thang severity trong file bug log gõ LẪN 2 kiểu chữ cho cùng 1 mức → user chốt quy về **3 mức**: `Major = High` · `Normal = Medium` · `Minor = Low` (Blocker/Critical nếu có gom vào Major). Ô trống / giá trị lạ (`Minior` sai chính tả đã map, còn lại) → `none` **KHÔNG vẽ trong pie** nhưng vẫn hiện thành ghi chú "Chưa phân loại: n/N bug" — bỏ hẳn thì mất mẫu số, CTO tưởng tháng chỉ có ngần ấy bug. **Mẫu số % của pie = bug đã phân loại**, không phải tổng bug tháng.
Tập bug = **y hệt biểu đồ cột** (dòng trong sheet tháng T **và** created trong T — #75) → tổng 2 chart luôn khớp. Tính **LIVE mọi tháng** (không đụng freeze #47/#69 — freeze chỉ áp Valid Bug Rate + Reopen).
Pie render **vào trong `#anMetricCharts`** (không tách card riêng) — vốn để lọt vào ảnh PNG/PDF reporter chụp gửi CTO (reporter đã gỡ — #100; `severity_counts()` Python giữ nguyên, hiện không còn caller).
Vẽ bằng **SVG `<path>` arc**, KHÔNG `conic-gradient` — html2canvas (nút xuất ảnh/PDF) không render conic.
⚠ Twin Python↔JS: `_SEV_MAP`/`_SEV_ORDER`/`_SEV_PIE`/`_sev_bucket` (`bug_backlog.py`) ↔ `SEV_MAP`/`SEV_ORDER`/`SEV_PIE`/`sevOf` (`app_v2.js`).
**Bổ sung 2026-08-10 — cột Severity ở bảng `/bug-log`**: thêm cột giữa Ngày và Trạng thái, badge 3 mức cùng bảng màu với pie (đọc chéo 2 màn không lệch). `none` (ô trống / giá trị lạ trong file) hiện `—` mờ, title kèm giá trị thô để biết file gõ gì — KHÔNG ép về Normal. Export Excel thêm cột tương ứng (HEADERS 7 → 8 cột, `none` → ô rỗng). Dropdown **lọc theo severity** (`blSevFilter`) cùng hàng với lọc tester/dev/link — option CỐ ĐỊNH (thang là hằng số, không build từ data), gồm cả "Chưa phân loại". `.bl-table{min-width:1120px}` vì 10 cột làm browser bóp cột "Liên kết Task" xuống ~60px (chữ gãy 3 dòng) — để wrapper `overflow-x:auto` cuộn ngang thay vì bóp. Hằng số `SEV_*` + `sevOf` trong `app_v2.js` đã **hoist ra scope chung** (cạnh `pagerHTML`) vì giờ dùng ở 2 controller (bug-log + analytics) — đừng khai báo lại bản copy trong IIFE.

### 86. Modal "Quản lý link drive" (`/bug-log`) — layout card + link mở thẳng chế độ EDIT
2 màn quản lý nguồn (`/bug-log` và `/test-cases`) trước đó khác hẳn nhau: bug-log là 3 input nằm ngang 1 dòng, test-case là card. Gộp về **layout card của test-case** (`.bl-src-row` từ flex-row → card `surface-low` + border, list `max-height:52vh`, thông số bám theo `.tc-link-item`) nhưng **giữ nguyên phần edit riêng của bug-log**: nhãn + **hậu tố** (`service`, dùng dựng bug id) + link + xoá + "Thêm link". Vẫn 1 nút **"Lưu & đồng bộ"** ở footer (POST full list `/save-bug-log-sources`) chứ KHÔNG per-card như test-case — backend nhận cả list, save từng card cũng phải gom lại.
**Link hiển thị + nút "Mở" = URL Sheets `/edit`**, không phải `drive.google.com/file/d/<id>/view` như trước (`/view` mở viewer chỉ-xem, phải bấm thêm 1 nhịp mới sửa được). `editUrlOf(u, id, name)` chuẩn hoá: link Sheets → ép `/edit` · link Drive / id trần / rỗng → `spreadsheets/d/<id>/edit` khi **tên file không thuộc `_NOT_SHEET`** (`.xls` cũ, pdf, doc…) → phần này vẫn `/view` · link không phải Drive/Sheets → để nguyên, không đoán. Native Sheet lẫn `.xlsx` trên Drive đều mở được bằng URL Sheets `/edit`.
Server không phải đổi: `extract_file_id` bắt `/d/<id>` nên nuốt cả 2 dạng link; store vẫn chỉ lưu **file id** (link chỉ là lớp hiển thị, mỗi lần render dựng lại).

### 45b. Bug Log — filter cho mọi người + Export Excel
Tách `filters_html` (3 dropdown lọc-xem, render cho **tất cả**) khỏi `link_widget` + checkbox column (giữ `editable`-only) → dev cũng lọc được. Dropdown build từ `monthScopeBugs()` (bug của tháng đang xem) chứ không phải mọi tháng.
`core/xlsx_export.py` zero-dep (stdlib `zipfile` + XML `inlineStr`, KHÔNG openpyxl): client build rows từ bảng đang xem, POST `/export-bug-log` → server chốt header + `build_xlsx`. Rows chỉ là chuỗi hiển thị → không chạm Jira/Drive/PAT. Cap 20000 rows, cell ≤32767, lọc ký tự XML không hợp lệ.

### 93. `project_from_filename` giữ nguyên tên dự án nhiều chữ *(2026-09-17)*
Nhãn nguồn `Bug Thu Hộ` / `Bug Chi Hộ` không có mã dạng chữ+số → rơi vào nhánh fallback, mà nhánh đó chỉ lấy **token đầu** → project = `THU` / `CHI`. Sai hiện ở mọi chỗ đọc `bug['project']`: legend chart Analytics ("THU (7)"), pie, dropdown lọc, và bug id trong bảng `/bug-log`.
Fallback giờ **join toàn bộ token** (bỏ token thuần số = năm) → `THU HỘ` / `CHI HỘ`. Nhánh mã chữ+số (`DA5`, `DA6`, `CVPS`…) đi trước nên không đổi; `Bug Retail` → `RETAIL`, `Autodebit` → `AUTODEBIT` giữ nguyên.
**Đánh đổi**: project nằm trong khoá diff `{project}#{service}#{month}#{STT}` **và** fingerprint (#54) → 13 bug của 2 file này đổi khoá ở lần sync FORCE kế tiếp → 1 lượt activity giả "xoá bug + log bug". Không migrate vì không có link task nào của 2 file này (verify data thật) và reopen_map cũng trống. Tầng-1 metadata (#25) sẽ skip file không đổi → phải bấm **"Đồng bộ ngay"** (force) mới re-parse.

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

## Analytics

### 81. Tab "Analytics" (`/analytics`) *(ghi bổ sung 2026-08-10; issue #158)*
Gom metric bug (số lượng theo dev/dự án, Valid & Rejected Bug Rate, Tỷ lệ Reopen, dải tồn đọng) + card placeholder metric Jira (#61). (Coverage automation/test case + `build_analytics_payload` cho API đã gỡ — #97.) Data embed trong `<script id="analyticsData">`, controller tính client-side → đổi tháng/scope không gọi server.
⚠ Nhiều công thức là **twin Python↔JS** (`_reopen_table`↔`renderReopen`, `_valid_counts`↔`renderValid`, `_month_of`↔`monthOf`, `prev_month_backlog`↔`computeBacklog`) (từng phục vụ cả report CTO lẫn UI — reporter gỡ ở #100, twin giữ nguyên vì Analytics/report tay vẫn đọc cùng số).

### 107. Analytics scope theo ACTIVE SPRINT (bỏ lăng kính tháng) *(2026-10-05, code: `bug_source_jira._sprint_state` + `config.SPRINT_FIELD` + IIFE ANALYTICS `app_v2.js`)*
User chốt: đang quản lý theo sprint → toàn trang Analytics tính trên **bug của sprint đang chạy** thay vì theo tháng. Squad lệch nhịp sprint KHÔNG sao vì mỗi issue mang `state` sprint của board nó (xác minh: SIT1 board 237, SIT2 board 236, đều Scrum Sprint 1 active).
- **Field Sprint** = `customfield_10020` (array object, mỗi cái có `state` active/future/closed — Cloud trả object, không phải string cũ). `bug_source_jira._sprint_state(f)` → bug dict thêm `sprint_state ∈ {active, future, backlog}` + `sprint` (tên): có active→active · không active mà có future→future · chỉ còn closed/rỗng→**backlog** (rớt sprint, chờ PO). `_FIELDS` += field; `_flatten_bugs` mang `sprintState`/`sprint` ra JS.
- **SCOPE = bug `sprintState==='active'`**; `scopeBugs()` lọc 1 lần, mọi render dùng chung: 4 KPI (Valid/Reject/Reopen/Open), chart squad/dev, bảng reopen, severity strip, tuổi bug đang mở — tất cả theo active sprint.
- **Section mới "Tình trạng theo Sprint"** (`renderSprint`, `#anSprintBody`): bug đang mở phân 3 tile **Trong sprint (active)** / **Đã xếp kỳ sau (future)** / **Backlog chờ PO (backlog)** + thanh tỷ lệ + danh sách backlog theo squad — đây là danh sách 2 leader review mỗi khi hết sprint.
- **Bỏ selector tháng** (page-head chỉ còn Export PDF) + chip "Sprint đang chạy". `computeValid`/`computeReopen` đổi chữ ký: nhận LIST (SCOPE) thay vì tháng, **bỏ freeze/frozenFor**. Chart bỏ dải tồn đọng T-1 (month-based).
**SUPERSEDES #75 (tồn đọng tháng) + #85-strip cho read-path Analytics; divergence CHỦ Ý với twin Python month-based (#47/#49/#81/#75) — các hàm đó là dead code (#100), KHÔNG còn twin với JS Analytics nữa.** Ranh giới: mất khả năng so tháng-qua-tháng (active = ảnh chụp hiện tại); không suy được "PO đã xem & cố ý để lại", chỉ biết "chưa xếp vào sprint". Dead JS: `monthOf`/`frozenFor`/`fillMonth`/`computeBacklog`/`backlogSegs`/`curSheetOf`/`FULL_MONTH_YEARS` còn trong file nhưng không caller. **BẮT BUỘC quy trình: mọi Bug Testing phải gắn sprint** (2 leader enforce) — field rỗng thì bug rơi vào backlog bucket.

### 106. Redesign toàn trang Analytics — 4 KPI + squad chart + reopen drawer *(2026-10-05, code: `core/render/analytics.py:render_analytics_v2` + IIFE ANALYTICS trong `app_v2.js` + `.an-*`/`.ank-*`/`.anrt-*`/`.andr-*` trong `styles_v2.css`)*
User chốt bố cục mới (mockup Tailwind/dark). Dựng lại theo mockup nhưng **giữ token app** (hợp light+dark, khớp sidebar), **KHÔNG Tailwind/không đổi color scheme**; **mọi công thức + freeze + twin Python↔JS giữ nguyên** — chỉ đổi cách trình bày + thêm tương tác. User chọn 3 hướng: token app · chart gom squad+chồng severity · drawer chỉ field có sẵn.
- **Control chung ở page-head**: 1 `<select id="anMonth">` (tháng, GLOBAL — thay 3 select per-section `anValidMonth`/`anMetricMonth`/`anReopenMonth`) + nút **Export PDF** (`anExport`, trước là `anExportChart` trong card). `renderAll()` = renderKpis+renderAge+renderMetric+renderReopen, chạy lại khi đổi tháng (reset squadFilter='all').
- **4 KPI** (`renderKpis`, card `#anKpi{Valid,Reject,Reopen,Open}`): badge trạng thái theo ngưỡng (Valid ≥90 → "Đạt", Reject <5 → "Tốt", Reopen ≤10/≤25/>25 → Chất lượng cao/Cần theo dõi/Cần cải thiện, Open >0 → "Đang xử lý"). Valid/Reject từ `computeValid(m)`, Reopen từ `computeReopen(m)`, Open từ `computeOpenAge()` (không theo tháng — trạng thái hiện tại).
- **Section Tuổi bug đang mở** (`renderAge`): pill tóm tắt ở header + dải phân bố 5 bucket. (Gộp card open_age #105 vào đây — bỏ `_jira_metrics_placeholder`/`[data-jm]`/empty-state.)
- **Chart "Bug theo Squad & Dev"** (`renderMetric`): nhóm theo **project(=squad)**, mỗi dev 1 cột **chồng theo severity** (SEV_COLOR), có **tab lọc squad** (`#anSquadTabs`, state `squadFilter`), grid y-axis, stat tile (tổng/đã fix), dải tồn đọng (`compBar` giữ nguyên), strip severity gọn ở đáy. SUPERSEDES pie severity #85 (bỏ `pieSVG`/`sevBlockHTML`; `sevCounts`/`SEV_*` twin giữ). mBugs = bug created trong T (khớp #75/#104).
- **Bảng Reopen** (`renderReopen`): cột Developer(avatar+squad) · Reopen/Fix · Tỷ lệ Reopen(mini-bar) · Đánh giá rủi ro(badge: Chuẩn/Tốt/An toàn/Cần chú ý theo ngưỡng 0/≤10/≤20/>20) · nút "Xem bug (n)" mở **drawer**. Tỷ lệ reopen VẪN = `reopenPct(nb, denom)` (twin `_reopen_table` #81, KHÔNG đổi). `computeReopen` tách ra để KPI + bảng + drawer dùng chung; detail kèm key/sev/status.
- **Drawer** (`#anDrawer`, `openDrawer(dev)`): panel phải, list bug reopen của dev — **chỉ field có sẵn** (key→link `window.__jiraBase`/browse, severity, số lần reopen, status hiện tại, summary). Lý do reopen/QA-reporter/thời điểm KHÔNG hiển thị (không có trong `analyticsData`, không fetch thêm — user chốt).
- **Footer** công thức + nhãn engine.
**Ranh giới / dead code**: các id `anValid*`/`anMetric*`/`anReopenMonth`/`anReopenKpi` + hàm `renderValid`/`pieSVG`/`sevBlockHTML` đã gỡ; CSS cũ `.an-valid-*`/`.sev-*`/`.mc-legend`/`.mc-leg`/`.mc-total`/`.mc-stat`/`.oa-kpis`/`.oa-tile`/`.jm-*` còn trong file nhưng **dead** (chưa dọn, low-risk). `.mc-backlog`/`.oa-row`/`.oa-track`/`.oa-fill` vẫn dùng. Export PDF giữ (html2canvas chụp `#anMetricCharts`). Data mỏng (Bug Testing vừa cut-over #104) nên chart/bảng còn thưa.

### 105. Metric Jira "Tuổi bug đang mở" — bật card đầu tiên trong section placeholder *(2026-10-05, code: `core/render/analytics.py:_jira_metrics_placeholder` + `app_v2.js:renderJiraMetrics`)*
REALIZES 1 phần của #61: nguồn bug đã sang Jira (#104) → điền dần section "Metric từ Jira" (trước là 6 card empty "Sắp có"). Option A của user: làm ngay cái **rẻ, data sẵn**, không cần resolutiondate/changelog.
- Giữ DUY NHẤT card `open_age` (**Tuổi bug đang mở**); gỡ 5 card còn lại (`resolution_time`/`by_priority`/`first_response`/`throughput`/`by_component`). Lý do: `by_priority` trùng pie Severity #85; `resolution_time`/`throughput` dính bẫy `resolutiondate` thường null (#4b) → phải suy từ changelog; `by_component` vô nghĩa vì #104 chia theo **squad** không module. Để sau (gói "changelog metrics").
- `renderJiraMetrics()` tính **client-side thuần** từ `BUGS` (created + status lifecycle): bug "đang mở" = `!isClosed && !isReject` (dùng chung helper của Valid Bug Rate). Headline = số bug mở + tuổi trung vị + bug mở lâu nhất; bars phân bố 5 bucket tuổi (≤3/4–7/8–14/15–30/>30 ngày, xanh→đỏ). KHÔNG month-filter (phản ánh trạng thái HIỆN TẠI, mọi tháng). Không có bug mở → empty-state "Không có bug nào đang mở".
- `renderJiraMetrics` gọi SỚM trong IIFE (trước khai báo `isClosed/isReject`) — an toàn vì cả 2 là function declaration (hoisted).
**Ranh giới**: KHÔNG twin Python (tính hoàn toàn ở JS, không freeze/report). `jiraMetrics` trong `analyticsData` vẫn rỗng (hook cũ #61, chưa dùng). Data Bug Testing còn mỏng (vừa cut-over #104) → số nhỏ là bình thường.
**Bổ sung 2026-10-05 — gom inline style các block Analytics còn lại sang CSS + polish**: card open_age bỏ class `jira-soon` (viền nét đứt placeholder) khi có data; bar chart dev/dự án đổi header "Tổng số bug / Bug mới đã fix" thành stat tile (`.mc-total`/`.mc-stat`), legend thành chip (`.mc-legend`/`.mc-leg`), dải tồn đọng thành `.mc-backlog`; khối Severity gom thành `.sev-*` (pie 200→170, rows grid 4 cột zebra). CHỈ đổi markup/CSS — công thức (dedup/freeze/Export PDF html2canvas, twin #49/#85) KHÔNG đụng; màu data-driven (PIE_COLORS/SEV_COLOR) vẫn inline cho html2canvas. Valid Bug Rate (`.an-valid-*`) + Reopen table (`.rk-*`) vốn đã dùng CSS → giữ nguyên.

### 100. Gỡ phần tự GỬI report tháng cho CTO *(2026-10-02, issue #198)*
SUPERSEDES #82. User chốt bỏ việc bắn report tháng tự động; **Analytics giữ nguyên 100%** (trang, chart, twin công thức, freeze data).
- Xoá `core/monthly_reporter_chat_app.py`, `scripts/run_monthly_report.{ps1,sh}`, `docs/report-reopen-bug.md`.
- `requirements.txt` chỉ còn `requests` + `cryptography`: `playwright`/`python-dotenv`/`google-api-python-client`/`google-auth` chỉ reporter dùng (Drive bug log đi bằng `requests`).
- `bug_backlog.freeze_month`/`severity_counts`/`prev_month_backlog` **giữ** (Analytics đã nói để nguyên; hiện không còn caller Python ngoài chính module) — đừng "dọn dead code" mà không hỏi.
- Scheduled Task "QA Monthly Report CTO" không tồn tại trên máy dựng lại (2026-09-14) → không có gì để gỡ. `GOOGLE_CHAT_SPACE_ID` trong `.env` + `gcp-service-account.json` ở root nằm thừa, xoá tay nếu muốn (vẫn gitignore).

## Custom status & misc

### 21. Custom status overlay — nhãn tình trạng thật (local)
Status Jira nghèo, không nói được "Chờ BA confirm" hay "Dev fix bug". Lớp nhãn **phủ local**, KHÔNG đụng status Jira.
Store: `{status:{KEY:{v:[labels],by,at}}, activity:[...]}`. **Mỗi task nhiều nhãn** (`v` là list; string cũ đọc thành list 1 phần tử). 6 nhãn (2026-08-10): Dev fix bug · Chờ BA confirm requirement · Có thay đổi requirement · Chờ data test · Môi trường test chưa sẵn sàng · Chờ deploy lên test.
⚠ Đổi/bỏ nhãn PHẢI giữ **key cũ** ở đâu semantic trùng — `values_of` lọc theo `_VALID`, đổi key = task đang gắn key đó rớt nhãn.
Mỗi lần đổi ghi 1 event vào activity (cap 200, prune 14 ngày) → gộp vào block "Hoạt động".

### 90. Overlay status vừa ghi — dashboard hiện ngay, không chờ Jira/cache bắt kịp *(2026-09-03, code: `core/status_overlay.py`)*
Client đã vá tại chỗ sau transition (#24), nhưng mọi lần render SAU đó đọc lại status từ Jira và dính **2 tầng trễ**: (a) cache SWR `_CACHE_TTL=120s`/stale 900s → chuyển tab là ra status cũ; (b) **search index Jira lag vài giây** → F5 (`force=True`, bỏ qua cache) vẫn có thể trả status cũ. Triệu chứng: status "nhảy về" giá trị trước.
- Store RAM per-process `{key: {status, at}}`. Ghi vào lúc `/do-transition` OK: status lấy **authoritative** bằng `jira_write.get_issue_status` (`GET /issue/{key}` — KHÔNG qua `/search` nên không lag index), fail thì dùng `to` client gửi kèm; response trả `status` để client dùng thay `toName`.
- Áp ở **4 seam đọc**: `fetch_all` · `fetch_all_shared` (kể cả bản RAM cũ khi `'auth'`) · `fetch_activity_feed(with_status=True)` (map status của poll 60s — nếu không vá thì poll dội status cũ về bảng) · `fetch_issue_detail` (drawer).
- **Hết hiệu lực** khi `updated` của issue `+2s >= at` (data đã bao gồm thao tác của mình, hoặc người khác đổi tiếp → tin Jira) hoặc quá `_TTL=900s` (backstop, khớp cửa sổ stale SWR). Feed không fetch `updated` → vòng đời do bucket + TTL quyết định.
- Mutate issue dict **tại chỗ** (object nằm trong cache SWR) → mọi bản copy trong RAM thống nhất.
**Ranh giới có chủ đích**: CHỈ status Jira (nhãn nội bộ đã là store local #21; duedate vẫn chỉ vá client-side). RAM per-process, KHÔNG sync chéo máy — trễ nằm ở cache/index của CHÍNH process đang serve. Chỉ ghi đè **tên** status, không dựng `statusCategory` (không code nào đọc field đó); count-only KPI (`done_total`/`created_week`/`resolved_week`) KHÔNG đổi theo overlay.

### 111. Checklist "Cần soát trước khi chốt sprint" ở Analytics *(2026-10-06, code: `sprintChecklist` trong IIFE ANALYTICS `app_v2.js`)*
Mở rộng section "Tình trạng theo Sprint" (#107): 2 leader duyệt cuối sprint cần thấy bug **đang mở trong active sprint thiếu metadata** — enforce quy tắc "mọi Bug Testing phải gắn sprint + dev + severity".
- **Thuần JS** (`sprintChecklist(openBugs)` append vào `#anSprintBody` sau khối backlog): từ bug đang mở (`isOpenBug`) ∩ active sprint (`inActive`), tách 2 nhóm — **Chưa gán dev** (`!b.dev`) · **Chưa đặt severity** (`sevOf(b)==='none'`). 1 bug có thể ở cả 2 nhóm. Mỗi dòng = key→link Jira + summary + squad.
- Cả 2 rỗng → dòng xanh "Mọi bug trong sprint đã đủ dev + severity". (Bug rớt sprint đã nêu ở khối backlog trên đó, không lặp.)
**Ranh giới**: chỉ bug ĐANG MỞ (Closed/Rejected không cần metadata đầy đủ); 0 call thêm (dùng `BUGS` của `analyticsData`). Không ghi Jira — chỉ liệt kê để leader vào Jira sửa.

### 110. Nút "Copy standup" ở `/today` *(2026-10-06, code: `core/render/today.py` + IIFE cuối `app_v2.js`)*
Sub-lead (role mới) commit 30% 1 squad vẫn phải standup/báo cáo phần việc đó → gõ tay mỗi ngày. Nút sinh text copy-paste từ data đã có (`_my_work_bundle`, **0 call Jira thêm**).
- **Dựng server-side** (`build_standup(tasks, groups, now)` + `format_standup(st, now)`, thuần, test được): 3 nhóm — **Đã xong** (task DONE có `doneAt` trong cửa sổ nhìn lại: Thứ Hai = 3 ngày gộp cuối tuần, else 1) · **Hôm nay** (quá hạn + đến hạn hôm nay + In Progress) · **Blocker** (kẹt ≥ STUCK_DAYS + task mang nhãn nội bộ #21 = lý do đang chờ). Text nhét vào `<pre id="standupText" hidden>`.
- **`doneAt`** thêm vào done task của `build_my_work_payload` (dashboard.py): `resolutiondate` thường null (#4b) → fallback `updated`. Field thừa, `/my-work` JS không vỡ.
- **JS**: IIFE **cuối** `app_v2.js` (top-level, NGOÀI scope `toast` của IIFE chính — `toast` không global, xác minh `typeof toast==='undefined'` ở window) → KHÔNG gọi `toast`, feedback ngay trên nút (`flash` đổi text 1.6s). Copy: `navigator.clipboard.writeText` → fallback `execCommand('copy')` khi reject/absent.
**Ranh giới**: read-only; cửa sổ "đã xong" chỉ 1 ngày (3 ngày Thứ Hai) — không phải toàn bộ done_week. Browser pane Claude chặn clipboard (như Notification #103) → hiện "✗"; browser thật localhost (secure context + user gesture) copy được.

### 109. Strip "Bug tồn đọng" ở `/today` + thêm `updated` vào bug dict *(2026-10-06, code: `core/render/today.py` + `core/bug_source_jira.py`)*
Trang `/today` (#102) chỉ gom task cá nhân; là sub-lead (role mới 2026-10-06, commit 30% 1 squad) cần thấy ngay **bug mở đang rệu rã** để review — không phải mở `/analytics`. Thêm 1 card cross-squad TRÊN lưới task cá nhân.
- **Nguồn**: `load_bug_log()` (cache local `.bug_log.json`, **0 call Jira**) truyền vào `render_today_v2(bug_data=...)`; lỗi cache → bỏ qua, `/today` vẫn render (degrade mềm).
- **Logic thuần** (`build_bug_aging(bugs, now, threshold)` + `_flatten_open_bugs`, test được): bug MỞ (lifecycle ∉ {Closed, Rejected}) mà "chưa đụng" ≥ `_BUG_STALE_DAYS` (= `STUCK_DAYS` = 5, parity với "task kẹt") → gom theo squad (`project`). Tuổi = số ngày từ `updated` (lần đụng gần nhất); **cache cũ thiếu `updated` → fallback `created`**.
- **Thêm field `updated`** vào bug dict (`bug_source_jira._issue_to_bug`) — `_FIELDS` vốn đã fetch `updated` nhưng chưa map. Field thừa, downstream không vỡ; populate đầy đủ sau 1 lần sync bug log.
- **Render**: chip per-squad (count + "cũ nhất Nd") + list ≤8 bug cũ nhất (key→link Jira, summary, badge tuổi đổi màu: ≥14d đỏ · ≥10d cam · còn lại xám) + "+N bug nữa → Bug Log". **Không có bug quá ngưỡng → card ẩn hẳn** (trả `''`).
**Ranh giới**: chỉ hiển thị (read-only), không ghi Jira; cross-squad (không lọc theo squad của user vì không lưu "squad của user"). Tươi khi F5 như KPI `/today` (không nhận patch poll #24).
Mở rộng #24, không thêm endpoint: dùng chính `/activity-feed`. Bật/tắt ở modal Setting (`#setNotifSect`) hoặc palette; quyền do browser giữ theo origin (`localhost` là secure context), cờ bật ở `localStorage qa-desktop-notif`.
- **Leader 1 tab** qua Web Lock `qa-notif-leader` (giữ tới khi tab đóng, tab khác tự lên thay): CHỈ leader được poll khi tab ẩn (#24 vốn bỏ qua tab ẩn — tab ẩn khác vẫn nghỉ) và CHỈ leader bắn → nhiều tab không trùng.
- **Không bắn khi bạn đang nhìn**: cờ chung `qa-focus` (focus → `1`, blur/pagehide → `0`) + `document.hasFocus()`. Noti tới lúc đang focus bị bỏ hẳn (đã có toast + chuông), không dồn lại bắn sau.
- Dedup: `seenIds` (mới giữa 2 poll) + `qa-notif-shown` (id đã bắn, prune 14 ngày / cap 500) → reload không bắn lại. Lúc bật, mọi noti đang có bị đánh dấu đã bắn (không xả cả lô cũ). >3 mục/lần → 1 thông báo gộp `tag:'qa-batch'`.
- Click thông báo → focus cửa sổ + `/dismiss` + mở drawer.
**Giới hạn**: cần ít nhất 1 tab dashboard đang mở (có thể thu nhỏ); browser throttle timer tab ẩn ~1′ nên trễ ≤ ~2′. Browser chặn quyền thì UI chỉ hướng dẫn mở lại (không xin lại được bằng code). Browser pane của Claude desktop luôn `denied` — test bằng mock `Notification`.

### 102. Trang "Hôm nay" (`/today`) = trang chính *(2026-10-02, issue #198, code: `core/render/today.py`)*
Bảng Việc của tôi trả lời "tôi có gì" chứ không trả lời "hôm nay làm gì trước". `/today` gom từ **đúng bundle của `/my-work`** (`_my_work_bundle` — 0 call Jira thêm): KPI + các nhóm **Quá hạn → Đến hạn hôm nay → Được nhắc chưa đọc → Kẹt ≥5 ngày → 7 ngày tới → Đang có ghi chú (#101)**.
- `build_today_groups` thuần (test được): mỗi task active vào **đúng 1 nhóm** theo ưu tiên overdue > today > stuck > upcoming > noted; Done/Cancelled bỏ. Mention = activity chuông `mention && is_unread` (đã lọc noti do chính mình gây ra #34).
- `/` redirect `/today`; sidebar + palette có mục "Hôm nay" đầu tiên. Admin-only (403, không redirect — tránh vòng lặp với `/`).
- Click hàng → **shared drawer** (trang không có `#rows`, #18); hàng mention bấm vào = `/dismiss` + mở drawer. Server-render, KHÔNG nhận patch poll (#24) → tươi khi F5 như KPI.
⚠ `_jira_cls` (Python) twin `jiraCls` (JS) cho màu badge status.

### 101. Ghi chú riêng theo task *(2026-10-02, issue #198, code: `core/task_notes.py`)*
Lớp phủ local kiểu #21 cho thứ status/nhãn không nói được: checklist cá nhân, lý do đang chờ, link Chat. **KHÔNG đẩy Jira**, chỉ chính chủ (`/set-note` + `detail.note` gate `_is_admin`).
- Kho: KV `qa-dashboard-task-notes` local-first (#78) + `.task_notes.json` (gitignore). Shape `{notes:{KEY:{t,at}}}`, cap 5000 ký tự/ghi chú, 2000 task. Text rỗng = xoá. `threading.Lock` quanh read-modify-write vì autosave bắn POST chồng nhau.
- Lưu theo **key thật**, tra theo `canon_key` (#76) → qua kỳ nửa năm vẫn thấy; lưu lại thì entry key kỳ cũ bị thay bằng key mới (1 task = 1 ghi chú).
- UI: mục "Ghi chú riêng" trong **cả 2 drawer** (`noteSectionHtml` shared, render sau "Bug liên quan"), autosave debounce 900ms + lưu ngay khi blur + `fetch keepalive` lúc `pagehide`. Client giữ `NOTE_TXT[key]` → drawer render lại (poll #24, đổi status) KHÔNG mất chữ đang gõ (nhưng vẫn mất focus — như ô comment). Bảng Việc của tôi có icon `note-pencil` cạnh tiêu đề (`hasNote`, vá client qua `__applyNotePatch`).
**Giới hạn**: plain text, không render checklist/markdown. Không có lịch sử sửa (last-write-wins như mọi kho #78).

### 27. Dọn dead code `.last_seen.json` / snapshot-diff NEW badge
Snapshot-diff vẫn chạy mỗi request nhưng **không còn được render** (QA controller không đọc `isNew`). Đã xoá `core/state.py`, `_build_view`, param `new_keys`/`first_run`, `STATE_FILE`.
Cái "New" còn thấy là **nguồn KHÁC, giữ nguyên**: pill New ở `render_admin_v2` = `created == hôm nay` (stateless).

---

## Decision đã chết / bị thay — chỉ giữ để tra số

| # | Nội dung | Trạng thái |
|---|---|---|
| 2 | Bearer PAT auth (Jira DC), cấm Basic | ⛔ SUPERSEDED bởi #94 (Jira Cloud: Basic email+API token) |
| 3 | Auto-refresh 15 phút + activity pending tích luỹ | ❌ chết cùng UI cũ (`app.js` đã xoá). UI v2 chưa từng có auto-reload; notification theo #24 |
| 7 | State file `.last_seen.json` (snapshot + pending) | ❌ gỡ hẳn — xem #27 |
| 8 / 8b / 8c | Tab "Báo cáo tuần" (`/report`) + cây tiến độ theo line | ❌ xoá khỏi dự án 2026-06-08 |
| 10 | Filter theo người (assignee/reporter) client-side + donut filter-aware | ❌ chết cùng UI topnav (cleanup #43) |
| 14 | Sync roadmap/docs qua **Jira user property** làm kho chung | ⛔ SUPERSEDED bởi #78 (Cloudflare KV local-first) |
| 14b | Login + phân quyền qua Cloudflare Access (header-trust) | ⛔ SUPERSEDED bởi #15 (Google OAuth) |
| 16 | Lens cá nhân `render_personal` cho QA non-admin | ⛔ SUPERSEDED bởi #17/#19 (`render_qa_v2` dùng cho cả QA lẫn `/my-work`) |
| 32 | Chatbot AI float (Ollama proxy) | ❌ gỡ hoàn toàn 2026-07-06 |
| 33 / 36 / 46 / 62 / 68 | Tồn đọng T-1 theo snapshot / fingerprint / carry-copy | ⛔ SUPERSEDED bởi #75 (sheet-based) cho read-path. Kho `months`/`carry` vẫn được `archive()` ghi nhưng **dead cho read path** |
| 84 | Snapshot task L2 KV / L3 đĩa + chế độ OFFLINE (`bug_log_offline.py`) để sống khi mất VPN | ⛔ SUPERSEDED bởi #95 (Jira Cloud không cần VPN) — gỡ hẳn |
| 40 | Card insight "Cần chú ý hôm nay" | ❌ gỡ 2026-07-08 (user thấy không thêm giá trị) |
| — | Tính năng PIC (`pic.py`, `/save-pic`) | ❌ bỏ hẳn (cleanup #43) |
| 22 (phần parent) | Sub-task chỉ được tạo dưới Task-PTSP | ⛔ nới thành **bất kỳ task** — xem #57 |
| 5 | Workload threshold ≥15 / 5–14 / ≤4 (strip workload dashboard team) | ❌ gỡ cùng dashboard team — #97 |
| 12 | Tab Roadmap (`/roadmap`, `/public/roadmap`) | ❌ gỡ — #97 (data `.roadmap_config.json` + KV giữ nguyên) |
| 17 | `/my-work` = lens cá nhân **phụ** cho admin | ⛔ thành trang chính duy nhất, `/` redirect về đây — #97 |
| 45 | Role "dev" (`JIRA_DEV_EMAIL`) chỉ my-work + bug-log | ❌ gỡ — #97 |
| 71 | Leader Eval (`/leader-eval`, `/batch-eval`) | ❌ gỡ — #97 |
| 80 / 42 / 44 / 55 / 64 / 91 | Tab Test Case: store/import/sync Drive, mirror sheet, repo panel, độ phủ automation, cột Round | ❌ gỡ — #97 (data `.tc_config.json`/`.testcase_*.json` + KV giữ nguyên) |
| 83 | API JSON `/api/*` cho app Android + App Links + Bearer token | ❌ gỡ cùng app — #97 |
| 60 | Cổng QA gate — chuông "chuyển READY PRODUCTION nhưng CHƯA có sub-task QA" (`fetch_ready_prod_gaps`, `READY_PROD_*`) | ❌ gỡ hẳn 2026-10-02 theo yêu cầu user (noti cũ 86 ngày, không còn giá trị khi dashboard dùng riêng — #97) |
| 89 | Bỏ pill "New" ở dashboard team | ❌ dashboard team đã gỡ — #97 |
| 82 | Report tháng gửi CTO qua Google Chat (`monthly_reporter_chat_app.py` + Scheduled Task) | ❌ gỡ — #100 (Analytics giữ nguyên) |
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
- Server `ThreadingHTTPServer` + Google OAuth login, chỉ phục vụ localhost (LOCAL_ONLY #96), chỉ tracking task của chính chủ (#97)
- Hôm nay (`/today`, `/` redirect về đây — #102), Việc của tôi (`/my-work`), Tài liệu (`/docs`), Bug Log (`/bug-log`), Analytics (`/analytics`), Cài đặt (`/settings`)
- Ghi Jira bằng PAT cá nhân: đổi status, comment (@-mention), đổi due date, tạo sub-task hàng loạt nhiều cha
- Custom status overlay, ghi chú riêng theo task (#101), notification short-poll 60s + thông báo desktop (#103), command palette Ctrl+K
- Auto-login chính chủ khi mở từ localhost (#98), autostart lúc logon (#99)
- Bug Log nguồn **Jira "Bug Testing" (10382)** — trang `/bug-log` chia **5 tab**: 4 squad SIT1-4 (bug active-sprint) + Backlog (ngoài sprint, chia squad bên trong) (#108); reopen từ changelog, export Excel (#104). Drive đã gỡ.
- Viewer tài liệu inline (PDF/ảnh/Office/text/HTML sandbox), folder Quy Trình dạng tab

### Known Limitations
- Pagination cap cứng: active 300 · new24 50 · done 500 · activity feed 120 issue/7 ngày (#38).
- No HTTPS ở tầng app — server bind `127.0.0.1`; mặc định LOCAL_ONLY (#96) chặn mọi request qua tunnel → chỉ dùng được trên máy host.
- Display name mặc định hardcode trong `DEFAULT_DISPLAY_NAMES` (override qua env `JIRA_DISPLAY_NAMES` JSON).
- Data bảng/KPI chỉ tươi khi F5 (trừ status + nhãn nội bộ, xem #24).
- Nhiều công thức là **twin Python↔JS** — sửa 1 bên phải sửa bên kia (danh sách ở #47/#49/#54/#75/#76/#81/#85).
- Fingerprint match theo nội dung → team sửa `summary` lúc copy sheet là đứt (#54).
- File upload không sync chéo máy (chỉ ở host, `uploads/` gitignore).

## Things NOT to Do

- KHÔNG đổi `STUCK_DAYS` tự ý
- KHÔNG đổi color scheme (Atlassian-blue intentional)
- KHÔNG đề xuất rewrite sang React/Vue/Svelte — user explicit chọn server-side render
- KHÔNG thêm dep (Flask/openpyxl/PyJWT/framework) — minimal-deps là quyết định
- KHÔNG thêm tracking/analytics
- KHÔNG hardcode API token, dù để test
- KHÔNG gọi `/rest/api/2/search` (Cloud đã gỡ) hay JQL/payload bằng username trần — đi qua `jira_cloud` (#94)
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
├── start.bat / start.command
├── CLAUDE.md / README.md / requirements.txt / .env.example
│
├── core/
│   ├── config.py            ← env, paths, USERS(=SELF_USER)/PORT/role, LOCAL_ONLY, field ids, canon_key, atomic_write
│   ├── issues.py            ← accessor i_* + helper (parse_date, is_stuck, esc, status_class, issue_link)
│   ├── jira_cloud.py        ← lớp biên Jira Cloud: Basic auth, map username↔accountId, normalize response, canon status, mention (#94)
│   ├── jira_api.py          ← Jira REST bằng token chung: search/count, fetch_all(+shared snapshot), activity feed, SWR cache, run_parallel, ready-prod gaps. PAT redact ở đây.
│   ├── auth.py              ← Google OAuth + session cookie HMAC (#15)
│   ├── crypto_util.py       ← Fernet at-rest (#20)
│   ├── pat_store.py         ← API token cá nhân {email: enc('email:token')} (#20, #94)
│   ├── jira_write.py        ← ghi Jira bằng API token cá nhân: transition/comment/duedate/sub-task (#20,#57,#77)
│   ├── custom_status.py     ← nhãn overlay + activity (#21)
│   ├── task_notes.py        ← ghi chú riêng theo task (#101)
│   ├── remote_store.py      ← kho sync chéo máy Cloudflare KV, local-first (#78)
│   ├── docs.py              ← cây tài liệu (#11,#66)
│   ├── file_preview.py      ← dựng HTML preview docx/xlsx/pptx/text (#63)
│   ├── bug_log.py           ← CHỈ còn primitive đọc xlsx thô cho file_preview (#63, #104)
│   ├── bug_log_source.py    ← danh sách nguồn Jira "Bug Testing" (#104)
│   ├── bug_log_store.py     ← scan Jira + reopen từ changelog + persist `.bug_log.json` (#104)
│   ├── bug_source_jira.py   ← provider Jira "Bug Testing": fetch + map bug dict (#104)
│   ├── bug_backlog.py       ← tồn đọng created-based, severity, freeze tháng (#104,#69)
│   ├── xlsx_export.py       ← build .xlsx zero-dep (#45b)
│   ├── render/              ← package: base · shell · misc · today (= Hôm nay #102) · dashboard (= Việc của tôi) · docs · bug_log · analytics (`__init__.py` re-export cho caller cũ)
│   └── routes/              ← oauth · uploads · write (mixin cho handler)
│
├── assets/  app_v2.js · styles_v2.css (UI v2) · styles.css (chỉ error page)
├── scripts/ install_autostart.ps1 (autostart lúc logon — #99) · jira_cloud_probe.py (dò config Jira Cloud vs config.py — #94)
├── docs/    ghi chú kỹ thuật rời
│
│   ── gitignore (sinh lúc chạy) ──
├── .env · .crypto_key · .drive_token.json · .pat_store.json · .jira_accounts.json · .sync_meta.json
├── .docs_config.json · .custom_status.json · .task_notes.json · (.roadmap_config.json · .tc_config.json — data cũ, không còn code đọc, #97)
├── .bug_log*.json · .bug_monthly.json · .bug_task_link.json · .testcase_*.json
├── uploads/ · reports/ · gcp-service-account.json
```

## Coding Conventions

- **Layer, KHÔNG vòng lặp import**: `config` → `issues` → `{crypto_util, remote_store, jira_cloud}` → `jira_api` → `{pat_store, drive_token, jira_write, custom_status, docs, bug_log*, task_link}` → `render` → `qa_dashboard`. Import lazy (trong hàm) khi buộc phải đi ngược.
- `from X import (tên cụ thể)`, không `import *`.
- Section comment: `# ===== SECTION NAME =====`
- Accessor issue field dùng prefix `i_`.
- Render = f-string inline trong `render_*`; CSS ở `styles_v2.css`, KHÔNG inline style trừ trường hợp đặc biệt.
- Vietnamese trong UI string + comment giải thích "vì sao"; English trong tên hàm/biến.
- Khi thêm/đổi cấu trúc: **tự ghi Decision mới** vào file này (số kế tiếp), không đợi user nhắc.

## Last Updated

2026-10-06 — Role user đổi Acting QA Manager → **QA sub-lead** (30% effort 1 squad); cập nhật Project Purpose + bảng QA team.

2026-10-06 (#111) — Checklist "Cần soát trước khi chốt sprint" ở Analytics: bug active-sprint đang mở thiếu dev / severity, cho 2 leader duyệt. Thuần JS trong section Sprint (#107).

2026-10-06 (#110) — Nút "Copy standup" ở `/today`: sinh text 3 nhóm (Đã xong / Hôm nay / Blocker) từ data my-work (0 call Jira), copy-paste vào standup. Thêm `doneAt` vào done task.

2026-10-06 (#109) — Strip "Bug tồn đọng" ở `/today`: bug mở chưa đụng ≥5 ngày gom theo squad (cross-squad, read-only, nguồn cache local 0 call Jira). Thêm field `updated` vào bug dict (`bug_source_jira`).

2026-10-05 (#108) — Trang `/bug-log` chia 5 tab theo squad + backlog thay lăng kính tháng (nối tiếp #107): 4 tab SIT1-4 (bug active-sprint, mọi status) + tab Backlog (bug ngoài sprint còn mở, chia squad bằng section-header). Payload thêm `sprintState`/`sprint`. Gỡ toàn bộ month-tab/`splitGroups` trong IIFE bug-log. SUPERSEDES #72/#75 cho màn Bug Log.

2026-10-05 (#107) — Analytics scope theo ACTIVE SPRINT: thêm `sprint_state` (field customfield_10020) vào bug dict, toàn trang tính trên bug sprint đang chạy, section "Tình trạng theo Sprint" (active/future/backlog chờ PO), bỏ selector tháng + freeze. Squad lệch nhịp vẫn đúng (state per board). Divergence chủ ý với twin Python month-based (dead code #100). Bắt buộc Bug Testing gắn sprint.

2026-10-05 (#106) — Redesign toàn trang Analytics theo mockup: hàng 4 KPI (Valid/Reject/Reopen/Open) có badge ngưỡng · section Tuổi bug đang mở (pill + dải) · chart gom theo Squad, cột dev chồng Severity + tab lọc squad · bảng Reopen có đánh giá rủi ro + drawer chi tiết bug reopen · control tháng global + Export PDF ở page-head · footer công thức. Giữ token app (light+dark, không Tailwind), giữ nguyên mọi công thức/freeze/twin. Pie severity #85 bỏ (thay bằng cột chồng + strip).

2026-10-05 (#105 polish) — Bỏ note "Google Sheet" dưới "Metric từ Jira"; thiết kế lại card open_age (stat tile + bar + %) và gom inline style các block Analytics còn lại (bar chart dev/dự án, Severity) sang CSS (`.mc-*`/`.sev-*`), chỉ đổi markup không đụng công thức.

2026-10-05 (#105) — Bật card "Tuổi bug đang mở" trong section "Metric từ Jira" (realize 1 phần #61); gỡ 5 card placeholder còn lại. Tính client-side thuần từ created+status, 5 bucket tuổi, không month-filter.

2026-10-05 (follow-up #104) — Severity hiện ĐÚNG 5 mức field Jira (bỏ convert 3 mức #85); cột "Liên kết" = link native Jira (parent + Relates), GỠ HẲN task_link thủ công (xoá `task_link.py`, route `/link-task` + `/search-tasks`); dọn sạch Drive dead code (xoá `drive_token.py`, gut `bug_log.py` còn primitive xlsx, bỏ nhánh Drive trong `bug_log_store`, bỏ drive helpers trong `auth.py`, `bug_log_source` jira-only). #85/#79/#37/#50/#51 superseded.

2026-10-05 — Thêm Decision #104 (cut-over Bug Log Google Drive → Jira "Bug Testing" 10382: nguồn JQL issuetype=10382, chia theo squad=project, bỏ service/feature, severity từ customfield_10404, reopen từ changelog, backlog created-based, dedup theo key, gỡ Drive OAuth/UI/route). #61 realized, #75 superseded (read-path). `scripts/reset_bug_log.py` chạy 1 lần xoá data Drive cũ.

2026-10-02 — Issue #198 (productivity dashboard dùng riêng): #98 auto-login + chặn CSRF POST · #99 autostart lúc logon · #100 gỡ phần tự gửi report tháng (Analytics giữ nguyên; #82 → bảng chết) · #101 ghi chú riêng theo task · #102 trang Hôm nay làm trang chính · #103 thông báo desktop.

2026-10-02 — Gỡ cổng QA gate (#60 → bảng decision chết): chuông không còn noti READY PRODUCTION thiếu sub-task QA.

2026-10-02 — Thêm Decision #97 (dashboard dùng riêng 1 người: roster = SELF_USER, gỡ dashboard team / roadmap / test case / leader eval / API mobile / role dev). #5/#12/#17/#45/#71/#80/#42/#44/#55/#64/#91/#83/#89 chuyển vào bảng decision chết.

2026-10-02 — Thêm Decision #96 (LOCAL_ONLY: dashboard chỉ phục vụ chính máy host, chặn request qua tunnel cloudflared).

2026-10-02 — Thêm Decision #95 (gỡ snapshot L2/L3 + chế độ OFFLINE/`bug_log_offline.py` vì Jira Cloud không cần VPN). #84 chuyển vào bảng decision chết.

2026-09-25 — Thêm Decision #94 (chuyển Jira DC → Jira Cloud: Basic auth API token, dịch accountId ở biên, search/jql, field id mới). #2 chuyển vào bảng decision chết.

2026-09-17 — Thêm Decision #93 (project_from_filename giữ tên dự án nhiều chữ: THU HỘ / CHI HỘ thay vì THU / CHI).

2026-09-17 — Nút “Mở tab mới” trong viewer tài liệu mở trang `/file-view` toàn màn hình thay vì tải file về (ghi vào Decision #63).

2026-09-14 — Thêm Decision #92 (gỡ tin header Cf-Access-Authenticated-User-Email: auth bypass, phần còn sót của issue #44).

2026-09-14 — Thêm Decision #91 (sync test case đọc cột Round 1/2/3, lấy kết quả round mới nhất có dữ liệu).

2026-09-03 — Thêm Decision #90 (overlay status vừa ghi: dashboard/poll/drawer hiện ngay status mới, không chờ cache SWR + index Jira).

2026-09-03 — Nới `MAX_FOLDERS` test case 100→1000 + báo lỗi cap tường minh (ghi vào Decision #80).

2026-09-03 — Bổ sung lọc Assignee client-side ở `/leader-eval` (ghi vào Decision #71).

2026-09-03 — Thêm Decision #89 (bỏ pill "New" ở dashboard, task mới nằm trong To Do).

2026-08-14 — Thêm Decision #88 (sau đồng bộ bug log = 2 popup song song: thay đổi file | dòng thiếu STT).

2026-08-11 — Thêm Decision #87 (custom select `xsel` thay popup `<select>` native toàn app).

2026-08-10 — Dọn lại toàn bộ Decision: bỏ log verify/smoke, gộp #12 trùng, đưa #77 về đúng thứ tự, gom 13 decision chết/superseded vào bảng cuối, bổ sung 7 decision cho phần code chưa có tài liệu (KV store #78, Drive token #79, Test Case #80, Analytics #81, report Chat #82, API mobile #83, offline/snapshot #84), cập nhật File Map (package `core/render`, `core/routes`, module mới) + Current State + Known Limitations theo code thật.
