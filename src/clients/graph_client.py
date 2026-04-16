# src/clients/graph_client.py

import random
import time
from typing import Any, Dict, Iterable, List, Optional

import requests


class GraphAPIError(RuntimeError):
    """Custom exception for Graph API errors."""


class GraphAPIClient:
    """
    Robust client for interacting with the Meta Graph API.
    
    Features:
    - Automatic access token injection
    - Exponential backoff and retry for rate limits (429) and server errors (5xx)
    - Handling of 'Retry-After' headers
    - Automatic pagination support (paging.next and cursors)
    """
    def __init__(
        self,
        access_token: str,
        version: str = "v22.0",
        base_url: str = "https://graph.facebook.com",
        timeout: float = 30.0,
    ):
        """
        Initialize the Graph API client.

        Args:
            access_token: Long-lived User or System User access token.
            version: API version string (e.g. 'v21.0').
            base_url: Base graph URL.
            timeout: Request timeout in seconds.
        """
        self.access_token = access_token
        self.version = version
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # --------------------------------------------------
    # URL builder
    # --------------------------------------------------
    def _build_url(self, endpoint: str) -> str:
        # endpoint examples: "me/adaccounts", "act_123/insights", "12345"
        endpoint = endpoint.lstrip("/")
        return f"{self.base_url}/{self.version}/{endpoint}"

    # --------------------------------------------------
    # Core request with retry / rate-limit handling
    # --------------------------------------------------
    def _request_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        max_retries: int = 5,
        base_backoff: float = 1.0,
    ) -> Dict[str, Any]:
        """
        GET URL -> JSON with:
          - automatic access_token injection (if not present)
          - retry on 429 + 5xx
          - respect Retry-After when present
        """
        params = dict(params or {})

        # Inject token only if absent from both params dict and the URL itself.
        # paging.next URLs already contain access_token; adding it again via params
        # causes it to accumulate on every page, eventually exceeding Meta's URL limit.
        if "access_token" not in params and "access_token" not in url:
            params["access_token"] = self.access_token

        for attempt in range(max_retries):
            try:
                resp = requests.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as e:
                # Network issue (DNS, connection reset, etc.)
                if attempt < max_retries - 1:
                    sleep_for = base_backoff * (2**attempt)
                    time.sleep(sleep_for)
                    continue
                raise GraphAPIError(f"Network error calling {url}: {e}") from e

            status = resp.status_code

            # Success
            if status == 200:
                return resp.json()

            # Rate limit or server error
            if status in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        sleep_for = float(retry_after)
                    except ValueError:
                        sleep_for = base_backoff * (2**attempt)
                else:
                    # Exponential backoff + jitter
                    sleep_for = base_backoff * (2**attempt) + random.uniform(0, 0.5)

                time.sleep(sleep_for)
                # On 429/5xx, retry with same params
                continue

            # For 4xx (other than 429) or exhausted retries: raise detailed error
            try:
                payload = resp.json()
            except ValueError:
                payload = {"raw_text": resp.text}

            raise GraphAPIError(f"HTTP {status} calling {url}: {payload}")

        # If we somehow exit loop without returning or raising above
        raise GraphAPIError(f"Unreachable state calling {url}")

    # --------------------------------------------------
    # Generic pagination
    # --------------------------------------------------
    def iterate(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        use_next_url: bool = True,
        data_key: str = "data",
        max_pages: Optional[int] = None,
        max_rows: Optional[int] = None,
    ) -> Iterable[Dict[str, Any]]:
        """
        Stream all rows across pages from a Graph endpoint.

        - use_next_url=True:
            follow 'paging.next' (fully formed URL) -> safest
        - use_next_url=False:
            use 'cursors.after' with the same base URL

        You almost always want use_next_url=True for Insights.
        """
        params = dict(params or {})
        # Do NOT add access_token here; _request_json handles it

        base_url = self._build_url(endpoint)
        rows_yielded = 0
        pages_seen = 0

        if use_next_url:
            # First call with params, then follow paging.next
            url = base_url
            first = True
            while True:
                if max_pages is not None and pages_seen >= max_pages:
                    break

                payload = self._request_json(url, params=params if first else None)
                pages_seen += 1

                data = payload.get(data_key) or []
                if not isinstance(data, list):
                    data = []

                for row in data:
                    yield row
                    rows_yielded += 1
                    if max_rows is not None and rows_yielded >= max_rows:
                        return

                paging = payload.get("paging") or {}
                next_url = paging.get("next")
                if not next_url:
                    break

                url = next_url
                first = False

        else:
            # Cursor-based pagination using 'after'
            after = None
            while True:
                if max_pages is not None and pages_seen >= max_pages:
                    break

                req_params = dict(params)
                if after:
                    req_params["after"] = after

                payload = self._request_json(base_url, params=req_params)
                pages_seen += 1

                data = payload.get(data_key) or []
                if not isinstance(data, list):
                    data = []

                for row in data:
                    yield row
                    rows_yielded += 1
                    if max_rows is not None and rows_yielded >= max_rows:
                        return

                paging = payload.get("paging") or {}
                cursors = paging.get("cursors") or {}
                after = cursors.get("after")
                if not after:
                    break

    def fetch_list(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        use_next_url: bool = True,
        data_key: str = "data",
        max_pages: Optional[int] = None,
        max_rows: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Convenience: return all rows as a list.
        """
        return list(
            self.iterate(
                endpoint,
                params=params,
                use_next_url=use_next_url,
                data_key=data_key,
                max_pages=max_pages,
                max_rows=max_rows,
            )
        )

    # --------------------------------------------------
    # Simple GET helper (single page)
    # --------------------------------------------------
    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Perform a single GET request to a Graph endpoint.
        """
        url = self._build_url(endpoint)
        return self._request_json(url, params=params)
