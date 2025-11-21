# src/etl/pipelines/meta_insights_daily.py

from typing import Optional

from src.etl.extract.meta_insights import fetch_insights
from src.etl.transform.meta_insights import normalize_insights
from src.etl.load.csv_loader import save_df_to_csv
from src.etl.load.postgres_loader import save_df_to_postgres_upsert
from src.schema.unique_keys import UNIQUE_KEYS


def run_meta_insights_daily(
    level: str = "ad",
    date_preset: str = "yesterday",
    to_db: bool = False,
    csv_path: Optional[str] = None,
):
    """
    Run a daily Meta insights pipeline using a date_preset
    (e.g. 'yesterday', 'last_7d').

    level: 'ad', 'adset', 'campaign', or 'account'
    """

    print(f"[pipeline-daily] Fetching {level}-level insights (date_preset={date_preset})...")

    records = fetch_insights(
        level=level,
        date_preset=date_preset,
    )
    print(f"[pipeline-daily] Fetched {len(records)} records.")

    if not records:
        print("[pipeline-daily] No records returned.")
        return None

    print("[pipeline-daily] Normalizing...")
    df = normalize_insights(records)
    print(f"[pipeline-daily] DataFrame shape: {df.shape}")

    if csv_path:
        print(f"[pipeline-daily] Saving to CSV: {csv_path}")
        save_df_to_csv(df, csv_path)

    if to_db:
        table_name = f"fact_meta_delivery_{level}"
        unique_cols = UNIQUE_KEYS.get(table_name)

        if unique_cols is None:
            raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")

        print(f"[pipeline-daily] Saving to Postgres ({table_name}) with unique_cols={unique_cols}...")
        save_df_to_postgres_upsert(
            df,
            table_name,
            unique_cols=unique_cols,
        )

    return df
