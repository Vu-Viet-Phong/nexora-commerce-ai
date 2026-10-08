"""Explainable RFM rules and a reproducible K-Means baseline."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

RFM_COLUMNS = ("recency_days", "frequency", "monetary")
DEFAULT_RANDOM_STATE = 42
RFM_SCORE_COLUMNS = ("recency_score", "frequency_score", "monetary_score")
SEGMENT_LABELS = (
    "Champions",
    "Loyal Customers",
    "Potential Loyalists",
    "At Risk",
    "Lost Customers",
)


def _require_rfm(frame: pd.DataFrame) -> None:
    missing = set(RFM_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"missing RFM columns: {sorted(missing)}")
    if "customer_id" not in frame.columns:
        raise ValueError("customer_id is required")
    if frame["customer_id"].isna().any() or frame["customer_id"].duplicated().any():
        raise ValueError("customer_id must be non-null and unique")
    for column in RFM_COLUMNS:
        values = pd.to_numeric(frame[column], errors="coerce")
        allowed_missing = column == "recency_days"
        if values.isna().any() and not allowed_missing:
            raise ValueError(f"{column} must contain finite numeric values")
        if values.notna().any() and not np.isfinite(values.dropna()).all():
            raise ValueError(f"{column} must contain finite numeric values")
    if frame["recency_days"].isna().any() and (
        frame.loc[frame["recency_days"].isna(), "frequency"] > 0
    ).any():
        raise ValueError("active customers require recency_days")


def _quantile_score(values: pd.Series, *, higher_is_better: bool) -> pd.Series:
    ranks = values.rank(method="first", ascending=higher_is_better)
    pure_scores = pd.qcut(ranks, q=5, labels=False, duplicates="drop") + 1
    scores = pure_scores.groupby(values).transform("median").round()
    return scores.astype("Int64")


def add_rfm_scores(frame: pd.DataFrame) -> pd.DataFrame:
    """Add transparent 1-5 scores; inactive customers receive score 1."""
    _require_rfm(frame)
    result = frame.copy()
    active = result["frequency"] > 0
    result["recency_score"] = 1
    result["frequency_score"] = 1
    result["monetary_score"] = 1
    active_frame = result.loc[active]
    if not active_frame.empty:
        result.loc[active, "recency_score"] = _quantile_score(
            active_frame["recency_days"], higher_is_better=False
        ).to_numpy()
        result.loc[active, "frequency_score"] = _quantile_score(
            active_frame["frequency"], higher_is_better=True
        ).to_numpy()
        result.loc[active, "monetary_score"] = _quantile_score(
            active_frame["monetary"], higher_is_better=True
        ).to_numpy()
    for column in RFM_SCORE_COLUMNS:
        result[column] = result[column].astype("int64")
    result["rfm_score"] = (
        result["recency_score"].astype(str)
        + result["frequency_score"].astype(str)
        + result["monetary_score"].astype(str)
    )
    return result


def segment_by_rfm_rules(scored: pd.DataFrame) -> pd.DataFrame:
    """Apply experimental, documented RFM thresholds to scored customers."""
    missing = set(RFM_SCORE_COLUMNS) - set(scored.columns)
    if missing:
        raise ValueError(f"missing RFM score columns: {sorted(missing)}")
    result = scored.copy()
    r = result["recency_score"]
    f = result["frequency_score"]
    m = result["monetary_score"]
    result["rfm_segment"] = np.select(
        [
            (f == 1) & (result["frequency"] == 0),
            (r >= 4) & (f >= 4) & (m >= 4),
            (r >= 3) & (f >= 3) & (m >= 3),
            (r >= 3) & (f <= 3) & (m >= 2),
            (r <= 2) & (f >= 3),
            (r <= 2) & (f <= 2),
        ],
        [
            "Lost Customers",
            "Champions",
            "Loyal Customers",
            "Potential Loyalists",
            "At Risk",
            "Lost Customers",
        ],
        default="Other",
    )
    return result


def signed_log1p(values: pd.Series) -> pd.Series:
    """Compress heavy tails while preserving the sign of return-only monetary."""
    numeric = pd.to_numeric(values, errors="raise").astype(float)
    return np.sign(numeric) * np.log1p(np.abs(numeric))


def prepare_rfm_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Return validated IDs/features and scaled values used by K-Means."""
    _require_rfm(frame)
    result = frame.loc[:, ["customer_id", *RFM_COLUMNS]].copy()
    for column in RFM_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="raise").astype(float)
        
    active_recency = result.loc[result["frequency"] > 0, "recency_days"]
    recency_fill = (
        float(active_recency.max() + 1) if not active_recency.empty else 1.0
    )
    imputed_recency = result["recency_days"].fillna(recency_fill)
    
    transformed = pd.DataFrame(
        {
            "recency_days": signed_log1p(imputed_recency),
            "frequency": signed_log1p(result["frequency"]),
            "monetary": signed_log1p(result["monetary"]),
        },
        index=result.index,
    )
    scaler = StandardScaler()
    scaled = scaler.fit_transform(transformed)
    return result, scaled


def evaluate_kmeans(
    scaled_features: np.ndarray,
    k_values: Iterable[int] = range(2, 7),
    *,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> pd.DataFrame:
    """Compare candidate k using silhouette and cluster size diagnostics."""
    rows: list[dict[str, float | int]] = []
    sample_count = len(scaled_features)
    for k in k_values:
        if k < 2 or k >= sample_count:
            raise ValueError("each k must satisfy 2 <= k < number of customers")
        model = KMeans(n_clusters=k, random_state=random_state, n_init=20)
        labels = model.fit_predict(scaled_features)
        counts = np.bincount(labels, minlength=k)
        rows.append(
            {
                "k": k,
                "silhouette_score": float(silhouette_score(scaled_features, labels)),
                "min_cluster_size": int(counts.min()),
                "max_cluster_size": int(counts.max()),
                "small_cluster_fraction": float(counts.min() / sample_count),
                "inertia": float(model.inertia_),
            }
        )
    return pd.DataFrame(rows)


def select_k_by_silhouette(evaluation: pd.DataFrame) -> int:
    """Select the highest silhouette score, preferring the smaller k on ties."""
    required = {"k", "silhouette_score"}
    if not required <= set(evaluation.columns) or evaluation.empty:
        raise ValueError("evaluation must contain k and silhouette_score rows")
    return int(
        evaluation.sort_values(
            ["silhouette_score", "k"], ascending=[False, True]
        ).iloc[0]["k"]
    )


def fit_kmeans(
    frame: pd.DataFrame,
    *,
    k: int,
    random_state: int = DEFAULT_RANDOM_STATE,
) -> tuple[pd.DataFrame, KMeans, StandardScaler]:
    """Fit deterministic K-Means and return assignments with preprocessing."""
    source, scaled = prepare_rfm_features(frame)
    model = KMeans(n_clusters=k, random_state=random_state, n_init=20)
    result = source.copy()
    result["cluster"] = model.fit_predict(scaled)
    
    scaler = StandardScaler()
    active_recency = source.loc[source["frequency"] > 0, "recency_days"]
    recency_fill = (
        float(active_recency.max() + 1) if not active_recency.empty else 1.0
    )
    imputed_recency = source["recency_days"].fillna(recency_fill)
    transformed = pd.DataFrame(
        {
            "recency_days": signed_log1p(imputed_recency),
            "frequency": signed_log1p(source["frequency"]),
            "monetary": signed_log1p(source["monetary"]),
        },
        index=source.index
    )
    scaler.fit(transformed)
    return result, model, scaler


def profile_clusters(assignments: pd.DataFrame) -> pd.DataFrame:
    """Summarize raw RFM behavior per cluster, not transformed values."""
    _require_rfm(assignments)
    if "cluster" not in assignments.columns:
        raise ValueError("cluster assignment is required")
    return (
        assignments.groupby("cluster", as_index=False)
        .agg(
            customer_count=("customer_id", "size"),
            average_recency=("recency_days", "mean"),
            average_frequency=("frequency", "mean"),
            average_monetary=("monetary", "mean"),
            median_monetary=("monetary", "median"),
        )
        .sort_values("cluster")
        .reset_index(drop=True)
    )


def compare_segments_and_clusters(
    segmented: pd.DataFrame, assignments: pd.DataFrame
) -> pd.DataFrame:
    """Cross-tab experimental RFM labels against unsupervised clusters."""
    if "rfm_segment" not in segmented.columns or "cluster" not in assignments.columns:
        raise ValueError("both RFM segments and clusters are required")
        
    if segmented["customer_id"].duplicated().any() or assignments["customer_id"].duplicated().any():
        raise ValueError("customer_id must be unique in both dataframes")
        
    seg_ids = set(segmented["customer_id"])
    assign_ids = set(assignments["customer_id"])
    
    if seg_ids != assign_ids:
        raise ValueError(
            f"customer_id sets do not match. "
            f"Missing in assignments: {len(seg_ids - assign_ids)}, "
            f"missing in segmented: {len(assign_ids - seg_ids)}"
        )

    merged = segmented[["customer_id", "rfm_segment"]].merge(
        assignments[["customer_id", "cluster"]],
        on="customer_id",
        how="inner",
        validate="one_to_one",
    )
    return pd.crosstab(merged["rfm_segment"], merged["cluster"])


def clustering_stability(
    frame: pd.DataFrame,
    *,
    k: int,
    seeds: tuple[int, int] = (42, 43),
) -> float:
    """Measure label-permutation-safe stability with Adjusted Rand Index."""
    _, first, _ = fit_kmeans(frame, k=k, random_state=seeds[0])
    first_labels = first.labels_
    _, second, _ = fit_kmeans(frame, k=k, random_state=seeds[1])
    return float(adjusted_rand_score(first_labels, second.labels_))
