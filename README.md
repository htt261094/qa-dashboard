# QA Team Dashboard

Dashboard nội bộ cho team QA Bảo Kim — pull data **live** từ Jira (Data Center 10.7.3) qua REST API, render HTML server-side bằng Python thuần. Thay cho Jira native dashboard.

Stack: Python 3.8+ · chỉ 2 dep (`requests`, `cryptography`) · server `http.server` stdlib · không framework.

---

## Các trang (tab)

| Route | Tab | Mô tả | Ai xem được |
|---|---|---|---|
| `/` | **Tổng quan** | Dashboard vận hành live. Admin thấy lens quản lý (workload matrix, donut, KPI Vào/Ra, activity feed toàn team). QA thường thấy **lens cá nhân** ("Việc của tôi") tự scope về mình. | Mọi người |
| `/report` | **Báo cáo tuần** | Rollup theo project key + RAG, 2 donut, cây "Tiến độ test theo line", in được (Ctrl+P). | Chỉ admin |
| `/roadmap` | **Roadmap** | Giai đoạn › mục › sub-task, status/%/hạn, cảnh báo hạn ≤2 tuần đẩy lên dashboard. | Mọi người xem; chỉ admin sửa |
| `/docs` | **Tài liệu** | Cây thư mục + link Google Drive cho tài liệu training. | Mọi người xem; chỉ admin sửa |
| `/settings` | **Cài đặt** | Đặt PAT cá nhân (mã hoá khi lưu) để thao tác Jira ghi đúng tên người dùng. | Mọi người |

## Features chính

- **5 KPI cards** (admin: Active / Overdue / Due tuần / Vào-Ra tuần / Done · QA: bản cá nhân)
- **Workload matrix** Assignee × Status, badge QUÁ TẢI/OK/NHẸ (ngưỡng ≥15 / 5–14 / ≤4)
- **Overdue tính theo ngày làm việc** (T2–T6, bỏ T7/CN)
- **Activity feed** dựng từ Jira changelog (status/assignee/duedate/priority/comment/tạo mới); dismiss đồng bộ chéo máy qua Jira user property. Lens cá nhân: feed theo **watcher** (QA watch task nào thì thấy hoạt động trên task đó).
- **Filter theo người** (assignee/reporter) — client-side, nhớ qua localStorage
- **Auto-refresh 15 phút** (toggle ON/OFF ở header, nhớ qua localStorage). F5 = pull data tươi.
- **Highlight task mới** phát sinh giữa 2 lần refresh (badge NEW cam)
- **Đổi status / nhãn nội bộ** ngay trên dashboard (nếu PAT đủ quyền)
- Mọi key Jira là hyperlink → mở thẳng task. UTF-8 tiếng Việt.

## Đăng nhập & phân quyền

- **Local dev** (`GOOGLE_CLIENT_ID`/`SECRET` để trống): không bắt login, mọi request = admin.
- **Golive**: Google OAuth — app redirect sang Google, chỉ chấp nhận email thuộc `JIRA_ALLOWED_DOMAIN`, set session cookie ký HMAC (TTL 12h). `JIRA_ADMIN_EMAIL` = người duy nhất được sửa roadmap/docs + xem báo cáo tuần. (Chi tiết kiến trúc auth xem `CLAUDE.md` Decision #15.)

---

## Setup (lần đầu)

### 1. Cài dependencies

```bash
pip install -r requirements.txt
```

### 2. Tạo Jira Personal Access Token

Login Jira Bảo Kim → avatar góc phải → **Profile** → **Personal Access Tokens** → **Create token**:
- Name: `qa-dashboard` · Expiry: theo policy
- Quyền cần: **Browse Projects** (thêm quyền transition nếu muốn đổi status từ dashboard)
- Copy token (chỉ hiện 1 lần)

### 3. Tạo file `.env`

```bash
cp .env.example .env
# Mở .env, điền JIRA_PAT (và phần OAuth nếu golive)
```

Các biến chính (xem `.env.example` để đầy đủ + chú thích):

| Biến | Ý nghĩa |
|---|---|
| `JIRA_URL` | `https://jira.baokim.vn:8443` (không có `/` cuối) |
| `JIRA_PAT` | Personal Access Token |
| `JIRA_USERS` | username QA team, phân tách dấu phẩy |
| `JIRA_PORT` | cổng local (mặc định 8080) |
| `JIRA_ADMIN_EMAIL` | email role admin (sửa roadmap/docs, xem báo cáo) |
| `JIRA_ALLOWED_DOMAIN` | domain được phép login (vd `baokim.vn`) |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | bật khi golive → bắt đăng nhập Google |
| `SESSION_SECRET` | khoá ký session cookie (bắt buộc khi bật OAuth): `python -c "import secrets;print(secrets.token_urlsafe(48))"` |

> **OPSEC:** `.env` và mọi file state KHÔNG commit lên git (đã có trong `.gitignore`). Không bao giờ log/in PAT ra console.

### 4. Chạy

```bash
python qa_dashboard.py
```

Hoặc double-click launcher: `start.bat` (Windows) · `start.command` (macOS).

```
QA Team Dashboard
  Jira:      https://jira.baokim.vn:8443
  Tracking:  Quang, Nhung, Phương, Thơ, Thành
  Dashboard: http://localhost:8080/
  State:     .last_seen.json
  Ctrl+C để stop
```

Mở browser: `http://localhost:8080/`

---

## Sử dụng hằng ngày

- **F5** (hoặc auto 15 phút): pull data tươi từ Jira.
- Lần refresh đầu: ghi snapshot baseline, chưa highlight. Lần sau: task mới → badge **NEW** cam.
- Click key (vd `DA51H26-2843`) → mở task trong Jira.
- Filter dropdown (góc trên grid): xem nhanh việc của 1 QA.

## Customize

| Muốn đổi | Cách |
|---|---|
| Danh sách user track | Sửa `JIRA_USERS` trong `.env`, restart |
| Display name | `config.py` → `DEFAULT_DISPLAY_NAMES` (hoặc env `JIRA_DISPLAY_NAMES` JSON) |
| Ngưỡng QUÁ TẢI (15/5/4) | `render.py` → `render_workload` |
| Ngưỡng "kẹt" (5 ngày) | `config.py` → `STUCK_DAYS` |
| Port | `JIRA_PORT` trong `.env` |

## Reset state

```bash
rm .last_seen.json     # coi như chạy lần đầu (mất baseline NEW-badge)
```

Roadmap/docs sync qua Jira property nên xoá file local không mất data (Jira là source of truth).

## Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `401 PAT sai hoặc hết hạn` | Token sai/expired | Tạo PAT mới, update `.env` |
| `403 PAT không đủ quyền` | Thiếu Browse Projects | PAT mới đủ scope |
| `Port đang bị chiếm` | Process khác dùng 8080 | Đổi `JIRA_PORT` |
| `Network error` | Không vào được Jira | Check VPN/Tailscale/kết nối nội bộ |
| Trống không có task | JQL ra 0 issue | Check `JIRA_USERS` đúng username |
| Bị đá về `/login` liên tục | OAuth chưa cấu hình đúng | Check `GOOGLE_*` + redirect URI khớp |

---

## Kiến trúc & file

Module theo layer (không vòng import): `config` → `issues` → `{jira_api, state, pic, docs, roadmap, auth, pat_store, custom_status, crypto_util, jira_write}` → `render` → `qa_dashboard` (entry).

```
qa_dashboard.py   ← ENTRY: HTTP Handler (do_GET/do_POST) + main()
config.py         ← env load, JIRA_URL/PAT/USERS/PORT, display_name, STUCK_DAYS
issues.py         ← accessor i_* + helper (parse_date, days_overdue, is_stuck, esc...)
jira_api.py       ← gọi Jira REST (fetch_all/lines/activity_feed, load/save property)
state.py          ← snapshot .last_seen.json cho NEW badge
auth.py           ← Google OAuth + session cookie HMAC
pat_store.py      ← PAT cá nhân per-user (mã hoá qua crypto_util)
crypto_util.py    ← mã hoá/giải mã PAT cá nhân
custom_status.py  ← nhãn trạng thái nội bộ
jira_write.py     ← ghi Jira (transition status)
pic.py / docs.py / roadmap.py  ← data tự soạn (sync qua Jira property + cache local)
render.py         ← toàn bộ render_* (4 page) + load_css/load_js
styles.css        ← toàn bộ CSS (inline lúc render)
app.js            ← toàn bộ JS (inline lúc render)
start.bat / start.command  ← launcher
.env / .env.example
.last_seen.json   ← state (auto-generated)
```

> File chi tiết quyết định thiết kế + lý do: xem **`CLAUDE.md`**.
