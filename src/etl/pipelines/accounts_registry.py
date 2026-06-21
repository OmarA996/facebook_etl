from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import PostgresConfig
from src.etl.extract.accounts import fetch_accounts
from src.etl.load.csv_loader import save_df_to_csv
from src.etl.load.postgres_loader import save_df_to_postgres_upsert
from src.schema.unique_keys import UNIQUE_KEYS
from src.utils.logger import get_logger

logger = get_logger(__name__)


REGISTRY_COLUMNS = [
    "account_id",
    "account_name",
    "account_status",
    "profile_name",
    "include_in_etl",
    "notes",
]


def _load_existing_registry_csv(csv_path: Optional[str]) -> pd.DataFrame:
    if not csv_path:
        return pd.DataFrame(columns=REGISTRY_COLUMNS)

    path = Path(csv_path)
    if not path.exists():
        return pd.DataFrame(columns=REGISTRY_COLUMNS)

    df = pd.read_csv(path, dtype={"account_id": "string"})
    for column in REGISTRY_COLUMNS:
        if column not in df.columns:
            df[column] = None
    return df[REGISTRY_COLUMNS].copy()


def _normalize_registry_df(records: list[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        rows.append(
            {
                "account_id": str(record.get("id")) if record.get("id") is not None else None,
                "account_name": record.get("name"),
                "account_status": pd.to_numeric(record.get("account_status"), errors="coerce"),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=REGISTRY_COLUMNS)

    df = df.drop_duplicates(subset=["account_id"], keep="last")
    df["account_status"] = df["account_status"].astype("Int64")
    df["profile_name"] = None
    df["include_in_etl"] = True
    df["notes"] = None
    return df[REGISTRY_COLUMNS]


def _merge_registry(existing: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        merged = fresh.copy()
    else:
        merged = fresh.merge(
            existing[["account_id", "profile_name", "include_in_etl", "notes"]],
            on="account_id",
            how="left",
            suffixes=("", "_existing"),
        )
        merged["profile_name"] = merged["profile_name_existing"].where(
            merged["profile_name_existing"].notna(),
            merged["profile_name"],
        )
        merged["include_in_etl"] = merged["include_in_etl_existing"].where(
            merged["include_in_etl_existing"].notna(),
            merged["include_in_etl"],
        )
        merged["notes"] = merged["notes_existing"].where(
            merged["notes_existing"].notna(),
            merged["notes"],
        )
        merged = merged.drop(columns=["profile_name_existing", "include_in_etl_existing", "notes_existing"])

    merged["profile_name"] = merged["profile_name"].where(merged["profile_name"].notna(), None)
    merged["include_in_etl"] = merged["include_in_etl"].fillna(True).astype(bool)
    merged["notes"] = merged["notes"].where(merged["notes"].notna(), None)
    merged = merged.sort_values(
        ["profile_name", "include_in_etl", "account_name", "account_id"],
        ascending=[True, False, True, True],
        na_position="last",
    )
    return merged[REGISTRY_COLUMNS].reset_index(drop=True)


def run_accounts_registry(
    csv_path: str = "data/account_registry.csv",
    profile: Optional[str] = None,
    to_db: bool = False,
    to_bigquery: bool = False,
    bq_write_disposition: str = "WRITE_APPEND",
    bq_table_name: Optional[str] = None,
    db_config: Optional[PostgresConfig] = None,
) -> Optional[pd.DataFrame]:
    logger.info("Fetching accounts")
    records = fetch_accounts()
    logger.info("Fetched accounts", count=len(records))

    if not records:
        logger.warning("No accounts returned")
        return None

    fresh_df = _normalize_registry_df(records)
    existing_df = _load_existing_registry_csv(csv_path)
    final_df = _merge_registry(existing_df, fresh_df)

    save_df_to_csv(final_df, csv_path)

    if to_db:
        table_name = "dim_meta_account_registry"
        unique_cols = UNIQUE_KEYS.get(table_name)
        if unique_cols is None:
            raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")
        save_df_to_postgres_upsert(
            final_df,
            table_name,
            unique_cols=unique_cols,
            conn_string=db_config.conn_string if db_config else None,
        )

    if to_bigquery:
        from src.etl.load.bigquery_loader import save_df_to_bigquery

        save_df_to_bigquery(
            final_df,
            table_name=bq_table_name or "dim_meta_account_registry",
            profile=profile,
            write_disposition=bq_write_disposition,
        )

    return final_df
