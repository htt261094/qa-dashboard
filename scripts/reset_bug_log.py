"""Reset cache + kho KV của Bug Log — chạy 1 LẦN khi cut-over Drive -> Jira (Decision #104).

Vì sao: dữ liệu bug log cũ kéo từ Google Sheet trên Drive (nhất là tháng 10) KHÔNG đáng tin;
cut-over sang Jira "Bug Testing" nên xoá sạch để scan đầu dựng lại từ Jira, khỏi lẫn bug Drive cũ
vào metric. KHÔNG auto-wipe trong code (tránh mất data ngoài ý muốn) -> chạy tay script này.

    .venv\\Scripts\\python.exe scripts\\reset_bug_log.py          # hỏi xác nhận
    .venv\\Scripts\\python.exe scripts\\reset_bug_log.py --yes    # không hỏi

Xoá: local .json + key KV tương ứng (bug log snapshot, nguồn, monthly/backlog, watermark đã xem,
link bug<->task). KHÔNG đụng Drive token, PAT, docs, custom-status, task-notes.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'core'))

import config  # noqa: E402
from remote_store import remote_delete  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8')
except (AttributeError, ValueError):
    pass

LOCAL_FILES = [
    config.BUG_LOG_FILE,
    config.BUG_LOG_SOURCE_FILE,
    config.BUG_MONTHLY_FILE,
    config.BUG_TASK_LINK_FILE,
]
KV_KEYS = [
    'qa-dashboard-bug-log',
    'qa-dashboard-bug-log-seen',
    'qa-dashboard-bug-log-source',
    'qa-dashboard-bug-monthly',
    'qa-dashboard-bug-task-link',
]


def main(auto_yes):
    print('Sẽ XOÁ (reset Bug Log cho cut-over Drive -> Jira #104):')
    for p in LOCAL_FILES:
        print(f'  local: {p}  ({"có" if os.path.exists(p) else "không có"})')
    for k in KV_KEYS:
        print(f'  KV:    {k}')
    if not auto_yes:
        ans = input('\nGõ "yes" để xoá: ').strip().lower()
        if ans != 'yes':
            print('Huỷ.')
            return 1

    for p in LOCAL_FILES:
        try:
            if os.path.exists(p):
                os.remove(p)
                print(f'[local] đã xoá {p}')
        except OSError as e:
            print(f'[local] LỖI xoá {p}: {e}')
    for k in KV_KEYS:
        try:
            remote_delete(k)
            print(f'[KV] đã xoá {k}')
        except Exception as e:  # noqa: BLE001
            print(f'[KV] bỏ qua {k}: {type(e).__name__} (KV tắt/không với tới?)')
    print('\nXong. Khởi động lại app -> scan đầu sẽ dựng lại Bug Log từ Jira.')
    return 0


if __name__ == '__main__':
    sys.exit(main('--yes' in sys.argv[1:]))
