# Nexora Commerce AI — Project Learning Log

## 1. Project Overview

Nexora Commerce AI là project E-Commerce Intelligence dùng dữ liệu giao dịch
Online Retail II để xây dựng nền tảng phân tích thương mại điện tử. Mục tiêu
dài hạn của project là đi từ data engineering và analytics đến machine
learning, recommendation, multimodal search, LLM, API, application và MLOps.

Tại thời điểm đóng Stage 1, project mới hoàn thành data foundation: audit,
ingestion, cleaning có giải thích, validation, tests và tài liệu. Các phần
sau Stage 1 chưa được implement và không được giả định là đã sẵn sàng.

## 2. Project Architecture

Luồng kiến trúc mục tiêu:

```text
Raw Data
→ Data Engineering
→ SQL
→ Analytics
→ ML
→ Recommendation
→ Multimodal Search
→ LLM
→ API
→ Application
→ MLOps
```

Stage 1 mới bao phủ phần đầu của Data Engineering. SQL, analytics, ML,
recommendation, multimodal search, LLM, API, application và MLOps là các
phần sau, chưa implement.

## 3. Project Structure

- `configs/`: nơi dành cho configuration dùng chung; Stage 1 chưa cần thêm
  configuration riêng.
- `data/`: dữ liệu theo lifecycle. `data/raw/` là nguồn bất biến,
  `data/interim/` là cache/snapshot trung gian, `data/processed/` là output
  đã được chuẩn hóa và flag.
- `docs/`: tài liệu project, audit và learning log.
- `notebooks/`: exploratory work và data audit; notebook audit đã execute là
  `notebooks/01_data_audit.ipynb`.
- `src/`: source code; Stage 1 nằm trong `src/data/`.
- `tests/`: test suite; fixture nhỏ cho data logic nằm trong
  `tests/test_data/`.

## 4. Environment & Tooling

Stage 1 được chạy bằng Conda environment `vbpr_env`, Python 3.11.16. Đây là
environment hiện tại dùng để verify, không phải cam kết rằng project đã có
project-specific `.venv` hoàn chỉnh.

Dependencies được khai báo trong `pyproject.toml`:

- Runtime: `pandas`, `numpy`, `openpyxl`, `pyarrow`.
- Development/test: `pytest`.

Jupyter notebook audit dùng kernel Python 3.11 của `vbpr_env`. Notebook dùng
`pathlib`, `pandas` và `numpy` theo yêu cầu audit. PyArrow cung cấp Parquet
engine; pytest chạy unit tests.

Git quản lý source và documentation. Repository hiện tại có remote GitHub và
branch chính là `main`. GitHub CLI có thể dùng cho các thao tác GitHub, nhưng
commit/push trong Stage 1 vẫn là Git operations thông thường.

## 5. Git & GitHub Setup

`git init` tạo local repository; `.gitignore` loại raw datasets, generated
Parquet, cache, secrets và các artifact không nên commit. Local history trước
Stage 1 có các commit khởi tạo project và cập nhật data ignore rules.

Các thao tác Git khác nhau:

- `git add`: đưa thay đổi vào staging area để chuẩn bị commit.
- `git commit`: ghi snapshot đã stage vào local history.
- `git push`: gửi commit local lên remote, ở đây là GitHub.
- `git pull`: lấy thay đổi từ remote và tích hợp vào local branch.

`main` là branch đang phát triển và được đồng bộ với `origin/main` tại thời
điểm bắt đầu checkpoint. Commit không phải là push; một thay đổi chỉ lên
GitHub sau khi push thành công.

## 6. Dataset

Dataset là UCI Online Retail II:

```text
data/raw/uci/online_retail_II.xlsx
```

Raw Excel được coi là immutable: pipeline chỉ đọc và không ghi đè. Dataset
không được commit vì kích thước lớn, không phù hợp source control, và raw
phải có thể được kiểm tra bằng checksum độc lập. `.gitignore` xác nhận
`data/raw/**` bị ignore.

Workbook thực tế có hai sheet:

- `Year 2009-2010`: 525,461 rows.
- `Year 2010-2011`: 541,910 rows.

Tổng raw là 1,067,371 rows với tám cột:
`Invoice`, `StockCode`, `Description`, `Quantity`, `InvoiceDate`,
`Price`, `Customer ID`, `Country`.

Date range thực tế là `2009-12-01 07:45:00` đến
`2011-12-09 12:50:00`. Hai sheet có vùng overlap, đặc biệt khoảng
`2010-12-01` đến `2010-12-09`, nên không thể concat mù quáng rồi coi mọi
record là độc lập.

## 7. Data Audit Milestone

Notebook `notebooks/01_data_audit.ipynb` đọc workbook thật trước khi cleaning.
Audit ghi nhận:

- Shape: hai sheet như trên, tổng 1,067,371 rows và 8 columns.
- `Invoice`, `StockCode`, `Description`, `Country` là object/string trong
  bản đọc; `InvoiceDate` là datetime; `Quantity`, `Price` là numeric;
  `Customer ID` bị đọc dạng float-backed do có missing.
- Missing `Customer ID`: 243,007 rows (22.767%).
- Missing `Description`: 4,382 rows (0.411%).
- Duplicate toàn bộ row: 12,133 rows (1.136718%).
- Quantity <= 0: 22,950 rows.
- Price <= 0: 6,207 rows.
- Invoice prefix `C`: 19,494 cancellation rows, 8,292 unique invoices;
  19,493 cancellation rows có Quantity âm.
- Dataset có Price bằng 0, Price âm, prefix `A`, special/non-product
  `StockCode`, outlier và tháng cuối không đầy đủ.

Audit không xóa hoặc sửa row. Kết quả này cho thấy data cleaning phải là
business-aware, không chỉ là drop null hoặc drop outlier.

Data audit phải xảy ra trước cleaning vì cleaning rules phụ thuộc schema,
missingness, duplicate pattern, overlap giữa sheet và ý nghĩa nghiệp vụ của
record. Nếu drop trước khi hiểu dữ liệu, có thể mất cancellation, inventory
adjustment hoặc giao dịch thiếu customer nhưng vẫn hữu ích cho tổng thể.
Audit cũng tạo baseline để validation sau cleaning có thể giải thích số dòng
đã giữ và số dòng đã loại.

## 8. Ingestion Milestone

`src/data/ingest.py` thực hiện:

```text
Raw Excel
→ pd.read_excel(..., sheet_name=None)
→ sheet-level cache
→ interim Parquet snapshot
```

`sheet_name=None` đảm bảo workbook được đọc trong một lần gọi pandas và tất cả
sheet được giữ riêng. Khi hợp nhất để audit/cleaning, `source_sheet` được thêm
để truy xuất nguồn record.

Loader tính SHA-256 raw file. Cache chỉ được reuse nếu checksum trong cache
manifest khớp checksum hiện tại; raw thay đổi sẽ làm cache stale và buộc
đọc lại. `raw_manifest.json` ghi source portable, filename, checksum, size,
sheet names, rows per sheet, total rows, columns, date min/max và timestamp.

Benchmark thực tế đã ghi nhận:

- Excel load benchmark từ notebook audit: khoảng 94.29 giây.
- Parquet cache load: khoảng 0.434 giây.
- Pipeline dùng cache: khoảng 7.145 giây.

Parquet nhanh hơn Excel trong workflow này vì Excel là workbook XML cần parse
sheet/cell và suy luận kiểu, còn Parquet là columnar binary format đã được
serialize cho analytics.

## 9. Cleaning Milestone

`src/data/clean.py` chuẩn hóa identifier, text, numeric fields và datetime,
đồng thời tạo quality/business flags.

Nguyên tắc chính:

- Không drop tất cả rows thiếu `Customer ID`; giữ lại và gắn
  `has_customer_id`.
- Không drop tất cả Quantity âm; cancellation và các nhóm khác có ý nghĩa
  khác nhau.
- Invoice prefix `C` được giữ và gắn `is_cancellation`.
- Negative Quantity non-C được giữ riêng; nhóm Price = 0 và thiếu customer
  được gắn `is_inventory_adjustment`.
- Price = 0 và Price < 0 có cờ riêng. Prefix `A` được gắn
  `is_bad_debt_adjustment`.
- Cross-sheet exact overlap được xử lý theo tám cột gốc; occurrence đầu tiên
  theo workbook order được giữ.
- Within-sheet duplicates chỉ detect/flag vì không có line-level unique
  identifier; không blindly drop.
- Special StockCode dùng classification list rõ ràng. Không dùng rule đơn
  giản “không bắt đầu bằng số = non-product”; code chưa chắc chắn được giữ và
  đánh dấu special/unknown khi phù hợp.

`REMOVE` hiện chỉ áp dụng cho exact cross-sheet duplicate. Các trường hợp
missing customer, missing description, return/cancellation, price issue và
within-sheet duplicate đều là `RETAIN + FLAG` để bảo toàn thông tin.

Kết quả thực tế sau cleaning:

- Raw rows: 1,067,371.
- Cross-sheet rows removed: 22,523.
- Processed rows retained: 1,044,848.
- Cancellations retained: 19,165.
- Inventory adjustments retained: 3,393.
- Bad debt adjustments retained: 6.
- Missing Customer ID retained: 235,287.
- Missing Description retained: 4,275.
- Within-sheet duplicate rows detected: 23,430.

## 10. Validation Milestone

`src/data/validate.py` bảo vệ pipeline khỏi:

- thiếu required schema;
- thiếu `source_sheet` hoặc expected flags;
- datetime không hợp lệ;
- Quantity/Price không numeric;
- row count không reconcile với raw rows trừ cross-sheet duplicates;
- date range thay đổi ngoài ý muốn.

Pipeline còn đọc lại processed Parquet và chạy validation lần hai để kiểm tra
output integrity. Validation hiện tại pass với `is_valid: true`.

## 11. Pipeline Milestone

`src/data/pipeline.py` chạy flow thực tế:

```text
Excel
→ SHA-256 checksum
→ checksum-aware interim cache
→ transactions_raw.parquet
→ cleaning
→ validation
→ transactions_clean.parquet
→ cleaning_summary.json
```

Pipeline có tính idempotent ở ingestion: cùng raw checksum sẽ reuse cache,
còn raw thay đổi sẽ invalidate cache. Manifest và cleaning summary làm cho
source, row reconciliation và quyết định cleaning có thể reproduce/audit.

## 12. Testing Milestone

Tests trong `tests/test_data/test_stage1.py` dùng fixture nhỏ tự tạo, không
đọc toàn dataset:

- cross-sheet exact duplicate bị loại một bản;
- within-sheet duplicate được giữ và flag;
- required schema thiếu bị validation fail;
- checksum cache tạo và reuse manifest;
- cancellation prefix `C`;
- negative Quantity non-C;
- bad debt prefix `A`;
- inventory adjustment condition;
- missing customer/description được giữ và flag;
- Price = 0 và Price < 0;
- invalid datetime và missing expected flag bị phát hiện.

Kết quả cuối là **6 passed**. Đây không phải coverage toàn diện; chưa có
property-based test, distributed test, performance regression suite hay
integration matrix cho nhiều phiên bản Excel. Đây là limitation cần ghi nhận,
không nên gọi Stage 1 là đã test toàn diện.

## 13. Stage 1 Outputs

- `data/interim/raw_manifest.json`: portable source manifest và checksum.
- `data/interim/transactions_raw.parquet`: snapshot hợp nhất raw sheets có
  `source_sheet`, dùng để tránh parse Excel lại.
- `data/processed/transactions_clean.parquet`: normalized data cùng quality
  flags và `line_total`.
- `data/processed/cleaning_summary.json`: reconciliation, retained/removed
  counts, flags, validation và runtime metrics.

Các generated Parquet/cache không commit lên GitHub; chúng được tạo local từ
raw immutable và có thể regenerate.

## 14. Cleaning Decisions Needing Human Review

Các quyết định sau chưa được coi là approved:

1. Cross-sheet duplicate: giữ occurrence đầu tiên theo workbook order.
2. Inventory adjustment: `negative Quantity` + không phải cancellation +
   `Price = 0` + missing `Customer ID`.
3. Non-product classification: dùng danh sách special StockCode rõ ràng;
   code chưa chắc chắn không bị loại.
4. Within-sheet duplicate: detect/report nhưng chưa drop.

**STATUS: PENDING INDEPENDENT REVIEW**

Gravity đang review độc lập Data Quality và Cleaning Decisions. Không được
đánh dấu các rule này approved trước khi review hoàn tất.

## 15. Stage 1 Summary

### What was built

Checksum-aware ingestion, interim Parquet cache, raw manifest, type
normalization, explainable cleaning flags, cross-sheet overlap resolution,
validation, processed Parquet, cleaning summary, focused tests và tài liệu.

### What I learned

Excel raw data cần được profile trước khi chọn cleaning rule. Duplicate có thể
đến từ overlap giữa sheet hoặc lặp nghiệp vụ trong cùng sheet; hai trường hợp
không nên xử lý giống nhau. Missing identifier không tự động có nghĩa là row
vô dụng. Quality flags thường an toàn hơn silent deletion khi business meaning
chưa chắc chắn.

### Raw → processed flow

Raw workbook được checksum, đọc/cache, snapshot thành interim Parquet, sau đó
chuẩn hóa và flag. Exact cross-sheet repeats được loại có giải thích; phần
còn lại được validate và ghi processed Parquet.

### Important decisions

Giữ record có missing customer, giữ returns/cancellations, tách inventory và
bad debt, không drop within-sheet duplicates, và phân loại special StockCode
bảo thủ.

### Performance improvement

Excel benchmark khoảng 94.29 giây; cache load khoảng 0.434 giây; pipeline với
cache khoảng 7.145 giây. Đây là cải thiện thực tế cho các lần development sau.

### Tests

6 focused tests pass; full suite hiện có cùng kết quả. Tests nhỏ, deterministic
và không phụ thuộc toàn dataset.

### Known limitations

Chưa có line-level unique identifier; non-product classification vẫn cần
business review; test coverage chưa toàn diện; Stage 1 chưa có database,
analytics hoặc downstream customer modeling.

### Pending review decisions

Bốn cleaning decisions trong mục 14 có status **PENDING INDEPENDENT REVIEW**.

### Next Stage

**Stage 2 — PostgreSQL & Data Modeling**

**DO NOT START UNTIL STAGE 1 REVIEW IS APPROVED.**

## Stage 1 Independent Review Fixes

Independent review là một lần kiểm tra bởi reviewer khác với người viết
pipeline. Mục tiêu là tìm semantic bug và edge case mà unit tests ban đầu có
thể chưa bao phủ. Gravity kết luận Stage 1 **READY WITH CONDITIONS** và yêu
cầu ba điều chỉnh trước khi đóng review.

### 1. Tách customer return khỏi inventory adjustment

Quantity `< 0` không tự động có nghĩa là customer return. Review xác nhận
3,393 rows negative non-C có `Price = 0` và thiếu `Customer ID`, phù hợp với
warehouse shrinkage/write-off hơn là hành vi trả hàng của customer.

Vì vậy implementation hiện tại dùng:

- Invoice prefix `C` → `is_return = True`, `is_cancellation = True`,
  `is_inventory_adjustment = False`.
- Negative Quantity + non-C + `Price = 0` + missing Customer ID →
  `is_inventory_adjustment = True`, `is_return = False`.

Các rows vẫn được giữ lại. Điều này bảo vệ return-rate calculation khỏi việc
đếm nhầm write-off nội bộ như customer return.

### 2. Normalize StockCode trước classification

`StockCode` được chuyển sang nullable `string`, strip whitespace và uppercase
trước khi classification. Missing value vẫn là `<NA>`, không bị biến thành
literal `"NAN"`. Normalization giúp `test002`, `cRuK` và các biến thể có
whitespace được xử lý nhất quán.

### 3. Explicit special-code patterns

Classification không dùng rule nguy hiểm “StockCode không bắt đầu bằng số là
non-product”. Các code/pattern được review xác nhận được nhận diện explicit:

- `TEST002`
- `CRUK`
- `ADJUST2`
- prefix `GIFT_0001_...`

Product-like code như `DCGS0058` không bị loại chỉ vì có chữ. Đây là ví dụ
quan trọng cho việc classification phải dựa trên evidence và business
vocabulary, không dựa trên heuristic hình thức.

### 4. Regression testing và pipeline verification

Regression testing là chạy lại các behavior đã được chấp nhận sau khi sửa
implementation, để phát hiện bug mới hoặc metric thay đổi ngoài ý muốn.
Tests mới kiểm tra:

- C invoice âm là return nhưng không phải inventory adjustment;
- negative non-C zero-price thiếu customer là inventory adjustment nhưng không
  phải return;
- normal sale không có hai flag;
- StockCode mixed-case được uppercase;
- gift voucher pattern, `TEST002`, `CRUK`, `ADJUST2`;
- missing StockCode vẫn là nullable missing;
- `DCGS...` không bị đánh dấu non-product do heuristic.

Sau tests, pipeline được chạy lại từ checksum-valid Parquet cache thay vì đọc
Excel lại. Validation sau khi ghi và đọc lại processed Parquet phải pass,
row reconciliation và date range phải giữ nguyên. Thay đổi có chủ đích sau
fix là semantic count của `is_return`: nó không còn bao gồm 3,393 inventory
adjustments.

**Review status: CONDITIONS ADDRESSED — chờ reviewer xác nhận lại trước khi
bắt đầu Stage 2.**

## Stage 1 Final Approval

Independent Reviewer (Gravity) đã hoàn tất final re-review và kết luận:

**READY — STAGE 1 APPROVED**

Ba conditions đã được xử lý và xác nhận:

1. `is_return` chỉ phản ánh cancellation/customer return có invoice prefix
   `C`; negative non-C được tách thành `is_inventory_adjustment`.
2. `StockCode` được normalize thành nullable uppercase string trước
   classification, trong khi missing vẫn giữ là `<NA>`.
3. Special-code classification nhận diện explicit `GIFT_0001_*`, `TEST002`,
   `CRUK` và `ADJUST2`, đồng thời không dùng heuristic loại `DCGS...`
   product-like codes.

Final verification ghi nhận 7/7 tests pass, validation pass, row
reconciliation `1,067,371 - 22,523 = 1,044,848`, và processed Parquet reload
thành công. Raw checksum vẫn khớp manifest và raw Excel vẫn immutable.

Known limitations còn lại:

- Dataset không có line-level unique identifier; within-sheet duplicates
  tiếp tục được retain + flag.
- Special-code classification vẫn là business vocabulary cần review khi có
  thêm domain evidence.
- Stage 1 tests là focused tests, chưa phải exhaustive/property-based
  coverage.

Stage 1 được phép chuyển sang **Stage 2 — PostgreSQL & Data Modeling**.
Stage 2 phải tiếp tục theo workflow milestone: implement, verify, update log,
commit, push và xác nhận local `main` đồng bộ với `origin/main`.
