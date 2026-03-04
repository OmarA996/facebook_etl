from typing import Optional

import pandas as pd

from src.clients.graph_client import GraphAPIError
from src.etl.extract.ads_settings import fetch_ads_settings
from src.etl.transform.core import flatten_json, fill_numeric_keep_nulls, ensure_id_and_name
from src.etl.load.csv_loader import save_df_to_csv
from src.etl.load.postgres_loader import save_df_to_postgres_upsert, insert_raw_records
from src.schema.unique_keys import UNIQUE_KEYS
from src.config import PostgresConfig, load_ad_account_ids


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
    print("[ads-info] Fetching ads (settings)...")
    accounts = ad_account_ids or load_ad_account_ids()
    try:
        records = fetch_ads_settings(
            effective_statuses=effective_statuses,
            ad_account_ids=accounts,
            max_workers=max_workers,
        )
    except GraphAPIError as e:
        print(f"[ads-info] ERROR fetching ads: {e}")
        return None

    print(f"[ads-info] Fetched {len(records)} ads.")
    if not records:
        print("[ads-info] No ads returned.")
        return None

    if to_db and db_config is not None:
        insert_raw_records(
            records,
            table_name="meta_ads_raw",
            key_mapping={
                "ad_id": "id",
                "account_id": "account_id",
                "adset_id": "adset_id",
                "campaign_id": "campaign_id",
            },
            conn_string=db_config.conn_string,
        )

    df = flatten_json(records)
    df = ensure_id_and_name(df, id_col="ad_id", name_col="ad_name")
    df = fill_numeric_keep_nulls(df)
    print(f"[ads-info] DataFrame shape: {df.shape}")

    if csv_path:
        save_df_to_csv(df, csv_path)

    if to_db:
        table_name = "dim_meta_ads_settings"
        unique_cols = UNIQUE_KEYS.get(table_name)
        if unique_cols is None:
            raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")
        print(f"[ads-info] Upserting to Postgres table '{table_name}' with unique_cols={unique_cols}...")
        save_df_to_postgres_upsert(
            df,
            table_name,
            unique_cols=unique_cols,
            conn_string=db_config.conn_string if db_config else None,
        )

    return df
