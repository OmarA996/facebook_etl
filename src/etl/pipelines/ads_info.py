from typing import Optional

import pandas as pd

from src.clients.graph_client import GraphAPIError
from src.etl.extract.ads import fetch_ads
from src.etl.transform.core import apply_rename_map, flatten_json, fill_numeric_keep_nulls, ensure_id_and_name
from src.etl.load.csv_loader import save_df_to_csv
from src.etl.load.postgres_loader import save_df_to_postgres_upsert
from src.schema.unique_keys import UNIQUE_KEYS
from src.config import PostgresConfig, load_ad_account_ids
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_ads_info(
    csv_path: Optional[str] = None,
    to_db: bool = True,
    effective_statuses: Optional[list[str]] = None,
    db_config: Optional[PostgresConfig] = None,
    ad_account_ids: Optional[list[str]] = None,
    max_workers: int = 1,
) -> Optional[pd.DataFrame]:
    """
    Fetch ad metadata/settings, flatten, optional CSV, optional DB upsert.
    """
    logger.info("Fetching ads (settings)")
    accounts = ad_account_ids or load_ad_account_ids()
    try:
        records = fetch_ads(
            effective_statuses=effective_statuses,
            ad_account_ids=accounts,
            max_workers=max_workers,
        )
    except GraphAPIError as e:
        logger.error("Error fetching ads", error=str(e))
        return None

    logger.info("Fetched ads", count=len(records))
    if not records:
        logger.warning("No ads returned")
        return None

    df = flatten_json(records)
    df = ensure_id_and_name(df, id_col="ad_id", name_col="ad_name")
    df = apply_rename_map(df, "ads-info", table_name="dim_meta_ads")
    df = fill_numeric_keep_nulls(df)
    logger.info("DataFrame ready", shape=df.shape)

    if csv_path:
        save_df_to_csv(df, csv_path)

    if to_db:
        _save_ads_dimensions(df, conn_string=db_config.conn_string if db_config else None)

    return df


def _row_value(row: dict, *keys: str) -> object:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _build_creatives_dimension_df(df: pd.DataFrame) -> pd.DataFrame:
    """Seed dim_meta_creatives with only the fields the ads API returns (id + name).

    The ads endpoint only fetches creative{id,name}, so we intentionally limit
    the upsert to those three columns. This prevents the ON CONFLICT DO UPDATE
    from overwriting image_url / thumbnail_url / etc. that creatives-info
    has already populated from the dedicated /adcreatives endpoint.
    """
    if df.empty:
        return pd.DataFrame()

    creative_rows = []
    for row in df.to_dict(orient="records"):
        creative_id = _row_value(row, "creative.id", "creative_id")
        if creative_id is None:
            continue
        creative_rows.append({
            "creative_id": str(creative_id),
            "account_id": _row_value(row, "account_id"),
            "creative_name": _row_value(row, "creative.name", "creative_name"),
        })

    if not creative_rows:
        return pd.DataFrame()

    creatives_df = pd.DataFrame(creative_rows)
    creatives_df.drop_duplicates(subset=["creative_id"], keep="last", inplace=True)
    return creatives_df


def _save_ads_dimensions(df: pd.DataFrame, conn_string: str | None = None) -> None:
    table_name = "dim_meta_ads"
    unique_cols = UNIQUE_KEYS.get(table_name)
    if unique_cols is None:
        raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")
    logger.info("Upserting to Postgres", table=table_name, unique_cols=unique_cols)
    save_df_to_postgres_upsert(
        df,
        table_name,
        unique_cols=unique_cols,
        conn_string=conn_string,
    )

    creatives_df = _build_creatives_dimension_df(df)
    if creatives_df.empty:
        return

    creatives_table = "dim_meta_creatives"
    creatives_unique_cols = UNIQUE_KEYS.get(creatives_table)
    if creatives_unique_cols is None:
        raise ValueError(f"No UNIQUE_KEYS defined for table '{creatives_table}'")
    logger.info(
        "Upserting compatibility rows",
        table=creatives_table,
        unique_cols=creatives_unique_cols,
        rows=len(creatives_df),
    )
    save_df_to_postgres_upsert(
        creatives_df,
        creatives_table,
        unique_cols=creatives_unique_cols,
        conn_string=conn_string,
    )
