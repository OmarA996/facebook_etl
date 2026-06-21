import pytest


pytest.importorskip("dotenv")

from src.etl.pipelines.meta_insights import get_bigquery_load_options


def test_get_bigquery_load_options_for_ad_table():
    assert get_bigquery_load_options("fact_meta_delivery_ad") == {
        "merge_keys": ["ad_id", "date_start"],
        "partition_field": "date_start",
        "cluster_fields": ["account_id", "campaign_id", "adset_id", "ad_id"],
    }


def test_get_bigquery_load_options_for_account_table():
    assert get_bigquery_load_options("fact_meta_delivery_account") == {
        "merge_keys": ["account_id", "date_start"],
        "partition_field": "date_start",
        "cluster_fields": ["account_id"],
    }


def test_get_bigquery_load_options_for_other_tables():
    assert get_bigquery_load_options("fact_meta_delivery_campaign") == {}
