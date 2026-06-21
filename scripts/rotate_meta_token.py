"""Rotate the Meta long-lived access token.

Exchanges a short-lived user token for a long-lived one (lifetime ~60 days)
using the Meta Graph API. Writes the new token back into the project .env
file in place of META_ACCESS_TOKEN.

Usage:
    python scripts/rotate_meta_token.py --short-token <token>

Requires META_APP_ID and META_APP_SECRET to be set in the .env file.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import dotenv_values, load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def exchange_token(app_id: str, app_secret: str, short_token: str, version: str) -> dict:
    url = f"https://graph.facebook.com/{version}/oauth/access_token"
    resp = requests.get(
        url,
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def write_token(env_path: Path, new_token: str) -> None:
    if not env_path.exists():
        raise FileNotFoundError(f".env not found at {env_path}")

    lines = env_path.read_text(encoding="utf-8").splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith("META_ACCESS_TOKEN="):
            lines[i] = f"META_ACCESS_TOKEN={new_token}"
            replaced = True
            break
    if not replaced:
        lines.append(f"META_ACCESS_TOKEN={new_token}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate Meta long-lived access token")
    parser.add_argument("--short-token", required=True, help="Short-lived token from Graph API Explorer")
    parser.add_argument("--env", default=str(ENV_PATH), help="Path to .env file to update")
    args = parser.parse_args()

    load_dotenv(args.env)
    cfg = dotenv_values(args.env)

    app_id = os.environ.get("META_APP_ID") or cfg.get("META_APP_ID")
    app_secret = os.environ.get("META_APP_SECRET") or cfg.get("META_APP_SECRET")
    version = os.environ.get("META_API_VERSION") or cfg.get("META_API_VERSION") or "v25.0"

    if not app_id or not app_secret:
        print("ERROR: META_APP_ID and META_APP_SECRET must be set in .env", file=sys.stderr)
        return 2

    payload = exchange_token(app_id, app_secret, args.short_token, version)
    new_token = payload.get("access_token")
    if not new_token:
        print(f"ERROR: no access_token in response: {payload}", file=sys.stderr)
        return 3

    write_token(Path(args.env), new_token)
    expires = payload.get("expires_in", "unknown")
    print(f"OK: rotated META_ACCESS_TOKEN (expires_in={expires}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
