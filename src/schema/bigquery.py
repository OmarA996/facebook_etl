from __future__ import annotations

from google.cloud import bigquery

from src.schema.tables import TABLE_SCHEMAS
from src.utils.names import normalize_column_name


PG_TO_BQ_TYPE = {
    "TEXT": "STRING",
    "INTEGER": "INT64",
    "BIGSERIAL": "INT64",
    "NUMERIC": "NUMERIC",
    "DATE": "DATE",
    "TIMESTAMPTZ": "TIMESTAMP",
    "BOOLEAN": "BOOL",
    "JSONB": "STRING",
}


def _pg_base_type(definition: str) -> str:
    return str(definition).strip().split()[0].upper()


def _get_combined_type_map() -> dict[str, str]:
    """Build the BQ type map for fact_meta_ads_combined.

    Uses the view's exact column lists so we only declare types for columns
    that actually appear in the SELECT — no phantom columns, no ambiguity.
    Dynamic action columns (actions_link_click etc.) are not declared here;
    they fall back to dtype inference (FLOAT64) in _build_full_schema_for_df.
    """
    from src.schema.views import _DIM_ACCOUNTS_COLS, _DIM_ADS_COLS, _DIM_CREATIVES_COLS

    type_map: dict[str, str] = {}

    # All declared fact table columns
    fact_schema = TABLE_SCHEMAS.get("fact_meta_delivery_ad", {})
    for col, definition in fact_schema.items():
        type_map[normalize_column_name(col, max_len=300)] = PG_TO_BQ_TYPE.get(_pg_base_type(definition), "STRING")

    # Only the columns explicitly selected from each dim table (with view aliases)
    acc_schema = TABLE_SCHEMAS.get("dim_meta_accounts", {})
    for col, alias in _DIM_ACCOUNTS_COLS:
        out_col = normalize_column_name(alias or col, max_len=300)
        if col in acc_schema:
            type_map[out_col] = PG_TO_BQ_TYPE.get(_pg_base_type(acc_schema[col]), "STRING")

    ads_schema = TABLE_SCHEMAS.get("dim_meta_ads", {})
    for col, alias in _DIM_ADS_COLS:
        out_col = normalize_column_name(alias or col, max_len=300)
        if col in ads_schema:
            type_map[out_col] = PG_TO_BQ_TYPE.get(_pg_base_type(ads_schema[col]), "STRING")

    cr_schema = TABLE_SCHEMAS.get("dim_meta_creatives", {})
    for col, alias in _DIM_CREATIVES_COLS:
        out_col = normalize_column_name(alias or col, max_len=300)
        if col in cr_schema:
            type_map[out_col] = PG_TO_BQ_TYPE.get(_pg_base_type(cr_schema[col]), "STRING")

    return type_map


def get_declared_bigquery_type_map(table_name: str) -> dict[str, str]:
    if table_name == "fact_meta_ads_combined":
        return _get_combined_type_map()
    schema = TABLE_SCHEMAS.get(table_name, {})
    type_map: dict[str, str] = {}
    for column_name, definition in schema.items():
        normalized = normalize_column_name(column_name, max_len=300)
        type_map[normalized] = PG_TO_BQ_TYPE.get(_pg_base_type(definition), "STRING")
    return type_map


def get_declared_bigquery_schema(table_name: str) -> list[bigquery.SchemaField]:
    type_map = get_declared_bigquery_type_map(table_name)
    return [
        bigquery.SchemaField(column_name, field_type)
        for column_name, field_type in type_map.items()
    ]
