# src/etl/pipelines/meta_insights_range.py

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from src.etl.extract.meta_insights import fetch_insights
from src.etl.transform.meta_insights import normalize_insights
from src.etl.load.postgres_loader import save_df_to_postgres_upsert
from src.etl.load.csv_loader import save_df_to_csv
from src.schema.unique_keys import UNIQUE_KEYS


def _date_chunks(start: datetime, end: datetime, chunk_size_days: int):
    """
    Yield (since, until) date pairs in 'YYYY-MM-DD' format,
    covering the inclusive range [start, end] in chunks.
    """
    one_day = timedelta(days=1)
    chunk_delta = timedelta(days=chunk_size_days - 1)

    current = start
    while current <= end:
        chunk_end = min(current + chunk_delta, end)
        yield (
            current.strftime("%Y-%m-%d"),
            chunk_end.strftime("%Y-%m-%d"),
        )
        current = chunk_end + one_day


def run_meta_insights_range(
    level: str,
    from_date: str,
    to_date: str,
    chunk_size_days: int = 7,
    to_db: bool = True,
    csv_path: Optional[str] = None,
):
    """
    Fetch Meta insights for a date range [from_date, to_date],
    split into smaller chunks so each API call is manageable.

    Args:
        level: 'ad', 'adset', 'campaign', or 'account'
        from_date: start date (inclusive), 'YYYY-MM-DD'
        to_date: end date (inclusive), 'YYYY-MM-DD'
        chunk_size_days: number of days per API call (1, 3, 7, etc.)
        to_db: whether to load into Postgres
        csv_path: optional CSV export path
    """

    start_dt = datetime.strptime(from_date, "%Y-%m-%d")
    end_dt = datetime.strptime(to_date, "%Y-%m-%d")

    all_records: List[Dict[str, Any]] = []

    print(
        f"[pipeline-range] Fetching {level}-level insights "
        f"from {from_date} to {to_date} in chunks of {chunk_size_days} day(s)..."
    )

    for since, until in _date_chunks(start_dt, end_dt, chunk_size_days):
        print(f"[pipeline-range] Chunk {since} → {until}")

        chunk_records = fetch_insights(
            level=level,
            since=since,
            until=until,
        )
        print(f"[pipeline-range]   fetched {len(chunk_records)} rows")

        all_records.extend(chunk_records)

    print(f"[pipeline-range] Total raw rows fetched: {len(all_records)}")

    if not all_records:
        print("[pipeline-range] No data returned for this range.")
        return None

    print("[pipeline-range] Normalizing...")
    df = normalize_insights(all_records)
    print(f"[pipeline-range] DataFrame shape after normalize: {df.shape}")

    if csv_path:
        print(f"[pipeline-range] Saving to CSV: {csv_path}")
        save_df_to_csv(df, csv_path)

    if to_db:
        table_name = f"fact_meta_delivery_{level}"
        unique_cols = UNIQUE_KEYS.get(table_name)

        if unique_cols is None:
            raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")

        print(f"[pipeline-range] Saving to Postgres ({table_name}) with unique_cols={unique_cols}...")
        save_df_to_postgres_upsert(
            df,
            table_name,
            unique_cols=unique_cols,
        )

    return df
