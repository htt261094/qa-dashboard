import os
import sys
import asyncio
import datetime
import argparse
import base64
import io
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload

# Xử lý tham số dòng lệnh
parser = argparse.ArgumentParser()
parser.add_argument('--cron', action='store_true', help='Chỉ chạy nếu hôm nay là ngày cuối tháng')
parser.add_argument('--month', type=int, default=None,
                    help='Tháng muốn gửi report (1-12). Năm tự lấy năm hiện tại. '
                         'VD: 6 -> 06/2026, 8 -> 08/2026 (sang 2027 thì 6 -> 06/2027). '
                         'Bỏ trống = tháng hiện tại (mặc định của trang).')
args = parser.parse_args()

# Xác định tháng target (MM/YYYY) nếu user truyền --month
TARGET_MONTH = None
if args.month is not None:
    if not (1 <= args.month <= 12):
        print(f"--month phải trong khoảng 1-12 (nhận: {args.month}).")
        sys.exit(1)
    TARGET_MONTH = f"{args.month:02d}/{datetime.date.today().year}"

if args.cron:
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    if tomorrow.day != 1:
        print("Hôm nay không phải ngày cuối tháng. Bỏ qua chạy cron.")
        sys.exit(0)

# Đọc file .env
load_dotenv()

JIRA_PORT = os.environ.get('JIRA_PORT', '8080')
URL = f"http://localhost:{JIRA_PORT}/analytics"

SPACE_ID = os.environ.get('GOOGLE_CHAT_SPACE_ID')
SERVICE_ACCOUNT_FILE = 'gcp-service-account.json'

from auth import make_session_token

async def main():
    print(f"Truy cập vào {URL} ...")
    
    # Tạo cookie phiên đăng nhập cho bot (bypass login)
    from config import ADMIN_EMAIL
    admin_email = ADMIN_EMAIL or 'admin@baokim.vn'
    session_token = make_session_token(admin_email)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # Inject cookie vào context
        await context.add_cookies([{
            'name': 'qa_session',
            'value': session_token,
            'domain': 'localhost',
            'path': '/'
        }])
        
        page = await context.new_page()
        
        try:
            await page.goto(URL)
            await page.wait_for_selector('#anMetricCharts', timeout=15000)

            # Nếu user chỉ định tháng -> đổi select rồi đợi chart re-render
            if TARGET_MONTH:
                options = await page.locator('#anMetricMonth option').evaluate_all(
                    'els => els.map(e => e.value)')
                if TARGET_MONTH not in options:
                    print(f"Tháng {TARGET_MONTH} không có trong danh sách. "
                          f"Các tháng khả dụng: {options}")
                    sys.exit(1)
                print(f"Chọn tháng report: {TARGET_MONTH}")
                await page.select_option('#anMetricMonth', TARGET_MONTH)

            # Đợi một chút để chart render xong animation (nếu có)
            await page.wait_for_timeout(2000)

            # Chặn sớm nếu tháng không có bug: chart rỗng -> nút export return sớm,
            # KHÔNG tạo download -> expect_download() sẽ treo tới timeout. Fail rõ ràng thay vì treo.
            charts_html = await page.locator('#anMetricCharts').inner_html()
            if 'an-empty' in charts_html or not charts_html.strip():
                month_disp = TARGET_MONTH or 'hiện tại'
                print(f"Tháng {month_disp} không có dữ liệu bug để export. Bỏ qua gửi report.")
                sys.exit(1)

            print("Đang click Export PDF...")
            # Bấm nút export và đợi file tải về
            async with page.expect_download() as download_info:
                await page.click('#anExportChart')
            
            download = await download_info.value
            
            # Lưu file vào thư mục reports
            os.makedirs('reports', exist_ok=True)
            file_name = download.suggested_filename
            file_path = os.path.join('reports', file_name)
            
            await download.save_as(file_path)
            print(f"Đã lưu báo cáo PDF tại: {file_path}")

            month_val = await page.locator('#anMetricMonth').input_value()
            
            # Khởi tạo Google Chat API Client và Drive API Client
            SCOPES = [
                'https://www.googleapis.com/auth/chat.bot',
                'https://www.googleapis.com/auth/drive.file'
            ]
            credentials = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
            chat = build('chat', 'v1', credentials=credentials)
            drive = build('drive', 'v3', credentials=credentials)
            
            from config import ADMIN_EMAILS
            viewer_emails = [os.environ.get('RECEIVER_EMAIL', 'phuongnm@baokim.vn')] + list(ADMIN_EMAILS)
            
            # Trích xuất ảnh Base64 từ JS
            img_b64 = await page.evaluate("window.__lastExportedImage")
            img_link = None
            if img_b64 and ',' in img_b64:
                b64_data = img_b64.split(',')[1]
                img_bytes = base64.b64decode(b64_data)
                img_stream = io.BytesIO(img_bytes)
                
                print("Đang upload Ảnh biểu đồ lên Google Drive...")
                media_img = MediaIoBaseUpload(img_stream, mimetype='image/png', resumable=True)
                img_file = drive.files().create(
                    body={
                        'name': f'Bug_Metric_{month_val}.png',
                        'parents': ['0AOuFd9ZsWbmkUk9PVA']
                    },
                    media_body=media_img,
                    fields='id, webViewLink',
                    supportsAllDrives=True
                ).execute()
                
                for email in viewer_emails:
                    if email:
                        try:
                            drive.permissions().create(
                                fileId=img_file.get('id'),
                                body={'type': 'user', 'role': 'reader', 'emailAddress': email},
                                sendNotificationEmail=False,
                                supportsAllDrives=True
                            ).execute()
                        except Exception as e:
                            print(f"Bỏ qua cấp quyền cho {email} (có thể đã là thành viên thư mục): {e}")
                img_link = img_file.get('webViewLink')

            # Upload PDF file
            print("Đang upload file PDF lên Google Drive...")
            media_pdf = MediaFileUpload(file_path, mimetype='application/pdf', resumable=True)
            pdf_file = drive.files().create(
                body={
                    'name': f'Bug_Metric_{month_val}.pdf',
                    'parents': ['0AOuFd9ZsWbmkUk9PVA']
                },
                media_body=media_pdf,
                fields='id, webViewLink',
                supportsAllDrives=True
            ).execute()
            
            for email in viewer_emails:
                if email:
                    try:
                        drive.permissions().create(
                            fileId=pdf_file.get('id'),
                            body={'type': 'user', 'role': 'reader', 'emailAddress': email},
                            sendNotificationEmail=False,
                            supportsAllDrives=True
                        ).execute()
                    except Exception as e:
                        print(f"Bỏ qua cấp quyền cho {email} (có thể đã là thành viên thư mục): {e}")
            pdf_link = pdf_file.get('webViewLink')

            # Chi tiết Reopen -> file Excel (dữ liệu bảng thuộc về spreadsheet: CTO tự lọc/sort,
            # file vài KB, chữ chuẩn tiếng Việt). PDF chỉ giữ biểu đồ (thứ vốn là ảnh).
            excel_link = None
            try:
                from bug_backlog import load_backlog
                from xlsx_export import build_xlsx
                exm, exy = month_val.split('/')
                ro2 = (load_backlog().get('chart', {}) or {}).get(f"{exy}-{exm}", {}).get('reopen')
                if ro2 and ro2.get('distinctTotal'):
                    # gộp per-dev detail -> 1 dòng / bug (dedup theo id, gộp tên dev cùng fix)
                    flat = {}
                    for dev_name, dd in (ro2.get('devs', {}) or {}).items():
                        for it in dd.get('detail', []) or []:
                            e = flat.setdefault(it.get('id', ''), {
                                'id': it.get('id', ''), 'summary': it.get('summary', ''),
                                'reopen': it.get('reopen', 0), 'fix': it.get('fix', 0), 'devs': []})
                            if dev_name not in e['devs']:
                                e['devs'].append(dev_name)
                            e['reopen'] = max(e['reopen'], it.get('reopen', 0))
                            e['fix'] = max(e['fix'], it.get('fix', 0))
                    rows = [[b['id'], ', '.join(b['devs']), f"{b['reopen']:g}", f"{b['fix']:g}",
                             ' '.join((b['summary'] or '').split())]
                            for b in sorted(flat.values(), key=lambda x: x['reopen'], reverse=True)]
                    headers = ['Bug ID', 'Dev', 'Số lần reopen', 'Số lần fix', 'Mô tả']
                    xlsx_bytes = build_xlsx(headers, rows, sheet_name=f"Reopen {exm}-{exy}",
                                            col_widths=[16, 14, 13, 12, 90], wrap=True)
                    print("Đang upload file Excel Reopen lên Google Drive...")
                    xlsx_file = drive.files().create(
                        body={'name': f'Reopen_Detail_{exm}_{exy}.xlsx',
                              'parents': ['0AOuFd9ZsWbmkUk9PVA']},
                        media_body=MediaIoBaseUpload(
                            io.BytesIO(xlsx_bytes),
                            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            resumable=True),
                        fields='id, webViewLink', supportsAllDrives=True).execute()
                    for email in viewer_emails:
                        if email:
                            try:
                                drive.permissions().create(
                                    fileId=xlsx_file.get('id'),
                                    body={'type': 'user', 'role': 'reader', 'emailAddress': email},
                                    sendNotificationEmail=False, supportsAllDrives=True).execute()
                            except Exception as e:
                                print(f"Bỏ qua cấp quyền Excel cho {email}: {e}")
                    excel_link = xlsx_file.get('webViewLink')
            except Exception as e:
                print(f"Bỏ qua file Excel Reopen (lỗi): {e}")

            print("Đang gửi tin nhắn Google Chat...")
            
            text_content = f"Kính gửi anh Phương,\n\nĐây là báo cáo Bug Metric tháng {month_val} từ hệ thống QA Workspace.\n\n"

            # Tồn đọng T-1 (bug tháng liền trước còn mở lúc chuyển tháng) — tách rõ nợ cũ vs mới.
            try:
                from bug_backlog import prev_month_backlog
                mm, yyyy = month_val.split('/')
                bl = prev_month_backlog(report_month=f"{yyyy}-{mm}")
                if bl.get('has_snapshot'):
                    text_content += (
                        f"🆕 *Bug mới phát sinh trong tháng*: {bl['new_count']}\n"
                        f"📌 *Bug tồn đọng từ T-1 ({bl['prev_month']})*: {bl['total']} "
                        f"(còn: {bl['still_open']}, đã xử lý: {bl['resolved']})\n\n"
                    )
            except Exception as e:
                print(f"Bỏ qua phần tồn đọng T-1 (lỗi tính): {e}")

            # Reopen: text = TÍN HIỆU (tỷ lệ tổng + trend T-1 + tỷ lệ theo dev + bug dội nhiều
            # lần). Chi tiết đầy đủ từng bug nằm trong file Excel đính kèm — Chat hẹp, không nhồi.
            try:
                from bug_backlog import load_backlog
                REPEAT_MIN = 2                        # bug bị dội >= n lần mới nêu đích danh
                DEV_WARN_PCT, DEV_WARN_MIN = 40, 5    # cờ ⚠️ dev tỷ lệ cao + đủ mẫu
                rmm, ryyyy = month_val.split('/')
                chart_all = load_backlog().get('chart', {}) or {}
                ro = chart_all.get(f"{ryyyy}-{rmm}", {}).get('reopen')
                if ro and ro.get('distinctTotal'):
                    total, distinct = ro.get('totalBugs', 0), ro.get('distinctTotal', 0)
                    pct = round(distinct / total * 100) if total else 0
                    # Trend so với T-1 (reopen giảm = tốt).
                    py, pmn = int(ryyyy), int(rmm) - 1
                    if pmn == 0:
                        py, pmn = py - 1, 12
                    pro = chart_all.get(f"{py:04d}-{pmn:02d}", {}).get('reopen') or {}
                    trend = ''
                    if pro.get('totalBugs'):
                        ppct = round(pro['distinctTotal'] / pro['totalBugs'] * 100)
                        diff = pct - ppct
                        if diff < 0:
                            trend = f" — giảm {abs(diff)}đ so với T{pmn} ({ppct}%) ✅"
                        elif diff > 0:
                            trend = f" — tăng {diff}đ so với T{pmn} ({ppct}%) ⚠️"
                        else:
                            trend = f" — ngang T{pmn} ({ppct}%)"
                    text_content += f"🔁 *Reopen tháng {month_val}*: {distinct}/{total} bug ({pct}%){trend}\n\n"
                    devs = ro.get('devs', {}) or {}
                    # Tỷ lệ reopen theo dev (lens chất lượng fix), xếp theo tỷ lệ giảm dần.
                    ranked = []
                    for name, d in devs.items():
                        nb = d.get('nb', 0)
                        if nb <= 0:
                            continue
                        denom = d.get('denom', 0) or 0
                        ranked.append((nb / denom if denom else 0, name, nb, denom))
                    ranked.sort(reverse=True)
                    if ranked:
                        text_content += "*Chất lượng fix theo dev* (tỷ lệ reopen):\n"
                        for r, name, nb, denom in ranked:
                            flag = ' ⚠️' if (round(r * 100) >= DEV_WARN_PCT and denom >= DEV_WARN_MIN) else ''
                            text_content += f"• *{name}*: {round(r * 100)}% ({nb:g}/{denom:g}){flag}\n"
                        text_content += "\n"
                    # Bug bị dội >= REPEAT_MIN lần (dedup theo id, gộp tên dev cùng fix).
                    repeats = {}
                    for name, d in devs.items():
                        for it in d.get('detail', []) or []:
                            if it.get('reopen', 0) >= REPEAT_MIN:
                                e = repeats.setdefault(it.get('id', ''),
                                                       {'reopen': it.get('reopen', 0), 'devs': []})
                                if name not in e['devs']:
                                    e['devs'].append(name)
                                e['reopen'] = max(e['reopen'], it.get('reopen', 0))
                    if repeats:
                        text_content += f"*Bug có số lượng reopen ≥{REPEAT_MIN}*: {len(repeats)}\n"
                        for bid, e in sorted(repeats.items(), key=lambda kv: kv[1]['reopen'], reverse=True):
                            text_content += f"• {bid} ({', '.join(e['devs'])}) — {e['reopen']:g} lần\n"
                    else:
                        text_content += f"✅ Không có bug nào reopen ≥{REPEAT_MIN} lần trong tháng.\n"
                    text_content += "\n_Chi tiết đầy đủ từng bug: xem file Excel đính kèm._\n\n"
            except Exception as e:
                print(f"Bỏ qua phần Reopen (lỗi tính): {e}")

            if img_link:
                text_content += f"📊 *Ảnh biểu đồ*: {img_link}\n"
            if pdf_link:
                text_content += f"📄 *File PDF*: {pdf_link}\n"
            if excel_link:
                text_content += f"📑 *File Excel chi tiết Reopen*: {excel_link}\n"
            text_content += "\n"
            text_content += "Trân trọng,\nHuỳnh Tuấn Thành"

            # Tạo tin nhắn đính kèm file
            message_body = {
                'text': text_content
            }

            # Gửi tin nhắn
            chat.spaces().messages().create(
                parent=SPACE_ID,
                body=message_body
            ).execute()
                
            print("✅ Gửi tin nhắn Google Chat thành công!")

        except Exception as e:
            print(f"Lỗi trong quá trình thao tác: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
