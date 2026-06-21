from __future__ import annotations

from typing import Optional

from sqlalchemy import create_engine, inspect, text

from src.config import PostgresConfig, load_postgres_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

COMBINED_TABLE = "fact_meta_ads_combined"
SOURCE_VIEW = "vw_meta_ads_full"


def run_materialize_combined(
    *,
    db_config: Optional[PostgresConfig] = None,
    to_bigquery: bool = False,
    profile: Optional[str] = None,
) -> None:
    conn_string = db_config.conn_string if db_config else load_postgres_config().conn_string
    engine = create_engine(conn_string)

    insp = inspect(engine)
    if not (insp.has_table(SOURCE_VIEW) or SOURCE_VIEW in insp.get_view_names(schema="public")):
        raise ValueError(f"Source view '{SOURCE_VIEW}' does not exist. Run accounts-info first to create it.")

    logger.info("Materializing combined table", source=SOURCE_VIEW, target=COMBINED_TABLE)
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{COMBINED_TABLE}" CASCADE'))
        conn.execute(text(f'CREATE TABLE "{COMBINED_TABLE}" AS SELECT * FROM "{SOURCE_VIEW}"'))

    with engine.connect() as conn:
        row_count = conn.execute(text(f'SELECT COUNT(*) FROM "{COMBINED_TABLE}"')).scalar()
    logger.info("Combined table materialized", table=COMBINED_TABLE, rows=row_count)

    if to_bigquery:
        from src.etl.pipelines.sync_to_bigquery import run_sync_to_bigquery
        run_sync_to_bigquery(
            table_names=[COMBINED_TABLE],
            db_config=db_config or PostgresConfig(conn_string=conn_string),
            profile=profile,
            mode="truncate",
            create_if_missing=True,
        )
