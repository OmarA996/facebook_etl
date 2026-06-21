from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from src.config import PostgresConfig, load_bigquery_config, load_postgres_config
from src.etl.load.postgres_loader import save_df_to_postgres_upsert
from src.etl.load.schema_manager import ensure_database_and_tables
from src.schema.unique_keys import UNIQUE_KEYS
from src.utils.logger import get_logger

logger = get_logger(__name__)

REQUIRED_COLUMNS = {"account_id", "month"}
GOAL_COLUMNS = [
    "goal_spend",
    "goal_purchase_value",
    "goal_roas",
    "goal_purchases",
    "goal_messages",
]


def _normalize_account_id(val: str) -> str:
    val = str(val).strip()
    return val if val.startswith("act_") else f"act_{val}"


def _parse_month(val: str) -> str:
    """Return the first day of the month as YYYY-MM-DD."""
    ts = pd.to_datetime(val, errors="raise")
    return ts.replace(day=1).strftime("%Y-%m-%d")


def run_load_goals(
    csv_path: str,
    to_db: bool = True,
    to_bigquery: bool = False,
    db_config: Optional[PostgresConfig] = None,
    profile: Optional[str] = None,
) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Goals CSV not found: {path}")

    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Goals CSV is missing required columns: {sorted(missing)}")

    df["account_id"] = df["account_id"].apply(_normalize_account_id)
    df["month"] = df["month"].apply(_parse_month)

    for col in GOAL_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = None

    if "note" not in df.columns:
        df["note"] = None

    keep = ["account_id", "month"] + GOAL_COLUMNS + ["note"]
    df = df[[c for c in keep if c in df.columns]]

    # Drop rows with no account_id or month
    df = df.dropna(subset=["account_id", "month"])
    df = df[df["account_id"].str.strip() != ""]

    logger.info("Goals CSV loaded", rows=len(df), path=str(path))

    if not to_db:
        logger.info("Skipping DB upsert (--no-db)")
        return df

    if db_config is None:
        db_config = load_postgres_config(profile)

    ensure_database_and_tables(db_config.conn_string, table_names=["dim_goals"])

    unique_cols = UNIQUE_KEYS["dim_goals"]
    save_df_to_postgres_upsert(
        df,
        "dim_goals",
        unique_cols=unique_cols,
        conn_string=db_config.conn_string,
    )
    logger.info("Goals upserted to Postgres", rows=len(df), table="dim_goals")

    if to_bigquery:
        _sync_goals_to_bigquery(df, profile=profile, db_config=db_config)

    return df


def _sync_goals_to_bigquery(
    df: pd.DataFrame,
    profile: Optional[str] = None,
    db_config: Optional[PostgresConfig] = None,
) -> None:
    from src.etl.load.bigquery_loader import save_df_to_bigquery, create_or_update_bq_view
    from src.config import load_bigquery_config

    try:
        bq_cfg = load_bigquery_config(profile)
    except Exception as exc:
        logger.error("BigQuery config unavailable, skipping BQ sync", error=str(exc))
        return

    save_df_to_bigquery(
        df,
        table_name="dim_goals",
        write_disposition="WRITE_TRUNCATE",
        project_id=bq_cfg.project_id,
        dataset_id=bq_cfg.dataset_id,
        credentials_path=bq_cfg.credentials_path,
        impersonate_service_account=bq_cfg.impersonate_service_account,
        create_if_missing=True,
    )
    logger.info("dim_goals synced to BigQuery", rows=len(df))

    _ensure_goals_view(bq_cfg.project_id, bq_cfg.dataset_id, bq_cfg.credentials_path, bq_cfg.impersonate_service_account)


def _ensure_goals_view(
    project_id: str,
    dataset_id: str,
    credentials_path: Optional[str] = None,
    impersonate_service_account: Optional[str] = None,
) -> None:
    from src.etl.load.bigquery_loader import create_or_update_bq_view

    p, d = project_id, dataset_id
    sql = f"""
SELECT
  a.date_start,
  a.date_stop,
  a.account_id,
  a.account_name,
  a.campaign_id,
  a.campaign_name,
  a.adset_id,
  a.adset_name,
  a.ad_id,
  a.ad_name,
  a.objective,
  a.spend,
  a.action_values_purchase                                                      AS purchase_value,
  SAFE_DIVIDE(a.action_values_purchase, NULLIF(a.spend, 0))                    AS roas,
  a.actions_purchase                                                             AS purchases,
  a.actions_onsite_conversion_messaging_conversation_started_7d                AS messages,
  g.goal_spend,
  g.goal_purchase_value,
  g.goal_roas,
  g.goal_purchases,
  g.goal_messages,
  SAFE_DIVIDE(a.spend,                     g.goal_spend)          AS pct_spend_goal,
  SAFE_DIVIDE(a.action_values_purchase,    g.goal_purchase_value) AS pct_purchase_value_goal,
  SAFE_DIVIDE(a.actions_purchase,          g.goal_purchases)      AS pct_purchases_goal,
  SAFE_DIVIDE(
    a.actions_onsite_conversion_messaging_conversation_started_7d,
    g.goal_messages
  )                                                                              AS pct_messages_goal
FROM `{p}.{d}.fact_meta_ads_combined` a
LEFT JOIN `{p}.{d}.dim_goals` g
  ON  a.account_id = g.account_id
  AND DATE_TRUNC(a.date_start, MONTH) = g.month
"""
    create_or_update_bq_view(
        view_name="vw_goals_vs_actual",
        sql=sql.strip(),
        project_id=project_id,
        dataset_id=dataset_id,
        credentials_path=credentials_path,
        impersonate_service_account=impersonate_service_account,
    )
