# Report cuối tháng — số liệu Reopen Bug

Cách phần Reopen được đưa vào report tháng gửi CTO (Google Chat), sau các thay đổi 2026-07-15.

## Cấu trúc report (3 lớp, đúng medium)

| Lớp | Nội dung | Vì sao |
|---|---|---|
| **Chat text** | TÍN HIỆU: tỷ lệ reopen tổng + trend so với T-1 + tỷ lệ theo dev + bug reopen ≥2 lần | Sếp nắm nhanh trong 5 giây; không nhồi bảng dài vào Chat hẹp (tràn/cutoff) |
| **PDF** | Chỉ biểu đồ số lượng bug (ảnh) | Biểu đồ vốn là ảnh — hợp lý |
| **Excel** `Reopen_Detail_MM_YYYY.xlsx` | Chi tiết từng bug: Bug ID · Dev · Số lần reopen · Số lần fix · Mô tả | Dữ liệu bảng thuộc về spreadsheet — CTO tự lọc/sort, wrap text, vài KB |

File: [core/monthly_reporter_chat_app.py](../core/monthly_reporter_chat_app.py). Nguồn số = snapshot đã freeze `chart[YYYY-MM].reopen` trong [.bug_monthly.json](../core/bug_backlog.py) (`load_backlog`), KHÔNG gọi thêm Jira.

## Mẫu message Chat

```
🔁 Reopen tháng 07/2026: 23/117 bug (20%) — giảm 3đ so với T6 (23%) ✅

Chất lượng fix theo dev (tỷ lệ reopen):
• VietND: 62% (8/13) ⚠️
• PhucTV: 28% (7/25)
• VietBT: 24% (4/17)
• DucLV: 15% (3/20)
• DuongNT: 12% (1/8)

Bug có số lượng reopen ≥2: 3
• DA5-B2B-10 (VietND) — 2 lần
• DA5-B2B-15 (VietND) — 2 lần
• DA5-B2B-35 (VietBT) — 2 lần

Chi tiết đầy đủ từng bug: xem file Excel đính kèm.
```

## Cách tính (nguồn: `chart[ym].reopen` = `{totalBugs, distinctTotal, devs:{dev:{nb,fx,denom,detail}}}`)

- **Tỷ lệ tổng** = `distinctTotal / totalBugs`. **Trend** = so `distinctTotal/totalBugs` của tháng với T-1 (reopen giảm = tốt ✅).
- **Tỷ lệ theo dev** = `nb / denom` (bug bị reopen / tổng bug dev nhận), xếp giảm dần. Cờ ⚠️ khi `≥40%` và mẫu `≥5` (`DEV_WARN_PCT`/`DEV_WARN_MIN`).
- **Bug reopen ≥N** = bug có `detail.reopen ≥ REPEAT_MIN` (=2), dedup theo id, gộp tên dev.
- **Excel** = gộp `detail` toàn bộ dev → 1 dòng/bug (dedup id), sort theo số lần reopen giảm dần.

## Quy ước reopen (đừng đổi khi sửa report)

- **Carry lifetime qua sheet tháng** (case 2, user chốt): bug tồn đọng copy sang sheet tháng mới mà đang **Reopen** → số reopen ở tháng T = reopen chốt cuối T-1 + reopen mới trong T (định danh theo fingerprint nội dung). "N lần reopen" = tổng cả đời, quy về tháng dev đang xử lý. Code: `_seed_current_reopens`/`_count_reopens` trong [bug_log_store.py](../core/bug_log_store.py). Chuẩn tuyệt đối từ chu kỳ tháng sau khi bật (fingerprint stamp dần).
- **Full attribution**: bug nhiều dev → mỗi dev tính đủ 1 (số nguyên), không chia 1/n → `sum(denom)` có thể > `totalBugs`.
- **Số lần fix** = số lần reopen + 1 nếu bug đang Fixed/Closed (mỗi reopen = 1 lần fix bị trả lại).
- **Chỉ đếm bug còn trong file** (không type Bug / đã xoá / đổi sheet → bỏ).

## Trigger

```bash
python core/monthly_reporter_chat_app.py --month 7     # test 1 tháng
python core/monthly_reporter_chat_app.py --cron        # tự chạy cuối tháng (Scheduled Task)
```
Cần: app dashboard chạy ở `localhost:8080` + `gcp-service-account.json` (auth Google Chat/Drive) + bot service account đã ở trong space (`GOOGLE_CHAT_SPACE_ID`).

## Ranh giới

- Số reopen trước khi bật theo dõi / round-trip gọn trong 1 nhịp quét có thể sót (cận dưới).
- Tỷ lệ reopen dùng mẫu số RAW (đếm dòng), khác Valid Bug Rate (dedup fingerprint) — có chủ đích (Decision #47).
- Cần app chạy + ≥1 scan quanh cuối tháng để `chart[ym]` freeze sát mốc chuyển tháng.
