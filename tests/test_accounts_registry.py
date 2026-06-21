import pandas as pd

from src.etl.pipelines.accounts_registry import _merge_registry, _normalize_registry_df


def test_normalize_registry_df_builds_expected_columns():
    df = _normalize_registry_df(
        [
            {"id": "act_1", "name": "Account A", "account_status": "1"},
            {"id": "act_2", "name": "Account B", "account_status": 2},
        ]
    )

    assert list(df.columns) == [
        "account_id",
        "account_name",
        "account_status",
        "profile_name",
        "include_in_etl",
        "notes",
    ]
    assert df.loc[0, "account_id"] == "act_1"
    assert df.loc[0, "account_name"] == "Account A"
    assert bool(df.loc[0, "include_in_etl"]) is True


def test_merge_registry_preserves_existing_include_flag_and_notes():
    existing = pd.DataFrame(
        [
            {
                "account_id": "act_1",
                "account_name": "Old Name",
                "account_status": 1,
                "profile_name": "freelance",
                "include_in_etl": False,
                "notes": "skip this one",
            }
        ]
    )
    fresh = _normalize_registry_df(
        [
            {"id": "act_1", "name": "New Name", "account_status": "2"},
            {"id": "act_2", "name": "Second", "account_status": "1"},
        ]
    )

    merged = _merge_registry(existing, fresh)

    row1 = merged.loc[merged["account_id"] == "act_1"].iloc[0]
    row2 = merged.loc[merged["account_id"] == "act_2"].iloc[0]

    assert row1["account_name"] == "New Name"
    assert row1["account_status"] == 2
    assert row1["profile_name"] == "freelance"
    assert bool(row1["include_in_etl"]) is False
    assert row1["notes"] == "skip this one"

    assert bool(row2["include_in_etl"]) is True
    assert pd.isna(row2["notes"]) or row2["notes"] is None
