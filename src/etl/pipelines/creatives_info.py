from typing import Optional

import pandas as pd

from src.clients.graph_client import GraphAPIError
from src.etl.extract.creatives import fetch_creatives, fetch_preview_url
from src.etl.transform.core import apply_rename_map, flatten_json, fill_numeric_keep_nulls, ensure_id_and_name
from src.etl.load.csv_loader import save_df_to_csv
from src.etl.load.postgres_loader import save_df_to_postgres_upsert
from src.schema.unique_keys import UNIQUE_KEYS
from src.config import PostgresConfig, load_ad_account_ids
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _extract_asset_feed_first_image(df: pd.DataFrame) -> pd.DataFrame:
    """Pull the first image URL/hash out of asset_feed_spec.images[] into flat columns.

    Asset-feed creatives (most modern Meta ads) don't expose a top-level
    image_url; the image lives at asset_feed_spec.images[0].url. flatten_json
    keeps the images list as a column-of-lists, so we extract the first entry
    here into asset_feed_spec_image_url / asset_feed_spec_image_hash so the
    rest of the pipeline (rename map, view COALESCE) can treat them as plain
    columns.
    """
    if df.empty:
        return df

    src_col = "asset_feed_spec.images"
    if src_col not in df.columns:
        return df

    def _first(field: str):
        def _pick(value):
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, dict):
                    return first.get(field)
            return None
        return _pick

    df = df.copy()
    df["asset_feed_spec_image_url"] = df[src_col].apply(_first("url"))
    df["asset_feed_spec_image_hash"] = df[src_col].apply(_first("hash"))
    return df


def run_creatives_info(
    csv_path: Optional[str] = None,
    to_db: bool = True,
    include_preview: bool = False,
    db_config: Optional[PostgresConfig] = None,
    ad_account_ids: Optional[list[str]] = None,
    max_workers: int = 1,
) -> Optional[pd.DataFrame]:
    """
    Fetch creatives across accounts, flatten them, and optionally save to CSV/DB.
    """
    logger.info("Fetching creatives")
    accounts = ad_account_ids or load_ad_account_ids()
    try:
        records = fetch_creatives(ad_account_ids=accounts, max_workers=max_workers)
    except GraphAPIError as e:
        logger.error("Error fetching creatives", error=str(e))
        return None

    logger.info("Fetched creatives", count=len(records))
    if not records:
        logger.warning("No creatives returned")
        return None

    df = flatten_json(records)
    df = ensure_id_and_name(df, id_col="creative_id", name_col="creative_name")
    df = _extract_asset_feed_first_image(df)
    df = apply_rename_map(df, "creatives-info", table_name="dim_meta_creatives")

    if "creative_id" in df.columns:
        before_count = len(df)
        df.drop_duplicates(subset=["creative_id"], inplace=True)
        dropped = before_count - len(df)
        if dropped:
            logger.info("Dropped duplicate creatives", dropped=dropped, remaining=len(df))

    df = fill_numeric_keep_nulls(df)

    if include_preview:
        preview_urls = []
        for idx, row in enumerate(df.itertuples(index=False), start=1):
            account_id = getattr(row, "account_id", None)
            creative_id = getattr(row, "creative_id", None)
            if not account_id or not creative_id:
                preview_urls.append(None)
                continue
            try:
                url = fetch_preview_url(account_id, creative_id)
            except GraphAPIError as e:
                logger.warning("Preview fetch error", creative_id=creative_id, error=str(e))
                url = None
            preview_urls.append(url)
            if idx % 200 == 0:
                logger.info("Preview progress", fetched=idx, total=len(df))
        df["preview_url"] = preview_urls
    else:
        if "preview_url" not in df.columns:
            df["preview_url"] = None

    logger.info("DataFrame ready", shape=df.shape)

    if csv_path:
        save_df_to_csv(df, csv_path)

    if to_db:
        table_name = "dim_meta_creatives"
        unique_cols = UNIQUE_KEYS.get(table_name)
        if unique_cols is None:
            raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")
        logger.info("Upserting to Postgres", table=table_name, unique_cols=unique_cols)
        save_df_to_postgres_upsert(
            df,
            table_name,
            unique_cols=unique_cols,
            conn_string=db_config.conn_string if db_config else None,
        )

    return df
