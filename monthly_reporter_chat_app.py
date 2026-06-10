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
URL = f"http://localhost:{JIRA_PORT}/bug-log"

SPACE_ID = os.environ.get('GOOGLE_CHAT_SPACE_ID')
SERVICE_ACCOUNT_FILE = 'gcp-service-account.json'

async def main():
    print(f"Truy cập vào {URL} ...")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(URL)
            await page.wait_for_selector('#blMetricCharts', timeout=15000)
            
            # Đợi một chút để chart render xong animation (nếu có)
            await page.wait_for_timeout(2000)
            
            print("Đang click Export PDF...")
            # Bấm nút export và đợi file tải về
            async with page.expect_download() as download_info:
                await page.click('#btnExportMetricChart')
            
            download = await download_info.value
            
            # Lưu file vào thư mục reports
            os.makedirs('reports', exist_ok=True)
            file_name = download.suggested_filename
            file_path = os.path.join('reports', file_name)
            
            await download.save_as(file_path)
            print(f"Đã lưu báo cáo PDF tại: {file_path}")

            month_val = await page.locator('#blMetricMonth').input_value()
            
            print("Đang tải file lên Google Chat...")
            
            # Khởi tạo Google Chat API Client
            SCOPES = ['https://www.googleapis.com/auth/chat.bot']
            credentials = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
            chat = build('chat', 'v1', credentials=credentials)
            
            # Trích xuất ảnh Base64 từ JS
            img_b64 = await page.evaluate("window.__lastExportedImage")
            attachment_img = None
            if img_b64 and ',' in img_b64:
                b64_data = img_b64.split(',')[1]
                img_bytes = base64.b64decode(b64_data)
                img_stream = io.BytesIO(img_bytes)
                
                media_img = MediaIoBaseUpload(img_stream, mimetype='image/png')
                print("Đang upload Ảnh biểu đồ...")
                attachment_img = chat.media().upload(
                    parent=SPACE_ID,
                    media_body=media_img
                ).execute()

            # Upload PDF file
            print("Đang upload file PDF...")
            media_pdf = MediaFileUpload(file_path, mimetype='application/pdf')
            attachment_pdf = chat.media().upload(
                parent=SPACE_ID,
                media_body=media_pdf
            ).execute()

            print("Đang gửi tin nhắn...")
            # Tạo tin nhắn đính kèm file
            message_body = {
                'text': f"Kính gửi anh Phương,\n\nĐây là báo cáo Bug Metric tháng {month_val} từ hệ thống QA Workspace.\n\nTrân trọng,\nHuỳnh Tuấn Thành",
                'attachment': []
            }
            
            if attachment_img:
                message_body['attachment'].append({
                    'attachmentDataRef': {
                        'resourceName': attachment_img['attachmentDataRef']['resourceName']
                    }
                })
                
            if attachment_pdf:
                message_body['attachment'].append({
                    'attachmentDataRef': {
                        'resourceName': attachment_pdf['attachmentDataRef']['resourceName']
                    }
                })

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
