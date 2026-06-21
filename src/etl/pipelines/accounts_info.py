from typing import Optional

import pandas as pd

from src.etl.extract.accounts import fetch_accounts
from src.etl.transform.core import apply_rename_map, flatten_json, fill_numeric_keep_nulls
from src.etl.load.csv_loader import save_df_to_csv
from src.etl.load.postgres_loader import save_df_to_postgres_upsert
from src.schema.unique_keys import UNIQUE_KEYS
from src.config import PostgresConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_accounts_info(
    csv_path: Optional[str] = None,
    profile: Optional[str] = None,
    to_db: bool = True,
    to_bigquery: bool = False,
    bq_write_disposition: str = "WRITE_APPEND",
    bq_table_name: Optional[str] = None,
    db_config: Optional[PostgresConfig] = None,
) -> Optional[pd.DataFrame]:
    """
    Fetch account info (including billing-related fields) and optionally export to CSV.
    """
    logger.info("Fetching accounts")
    records = fetch_accounts()
    logger.info("Fetched accounts", count=len(records))

    if not records:
        logger.warning("No accounts returned")
        return None

    df = flatten_json(records)
    df = apply_rename_map(df, "accounts-info", table_name="dim_meta_accounts")
    df = fill_numeric_keep_nulls(df)
    logger.info("DataFrame ready", shape=df.shape)

    if csv_path:
        save_df_to_csv(df, csv_path)

    if to_db:
        table_name = "dim_meta_accounts"
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

    if to_bigquery:
        from src.etl.load.bigquery_loader import save_df_to_bigquery

        save_df_to_bigquery(
            df,
            table_name=bq_table_name or "dim_meta_accounts",
            profile=profile,
            write_disposition=bq_write_disposition,
        )

    return df
