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
            
            # Đợi một chút để chart render xong animation (nếu có)
            await page.wait_for_timeout(2000)
            
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

            print("Đang gửi tin nhắn Google Chat...")
            
            text_content = f"Kính gửi anh Phương,\n\nĐây là báo cáo Bug Metric tháng {month_val} từ hệ thống QA Workspace.\n\n"
            if img_link:
                text_content += f"📊 *Ảnh biểu đồ*: {img_link}\n"
            if pdf_link:
                text_content += f"📄 *File PDF*: {pdf_link}\n\n"
            text_content += "Trân trọng,\nHuỳnh Tuấn Thành\n\n_(Lưu ý: File đã được cấp quyền truy cập an toàn cho email của anh)_"

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
