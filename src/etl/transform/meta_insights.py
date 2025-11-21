from typing import List, Dict, Any
import pandas as pd
import numpy as np


from src.etl.transform.core import flatten_json
from src.schema import column_renames

def normalize_insights(records: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Insights-specific cleaning.
    Core flattening is done in core.flatten_json().
    """
    df = flatten_json(records)
    df = df.rename(columns=column_renames.META_RENAME_MAP, errors="ignore")
    df = df.replace([np.inf, -np.inf], None)
    df = df.replace({np.nan: None})



    # Add endpoint-specific cleaning here later:
    # - handle actions arrays
    # - extract purchase values
    # - rename columns
    # - filter unwanted fields

    return df

def drop_pure_zero_rows(df):
    metric_cols = [
        "spend", "impressions", "clicks",
        "purchase", "pixel_purchase", "value_purchase",
        # add more key metrics you care about
    ]

    df[metric_cols] = df[metric_cols].fillna(0)

    mask = (df[metric_cols].sum(axis=1) > 0)
    return df[mask]