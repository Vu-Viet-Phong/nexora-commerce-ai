# Tài Liệu Học Tập: Xây Dựng E-Commerce Analytics Dashboard MVP với Streamlit & PostgreSQL

> **Dự án:** Nexora Commerce AI  
> **Giai đoạn:** Analytics Dashboard MVP  
> **Tác giả:** Senior Full-Stack Data Engineer / Streamlit Developer  
> **Ngôn ngữ:** Python 3.11, SQL, Streamlit 1.65.0  
> **Cơ sở dữ liệu:** PostgreSQL 16 Native Windows (localhost:5432)  
> **Bộ dữ liệu nguồn:** UCI Online Retail II (5,942 Customers, 53,628 Invoices, 1,044,848 Lines)  

---

## Mục Lục
1. [Tổng Quan Kiến Trúc Dashboard](#1-tổng-quan-kiến-trúc-dashboard)
2. [Streamlit là gì?](#2-streamlit-là-gì)
3. [Tại sao chọn Streamlit?](#3-tại-sao-chọn-streamlit)
4. [Luồng Dữ Liệu: PostgreSQL → SQL Marts → Dashboard](#4-luồng-dữ-liệu-postgresql--sql-marts--dashboard)
5. [Cấu Trúc Thư Mục Tối Giản (Lean Code Architecture)](#5-cấu-trúc-thư-mục-tối-giản-lean-code-architecture)
6. [Giải Thích Từng File Python](#6-giải-thích-từng-file-python)
7. [Giải Thích Từng Hàm Quan Trọng Trong Query Layer](#7-giải-thích-từng-hàm-quan-trọng-trong-query-layer)
8. [Input / Output Thực Tế](#8-input--output-thực-tế)
9. [SQL Query & Server-Side Aggregation](#9-sql-query--server-side-aggregation)
10. [Data Visualization Trong Dashboard](#10-data-visualization-trong-dashboard)
11. [Caching & Performance Tối Ưu Hóa](#11-caching--performance-tối-ưu-hóa)
12. [Các Lỗi Phát Sinh và Cách Giải Quyết](#12-các-lỗi-phát-sinh-và-cách-giải-quyết)
13. [Hướng Dẫn Chạy Dashboard Từ Đầu](#13-hướng-dẫn-chạy-dashboard-từ-đầu)
14. [Kết Quả Kiểm Thử (Automated Test Results)](#14-kết-quả-kiểm-thử-automated-test-results)
15. [Lịch Sử Git Commits Theo Checkpoint](#15-lịch-sử-git-commits-theo-checkpoint)
16. [Kiến Thức Cốt Lõi Học Được & Câu Hỏi Ôn Tập](#16-kiến-thức-cốt-lõi-học-được--câu-hỏi-ôn-tập)

---

## 1. Tổng Quan Kiến Trúc Dashboard

Trong các hệ thống phân tích dữ liệu thương mại điện tử hiện đại, việc phân tách rõ ràng giữa **Storage & Transformation Layer** (Data Warehouse / Marts) và **Presentation Layer** (BI Dashboard) là nguyên tắc sống còn.

Kiến trúc của Nexora Commerce AI Dashboard được thiết kế theo mô hình **3-Tier Lean Architecture**:

```
+-------------------------------------------------------------+
|                      DATA WAREHOUSE                         |
|   PostgreSQL 16 Native Windows (Database: nexora_commerce)   |
|   - Base Tables: customers, products, invoices, invoice_lines|
|   - 1,044,848 transaction lines                             |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                     ANALYTICAL MARTS                        |
|   1. mart_daily_sales (calendar_day, country, merchandise)  |
|   2. mart_customer_daily (customer_id, calendar_day)        |
|   3. mart_customer_snapshot (customer_id, RFM metrics)      |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                    QUERY ACCESS LAYER                       |
|   app/queries.py (SQLAlchemy + Safe Parameterization)       |
|   - Server-side aggregation (không kéo 1 triệu dòng vào RAM)|
|   - Resilient error handling (DatabaseQueryError)           |
|   - Cross-engine compatibility (PostgreSQL & SQLite)        |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                     PRESENTATION LAYER                      |
|   app/dashboard.py (Streamlit Web Interface)                |
|   - @st.cache_data / @st.cache_resource                     |
|   - Sidebar Filters: Date Range Picker, Country Selectbox   |
|   - 3 Business Tabs: Sales Overview, Customers, RFM Segments|
+-------------------------------------------------------------+
```

---

## 2. Streamlit là gì?

**Streamlit** là một framework mã nguồn mở của Python được thiết kế chuyên biệt để xây dựng các ứng dụng web tương tác cho Data Science và Machine Learning mà không cần viết HTML, CSS, JavaScript hay cấu hình backend phức tạp (như Django, Flask, FastAPI).

Đặc điểm hoạt động cốt lõi của Streamlit:
- **Execution Model (Re-run on State Change):** Mỗi khi người dùng tương tác với một widget (ví dụ thay đổi Date Range hoặc chọn Country), toàn bộ script Python sẽ được thực thi lại từ trên xuống dưới.
- **Smart Caching:** Để tránh việc mỗi lần re-run lại phải query lại database 1 triệu dòng, Streamlit cung cấp cơ chế `@st.cache_data` và `@st.cache_resource`, giúp lưu kết quả trong bộ nhớ đệm dựa trên hash của các tham số đầu vào.

---

## 3. Tại sao chọn Streamlit?

1. **Tốc độ triển khai (Fast Time-to-Market):** Tạo dashboard hoàn chỉnh với KPI cards, line charts, bar charts, data table chỉ trong vài chục dòng code Python thuần túy.
2. **Không phân mảnh công nghệ:** Cả pipeline kỹ thuật dữ liệu (Pandas, PyArrow, SQLAlchemy) và giao diện phân tích đều sử dụng chung một ngôn ngữ Python 3.11.
3. **Lean Code (Không over-engineering):** Không cần xây dựng REST API riêng, frontend framework (React/Vue), routing, hay authentication phức tạp trong giai đoạn MVP.
4. **Tích hợp sâu với PyData:** Hỗ trợ trực tiếp Pandas DataFrame, Matplotlib, Altair, Plotly.

---

## 4. Luồng Dữ Liệu: PostgreSQL → SQL Marts → Dashboard

1. **Dữ liệu thô đã làm sạch (Stage 1 Parquet):** `transactions_clean.parquet` chứa 1,044,848 dòng giao dịch với các cờ dữ liệu (`is_valid_sale`, `is_cancellation`, `is_inventory_adjustment`, `is_non_product`).
2. **PostgreSQL Tables (Stage 2.3 Loader):** Nạp vào 4 bảng chuẩn hóa: `customers` (5,942), `products` (5,131), `invoices` (53,628), `invoice_lines` (1,044,848).
3. **SQL Analytics Marts (Milestone 2.4):**
   - `mart_daily_sales`: Grain là `(calendar_day, country, is_physical_merchandise)`. Tính toán trước `gross_sales`, `valid_sales_revenue`, `return_value`, `net_sales`, `distinct_invoices`, `units_sold`.
   - `mart_customer_daily`: Grain là `(customer_id, calendar_day)`. Tính `order_frequency`, `gross_spend`, `return_value`, `net_spend`.
   - `mart_customer_snapshot`: Grain là 1 dòng cho mỗi khách hàng định danh (5,942 khách hàng). Tính toán sẵn các chỉ số RFM: `recency_days`, `frequency`, `monetary`, `average_order_value`, `tenure_days`.
4. **Dashboard Query Layer:** Dashboard KHÔNG truy vấn bảng thô `invoice_lines` 1 triệu dòng, mà CHỈ truy vấn vào 3 SQL Marts này. Do đó thời gian query chỉ mất dưới **15 mili-giây**!

---

## 5. Cấu Trúc Thư Mục Tối Giản (Lean Code Architecture)

```
nexora-commerce-ai/
├── app/
│   ├── __init__.py           # Package marker
│   ├── queries.py            # Read-only query layer & RFM logic
│   └── dashboard.py          # Streamlit UI & interactive visualizer
├── docs/
│   └── learning/
│       └── analytics_dashboard_streamlit.md   # Tài liệu học tập (file này)
├── sql/
│   └── marts/                # SQL Mart definition views
│       ├── mart_daily_sales.sql
│       ├── mart_customer_daily.sql
│       └── mart_customer_snapshot.sql
├── tests/
│   └── test_dashboard.py     # Unit tests & contracts (chạy in-memory SQLite)
└── pyproject.toml            # Khai báo dependency: streamlit, sqlalchemy, pandas...
```

**Nguyên tắc Lean Code áp dụng:**
- Không tạo các lớp abstraction thừa (không tạo DAO/Repository lồng nhau nhiều tầng).
- Không thêm Redis, Celery, FastAPI, RabbitMQ khi chưa có nhu cầu scale phân tán.
- Chỉ tạo 2 file ứng dụng cốt lõi: `app/queries.py` (logic & data fetch) và `app/dashboard.py` (UI).

---

## 6. Giải Thích Từng File Python

### `app/queries.py`
Chịu trách nhiệm toàn bộ việc giao tiếp với cơ sở dữ liệu.
- Quản lý engine SQLAlchemy với `pool_pre_ping=True` để tự động phát hiện kết nối chết.
- Chuẩn hóa URL kết nối (`normalize_db_url`) để encode các ký tự đặc biệt trong password mà không in password ra log.
- Cung cấp các hàm truy vấn tham số hóa (parameterized queries) ngăn ngừa triệt để SQL Injection.
- Cung cấp hàm `compute_rfm_segments` để chia nhóm khách hàng theo ma trận RFM.

### `app/dashboard.py`
Chịu trách nhiệm hiển thị giao diện Streamlit.
- Cấu hình layout trang rộng (`layout="wide"`).
- Quản lý Sidebar: trạng thái kết nối DB, bộ chọn khoảng thời gian (Date Range), bộ chọn quốc gia (Country Filter), nút làm mới cache.
- Tổ chức 3 Tab nghiệp vụ: **Sales Overview**, **Customer Analytics**, **RFM Segmentation**.
- Kết nối dữ liệu với các hàm cached (`@st.cache_data`, `@st.cache_resource`).

### `tests/test_dashboard.py`
Bộ kiểm thử tự động độc lập, không phụ thuộc vào cơ sở dữ liệu đang chạy:
- Sử dụng SQLite in-memory fixture mô phỏng schema của các SQL Marts.
- Kiểm tra tính toán KPIs: Gross sales, Net sales, Return value, AOV, Return rate.
- Kiểm tra bộ lọc ngày và quốc gia.
- Kiểm tra thuật toán phân nhóm RFM khi có khách hàng chưa từng mua hàng (`recency_days IS NULL`).
- Đảm bảo 100% test chạy trong thời gian dưới 1 giây.

---

## 7. Giải Thích Từng Hàm Quan Trọng Trong Query Layer

| Tên Hàm | Tham Số Đầu Vào | Dữ Liệu Trả Về | Ý Nghĩa Nghiệp Vụ |
| :--- | :--- | :--- | :--- |
| `get_engine()` | `database_url`, `load_env` | `sqlalchemy.Engine` | Khởi tạo connection pool với cơ chế kiểm tra kết nối `pool_pre_ping`. |
| `normalize_db_url()` | `url: str` | `str` | URL-encode ký tự đặc biệt trong mật khẩu tránh lỗi parse của SQLAlchemy. |
| `get_date_range()` | `engine` | `(min_date, max_date)` | Lấy ngày nhỏ nhất và lớn nhất của tập dữ liệu để thiết lập min/max cho Date Picker. |
| `get_available_countries()` | `engine` | `list[str]` | Lấy danh sách 43 quốc gia có phát sinh giao dịch cho dropdown bộ lọc. |
| `get_sales_kpis()` | `engine, start_date, end_date, country` | `dict[str, float]` | Tính tổng doanh thu gộp, doanh thu thuần, tiền hoàn, số đơn hàng, AOV trực tiếp trên DB. |
| `get_daily_sales_trend()` | `engine, start_date, end_date, country` | `pd.DataFrame` | Lấy chuỗi thời gian doanh thu hàng ngày phục vụ vẽ biểu đồ xu hướng. |
| `get_sales_by_country()` | `engine, start_date, end_date, limit` | `pd.DataFrame` | Xếp hạng các thị trường quốc tế theo doanh thu thuần. |
| `get_merchandise_breakdown()`| `engine, start_date, end_date, country` | `pd.DataFrame` | Phân tích tỉ trọng giữa Hàng hóa vật lý (Physical) và Phí dịch vụ/Bưu điện. |
| `get_customer_kpis()` | `engine, country` | `dict[str, float]` | Tính tổng số khách hàng, tổng chi tiêu, tần suất mua trung bình, AOV trung bình. |
| `get_customer_daily_trend()`| `engine, start_date, end_date` | `pd.DataFrame` | Theo dõi số lượng khách hàng mua hàng hoạt động hàng ngày (Active Buyers). |
| `get_top_customers()` | `engine, country, limit` | `pd.DataFrame` | Bảng xếp hạng Top khách hàng chi tiêu nhiều nhất. |
| `get_rfm_snapshot()` | `engine, country` | `pd.DataFrame` | Lấy bảng dữ liệu 5,942 khách hàng kèm các chỉ số R, F, M. |
| `compute_rfm_segments()` | `df: pd.DataFrame` | `pd.DataFrame` | Tính điểm 1-5 cho R, F, M bằng percentiles và gán phân khúc khách hàng. |

---

## 8. Input / Output Thực Tế

### Truy Vấn Toàn Bộ Hệ Thống (Không Lọc)
- **Khoảng thời gian:** `2009-12-01` đến `2011-12-09` (2 năm).
- **Số quốc gia:** `43` quốc gia.
- **Sales KPIs:**
  - `gross_sales`: **£19,700,954.44**
  - `return_value`: **-£719,692.94**
  - `net_sales`: **£18,981,261.50**
  - `total_orders`: **39,516** đơn hàng hợp lệ
  - `units_sold`: **11,221,957** sản phẩm
  - `units_returned`: **469,882** sản phẩm bị trả lại
  - `aov` (Average Order Value): **£480.34**
  - `return_rate_pct`: **3.65%**
- **Customer Snapshot KPIs:**
  - `total_customers`: **5,942** khách hàng định danh
  - `total_customer_spend`: **£16,411,894.73**
  - `avg_frequency`: **6.16** đơn hàng/khách
  - `avg_aov`: **£386.11**
  - `avg_recency_days`: **200.7** ngày
  - `avg_tenure_days`: **474.5** ngày

### Phân Bổ Phân Khúc RFM (5,942 Khách Hàng)
- **Loyal Customers:** 1,435 (24.1%)
- **Champions:** 1,307 (22.0%)
- **Lost:** 802 (13.5%)
- **At Risk:** 619 (10.4%)
- **Hibernating:** 512 (8.6%)
- **Potential Loyalists:** 444 (7.5%)
- **Standard:** 274 (4.6%)
- **About To Sleep:** 238 (4.0%)
- **Need Attention:** 205 (3.5%)
- **Promising:** 106 (1.8%)

---

## 9. SQL Query & Server-Side Aggregation

Thay vì load toàn bộ 1 triệu dòng vào Pandas rồi dùng `.groupby()` tốn hàng Gigabyte RAM và làm chậm ứng dụng, chúng ta đẩy toàn bộ gánh nặng tính toán xuống PostgreSQL:

```sql
SELECT
    COALESCE(SUM(gross_sales), 0) AS gross_sales,
    COALESCE(SUM(valid_sales_revenue), 0) AS valid_sales,
    COALESCE(SUM(return_value), 0) AS return_value,
    COALESCE(SUM(net_sales), 0) AS net_sales,
    COALESCE(SUM(distinct_invoices), 0) AS total_orders,
    COALESCE(SUM(units_sold), 0) AS units_sold,
    COALESCE(SUM(units_returned), 0) AS units_returned
FROM mart_daily_sales
WHERE calendar_day >= :start_date 
  AND calendar_day <= :end_date 
  AND country = :country;
```

Kết quả trả về chỉ là **1 dòng duy nhất** dung lượng vài chục byte, tốc độ truy vấn tức thì (< 5ms).

---

## 10. Data Visualization Trong Dashboard

Dashboard kết hợp các thành phần trực quan:
1. **KPI Metric Cards:** Hiển thị doanh thu, đơn hàng, AOV với delta hiển thị tỷ lệ hoàn trả hàng (Return Rate %).
2. **Time-Series Line Charts:** Biểu diễn doanh thu gộp vs doanh thu thuần qua thời gian, nhận diện các mùa vụ cao điểm (ví dụ tháng 11 - 12 Black Friday và Giáng Sinh).
3. **Horizontal Bar Charts:** Xếp hạng các thị trường quốc tế hàng đầu (United Kingdom, EIRE, Germany, France, Netherlands...).
4. **Distribution Bar Charts & Dataframes:** Biểu đồ cơ cấu nhóm khách hàng RFM và bảng chi tiết danh sách khách hàng VIP.

---

## 11. Caching & Performance Tối Ưu Hóa

Streamlit cung cấp 2 decorator bộ nhớ đệm:
- `@st.cache_resource`: Dùng cho các đối tượng duy trì kết nối như Database Engine hoặc ML Model.
  ```python
  @st.cache_resource
  def init_engine():
      return get_engine()
  ```
- `@st.cache_data(ttl=300)`: Dùng cho dữ liệu dạng DataFrame hoặc Dictionary. Lưu trong bộ nhớ 5 phút (300 giây). Nếu người dùng chọn cùng một bộ lọc ngày và quốc gia, dữ liệu được lấy ngay từ RAM máy chủ trong 0.001 giây thay vì gọi lại PostgreSQL.

---

## 12. Các Lỗi Phát Sinh và Cách Giải Quyết

### Lỗi 1: `sqlite3.OperationalError: unrecognized token: ":"`
- **Nguyên nhân:** Khi viết query cho PostgreSQL, lập trình viên sử dụng cú pháp ép kiểu đặc thù của Postgres là `::NUMERIC(14, 2)` và `::BIGINT`. Khi chạy bộ kiểm thử SQLite in-memory, SQLite không hỗ trợ toán tử `::` và báo lỗi cú pháp.
- **Giải pháp:** Bỏ toán tử `::` trong câu lệnh SELECT, chuyển sang ANSI SQL thuần túy (`COALESCE(SUM(col), 0)`). Vì bản thân các SQL Marts trong PostgreSQL đã khai báo kiểu `NUMERIC(14, 2)` ngay trong view, việc ép kiểu lại ở tầng query là thừa thãi.

### Lỗi 2: `pandas.errors.IntCastingNaNError: Cannot convert non-finite values (NA or inf) to integer`
- **Nguyên nhân:** Trong 5,942 khách hàng của `mart_customer_snapshot`, có đúng **90 khách hàng** không có bất kỳ giao dịch mua hàng hợp lệ nào (chỉ có đơn hủy hoặc điều chỉnh nợ xấu). Do đó `last_purchase_date` là NULL dẫn đến `recency_days` là NaN. Khi tính `rank()` và ép kiểu về integer để chấm điểm RFM, Pandas gặp lỗi.
- **Giải pháp:** Sử dụng `.fillna()` an toàn trước khi xếp hạng:
  ```python
  clean_recency = result["recency_days"].fillna(result["recency_days"].max() + 365)
  r_pct = clean_recency.rank(pct=True, method="first", ascending=False)
  result["r_score"] = np.ceil(r_pct * 5).fillna(1).astype(int).clip(1, 5)
  ```
  Nhờ đó, 90 khách hàng không có ngày mua gần nhất sẽ nhận `r_score = 1` và được phân loại đúng vào nhóm `"Lost"` hoặc `"Hibernating"`.

### Lỗi 3: Lộ mật khẩu trong connection string hoặc logs
- **Nguyên nhân:** Chuỗi kết nối PostgreSQL chứa username và password. Nếu mật khẩu chứa ký tự đặc biệt (ví dụ `@`, `#`), SQLAlchemy có thể parse sai hoặc in ra exception trace.
- **Giải pháp:** Sử dụng hàm `normalize_db_url()` mã hóa ký tự mật khẩu bằng `urllib.parse.quote` và không bao giờ `print()` chuỗi kết nối chứa mật khẩu ra console hoặc commit vào Git.

---

## 13. Hướng Dẫn Chạy Dashboard Từ Đầu

### Bước 1: Kích hoạt môi trường ảo
```powershell
.\.venv\Scripts\Activate.ps1
```

### Bước 2: Khởi chạy Streamlit Dashboard
```powershell
streamlit run app/dashboard.py
```

### Bước 3: Truy cập trên trình duyệt
Ứng dụng sẽ tự động mở tại địa chỉ:
`http://localhost:8501`

---

## 14. Kết Quả Kiểm Thử (Automated Test Results)

Chạy toàn bộ test suite:
```powershell
pytest tests/test_dashboard.py -v
```

Kết quả sau Checkpoint B:
```
tests/test_dashboard.py::test_normalize_db_url_encodes_special_password PASSED
tests/test_dashboard.py::test_normalize_db_url_leaves_standard_url_untouched PASSED
tests/test_dashboard.py::test_load_env_config_reads_custom_env PASSED
tests/test_dashboard.py::test_get_engine_missing_url_raises PASSED
tests/test_dashboard.py::test_get_date_range_and_countries PASSED
tests/test_dashboard.py::test_get_sales_kpis_all_filters PASSED
tests/test_dashboard.py::test_get_sales_kpis_filtered_by_country_and_date PASSED
tests/test_dashboard.py::test_get_daily_sales_trend PASSED
tests/test_dashboard.py::test_get_sales_by_country PASSED
tests/test_dashboard.py::test_get_merchandise_breakdown PASSED
tests/test_dashboard.py::test_resample_sales_trend_weekly_and_monthly PASSED
tests/test_dashboard.py::test_calculate_country_shares PASSED
tests/test_dashboard.py::test_resample_sales_trend_empty PASSED
tests/test_dashboard.py::test_get_customer_kpis PASSED
tests/test_dashboard.py::test_get_customer_daily_trend PASSED
tests/test_dashboard.py::test_get_top_customers PASSED
tests/test_dashboard.py::test_compute_customer_distributions PASSED
tests/test_dashboard.py::test_compute_customer_distributions_empty PASSED
tests/test_dashboard.py::test_compute_rfm_segments_empty_dataframe PASSED
tests/test_dashboard.py::test_compute_rfm_segments_handles_null_recency_and_assigns_segments PASSED
tests/test_dashboard.py::test_missing_table_raises_database_query_error PASSED

============================= 21 passed in 1.18s ==============================
```

---

## 15. Lịch Sử Git Commits Theo Checkpoint

- **Checkpoint A (`3337dfc`):** Khởi tạo kiến trúc Dashboard & Query Layer, cấu hình Streamlit dependency, xử lý kết nối DB an toàn và xây dựng bộ kiểm thử in-memory.
- **Checkpoint B (`de9942c`):** Hoàn thiện Sales Overview Section:
  - 5 KPI metric cards với chỉ số hoàn hàng và realization rate.
  - Bộ điều khiển độ phân giải thời gian (Daily, Weekly, Monthly) với line chart, bar chart và cumulative revenue area chart.
  - Phân tích thị trường quốc tế với tỉ trọng thị phần (Market Share %) và bảng chi tiết doanh thu theo quốc gia.
  - Thẻ thông tin kiểm soát dữ liệu và phân loại hàng hóa vật lý (Physical Merchandise).
- **Checkpoint C:** Hoàn thiện Customer Analytics Section:
  - 5 KPI cards mở rộng: Tổng khách hàng (5,942), Tỷ lệ khách mua lại (Repeat Rate: 71.3%), Tổng chi tiêu trọn đời (£16.41M), AOV (£386.11), Vòng đời trung bình (474.5 ngày).
  - Phân bố tần suất mua hàng (One-Time, Occasional, Frequent, VIP Power Buyers) và các phân khúc ngân sách chi tiêu.
  - Biểu đồ chuỗi thời gian người mua hoạt động hàng ngày (Active Buyers) và chi tiêu hàng ngày từ `mart_customer_daily`.
  - Bảng xếp hạng Top 15 khách hàng VIP có giá trị chi tiêu cao nhất kèm thông tin quốc gia, số đơn, AOV và ngày mua cuối.
- **Checkpoint D:** (Kế tiếp) Hoàn thiện RFM Analytics Section.
- **Checkpoint E:** (Kế tiếp) Hoàn thiện toàn diện, kiểm tra an ninh và kiểm thử hồi quy.

---

## 16. Kiến Thức Cốt Lõi Học Được & Câu Hỏi Ôn Tập

### Kiến Thức Cốt Lõi
1. **Database-first BI:** Để dashboard nhanh và ổn định, hãy tính toán và chuẩn hóa grain ngay trong SQL Marts thay vì đẩy gánh nặng xử lý dữ liệu lớn lên frontend.
2. **Idempotent UI:** Thiết kế các hàm query có khả năng chịu lỗi, trả về giá trị mặc định rõ ràng khi dữ liệu rỗng.
3. **An toàn kết nối:** Không hard-code credentials, luôn dùng `.env` kết hợp biến môi trường của hệ điều hành.

### Câu Hỏi Ôn Tập
1. *Tại sao không nên query trực tiếp bảng `invoice_lines` 1,044,848 dòng từ Streamlit?*  
   **Trả lời:** Vì mỗi lần người dùng bấm lọc, Streamlit sẽ re-run script. Query 1 triệu dòng qua mạng hoặc vào RAM sẽ làm nghẽn CPU và bộ nhớ, trong khi SQL Mart `mart_daily_sales` đã aggregate sẵn chỉ còn 3,160 dòng, phản hồi dưới 15ms.
2. *Làm thế nào để xử lý 90 khách hàng có `recency_days` là NULL trong phân tích RFM?*  
   **Trả lời:** Gán giá trị recency phạt cao hơn ngày tối đa (`max + 365`), cho điểm `r_score = 1` và xếp vào nhóm khách hàng `Lost` hoặc `Hibernating`.
