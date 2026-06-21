from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url, URL

from src.schema.tables import TABLE_SCHEMAS
from src.schema.unique_keys import UNIQUE_KEYS
from src.schema.views import STATIC_FACT_COLUMNS, VIEW_NAME, postgres_view_sql
from src.utils.names import shorten_from_left, shorten_from_right, normalize_column_name
from src.utils.logger import get_logger

logger = get_logger(__name__)

TYPE_INFER_MAP = {
    "int64": "INTEGER",
    "int32": "INTEGER",
    "float64": "NUMERIC",
    "float32": "NUMERIC",
    "datetime64[ns]": "TIMESTAMPTZ",
    "datetime64[ns, utc]": "TIMESTAMPTZ",
    "bool": "BOOLEAN",
    "object": "TEXT",
    "string": "TEXT",
}

# None = no cap on inferred columns; set to an int to limit.
MAX_INFERRED_COLUMNS: int | None = None

ID_LIKE_COLUMNS = {
    "ad_id",
    "account_id",
    "campaign_id",
    "adset_id",
    "creative_id",
    "page_id",
    "id",
}


def _sanitize_col_name(name: str) -> str:
    """
    Normalize a column name for Postgres: replace dots/colons with underscores,
    lowercase, strip spaces, and cap length.
    """
    if name is None:
        return name
    safe = str(name).replace(".", "_").replace(":", "_")
    safe = normalize_column_name(safe)
    return safe


def _infer_sql_type_from_series(series: pd.Series) -> str:
    dtype_str = str(series.dtype)
    return TYPE_INFER_MAP.get(dtype_str, "TEXT")


def _is_numeric_like(series: pd.Series) -> bool:
    """
    Determine whether a Series can be safely treated as numeric.
    """
    if series.empty:
        return False
    # Treat empty strings as missing
    series = series.replace("", pd.NA)

    non_null = series.dropna()
    if non_null.empty:
        return False

    coerced = pd.to_numeric(non_null, errors="coerce")
    return coerced.notna().all()


def _parse_dbname(url: URL) -> str:
    if not url.database:
        raise ValueError("Connection URL missing database name.")
    return url.database


def _url_without_db(url: URL) -> URL:
    return url.set(database="postgres")


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def ensure_database_exists(conn_string: str) -> None:
    """
    Ensure the target database exists; create if missing.
    """
    url = make_url(conn_string)
    dbname = _parse_dbname(url)
    server_url = _url_without_db(url)

    server_engine = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with server_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname=:dname"), {"dname": dbname}
        ).scalar()
        if not exists:
            quoted_dbname = _quote_ident(dbname)
            conn.execute(text(f"CREATE DATABASE {quoted_dbname} ENCODING 'UTF8' TEMPLATE template1"))
            logger.info("Created database", db=dbname)


def _create_table(engine: Engine, table_name: str, schema_def: Dict[str, str]) -> None:
    cols = []
    for col, col_type in schema_def.items():
        cols.append(f"{col} {col_type}")
    cols_clause = ", ".join(cols)
    sql = f"CREATE TABLE {table_name} ({cols_clause});"
    with engine.begin() as conn:
        conn.execute(text(sql))
    logger.info("Created table", table=table_name)


def _ensure_unique_index(engine: Engine, table_name: str, key_cols: list[str]) -> None:
    """
    Ensure a unique index exists on the given columns to support ON CONFLICT.
    """
    if not key_cols:
        return
    idx_name_raw = f"uq_{table_name}_{'_'.join(key_cols)}"
    idx_name = shorten_from_left(idx_name_raw)
    cols_clause = ", ".join(key_cols)
    with engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {idx_name} "
                f"ON {table_name} ({cols_clause})"
            )
        )


def ensure_table_schema(engine: Engine, table_name: str, expected_schema: Dict[str, str], df: Optional[pd.DataFrame] = None) -> None:
    inspector = inspect(engine)
    existing_cols_raw = inspector.get_columns(table_name) if inspector.has_table(table_name) else []
    existing_names_all: set[str] = set()
    for col in existing_cols_raw:
        name = col["name"]
        existing_names_all.add(name)
        existing_names_all.add(shorten_from_left(name))
        existing_names_all.add(shorten_from_right(name))
        existing_names_all.add(_sanitize_col_name(name))

    if not existing_cols_raw:
        # create with normalized names
        if expected_schema:
            normalized_schema = {shorten_from_left(k): v for k, v in expected_schema.items()}
        elif df is not None and not df.empty:
            normalized_schema = {shorten_from_left(c): "TEXT" for c in df.columns}
        else:
            normalized_schema = {}
        _create_table(engine, table_name, normalized_schema)
        existing_cols_raw = inspect(engine).get_columns(table_name)
        existing_names_all = set()
        for col in existing_cols_raw:
            name = col["name"]
            existing_names_all.add(name)
            existing_names_all.add(shorten_from_left(name))
            existing_names_all.add(shorten_from_right(name))

    missing_columns: Dict[str, str] = {}
    for col, col_type in expected_schema.items():
        norm_col = shorten_from_left(col)
        norm_pg_style = shorten_from_right(col)
        if norm_col in existing_names_all or norm_pg_style in existing_names_all:
            continue
        missing_columns[norm_col] = col_type
        existing_names_all.add(norm_col)

    # If existing columns have ID-like names but integer types, coerce to TEXT to avoid overflow
    if existing_cols_raw:
        for col in existing_cols_raw:
            col_name = col["name"]
            if table_name.startswith("meta_") and table_name.endswith("_raw") and col_name == "id":
                continue
            norm_col = shorten_from_left(col_name)
            if norm_col in ID_LIKE_COLUMNS or norm_col.endswith("_id"):
                col_type = str(col["type"]).lower()
                if "int" in col_type:
                    with engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN {col_name} TYPE TEXT USING {col_name}::text;"))
                    logger.info("Altered column to TEXT for large IDs", table=table_name, column=col_name)

    # Align date columns to DATE where expected
    if existing_cols_raw and expected_schema:
        for col in existing_cols_raw:
            col_name = col["name"]
            if col_name not in expected_schema:
                continue
            expected_type = expected_schema.get(col_name, "").upper()
            if expected_type != "DATE":
                continue
            col_type = str(col["type"]).lower()
            if "timestamp" in col_type or "time" in col_type or "date" not in col_type:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table_name} ALTER COLUMN {col_name} TYPE DATE USING NULLIF({col_name}, '')::date;"
                        )
                    )
                logger.info("Altered column to DATE to match schema", table=table_name, column=col_name)

    # Add inferred columns from df if not in expected_schema
    if df is not None:
        inferred_candidates: Dict[str, str] = {}
        for col in df.columns:
            norm_col = shorten_from_left(col)
            norm_pg_style = shorten_from_right(col)
            safe_col = _sanitize_col_name(col)
            if norm_col in existing_names_all or norm_pg_style in existing_names_all or safe_col in existing_names_all:
                continue
            # Skip columns that hold lists/dicts to avoid schema explosion; keep them as JSON data in the column.
            series = df[col]
            if series.apply(lambda x: isinstance(x, (list, dict))).any():
                continue
            # Infer type from the series; keep IDs as TEXT
            target_col = safe_col
            if target_col in ID_LIKE_COLUMNS or target_col.endswith("_id"):
                inferred_type = "TEXT"
            else:
                inferred_type = _infer_sql_type_from_series(series)
            inferred_candidates[target_col] = inferred_type

        items = list(inferred_candidates.items())
        if MAX_INFERRED_COLUMNS is not None and len(items) > MAX_INFERRED_COLUMNS:
            logger.info(
                "Limiting inferred columns to avoid schema explosion",
                table=table_name,
                inferred=len(items),
                limit=MAX_INFERRED_COLUMNS,
            )
            items = items[:MAX_INFERRED_COLUMNS]
        for col, col_type in items:
            missing_columns[col] = col_type
            existing_names_all.add(col)

    # If df provided, upgrade existing TEXT columns to NUMERIC when the incoming data is numeric-like
    if df is not None and existing_cols_raw:
        for col in existing_cols_raw:
            col_name = col["name"]
            norm_col = shorten_from_left(col_name)
            if norm_col in ID_LIKE_COLUMNS or norm_col.endswith("_id"):
                continue
            if norm_col not in df.columns:
                continue
            series = df[norm_col]
            col_type = str(col["type"]).lower()
            if ("text" in col_type or "char" in col_type) and _is_numeric_like(series):
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            f"ALTER TABLE {table_name} ALTER COLUMN {col_name} TYPE NUMERIC USING NULLIF({col_name}, '')::numeric;"
                        )
                    )
                logger.info("Altered column to NUMERIC based on incoming data", table=table_name, column=col_name)

    for col, col_type in missing_columns.items():
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col} {col_type};"))
        logger.info("Added column", table=table_name, column=col, col_type=col_type)


def ensure_views(engine: Engine) -> None:
    try:
        insp = inspect(engine)
        all_fact_cols = {col["name"] for col in insp.get_columns("fact_meta_delivery_ad")}
        extra = sorted(all_fact_cols - STATIC_FACT_COLUMNS)

        existing_dim_cols = {
            tbl: {col["name"] for col in insp.get_columns(tbl)}
            for tbl in ("dim_meta_accounts", "dim_meta_ads", "dim_meta_creatives")
            if insp.has_table(tbl)
        }

        sql = postgres_view_sql(extra_fact_columns=extra, existing_dim_cols=existing_dim_cols)
        with engine.begin() as conn:
            conn.execute(text(f"DROP VIEW IF EXISTS {VIEW_NAME}"))
            conn.execute(text(sql))
        logger.info("Created/updated view", view=VIEW_NAME, dynamic_columns=len(extra))
    except Exception as exc:
        first_line = str(exc).splitlines()[0]
        logger.warning("Could not create/update view", view=VIEW_NAME, error=first_line)


def ensure_database_and_tables(conn_string: str, table_names: Optional[List[str]] = None, df: Optional[pd.DataFrame] = None) -> None:
    """
    Ensure database exists; ensure tables exist and have required columns.
    If df is provided, will add missing columns based on df for the target tables.
    """
    ensure_database_exists(conn_string)
    engine = create_engine(conn_string)
    targets = table_names or list(TABLE_SCHEMAS.keys())

    for table_name in targets:
        expected_schema = TABLE_SCHEMAS.get(table_name, {})
        ensure_table_schema(engine, table_name, expected_schema, df=df)
        # Ensure unique index for ON CONFLICT support
        key_cols = UNIQUE_KEYS.get(table_name, [])
        _ensure_unique_index(engine, table_name, key_cols)

    inspector = inspect(engine)
    required = {"fact_meta_delivery_ad", "dim_meta_accounts", "dim_meta_ads", "dim_meta_creatives"}
    if required.issubset(set(inspector.get_table_names())):
        ensure_views(engine)
