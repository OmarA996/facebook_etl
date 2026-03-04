# src/etl/load/postgres_loader.py

from typing import List, Dict
import json
import pandas as pd
from sqlalchemy import create_engine, MetaData
from sqlalchemy.sql import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.config import load_postgres_config
from src.etl.load.schema_manager import ensure_database_and_tables
from src.utils.names import normalize_column_name

# Postgres hard limit is 65535 parameters per statement; stay well under this ceiling.
# Keep a wide buffer because the ON CONFLICT UPDATE portion can add parameters.
MAX_PARAMS_PER_STATEMENT = 20000


def save_df_to_postgres_upsert(
    df: pd.DataFrame,
    table_name: str,
    unique_cols: List[str],
    conn_string: str | None = None,
) -> None:
    """
    UPSERT a DataFrame into Postgres using ON CONFLICT DO UPDATE.

    unique_cols: columns that define a unique row, e.g. ["ad_id", "date_start"].
    """
    if df.empty:
        print(f"[postgres_loader] DataFrame is empty; nothing to upsert into {table_name}.")
        return

    if not conn_string:
        try:
            conn_string = load_postgres_config().conn_string
        except Exception as e:
            print(f"[postgres_loader] No DB connection available: {e}")
            return

    # Normalize column names for Postgres limit and drop duplicates after normalization
    df = df.copy()
    norm_cols = [normalize_column_name(c) for c in df.columns]
    df.columns = norm_cols

    # Convert datetime-like values to Python datetimes and null out NaT so psycopg2
    # doesn't see pandas NaT/ints in the payload.
    def _clean_dt(val):
        if isinstance(val, pd._libs.tslibs.nattype.NaTType):
            return None
        if isinstance(val, pd.Timestamp):
            return val.to_pydatetime()
        return val

    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].apply(lambda x: x.to_pydatetime() if pd.notnull(x) else None)
        else:
            # Even if dtype is object, sanitize Timestamp/NaT values.
            if df[col].apply(lambda x: isinstance(x, (pd.Timestamp, pd._libs.tslibs.nattype.NaTType))).any():
                df[col] = df[col].apply(_clean_dt)

    # Ensure unique columns exist and de-duplicate rows on the unique key to avoid
    # "ON CONFLICT DO UPDATE ... cannot affect row a second time" when duplicates
    # appear in the same batch.
    if unique_cols:
        missing_keys = [c for c in unique_cols if c not in df.columns]
        if missing_keys:
            raise ValueError(f"[postgres_loader] Missing unique key columns in DataFrame: {missing_keys}")
        # Normalize unique key columns to strings (keeping None for missing) so numeric
        # IDs (floats/ints) don't produce duplicate PKs within the same batch.
        for col in unique_cols:
            df[col] = df[col].apply(lambda x: None if pd.isna(x) else str(x))
        dup_mask = df.duplicated(subset=unique_cols, keep="last")
        dup_count = int(dup_mask.sum())
        if dup_count:
            print(f"[postgres_loader] Dropping {dup_count} duplicate rows on unique key {unique_cols} before upsert.")
            df = df.loc[~dup_mask]

    # Collapse duplicate normalized column names by taking the first non-null across duplicates
    duplicates = {}
    for idx, col in enumerate(norm_cols):
        duplicates.setdefault(col, []).append(idx)
    for col, idxs in duplicates.items():
        if len(idxs) <= 1:
            continue
        dup_df = df.iloc[:, idxs]
        merged = dup_df.bfill(axis=1).iloc[:, 0]
        df.drop(columns=dup_df.columns, inplace=True)
        df[col] = merged

    # Ensure DB and table/columns exist (based on normalized columns)
    try:
        ensure_database_and_tables(conn_string, [table_name], df=df)
    except Exception as e:
        print(f"[postgres_loader] Failed to ensure schema for '{table_name}': {e}")
        return

    # Create DB engine
    engine = create_engine(conn_string)
    metadata = MetaData()
    metadata.reflect(bind=engine)  # load existing tables

    if table_name not in metadata.tables:
        raise ValueError(f"[postgres_loader] Table '{table_name}' does not exist in the database.")

    table = metadata.tables[table_name]

    table_cols = set(table.columns.keys())
    df_cols = list(df.columns)
    dropped = [c for c in df_cols if c not in table_cols]
    if dropped:
        print(f"[postgres_loader] WARNING: dropping columns not in '{table_name}': {dropped}")
    # IMPORTANT: keep only columns that exist in the table
    df = df[[c for c in df_cols if c in table_cols]]

    # Convert DataFrame rows to list of dicts
    records = df.to_dict(orient="records")

    # Batch the upsert to respect Postgres parameter limits
    col_count = len(df.columns)
    if col_count == 0:
        print(f"[postgres_loader] No columns to upsert for '{table_name}'.")
        return
    # Each row contributes roughly `col_count` parameters for VALUES. Apply a 2x safety
    # multiplier to account for the UPDATE clause and stay well under Postgres limits.
    max_rows = max(1, MAX_PARAMS_PER_STATEMENT // (col_count * 2))

    total_rows = len(records)
    upserted = 0
    with engine.begin() as conn:
        for start in range(0, total_rows, max_rows):
            batch = records[start:start + max_rows]
            stmt = pg_insert(table).values(batch)
            insert_cols = set(df.columns)
            update_cols = {
                c.name: getattr(stmt.excluded, c.name)
                for c in table.columns
                if c.name in insert_cols and c.name not in unique_cols
            }
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=unique_cols,
                set_=update_cols,
            )
            conn.execute(upsert_stmt)
            upserted += len(batch)

    print(f"[postgres_loader] Upserted {upserted} rows into '{table_name}'.")


def truncate_all_tables(table_names: List[str], conn_string: str | None = None) -> None:
    """
    Truncate the given tables (if they exist) in a single statement.
    """
    if not conn_string:
        try:
            conn_string = load_postgres_config().conn_string
        except Exception as e:
            print(f"[postgres_loader] No DB connection available: {e}")
            return

    if not table_names:
        print("[postgres_loader] No tables provided to truncate.")
        return

    engine = create_engine(conn_string)
    with engine.begin() as conn:
        tables_str = ", ".join(table_names)
        conn.execute(text(f"TRUNCATE {tables_str} RESTART IDENTITY CASCADE;"))
    print(f"[postgres_loader] Truncated tables: {table_names}")


def insert_raw_insights(
    records: List[dict],
    level: str,
    breakdowns: list[str] | None = None,
    conn_string: str | None = None,
) -> None:
    """
    Append raw insights rows into meta_insights_raw.
    """
    if not records:
        return

    if not conn_string:
        try:
            conn_string = load_postgres_config().conn_string
        except Exception as e:
            print(f"[postgres_loader] No DB connection available: {e}")
            return

    # Ensure raw table exists
    try:
        ensure_database_and_tables(conn_string, ["meta_insights_raw"], df=None)
    except Exception as e:
        print(f"[postgres_loader] Failed to ensure schema for 'meta_insights_raw': {e}")
        return

    rows = []
    breakdown_str = ""
    if breakdowns:
        breakdown_str = ",".join(sorted([b.strip() for b in breakdowns if b and b.strip()]))
    for rec in records:
        account_id = rec.get("account_id")
        date_start = rec.get("date_start")
        date_stop = rec.get("date_stop")
        rows.append(
            {
                "account_id": account_id,
                "level": level,
                "date_start": date_start,
                "date_stop": date_stop,
                "breakdowns": breakdown_str,
                "payload": json.dumps(rec),
            }
        )

    engine = create_engine(conn_string)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO meta_insights_raw (account_id, level, date_start, date_stop, breakdowns, payload)
                VALUES (:account_id, :level, :date_start, :date_stop, :breakdowns, :payload)
                """
            ),
            rows,
        )
    print(f"[postgres_loader] Inserted {len(rows)} raw insight rows into 'meta_insights_raw'.")


def insert_raw_records(
    records: List[dict],
    table_name: str,
    key_mapping: Dict[str, str],
    conn_string: str | None = None,
) -> None:
    """
    Generic raw insert: maps record fields to table columns per key_mapping,
    stores full record as JSONB payload.
    key_mapping: {column_name_in_table: key_in_record}
    """
    if not records:
        return

    if not conn_string:
        try:
            conn_string = load_postgres_config().conn_string
        except Exception as e:
            print(f"[postgres_loader] No DB connection available: {e}")
            return

    try:
        ensure_database_and_tables(conn_string, [table_name], df=None)
    except Exception as e:
        print(f"[postgres_loader] Failed to ensure schema for '{table_name}': {e}")
        return

    rows = []
    for rec in records:
        row = {}
        for col, key in key_mapping.items():
            row[col] = rec.get(key)
        row["payload"] = json.dumps(rec)
        rows.append(row)

    cols_clause = ", ".join(list(key_mapping.keys()) + ["payload"])
    params_clause = ", ".join(f":{c}" for c in list(key_mapping.keys()) + ["payload"])
    sql = f"INSERT INTO {table_name} ({cols_clause}) VALUES ({params_clause})"

    engine = create_engine(conn_string)
    with engine.begin() as conn:
        conn.execute(text(sql), rows)
    print(f"[postgres_loader] Inserted {len(rows)} raw rows into '{table_name}'.")
