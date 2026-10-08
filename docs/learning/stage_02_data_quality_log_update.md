# Nội dung để tích hợp vào PROJECT_LEARNING_LOG.md khi merge

Đây là phần cập nhật riêng của Codex. Không sửa trực tiếp learning log của
Copilot trong phiên phát triển song song.

## Stage 02 — Milestone 2.5: Automated Data Quality & Validation

Trạng thái: core implementation và fixture verification đã bàn giao;
chờ tích hợp/nghiệm thu Milestone 2.4 và kiểm chứng full-data theo lựa chọn của
owner. **Không tự đánh dấu APPROVED.**

- Triển khai src/quality với 32 SQL core checks, schema/NUMERIC contracts,
  offline validators, Parquet source reconciliation, structured results và CLI.
- Core runner dùng REPEATABLE READ + SET TRANSACTION READ ONLY, bound source
  parameters, savepoints và timeout; không DDL/DML hay tự gọi loader.
- Bảo toàn guest NULL, retained duplicate lines, cancellations, inventory/bad-debt
  adjustments và non-product flags theo code Stage 1/2 hiện có.
- Source comparison dùng counts, hashed dimension keys, 15 flags, exact Decimal
  aggregates, same-key payload fingerprints và SHA-256 provenance.
- Raw price flags được xác minh trước rounding; stored zero không bị nhầm với
  raw zero; signed zero được canonicalize khi so fingerprint.
- CLI xuất JSON/Markdown và exit 0/1/2; gate_summary ghi rõ core/source scope,
  overall summary vẫn thể hiện ba marts SKIP.
- Fixtures nhỏ deterministic kiểm missing fields, duplicate grain, source-scoped
  FK, nghiệp vụ, monetary mismatch, malformed source, error recovery và CLI.
- Kết quả thực chạy: quality + Stage 1 offline 72 passed/24 skipped trong 3,23 s;
  private PostgreSQL 16.15 quality suite 88 passed/1 skipped trong 11,53 s;
  static DDL --noconftest 8 passed trong 0,06 s.
- Một full-data test opt-in chưa chạy; chưa chứng nhận development warehouse.
- Không đọc .env/password, không hard-code credentials, không track datasets/
  generated reports; staged scope và credential-URL/artifact checks đã chạy.
- Git checkpoints code: c5fcc96 (core), 0139cb4 (source/tests), ec18142 (CLI/gate).
  Checkpoint tài liệu tiếp theo có thể tra bằng git log của feature branch.
- Learning Notes: docs/learning/stage_02_data_quality.md.
- Operational guide: docs/quality_validation.md.
- Deferred mart contracts: docs/quality_marts_integration.md.

Kiến thức chính: grain phải phản ánh retained source row; nullable fact customer
không phải orphan; Decimal phải đi cùng rounding order thống nhất; counts không
đủ chứng minh fidelity; SKIP không đồng nghĩa PASS; quality gate kỹ thuật không
thay thế approval của milestone.
