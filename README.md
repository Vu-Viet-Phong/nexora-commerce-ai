<div align="center">

# NEXORA COMMERCE AI

### From raw retail transactions to decision-ready customer intelligence.

**An end-to-end data engineering, analytics, and machine learning project**  
Built around a reproducible PostgreSQL pipeline, explainable customer segmentation, and an interactive Streamlit dashboard.

<p>
  <a href="https://www.python.org/"><img alt="Python 3.11" src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white"></a>
  <a href="https://www.postgresql.org/"><img alt="PostgreSQL 16" src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white"></a>
  <a href="https://streamlit.io/"><img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white"></a>
  <a href="https://scikit-learn.org/"><img alt="scikit-learn" src="https://img.shields.io/badge/scikit--learn-ML%20Baseline-F7931E?style=for-the-badge&logo=scikitlearn&logoColor=white"></a>
</p>

<p>
  <img alt="Project status: Analytics MVP merged" src="https://img.shields.io/badge/Status-Analytics%20MVP%20Merged-208050?style=flat-square">
  <img alt="Data workflow: PostgreSQL to dashboard" src="https://img.shields.io/badge/Workflow-ETL%20%E2%86%92%20SQL%20%E2%86%92%20ML%20%E2%86%92%20BI-465A72?style=flat-square">
  <img alt="Project focus: Learning and portfolio" src="https://img.shields.io/badge/Focus-Learning%20%26%20Portfolio-6F42C1?style=flat-square">
</p>

**[Overview](#overview)** · **[Architecture](#system-architecture)** · **[Features](#what-is-implemented)** · **[Quick Start](#quick-start)** · **[Documentation](#documentation)** · **[Roadmap](#roadmap)**

</div>

---

## Overview

**Nexora Commerce AI** transforms the **UCI Online Retail II** dataset into an analytical foundation for e-commerce decision-making. Rather than treating machine learning as an isolated notebook, the project connects data ingestion, auditability, relational modeling, SQL reporting, customer feature engineering, unsupervised learning, and a BI interface.

The current **Analytics MVP is merged into `main`** via three development pull requests:

- **[PR #1 — Automated Data Quality](https://github.com/Vu-Viet-Phong/nexora-commerce-ai/pull/1)**: relational integrity, source reconciliation, and validation reporting.
- **[PR #2 — Customer Analytics & Segmentation](https://github.com/Vu-Viet-Phong/nexora-commerce-ai/pull/2)**: customer features, EDA, rule-based RFM, and K-Means baseline.
- **[PR #3 — Streamlit Dashboard](https://github.com/Vu-Viet-Phong/nexora-commerce-ai/pull/3)**: sales, customer, and RFM analytics in one interface.

> **Project maturity:** This is an integrated **analytics MVP**, not a deployed or production-certified e-commerce service. Churn prediction, forecasting, recommendation, and deployment are future work.

### Dataset at a glance

| Metric | Observed during project validation |
|:--|--:|
| Transaction / invoice lines | **1,044,848** |
| Distinct invoices | **53,628** |
| Identified customers | **5,942** |
| Products | **5,131** |

<sub>These are reported results from the project's full-data validation runs, not synthetic demonstration values. Counts may depend on the cleaning rules and reporting scope; unidentified customers are not silently discarded from the underlying transactional source.</sub>

---

## System Architecture

```mermaid
flowchart TD
    A["UCI Online Retail II<br/>Raw Excel"] --> B["Stage 1<br/>Ingestion · Cleaning · Audit"]
    B --> C["Processed Parquet<br/>Reproducible datasets"]
    C --> D["PostgreSQL<br/>Relational core"]
    D --> E["SQL Analytics Marts<br/>Sales · Customer Daily · Snapshot"]
    C -. "Source reconciliation" .-> Q["Data Quality Engine"]
    D -. "Integrity checks" .-> Q
    E --> F["Customer Analytics<br/>EDA · RFM features"]
    F --> G["Segmentation<br/>RFM rules · K-Means"]
    E --> H["Streamlit Dashboard"]
    G --> H
    Q -. "Validation reports" .-> I["QA & Learning Notes"]
    H --> J["Sales and Customer Insights"]
```

**Design principles**

- **Traceable data:** raw data is preserved; cleaning decisions and reconciliation are documented.
- **SQL-first analytics:** aggregate in PostgreSQL marts before loading compact customer-level features into Python.
- **Reproducible experiments:** deterministic fixtures and documented ML assumptions.
- **Clear metric semantics:** distinguish net/gross sales, invoice segments versus distinct orders, and lifetime snapshots versus date-filtered metrics.
- **Safe integration:** isolated Git worktrees and database test schemas; no customer datasets or secrets in Git.

---

## What Is Implemented

<table>
  <thead>
    <tr><th align="left">Layer</th><th align="left">Capabilities</th><th align="center">Status</th></tr>
  </thead>
  <tbody>
    <tr><td><strong>01 · Data Engineering</strong></td><td>Checksum-aware ingestion, cleaning, deduplication rules, audit summaries, Parquet outputs</td><td align="center">Integrated</td></tr>
    <tr><td><strong>02 · PostgreSQL</strong></td><td>Relational schema, atomic loader, reconciliation, SQL analytics marts</td><td align="center">Integrated</td></tr>
    <tr><td><strong>03 · Data Quality</strong></td><td>Core integrity checks, source comparison, structured reports, isolated integration tests</td><td align="center">Integrated¹</td></tr>
    <tr><td><strong>04 · Customer Analytics</strong></td><td>EDA, customer-level features, RFM metrics, coverage checks</td><td align="center">Integrated</td></tr>
    <tr><td><strong>05 · Machine Learning</strong></td><td>RFM rule-based segmentation, K-Means baseline, cluster evaluation and profiling</td><td align="center">Baseline</td></tr>
    <tr><td><strong>06 · Dashboard</strong></td><td>Sales Overview, Customer Analytics, RFM Segmentation</td><td align="center">MVP</td></tr>
    <tr><td><strong>07 · Predictive AI</strong></td><td>Churn, forecasting, recommendation, product search</td><td align="center">Planned</td></tr>
  </tbody>
</table>

<sub>¹ Core/source validation was integrated; three SQL mart quality checks were explicitly deferred during that acceptance scope. “Integrated” does not mean every future quality gate or production criterion is complete.</sub>

### Analytics capabilities

| Sales Overview | Customer Intelligence | Segmentation |
|---|---|---|
| Gross / net revenue | Recency, frequency, monetary | RFM score and segment |
| Returns and refunds | Average order value | Segment sizes and contribution |
| Invoice-segment reporting | Lifetime customer snapshot | K-Means cluster profiling |
| Country and time trends | Repeat purchasing behavior | Consistent RFM logic shared with ML |

> **Analytics note:** An *invoice segment* is not automatically a unique invoice when results are rolled up across multiple merchandise classifications or geographic groups. The dashboard documents this distinction rather than presenting a potentially double-counted metric as global distinct orders.

---

## Tech Stack

| Area | Technologies |
|---|---|
| Programming | Python 3.11 |
| Data processing | Pandas, NumPy, PyArrow |
| Storage and SQL | PostgreSQL 16, SQLAlchemy, psycopg |
| Machine learning | scikit-learn · RFM rules · K-Means |
| Application | Streamlit |
| Testing | pytest · SQLite fixtures · isolated PostgreSQL tests |
| Collaboration | Git · GitHub · feature branches / worktrees |
| Documentation | Markdown learning notes and QA reports |

---

## Repository Structure

```text
nexora-commerce-ai/
├── app/
│   ├── dashboard.py                 # Streamlit app entry point
│   └── queries.py                   # PostgreSQL query / metric layer
├── configs/                         # Project configuration
├── data/
│   ├── raw/                         # Local source data (not committed)
│   ├── interim/                     # Cached/intermediate data
│   └── processed/                   # Cleaned Parquet outputs
├── deployment/                     # Development deployment configuration
├── docs/
│   ├── learning/                     # Vietnamese technical learning notes
│   └── PROJECT_LEARNING_LOG.md       # Development and learning journal
├── notebooks/                      # Data audit and exploratory notebooks
├── sql/
│   ├── schema.sql                   # PostgreSQL relational schema
│   └── marts/                       # Reusable analytics marts
├── src/
│   ├── data/                        # Ingestion, cleaning, PostgreSQL loading
│   ├── quality/                     # Data quality and reconciliation
│   ├── analytics/                   # Customer analytics / feature engineering
│   └── segmentation/                # RFM and K-Means
├── tests/                           # Unit, contract, and integration tests
├── .env.example                     # Configuration template, not credentials
├── pyproject.toml                   # Python project / dependencies
└── README.md
```

*Selected folders and files are shown for readability; see the repository for the full tree.*

---

## Quick Start

The project is developed on **Windows with native PostgreSQL**. The following commands are intended to run from the repository root in **PowerShell**.

### 1. Clone and create a Python environment

```powershell
git clone https://github.com/Vu-Viet-Phong/nexora-commerce-ai.git
cd nexora-commerce-ai
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

> If PowerShell prevents script activation, use `.\.venv\Scripts\python.exe` instead of `python` in subsequent commands. Dependencies are declared in [`pyproject.toml`](pyproject.toml).

### 2. Prepare the data

Download the **UCI Online Retail II** workbook from its original dataset source and place it inside:

```text
data/raw/uci/
```

Keep original input files unchanged; the repository intentionally does not commit large raw retail datasets.

Run the ingestion and cleaning pipeline:

```powershell
python -m src.data.pipeline
```

Expected local artifacts include:

```text
data/interim/transactions_raw.parquet
data/processed/transactions_clean.parquet
data/processed/cleaning_summary.json
```

### 3. Configure PostgreSQL

Create a local `.env` from the provided example:

```powershell
Copy-Item .env.example .env
```

Configure the connection values required by the project's SQLAlchemy modules. The dashboard query layer accepts `DATABASE_URL` (or `NEXORA_DATABASE_URL`) and supports the `postgresql+psycopg://` dialect.

```text
DATABASE_URL=postgresql+psycopg://USER:YOUR_URL_ENCODED_PASSWORD@localhost:5432/DATABASE
```

Use a **separate PostgreSQL role with `SELECT` privileges** when connecting the dashboard. Do not copy an example username/password into production, and never commit `.env`.

The database layer uses [`sql/schema.sql`](sql/schema.sql), the loader under [`src/data/`](src/data/), and the three SQL scripts in [`sql/marts/`](sql/marts/). For initial schema creation, loading, metric definitions and integration details, follow the [Stage 2 PostgreSQL learning notes](docs/learning/stage_02_postgresql_sql.md); do not run destructive setup scripts against an existing populated database without reviewing them.

### 4. Launch the dashboard

Once the PostgreSQL marts are populated:

```powershell
python -m streamlit run app/dashboard.py
```

Open **http://localhost:8501** and explore the three views:

1. **Sales Overview** — revenue, returns, time trends, geographic performance.
2. **Customer Analytics** — customer KPIs, distribution, daily activity, top customers.
3. **RFM Segmentation** — segment overview, score distributions, customer drilldown.

<details>
<summary><strong>Dashboard preview — adding screenshots</strong></summary>

When a verified screenshot is available, save it under `docs/assets/dashboard_overview.png` and insert this into the README:

```markdown
![Nexora Dashboard](docs/assets/dashboard_overview.png)
```

A screenshot is not bundled with this README because no verified image asset exists in the repository materials provided.

</details>

---

## Tests and Data Quality

Run the standard fast tests:

```powershell
python -m pytest -ra tests/
```

Run the dashboard tests alone while working on the interface:

```powershell
python -m pytest -ra tests/test_dashboard.py
```

PostgreSQL integration tests are intentionally isolated and may require explicit flags and a dedicated test database. For example, the Data Quality suite supports:

```powershell
python -m pytest -ra tests/test_quality/test_postgres.py --quality-postgres
```

**Do not enable database-destructive integration tests against the primary application database.** Skipped tests can be intentional and must not be reported as passed.

### Validation evidence

| Check | Reported outcome |
|---|---|
| Integrated regression suite | **165 passed, 35 skipped** |
| Isolated PostgreSQL quality suite | **28 passed** |
| Dashboard-specific tests after RFM integration | **23 passed** |
| Customer feature verification | **5,942 customers** |

<sub>Results above are from the project's October 2026 QA/integration reports, not a live CI badge or a claim that tests were rerun by this README author. The three mart validation gates deferred during Stage 2 should be tracked separately.</sub>

---

## Documentation

A core goal of this repository is to make **engineering decisions understandable and reproducible**. Most implementation learning notes are written in **Vietnamese**, alongside Python and SQL examples.

| Document | Focus |
|---|---|
| [`docs/PROJECT_LEARNING_LOG.md`](docs/PROJECT_LEARNING_LOG.md) | Development chronology and learning outcomes |
| [`docs/learning/stage_02_postgresql_sql.md`](docs/learning/stage_02_postgresql_sql.md) | Schema, loading, marts, reconciliation |
| [`docs/learning/stage_02_data_quality.md`](docs/learning/stage_02_data_quality.md) | Data-quality checks and design |
| [`docs/learning/customer_analytics_feature_engineering.md`](docs/learning/customer_analytics_feature_engineering.md) | Customer features and EDA |
| [`docs/learning/customer_segmentation_ml.md`](docs/learning/customer_segmentation_ml.md) | RFM and K-Means theory and experiments |
| [`docs/learning/analytics_dashboard_streamlit.md`](docs/learning/analytics_dashboard_streamlit.md) | Streamlit dashboard, queries and fixes |

Integration reports and acceptance documents are maintained in the `docs/` area. Some historical QA reports may live on review branches and should not be mistaken for files already merged into `main`.

---

## Roadmap

The project is developed incrementally, with **a working analytics foundation before expanding into predictive and generative AI**.

- [x] Raw ingestion, cleaning, audit, and Parquet pipeline
- [x] PostgreSQL relational core and SQL analytics marts
- [x] Source/core Data Quality validation and integration
- [x] Customer feature engineering and EDA
- [x] Rule-based RFM and K-Means clustering baseline
- [x] Streamlit Analytics MVP integrated into `main`
- [ ] Churn / repeat-purchase prediction with leakage-safe temporal validation
- [ ] Demand and sales forecasting with rolling evaluation
- [ ] Recommendation systems and multimodal product intelligence
- [ ] API and application integration
- [ ] AI analyst / Text-to-SQL and document retrieval
- [ ] Deployment, observability, and MLOps

**Next planned milestone:** **Customer Churn Prediction** — define the prediction target, prediction horizon, training cutoffs, and baseline before selecting a complex model.

---

## Responsible Data Practices

- **Local source data stays local.** `.env`, credentials, exports, and customer-level artifacts must not be committed.
- **Read-only analytics by default.** Use a least-privilege PostgreSQL role for Streamlit and live analysis.
- **Preserve business meaning.** Returns, cancellations, missing customer identifiers, and negative monetary values are treated explicitly.
- **Avoid misleading metrics.** An invoice segment is not necessarily a globally unique order; historical snapshots must not be presented as point-in-time features without evidence.
- **Restrict customer drilldowns.** The MVP is not intended for unrestricted public access to customer-level tables.

---

<div align="center">

### Built to learn. Designed to scale.

**Nexora Commerce AI** · Data Engineering · Analytics · Machine Learning

Created and maintained by **[Vu-Viet-Phong](https://github.com/Vu-Viet-Phong)**

[Back to top](#nexora-commerce-ai)

</div>
