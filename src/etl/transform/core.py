import pandas as pd
import numpy as np
from typing import List, Dict, Any

from src.utils.logger import get_logger

logger = get_logger(__name__)


ID_LIKE_COLUMNS = {
    "id",
    "ad_id",
    "adset_id",
    "campaign_id",
    "account_id",
    "creative_id",
    "page_id",
}


def _coerce_numeric_if_safe(series: pd.Series) -> pd.Series:
    """
    Convert a series to numeric only when every non-null value is numeric-like.
    Otherwise, leave the series unchanged.
    """
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")

    non_null = series.dropna()
    if non_null.empty:
        return series

    coerced_non_null = pd.to_numeric(non_null, errors="coerce")
    if coerced_non_null.notna().all():
        return pd.to_numeric(series, errors="coerce")

    return series


def expand_action_array(cell, prefix):
    if not isinstance(cell, list):
        return {}

    flat = {}
    for item in cell:
        if not isinstance(item, dict):
            continue

        action_type = item.get("action_type") or item.get("indicator")
        value = item.get("value")

        if action_type is not None:
            col = f"{prefix}_{action_type}".replace(":", "_").replace(".", "_")
            flat[col] = value

    return flat


def normalize_meta_lists(df: pd.DataFrame) -> pd.DataFrame:
    """
    Auto-detect Meta list-columns (actions, results, video metrics, etc.)
    and expand them without hardcoding names.
    """

    for col in df.columns:
        # If any cell in this column is a list -> treat as Meta metric list
        if df[col].apply(lambda x: isinstance(x, list)).any():

            expanded = df[col].apply(lambda x: expand_action_array(x, col))
            if not expanded.apply(bool).any():
                # No action-type expansion possible; keep original list column.
                continue

            expanded_df = pd.json_normalize(expanded)

            df = pd.concat([df, expanded_df], axis=1)
            df.drop(columns=[col], inplace=True)

    return df


def flatten_json(records: List[Dict[str, Any]], expand_lists: bool = True) -> pd.DataFrame:
    """
    Flatten arbitrary JSON records to a DataFrame.
    If expand_lists is True, list-typed metrics (actions, results, etc.) are expanded into columns.
    """
    if not records:
        return pd.DataFrame()

    df = pd.json_normalize(records)

    if expand_lists:
        df = normalize_meta_lists(df)

    # Auto-cast numeric values (skip ID-like columns to avoid float coercion)
    for col in df.columns:
        col_lower = str(col).lower()
        if col_lower in ID_LIKE_COLUMNS or col_lower.endswith("_id"):
            continue
        df[col] = _coerce_numeric_if_safe(df[col])

    return df


def ensure_id_and_name(df: pd.DataFrame, id_col: str, name_col: str) -> pd.DataFrame:
    """
    Rename common Meta fields (id, name) to the target column names expected by our schemas.

    - If id_col is missing but an "id" column exists, rename it.
    - If name_col is missing but a "name" column exists, rename it.
    """
    if df.empty:
        return df

    df = df.copy()
    if id_col not in df.columns and "id" in df.columns:
        df = df.rename(columns={"id": id_col})
    if name_col not in df.columns and "name" in df.columns:
        df = df.rename(columns={"name": name_col})
    return df


def coerce_datetime_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """
    Convert columns to pandas datetime, coercing invalid/NaN to None so psycopg2
    sends NULL instead of float NaN.
    """
    if df.empty or not columns:
        return df

    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        parsed = pd.to_datetime(df[col], errors="coerce", utc=True)
        cleaned = [
            ts.to_pydatetime() if pd.notnull(ts) else None
            for ts in parsed
        ]
        df[col] = pd.Series(cleaned, dtype=object)
    return df


def apply_rename_map(
    df: pd.DataFrame,
    pipeline: str,
    table_name: str = "",
) -> pd.DataFrame:
    """
    Rename API field names → DB column names for the given pipeline.

    Behaviour driven by the 'status' column in api_field_rename_template.csv:
      approved  → renamed (using rename_to if set, else current_database_column)
      excluded  → column silently dropped from the DataFrame
      pending   → column skipped (not loaded); a warning is printed listing the fields
      (unknown) → auto-appended to CSV as 'pending' and skipped this run

    Call this after flatten_json(), before fill_numeric_keep_nulls() or DB save.
    To add or change a mapping, edit the CSV — no code changes needed.
    """
    from src.fields.rename_maps import (
        get_rename_map,
        get_excluded_fields,
        get_pending_fields,
        get_known_fields,
        register_new_fields,
    )

    if df.empty:
        return df

    df = df.copy()
    df_cols = set(df.columns)

    # --- 1. Drop excluded fields ---
    excluded = get_excluded_fields(pipeline) & df_cols
    if excluded:
        df.drop(columns=list(excluded), inplace=True)
        df_cols = set(df.columns)

    # --- 2. Detect brand-new fields (not in CSV at all) and register as pending ---
    known = get_known_fields(pipeline)
    brand_new = [c for c in df.columns if c not in known]
    if brand_new:
        n = register_new_fields(pipeline, table_name, brand_new)
        if n:
            logger.warning(
                "New API fields auto-registered as pending",
                pipeline=pipeline,
                count=n,
                fields=sorted(brand_new),
                action="open api_field_rename_template.csv, set rename_to, change status to approved, then re-run",
            )

    # --- 3. Drop pending fields (new + previously pending) ---
    pending = get_pending_fields(pipeline) & df_cols
    # Also drop brand-new fields registered this run (they're now pending too)
    skip_cols = pending | set(brand_new)
    if skip_cols:
        actually_skipped = skip_cols & df_cols
        if actually_skipped:
            logger.info(
                "Pending fields skipped (not loaded until approved in CSV)",
                pipeline=pipeline,
                count=len(actually_skipped),
                fields=sorted(actually_skipped),
            )
            df.drop(columns=list(actually_skipped), inplace=True)

    # --- 4. Apply approved renames ---
    rename = {k: v for k, v in get_rename_map(pipeline).items() if k in df.columns}
    if rename:
        df = df.rename(columns=rename)

    return df


def fill_numeric_keep_nulls(df: pd.DataFrame) -> pd.DataFrame:
    """
    For numeric-like columns, coerce to numeric and fill NaN/None with 0.
    For non-numeric columns (or ID-like columns), leave NaN/None intact.
    """
    if df.empty:
        return df

    df = df.copy()
    def _normalize_id_value(val):
        try:
            if pd.isna(val):
                return None
        except Exception:
            pass
        if isinstance(val, (np.integer, int)):
            return str(int(val))
        if isinstance(val, (np.floating, float)):
            if np.isnan(val):
                return None
            if float(val).is_integer():
                return str(int(val))
            return str(val)
        return str(val)

    for col in df.columns:
        col_lower = str(col).lower()
        if col_lower in ID_LIKE_COLUMNS or col_lower.endswith("_id"):
            # keep IDs as text; don't coerce/fill
            df[col] = df[col].apply(_normalize_id_value)
            continue
        # Leave datetime columns untouched to avoid coercing to int nanoseconds
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        # Skip columns that hold datetime-like objects even if dtype is object.
        if df[col].apply(lambda x: isinstance(x, (pd.Timestamp, pd._libs.tslibs.nattype.NaTType)) or hasattr(x, "isoformat")).any():
            continue

        series = df[col]
        # Detect numeric-like: actual numeric dtype or all non-null values convertible
        if pd.api.types.is_numeric_dtype(series):
            df[col] = pd.to_numeric(series, errors="coerce").fillna(0)
            continue

        non_null = series.dropna()
        if not non_null.empty:
            coerced_non_null = pd.to_numeric(non_null, errors="coerce")
            if coerced_non_null.notna().all():
                coerced_full = pd.to_numeric(series, errors="coerce")
                df[col] = coerced_full.fillna(0)

    return df
