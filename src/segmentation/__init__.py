"""Reproducible RFM and K-Means customer segmentation baselines."""

from .rfm_segmentation import (
    RFM_COLUMNS,
    add_rfm_scores,
    compare_segments_and_clusters,
    evaluate_kmeans,
    fit_kmeans,
    prepare_rfm_features,
    profile_clusters,
    select_k_by_silhouette,
    segment_by_rfm_rules,
)

__all__ = [
    "RFM_COLUMNS",
    "add_rfm_scores",
    "compare_segments_and_clusters",
    "evaluate_kmeans",
    "fit_kmeans",
    "prepare_rfm_features",
    "profile_clusters",
    "select_k_by_silhouette",
    "segment_by_rfm_rules",
]
