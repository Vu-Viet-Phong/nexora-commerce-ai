# Customer Segmentation bằng RFM và K-Means

## 1. Phạm vi

Đây là baseline Machine Learning cho Stage 3 Analytics, dùng customer-level
features đã được tạo ở checkpoint trước. Code không sửa SQL marts, không chạy
model trên guest customer và không tự tuyên bố production-ready. Các nhãn RFM
là quy tắc thử nghiệm; K-Means là baseline unsupervised để đánh giá khả năng
tách hành vi.

Code:

- [`src/segmentation/rfm_segmentation.py`](../../src/segmentation/rfm_segmentation.py)
- [`tests/test_segmentation.py`](../../tests/test_segmentation.py)

## 2. Customer Segmentation là gì?

Customer segmentation chia khách hàng thành các nhóm có hành vi tương tự để
phân tích, chăm sóc hoặc xây dựng recommendation. Nhóm không phải là ground
truth label trong dataset này. Vì vậy không dùng accuracy hay classification
metrics. Ta đánh giá bằng chất lượng hình học, kích thước cụm, độ ổn định và
khả năng giải thích.

Có hai kết quả được giữ tách biệt:

1. **RFM rule-based segments:** ngưỡng minh bạch, dễ giải thích.
2. **K-Means clusters:** nhóm do thuật toán tìm ra trong không gian feature.

Không được đặt tên K-Means cluster chỉ theo số thứ tự. Phải xem profile raw
R/F/M sau khi fit.

## 3. RFM Analysis

RFM là cách tóm tắt hành vi mua:

- **Recency:** số ngày từ lần mua hợp lệ cuối đến `reference_date`.
- **Frequency:** số distinct valid invoices.
- **Monetary:** net merchandise spend = gross valid sale + physical return.

Ví dụ: customer có `recency=5`, `frequency=10`, `monetary=1000` gần đây,
mua thường xuyên và chi tiêu cao hơn customer `recency=100`,
`frequency=1`, `monetary=20`.

Nguồn feature là `mart_customer_daily`, aggregate đến một `as_of_date`. Với
dataset thật:

- Population: **5.942 customers**.
- Frequency sum: **36.594**.
- Monetary sum: **£16,411,894.73**.
- 90 customer không có valid sale.

Customer có return-only activity có thể có monetary âm. Đây là dữ liệu hợp lệ,
không được ép về zero.

## 4. RFM Scoring

`add_rfm_scores` tạo điểm 1--5:

- Recency thấp hơn tốt hơn, nên giá trị nhỏ nhận score cao.
- Frequency cao hơn tốt hơn.
- Monetary cao hơn tốt hơn.
- Inactive customer (`frequency=0`) nhận score 1 và segment Lost Customers.

Điểm được tạo bằng rank rồi chia 5 quantile. Dùng rank `method="first"` để
qcut deterministic ngay cả khi nhiều customer có cùng giá trị. `rfm_score`
ghép ba điểm, ví dụ `545` nghĩa là recency tốt, frequency trung bình-cao,
monetary rất cao.

Ngưỡng rule thử nghiệm:

| Segment | Quy tắc |
|---|---|
| Champions | R >= 4, F >= 4, M >= 4 |
| Loyal Customers | R >= 3, F >= 3, M >= 3 |
| Potential Loyalists | R >= 3, F <= 3, M >= 2 |
| At Risk | R <= 2, F >= 3 |
| Lost Customers | frequency = 0 hoặc R <= 2, F <= 2 |
| Other | Các combination chưa được rule bao phủ |

Đây là **experimental segmentation rule**, chưa phải business contract.

Kết quả dataset thật:

| Segment | Customers |
|---|---:|
| Lost Customers | 1.601 |
| Champions | 1.282 |
| Loyal Customers | 1.128 |
| At Risk | 830 |
| Potential Loyalists | 697 |
| Other | 404 |

Tổng là 5.942, chứng minh customer coverage đầy đủ.

## 5. Unsupervised và supervised learning

Supervised learning cần target label đã biết, ví dụ churn label. Dataset hiện
không có ground truth segment/churn label. K-Means là **unsupervised learning**:
thuật toán chỉ nhận feature và tự tìm nhóm gần nhau.

Không dùng accuracy, precision, recall cho K-Means vì không có nhãn chuẩn để
đối chiếu.

## 6. K-Means hoạt động thế nào?

Với mỗi customer vector `x`, K-Means tìm centroid `mu_j` sao cho tổng
quadratic distance nhỏ:

```text
argmin Σ_i min_j ||x_i - mu_j||²
```

Quy trình lặp:

1. Khởi tạo k centroid.
2. Gán customer vào centroid gần nhất.
3. Tính lại centroid bằng trung bình các customer đã gán.
4. Lặp tới khi hội tụ.

Euclidean distance trong ba chiều R/F/M:

```text
d(x, y) = sqrt(
    (x_recency - y_recency)^2
  + (x_frequency - y_frequency)^2
  + (x_monetary - y_monetary)^2
)
```

Nếu monetary có scale lớn hơn frequency, nó sẽ chi phối khoảng cách. Vì vậy
phải transform và scale trước khi fit.

## 7. Preprocessing

### 7.1 Missing recency

90 customer không có valid sale có `recency_days=NULL`. Trong feature source,
NULL được giữ nguyên vì recency chưa có ý nghĩa. Riêng K-Means cần vector số,
nên `prepare_rfm_features` impute những customer inactive thành:

```text
max(recency của active customer) + 1
```

Đây là giá trị “kém gần đây nhất” trong input modelling, chỉ dùng ở bản sao
preprocessing và không ghi đè source.

Active customer có recency NULL bị reject vì đó là lỗi dữ liệu.

### 7.2 Monetary âm và long-tail

Không dùng `log1p(monetary)` trực tiếp vì monetary return-only có thể âm.
Code dùng signed log:

```text
signed_log1p(x) = sign(x) * log(1 + |x|)
```

Ví dụ `x=-10` thành `-log(11)`, vẫn giữ chiều âm. Sau đó
`StandardScaler` đưa từng feature về xấp xỉ mean 0 và standard deviation 1.

### 7.3 StandardScaler

```text
z = (x - mean(x)) / std(x)
```

K-Means chạy trên feature đã transform và scale; cluster profile vẫn dùng
R/F/M raw để người dùng giải thích được.

## 8. Elbow Method và Silhouette Score

**Elbow Method** xem `inertia`, tức tổng squared distance tới centroid. Inertia
luôn giảm khi tăng k, nên tìm điểm giảm thêm không còn đáng kể. Nó không phải
tiêu chuẩn duy nhất.

**Silhouette Score** của một điểm:

```text
s = (b - a) / max(a, b)
```

- `a`: khoảng cách trung bình tới cluster của chính nó.
- `b`: khoảng cách trung bình nhỏ nhất tới cluster gần nhất khác.
- Gần 1 tốt, gần 0 là overlap, âm là assignment đáng nghi.

Code `evaluate_kmeans` chạy k=2..8, trả về silhouette, inertia, min/max cluster
size và fraction cluster nhỏ nhất. `select_k_by_silhouette` chọn silhouette
cao nhất; nếu hòa thì chọn k nhỏ hơn để baseline dễ giải thích hơn.

## 9. Thực nghiệm Nexora thật

| k | Silhouette | Min size | Max size | Inertia |
|---:|---:|---:|---:|---:|
| 2 | 0.425752 | 2.452 | 3.490 | 9,326.99 |
| 3 | 0.334454 | 1.264 | 2.431 | 7,157.03 |
| 4 | 0.368869 | 119 | 2.583 | 5,511.61 |
| 5 | 0.381484 | 117 | 2.025 | 4,238.09 |
| 6 | 0.362319 | 116 | 1.754 | 3,548.26 |
| 7 | 0.350340 | 116 | 1.541 | 3,071.48 |
| 8 | 0.325621 | 116 | 1.339 | 2,776.15 |

Baseline chọn **k=2** vì silhouette cao nhất **0.425752** và không có cluster
quá nhỏ. Đây là lựa chọn thực nghiệm, chưa phải quyết định business.

Profile k=2 trên raw metrics:

| Cluster | Customers | Avg Recency | Avg Frequency | Avg Monetary | Median Monetary |
|---:|---:|---:|---:|---:|---:|
| 0 | 2.452 | 49.53 | 12.09 | £5,878.84 | £2,561.39 |
| 1 | 3.490 | 320.87 | 1.99 | £572.20 | £382.00 |

Diễn giải thận trọng:

- Cluster 0 có recency thấp hơn, frequency cao hơn và monetary cao hơn; có
  thể gọi mô tả là “recent high-value/high-frequency group”.
- Cluster 1 có activity thưa và cũ hơn, nhưng không tự động khẳng định
  churn vì không có churn ground truth.

Độ ổn định khi chạy seeds 42 và 43 đo bằng Adjusted Rand Index là **0.997306**.
ARI chỉ dùng để so sánh partition, không phải accuracy.

## 10. So sánh RFM rules và K-Means

Rule-based RFM tạo 6 nhãn dễ giải thích. K-Means k=2 tạo 2 nhóm hình học.
Crosstab thực nghiệm:

| RFM segment | Cluster 0 | Cluster 1 |
|---|---:|---:|
| Champions | 1.282 | 0 |
| Loyal Customers | 897 | 231 |
| Potential Loyalists | 122 | 575 |
| At Risk | 121 | 709 |
| Lost Customers | 0 | 1.601 |
| Other | 30 | 374 |

Hai phương pháp không có mục tiêu phải trùng nhau. RFM rules phù hợp khi cần
explainability và activation; K-Means hữu ích để phát hiện cấu trúc tự nhiên,
nhưng phụ thuộc scaling, k và metric distance.

## 11. Giải thích code

- `_require_rfm`: kiểm tra identifier, uniqueness, finite numeric values và
  active recency.
- `_quantile_score`: rank deterministic rồi chia 5 quantile.
- `add_rfm_scores`: thêm R/F/M scores và chuỗi `rfm_score`.
- `segment_by_rfm_rules`: áp dụng threshold thử nghiệm.
- `signed_log1p`: xử lý heavy-tail và monetary âm.
- `prepare_rfm_features`: copy RFM, impute inactive recency, transform và
  StandardScaler.
- `evaluate_kmeans`: benchmark nhiều k.
- `select_k_by_silhouette`: chọn k minh bạch, có tie-break.
- `fit_kmeans`: fit model với random seed cố định và trả assignments.
- `profile_clusters`: aggregate raw behavior per cluster.
- `compare_segments_and_clusters`: crosstab rule labels với ML clusters.
- `clustering_stability`: chạy hai seed và đo ARI.

## 12. Tests và reproducibility

Test file:
[`tests/test_segmentation.py`](../../tests/test_segmentation.py)

Coverage:

- RFM scoring và segment coverage.
- Negative monetary preservation.
- Missing inactive recency.
- Deterministic K-Means.
- Cluster assignment và profile.
- Silhouette bounds và k selection.
- Stability.
- Empty input.
- Invalid input.

Kết quả segmentation tests: **6 passed**.

Project full suite sau thêm dependency/code: **26 passed, 7 skipped**.
Lệnh chạy:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m pytest tests\test_segmentation.py -q
```

Experiment database thật dùng read-only feature query:

```text
fetch customer features: 1.448s
```

Không commit customer assignments, model pickle hoặc dataset lớn.

## 13. Hạn chế và approval pending

- K-Means giả định cluster gần hình cầu trong không gian Euclidean.
- k=2 tối ưu silhouette nhưng có thể quá thô cho activation campaign.
- Monetary return-only âm là hợp lệ nhưng có thể làm cluster nhạy với outlier.
- Chưa có ground truth để đánh giá business usefulness.
- Chưa có churn, margin, campaign response hoặc web behavior.
- RFM thresholds chưa phải business contract.
- Chưa productionize model registry, drift monitoring hay scheduled scoring.

## 14. Câu hỏi ôn tập

1. Vì sao phải scale R/F/M trước K-Means?
2. Vì sao không thể dùng `log1p` trực tiếp với monetary âm?
3. Silhouette gần 0 nói gì về overlap giữa các cluster?
4. Vì sao cluster ID 0 không có nghĩa là cluster tốt nhất?
5. Khi nào RFM rule-based dễ dùng hơn K-Means?
6. Vì sao accuracy không phù hợp khi chưa có ground truth segment?
7. Tại sao inactive customer giữ recency NULL ở source nhưng được impute khi fit?
8. Làm thế nào kiểm tra cluster stability khi label permutation xảy ra?

## 15. Fixes từ Customer Analytics Review

Các điểm cải tiến và sửa lỗi trong logic phân cụm và scoring:

### 15.1 K-Means Profiling và Imputation
- **Lỗi gốc:** Việc gán (impute) recency bị khuyết (NULL) thành `max + 1` được ghi đè trực tiếp lên Dataframe chứa dữ liệu gốc `source["recency_days"]`. Khi đưa Dataframe này vào `profile_clusters()`, hàm tính toán ra `average_recency` sai vì trung bình bao gồm cả các giá trị độ trễ nhân tạo khổng lồ, làm mất tính thực tế.
- **Code sửa:** Giao diện hàm `prepare_rfm_features` và `fit_kmeans` được cấu trúc lại để **không gán** trên biến `result["recency_days"]`. Phép toán impute chỉ thực hiện trên mảng chuẩn bị cho `StandardScaler` và `KMeans`. Bản gốc (`source`) trả về vẫn giữ đúng nguyên vẹn giá trị `NaN` cho các inactive customer. Điều này giúp `profile_clusters` thống kê chính xác dựa trên Recency thật.
- **Bài học rút ra:** Không bao giờ rò rỉ dữ liệu transformation/imputation (dành cho mô hình) ngược lại vào các báo cáo raw descriptives hoặc profile. Sự trong sạch của dữ liệu gốc phải được duy trì từ đầu đến cuối.

### 15.2 RFM Quantile Ties (Trường hợp bằng điểm)
- **Lỗi gốc:** Lệnh `values.rank(method="first")` tạo thứ hạng theo vị trí ban đầu trong DataFrame, dẫn đến 2 customer có R/F/M hoàn toàn bằng nhau lại có thể bị đẩy vào hai quantile khác nhau và nhận điểm (score) khác nhau một cách thiếu công bằng.
- **Code sửa:** Vẫn dùng `rank(method="first")` để chia 5 quantile đều nhau thông qua `qcut()`, sau đó dùng `.groupby(values).transform("median").round()` để ép các customer có cùng R/F/M nhận một score duy nhất (điểm trung vị làm tròn của nhóm đó). Điều này đảm bảo tính "permutation-invariant": Dù xáo trộn thứ tự dòng dữ liệu, score cho cùng giá trị R/F/M luôn giống hệt nhau.
- **Bài học rút ra:** Binning/Quantile với lượng lớn ties (ví dụ rất nhiều người có frequency = 1) là một vấn đề nhức nhối trong RFM. Cần đảm bảo hệ thống chấm điểm phải giải thích được và đối xử công bằng (deterministic) đối với các hành vi giống nhau.

### 15.3 Customer Coverage Error
- **Lỗi gốc:** Hàm `compare_segments_and_clusters` dùng phép `inner join` nhưng thiếu kiểm tra ràng buộc. Nếu 2 thuật toán bỏ sót customer hoặc sinh trùng lặp (duplicate IDs), lệnh join vẫn chạy êm ái mà không báo lỗi (silently drop).
- **Code sửa:** Thêm bước validation bắt buộc sử dụng tập hợp `set(segmented["customer_id"])` và `set(assignments["customer_id"])`. So sánh nếu có sự khác biệt về số lượng, code sẽ văng `ValueError` báo cáo chính xác khách hàng nào bị thiếu. Ngoài ra reject ngay lập tức nếu xuất hiện trùng lặp.
- **Bài học rút ra:** Luôn chặn chặn đứng nguy cơ mất mát dữ liệu ẩn (silent data drop) ở các giao điểm của các pipeline.
