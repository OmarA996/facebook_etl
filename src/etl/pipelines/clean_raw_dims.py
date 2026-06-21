import json
from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd
from sqlalchemy import create_engine, text

from src.config import PostgresConfig
from src.utils.logger import get_logger
from src.etl.transform.core import (
    flatten_json,
    fill_numeric_keep_nulls,
    ensure_id_and_name,
    coerce_datetime_columns,
)
from src.etl.load.postgres_loader import save_df_to_postgres_upsert
from src.schema.unique_keys import UNIQUE_KEYS

logger = get_logger(__name__)


@dataclass
class RawCleanConfig:
    raw_table: str
    target_table: str


RAW_CLEAN_CONFIGS: Dict[str, RawCleanConfig] = {
    "accounts": RawCleanConfig("meta_accounts_raw", "dim_meta_accounts"),
    "creatives": RawCleanConfig("meta_creatives_raw", "dim_meta_creatives"),
    "campaigns": RawCleanConfig("meta_campaigns_raw", "dim_meta_campaigns"),
    "adsets": RawCleanConfig("meta_adsets_raw", "dim_meta_adsets"),
    "ads": RawCleanConfig("meta_ads_raw", "dim_meta_ads"),
    "ad-previews": RawCleanConfig("meta_ads_previews_raw", "dim_meta_ads"),
}

# Map entities to the expected id/name column names in their dimension tables.
ID_NAME_MAP: Dict[str, tuple[str, str]] = {
    "accounts": ("id", "account_name"),
    "creatives": ("creative_id", "creative_name"),
    "campaigns": ("campaign_id", "campaign_name"),
    "adsets": ("adset_id", "adset_name"),
    "ads": ("ad_id", "ad_name"),
    "ad-previews": ("ad_id", "ad_name"),
}

# Datetime columns per entity to coerce and null out NaN values.
DATETIME_COLS: Dict[str, list[str]] = {
    "accounts": ["created_time"],
    "creatives": [],
    "campaigns": ["created_time", "start_time", "stop_time"],
    "adsets": ["created_time", "start_time", "end_time"],
    "ads": ["created_time", "updated_time"],
    "ad-previews": ["created_time", "updated_time"],
}


def run_clean_dim_from_raw(
    entity: str,
    limit: Optional[int] = None,
    to_db: bool = True,
    db_config: Optional[PostgresConfig] = None,
) -> Optional[pd.DataFrame]:
    """
    Re-clean raw dimension payloads into their target tables.

    entity: one of RAW_CLEAN_CONFIGS keys (accounts, creatives, campaigns, adsets, ads, ad-previews)
    """
    if db_config is None:
        raise ValueError("db_config is required to read raw dimension data from the database.")

    cfg = RAW_CLEAN_CONFIGS.get(entity)
    if cfg is None:
        raise ValueError(f"Unsupported entity '{entity}'. Choose from: {', '.join(RAW_CLEAN_CONFIGS.keys())}")

    conn_string = db_config.conn_string
    engine = create_engine(conn_string)

    limit_clause = ""
    params = {}
    if limit is not None and limit > 0:
        limit_clause = " LIMIT :limit"
        params["limit"] = limit

    sql = f"SELECT payload FROM {cfg.raw_table} ORDER BY id{limit_clause}"
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    if not rows:
        logger.warning("No raw rows found", entity=entity, raw_table=cfg.raw_table)
        return None

    records = []
    for row in rows:
        payload = row._mapping.get("payload")
        if payload is None:
            continue
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        records.append(payload)

    if not records:
        logger.warning("No payloads decoded", entity=entity, raw_table=cfg.raw_table)
        return None

    df = flatten_json(records)
    id_name = ID_NAME_MAP.get(entity)
    if id_name:
        df = ensure_id_and_name(df, id_col=id_name[0], name_col=id_name[1])
    dt_cols = DATETIME_COLS.get(entity, [])
    if dt_cols:
        df = coerce_datetime_columns(df, dt_cols)
    # Ensure ID-like columns stay as strings to avoid bigint coercion
    id_cols = [c for c in df.columns if str(c).lower() in {"campaign_id", "adset_id", "ad_id", "account_id", "creative_id", "id"} or str(c).lower().endswith("_id")]
    for col in id_cols:
        df[col] = df[col].apply(lambda x: None if pd.isna(x) else str(x))
    df = fill_numeric_keep_nulls(df)
    df = df.drop_duplicates()
    logger.info("Normalized rows", entity=entity, rows=len(df), shape=df.shape)

    if not to_db:
        logger.info("--no-db specified, returning DataFrame without upsert", entity=entity)
        return df

    unique_cols = UNIQUE_KEYS.get(cfg.target_table)
    if unique_cols is None:
        raise ValueError(f"No UNIQUE_KEYS defined for table '{cfg.target_table}'")

    logger.info("Upserting into target table", entity=entity, table=cfg.target_table, unique_cols=unique_cols)
    save_df_to_postgres_upsert(
        df,
        cfg.target_table,
        unique_cols=unique_cols,
        conn_string=conn_string,
    )
    return df
