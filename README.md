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
   - Một số dữ liệu phụ trợ không nằm trong trường chuẩn của Jira (Docs, Custom Status, Bug log link) được lưu vào *Cloudflare KV* để đồng bộ chéo máy giữa các thành viên.
   - Khi render trang, server fetch Jira API + đọc Local Cache (thường lưu dưới dạng các file `.json` ẩn như `.docs_config.json`, `.bug_log.json`).
   - Nếu Jira bị lỗi hoặc không có mạng, các tính năng không phụ thuộc trực tiếp vào trạng thái Jira Task (như xem list Tài liệu, Bug Log) vẫn render được nhờ Local Cache (Offline fallback).
3. **Real-time Notifications**: Giao diện không dùng Websocket mà sử dụng kỹ thuật *Short-Polling*. Mỗi 60 giây client sẽ gọi background API `/activity-feed`, pull changelog mới nhất và dùng DOM manipulation để hiển thị badge/toast/status mới trực tiếp trên UI.

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
   - **Phân quyền Admin**: Role Admin được xác định qua email khai báo tại biến môi trường `JIRA_ADMIN_EMAIL`. Admin = chính chủ dashboard: xem "Việc của tôi", quản lý Drive Token. (Server chỉ phục vụ localhost — `LOCAL_ONLY`.)

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
| **`docs.py`** | Module quản lý tài liệu nội bộ. Sync dữ liệu 2 chiều giữa JSON local cache và Cloudflare KV. |
| **`task_link.py`** | Quản lý mapping Link (Bug log) ↔ (Jira Task), để drawer task hiện bug liên quan. |
| **`custom_status.py`** | Xử lý "Nhãn Nội Bộ" (Overlay Status) để gán cho task Jira (VD: *Chờ QA*, *Đã Test*). Dữ liệu này không ghi thật vào Status của Jira mà lưu qua Cloudflare KV. |
| **`monthly_reporter_chat_app.py`** | Một script tool đứng riêng để tự sinh và báo cáo SLA tháng lên Google Chat thông qua Playwright headless. |
| **`render.py`** | Module phụ trách toàn bộ Logic Server-Side Rendering (SSR). Map các components lại với nhau và trả ra HTML hoàn chỉnh có gắn string templates. |
| **`routes/`** | Chứa `oauth.py`, `write.py`, `uploads.py` là các Mixins Class để tách nhỏ logic xử lý HTTP route khỏi file `qa_dashboard.py` khổng lồ. |

Tái cấu trúc folder (issue #85): code lõi trong `core/`, asset tĩnh trong `assets/`, script tiện ích trong `scripts/`. Entry `qa_dashboard.py` giữ ở root, tự thêm `core/` vào `sys.path`.

---

## Các trang (tab)

Điều hướng qua **sidebar** bên trái (UI v2). Profile chip dưới sidebar có menu **Cài đặt PAT** + **Đăng xuất**.

| Route | Tab | Mô tả |
|---|---|---|
| `/` | — | Redirect về `/my-work`. |
| `/my-work` | **Việc của tôi** | Task Jira của chính chủ (`JIRA_SELF_USER`): tabs Active/Quá hạn/Kẹt, KPI, drawer chi tiết. |
| `/bug-log` | **Bugs** | Bug log đồng bộ từ file `.xlsx`/Google Sheet trên Drive + liên kết bug ↔ Jira task. |
| `/analytics` | **Analytics** | Valid/Rejected Bug Rate, bug theo dev/dự án + severity, Tỷ lệ Reopen, tồn đọng (nguồn report tháng CTO). |
| `/docs` | **Tài liệu** | Cây thư mục + link Google Drive + upload file, viewer inline, folder Quy Trình. |
| `/settings` | **Cài đặt** | API token Jira cá nhân (mã hoá khi lưu) + kết nối Google Drive. |

Dashboard dùng riêng 1 người, chỉ chạy trên máy host (`LOCAL_ONLY`). Dashboard team, Roadmap, Test Case, Đánh giá leader và API cho app Android đã gỡ (CLAUDE.md Decision #96/#97).

## Features chính

- **KPI cards** cá nhân: Active · Quá hạn · Kẹt ≥5 ngày · Due tuần này · Done
- **Overdue tính theo ngày làm việc** (T2–T6, bỏ T7/CN)
- **Activity feed** dựng từ Jira changelog (status/assignee/duedate/priority/comment/tạo mới); tên người hiển thị đúng (QA = tên ngắn, người ngoài = display name); dismiss đồng bộ chéo máy qua Cloudflare KV.
- **Notification real-time** — short-poll `/activity-feed` mỗi 60s (tự dừng khi tab ẩn), cập nhật chuông + toast + status/nhãn nội bộ của task **mà KHÔNG reload trang**. (Thay cho cơ chế auto-refresh 15 phút của UI cũ.) Data bảng/KPI/donut vẫn chỉ tươi khi **F5 thủ công**.
- **Đổi status + gán nhãn nội bộ** (8 nhãn: Dev fix bug, Chờ BA confirm, …) ngay trên dashboard, ghi Jira **bằng PAT cá nhân** → đúng tên người
- **Tạo QA sub-task** dưới bất kỳ task cha (nhiều cha / 1 lần, auto-fill `[QA]`)
- **Bug log từ Drive**: background thread poll file `.xlsx` mỗi 10 phút, normalize + diff, link bug ↔ Jira task
- Mọi key Jira là hyperlink → mở thẳng task / drawer chi tiết. UTF-8 tiếng Việt.

---

## Setup (lần đầu)

### 1. Cài dependencies

```bash
pip install -r requirements.txt
```

### 2. Tạo Jira Personal Access Token

Jira Bảo Kim đã chuyển sang **Jira Cloud** (`https://baokim.atlassian.net`, issue #197). Cloud không có PAT — dùng **API token Atlassian**:
[id.atlassian.com → Security → API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) → **Create API token** (loại thường, không chọn "with scopes"):
- Name: `qa-workspace` · Expiry: tối đa 1 năm
- Copy token (chỉ hiện 1 lần)

> Token này (trong `.env`, kèm `JIRA_EMAIL` của chủ token) là **token chung** dùng để đọc. Mỗi QA còn có thể dán **API token cá nhân** ở `/settings` để thao tác *ghi* (đổi status, comment, tạo sub-task) ghi đúng tên mình.

### 3. Tạo file `.env`

```bash
cp .env.example .env
# Mở .env, điền JIRA_EMAIL + JIRA_API_TOKEN (và phần OAuth nếu golive)
```

Các biến chính (xem `.env.example` để đầy đủ + chú thích):

| Biến | Ý nghĩa |
|---|---|
| `JIRA_URL` | `https://baokim.atlassian.net` (không có `/` cuối) |
| `JIRA_EMAIL` | email Atlassian của chủ token chung |
| `JIRA_API_TOKEN` | API token chung (dùng để đọc) |
| `JIRA_ACCOUNT_IDS` | (tùy chọn) JSON override username → accountId |
| `JIRA_PORT` | cổng local (mặc định 8080) |
| `JIRA_ADMIN_EMAIL` | email chính chủ (role admin) |
| `JIRA_SELF_USER` | username Jira duy nhất được tracking (mặc định `thanhht1`) |
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
| User được track | Sửa `JIRA_SELF_USER` trong `.env`, restart |
| Display name | `config.py` → `DEFAULT_DISPLAY_NAMES` (hoặc env `JIRA_DISPLAY_NAMES` JSON) |
| Ngưỡng "kẹt" (5 ngày) | `config.py` → `STUCK_DAYS` |
| Nhãn nội bộ (custom status) | `custom_status.py` → `CUSTOM_STATUSES` |
| Field id tạo sub-task | `config.py` → `SUBTASK_TYPE_ID` / `TASK_PTSP_TYPE_ID` / `START_DATE_FIELD` / `LEADER_FIELD` |
| Port | `JIRA_PORT` trong `.env` |

## Reset state

Docs/dismiss/PAT/nhãn nội bộ sync qua Cloudflare KV nên xoá file cache local không mất data (Cloudflare KV là source of truth cho metadata phụ trợ, file local chỉ là cache fallback).

## Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `401 API token sai hoặc hết hạn` | Token sai/expired, hoặc `JIRA_EMAIL` không phải chủ token | Tạo token mới, update `.env` |
| `403 API token không đủ quyền` | Tài khoản thiếu Browse Projects | Xin quyền cho tài khoản chủ token |
| `Không tìm thấy tài khoản Jira Cloud cho "x"` | Không resolve được accountId (email bị ẩn) | Khai `JIRA_ACCOUNT_IDS` trong `.env` |
| `Port đang bị chiếm` | Process khác dùng 8080 | Đổi `JIRA_PORT` |
| `Network error` | Không vào được Jira | Check kết nối internet / status.atlassian.com |
| Trống không có task | JQL ra 0 issue | Check `JIRA_SELF_USER` đúng username |
| Bị đá về `/login` liên tục | OAuth chưa cấu hình đúng | Check `GOOGLE_*` + redirect URI khớp |
| Đổi status báo "chưa cấu hình API token" | Chưa dán token cá nhân (PAT Jira cũ không còn hiệu lực) | Vào `/settings` dán API token Jira Cloud |
| Bugs trống / không sync | Chưa kết nối Drive / chưa khai báo file nguồn | `/bug-log` → kết nối Drive + thêm file nguồn |

---

### ⚠ Đường dẫn ổn định cho cron / launchd / alias

Khi setup cron, launchd plist, alias hay shortcut, **đừng trỏ thẳng vào module con** (chúng có thể bị move khi tái cấu trúc folder — như issue #85 đã move mọi thứ vào `core/`/`scripts/`). Quy ước:

- **Chạy dashboard** → luôn gọi entry ở root: `python3 /Users/thanhht/qa-dashboard/qa_dashboard.py` (hoặc `start.command`/`start.bat`). Đây là API ổn định, không bao giờ move.
- **Script tiện ích** → nằm trong `scripts/` (vd `run_monthly_report.sh`). Job phải `cd <root>` rồi gọi `scripts/<tên>`.
- **Tool định kỳ** (`monthly_reporter_chat_app.py`) → nằm trong `core/`. Job phải `cd <root>` rồi gọi `core/<tên>.py` (cwd phải là root để đọc đúng `.env` + `gcp-service-account.json`).

Daemon hiện có trên host Mac (audit issue #88): `com.qa.dashboard` (→ `qa_dashboard.py` root, OK), `com.qa.cloudflared`, `com.qa.socks` (không trỏ module Python), và 1 crontab chạy `core/monthly_reporter_chat_app.py --cron` cuối tháng.
