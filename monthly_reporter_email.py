import os
import sys
import asyncio
import smtplib
import datetime
import argparse
from email.message import EmailMessage
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# Xử lý tham số dòng lệnh
parser = argparse.ArgumentParser()
parser.add_argument('--cron', action='store_true', help='Chỉ chạy nếu hôm nay là ngày cuối tháng')
args = parser.parse_args()

if args.cron:
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    if tomorrow.day != 1:
        print("Hôm nay không phải ngày cuối tháng. Bỏ qua chạy cron.")
        sys.exit(0)

# Đọc file .env
load_dotenv()

JIRA_PORT = os.environ.get('JIRA_PORT', '8080')
SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
RECEIVER_EMAIL = os.environ.get('RECEIVER_EMAIL', '')

async def main():
    if not SMTP_USER or not SMTP_PASSWORD or not RECEIVER_EMAIL:
        print("Lỗi: Chưa cấu hình đủ thông tin Email (SMTP_USER, SMTP_PASSWORD, RECEIVER_EMAIL) trong file .env")
        sys.exit(1)

    url = f"http://localhost:{JIRA_PORT}/bug-log"
    print(f"Truy cập vào {url} ...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Bypass đăng nhập (nếu AUTH_ENABLED = True) bằng cách tự sinh session cookie
        from config import AUTH_ENABLED
        if AUTH_ENABLED:
            from config import ADMIN_EMAIL, SELF_USER, ALLOWED_DOMAIN
            from auth import make_session_token, SESSION_COOKIE
            email = ADMIN_EMAIL or f"{SELF_USER}@{ALLOWED_DOMAIN or 'test.com'}"
            token = make_session_token(email)
            await context.add_cookies([{
                'name': SESSION_COOKIE,
                'value': token,
                'domain': 'localhost',
                'path': '/'
            }])

        page = await context.new_page()

        try:
            await page.goto(url, wait_until='networkidle')
            
            # Chờ bảng biểu đồ Metric xuất hiện
            await page.wait_for_selector('#blMetricCharts', timeout=15000)
            
            # Kiểm tra xem có nút Export không
            export_btn = page.locator('#btnExportMetricChart')
            if await export_btn.count() == 0:
                print("Không tìm thấy nút Export, có thể chưa có dữ liệu trong tháng.")
                await browser.close()
                return

            print("Đang click Export PDF...")
            # Bắt sự kiện tải file sinh ra từ jsPDF trên UI
            async with page.expect_download(timeout=30000) as download_info:
                await export_btn.click()
            
            download = await download_info.value
            file_name = download.suggested_filename
            
            # Lưu file vào thư mục reports
            report_dir = os.path.join(os.path.dirname(__file__), 'reports')
            os.makedirs(report_dir, exist_ok=True)
            file_path = os.path.join(report_dir, file_name)
            
            await download.save_as(file_path)
            print(f"Đã lưu báo cáo PDF tại: {file_path}")

            month_val = await page.locator('#blMetricMonth').input_value()
            
            print("Đang gửi báo cáo qua Email...")
            
            from email.utils import make_msgid
            import base64
            
            msg = EmailMessage()
            msg['Subject'] = f"Báo cáo Bug Metric (Tháng {month_val})"
            msg['From'] = SMTP_USER
            msg['To'] = RECEIVER_EMAIL
            
            msg.set_content(
                f"Kính gửi anh Phương,\n\n"
                f"Em xin gửi file đính kèm báo cáo Bug Metric tháng {month_val} từ hệ thống QA Workspace.\n\n"
                f"Trân trọng,\n"
                f"Huỳnh Tuấn Thành"
            )
            
            image_cid = make_msgid()
            msg.add_alternative(f"""\
            <html>
              <body style="font-family: sans-serif; line-height: 1.5; color: #333;">
                <p>Kính gửi anh Phương,</p>
                <p>Em xin gửi biểu đồ và file đính kèm báo cáo Bug Metric tháng {month_val} từ hệ thống QA Workspace.</p>
                <p><img src="cid:{image_cid[1:-1]}" alt="Bug Metric Chart" style="max-width: 1000px; width: 100%; border: 1px solid #ddd; border-radius: 8px;"></p>
                <p>Trân trọng,<br>Huỳnh Tuấn Thành</p>
              </body>
            </html>
            """, subtype='html')
            
            # Trích xuất ảnh Base64 từ JS (vừa được gen ra cùng lúc với lúc export PDF)
            img_b64 = await page.evaluate("window.__lastExportedImage")
            if img_b64 and ',' in img_b64:
                b64_data = img_b64.split(',')[1]
                img_bytes = base64.b64decode(b64_data)
                # Đính kèm ảnh inline vào phần HTML
                msg.get_payload()[1].add_related(img_bytes, 'image', 'png', cid=image_cid)
            
            # Đính kèm thêm file PDF
            with open(file_path, 'rb') as f:
                pdf_data = f.read()
            msg.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=file_name)
            
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
                
            print("✅ Gửi email báo cáo thành công!")

        except Exception as e:
            print(f"Lỗi trong quá trình Auto Export/Send Email: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
