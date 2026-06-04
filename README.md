# QA Team Dashboard

Dashboard cho team QA Bảo Kim, pull data live từ Jira qua REST API.

## Features

- 5 KPI cards: Total Active, Overdue, Due This Week, New 24h (self-created), Done This Week
- Workload matrix: Assignee × Status, có badge QUÁ TẢI/OK/NHẸ theo ngưỡng (≥15 / 5–14 / ≤4)
- Bảng Overdue có cột "Days Overdue"
- Bảng New 24h (do QA tự tạo) + Done This Week
- **Task mới phát sinh giữa 2 lần refresh được highlight badge "NEW" màu cam**
- Mọi key Jira đều là hyperlink → click mở thẳng task trên Jira Bảo Kim
- Refresh thủ công: F5 = pull data fresh

## Setup (lần đầu)

### 1. Cài Python + requests

```bash
pip install requests
```

### 2. Tạo Jira Personal Access Token

Login Jira Bảo Kim → click avatar góc phải trên → **Profile** → **Personal Access Tokens** → **Create token**:
- Name: `qa-dashboard`
- Expiry: 90 ngày (hoặc theo policy)
- Click **Create** → copy token (sẽ chỉ hiện 1 lần duy nhất)

### 3. Tạo file `.env`

Copy `.env.example` → `.env`, paste PAT vào:

```bash
cp .env.example .env
# Mở .env bằng editor, sửa JIRA_PAT
```

> **Lưu ý OPSEC:** File `.env` không bao giờ commit lên git. Thêm vào `.gitignore`:
> ```
> .env
> .last_seen.json
> ```

### 4. Chạy

```bash
python qa_dashboard.py
```

Output:
```
QA Team Dashboard
  Jira:      https://jira.baokim.vn:8443
  Tracking:  Quang, Nhung, Phương, Thơ, Thành
  Dashboard: http://localhost:8080/
  Ctrl+C để stop
```

Mở browser: `http://localhost:8080/`

## Sử dụng

- **F5**: pull data fresh từ Jira
- Lần refresh đầu: tất cả task được "ghi nhận" làm baseline, không có highlight
- Lần refresh sau: task nào mới xuất hiện so với baseline trước → highlight badge **NEW** cam, hàng nền vàng nhạt
- Click vào key (vd `DA51H26-2843`) → mở task trong Jira tab mới

## Customize

### Đổi danh sách user track

Sửa `JIRA_USERS` trong `.env`, restart script.

### Đổi display name

Mở `qa_dashboard.py`, sửa dict `DEFAULT_DISPLAY_NAMES` ở đầu file.

### Đổi ngưỡng QUÁ TẢI

Mở `qa_dashboard.py`, search `>= 15` trong function `render_workload`, đổi số.

### Đổi port

Sửa `JIRA_PORT` trong `.env`.

## Reset state (xóa baseline)

Nếu muốn coi như chạy lần đầu (vd: sau khi clear backlog):

```bash
rm .last_seen.json
```

## Troubleshooting

| Lỗi | Nguyên nhân | Fix |
|---|---|---|
| `401 PAT sai hoặc hết hạn` | Token sai hoặc expired | Tạo PAT mới, update `.env` |
| `403 PAT không đủ quyền` | PAT thiếu Browse Projects | Tạo PAT mới với đủ scope |
| `Port đang bị chiếm` | Có process khác dùng 8080 | Đổi `JIRA_PORT` trong `.env` |
| `Network error` | Mạng không vào được Jira | Check VPN / kết nối |
| Trống không có task | JQL filter ra 0 issue | Check `JIRA_USERS` có đúng username không |

## File trong folder

- `qa_dashboard.py` — main script (1 file, không tách module)
- `.env` — credential + config (KHÔNG commit)
- `.env.example` — template
- `.last_seen.json` — state file (auto-generated, không cần đụng vào)
- `README.md` — file này
