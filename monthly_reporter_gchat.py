import os
import sys
import asyncio
import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# Đọc file .env
load_dotenv()

JIRA_PORT = os.environ.get('JIRA_PORT', '8080')
WEBHOOK_URL = os.environ.get('GOOGLE_CHAT_WEBHOOK_URL', '')

async def main():
    if not WEBHOOK_URL:
        print("Lỗi: Chưa cấu hình GOOGLE_CHAT_WEBHOOK_URL trong file .env")
        sys.exit(1)

    url = f"http://localhost:{JIRA_PORT}/"
    print(f"Truy cập vào {url} ...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await page.goto(url, wait_until='networkidle')
            
            # Chờ bảng biểu đồ Metric xuất hiện
            await page.wait_for_selector('#blMetricCharts', timeout=15000)
            
            # Kiểm tra xem có nút Export không (nếu không có data, nút này vẫn render nhưng ta check theo logic)
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

            # Lưu ý quan trọng: Webhook Google Chat KHÔNG hỗ trợ đính kèm trực tiếp file (chỉ hỗ trợ Text/Card).
            # Do đó chúng ta bắn thông báo về Chat, và file thực tế được lưu trên ổ cứng Server (hoặc có thể setup gửi qua Email nếu muốn đính kèm).
            month_val = await page.locator('#blMetricMonth').input_value()
            
            message_text = (
                f"📊 *Báo cáo Bug Metric (Tháng {month_val})*\n"
                f"✅ File PDF biểu đồ đã được tự động xuất.\n\n"
                f"📄 *Đường dẫn file trên server*: `{file_path}`\n"
                f"🔗 *Xem trực tiếp tại Dashboard*: {url}\n\n"
                f"_Đây là tin nhắn tự động hàng tháng từ QA Dashboard Bot._"
            )
            
            print("Đang gửi thông báo lên Google Chat...")
            resp = requests.post(
                WEBHOOK_URL,
                json={"text": message_text}
            )
            if resp.status_code == 200:
                print("✅ Gửi thông báo Google Chat thành công!")
            else:
                print(f"❌ Lỗi khi gửi webhook: {resp.status_code} - {resp.text}")

        except Exception as e:
            print(f"Lỗi trong quá trình Auto Export: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
