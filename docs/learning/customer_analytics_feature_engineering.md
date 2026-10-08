# Customer Analytics và Feature Engineering

## 1. Phạm vi và milestone thực tế

Project specification mô tả Analytics, Machine Learning và Recommendation là
các module tương lai. Metric contract hiện tại xác định Stage 3 là
`Analytics & EDA`, đồng thời đã phê duyệt RFM, AOV và customer population.
Checkpoint này triển khai phần nền tảng Analytics/EDA và customer-level
feature dataset; không huấn luyện model và không bắt đầu Data Quality Engine
hay Streamlit Dashboard của agent khác.

Nguồn dữ liệu duy nhất là relational core và ba SQL marts đã được nghiệm thu.
Không sửa cleaning pipeline Stage 1 và không commit dữ liệu khách hàng/raw
dataset.

## 2. Kiến trúc và lý thuyết

Relational core có grain transaction line, còn analytics mart có grain đã
được cố định:

- `mart_customer_daily`: một row cho `(customer_id, calendar_day)`.
- `mart_customer_snapshot`: một row cho mỗi identified customer.
- `mart_daily_sales`: một row cho `(calendar_day, country,
  is_physical_merchandise)`.

Feature generation chỉ aggregate `mart_customer_daily` đến một
`as_of_date`. Vì vậy database chỉ đọc hơn một triệu transaction lines một lần
ở lớp mart; Python chỉ nhận khoảng 5.942 customer rows. Đây là cách tránh
đưa fact table lớn vào RAM và ngăn data leakage.

RFM theo contract:

- **Recency:** `as_of_date - last_purchase_date`, tính trên valid sale.
- **Frequency:** tổng `order_frequency`, tức distinct valid invoice ở mỗi ngày.
- **Monetary:** `SUM(net_spend)` = gross valid sale + physical return value.
- **AOV:** gross valid spend / frequency; NULL khi frequency bằng 0.
- **Tenure:** `as_of_date - first_purchase_date`; NULL khi chưa có valid sale.

`customer_id IS NULL` không được đưa vào customer mart. Không tạo customer
giả `0`/`99999`.

## 3. Code thực tế

Code nằm tại
[`src/analytics/customer_analytics.py`](../../src/analytics/customer_analytics.py)
và public API được export tại
[`src/analytics/__init__.py`](../../src/analytics/__init__.py).

### 3.1 Customer feature query

Query dùng các CTE:

```sql
WITH bounded_daily AS (
    SELECT customer_id, calendar_day, order_frequency,
           gross_spend, return_value, net_spend
    FROM mart_customer_daily
    WHERE calendar_day <= CAST(:as_of_date AS DATE)
),
aggregated AS (
    SELECT customer_id,
           SUM(order_frequency) AS frequency,
           SUM(net_spend) AS monetary
    FROM bounded_daily
    GROUP BY customer_id
)
SELECT ...
FROM customers AS c
LEFT JOIN aggregated AS a ON a.customer_id = c.customer_id
WHERE c.source_system = 'UCI';
```

`LEFT JOIN` giữ customer chưa có giao dịch trước `as_of_date`. Điều này khác
với việc drop missing value: row customer vẫn tồn tại, frequency/monetary
được đưa về zero, còn recency/AOV/tenure vẫn NULL vì chưa có ý nghĩa.

Input là PostgreSQL engine và một ngày tham chiếu. Output là DataFrame đúng
schema:

| Column | Ý nghĩa | Nullable |
|---|---|---:|
| `customer_id` | Stable source-scoped identifier | No |
| `primary_country` | Country canonical từ dimension | No |
| `reference_date` | Ngày dùng để cắt dữ liệu | No |
| `recency_days` | Số ngày từ lần mua cuối | Yes |
| `frequency` | Số valid orders | No |
| `monetary` | Net merchandise spend | No |
| `average_order_value` | Gross spend / frequency | Yes |
| `tenure_days` | Tuổi customer từ valid purchase đầu | Yes |

`validate_customer_features` kiểm tra cột bắt buộc, uniqueness, NULL
identifier, numeric finite values và các ngày/ frequency không âm.

### 3.2 EDA

`EDA_QUERIES` cung cấp mười truy vấn read-only:

1. Phân phối daily sales: min, median, p95, max.
2. Customer transaction behavior: customer count, frequency, recency,
   tenure trung bình.
3. Order frequency: histogram frequency/customer count.
4. Spending distribution: p50, p90, p99, max monetary.
5. Product popularity: top 100 theo units sold và gross sales.
6. Country distribution: net sales theo country.
7. Returns/cancellations: return value, units returned, số group có return.
8. Missing Customer ID: line count, missing line count, ledger amount.
9. Temporal patterns: daily net sales và invoice count.
10. Sparsity/long tail: positive customers, top customer và top-100 revenue
    share.

`run_eda(engine)` chỉ trả về các bảng summary bounded; không ghi file và
không thay đổi database.

## 4. Feature chưa có business contract

Các feature sau được ghi nhận là backlog, không nằm trong production output
ở checkpoint này:

- distinct products purchased;
- return frequency theo customer;
- purchase activity theo weekday/month;
- spending variability;
- product/category preference vectors.

Lý do là metric contract chưa định nghĩa chính xác cửa sổ thời gian, xử lý
return-only order, timezone/calendar bucket hoặc population denominator cho
những feature này. Tự đưa chúng vào ML dataset sẽ tạo metric divergence.

## 5. Kết quả EDA trên database thật

Smoke test read-only trên `nexora_commerce` chạy thành công:

- Customer feature rows: **5.942**.
- Feature columns: **8** theo contract.
- EDA sections: **10/10**.
- Temporal daily rows: **604**.
- Tổng frequency: **36.594** trong bounded feature query.
- Tổng customer monetary: **£16,411,894.73**, khớp customer mart.
- Daily net sales: median **£719.07**, p95 **£32,078.92**, max
  **£105,983.79**, min **-£11,880.84**.
- Customer monetary: p50 **£825.73**, p90 **£5,180.62**, p99 **£26,342.82**,
  max **£578,408.64**.
- Top 100 customer positive-monetary share: **36.68%**, cho thấy long-tail
  đáng kể; positive-monetary customer count là **5.832**.
- Physical return value **-£719,692.94**, returned units **469.882**, và
  1.269 daily mart groups có return.
- Missing customer lines: **235.287 / 1.044.848**, missing-customer ledger
  **£2,566,093.08**; các line này vẫn giữ ở company mart nhưng không vào RFM.

Kết quả này chứng minh pipeline thực sự đọc relational core/marts đã duyệt,
không dùng raw data hay dữ liệu giả. Các bảng EDA chi tiết được trả về ở
runtime, không lưu thành artifact chứa dữ liệu khách hàng trong repository.

## 6. Tests và các lỗi đã gặp

Tests deterministic nằm tại
[`tests/test_analytics/test_customer_analytics.py`](../../tests/test_analytics/test_customer_analytics.py).

Coverage hiện tại:

- Empty frame có schema hợp lệ.
- Duplicate customer ID bị từ chối.
- NULL customer ID bị từ chối.
- Negative recency bị từ chối.
- Query deterministic qua hai lần build.
- Query có `calendar_day <= :as_of_date`, bảo vệ temporal leakage.
- Query không tự chèn điều kiện làm mất population customer ở snapshot.

Lỗi runtime đầu tiên trong EDA là query long-tail join lại snapshot và tạo
ambiguous column `frequency`. Root cause là CTE đã có `frequency` nhưng
`JOIN ... USING (customer_id)` đưa thêm một cột cùng tên vào scope. Cách sửa
là bỏ join dư thừa và tính top-100 share trực tiếp trên CTE ranked. Đây vừa
loại lỗi SQL vừa làm công thức đúng hơn: `SUM(top_100 monetary) /
SUM(all positive monetary)`, thay vì lấy share lớn nhất của một customer.

Lỗi môi trường ban đầu là worktree không có `.venv` vì virtual environment
được ignore. Test được chạy bằng interpreter project tuyệt đối từ worktree
chính; không copy `.env`, không commit credentials và không ghi vào database
test của agent khác.

## 7. Reproducibility và lineage

Feature generation deterministic theo:

1. source namespace `UCI`;
2. approved `mart_customer_daily`;
3. explicit `as_of_date`;
4. `ORDER BY customer_id`;
5. stable customer ID từ dimension.

`write_customer_features` chỉ ghi DataFrame customer-level ra Parquet khi
caller yêu cầu. Output path nên đặt ngoài repository hoặc trong thư mục đã
ignore; repository không chứa output customer data.

## 8. Kết quả test checkpoint

Unit test analytics: **5 passed**.

Read-only smoke test database thật: **PASS**, 5.942 rows và 10 EDA sections.

Full regression sẽ chạy ở checkpoint D bằng project interpreter. Full-data
loader không cần chạy lại vì feature query reuse mart đã được nghiệm thu.

## 9. Kiến thức cần học thêm

- Thiết kế temporal feature store và point-in-time correctness.
- Robust scaling/log transform cho B2B heavy-tail.
- Cohort analysis và survival/churn definitions.
- Metric contract cho return rate, product diversity và spending volatility.
- Sparse matrix representation cho recommendation system.
- Privacy controls khi xuất customer-level ML dataset.
