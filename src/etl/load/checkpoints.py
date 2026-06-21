"""Insights range checkpointing.

Records every (profile, level, breakdowns_key, since, until) tuple that has
been successfully loaded so insights-range can resume after a partial failure
without redoing finished chunks. Set ``--force`` (or ``force=True`` in code)
to re-fetch chunks that are already marked complete.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional, Set, Tuple

from sqlalchemy import create_engine, text

from src.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = "etl_insights_checkpoint"
_DDL = (
    f"CREATE TABLE IF NOT EXISTS {_TABLE} ("
    "profile TEXT NOT NULL,"
    "level TEXT NOT NULL,"
    "breakdowns_key TEXT NOT NULL,"
    "since DATE NOT NULL,"
    "until DATE NOT NULL,"
    "rows_loaded BIGINT,"
    "completed_at TIMESTAMPTZ NOT NULL,"
    "PRIMARY KEY (profile, level, breakdowns_key, since, until)"
    ")"
)


def _profile_key(profile: Optional[str]) -> str:
    return (profile or "default").lower()


def breakdowns_key(breakdowns: Optional[Iterable[str]]) -> str:
    if not breakdowns:
        return "none"
    return ",".join(sorted(b.strip().lower() for b in breakdowns if b))


def _ensure_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(_DDL))


def fetch_completed(
    *,
    conn_string: str,
    profile: Optional[str],
    level: str,
    breakdowns: Optional[List[str]],
) -> Set[Tuple[str, str]]:
    """Return the set of (since, until) ISO strings already completed."""
    engine = create_engine(conn_string)
    _ensure_table(engine)
    sql = text(
        f"SELECT since, until FROM {_TABLE} "
        "WHERE profile = :profile AND level = :level AND breakdowns_key = :bk"
    )
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "profile": _profile_key(profile),
                "level": level,
                "bk": breakdowns_key(breakdowns),
            },
        ).fetchall()
    return {(r[0].isoformat(), r[1].isoformat()) for r in rows}


def mark_completed(
    *,
    conn_string: str,
    profile: Optional[str],
    level: str,
    breakdowns: Optional[List[str]],
    since: str,
    until: str,
    rows_loaded: int,
) -> None:
    engine = create_engine(conn_string)
    _ensure_table(engine)
    sql = text(
        f"""
        INSERT INTO {_TABLE}
            (profile, level, breakdowns_key, since, until, rows_loaded, completed_at)
        VALUES
            (:profile, :level, :bk, :since, :until, :rows_loaded, :completed_at)
        ON CONFLICT (profile, level, breakdowns_key, since, until) DO UPDATE SET
            rows_loaded = EXCLUDED.rows_loaded,
            completed_at = EXCLUDED.completed_at
        """
    )
    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "profile": _profile_key(profile),
                "level": level,
                "bk": breakdowns_key(breakdowns),
                "since": since,
                "until": until,
                "rows_loaded": rows_loaded,
                "completed_at": datetime.now(timezone.utc),
            },
        )
