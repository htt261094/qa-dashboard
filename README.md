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

## Các trang (tab)

Điều hướng qua **sidebar** bên trái (UI v2). Profile chip dưới sidebar có menu **Cài đặt PAT** + **Đăng xuất**.

| Route | Tab | Mô tả | Ai xem được |
|---|---|---|---|
| `/` | **Dashboard** | Vận hành live. Admin thấy lens quản lý toàn team (workload matrix, donut, KPI Vào/Ra, activity feed). QA thường thấy **lens cá nhân** tự scope về mình. | Mọi người |
| `/my-work` | **Việc của tôi** | Lens cá nhân của admin (task của chính mình), UI hệt QA member. | Chỉ admin (QA → đá về `/`) |
| `/leader-eval` | **Đánh giá** | Đánh giá task QA theo tháng (lọc category/leader/assignee). | Chỉ admin |
| `/roadmap` | **Roadmap** | Giai đoạn › mục › sub-task, status/%/hạn; cảnh báo hạn ≤2 tuần đẩy lên dashboard. | Mọi người xem; chỉ admin sửa |
| `/bug-log` | **Bugs** | Bug log đồng bộ từ file `.xlsx` trên Google Drive + tự liên kết bug/test-case ↔ Jira task. | Mọi người (đã đăng nhập) |
| `/docs` | **Tài liệu** | Cây thư mục + link Google Drive + **upload file thật** cho tài liệu training. | Mọi người xem; chỉ admin sửa |
| `/settings` | **Cài đặt** | Đặt PAT cá nhân (mã hoá khi lưu) để thao tác ghi Jira đúng tên người. | Mọi người |

## Features chính

- **KPI cards** + **Workload matrix** Assignee × Status, badge QUÁ TẢI/OK/NHẸ (ngưỡng ≥15 / 5–14 / ≤4)
- **Overdue tính theo ngày làm việc** (T2–T6, bỏ T7/CN); metric "kẹt ≥5 ngày" + "Vào/Ra tuần"
- **Activity feed** dựng từ Jira changelog (status/assignee/duedate/priority/comment/tạo mới); tên người hiển thị đúng (QA = tên ngắn, người ngoài = display name); dismiss đồng bộ chéo máy qua Jira user property.
- **Notification real-time** — short-poll `/activity-feed` mỗi 60s (tự dừng khi tab ẩn), cập nhật chuông + toast + status/nhãn nội bộ của task **mà KHÔNG reload trang**. (Thay cho cơ chế auto-refresh 15 phút của UI cũ.) Data bảng/KPI/donut vẫn chỉ tươi khi **F5 thủ công**.
- **Highlight task mới** phát sinh giữa 2 lần refresh (badge NEW cam)
- **Filter theo người** (assignee/reporter) — client-side, nhớ qua localStorage
- **Đổi status + gán nhãn nội bộ** (8 nhãn: Dev fix bug, Chờ BA confirm, …) ngay trên dashboard, ghi Jira **bằng PAT cá nhân** → đúng tên người
- **Tạo QA sub-task** dưới Task-PTSP từ modal (auto-fill `[QA]` + Leader Hiền)
- **Bug log từ Drive**: background thread poll file `.xlsx` mỗi 10 phút, normalize + diff, link bug ↔ Jira task
- Mọi key Jira là hyperlink → mở thẳng task / drawer chi tiết. UTF-8 tiếng Việt.

## Đăng nhập & phân quyền

- **Local dev** (`GOOGLE_CLIENT_ID`/`SECRET` để trống): không bắt login, mọi request = admin.
- **Golive**: Google OAuth — app redirect sang Google, chỉ chấp nhận email thuộc `JIRA_ALLOWED_DOMAIN`, set session cookie ký HMAC (TTL 12h). `JIRA_ADMIN_EMAIL` = người được sửa roadmap/docs + thấy tab admin. Server 403 là lock thật; ẩn UI chỉ là UX. (Chi tiết kiến trúc auth: `CLAUDE.md` Decision #15.)

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

Roadmap/docs/dismiss/PAT/nhãn nội bộ sync qua Jira property nên xoá file cache local không mất data (Jira là source of truth, file local chỉ là cache fallback).

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

## Kiến trúc & file

Module theo layer (không vòng import): `config` → `issues` → `{jira_api, state, docs, roadmap, auth, pat_store, custom_status, crypto_util, jira_write, bug_log*, drive_token, task_link}` → `render` → `qa_dashboard` (entry).

Tái cấu trúc folder (issue #85): code lõi trong `core/`, asset tĩnh trong `assets/`, script tiện ích trong `scripts/`. Entry `qa_dashboard.py` giữ ở root (`python qa_dashboard.py` không đổi), tự thêm `core/` vào `sys.path`.

```
qa_dashboard.py    ← ENTRY (ROOT): HTTP Handler (do_GET/do_POST, ~30 route) + main(). Thêm core/ vào sys.path.
start.bat / start.command  ← launcher (ROOT)

core/
  config.py          ← env load, JIRA_URL/PAT/USERS/PORT, ADMIN_EMAIL/SELF_USER, OAuth, field ids, STUCK_DAYS, ASSETS_DIR
  issues.py          ← accessor i_* + helper (parse_date, days_overdue, is_stuck, esc...)
  jira_api.py        ← Jira REST (PAT chung): fetch_all/activity_feed, leader_eval, load/save property
  auth.py            ← Google OAuth + session cookie HMAC
  crypto_util.py     ← Fernet mã hoá/giải mã (PAT cá nhân + token Drive)
  pat_store.py       ← PAT cá nhân per-user (verify đúng chủ + mã hoá)
  jira_write.py      ← ghi Jira bằng PAT cá nhân: transition / comment / create_subtask
  custom_status.py   ← nhãn trạng thái nội bộ (overlay, sync property)
  docs.py / roadmap.py  ← data tự soạn (sync Jira property + cache local)
  bug_log.py         ← tải + parse file .xlsx bug log từ Drive
  bug_log_source.py  ← danh sách file Drive nguồn
  bug_log_store.py   ← background thread poll Drive 10 phút + cache + diff
  drive_token.py     ← refresh_token Google Drive (mã hoá at-rest)
  task_link.py       ← link bug/test-case ↔ Jira task (sync property)
  render.py          ← toàn bộ render_* (UI v2 sidebar) + load_css/load_css_v2/load_js_v2 (đọc từ assets/)

assets/
  styles_v2.css / app_v2.js  ← UI v2 (Stitch sidebar), inline lúc render
  styles.css         ← chỉ render_error_page còn dùng

scripts/
  run_monthly_report.sh

.env / .env.example  ← (ROOT)
uploads/           ← file upload từ /docs (gitignore, hardcode path macOS — xem CLAUDE.md #37)
```

> File chi tiết quyết định thiết kế + lý do (24 Decision): xem **`CLAUDE.md`**.

### ⚠ Đường dẫn ổn định cho cron / launchd / alias

Khi setup cron, launchd plist, alias hay shortcut, **đừng trỏ thẳng vào module con** (chúng có thể bị move khi tái cấu trúc folder — như issue #85 đã move mọi thứ vào `core/`/`scripts/`). Quy ước:

- **Chạy dashboard** → luôn gọi entry ở root: `python3 /Users/thanhht/qa-dashboard/qa_dashboard.py` (hoặc `start.command`/`start.bat`). Đây là API ổn định, không bao giờ move.
- **Script tiện ích** → nằm trong `scripts/` (vd `run_monthly_report.sh`). Job phải `cd <root>` rồi gọi `scripts/<tên>`.
- **Tool định kỳ** (`monthly_reporter_chat_app.py`) → nằm trong `core/`. Job phải `cd <root>` rồi gọi `core/<tên>.py` (cwd phải là root để đọc đúng `.env` + `gcp-service-account.json`).

Daemon hiện có trên host Mac (audit issue #88): `com.qa.dashboard` (→ `qa_dashboard.py` root, OK), `com.qa.cloudflared`, `com.qa.socks` (không trỏ module Python), và 1 crontab chạy `core/monthly_reporter_chat_app.py --cron` cuối tháng.
