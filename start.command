#!/usr/bin/env bash
# QA Dashboard launcher — macOS / Linux
# Usage: ./start.sh   (chmod +x start.sh lần đầu)
set -e
cd "$(dirname "$0")"

# 1. Tìm Python 3
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "[LỖI] Chưa có Python 3. Cài tại https://www.python.org/downloads/"
  exit 1
fi

# 2. Kiểm tra .env
if [ ! -f .env ]; then
  echo "[LỖI] Thiếu file .env."
  echo "       Copy .env.example thành .env rồi điền JIRA_URL và JIRA_PAT."
  exit 1
fi

# 3. Cài 'requests' nếu thiếu
if ! "$PY" -c "import requests" >/dev/null 2>&1; then
  echo "Đang cài thư viện 'requests'..."
  "$PY" -m pip install requests || { echo "[LỖI] Cài requests thất bại."; exit 1; }
fi

# 4. Lấy port từ .env (mặc định 8080) — chỉ đọc JIRA_PORT, không lộ PAT
PORT="$(grep '^JIRA_PORT=' .env | head -1 | sed 's/^JIRA_PORT=//; s/["'"'"' ]//g')"
PORT="${PORT:-8080}"

# 5. Mở browser sau khi server kịp bind (chạy nền)
URL="http://localhost:${PORT}/"
(
  sleep 1.5
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  fi
) >/dev/null 2>&1 &

echo "Dashboard: $URL   (Ctrl+C để dừng)"
exec "$PY" qa_dashboard.py
