from typing import Optional

import pandas as pd

from src.clients.graph_client import GraphAPIError
from src.etl.extract.creatives import fetch_creatives, fetch_preview_url
from src.etl.transform.core import apply_rename_map, flatten_json, fill_numeric_keep_nulls, ensure_id_and_name
from src.etl.load.csv_loader import save_df_to_csv
from src.etl.load.postgres_loader import save_df_to_postgres_upsert, insert_raw_records
from src.schema.unique_keys import UNIQUE_KEYS
from src.config import PostgresConfig, load_ad_account_ids


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
    print("[creatives-info] Fetching creatives...")
    accounts = ad_account_ids or load_ad_account_ids()
    try:
        records = fetch_creatives(ad_account_ids=accounts, max_workers=max_workers)
    except GraphAPIError as e:
        print(f"[creatives-info] ERROR fetching creatives: {e}")
        return None

    print(f"[creatives-info] Fetched {len(records)} creatives.")
    if not records:
        print("[creatives-info] No creatives returned.")
        return None

    if to_db and db_config is not None:
        insert_raw_records(
            records,
            table_name="meta_creatives_raw",
            key_mapping={"creative_id": "id", "account_id": "account_id"},
            conn_string=db_config.conn_string,
        )

    df = flatten_json(records)
    df = ensure_id_and_name(df, id_col="creative_id", name_col="creative_name")
    df = apply_rename_map(df, "creatives-info", table_name="dim_meta_creatives")

    # Deduplicate by creative_id to ensure unique reporting
    if "creative_id" in df.columns:
        before_count = len(df)
        df.drop_duplicates(subset=["creative_id"], inplace=True)
        if len(df) < before_count:
            print(f"[creatives-info] Dropped {before_count - len(df)} duplicate creatives. Count: {len(df)}")

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
                print(f"[creatives-info]   preview error for creative {creative_id}: {e}")
                url = None
            preview_urls.append(url)
            if idx % 200 == 0:
                print(f"[creatives-info]   previews fetched: {idx}/{len(df)}")
        df["preview_url"] = preview_urls
    else:
        # Ensure column exists for hydration
        if "preview_url" not in df.columns:
            df["preview_url"] = None

    print(f"[creatives-info] DataFrame shape: {df.shape}")

    if csv_path:
        save_df_to_csv(df, csv_path)

    if to_db:
        table_name = "dim_meta_creatives"
        unique_cols = UNIQUE_KEYS.get(table_name)
        if unique_cols is None:
            raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")
        print(f"[creatives-info] Upserting to Postgres table '{table_name}' with unique_cols={unique_cols}...")
        save_df_to_postgres_upsert(
            df,
            table_name,
            unique_cols=unique_cols,
            conn_string=db_config.conn_string if db_config else None,
        )

    return df
