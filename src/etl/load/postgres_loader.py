# src/etl/load/postgres_loader.py

from typing import List
import pandas as pd
from sqlalchemy import create_engine, MetaData
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.config.settings import DB_CONN_STRING


def save_df_to_postgres_upsert(
    df: pd.DataFrame,
    table_name: str,
    unique_cols: List[str],
) -> None:
    """
    UPSERT a DataFrame into Postgres using ON CONFLICT DO UPDATE.

    unique_cols: columns that define a unique row, e.g. ["ad_id", "date_start"].
    """
    if df.empty:
        print(f"[postgres_loader] DataFrame is empty; nothing to upsert into {table_name}.")
        return

    if not DB_CONN_STRING:
        print("[postgres_loader] DB_CONN_STRING is empty; skipping load.")
        return

    # Create DB engine
    engine = create_engine(DB_CONN_STRING)
    metadata = MetaData()
    metadata.reflect(bind=engine)  # load existing tables

    if table_name not in metadata.tables:
        raise ValueError(f"[postgres_loader] Table '{table_name}' does not exist in the database.")

    table = metadata.tables[table_name]

    # IMPORTANT: keep only columns that exist in the table
    df = df[[c for c in df.columns if c in table.columns.keys()]]

    # Convert DataFrame rows to list of dicts
    records = df.to_dict(orient="records")

    with engine.begin() as conn:
        stmt = pg_insert(table).values(records)

        # Columns to update on conflict = all except the unique keys
        update_cols = {
            c.name: getattr(stmt.excluded, c.name)
            for c in table.columns
            if c.name not in unique_cols
        }

        upsert_stmt = stmt.on_conflict_do_update(
            index_elements=unique_cols,
            set_=update_cols,
        )

        conn.execute(upsert_stmt)

    print(f"[postgres_loader] Upserted {len(df)} rows into '{table_name}'.")
