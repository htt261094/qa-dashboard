# QA Workspace

Workspace nội bộ cho team QA — pull data **live** từ **Linear** qua GraphQL API (`https://api.linear.app/graphql`), render HTML server-side bằng Python thuần.

Stack: Python 3.8+ · server `http.server` stdlib · **không web-framework** · UI vanilla JS + CSS (`app_v2.js` / `styles_v2.css`) · Chart.js (Cycle Burndown).

Dependencies (xem `requirements.txt`):

| Dep | Dùng cho |
|---|---|
| `requests` | gọi Linear GraphQL API + Google OAuth/userinfo |
| `cryptography` | mã hoá at-rest API key cá nhân (Fernet) |

---

## Data Flow (Luồng Dữ Liệu)

1. **Linear GraphQL API là Source of Truth**:
   - Dữ liệu task, cycle, hierarchy (`project` = Feature, `parent`/`children` = Story & Sub-issue), changelog và comment được kéo trực tiếp từ Linear bằng `LINEAR_API_KEY`.
   - Jira tạm ngắt (`JIRA_ENABLED=false`, `BUG_LOG_JIRA_ENABLED=false`).
2. **Phạm vi Tracked Team & Accounts**:
   - Loại bỏ team `VC` (`LINEAR_EXCLUDED_TEAMS=VC`).
   - Track đúng danh sách thành viên + role khai báo trong `TRACKED_ROLES` (`core/config.py`): PO, BA, Designer, DEV, QA, QA Lead.
   - Màn **Bugs** & **Analytics** lọc theo Bug (`[Bug]` prefix hoặc label `Bug`), chia theo 2 QA (**Thuyết**, **Nhàn**) và 5 DEV được track.
3. **Local Cache & Cloudflare KV Sync**:
   - Dữ liệu bổ sung (Docs, Custom Status, Task Notes, Bug Log snapshot/seen watermark) lưu local (`.json`) và đồng bộ chéo máy qua Cloudflare KV nếu cấu hình.
4. **Real-time Notifications**:
   - Client short-poll `/activity-feed` mỗi **60 giây** (tự dừng khi tab ẩn), cập nhật chuông thông báo, toast và trạng thái trực tiếp trên UI.

---

## Các trang (tab)

| Route | Tab | Mô tả |
|---|---|---|
| `/` | — | Redirect về `/today`. |
| `/today` | **Hôm nay** | Tổng hợp việc cần xử lý: Bug tồn đọng ≥5 ngày, Quá hạn, Kẹt, Standup — bấm dòng mở drawer chi tiết. |
| `/my-work` | **Cycle {số}** | Burndown chart từng ngày (Chart.js) + Kanban board động theo workflow state Linear, lọc theo Người / Feature / Loại (`Chỉ Bug`), hỗ trợ **Gom theo Feature** + hiển thị `parent`/`sub-issues`. |
| `/bug-log` | **Bugs** | Danh sách bug từ Linear (`[Bug]` prefix / label `Bug`), chia tab **QA Thuyết** / **QA Nhàn**, lọc theo Feature / Tester / Dev / Severity, xuất Excel. |
| `/analytics` | **Analytics** | Valid/Rejected Bug Rate, chart bug theo Dev & Severity (`sev:*` → Blocker/Critical/High/Medium/Low), Tỷ lệ Reopen, Xu hướng qua các Sprint/Cycle. |
| `/docs` | **Tài liệu** | Cây thư mục tài liệu + upload/preview file. |
| `/settings` | **Cài đặt** | Cấu hình Linear API key cá nhân + bật thông báo desktop. |

---

## Setup & Chạy Local

### 1. Cài dependencies

```bash
pip install -r requirements.txt
```

### 2. Tạo file `.env`

```ini
LINEAR_API_KEY=lin_api_...
LINEAR_BASE_URL=https://linear.app/thehumaninc
JIRA_ENABLED=false
BUG_LOG_JIRA_ENABLED=false
BUG_LOG_LINEAR_ENABLED=true
JIRA_PORT=8080
LOCAL_ONLY=1
LOCAL_AUTOLOGIN=1
```

### 3. Khởi động server

```bash
python3 qa_dashboard.py
```

Mở trình duyệt tại `http://localhost:8080/`.
