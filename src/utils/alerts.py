"""Failure alerting helpers.

Sends notifications to Slack and/or a generic webhook when a pipeline run
fails. Both destinations are optional; if neither is configured the helper
silently returns. Network errors raised by the alert call itself are caught
and logged so a transient Slack outage cannot mask the real pipeline error.
"""
from __future__ import annotations

import os
import socket
from typing import Optional

import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

_TIMEOUT_SECONDS = 5


def _slack_webhook() -> Optional[str]:
    return os.environ.get("ALERT_SLACK_WEBHOOK_URL") or None


def _generic_webhook() -> Optional[str]:
    return os.environ.get("ALERT_WEBHOOK_URL") or None


def _environment_label() -> str:
    return os.environ.get("ALERT_ENVIRONMENT") or "unknown"


def send_failure_alert(
    *,
    command: str,
    profile: Optional[str],
    error: str,
    duration_seconds: Optional[float] = None,
    run_id: Optional[str] = None,
) -> None:
    slack = _slack_webhook()
    generic = _generic_webhook()
    if not slack and not generic:
        return

    host = socket.gethostname()
    env = _environment_label()
    duration_text = f"{duration_seconds:.1f}s" if duration_seconds is not None else "n/a"

    title = f":rotating_light: Meta ETL failure — `{command}`"
    fields = [
        f"*Environment:* {env}",
        f"*Host:* {host}",
        f"*Profile:* {profile or '(default)'}",
        f"*Duration:* {duration_text}",
    ]
    if run_id:
        fields.append(f"*Run ID:* `{run_id}`")
    body = "\n".join(fields) + f"\n*Error:* ```{error[:1500]}```"

    if slack:
        try:
            requests.post(
                slack,
                json={"text": f"{title}\n{body}"},
                timeout=_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # pragma: no cover - network error
            logger.warning("Slack alert failed", error=str(exc))

    if generic:
        try:
            requests.post(
                generic,
                json={
                    "command": command,
                    "profile": profile,
                    "environment": env,
                    "host": host,
                    "duration_seconds": duration_seconds,
                    "run_id": run_id,
                    "error": error,
                    "status": "FAILED",
                },
                timeout=_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # pragma: no cover - network error
            logger.warning("Generic webhook alert failed", error=str(exc))
