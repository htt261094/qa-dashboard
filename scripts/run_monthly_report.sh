#!/usr/bin/env bash
# Báo cáo Bug Metric tháng -> CTO (Google Chat).
#
# Wrapper tự dựng 1 instance qa_dashboard.py trên 1 PORT RIÊNG (né server chính 8080) để
# reporter (cookie phiên admin ký bằng SESSION_SECRET) drive /analytics, export PDF + gửi,
# rồi tắt server. Jira Cloud không cần VPN nên đã bỏ bản bug_log_offline.py.
#
# Crontab gọi script này cuối tháng. Output -> reports/cron.log (do crontab redirect).
set -u

ROOT="/Users/thanhht/qa-dashboard"
PY="/usr/bin/python3"
PORT="${REPORT_PORT:-8077}"   # port riêng cho lần chạy này, né server chính (8080)

cd "$ROOT" || { echo "[LỖI] Không cd được vào $ROOT"; exit 1; }
mkdir -p reports

echo "===== $(date '+%F %T') monthly report (port $PORT) ====="

# 1. Chỉ chạy thật vào ngày cuối tháng (mai là mùng 1). Giống guard --cron của reporter,
#    nhưng chặn SỚM để không phí dựng server vào 28/29/30.
if [ "$(date -v+1d '+%d')" != "01" ]; then
  echo "Hôm nay không phải ngày cuối tháng — bỏ qua."
  exit 0
fi

# 2. Dựng server trên port riêng.
JIRA_PORT="$PORT" "$PY" qa_dashboard.py &
SRV_PID=$!

# Tắt server dù thoát kiểu gì (lỗi/kill/xong).
cleanup() { kill "$SRV_PID" 2>/dev/null; wait "$SRV_PID" 2>/dev/null; }
trap cleanup EXIT

# 3. Đợi server sẵn sàng (tối đa ~40s). Probe route PUBLIC (assetlinks: không gate login,
#    không gọi Jira) — /analytics khi AUTH bật sẽ redirect sang login.
ready=0
for _ in $(seq 1 40); do
  if curl -fsS -o /dev/null "http://localhost:$PORT/.well-known/assetlinks.json"; then ready=1; break; fi
  # Server chết sớm (vd thiếu dep) -> khỏi đợi đủ 40s.
  kill -0 "$SRV_PID" 2>/dev/null || break
  sleep 1
done

if [ "$ready" != "1" ]; then
  echo "[LỖI] qa_dashboard.py không sẵn sàng trên port $PORT — bỏ qua gửi."
  exit 1
fi

# 4. Reporter: export PDF + gửi CTO. --cron tự guard ngày cuối tháng (double-check, vô hại).
JIRA_PORT="$PORT" "$PY" core/monthly_reporter_chat_app.py --cron
RC=$?

echo "===== xong (rc=$RC) ====="
exit "$RC"
