# Data Audit và Stage 1 cleaning

## Audit facts

Audit trên `data/raw/uci/online_retail_II.xlsx` ghi nhận:

- 2 sheet tương thích: `Year 2009-2010` (525,461 dòng) và
  `Year 2010-2011` (541,910 dòng).
- Tổng raw: 1,067,371 dòng, 8 cột; date range từ
  `2009-12-01 07:45:00` đến `2011-12-09 12:50:00`.
- Missing `Customer ID`: 243,007 dòng; missing `Description`: 4,382 dòng.
- Quantity <= 0: 22,950 dòng; Price <= 0: 6,207 dòng.
- Duplicate toàn bộ row: 12,133 dòng (1.136718%).
- Invoice prefix `C`: 19,494 dòng cancellation, 8,292 invoice khác nhau;
  19,493 dòng cancellation có quantity âm.

## Ingestion và manifest

Pipeline đọc workbook một lần bằng `pd.read_excel(..., sheet_name=None)`.
Raw Excel không bị ghi đè. Cache checksum-aware nằm trong
`data/interim/cache/`; `data/interim/raw_manifest.json` chỉ dùng đường dẫn
portable, không ghi absolute path máy cá nhân. Raw snapshot phục vụ các bước
sau nằm tại `data/interim/transactions_raw.parquet`.

## Cleaning decisions

- Chuẩn hóa kiểu dữ liệu và giữ lại mọi thông tin có thể.
- Deduplicate cross-sheet theo đúng 8 cột gốc, giữ bản đầu tiên theo thứ tự
  sheet. Pipeline đã loại 22,523 bản lặp cross-sheet.
- Duplicate trong cùng sheet không bị xóa; được gắn
  `is_duplicate_within_sheet`.
- Cancellation prefix `C` được giữ và gắn `is_cancellation`.
- Quantity âm ngoài prefix `C` không bị gộp vào customer return; nhóm âm,
  Price bằng 0 và thiếu customer được gắn `is_inventory_adjustment`.
- Prefix `A` được gắn `is_bad_debt_adjustment`.
- Price bằng 0 và Price âm được tách cờ riêng.
- Customer ID/Description thiếu được giữ lại và gắn cờ.
- Danh sách non-product rõ ràng gồm `POST`, `DOT`, `M`, `C2`, `D`, `S`,
  `BANK CHARGES`, `ADJUST`, `AMAZONFEE`, `GIFT VOUCHER`, `TEST001`.
  Code chưa chắc chắn không bị loại; được đánh dấu `is_unknown_special_code`
  khi phù hợp.

## Kết quả pipeline thực tế

| Metric | Value |
|---|---:|
| Raw rows | 1,067,371 |
| Cross-sheet rows removed | 22,523 |
| Rows retained / processed | 1,044,848 |
| Rows removed | 22,523 |
| Cancellations retained | 19,165 |
| Inventory adjustments retained | 3,393 |
| Bad debt adjustments retained | 6 |
| Missing Customer ID retained | 235,287 |
| Missing Description retained | 4,275 |
| Within-sheet duplicate rows detected | 23,430 |
| Price == 0 | 6,024 |
| Price < 0 | 5 |

Các metric pipeline phản ánh sau khi loại bản sao cross-sheet; metric audit
phía trên phản ánh raw workbook trước cleaning.

## Outputs

- `data/processed/transactions_clean.parquet`
- `data/processed/cleaning_summary.json`
- `data/interim/transactions_raw.parquet`
- `data/interim/raw_manifest.json`

Sau khi ghi processed Parquet, pipeline đọc lại file và chạy validation lần
nữa. Validation kiểm tra schema, cờ, numeric/datetime, row reconciliation,
source sheet và date range.

## Limitations

Không có line-level unique identifier nên duplicate trong cùng sheet chỉ là
phát hiện/flag, chưa thể kết luận là lỗi nghiệp vụ. Non-product codes được
phân loại bảo thủ; các code chưa chắc chắn không bị xóa. Việc chọn record
customer hợp lệ cho RFM/churn thuộc giai đoạn analytics sau, không nằm trong
Stage 1.
