# QA Workspace

Workspace nội bộ cho team QA Bảo Kim — pull data **live** từ Jira (Data Center 10.7.3) qua REST API, render HTML server-side bằng Python thuần. Thay cho Jira native dashboard.

Stack: Python 3.8+ · server `http.server` stdlib · **không web-framework** · UI vanilla JS + CSS (sidebar Material 3 "Stitch", `app_v2.js`/`styles_v2.css`).

Dependencies (xem `requirements.txt`):

| Dep | Dùng cho |
|---|---|
| `requests` | gọi Jira REST + Google OAuth/userinfo |
| `cryptography` | mã hoá at-rest PAT cá nhân + token Drive (Fernet) |
| `python-dotenv` | đọc `.env` |
| `google-api-python-client` · `google-auth` | đọc file bug-log `.xlsx` trên Google Drive (tab Bugs) |
| `playwright` | tooling phụ (`monthly_reporter_chat_app.py`), KHÔNG cần cho dashboard chính |

---

## Data Flow (Luồng Dữ Liệu)

Dự án hoạt động theo mô hình Server-Side Rendering (SSR) thuần, kết hợp với client-side polling để cập nhật trạng thái real-time mà không cần tải lại trang.

1. **Jira API là Source of Truth**: Dữ liệu chính (Task, Status, Assignee, Changelog) được pull trực tiếp từ Jira thông qua REST API sử dụng PAT chung (chỉ có quyền đọc).
2. **Local Cache & Cloudflare KV Sync**: 
   - Một số dữ liệu phụ trợ không nằm trong trường chuẩn của Jira (Roadmap, Docs, Custom Status, Test Case link, Bug log link) được lưu vào *Cloudflare KV* để đồng bộ chéo máy giữa các thành viên.
   - Khi render trang, server fetch Jira API + đọc Local Cache (thường lưu dưới dạng các file `.json` ẩn như `.roadmap_config.json`, `.bug_log.json`).
   - Nếu Jira bị lỗi hoặc không có mạng, các tính năng không phụ thuộc trực tiếp vào trạng thái Jira Task (như xem list Tài liệu, Roadmap) vẫn render được nhờ Local Cache (Offline fallback).
3. **Data Snapshot (Cross-machine Sync)**: Để giảm tải cho Jira và hỗ trợ thành viên quên bật VPN, hệ thống áp dụng cơ chế "Data Snapshot". Ai có VPN và vào trang sẽ tự động pull full data và ghi đè vào cache chung trên đĩa. Những người sau (kể cả không có VPN) sẽ đọc bản snapshot mới nhất này để xem thông tin team.
4. **Real-time Notifications**: Giao diện không dùng Websocket mà sử dụng kỹ thuật *Short-Polling*. Mỗi 60 giây client sẽ gọi background API `/activity-feed`, pull changelog mới nhất và dùng DOM manipulation để hiển thị badge/toast/status mới trực tiếp trên UI.

---

## Cơ Chế Đăng Nhập (Login & Auth)

Hệ thống hỗ trợ 2 mode hoạt động:

1. **Local Dev (`AUTH_ENABLED = False`)**: 
   - Dùng khi phát triển, bỏ trống biến `GOOGLE_CLIENT_ID` và `GOOGLE_CLIENT_SECRET` trong `.env`.
   - Không bắt buộc login. Mọi request mặc định được gán quyền Admin.
2. **Golive / Production (`AUTH_ENABLED = True`)**:
   - Sử dụng **Google OAuth 2.0**. Chỉ cho phép email thuộc domain nội bộ đã khai báo (VD: `@baokim.vn`).
   - **Luồng thực hiện**: 
     1. User vào web -> Check Session Cookie -> Nếu không có -> Redirect sang route `/login`.
     2. Mở cổng Google OAuth, user chọn email công ty để đăng nhập. Google trả về Auth Code.
     3. Server đổi Code lấy Access Token, xác nhận Email thuộc `JIRA_ALLOWED_DOMAIN`.
     4. Server tạo **Session Cookie ký HMAC** (chống giả mạo, dùng khoá `SESSION_SECRET`) với thời hạn nhất định (TTL) và gắn vào browser, redirect về `/`.
   - **Sliding Session**: Khi cookie hết nửa thời gian sống, server cấp mới lại (gia hạn) để user không bị gián đoạn (kick out) giữa chừng khi đang làm việc.
   - **Phân quyền Admin**: Role Admin được xác định qua email khai báo tại biến môi trường `JIRA_ADMIN_EMAIL`. Admin có thêm các quyền: Edit Roadmap, thêm Docs, quản lý Drive Token, và xem tab "Việc của tôi" (My Work) ở level đánh giá team.

---

## Kiến Trúc & Chi Tiết Các Module Lõi

Kiến trúc chia module theo layer rõ ràng, không vòng lặp import (circular import): `config` → `issues` → `{Các module state/api}` → `render` → `qa_dashboard`. Toàn bộ xử lý nằm trong thư mục `core/`. File gốc `qa_dashboard.py` (Entry Point) cấu hình route và khởi chạy server.

| Module trong `core/` | Mô tả chi tiết |
|---|---|
| **`auth.py`** | Xử lý Google OAuth, mã hóa và verify cookie dựa vào HMAC signature (Sliding session & verification). |
| **`config.py`** | Khởi tạo cấu hình biến môi trường (`.env`), setup domain, auth_enabled, URL Jira, ID custom fields, và timeout/stuck days. |
| **`issues.py`** | Phân tích JSON Issue từ Jira. Chứa các hàm tiện lợi parse `i_assignee`, `i_status`, và tính KPI (days overdue, stuck_days). |
| **`jira_api.py`** | Tương tác REST API chính với Jira qua PAT chung. Gồm fetch toàn bộ task, lấy feed hoạt động (changelog), và load/save data vào Cloudflare KV. |
| **`jira_write.py`** | Module write xuống Jira (đổi status, gửi comment, tạo sub-task QA) **bằng PAT cá nhân** của từng tester, đảm bảo đúng định danh. |
| **`pat_store.py`** | Quản lý việc lưu, xác thực, lấy ra và xoá PAT cá nhân. |
| **`crypto_util.py`** | Hàm mã hóa đối xứng (dùng thư viện `cryptography` / Fernet) để mã hóa PAT và Google Drive Token trên disk. Không lưu lộ token. |
| **`drive_token.py`** | Xử lý Auth và lưu/đọc Refresh Token của hệ thống Google Drive. |
| **`bug_log_store.py`** / **`bug_log.py`** | Background thread (10 phút/lần) kéo file XLSX từ Drive về. Module này parse dữ liệu bugs từ các sheet, diff sự thay đổi để tạo notif và cache file local. |
| **`bug_log_source.py`** | Quản lý danh sách các file/URL Google Sheets đang được link vào Dashboard làm nguồn bug log. |
| **`roadmap.py`** / **`docs.py`** | Module quản lý tài liệu nội bộ và Roadmap QA. Sync dữ liệu 2 chiều giữa JSON local cache và Cloudflare KV. |
| **`testcase_store.py`** | Kho lưu trữ Test Case tập trung. Xử lý tạo, xoá, đổi tên cấu trúc thư mục Test Case, import dữ liệu bulk từ Google Sheets. Cache tại local và Cloudflare KV. |
| **`task_link.py`** / **`testcase_link.py`** | Quản lý mapping Link giữa (Bug log) ↔ (Jira Task) và (Testcase Folder) ↔ (Jira Task). Để khi mở task trên Jira/Dashboard có thể thấy thông tin bug/testcase tương ứng ngay trong Drawer. |
| **`custom_status.py`** | Xử lý "Nhãn Nội Bộ" (Overlay Status) để gán cho task Jira (VD: *Chờ QA*, *Đã Test*). Dữ liệu này không ghi thật vào Status của Jira mà lưu qua Cloudflare KV. |
| **`monthly_reporter_chat_app.py`** | Một script tool đứng riêng để tự sinh và báo cáo SLA tháng lên Google Chat thông qua Playwright headless. |
| **`render.py`** | Module phụ trách toàn bộ Logic Server-Side Rendering (SSR). Map các components lại với nhau và trả ra HTML hoàn chỉnh có gắn string templates. |
| **`routes/`** | Chứa `oauth.py`, `write.py`, `uploads.py` là các Mixins Class để tách nhỏ logic xử lý HTTP route khỏi file `qa_dashboard.py` khổng lồ. |

Tái cấu trúc folder (issue #85): code lõi trong `core/`, asset tĩnh trong `assets/`, script tiện ích trong `scripts/`. Entry `qa_dashboard.py` giữ ở root, tự thêm `core/` vào `sys.path`.

---

## Các trang (tab)

Điều hướng qua **sidebar** bên trái (UI v2). Profile chip dưới sidebar có menu **Cài đặt PAT** + **Đăng xuất**.

| Route | Tab | Mô tả | Ai xem được |
|---|---|---|---|
| `/` | **Dashboard** | Vận hành live. Admin thấy lens quản lý toàn team (workload matrix, donut, KPI Vào/Ra, activity feed). QA thường thấy **lens cá nhân** tự scope về mình. | Mọi người |
| `/my-work` | **Việc của tôi** | Lens cá nhân của admin (task của chính mình), UI hệt QA member. | Chỉ admin (QA → đá về `/`) |
| `/leader-eval` | **Đánh giá** | Đánh giá task QA theo tháng (lọc category/leader/assignee). | Chỉ admin |
| `/roadmap` | **Roadmap** | Giai đoạn › mục › sub-task, status/%/hạn; cảnh báo hạn ≤2 tuần đẩy lên dashboard. | Mọi người xem; chỉ admin sửa |
| `/bug-log` | **Bugs** | Bug log đồng bộ từ file `.xlsx` trên Google Drive + tự liên kết bug ↔ Jira task. | Mọi người (đã đăng nhập) |
| `/test-cases` | **Test Cases**| Kho lưu trữ Test Case tập trung. Cấu trúc cây thư mục. Chức năng import từ Google Sheet. Tự liên kết Test Case Folder ↔ Jira task. | Mọi người |
| `/docs` | **Tài liệu** | Cây thư mục + link Google Drive + **upload file thật** cho tài liệu training. | Mọi người xem; chỉ admin sửa |
| `/analytics` | **Thống Kê**| Thống kê metric dự án (Valid Bug Rate, Tỉ lệ Reopen, Lỗi theo tính năng).| Mọi người |
| `/settings` | **Cài đặt** | Đặt PAT cá nhân (mã hoá khi lưu) để thao tác ghi Jira đúng tên người. Admin có thêm nút kết nối Google Drive API. | Mọi người |

## Features chính

- **KPI cards** + **Workload matrix** Assignee × Status, badge QUÁ TẢI/OK/NHẸ (ngưỡng ≥15 / 5–14 / ≤4)
- **Overdue tính theo ngày làm việc** (T2–T6, bỏ T7/CN); metric "kẹt ≥5 ngày" + "Vào/Ra tuần"
- **Activity feed** dựng từ Jira changelog (status/assignee/duedate/priority/comment/tạo mới); tên người hiển thị đúng (QA = tên ngắn, người ngoài = display name); dismiss đồng bộ chéo máy qua Cloudflare KV.
- **Notification real-time** — short-poll `/activity-feed` mỗi 60s (tự dừng khi tab ẩn), cập nhật chuông + toast + status/nhãn nội bộ của task **mà KHÔNG reload trang**. (Thay cho cơ chế auto-refresh 15 phút của UI cũ.) Data bảng/KPI/donut vẫn chỉ tươi khi **F5 thủ công**.
- **Highlight task mới** phát sinh giữa 2 lần refresh (badge NEW cam)
- **Filter theo người** (assignee/reporter) — client-side, nhớ qua localStorage
- **Đổi status + gán nhãn nội bộ** (8 nhãn: Dev fix bug, Chờ BA confirm, …) ngay trên dashboard, ghi Jira **bằng PAT cá nhân** → đúng tên người
- **Tạo QA sub-task** dưới Task-PTSP từ modal (auto-fill `[QA]` + Leader Hiền)
- **Bug log từ Drive**: background thread poll file `.xlsx` mỗi 10 phút, normalize + diff, link bug ↔ Jira task
- Mọi key Jira là hyperlink → mở thẳng task / drawer chi tiết. UTF-8 tiếng Việt.

---

## Setup (lần đầu)

### 1. Cài dependencies

```bash
pip install -r requirements.txt
```

### 2. Tạo Jira Personal Access Token

Login Jira Bảo Kim → avatar góc phải → **Profile** → **Personal Access Tokens** → **Create token**:
- Name: `qa-workspace` · Expiry: theo policy
- Quyền cần: **Browse Projects** (thêm quyền transition nếu muốn đổi status từ dashboard)
- Copy token (chỉ hiện 1 lần)

> PAT này (trong `.env`) là **PAT chung** dùng để đọc. Mỗi QA còn có thể dán **PAT cá nhân** ở `/settings` để thao tác *ghi* (đổi status, comment, tạo sub-task) ghi đúng tên mình.

### 3. Tạo file `.env`

```bash
cp .env.example .env
# Mở .env, điền JIRA_PAT (và phần OAuth nếu golive)
```

Các biến chính (xem `.env.example` để đầy đủ + chú thích):

| Biến | Ý nghĩa |
|---|---|
| `JIRA_URL` | `https://jira.baokim.vn:8443` (không có `/` cuối) |
| `JIRA_PAT` | Personal Access Token (PAT chung, read-only) |
| `JIRA_USERS` | username QA team, phân tách dấu phẩy |
| `JIRA_PORT` | cổng local (mặc định 8080) |
| `JIRA_ADMIN_EMAIL` | email role admin (sửa roadmap/docs, thấy tab admin) |
| `JIRA_SELF_USER` | username admin cho `/my-work` (mặc định `thanhht1`) |
| `JIRA_ALLOWED_DOMAIN` | domain được phép login (vd `baokim.vn`) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | bật khi golive → bắt đăng nhập Google |
| `SESSION_SECRET` | khoá ký session cookie (bắt buộc khi bật OAuth): `python -c "import secrets;print(secrets.token_urlsafe(48))"` |

> **OPSEC:** `.env` và mọi file state KHÔNG commit lên git (đã có trong `.gitignore`). Không bao giờ log/in PAT ra console.

### 4. Chạy

```bash
python qa_dashboard.py
```

Hoặc double-click launcher: `start.bat` (Windows) · `start.command` (macOS). Launcher tự đóng server cũ trên port, mở browser.

Mở browser: `http://localhost:8080/`

---

## Sử dụng hằng ngày

- **F5**: pull data tươi từ Jira (bảng/KPI/donut/workload). Notification thì tự cập nhật mỗi 60s không cần F5.
- Lần refresh đầu: ghi snapshot baseline, chưa highlight. Lần sau: task mới → badge **NEW** cam.
- Click key (vd `DA51H26-2843`) → mở **drawer chi tiết** (mô tả + comment + gửi comment). Mọi tab v2 đều mở được drawer.
- Filter dropdown: xem nhanh việc của 1 QA.
- Bấm chuông 🔔 → danh sách hoạt động; ✓ đánh dấu đã đọc (đồng bộ chéo máy).

## Customize

| Muốn đổi | Cách |
|---|---|
| Danh sách user track | Sửa `JIRA_USERS` trong `.env`, restart |
| Display name | `config.py` → `DEFAULT_DISPLAY_NAMES` (hoặc env `JIRA_DISPLAY_NAMES` JSON) |
| Ngưỡng QUÁ TẢI (15/5/4) | `render.py` → workload render |
| Ngưỡng "kẹt" (5 ngày) | `config.py` → `STUCK_DAYS` |
| Nhãn nội bộ (custom status) | `custom_status.py` → `CUSTOM_STATUSES` |
| Field id tạo sub-task | `config.py` → `SUBTASK_TYPE_ID` / `TASK_PTSP_TYPE_ID` / `START_DATE_FIELD` / `LEADER_FIELD` |
| Port | `JIRA_PORT` trong `.env` |

## Reset state

Roadmap/docs/dismiss/PAT/nhãn nội bộ sync qua Cloudflare KV nên xoá file cache local không mất data (Cloudflare KV là source of truth cho metadata phụ trợ, file local chỉ là cache fallback).

## Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `401 PAT sai hoặc hết hạn` | Token sai/expired | Tạo PAT mới, update `.env` |
| `403 PAT không đủ quyền` | Thiếu Browse Projects | PAT mới đủ scope |
| `Port đang bị chiếm` | Process khác dùng 8080 | Đổi `JIRA_PORT` |
| `Network error` | Không vào được Jira | Check VPN/Tailscale/kết nối nội bộ |
| Trống không có task | JQL ra 0 issue | Check `JIRA_USERS` đúng username |
| Bị đá về `/login` liên tục | OAuth chưa cấu hình đúng | Check `GOOGLE_*` + redirect URI khớp |
| Đổi status báo "chưa cấu hình PAT" | Chưa dán PAT cá nhân | Vào `/settings` dán PAT cá nhân |
| Bugs trống / không sync | Chưa kết nối Drive / chưa khai báo file nguồn | `/bug-log` → kết nối Drive + thêm file nguồn |

---

### ⚠ Đường dẫn ổn định cho cron / launchd / alias

Khi setup cron, launchd plist, alias hay shortcut, **đừng trỏ thẳng vào module con** (chúng có thể bị move khi tái cấu trúc folder — như issue #85 đã move mọi thứ vào `core/`/`scripts/`). Quy ước:

- **Chạy dashboard** → luôn gọi entry ở root: `python3 /Users/thanhht/qa-dashboard/qa_dashboard.py` (hoặc `start.command`/`start.bat`). Đây là API ổn định, không bao giờ move.
- **Script tiện ích** → nằm trong `scripts/` (vd `run_monthly_report.sh`). Job phải `cd <root>` rồi gọi `scripts/<tên>`.
- **Tool định kỳ** (`monthly_reporter_chat_app.py`) → nằm trong `core/`. Job phải `cd <root>` rồi gọi `core/<tên>.py` (cwd phải là root để đọc đúng `.env` + `gcp-service-account.json`).

Daemon hiện có trên host Mac (audit issue #88): `com.qa.dashboard` (→ `qa_dashboard.py` root, OK), `com.qa.cloudflared`, `com.qa.socks` (không trỏ module Python), và 1 crontab chạy `core/monthly_reporter_chat_app.py --cron` cuối tháng.
