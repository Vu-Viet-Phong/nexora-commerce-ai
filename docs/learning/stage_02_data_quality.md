# Stage 02 — Automated Data Quality & Validation

Tài liệu học tập này giải thích implementation Milestone 2.5 của Nexora Commerce AI.
Code thuộc `src/quality/`, tests thuộc `tests/test_quality/`; branch là
`feat/stage2-data-quality`. Bốn bảng được kiểm tra là `customers`, `products`,
`invoices`, `invoice_lines`. Tài liệu không xác nhận Milestone 2.5 APPROVED.

Các ví dụ chạy trong worktree riêng của Codex với Python 3.11 và dependencies của
project. Không chạy một lệnh pytest toàn repository trong phiên song song: fixtures
SQL cũ có thể nạp cấu hình và ghi vào database test dùng chung. Chỉ sử dụng các
phạm vi test được chỉ rõ bên dưới.

## Bản đồ implementation

| File | Vai trò thực tế |
|---|---|
| `src/quality/contracts.py` | Required columns, nullable columns, tiền NUMERIC, grain và 32 SELECT checks của core |
| `src/quality/frame.py` | Hàm offline kiểm tra missing, grain, FK, flags, cộng Decimal |
| `src/quality/engine.py` | Runner PostgreSQL read-only, repeatable-read, savepoint và timeout |
| `src/quality/source.py` | Đọc Parquet theo batches; đối soát counts, keys, flags, tiền, fingerprints, SHA-256 |
| `src/quality/results.py` | PASS/FAIL/SKIP, JSON, Markdown, summary và gate_summary |
| `src/quality/__main__.py` | CLI, process environment, exit codes và ghi report |
| `tests/test_quality/conftest.py` | Opt-in integration và database/schema riêng; không nạp .env |
| `tests/test_quality/test_core.py` | Catalog, query recovery, read-only orchestration, namespace, errors |
| `tests/test_quality/test_frame.py` | Logic validation offline với DataFrame nhỏ |
| `tests/test_quality/test_source.py` | Parquet fixtures, source contracts và fingerprints |
| `tests/test_quality/test_cli.py` | CLI configuration, reports, exit codes, redaction |
| `tests/test_quality/test_postgres.py` | SQL thật và CLI subprocesses trên sandbox riêng |

Nguồn xác lập contract là `sql/schema.sql`, `docs/data_dictionary.md`,
`src/data/clean.py`, `src/data/load.py` và các definitions trong tài liệu
Stage 2. Tài liệu metric cũ có benchmark tiền khác checklist 2.3; engine không
copy các số tiền đó làm expected cố định. Expected source được tính lại từ file
thực sự cung cấp, theo bước chuẩn hóa giá của loader.

## 1. Data Quality Dimensions

### 1.1 Định nghĩa và lý thuyết

Data quality là mức dữ liệu phù hợp với mục đích sử dụng và contract đã thống nhất.
Completeness hỏi trường bắt buộc có đủ không; uniqueness hỏi một entity/grain có
bị lặp không; integrity hỏi quan hệ có hợp lệ không. Business validity kiểm tra
các cờ nghiệp vụ; financial integrity kiểm tra tiền; source fidelity kiểm tra
dữ liệu đích còn phản ánh đúng dữ liệu nguồn sau các biến đổi được phê duyệt không.

Các dimensions bổ sung cho nhau. Một bảng đủ cột và không có NULL vẫn có thể
tham chiếu product không tồn tại. Một tổng tiền đúng vẫn có thể che giấu một
bản ghi bị mất và một bản ghi khác bị thêm với cùng giá trị.

### 1.2 Tại sao cần trong Data Engineering

Database constraints bảo vệ lúc INSERT nhưng không thay thế quality monitoring.
Schema có thể thay đổi, loader có thể ánh xạ nhầm field và report có thể cộng
sai tập giao dịch. Mỗi dimension đưa ra một câu hỏi rõ ràng để engineer biết
lỗi nằm ở cấu trúc, quan hệ, phân loại hay đối soát.

### 1.3 Ví dụ Nexora

Customer NULL được phép ở facts vì guest checkout vẫn là giao dịch thật.
Trong khi đó `quantity=NULL` là lỗi vì không tính được generated
`line_total`. Hai trường hợp đều là thiếu giá trị, nhưng khác contract.
Dòng có `quantity<0` không tự động lỗi: có thể là cancellation hoặc inventory
adjustment được giữ lại có chủ đích.

### 1.4 Code đã triển khai

`TABLE_COLUMNS`, `NULLABLE`, `MONEY_COLUMNS`, `GRAINS` và
`core_checks(schema)` trong `contracts.py` phân rã các dimensions thành
checks có tên, query và expected aggregate cụ thể.

```python
from src.quality.contracts import core_checks

checks = core_checks("public")
assert len(checks) == 32
assert any(check.name == "financial.invoice_ledger" for check in checks)
```

### 1.5 Giải thích từng bước

Hàm kiểm tra tên schema để tránh đưa input tùy ý vào SQL identifier. Sau đó nó
tạo qualified table names, đọc contract cột/grain, và sinh SELECT COUNT/SUM.
Mọi query dữ liệu sử dụng `:source` được bind khi thực thi. Các phép đếm lỗi
kỳ vọng bằng 0; dữ liệu hợp lệ vẫn được giữ nguyên.

### 1.6 Input và output

Input là tên schema hợp lệ. Output là danh sách 32 `Check`, không phải dữ liệu
khách hàng. Runner bổ sung catalog checks, source population, profile, Parquet
reconciliation và ba mart SKIP; vì vậy số result trong report lớn hơn 32.

### 1.7 Hướng dẫn chạy

```powershell
python -m pytest tests/test_quality/test_core.py -q
```

Trong suite, `test_queries_cover_core_contract_and_bind_namespace` xác nhận
checks có tên duy nhất, dùng bind parameter và không truy vấn marts.

### 1.8 Lỗi và cách khắc phục

Đếm NULL customer rồi coi tất cả là FAIL sẽ trái nullable contract. Đếm
Invoice + StockCode trùng rồi xóa sẽ trái line grain. Cách khắc phục là tra
DDL, cleaning và loader trước khi đặt expected; chỉ đánh giá lỗi theo contract
đã có, giữ số lượng edge cases dưới dạng profile.

### 1.9 Kiến thức rút ra

Chất lượng dữ liệu không đồng nghĩa với loại bỏ mọi dòng khác thường. Engineer
phải phân biệt lỗi contract với dữ liệu đặc biệt cần bảo toàn để đối soát ledger.

### 1.10 Câu hỏi ôn tập

1. Vì sao customer NULL và quantity NULL có kết quả khác nhau?
2. Vì sao row count bằng nhau chưa chứng minh dữ liệu nguồn và đích bằng nhau?
3. Dimension nào phát hiện được product reference sai dù tiền vẫn khớp?

## 2. Data Validation

### 2.1 Định nghĩa và lý thuyết

Validation là thực thi một điều kiện có expected, actual và kết luận rõ ràng.
PASS nghĩa điều kiện đã được kiểm tra và thỏa mãn; FAIL nghĩa sai hoặc không thể
thực thi check cần thiết; SKIP nghĩa chưa kiểm tra vì thiếu dependency/input.
SKIP không được đổi thành PASS để làm report đẹp hơn.

### 2.2 Tại sao cần trong Data Engineering

Validation chuyển câu nói “dữ liệu có vẻ ổn” thành tín hiệu máy đọc được.
Tên check giúp định vị lỗi; expected/actual giúp đo chênh lệch; duration giúp
phát hiện query chậm. Structured results cũng dùng được cho quality gate và CI.

### 2.3 Ví dụ Nexora

`source.records` kỳ vọng `missing=0, extra=0, changed=0`.
Nếu một row quantity bị sửa nhưng stable key vẫn giữ nguyên, actual có
`changed=1`. Nếu chưa cung cấp Parquet, source check là SKIP, không giả định
database đã đối soát đầy đủ.

### 2.4 Code đã triển khai

`ValidationResult`, `compare`, `skipped` trong `results.py` là nền tảng nhỏ;
không có plugin registry hoặc framework nội bộ.

```python
from decimal import Decimal
from src.quality.results import compare, skipped

result = compare("ledger", Decimal("0.30"), Decimal("0.31"))
assert result.status == "FAIL"
assert result.failure_reason is not None
pending = skipped("source.reconciliation", "No source supplied")
assert pending.status == "SKIP"
```

### 2.5 Giải thích từng bước

`compare` so expected với actual. Khi caller cung cấp tolerance Decimal,
hàm so độ lệch tuyệt đối với tolerance và từ chối tolerance âm. SQL core và
source monetary aggregates hiện dùng equality chính xác; API tolerance không
có nghĩa mọi check được tự động bỏ qua vài cent.

`run_query` mở savepoint, chạy SELECT, lấy scalar và tạo result. Nếu query
lỗi, savepoint được rollback, result FAIL dùng thông báo an toàn; exception gốc
không được đưa vào report vì có thể chứa SQL parameters hoặc connection info.

### 2.6 Input và output

Input là expected/actual aggregates hoặc một Check + connection + params.
Output có `name`, `expected`, `actual`, `status`, `execution_ms`,
`failure_reason`. Không có sample customer records trong output.

### 2.7 Hướng dẫn chạy

```powershell
python -m pytest tests/test_quality/test_core.py -q
python -m src.quality --help
```

### 2.8 Lỗi và cách khắc phục

Một SELECT lỗi trên PostgreSQL làm transaction vào trạng thái aborted. Nếu chỉ
catch exception rồi chạy SELECT tiếp, query sau cũng lỗi. Implementation dùng
`begin_nested()` để rollback check bị lỗi và tiếp tục snapshot. Integration
test `test_bad_query_recovers_in_savepoint_and_sanitizes_errors` xác nhận điều này.

### 2.9 Kiến thức rút ra

Error handling là một phần của correctness. Một runner cần báo lỗi đủ hiểu,
không lộ dữ liệu, và không biến các checks chưa thực hiện thành thành công.

### 2.10 Câu hỏi ôn tập

1. FAIL vì query lỗi khác SKIP vì thiếu input như thế nào?
2. Tại sao một savepoint giúp runner tiếp tục kiểm tra?
3. Vì sao không dùng `str(exception)` làm failure_reason?

## 3. Data Contracts

### 3.1 Định nghĩa và lý thuyết

Data contract mô tả cấu trúc, grain, nullable rules, kiểu tiền, lineage và
ý nghĩa nghiệp vụ. Contract được dùng chung giữa producer, database và consumer.
Một contract có ích phải ánh xạ tới cột và logic thực sự tồn tại.

### 3.2 Tại sao cần trong Data Engineering

Contract ngăn mỗi engineer tự định nghĩa doanh thu hoặc customer population.
Nó cũng làm schema drift có thể phát hiện tự động: đổi NUMERIC sang FLOAT,
đổi scale, hoặc chuyển nullable customer thành NOT NULL đều là thay đổi ý nghĩa.

### 3.3 Ví dụ Nexora

Grain lines là một retained row trong source sheet, không phải một product trong
invoice. Stable key là `(source_system, source_line_key)`; source position là
`(source_system, source_sheet, source_row_number)`. Row ordinal là thứ tự retained
rows của loader sau Stage 1, không phải số dòng Excel raw.

`is_valid_sale` bắt nguồn từ Stage 1:
không cancellation, không bad debt, quantity dương, giá gốc hợp lệ, không non-product.
Returns dùng `is_cancellation AND NOT is_non_product` khi cộng tiền hàng trả.

### 3.4 Code đã triển khai

`schema_results` đọc catalog PostgreSQL; `core_checks` đọc contract Python.
`KNOWN_NON_PRODUCT_CODES` và prefixes được import từ cleaning code hiện có.

```python
from src.quality.contracts import GRAINS, MONEY_COLUMNS, NULLABLE

assert GRAINS["customers"] == ("source_system", "customer_id")
assert "customer_id" in NULLABLE["invoice_lines"]
assert MONEY_COLUMNS[("invoice_lines", "unit_price")] == 12
```

### 3.5 Giải thích từng bước

Runner đọc `information_schema.columns` đúng schema và bốn bảng. Nó index
catalog theo table/column, tìm cột thiếu, kiểm nullable và các monetary columns.
Expected precision của unit_price là 12; các totals là 14; scale tất cả là 2.
Nếu thiếu required columns, các SQL phụ thuộc được SKIP để tránh loạt lỗi khó đọc.

### 3.6 Input và output

Input là catalog metadata hoặc rows từ fixture catalog nhỏ. Output có
`schema.required_columns`, `schema.nullability`, `financial.decimal_storage`.
Required-columns actual chỉ liệt kê tên cột thiếu trong contract, không dump
tất cả metadata hay dữ liệu bảng.

### 3.7 Hướng dẫn chạy

```powershell
python -m pytest tests/test_quality/test_core.py -q
python -m pytest --noconftest tests/test_sql/test_schema.py -q
```

Lệnh thứ hai chỉ chạy static DDL tests và không nạp conftest SQL cũ.

### 3.8 Lỗi và cách khắc phục

Tài liệu metric cũ dùng tên fact/dim và số tiền benchmark không trùng schema/
checklist mới. Implementation lấy tên thật trong DDL và tính expected từ source.
Một edge case khác: flags giá được tính trước rounding. Giá gốc 0.001 có thể
thành unit_price 0.00 nhưng vẫn has_valid_price=True. Source raw flags được
validate trước rounding; DB check tại giá zero kiểm partition của ba price flags.

### 3.9 Kiến thức rút ra

Contract cần giữ cả transform order, không chỉ tên cột. Khi documentation và code
có drift, phải ghi rõ bằng chứng và điều kiện đối soát; không âm thầm sửa benchmark
hoặc logic loader trong một milestone khác.

### 3.10 Câu hỏi ôn tập

1. Tại sao unit_price 0.00 chưa đủ suy ra giá gốc bằng zero?
2. Stable source key khác line_id như thế nào khi reload?
3. Vì sao không lấy benchmark tiền cũ làm expected cố định?

## 4. Completeness, Uniqueness và Referential Integrity

### 4.1 Định nghĩa và lý thuyết

Completeness kiểm sự hiện diện của fields bắt buộc. Uniqueness kiểm mỗi grain
chỉ có một row. Referential integrity kiểm child key có parent trong đúng
namespace. Composite key phải được so như một tuple; chỉ so customer_id hay
stock_code có thể trộn hai source systems.

### 4.2 Tại sao cần trong Data Engineering

Missing field làm transform thiếu input; duplicate grain làm tổng tiền bị
nhân đôi; orphan làm JOIN mất dòng. Cả ba có thể khiến dashboard sai mà query
vẫn chạy bình thường. JOIN cardinality là hệ quả trực tiếp của grain và FK.

### 4.3 Ví dụ Nexora

Hai dòng giống invoice/product/quantity có thể là retained POS duplicates,
nên vẫn hợp lệ nếu source positions khác nhau. Ngược lại hai dòng cùng stable
source key là duplicate grain. Một customer 123 tồn tại ở source UCI không làm
child source OTHER/customer 123 thành hợp lệ. Guest customer NULL không phải orphan.

### 4.4 Code đã triển khai

`missing_values`, `unique_grain`, `foreign_keys` là hàm offline;
core SQL dùng COUNT, GROUP BY/HAVING và NOT EXISTS.

```python
import pandas as pd
from src.quality.frame import foreign_keys, missing_values, unique_grain

parents = pd.DataFrame({"source_system": ["UCI"], "customer_id": [123]})
children = pd.DataFrame({
    "source_system": ["UCI", "OTHER", "UCI"],
    "customer_id": [123, 123, None],
})
result = foreign_keys(children, parents, ("source_system", "customer_id"),
                      nullable_key="customer_id")
assert result.actual == 1
assert unique_grain(parents, ("source_system", "customer_id")).status == "PASS"
assert missing_values(parents, ("source_system", "customer_id")).status == "PASS"
```

### 4.5 Giải thích từng bước

Missing helper kiểm required columns trước, rồi đếm rows có ít nhất một NULL
trong required fields. Unique helper đếm rows dư sau row đầu của từng grain.
FK helper bỏ nullable child key, tạo parent tuples và đếm tuples không tồn tại.
SQL dùng `parent.source_system=child.source_system` cùng business identifier.

Engine còn so row count trước và sau JOIN lines→invoices/products, LEFT JOIN
customers. Đây là check fanout/missing cardinality, kết hợp các uniqueness/FK
checks để không chỉ dựa vào một phép đếm có thể triệt tiêu lỗi.

### 4.6 Input và output

Input là DataFrames nhỏ hoặc schema PostgreSQL. Output là số vi phạm:
missing rows, duplicate surplus rows, orphan rows và row-count difference.
Report không đưa child key bị lỗi hay customer identifiers ra ngoài.

### 4.7 Hướng dẫn chạy

```powershell
python -m pytest tests/test_quality/test_frame.py -q
# Sau khi cấu hình dedicated database riêng:
python -m pytest tests/test_quality/test_postgres.py --quality-postgres -q
```

### 4.8 Lỗi và cách khắc phục

Test FK trên database có constraint thường bị chặn ngay lúc tạo orphan,
nên chưa kiểm được detector. Integration test chỉ trong sandbox riêng sẽ tháo
FK của invoice_lines rồi tạo orphan fixture; test duplicate tương tự tháo UNIQUE.
Schema này bị xóa trong finally. Không tháo constraints trên development DB.

### 4.9 Kiến thức rút ra

Một quality check cần kiểm cả trạng thái dữ liệu hiện tại, kể cả khi constraints
đã bị thay đổi. Việc dựng dữ liệu lỗi cho test phải giới hạn trong sandbox sở hữu.

### 4.10 Câu hỏi ôn tập

1. Khi nào hai invoice lines nhìn giống nhau vẫn hợp lệ?
2. Vì sao JOIN customer cần LEFT JOIN để giữ guest lines?
3. Có thể chứng minh integrity chỉ bằng tổng row count sau JOIN không?

## 5. Financial Reconciliation

### 5.1 Định nghĩa và lý thuyết

Reconciliation so sánh cùng một lượng tiền tính theo hai đường độc lập.
Nexora kiểm generated line total, invoice ledger, customer merchandise spend và
Parquet→PostgreSQL aggregates. Tiền dùng Decimal/NUMERIC, tránh cộng bằng float.
Equality chính xác và tolerance phải là quyết định của contract.

### 5.2 Tại sao cần trong Data Engineering

Sai vài cent có thể đến từ rounding order, không chỉ từ dữ liệu thiếu. Hai
implementation “quantity nhân price” vẫn khác nếu một bên làm tròn từng giá
trước khi nhân, còn bên kia cộng giá trị float gốc rồi mới round tổng.

### 5.3 Ví dụ Nexora

Loader dùng `Price.round(2)`, COPY dạng `%.2f`; PostgreSQL sinh
`ROUND(quantity::numeric * unit_price, 2)`. Source expectations tái hiện bước
đó và cộng Decimal. Header/customer loader đang aggregate source line_total
trước đó; nếu các totals này khác exact stored line totals, financial check
báo FAIL thay vì tự tăng tolerance.

Gross merchandise sales cộng lines is_valid_sale. Merchandise returns cộng
cancellation và không non-product. Net merchandise = gross + returns. Guest
sales vẫn trong company gross; guest NULL không thuộc customer dimension spend.

### 5.4 Code đã triển khai

`copy_money`, `source_expectations`, `monetary_total` và các SELECT
`financial.line_arithmetic`, `financial.invoice_ledger`,
`financial.customer_merchandise` thực hiện đối soát.

```python
from decimal import Decimal
from src.quality.frame import monetary_total
from src.quality.results import compare

total = monetary_total(["0.10", "0.20"])
assert total == Decimal("0.30")
assert compare("ledger", total, Decimal("0.31")).status == "FAIL"
```

### 5.5 Giải thích từng bước

Mỗi source batch giữ raw prices để validate flags. Sau đó Price được round(2),
chuyển sang dạng hai chữ số tương thích COPY và thành Decimal. Mỗi row có
Decimal total = quantity × unit_price; các tổng ledger/gross/returns được cập
nhật theo flags; cuối cùng net được tính từ gross + returns.

SQL line arithmetic so generated value với công thức exact. Invoice check
GROUP BY source/invoice, so số lines, quantity, amount và MIN timestamp với
header. Customer check GROUP BY source/customer, COUNT DISTINCT valid invoices
và cộng valid sales/physical returns theo metric contract.

### 5.6 Input và output

Input là source Parquet và bảng NUMERIC trong snapshot. Output là số invoices/
customers lệch và dictionary tiền aggregate. JSON lưu tiền dưới dạng string
như "8.00", để consumer không đưa money trở lại binary float.

### 5.7 Hướng dẫn chạy

```powershell
python -m pytest tests/test_quality/test_source.py tests/test_quality/test_frame.py -q
python -m pytest tests/test_quality/test_postgres.py --quality-postgres -q
```

Test monetary mismatch tăng totals lên 0.01 và xác nhận FAIL. Test edge case
giá ±0.001 xác nhận raw flags được bảo toàn và fingerprint xử lý negative zero.

### 5.8 Lỗi và cách khắc phục

Trong kiểm chứng, signed zero cần chuẩn hóa: COPY có thể đưa "-0.00" nhưng
PostgreSQL NUMERIC trả "0.00". Fingerprint dùng cùng biểu diễn zero.
Không làm tròn ledger floats rồi kết luận exact equality. Khi production report
báo header/customer mismatch, cần truy nguyên transform order ở milestone sở hữu
loader và xin quyết định contract; quality module chỉ phát hiện lỗi.

### 5.9 Kiến thức rút ra

“Tiền là Decimal” chưa đủ; rounding stage và nhóm giao dịch phải thống nhất.
Expected source phải phản ánh transform hợp lệ, đồng thời giữ checks đối soát
độc lập để phát hiện những tổng chưa đồng nhất.

### 5.10 Câu hỏi ôn tập

1. Vì sao sum raw line_total có thể khác sum stored NUMERIC line_total?
2. Tại sao returns non-product không được đưa vào merchandise return value?
3. Khi totals lệch, vì sao quality engine không tự sửa loader?

## 6. Unit Testing và Integration Testing

### 6.1 Định nghĩa và lý thuyết

Unit tests kiểm logic nhỏ bằng input deterministic, không cần service thật.
Integration tests kiểm các thành phần phối hợp, đặc biệt SQL dialect, NUMERIC,
transaction semantics, generated columns, streaming cursor và CLI→database.
Một suite offline PASS không chứng minh PostgreSQL queries đều thực thi đúng.

### 6.2 Tại sao cần trong Data Engineering

Unit tests giúp phản hồi nhanh khi sửa rules/results. Integration tests bắt lỗi
adapter và database mà mock không mô phỏng: ANY(array), FILTER, BOOL_OR,
IS DISTINCT FROM, schema catalog và savepoint recovery đều cần SQL thật.

### 6.3 Ví dụ Nexora

`test_invalid_foreign_keys_are_source_scoped_and_null_guests_are_allowed`
dùng DataFrame ba rows. `test_orphan_product_detected` tạo orphan ở schema riêng
và chạy SELECT thực tế. `test_cli_end_to_end_reports_and_exit_codes` khởi động
Python subprocess, ghi JSON/Markdown, so stdout với file và kiểm exit code.

### 6.4 Code đã triển khai

Options `--quality-postgres`, `--quality-full-data` cùng markers ở quality
conftest làm integration/full-data opt-in. Fixture chỉ chấp nhận database tên
`nexora_quality_codex_test`, verify current_database, tạo schema
`codex_quality_<uuid>`, cài DDL và load fixture nhỏ bằng loader hiện có.

```python
from src.quality.contracts import Check
from src.quality.engine import run_query

# run_query được test bằng fake connection trong unit suite;
# integration suite dùng cùng hàm trên PostgreSQL và savepoint thật.
check = Check("example.zero_violations", "SELECT 0")
assert check.expected == 0
```

### 6.5 Giải thích từng bước

Mặc định collection gắn SKIP cho tests cần PostgreSQL. Khi bật --quality-postgres,
fixture đọc duy nhất process variable NEXORA_QUALITY_TEST_DATABASE_URL,
không nạp file .env. Nó kiểm database identity trước CREATE SCHEMA, tạo schema,
load synthetic fixture, yield sandbox, rồi DROP đúng schema trong finally.
Full-data test chỉ mở khi caller bật cả hai options và cung cấp source path.

Lần kiểm chứng dùng PostgreSQL 16.15 instance tạm chỉ bind loopback port 59165,
tách khỏi native development service port 5432. Database/schema đều do Codex
sở hữu; tests không reset database development và không sửa mart objects.

### 6.6 Input và output

Offline input là fixtures/mocks. Integration input là process-configured private
database và schema mới. Output là pytest passed/failed/skipped cùng reports từ CLI.
Full-data test không chạy mặc định, cũng không được gọi chỉ vì Parquet có sẵn.

### 6.7 Hướng dẫn chạy

```powershell
# Offline; không cần database:
python -m pytest tests/test_quality tests/test_data -q
# DATABASE_URL test phải là instance/database riêng bạn sở hữu.
# Inject NEXORA_QUALITY_TEST_DATABASE_URL qua process configuration.
python -m pytest tests/test_quality --quality-postgres -q
# Chỉ khi chủ động cho phép full-data và có NEXORA_QUALITY_SOURCE:
python -m pytest tests/test_quality --quality-postgres --quality-full-data -q
```

Không chạy integration lên một database mang tên đúng nhưng thực tế do team
khác quản lý. Kiểm database name là guard bổ sung; ownership của instance vẫn
là điều kiện vận hành phải đảm bảo.

### 6.8 Lỗi và cách khắc phục

Mock SQL PASS có thể che lỗi cú pháp PostgreSQL. Vì vậy suite có SQL thật.
Thiếu private URL thì integration SKIP. URL chỉ đến shared test database sẽ
bị fixture từ chối bởi tên database. Đừng đổi tên guard để dùng database chung.
Nếu --quality-full-data không đi cùng --quality-postgres, pytest báo UsageError.

Trong kiểm thử CLI, assertion privacy ban đầu kiểm substring customer_id và
nhầm cả aggregate flag has_customer_id. Assertion được sửa để kiểm raw field
key chính xác; aggregate count của has_customer_id vẫn là output hợp lệ.

### 6.9 Kiến thức rút ra

Không gộp skipped với passed. Ghi phạm vi test cùng kết quả: PostgreSQL fixture
suite kiểm SQL thật, nhưng chưa chứng nhận dữ liệu production/full-data.

### 6.10 Câu hỏi ôn tập

1. Những tính năng PostgreSQL nào không thể chứng minh bằng MagicMock?
2. Vì sao database name guard chưa tự chứng minh ownership?
3. Điều kiện nào cho phép chạy full-data test?

## 7. Test Fixtures

### 7.1 Định nghĩa và lý thuyết

Fixture là input/trạng thái được dựng để test lặp lại cùng kết quả.
Deterministic fixtures nhỏ giúp nhìn rõ nguyên nhân FAIL và cô lập một thay đổi.
Một fixture tốt có cả dữ liệu thông thường lẫn edge cases của contract thật.

### 7.2 Tại sao cần trong Data Engineering

Dataset một triệu rows khiến unit test chậm và khó hiểu lỗi. Fixture vài rows
có thể mô phỏng guest, return, duplicate, non-product và negative price với
expected tiền tính được bằng tay. Integration vẫn dùng schema/loader thực tế.

### 7.3 Ví dụ Nexora

`make_source` tạo tám retained rows: hai valid duplicate sales cùng invoice,
một cancellation, inventory adjustment không customer/giá zero, POST line,
quantity zero, negative price và bad-debt invoice. Có bảy invoices, hai products,
một identified customer, hai guest lines. Exact ledger là 8.00, gross là 4.00,
physical returns là -2.00.

Đây là synthetic fixtures; các customer/product values không phải dữ liệu raw
được lấy ra khỏi dataset thật.

### 7.4 Code đã triển khai

`raw_row`, `make_source` trong `test_source.py` dùng `clean_data` hiện có để
sinh flags, ghi Parquet trong tmp_path. `QualitySandbox` chứa engine/schema/path,
không chứa raw rows hoặc password. Fixture PG gọi loader sau khi tạo DDL riêng.

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from src.quality.source import source_expectations
from tests.test_quality.test_source import make_source

with TemporaryDirectory() as directory:
    expected = source_expectations(make_source(Path(directory)), batch_size=2)
    assert expected["row_counts"]["invoice_lines"] == 8
    assert expected["flag_counts"]["guest_lines"] == 2
```

### 7.5 Giải thích từng bước

Row helper tạo fields đúng ORIGINAL_COLUMNS. make_source đưa rows qua
clean_data, giữ within-sheet duplicates và sinh semantic flags. File được ghi
vào pytest tmp_path; prepare_frames cung cấp expected loader representation.
Source tests dùng batch sizes 1/2/3 để xác nhận ordinal/fingerprint không đổi
khi rows đi qua batch boundary.

Negative fixtures thay đổi đúng một field hoặc constraint trong sandbox.
Ví dụ đổi source position từ 1 sang 99 giữ row count nhưng tạo missing=1/extra=1.
Đổi quantity cùng key tạo changed=1. Test tiền tăng total_invoice_amount 0.01.

### 7.6 Input và output

Input là list rows synthetic tùy chọn. Output là immutable fixture Parquet path
và database schema tạm. Trong tests, việc mutation là deliberate fault injection,
chỉ xảy ra trên fixtures riêng; production validation runner vẫn read-only.

### 7.7 Hướng dẫn chạy

```powershell
python -m pytest tests/test_quality/test_source.py -q
python -m pytest tests/test_quality/test_frame.py -q
```

Chạy cùng suite nhiều lần phải cho kết quả logic giống nhau. Runtime và UUID
schema có thể thay đổi; assertions không hard-code hai giá trị này.

### 7.8 Lỗi và cách khắc phục

Nếu tạo flags bằng tay không khớp cleaning contract, source reader sẽ báo FAIL
ở bước Parquet validation. Dùng clean_data cho positive fixture, rồi cố ý sửa
field cần test trong negative case. Không để test phụ thuộc ngày hiện tại,
thứ tự database không có ORDER BY, hoặc dataset external.

### 7.9 Kiến thức rút ra

Fixture nhỏ không có nghĩa schema giả hoặc rules đơn giản hóa. Ta dùng đúng
schema và transforms, chỉ giảm số rows để expected dễ kiểm chứng.

### 7.10 Câu hỏi ôn tập

1. Fixture tám rows bao phủ những trường hợp nào?
2. Vì sao cần test batch_size=1 và batch_size=3?
3. Tại sao test UUID/runtime không nên dùng expected cố định?

## 8. Data Quality Pipeline

### 8.1 Định nghĩa và lý thuyết

Quality pipeline là chuỗi validate có thứ tự dependency: cấu hình → catalog →
core checks → source reconciliation → report. Các checks đọc cùng snapshot để
một lần run không trộn counts trước và sau khi loader khác commit.

### 8.2 Tại sao cần trong Data Engineering

Nếu mỗi SELECT dùng snapshot khác nhau, row count có thể lấy trước reload và
ledger lấy sau reload. Một report như vậy không đại diện cho trạng thái thật.
Dependency handling cũng tránh chạy query tiền khi cột tiền chưa tồn tại.

### 8.3 Ví dụ Nexora

`validate_database` chạy REPEATABLE READ và SET TRANSACTION READ ONLY trước các
queries dữ liệu. Missing core column làm dependent checks SKIP. Timeout mặc định
120.000 ms áp dụng cho mỗi statement; đây không phải tổng deadline của cả run.

### 8.4 Code đã triển khai

`validate_database` trong engine.py và `reconcile_source` trong source.py phối
hợp theo thứ tự trên; main() tạo engine từ environment và dispose trong finally.

```python
from sqlalchemy import create_engine
from src.quality.engine import validate_database

def run_quality(database_url, schema, source_path):
    engine = create_engine(database_url, hide_parameters=True)
    try:
        return validate_database(engine, schema=schema, source_path=source_path)
    finally:
        engine.dispose()
```

Hàm ví dụ yêu cầu caller cung cấp URL qua cấu hình an toàn; không đọc .env và
không in URL.

### 8.5 Giải thích từng bước

Catalog và 32 core checks được chạy trong một transaction. Mỗi SELECT riêng
có savepoint để hồi phục khi lỗi. Profile ghi các counts được phép như guest,
retained duplicates, zero quantity/price. Source reader kiểm columns, missing
values và raw business flags, round giá theo loader, tạo hashes và exact totals.

Source dimension keys được băm rồi đối chiếu sets; records được index theo
sheet/retained ordinal. Khi đọc database rows, engine so fingerprint và pop
expected key: cuối cùng keys còn lại là missing, key không có là extra,
same-key hash khác là changed. SHA-256 của file được kiểm trước/sau đọc để
phát hiện source thay đổi trong lúc xây expectations.

### 8.6 Input và output

Input là engine, schema, source_system, optional source_path và timeout.
Output là QualityReport gồm 47 results trên fixture đầy đủ:
44 checks PASS, ba mart checks SKIP. Nếu không cung cấp source, reconciliation
SKIP và relational/source gate chưa đầy đủ.

Parquet được đọc từng batch 50.000 rows, nhưng hashes và entity key sets giữ
trong RAM; memory tăng theo cardinality. Đây không phải thuật toán dùng RAM
cố định. DB line rows được stream bằng yield_per=50.000.

### 8.7 Hướng dẫn chạy

```powershell
# DATABASE_URL đã được inject vào process environment.
python -m src.quality --source-system UCI --schema public --source "D:/data science/nexora-commerce-ai/nexora-commerce-ai/data/processed/transactions_clean.parquet" --json-out "quality-report.json" --markdown-out "quality-report.md"
```

CLI là read-only ngay cả khi đọc development DB. Lệnh trên không load/rebuild DB.
Chọn output ngoài Git; nếu chưa chủ động full-data run, dùng tests fixtures để học.

### 8.8 Lỗi và cách khắc phục

Sai schema/missing table gây catalog FAIL và dependent SKIP. Không có Parquet
thì source SKIP; path được chỉ rõ nhưng không đọc được thì source.parquet FAIL.
Timeout/permissions gây FAIL với thông báo an toàn; cần kiểm lại quyền SELECT
và scope schema mà không dump connection info hoặc raw records vào report.

Source reconciliation hiện chỉ hỗ trợ UCI vì loader dùng SOURCE_SYSTEM=UCI.
Core checks vẫn nhận source_system khác; source check của namespace khác SKIP
để tránh áp nhầm identity contract.

### 8.9 Kiến thức rút ra

Read-only là ràng buộc ở database transaction, không chỉ là lời hứa của code.
Snapshot nhất quán, dependency checks, explicit skip và safe errors giúp report
đáng tin hơn một tập SELECT chạy rời rạc.

### 8.10 Câu hỏi ôn tập

1. REPEATABLE READ bảo vệ report trước reload đồng thời như thế nào?
2. Vì sao source checksum được kiểm cả trước và sau khi đọc?
3. Phần nào của reconciliation còn sử dụng RAM theo số lượng rows?

## 9. Automated Quality Gates

### 9.1 Định nghĩa và lý thuyết

Quality gate là điều kiện cho bước pipeline tiếp theo, dựa trên kết quả checks
và exit code. Gate kỹ thuật không tương đương sign-off nghiệp vụ của milestone.
Một gate cũng phải nói rõ scope; coverage thiếu không được lẫn với success.

### 9.2 Tại sao cần trong Data Engineering

CI/scheduler cần tín hiệu ổn định để dừng pipeline khi FK/ledger/source sai.
Con người vẫn cần report để giải thích failures, đánh giá coverage và phê duyệt
integration. Nếu gate coi thiếu input là PASS, pipeline có thể tiếp tục với
dữ liệu chưa được đối soát.

### 9.3 Ví dụ Nexora

`summary` tính tất cả results, gồm ba marts deferred, nên overall là SKIP
trên fixture đúng. `gate_summary` ghi scope relational_core_and_source và
chỉ loại những mart checks deferred khỏi gate. Trên fixture đúng gate PASS;
trên fixture đổi is_valid_sale gate FAIL. Milestone 2.5 vẫn chưa APPROVED.

### 9.4 Code đã triển khai

`QualityReport.summary`, `gate_summary`, `to_json`, `to_markdown` và CLI
return mapping triển khai quyết định gate.

```python
from src.quality.results import QualityReport, compare, skipped

report = QualityReport("UCI", "public", [
    compare("source.records", 0, 0),
    skipped("marts.mart_daily_sales", "Pending Milestone 2.4"),
])
assert report.summary["status"] == "SKIP"
assert report.gate_summary["status"] == "PASS"
assert QualityReport("UCI", "public").gate_summary["status"] == "SKIP"
```

Ví dụ chỉ minh họa aggregation của results; production runner chạy catalog,
core và source checks đầy đủ trước khi quyết định gate.

### 9.5 Giải thích từng bước

Nếu có FAIL, gate FAIL. Nếu không FAIL nhưng có required SKIP hoặc không có
required results, gate SKIP. Chỉ khi mọi required result đã PASS mới gate PASS.
CLI map PASS→0, FAIL→1, SKIP→2. Missing/invalid DATABASE_URL được báo FAIL;
invalid CLI arguments dùng argparse exit 2. Report-write failure cũng làm gate FAIL.

JSON giữ structure cho automation. Markdown cho người đọc dùng bảng cùng
expected/actual/status/time/reason. Khi một output write thất bại, CLI đưa lỗi
an toàn vào stdout report và cố cập nhật JSON đã ghi trước đó nếu có.

### 9.6 Input và output

Input là results list đã validate. Output là summaries và process exit code.
Milestone APPROVED không được tự động thay đổi trong bất kỳ file status nào.
Marts không được cài hoặc truy vấn chỉ vì SQL files đã hiện diện trên branch base.

### 9.7 Hướng dẫn chạy

```powershell
python -m src.quality --source "D:/data science/nexora-commerce-ai/nexora-commerce-ai/data/processed/transactions_clean.parquet"
if ($LASTEXITCODE -eq 1) { throw "Quality validation failed; inspect the report." }
if ($LASTEXITCODE -eq 2) { throw "Quality gate incomplete or CLI arguments invalid." }
```

Trước lệnh này DATABASE_URL phải có trong process environment. Pipeline chỉ
tiếp tục khi exit code 0; ghi rõ deferred mart coverage ở bước nghiệm thu.
Không đưa password vào command history hoặc hard-code vào workflow.

### 9.8 Lỗi và cách khắc phục

Report rỗng trước đây có thể bị tính như “không có FAIL nên PASS”.
Implementation hiện cho report rỗng SKIP. Mart SKIP không được giấu; luôn có
ba explicit results và overall summary SKIP. Missing source cũng không có
green gate dù SQL core đã PASS.

### 9.9 Kiến thức rút ra

Gate phải có phạm vi, dependency và nghĩa exit code rõ ràng. Dùng gate core
giúp phát triển độc lập trong lúc marts chưa được nghiệm thu, đồng thời giữ
coverage pending hiển thị để không nhầm với approval toàn milestone.

### 9.10 Câu hỏi ôn tập

1. Vì sao summary SKIP và gate_summary PASS có thể đồng thời đúng?
2. Gate PASS có tự cho phép merge hoặc APPROVED Milestone 2.5 không?
3. CI nên xử lý exit code 2 như thế nào?

## Bằng chứng kiểm chứng và giới hạn bàn giao

| Kiểm chứng đã chạy | Kết quả thực tế | Thời gian |
|---|---|---:|
| Quality + Stage 1, offline | 72 passed, 24 skipped | 3,23 giây |
| Quality trên private PostgreSQL 16.15, có CLI subprocesses | 88 passed, 1 skipped | 11,53 giây |
| Static schema với --noconftest | 8 passed | 0,06 giây |
| Hai CLI fixtures được lưu báo cáo minh chứng | 2 passed | 4,49 giây |

Trong offline suite, quality có 65 tests PASS và 24 integration/full-data SKIP;
Stage 1 có bảy tests PASS. Trong private PostgreSQL suite, 23 integration tests
được chạy và chỉ một full-data test SKIP. Tám static schema tests đọc DDL,
không kết nối DB. Các runtimes trên là lần run đã ghi nhận, không phải SLA.

Report fixture đúng có 44 PASS, 0 FAIL, 3 SKIP; DB validation mất khoảng 212 ms.
Report fixture đổi một cờ is_valid_sale có 39 PASS, 5 FAIL, 3 SKIP; khoảng 208 ms.
Thời gian này đo validation runner trên tám rows; không dự đoán runtime warehouse
1.044.848 rows. CLI/subprocess/test setup có thời gian riêng.

Chưa chạy full-data validation trên development warehouse. Checks header/
customer money có thể phát hiện rounding disagreement của loader khi chạy dữ
liệu thật. Source comparison kiểm exact line payload, dimension keys và SHA;
chưa so mọi mode description/country/median của dimension với source-derived
attributes. Không phát triển các metrics bị cấm như profit, conversion hay CAC.

Ba mart checks chỉ được kích hoạt bằng implementation/test integration sau khi
Milestone 2.4 được approve và merge; đọc [contracts tích hợp](../quality_marts_integration.md).
Nội dung để tích hợp vào learning log có trong
[stage_02_data_quality_log_update.md](stage_02_data_quality_log_update.md);
file PROJECT_LEARNING_LOG.md của Copilot không bị sửa trong phiên song song.
