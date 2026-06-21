"""Persistent ETL run history.

Each CLI invocation is recorded in the etl_run_log table:

    run_id, command, profile, status, started_at, ended_at,
    duration_seconds, rows_loaded, error_message, host

Use it from SQL to answer "did yesterday's run succeed?" without grepping log
files. The recorder is best-effort: any failure to write to the run log is
logged and swallowed so it cannot mask the underlying pipeline failure.
"""
from __future__ import annotations

import os
import socket
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import create_engine, text

from src.utils.logger import get_logger

logger = get_logger(__name__)

_TABLE = "etl_run_log"
_DDL = (
    f"CREATE TABLE IF NOT EXISTS {_TABLE} ("
    "run_id TEXT PRIMARY KEY,"
    "command TEXT NOT NULL,"
    "profile TEXT,"
    "status TEXT NOT NULL,"
    "started_at TIMESTAMPTZ NOT NULL,"
    "ended_at TIMESTAMPTZ,"
    "duration_seconds NUMERIC,"
    "rows_loaded BIGINT,"
    "error_message TEXT,"
    "host TEXT"
    ")"
)


def _resolve_conn_string(profile: Optional[str]) -> Optional[str]:
    """Best-effort conn-string lookup; returns None if not configured.

    We don't want to crash health-check / --no-db runs just because a run
    log destination wasn't set up, so failures here are silent.
    """
    try:
        from src.config import load_postgres_config

        return load_postgres_config(profile).conn_string
    except Exception:
        return None


def _ensure_table(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(_DDL))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_etl_run_log_started_at "
                f"ON {_TABLE} (started_at DESC)"
            )
        )


def _utcnow():
    return datetime.now(timezone.utc)


def _record(
    *,
    conn_string: str,
    run_id: str,
    command: str,
    profile: Optional[str],
    status: str,
    started_at: datetime,
    ended_at: Optional[datetime],
    duration_seconds: Optional[float],
    rows_loaded: Optional[int],
    error_message: Optional[str],
) -> None:
    engine = create_engine(conn_string)
    _ensure_table(engine)
    sql = text(
        f"""
        INSERT INTO {_TABLE} (
            run_id, command, profile, status,
            started_at, ended_at, duration_seconds,
            rows_loaded, error_message, host
        ) VALUES (
            :run_id, :command, :profile, :status,
            :started_at, :ended_at, :duration_seconds,
            :rows_loaded, :error_message, :host
        )
        ON CONFLICT (run_id) DO UPDATE SET
            status = EXCLUDED.status,
            ended_at = EXCLUDED.ended_at,
            duration_seconds = EXCLUDED.duration_seconds,
            rows_loaded = EXCLUDED.rows_loaded,
            error_message = EXCLUDED.error_message
        """
    )
    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "run_id": run_id,
                "command": command,
                "profile": profile,
                "status": status,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_seconds": duration_seconds,
                "rows_loaded": rows_loaded,
                "error_message": (error_message or None),
                "host": socket.gethostname(),
            },
        )


@contextmanager
def record_run(command: str, profile: Optional[str]):
    """Context manager that records the lifecycle of a CLI invocation.

    Yields a mutable dict; set ``rows_loaded`` on it from inside the with-
    block to surface row counts in the run log. On exception the run is
    marked FAILED and a failure alert is dispatched via src.utils.alerts.
    """
    from src.utils.alerts import send_failure_alert

    run_id = uuid.uuid4().hex
    started_at = _utcnow()
    info = {"run_id": run_id, "rows_loaded": None}
    conn_string = _resolve_conn_string(profile)

    structlog.contextvars.bind_contextvars(run_id=run_id, command=command, profile=profile)

    if conn_string:
        try:
            _record(
                conn_string=conn_string,
                run_id=run_id,
                command=command,
                profile=profile,
                status="STARTED",
                started_at=started_at,
                ended_at=None,
                duration_seconds=None,
                rows_loaded=None,
                error_message=None,
            )
        except Exception as exc:
            logger.warning("Could not write STARTED row to etl_run_log", error=str(exc))

    try:
        yield info
    except Exception as exc:
        ended_at = _utcnow()
        duration = (ended_at - started_at).total_seconds()
        if conn_string:
            try:
                _record(
                    conn_string=conn_string,
                    run_id=run_id,
                    command=command,
                    profile=profile,
                    status="FAILED",
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_seconds=duration,
                    rows_loaded=info.get("rows_loaded"),
                    error_message=str(exc),
                )
            except Exception as log_exc:
                logger.warning("Could not write FAILED row to etl_run_log", error=str(log_exc))
        try:
            send_failure_alert(
                command=command,
                profile=profile,
                error=str(exc),
                duration_seconds=duration,
                run_id=run_id,
            )
        except Exception as alert_exc:
            logger.warning("Failure alert dispatch errored", error=str(alert_exc))
        structlog.contextvars.clear_contextvars()
        raise
    else:
        ended_at = _utcnow()
        duration = (ended_at - started_at).total_seconds()
        if conn_string:
            try:
                _record(
                    conn_string=conn_string,
                    run_id=run_id,
                    command=command,
                    profile=profile,
                    status="SUCCEEDED",
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_seconds=duration,
                    rows_loaded=info.get("rows_loaded"),
                    error_message=None,
                )
            except Exception as exc:
                logger.warning("Could not write SUCCEEDED row to etl_run_log", error=str(exc))
        structlog.contextvars.clear_contextvars()
