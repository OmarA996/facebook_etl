import pandas as pd
from typing import List, Dict, Any



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
            expanded_df = pd.json_normalize(expanded)

            df = pd.concat([df, expanded_df], axis=1)
            df.drop(columns=[col], inplace=True)

    return df


def flatten_json(records: List[Dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()

    df = pd.json_normalize(records)
    

    # Automatically normalize all Meta weird list fields
    df = normalize_meta_lists(df)

    # Auto-cast numeric values
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="ignore")

    return df
