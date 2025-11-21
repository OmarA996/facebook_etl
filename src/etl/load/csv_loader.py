from pathlib import Path
import pandas as pd


def save_df_to_csv(df: pd.DataFrame, filepath: str) -> str:
    """
    Save a DataFrame to any absolute or relative file path.
    
    Example:
        save_df_to_csv(df, r"C:\\Users\\Mahmoud\\Desktop\\file.csv")
        save_df_to_csv(df, "data/output.csv")
    """
    if df.empty:
        print("[csv_loader] DataFrame is empty; nothing to save.")
        return ""

    path = Path(filepath)

    # Ensure directories exist
    path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[csv_loader] Saved {len(df)} rows to {path}")
    return str(path)
