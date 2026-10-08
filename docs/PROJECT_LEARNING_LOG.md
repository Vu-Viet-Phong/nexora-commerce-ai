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

## 6. Milestone 2.4 — Test isolation and runtime optimization

The PostgreSQL integration tests previously shared the `public` schema. The
schema test and loader test both dropped the same four tables, while the marts
test read whichever state a previous test left behind. That made the result
depend on collection order and could leave the test database in an empty
sentinel-like state. The database was not changing because of a business-metric
calculation; it was being changed by destructive test setup.

Schema integration tests now use a per-test PostgreSQL schema and never drop
objects in `public`. The loader accepts an explicit schema for this test-only
namespace, and the full-data loader and marts tests each create their own
schema and load their own source before asserting metrics. This removes the
ordering dependency without changing the production database or metric logic.

The complete Parquet and PostgreSQL reconciliation tests are marked
`full_data` and are skipped by default. Run them deliberately with
`pytest --run-full-data`; ordinary unit tests continue to use small,
deterministic in-memory fixtures. This keeps the 1,044,848-row load out of
normal feedback loops while preserving a separate, explicit reconciliation
path for release verification.

Measured runtimes in this environment:

- Default unit/schema group: 16 passed, 6 skipped in 2.79 seconds.
- Full-data loader/idempotency group: 1 passed in 609.86 seconds.
- Full-data marts reconciliation group: 1 passed in 194.82 seconds.

The loader is the main bottleneck because it prepares and copies the complete
dataset and repeats the load for idempotency and rollback checks. Marts
reconciliation is the second bottleneck because it builds all three views over
the full fact table. Neither group is suitable for every local test cycle.

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

---

## Milestone 2.1 — PostgreSQL Development Environment

### Objective

Tạo môi trường PostgreSQL reproducible cho Stage 2 mà không yêu cầu mỗi
developer phải tự cài PostgreSQL theo cách riêng.

### Why This Matters

Stage 2 cần một database thật để kiểm tra schema, foreign key, transaction,
loader idempotency và SQL marts. Docker Compose mô tả database bằng code, giúp
những lần chạy sau dùng cùng image, port, biến môi trường và healthcheck.

### Input

- Cấu hình project hiện có trong `pyproject.toml`.
- Các biến môi trường PostgreSQL do developer cung cấp qua `.env`.

### Output

- `deployment/docker-compose.yml` với PostgreSQL 16 và named volume.
- `.env.example` với placeholder cho database configuration.
- Dependencies `SQLAlchemy` và `psycopg[binary]`.

### Files Created / Modified

- `deployment/docker-compose.yml`: định nghĩa service PostgreSQL,
  healthcheck, port mapping và persistent development volume.
- `.env.example`: ghi lại tên biến cần thiết, không chứa secret thật.
- `pyproject.toml`: khai báo SQLAlchemy và psycopg cho database access ở các
  milestone sau.
- `docs/PROJECT_LEARNING_LOG.md`: ghi lại design và validation của milestone.

### Concepts Learned

- **Relational database**: database lưu dữ liệu trong các bảng có quan hệ
  logic, phù hợp để biểu diễn customers, invoices và invoice lines ở Stage 2.
- **PostgreSQL**: hệ quản trị cơ sở dữ liệu quan hệ được chọn cho môi trường
  phát triển và các constraint SQL thực tế.
- **Docker Compose**: file YAML mô tả một hoặc nhiều container có thể khởi tạo
  bằng cùng một cấu hình, làm môi trường local reproducible hơn.
- **DATABASE_URL**: chuỗi kết nối tập trung thông tin driver, user, password,
  host, port và database để code không hard-code connection details.
- **Environment variables**: cấu hình runtime tách khỏi source code. Password
  thật chỉ nằm trong `.env` local và `.env` bị gitignore; `.env.example` chỉ
  dùng để hướng dẫn tên biến.

### Implementation

Flow:

`.env` hoặc defaults local → Docker Compose interpolation → PostgreSQL
container → healthcheck `pg_isready` → các milestone schema/loader sau.

Service dùng `postgres:16`, map `POSTGRES_DB`, `POSTGRES_USER` và
`POSTGRES_PASSWORD`, đồng thời lưu database vào named volume
`postgres_data`. Healthcheck tránh coi container là ready trước khi server
nhận connection.

SQLAlchemy là database toolkit Python; psycopg là PostgreSQL driver. Chúng
được khai báo ngay từ foundation để các milestone sau dùng cùng dependency
stack thay vì thêm framework ORM không cần thiết.

### Important Code

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
```

Compose dùng `$$` để truyền biến vào shell bên trong container thay vì
interpolate sớm ở phía Compose. Vì vậy healthcheck kiểm tra đúng credentials
runtime của service.

### Design Decisions

Decision: dùng PostgreSQL 16 và named volume, thay vì commit database files.

Reason: image version được ghim ở major version để môi trường ổn định, còn
volume giữ dữ liệu local giữa các lần restart.

Trade-off: volume local cần được xóa thủ công khi muốn recreate database từ
scratch; volume không được đưa vào Git.

Decision: yêu cầu các biến PostgreSQL từ `.env` hoặc environment bên ngoài.

Reason: Compose không chứa username/password mặc định, tránh biến cấu hình
trông giống secret bị hard-code. `.env.example` chỉ cung cấp giá trị mẫu để
developer copy và thay đổi khi cần.

### Problems Encountered

Docker CLI không có trong environment hiện tại, nên không thể khởi động
container, chạy `docker compose config` hoặc chạy connection check thực tế
trong milestone này.

### Root Cause

`docker --version` và `docker compose version` đều thất bại vì lệnh `docker`
không tồn tại trên PATH của máy hiện tại.

### Solution

Đã kiểm tra nội dung Compose tĩnh và ghi nhận Docker runtime là prerequisite
còn thiếu. Compose file dùng biến bắt buộc, healthcheck và environment-driven
settings để có thể verify runtime khi Docker được cài.

### Why The Solution Works

Compose schema này chỉ có một PostgreSQL service, không phụ thuộc vào
host-specific path và không lưu secret trong repository. Khi Docker khả dụng,
`docker compose config` kiểm tra interpolation, còn `docker compose up -d`
và `pg_isready` kiểm tra runtime readiness.

### Tests / Validation

- Interpreter system ban đầu: Python 3.9.2; `.venv` cũ cũng là Python 3.9.2.
- Python 3.11.16 được xác nhận trong `vbpr_env`; không xóa hoặc sửa
  environment thesis.
- `.venv` đã được tái tạo project-specific bằng Python 3.11.16.
- `.\.venv\Scripts\python.exe -m pip install -e '.[dev]'` hoàn tất từ
  `pyproject.toml`.
- Import `pandas`, `numpy`, `pyarrow`, `sqlalchemy`, `psycopg`, `pytest`:
  PASS.
- `.\.venv\Scripts\python.exe -m pytest tests/test_data/test_stage1.py`:
  **7 passed**.
- `.env.example` chỉ chứa giá trị mẫu, không chứa secret thật; `.env` vẫn
  bị gitignore.
- Đã kiểm tra `docker --version` và `docker compose version`; runtime
  verification bị block vì Docker chưa được cài.

### How To Run

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f deployment/docker-compose.yml config
docker compose --env-file .env -f deployment/docker-compose.yml up -d
docker compose --env-file .env -f deployment/docker-compose.yml ps
```

### How To Verify

Khi Docker khả dụng, service phải ở trạng thái healthy:

```powershell
docker compose --env-file .env -f deployment/docker-compose.yml ps
docker compose --env-file .env -f deployment/docker-compose.yml exec postgres \
  pg_isready -U $env:POSTGRES_USER -d $env:POSTGRES_DB
```

### Git Checkpoint

Commit: pending

Message: `feat(db): add PostgreSQL development environment`

### What I Learned

Database environment cũng là một phần của reproducible data system. Tách
configuration khỏi code và có healthcheck giúp các bước schema/loader sau
phát hiện database chưa sẵn sàng một cách rõ ràng.

### Limitations

Milestone này chưa tạo schema, chưa load Parquet và chưa kiểm tra connection
thực tế vì Docker runtime không khả dụng.

### Next Step

Milestone 2.2 sẽ xác định grain của từng bảng và tạo PostgreSQL schema, PK/FK,
indexes cùng ERD dựa trên dữ liệu Stage 1 thực tế.

## Milestone 2.1 — Database Foundation Review Checkpoint

Milestone 2.1 đã được Gravity review và **APPROVED**. PostgreSQL
development foundation, environment-variable separation, persistent volume,
healthcheck và Stage 1 regression coverage đã được kiểm tra. Các tài liệu
review và acceptance checklist trong `docs/` được giữ làm evidence cho
Milestone 2.2.

### Checkpoint Decision

Milestone 2.2 được phép bắt đầu từ repository hiện tại. Schema phải được
thiết kế từ `data/processed/transactions_clean.parquet` thực tế, không sửa
processed data và không giả định lại các kết quả đã được Stage 1 xác nhận.

## Milestone 2.2 — Relational Schema & Grain Design

### Concepts

- **Relational database:** Lưu dữ liệu trong các bảng có cấu trúc và quan hệ
  được kiểm soát bằng khóa, constraint và transaction thay vì chỉ dựa vào
  quy ước trong file.
- **Grain:** Mức chi tiết mà một row đại diện. Grain phải được chốt trước khi
  viết SQL; nếu không, aggregate có thể đếm hoặc cộng cùng một sự kiện nhiều
  lần.
- **Primary key:** Định danh duy nhất một row trong bảng. Schema dùng
  composite business keys có `source_system` cho customers, products và
  invoices; `invoice_lines` dùng `line_id` nội bộ.
- **Foreign key:** Ràng buộc tham chiếu bảo đảm invoice line trỏ tới invoice,
  product và customer hợp lệ. Customer FK nullable để giữ guest transactions.
- **Surrogate/internal key:** `line_id` là identity key nội bộ, không dùng
  `StockCode` làm line key vì một product xuất hiện trên nhiều lines.
- **Normalization:** Tách customer, product, invoice header và invoice line
  để giảm lặp thuộc tính, trong khi các cờ và measures vẫn ở line grain.
- **Cardinality:** Một customer có nhiều invoices và lines; một invoice có
  nhiều lines; một product có nhiều lines. Đây là các quan hệ 1:N và chiều
  ngược lại là N:1.
- **Fact vs dimension:** `invoice_lines` và `invoices` là transaction facts;
  `customers` và `products` là descriptive dimensions. Schema hiện tại ưu
  tiên core relational foundation, chưa tạo marts.
- **Nullable field:** `customer_id` nullable vì 235,287 processed lines thiếu
  Customer ID. Không tạo dummy customer và không silent-drop các lines này.
- **NUMERIC vs FLOAT:** Money dùng `NUMERIC(12,2)`/`NUMERIC(14,2)` để tránh
  sai số binary floating point; không dùng FLOAT, REAL hoặc DOUBLE PRECISION.
- **Index:** Chỉ tạo index cho foreign-key/join columns và invoice date,
  tránh index mọi cột flag gây write overhead không cần thiết.
- **Source namespace:** `source_system` nằm trong identity/FK để UCI, MMRec và
  Amazon có thể cùng tồn tại mà không trộn invoice hoặc stock code trùng tên.
- **Join fan-out:** Join phải theo đúng composite key và đúng grain. Join
  thiếu source namespace hoặc join dimension không unique có thể nhân số row.
- **Revenue nhân do sai grain:** Nếu invoice header bị join với nhiều lines
  rồi tổng header amount, cùng một invoice amount sẽ được lặp theo số lines.
  Vì vậy revenue line-level phải aggregate từ `invoice_lines`, còn header
  amount phải được aggregate ở invoice grain.

### Nexora decisions

Processed schema thực tế có 25 columns và 1,044,848 rows. Các grain được cố
định như sau:

- `customers`: một row cho mỗi identified `Customer ID` trong một
  `source_system`; 5,942 customer IDs; missing IDs không tạo dimension row.
- `products`: một row cho mỗi normalized `StockCode` trong một
  `source_system`; 5,131 stock codes; special/non-product codes vẫn được
  biểu diễn để không mất ledger provenance.
- `invoices`: một row cho mỗi `Invoice` trong một `source_system`; 53,628
  invoice headers; `invoice_date` dùng timestamp nhỏ nhất khi một invoice có
  nhiều timestamp.
- `invoice_lines`: một row cho mỗi retained processed transaction line,
  gồm cancellation, return, inventory adjustment, bad debt, non-product và
  duplicate flags; không silent-drop ambiguity.

`source_line_key` là stable source-level identifier do loader tạo từ source
namespace, source sheet và deterministic source row ordinal. `line_id` chỉ là
internal identity và không thay thế source provenance. SHA-256, sheet và row
ordinal được lưu để truy nguyên file nguồn. `line_total` là generated
`NUMERIC` từ quantity và unit price; raw/processed Parquet không bị sửa.

Chi tiết lý thuyết, ví dụ SQL, kiểm thử static/integration và các giới hạn
runtime của Milestone 2.2 được ghi tại
[`docs/learning/stage_02_postgresql_sql.md`](learning/stage_02_postgresql_sql.md).
Static tests và processed-source reconciliation đã chạy. PostgreSQL 16 native
trên Windows cũng đã được xác minh qua SQLAlchemy và `psycopg` với database
test riêng `nexora_commerce_test`; Docker không được tiếp tục troubleshoot
trong milestone này.

Integration test tự đọc `.env` trong process Python, vì vậy không phụ thuộc
environment của terminal khác. Test apply `sql/schema.sql`, kiểm tra metadata
PK/FK/UNIQUE, indexes và NUMERIC, rồi kiểm tra NULL customer, generated
`line_total`, invalid FK, duplicate source identity và savepoint rollback.
Kết quả runtime: **1 passed**.

Lỗi thực tế đầu tiên là password local có ký tự `@` chưa URL-encode, làm
hostname bị phân tích sai. Loader test chuẩn hóa giá trị đó mà không log
credential; cách cấu hình chuẩn vẫn là percent-encode ký tự đặc biệt trong
`.env`. Sau lỗi integrity, PostgreSQL cần rollback savepoint trước khi chạy
statement tiếp theo, nếu không sẽ báo `InFailedSqlTransaction`.

Database chính được kiểm tra read-only trước DDL: đúng `nexora_commerce` và
không có target tables. Sau đó schema được apply thành công với 4 tables;
không drop hoặc ghi đè dữ liệu hiện có. Full suite kết thúc **20 passed**.
Milestone 2.2 đã được review document xác nhận approved; Milestone 2.3 bắt
đầu sau checkpoint commit `36762ec`.

### Milestone 2.3 — PostgreSQL Data Loader

Loader trong `src/data/load.py` đọc Parquet immutable, chuẩn bị bốn grain
được phê duyệt, rồi bulk load bằng PostgreSQL `COPY FROM STDIN`. ETL tách rõ
extract/transform/load; database transaction cung cấp ACID, atomic commit và
rollback khi bất kỳ bước nào lỗi.

Idempotency dùng delete-and-reload có scope `source_system = 'UCI'`, không
dùng `TRUNCATE CASCADE`, nên không xóa namespace nguồn khác. Parent tables
được nạp trước fact table để giữ referential integrity. `source_sheet`,
`source_row_number`, `source_line_key` và SHA-256 giữ lineage; NULL customer,
cancellation, return, inventory adjustment, bad debt và special StockCode
được giữ nguyên.

Kết quả test thực tế trên `nexora_commerce_test`:

- customers: 5,942
- products: 5,131
- invoices: 53,628
- invoice_lines: 1,044,848
- NULL customer IDs: 235,287
- valid-sale SQL total theo NUMERIC schema: 19,700,954.44
- physical-return SQL total: -719,692.94
- loader integration: **1 passed in 606.08s**
- full suite trước loader: **20 passed**
- full suite sau loader: **21 passed in 621.09s**
- main database loader: **188.25s**

Chạy loader lần hai cho cùng kết quả counts, không nhân đôi. Test lỗi cố ý
sau COPY cũng rollback toàn bộ và giữ lại state hoàn chỉnh trước đó. Chênh
0.02 giữa valid-sale Parquet float aggregate (19,700,954.46) và SQL
19,700,954.44 là do schema bắt buộc `unit_price NUMERIC(12,2)` và generated
`line_total` làm tròn phép nhân ở database; đây là khác biệt contract được
ghi rõ, không phải mất dòng.

Milestone 2.4 chưa bắt đầu; loader milestone dừng tại đây để Antigravity
review.

### Milestone 2.4 — SQL Analytics Marts

Milestone 2.4 adds three reproducible PostgreSQL views:

- `mart_daily_sales`: `(calendar_day, country, is_physical_merchandise)`.
- `mart_customer_daily`: `(customer_id, calendar_day)`, excluding NULL
  customer IDs from customer analytics.
- `mart_customer_snapshot`: one row per 5,942 identified customers with
  recency, distinct-invoice frequency, net monetary value, AOV and tenure.

The mart SQL separates the OLTP relational core from an OLAP read layer.
Canonical invoice header dates prevent one invoice from being split across
days. Composite source-scoped joins prevent cross-source matches, and the
tests check duplicate grain and reconciliation. Inventory adjustments and
non-product cancellations are excluded; physical returns remain negative
return value. Ninety identified customers have no valid sale and remain in
the snapshot with frequency zero.

Live test-database results using PostgreSQL NUMERIC arithmetic:

- 19,700,954.44 daily gross/valid-sale revenue
- -719,692.94 physical return value
- 18,981,261.50 net sales
- 39,516 distinct invoices
- 11,221,957 units sold and 469,882 units returned
- customer-level gross/net: 17,124,940.98 / 16,411,894.73
- 5,942 snapshot customers, including 5,852 with purchases and 90
  return-only/no-valid-sale customers

An initial test sentinel row inflated the daily total by 19.99 because the
view did not filter `source_system='UCI'`. The explicit source filter fixed
the root cause. The focused integration test then passed. EXPLAIN ANALYZE
showed hash joins, parallel scans and sort-to-temp as the current
bottleneck; no speculative index was added.

### Learning Notes (tiếng Việt) — đối soát và QA Milestone 2.4

Ba mart là lớp đọc OLAP trên bốn bảng lõi. `mart_daily_sales` có grain
`calendar_day + country + is_physical_merchandise`; `mart_customer_daily` có
grain `customer_id + calendar_day`; `mart_customer_snapshot` có đúng một row
cho mỗi customer đã nhận diện. Input là `invoice_lines`, ghép với `invoices`
để lấy ngày hóa đơn chuẩn và ghép `products` để lấy cờ hàng vật lý. Output là
các measure đã aggregate, không làm thay đổi fact tables.

Trong SQL, `WITH` tạo CTE để lọc input một lần; `JOIN` dùng cả
`source_system` và business key để không trộn namespace; `GROUP BY` bảo vệ
grain; `SUM` cộng tiền/quantity; `COUNT(DISTINCT invoice_number)` đếm order
thay vì đếm line; `CASE` và `FILTER (WHERE ...)` tách valid sale khỏi return;
`LEFT JOIN` trong snapshot giữ lại 5.942 customer, kể cả 90 customer không có
valid sale. `line_total` và kết quả tiền dùng PostgreSQL `NUMERIC`, không dùng
FLOAT, nên so sánh bằng `Decimal` là đúng metric contract.

Đối soát full-data xác nhận gross/valid revenue £19,700,954.44, physical
return -£719,692.94, net sales £18,981,261.50, 39.516 order, và
11.221.957/469.882 units sold/returned. Customer mart thấp hơn company mart
vì 235.287 line guest (`customer_id IS NULL`) không được gán vào RFM. Snapshot
đạt 5.852 customer có mua và 90 frequency bằng 0; nhóm return-only có thể có
monetary âm, nhưng AOV phải NULL.

QA kiểm tra thêm join đầy đủ `invoice_lines -> invoices -> products`: đúng
1.044.848 row, không fan-out, với ledger database £18,909,762.10. Parquet
audit là £18,909,762.12; chênh £0.02 là do cột generated
`ROUND(quantity::NUMERIC * unit_price, 2)` làm tròn từng line trước khi SUM,
không phải mất dữ liệu. Các invariant `net = gross + return`, kiểu
`pg_typeof(...) = numeric`, uniqueness của từng grain và source filter đều
được test trực tiếp.

Hai lỗi QA thực tế đã được sửa trong checkpoint này. Assertion ledger ban đầu
dùng tổng Parquet thay cho tổng database NUMERIC; assertion RFM ban đầu giả
định mọi frequency-zero customer có monetary bằng 0, trong khi return-only
customer hợp lệ có monetary âm. Cách khắc phục là tách rõ source-vs-database
contract và chỉ yêu cầu AOV NULL cho frequency zero.

Runtime đo được bằng `.venv` Python 3.11.16: regression suite **16 passed,
6 skipped trong 1.55s**; full-data mart reconciliation **1 passed trong
224.67s**. Test full loader không chạy lại ở checkpoint này; mart test tự tạo
schema UUID riêng, load trong namespace riêng rồi teardown `CASCADE`, nên
không đụng database/test schema của worktree khác.

### Stage 3 Analytics — Customer Analytics, EDA và Feature Engineering

Checkpoint `feat/customer-analytics` triển khai
[`src/analytics/customer_analytics.py`](../src/analytics/customer_analytics.py)
và tài liệu
[`docs/learning/customer_analytics_feature_engineering.md`](learning/customer_analytics_feature_engineering.md).
Feature query chỉ đọc `mart_customer_daily`, cắt theo `as_of_date`, aggregate
về đúng một row/customer rồi validate uniqueness, numeric finite values và
non-negative temporal metrics. Vì chỉ trả khoảng 5.942 customer rows về
Python, pipeline không load 1 triệu fact lines vào RAM.

Production output hiện chỉ có các feature đã có contract: recency,
frequency, monetary, AOV và tenure, cùng customer ID, country và reference
date. Distinct products, return frequency, purchase time activity và
spending variability được ghi nhận pending vì metric contract chưa định nghĩa
cửa sổ và denominator; chưa đưa vào ML output.

EDA read-only có đủ 10 nhóm: sales distribution, customer behavior, order
frequency, spending, product popularity, country, returns, missing customer
ID, temporal pattern và sparsity/long-tail. Kết quả thật trên
`nexora_commerce`: 5.942 feature rows, 10/10 EDA sections, customer
monetary £16,411,894.73, top-100 positive-monetary share 36.68%, missing
customer lines 235.287/1.044.848 và return value -£719,692.94.

Unit tests analytics **5 passed**; full suite trong worktree
**20 passed, 7 skipped trong 0.91s**. Read-only smoke test database thật
pass. Một lỗi SQL long-tail do ambiguous `frequency` đã được sửa bằng cách
bỏ join dư thừa và tính top-100 share trực tiếp trên CTE ranked. Không có
database write, customer artifact hoặc secret nào được commit.
