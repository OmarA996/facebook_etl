import pandas as pd
import pytest


bigquery_loader = pytest.importorskip("src.etl.load.bigquery_loader")
bigquery_schema = pytest.importorskip("src.schema.bigquery")


def test_save_df_to_bigquery_rejects_missing_merge_keys(monkeypatch):
    monkeypatch.setattr(
        bigquery_loader,
        "_build_client",
        lambda *args, **kwargs: pytest.fail("_build_client should not be called for invalid merge keys"),
    )

    df = pd.DataFrame({"date_start": ["2026-03-24"]})

    with pytest.raises(ValueError, match="Missing merge key columns"):
        bigquery_loader.save_df_to_bigquery(
            df,
            table_name="fact_meta_delivery_ad",
            project_id="proj",
            dataset_id="dataset",
            merge_keys=["ad_id", "date_start"],
        )


def test_save_df_to_bigquery_rejects_null_merge_keys(monkeypatch):
    monkeypatch.setattr(
        bigquery_loader,
        "_build_client",
        lambda *args, **kwargs: pytest.fail("_build_client should not be called for null merge keys"),
    )

    df = pd.DataFrame({"ad_id": [None], "date_start": ["2026-03-24"]})

    with pytest.raises(ValueError, match="contain null values"):
        bigquery_loader.save_df_to_bigquery(
            df,
            table_name="fact_meta_delivery_ad",
            project_id="proj",
            dataset_id="dataset",
            merge_keys=["ad_id", "date_start"],
        )


def test_save_df_to_bigquery_dispatches_merge_mode(monkeypatch):
    sentinel_client = object()
    captured: dict[str, object] = {}

    monkeypatch.setattr(bigquery_loader, "_build_client", lambda *args, **kwargs: sentinel_client)
    monkeypatch.setattr(bigquery_loader, "_ensure_dataset", lambda *args, **kwargs: None)

    def fake_merge(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(bigquery_loader, "_merge_df_to_bigquery", fake_merge)

    df = pd.DataFrame(
        {
            "ad_id": ["123"],
            "date_start": ["2026-03-24"],
            "account_id": ["456"],
        }
    )

    bigquery_loader.save_df_to_bigquery(
        df,
        table_name="fact_meta_delivery_ad",
        project_id="proj",
        dataset_id="dataset",
        merge_keys=["ad_id", "date_start"],
        partition_field="date_start",
        cluster_fields=["account_id", "ad_id"],
    )

    assert captured["client"] is sentinel_client
    assert captured["project_id"] == "proj"
    assert captured["dataset_id"] == "dataset"
    assert captured["table_name"] == "fact_meta_delivery_ad"
    assert captured["merge_keys"] == ["ad_id", "date_start"]
    assert captured["partition_field"] == "date_start"
    assert captured["cluster_fields"] == ["account_id", "ad_id"]


def test_prepare_df_for_bigquery_coerces_partition_field_to_date():
    df = pd.DataFrame(
        {
            "ad_id": ["123"],
            "date_start": ["2026-03-24"],
        }
    )

    prepared = bigquery_loader._prepare_df_for_bigquery(
        df,
        table_name="fact_meta_delivery_ad",
        normalize_columns=True,
        serialize_complex_types=True,
        partition_field="date_start",
    )

    assert str(prepared["date_start"].iloc[0]) == "2026-03-24"
    assert type(prepared["date_start"].iloc[0]).__name__ == "date"


def test_build_merge_sql_casts_source_columns_to_final_types():
    sql = bigquery_loader._build_merge_sql(
        final_table_id="proj.dataset.fact_meta_delivery_ad",
        staging_table_id="proj.dataset._fact_meta_delivery_ad__staging",
        columns=["ad_id", "date_start", "reach"],
        merge_keys=["ad_id", "date_start"],
        field_types={"ad_id": "STRING", "date_start": "DATE", "reach": "INT64"},
    )

    assert "reach = CAST(S.reach AS INT64)" in sql
    assert "VALUES (CAST(S.ad_id AS STRING), CAST(S.date_start AS DATE), CAST(S.reach AS INT64))" in sql


def test_save_df_to_bigquery_requires_existing_table(monkeypatch):
    sentinel_client = object()

    monkeypatch.setattr(bigquery_loader, "_build_client", lambda *args, **kwargs: sentinel_client)
    monkeypatch.setattr(bigquery_loader, "_table_exists", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        bigquery_loader,
        "_ensure_dataset",
        lambda *args, **kwargs: pytest.fail("_ensure_dataset should not be called when require_existing_table=True"),
    )

    df = pd.DataFrame({"id": ["1"]})

    with pytest.raises(ValueError, match="Target BigQuery table does not exist"):
        bigquery_loader.save_df_to_bigquery(
            df,
            table_name="dim_meta_accounts",
            project_id="proj",
            dataset_id="dataset",
            require_existing_table=True,
        )


def test_prepare_df_for_bigquery_aligns_to_declared_schema():
    df = pd.DataFrame(
        {
            "ad_id": ["123"],
            "date_start": ["2026-03-24"],
            "date_stop": ["2026-03-24"],
            "account_id": ["456"],
            "extra_metric": [99],
        }
    )

    prepared = bigquery_loader._prepare_df_for_bigquery(
        df,
        table_name="fact_meta_delivery_ad",
        normalize_columns=True,
        serialize_complex_types=True,
        partition_field="date_start",
    )

    declared_columns = list(bigquery_schema.get_declared_bigquery_type_map("fact_meta_delivery_ad").keys())
    assert list(prepared.columns) == declared_columns
    assert "extra_metric" not in prepared.columns
    assert prepared.loc[0, "ad_id"] == "123"
    assert prepared.loc[0, "date_start"].isoformat() == "2026-03-24"
    assert "results" in prepared.columns


def test_declared_bigquery_schema_maps_postgres_types():
    type_map = bigquery_schema.get_declared_bigquery_type_map("fact_meta_delivery_ad")

    assert type_map["ad_id"] == "STRING"
    assert type_map["date_start"] == "DATE"
    assert type_map["spend"] == "NUMERIC"
    assert type_map["results"] == "STRING"
