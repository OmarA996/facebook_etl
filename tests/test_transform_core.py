import pandas as pd

from src.etl.transform.core import flatten_json


def test_flatten_json_coerces_numeric_like_columns():
    df = flatten_json(
        [
            {"spend": "12.5", "clicks": "7"},
            {"spend": "0", "clicks": "3"},
        ]
    )

    assert pd.api.types.is_numeric_dtype(df["spend"])
    assert pd.api.types.is_numeric_dtype(df["clicks"])
    assert df.loc[0, "spend"] == 12.5
    assert df.loc[1, "clicks"] == 3


def test_flatten_json_leaves_mixed_text_columns_unchanged():
    df = flatten_json(
        [
            {"name": "Account A", "currency": "USD"},
            {"name": "Account B", "currency": "EUR"},
        ]
    )

    assert list(df["name"]) == ["Account A", "Account B"]
    assert list(df["currency"]) == ["USD", "EUR"]


def test_flatten_json_keeps_id_like_columns_as_text():
    df = flatten_json(
        [
            {"id": "1234567890123456789", "account_id": "9876543210123456789"},
        ]
    )

    assert df.loc[0, "id"] == "1234567890123456789"
    assert df.loc[0, "account_id"] == "9876543210123456789"
