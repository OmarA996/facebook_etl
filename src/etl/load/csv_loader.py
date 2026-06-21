from pathlib import Path
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)


def save_df_to_csv(df: pd.DataFrame, filepath: str) -> str:
    """
    Save a DataFrame to any absolute or relative file path.

    Example:
        save_df_to_csv(df, r"C:\\Users\\Mahmoud\\Desktop\\file.csv")
        save_df_to_csv(df, "data/output.csv")
    """
    if df.empty:
        logger.warning("DataFrame is empty, nothing to save", filepath=filepath)
        return ""

    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(path, index=False, encoding="utf-8-sig")
    logger.info("Saved CSV", rows=len(df), path=str(path))
    return str(path)
