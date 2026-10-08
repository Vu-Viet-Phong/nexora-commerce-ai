import numpy as np
import pandas as pd
import pytest

from src.segmentation.rfm_segmentation import (
    add_rfm_scores,
    clustering_stability,
    evaluate_kmeans,
    fit_kmeans,
    prepare_rfm_features,
    profile_clusters,
    select_k_by_silhouette,
    segment_by_rfm_rules,
)


def rfm_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "customer_id": range(1, 9),
            "recency_days": [2, 4, 8, 15, 30, 50, 80, 100],
            "frequency": [12, 10, 8, 6, 4, 2, 1, 0],
            "monetary": [500, 400, 300, 200, 100, 50, -10, 0],
        }
    )


def test_rfm_scores_and_segments_cover_every_customer() -> None:
    scored = add_rfm_scores(rfm_fixture())
    segmented = segment_by_rfm_rules(scored)
    assert scored["customer_id"].is_unique
    assert scored["rfm_score"].str.len().eq(3).all()
    assert len(segmented) == 8
    assert segmented["rfm_segment"].notna().all()
    assert segmented.loc[segmented["frequency"] == 0, "rfm_segment"].item() == (
        "Lost Customers"
    )


def test_negative_monetary_is_preserved_by_signed_transform() -> None:
    source, scaled = prepare_rfm_features(rfm_fixture())
    assert source.loc[source["customer_id"] == 7, "monetary"].item() == -10
    assert np.isfinite(scaled).all()


def test_inactive_customer_missing_recency_is_kept_null_in_raw() -> None:
    frame = rfm_fixture()
    frame.loc[7, "recency_days"] = np.nan
    source, scaled = prepare_rfm_features(frame)
    assert pd.isna(source.loc[source["customer_id"] == 8, "recency_days"].item())
    # Should be valid in scaled
    assert np.isfinite(scaled).all()


def test_kmeans_is_deterministic_and_assigns_every_customer() -> None:
    first, _, _ = fit_kmeans(rfm_fixture(), k=2)
    second, _, _ = fit_kmeans(rfm_fixture(), k=2)
    assert first["cluster"].tolist() == second["cluster"].tolist()
    assert first["customer_id"].is_unique
    assert first["cluster"].notna().all()


def test_evaluation_and_profile_are_valid() -> None:
    _, scaled = prepare_rfm_features(rfm_fixture())
    evaluation = evaluate_kmeans(scaled, k_values=(2, 3))
    assignments, _, _ = fit_kmeans(rfm_fixture(), k=2)
    profile = profile_clusters(assignments)
    assert set(evaluation["k"]) == {2, 3}
    assert evaluation["silhouette_score"].between(-1, 1).all()
    assert select_k_by_silhouette(evaluation) in {2, 3}
    assert profile["customer_count"].sum() == 8
    assert clustering_stability(rfm_fixture(), k=2) >= 0


def test_invalid_and_empty_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="missing RFM"):
        add_rfm_scores(pd.DataFrame({"customer_id": [1]}))
    with pytest.raises(ValueError, match="finite"):
        prepare_rfm_features(
            pd.DataFrame(
                {
                    "customer_id": [1],
                    "recency_days": [1],
                    "frequency": [1],
                    "monetary": [np.nan],
                }
            )
        )
    with pytest.raises(ValueError, match="number of customers"):
        evaluate_kmeans(np.empty((0, 3)), k_values=(2,))


def test_rfm_scoring_is_permutation_invariant() -> None:
    frame1 = rfm_fixture()
    frame2 = frame1.sample(frac=1, random_state=42).reset_index(drop=True)
    
    scored1 = add_rfm_scores(frame1)
    scored2 = add_rfm_scores(frame2)
    
    scored1_sorted = scored1.sort_values("customer_id").reset_index(drop=True)
    scored2_sorted = scored2.sort_values("customer_id").reset_index(drop=True)
    
    pd.testing.assert_frame_equal(scored1_sorted, scored2_sorted)


def test_rfm_scoring_assigns_same_score_to_ties() -> None:
    frame = rfm_fixture()
    # Create a tie in frequency
    frame.loc[0, "frequency"] = 10
    frame.loc[1, "frequency"] = 10
    scored = add_rfm_scores(frame)
    # They should have the same frequency_score
    f_score_0 = scored.loc[scored["customer_id"] == 1, "frequency_score"].item()
    f_score_1 = scored.loc[scored["customer_id"] == 2, "frequency_score"].item()
    assert f_score_0 == f_score_1
