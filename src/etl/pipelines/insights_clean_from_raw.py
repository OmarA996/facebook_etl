import json
from typing import List, Optional

import pandas as pd
from sqlalchemy import create_engine, text

from src.config import PostgresConfig
from src.etl.transform.meta_insights import get_insights_table_name, normalize_insights
from src.etl.load.postgres_loader import save_df_to_postgres_upsert
from src.schema.unique_keys import UNIQUE_KEYS
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _canonical_breakdown_str(breakdowns: Optional[List[str]]) -> str:
    if not breakdowns:
        return ""
    return ",".join(sorted([b.strip() for b in breakdowns if b and b.strip()]))


def run_insights_clean_from_raw(
    level: str = "ad",
    breakdowns: Optional[List[str]] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: Optional[int] = None,
    to_db: bool = True,
    db_config: Optional[PostgresConfig] = None,
) -> Optional[pd.DataFrame]:
    """
    Re-run the cleaning/flattening step using raw rows in meta_insights_raw.

    - Reads raw payloads for the given level (and optional breakdown/date filters)
    - Normalizes them to a DataFrame
    - Optionally upserts into the fact table for that level/breakdown
    """
    if db_config is None:
        raise ValueError("db_config is required to read raw insights from the database.")

    conn_string = db_config.conn_string
    engine = create_engine(conn_string)

    # Build filters
    where_parts = ["level = :level"]
    params = {"level": level}

    if from_date:
        where_parts.append("date_start >= :from_date")
        params["from_date"] = from_date
    if to_date:
        where_parts.append("date_start <= :to_date")
        params["to_date"] = to_date

    if breakdowns is not None:
        where_parts.append("COALESCE(breakdowns, '') = :breakdowns")
        params["breakdowns"] = _canonical_breakdown_str(breakdowns)

    where_clause = " AND ".join(where_parts)
    limit_clause = ""
    if limit is not None and limit > 0:
        limit_clause = " LIMIT :limit"
        params["limit"] = limit

    sql = f"""
    SELECT id, date_start, date_stop, breakdowns, payload
    FROM meta_insights_raw
    WHERE {where_clause}
    ORDER BY id{limit_clause}
    """

    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    if not rows:
        logger.warning("No raw rows found for the given filters", level=level)
        return None

    breakdown_values = set()
    records: List[dict] = []
    for row in rows:
        mapping = row._mapping
        breakdown_values.add(mapping.get("breakdowns") or "")
        payload = mapping.get("payload")
        if payload is None:
            continue
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        records.append(payload)

    if not records:
        logger.warning("No payloads decoded from raw rows", level=level)
        return None

    # Determine effective breakdowns if not provided
    if breakdowns is None:
        if len(breakdown_values) > 1:
            raise ValueError(
                f"[insights-clean] Multiple breakdown sets found in raw data: {sorted(breakdown_values)}. "
                "Pass --breakdowns to select one set to clean."
            )
        single = next(iter(breakdown_values))
        effective_breakdowns = [b for b in single.split(",") if b]
    else:
        effective_breakdowns = breakdowns

    logger.info("Loaded raw rows", count=len(records), distinct_breakdowns=sorted(breakdown_values))

    df = normalize_insights(records, level=level, breakdowns=effective_breakdowns)
    norm_count = len(df)
    if norm_count > len(records):
        logger.warning(
            "Normalized rows exceed raw rows, dropping duplicates",
            normalized=norm_count,
            raw=len(records),
        )
        df = df.drop_duplicates()
        norm_count = len(df)
    logger.info("Normalized rows", count=norm_count, shape=df.shape)

    if not to_db:
        logger.info("--no-db specified, skipping fact table upsert")
        return df

    table_name = get_insights_table_name(level, effective_breakdowns)
    unique_cols = UNIQUE_KEYS.get(table_name)
    if unique_cols is None:
        raise ValueError(f"No UNIQUE_KEYS defined for table '{table_name}'")

    logger.info("Upserting into fact table", table=table_name, unique_cols=unique_cols)
    save_df_to_postgres_upsert(
        df,
        table_name,
        unique_cols=unique_cols,
        conn_string=conn_string,
    )
    return df
