from datetime import date

import pandas as pd
import pytest

from src.analytics.customer_analytics import (
    CUSTOMER_FEATURE_COLUMNS,
    build_customer_features_query,
    validate_customer_features,
)


def feature_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "customer_id": 10,
                "primary_country": "United Kingdom",
                "reference_date": date(2011, 12, 10),
                "recency_days": 2,
                "frequency": 3,
                "monetary": 120.50,
                "average_order_value": 40.17,
                "tenure_days": 30,
            },
            {
                "customer_id": 20,
                "primary_country": "France",
                "reference_date": date(2011, 12, 10),
                "recency_days": None,
                "frequency": 0,
                "monetary": 0,
                "average_order_value": None,
                "tenure_days": None,
            },
        ],
        columns=CUSTOMER_FEATURE_COLUMNS,
    )


def test_feature_validation_accepts_empty_frame_with_schema() -> None:
    validate_customer_features(pd.DataFrame(columns=CUSTOMER_FEATURE_COLUMNS))


def test_feature_validation_rejects_duplicate_customer_ids() -> None:
    frame = pd.concat([feature_frame(), feature_frame().iloc[[0]]])
    with pytest.raises(ValueError, match="unique"):
        validate_customer_features(frame)


def test_feature_validation_rejects_null_customer_ids() -> None:
    frame = feature_frame()
    frame.loc[0, "customer_id"] = None
    with pytest.raises(ValueError, match="NULL"):
        validate_customer_features(frame)


def test_feature_validation_rejects_negative_recency() -> None:
    frame = feature_frame()
    frame.loc[0, "recency_days"] = -1
    with pytest.raises(ValueError, match="recency_days"):
        validate_customer_features(frame)


def test_feature_query_is_bounded_and_reproducible() -> None:
    query = build_customer_features_query()
    assert query == build_customer_features_query()
    assert "mart_customer_daily" in query
    assert "calendar_day <= CAST(:as_of_date AS DATE)" in query
    assert "customer_id IS NOT NULL" not in query


def test_feature_validation_rejects_all_null_frequency() -> None:
    import numpy as np
    frame = feature_frame()
    frame["frequency"] = np.nan
    with pytest.raises(ValueError, match="entirely NULL"):
        validate_customer_features(frame)


def test_feature_validation_rejects_invalid_strings() -> None:
    frame = feature_frame()
    frame.loc[0, "frequency"] = "abc"
    with pytest.raises(ValueError, match="non-numeric"):
        validate_customer_features(frame)


def test_feature_validation_rejects_infinity() -> None:
    import numpy as np
    frame = feature_frame()
    frame.loc[0, "monetary"] = np.inf
    with pytest.raises(ValueError, match="non-finite"):
        validate_customer_features(frame)


def test_feature_validation_rejects_missing_recency_for_active() -> None:
    import numpy as np
    frame = feature_frame()
    frame.loc[0, "recency_days"] = np.nan
    with pytest.raises(ValueError, match="must not be NULL when frequency > 0"):
        validate_customer_features(frame)


def test_feature_validation_rejects_recency_for_inactive() -> None:
    frame = feature_frame()
    frame.loc[1, "recency_days"] = 10  # freq is 0 here
    with pytest.raises(ValueError, match="must be NULL when frequency == 0"):
        validate_customer_features(frame)


def test_temporal_leakage_warning() -> None:
    from src.analytics.customer_analytics import fetch_customer_features
    from unittest.mock import MagicMock
    import warnings
    
    mock_engine = MagicMock()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            # We mock pd.read_sql and validate_customer_features
            import pandas as pd
            from src.analytics import customer_analytics
            original_read = pd.read_sql
            original_val = customer_analytics.validate_customer_features
            pd.read_sql = MagicMock(return_value=pd.DataFrame())
            customer_analytics.validate_customer_features = MagicMock()
            
            fetch_customer_features(mock_engine, as_of_date=date(2010, 1, 1))
            
            assert len(w) == 1
            assert "Temporal leakage" in str(w[-1].message)
        finally:
            pd.read_sql = original_read
            customer_analytics.validate_customer_features = original_val
