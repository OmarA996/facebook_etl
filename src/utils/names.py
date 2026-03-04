PG_MAX_NAME_LEN = 63


def shorten_from_left(name: str, max_len: int = PG_MAX_NAME_LEN) -> str:
    """
    Normalize a name to fit within PostgreSQL's identifier length limit
    by trimming from the left if necessary.
    """
    if name is None:
        return name
    name = str(name)
    if len(name) <= max_len:
        return name
    return name[-max_len:]


def shorten_from_right(name: str, max_len: int = PG_MAX_NAME_LEN) -> str:
    """
    Postgres historically truncates long identifiers from the right (keeping the leftmost part).
    This helper mirrors that behavior so we can detect legacy columns that were auto-truncated.
    """
    if name is None:
        return name
    name = str(name)
    if len(name) <= max_len:
        return name
    return name[:max_len]


def normalize_column_name(col: str, max_len: int = PG_MAX_NAME_LEN) -> str:
    """
    Normalize a column name for Postgres:
    - strip spaces
    - replace spaces, dots, and colons with underscore
    - lowercase
    - truncate from the left to max_len
    """
    if col is None:
        return col
    col = (
        str(col)
        .strip()
        .replace(" ", "_")
        .replace(".", "_")
        .replace(":", "_")
        .lower()
    )
    if len(col) > max_len:
        col = col[-max_len:]
    return col
