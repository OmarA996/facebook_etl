from typing import List, Optional

from src.config import PostgresConfig
from src.etl.pipelines.meta_insights import run_meta_insights


def run_meta_insights_range(
    level: str,
    from_date: str,
    to_date: str,
    chunk_size_days: int = 7,
    breakdowns: Optional[List[str]] = None,
    profile: Optional[str] = None,
    to_db: bool = True,
    to_bigquery: bool = False,
    bq_write_disposition: str = "WRITE_APPEND",
    bq_table_name: Optional[str] = None,
    csv_path: Optional[str] = None,
    db_config: Optional[PostgresConfig] = None,
    ad_account_ids: Optional[List[str]] = None,
    max_workers: int = 1,
    force: bool = False,
):
    return run_meta_insights(
        level=level,
        from_date=from_date,
        to_date=to_date,
        chunk_size_days=chunk_size_days,
        breakdowns=breakdowns,
        profile=profile,
        to_db=to_db,
        to_bigquery=to_bigquery,
        bq_write_disposition=bq_write_disposition,
        bq_table_name=bq_table_name,
        csv_path=csv_path,
        db_config=db_config,
        ad_account_ids=ad_account_ids,
        max_workers=max_workers,
        force=force,
    )
