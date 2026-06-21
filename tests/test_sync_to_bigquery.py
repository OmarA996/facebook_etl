import pytest
from unittest.mock import patch


pytest.importorskip("dotenv")

from src.etl.pipelines.sync_to_bigquery import resolve_sync_options, resolve_sync_table_names


def test_resolve_sync_options_defaults_fact_meta_delivery_ad_to_merge():
    resolved = resolve_sync_options("fact_meta_delivery_ad", mode="auto")

    assert resolved["mode"] == "merge"
    assert resolved["merge_keys"] == ["ad_id", "date_start"]
    assert resolved["partition_field"] == "date_start"


def test_resolve_sync_options_defaults_unknown_table_to_truncate():
    resolved = resolve_sync_options("dim_meta_accounts", mode="auto")

    assert resolved["mode"] == "truncate"
    assert resolved["merge_keys"] is None


def test_resolve_sync_options_rejects_merge_for_unknown_table():
    with pytest.raises(ValueError, match="No merge strategy configured"):
        resolve_sync_options("dim_meta_accounts", mode="merge")


def test_resolve_sync_table_names_all_uses_overlap():
    with (
        patch("src.etl.pipelines.sync_to_bigquery.list_postgres_tables", return_value=["meta_accounts_raw", "dim_meta_accounts", "fact_meta_delivery_ad"]),
        patch("src.etl.pipelines.sync_to_bigquery.list_bigquery_tables", return_value=["dim_meta_accounts", "fact_meta_delivery_ad", "fact_meta_delivery_account"]),
    ):
        resolved = resolve_sync_table_names(["all"], conn_string="postgresql://example")

    assert resolved == ["dim_meta_accounts", "fact_meta_delivery_ad"]


def test_resolve_sync_table_names_all_rejects_empty_overlap():
    with (
        patch("src.etl.pipelines.sync_to_bigquery.list_postgres_tables", return_value=["meta_accounts_raw"]),
        patch("src.etl.pipelines.sync_to_bigquery.list_bigquery_tables", return_value=["dim_meta_accounts"]),
    ):
        with pytest.raises(ValueError, match="No overlapping PostgreSQL and BigQuery tables"):
            resolve_sync_table_names(["all"], conn_string="postgresql://example")
