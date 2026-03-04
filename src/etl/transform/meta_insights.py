import re
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

from src.utils.logging_utils import get_logger
from src.etl.transform.core import flatten_json, fill_numeric_keep_nulls

logger = get_logger("transform.insights")


def _split_results_columns(records: List[Dict[str, Any]]) -> None:
    """
    Convert the Meta "results" list into two simple columns:
    - results_indicator: comma-separated indicators
    - results_value: comma-separated values

    Removes the original "results" key to avoid column explosion.
    """
    for rec in records:
        res = rec.get("results")
        indicators: List[str] = []
        values: List[str] = []

        if isinstance(res, list):
            for item in res:
                if not isinstance(item, dict):
                    continue
                indicator = item.get("indicator") or item.get("action_type")
                value = item.get("value")
                # Meta often wraps values in a "values": [{"value": "..."}] list
                if value is None and isinstance(item.get("values"), list):
                    for val_item in item["values"]:
                        if isinstance(val_item, dict) and "value" in val_item:
                            value = val_item.get("value")
                            break
                if indicator is not None:
                    indicators.append(str(indicator))
                    # Default missing values to 0 to avoid empty strings
                    val = 0 if value is None else value
                    values.append(str(val))
        elif isinstance(res, dict):
            # Handle dict-shaped results: keys as indicators, values as result
            for indicator, value in res.items():
                indicators.append(str(indicator))
                val = 0 if value is None else value
                values.append(str(val))
        elif res is not None:
            # Scalar fallback
            indicators.append("results")
            val = 0 if res is None else res
            values.append(str(val))

        rec["results_indicator"] = ",".join(indicators) if indicators else None
        rec["results_value"] = ",".join(values) if values else None

        # remove original list to prevent expansion into many columns
        if "results" in rec:
            rec.pop("results", None)


def _collapse_numbered_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse columns that were auto-numbered (col, col.1, col.2...) by pandas,
    keeping the first non-null value across the set.
    """
    collapsed_sets = []
    grouped: Dict[str, List[str]] = {}
    for col in df.columns:
        m = re.match(r"(.+)\.(\d+)$", str(col))
        if m:
            base = m.group(1)
            grouped.setdefault(base, []).append(col)

    for base, suffix_cols in grouped.items():
        cols = [c for c in [base] + suffix_cols if c in df.columns]
        if not cols:
            continue
        combined = df[cols].bfill(axis=1).iloc[:, 0]
        df = df.drop(columns=cols)
        df[base] = combined
        collapsed_sets.append({"base_name": base, "duplicates": [c for c in cols if c != base]})

    # Handle exact duplicate labels if any remain
    dupes = df.columns[df.columns.duplicated()].unique()
    for col in dupes:
        cols = [c for c in df.columns if c == col]
        combined = df[cols].bfill(axis=1).iloc[:, 0]
        df = df.drop(columns=cols)
        df[col] = combined
        collapsed_sets.append({"base_name": col, "duplicates": [c for c in cols if c != col]})

    if collapsed_sets:
        logger.info("Collapsed duplicate columns: %s", collapsed_sets)

    return df


def get_insights_table_name(level: str, breakdowns: Optional[List[str]] = None) -> str:
    base = f"fact_meta_delivery_{level}"
    if not breakdowns:
        return base
    suffix = "_".join(sorted([b.strip() for b in breakdowns if b and b.strip()]))
    return f"{base}__{suffix}"


def normalize_insights(
    records: List[Dict[str, Any]],
    level: str,
    breakdowns: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Insights-specific cleaning.
    Core flattening is done in core.flatten_json().
    """
    breakdowns = breakdowns or []

    # Split the "results" list into two simple columns before flattening
    _split_results_columns(records)

    df = flatten_json(records, expand_lists=True)
    df = _collapse_numbered_duplicates(df)
    df = df.replace([np.inf, -np.inf], None)
    df = df.replace({np.nan: None})

    # Ensure key columns present
    id_map = {
        "ad": "ad_id",
        "adset": "adset_id",
        "campaign": "campaign_id",
        "account": "account_id",
    }
    id_col = id_map.get(level)
    if id_col and id_col not in df.columns:
        df[id_col] = None
    for col in ["date_start", "date_stop"]:
        if col not in df.columns:
            df[col] = None

    # Ensure breakdown columns exist
    for b in breakdowns:
        b = b.strip()
        if b and b not in df.columns:
            df[b] = None

    df = fill_numeric_keep_nulls(df)

    return df
