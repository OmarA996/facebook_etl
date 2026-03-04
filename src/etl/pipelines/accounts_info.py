from typing import Optional

import pandas as pd

from src.etl.extract.accounts import fetch_accounts
from src.etl.transform.core import flatten_json, fill_numeric_keep_nulls, ensure_id_and_name
from src.etl.load.csv_loader import save_df_to_csv
from src.etl.load.postgres_loader import save_df_to_postgres_upsert, insert_raw_records
from src.schema.unique_keys import UNIQUE_KEYS
from src.config import PostgresConfig


def run_accounts_info(
    csv_path: Optional[str] = None,
    to_db: bool = True,
    db_config: Optional[PostgresConfig] = None,
) -> Optional[pd.DataFrame]:
    """
    Fetch account info (including billing-related fields) and optionally export to CSV.
    """
    print("[accounts-info] Fetching accounts...")
    records = fetch_accounts()
    print(f"[accounts-info] Fetched {len(records)} accounts.")

    if not records:
        print("[accounts-info] No accounts returned.")
        return None

    # Persist raw payloads
    if to_db and db_config is not None:
        insert_raw_records(
            records,
            table_name="meta_accounts_raw",
            key_mapping={"account_id": "id"},
            conn_string=db_config.conn_string,
        )

    df = flatten_json(records)
    df = ensure_id_and_name(df, id_col="id", name_col="account_name")
    df = fill_numeric_keep_nulls(df)
    print(f"[accounts-info] DataFrame shape: {df.shape}")

    if csv_path:
        save_df_to_csv(df, csv_path)

    if to_db:
        table_name = "dim_meta_accounts"
        unique_cols = UNIQUE_KEYS.get(table_name)
        if unique_cols is None:
            raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")
        print(f"[accounts-info] Upserting to Postgres table '{table_name}' with unique_cols={unique_cols}...")
        save_df_to_postgres_upsert(
            df,
            table_name,
            unique_cols=unique_cols,
            conn_string=db_config.conn_string if db_config else None,
        )

    return df
