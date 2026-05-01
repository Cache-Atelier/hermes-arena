"""arena_client — Are.na v3 API client for the hermes-arena skill.

Encapsulates the auth, User-Agent, rate-limit, and error-handling lessons
learned from real production use:

- Are.na's API sits behind Cloudflare. Default Python `urllib`/`requests`
  User-Agents return HTTP 403 with body `error code: 1010` ("Access denied
  based on browser signature"). Always send a real browser-shape UA.
- v2 endpoints are deprecated; v3 PATs return 401 against v2 paths even
  though the docs may still reference them. This client uses v3 only.
- Channel ids are integers; slugs work for GET but `channel_ids` in POST
  bodies must be ints. Helpers convert as needed.
- Rate limit is per-tier (free = 120/min). The client respects the
  `X-RateLimit-Reset` header and backs off automatically on 429.
- Block deletion is not exposed by the API. Removing a block from a channel
  is done by deleting the *connection* (DELETE /v3/connections/{id}),
  which leaves the block itself intact.

Public surface: the `ArenaClient` class plus `ArenaAPIError`.
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterable

import requests


# A real browser-shape User-Agent is required to pass Cloudflare's bot-block
# (otherwise: HTTP 403, body `error code: 1010`). The string also identifies
# the client honestly to Are.na operators via the version + project URL hint.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36 "
    "hermes-arena/0.1 (+https://github.com/cacheatelier/hermes-arena)"
)

DEFAULT_BASE_URL = "https://api.are.na/v3"
DEFAULT_THROTTLE_S = 0.6  # ≥600ms between requests; well under 120/min free-tier
DEFAULT_TIMEOUT_S = 30


class ArenaAPIError(Exception):
    """Raised for any 4xx / 5xx response from Are.na.

    Carries the parsed v3 error body where available, plus the original
    HTTP status code for callers that want to react to specific failures.
    """

    def __init__(self, status: int, message: str, details: dict | str | None = None):
        super().__init__(f"[{status}] {message}")
        self.status = status
        self.message = message
        self.details = details

    def as_dict(self) -> dict:
        return {"status": self.status, "message": self.message, "details": self.details}


class ArenaClient:
    """Thin, opinionated client for the Are.na v3 API.

    Designed for batch scripts and agent contexts:
    - Always sends a real User-Agent
    - Honors throttle and 429 backoff automatically
    - Retries 5xx with exponential backoff (max 3 attempts)
    - Raises `ArenaAPIError` on 4xx/5xx with the parsed v3 error body
    - Returns parsed JSON on success
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        throttle_s: float = DEFAULT_THROTTLE_S,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> None:
        if not api_key:
            raise ValueError(
                "ArenaClient requires an api_key. Generate a Personal Access Token at "
                "https://www.are.na/developers/personal-access-tokens (write scope), "
                "then set ARENA_API_KEY in your environment."
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.throttle_s = throttle_s
        self._last_request_at: float = 0.0
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "User-Agent": user_agent,
                "Accept": "application/json",
            }
        )

    # ----------------------------------------------------------------------
    # Low-level HTTP
    # ----------------------------------------------------------------------

    def _throttle(self) -> None:
        if self.throttle_s <= 0:
            return
        delta = time.time() - self._last_request_at
        if delta < self.throttle_s:
            time.sleep(self.throttle_s - delta)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        max_retries: int = 3,
    ) -> Any:
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        headers: dict[str, str] = {}
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        attempt = 0
        while True:
            self._throttle()
            self._last_request_at = time.time()
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    data=json.dumps(json_body) if json_body is not None else None,
                    headers=headers,
                    timeout=self.timeout_s,
                )
            except requests.RequestException as exc:
                # Network-level errors: retry once with backoff
                if attempt < max_retries - 1:
                    attempt += 1
                    time.sleep(min(2**attempt, 8))
                    continue
                raise ArenaAPIError(0, f"Network error contacting Are.na: {exc}") from exc

            # Success
            if 200 <= resp.status_code < 300:
                if resp.status_code == 204 or not resp.content:
                    return None
                try:
                    return resp.json()
                except ValueError:
                    return resp.text

            # Rate limited
            if resp.status_code == 429 and attempt < max_retries:
                reset_at = resp.headers.get("X-RateLimit-Reset")
                wait_s = self._compute_rate_wait(reset_at)
                time.sleep(wait_s)
                attempt += 1
                continue

            # 5xx → retry with backoff
            if resp.status_code >= 500 and attempt < max_retries - 1:
                attempt += 1
                time.sleep(min(2**attempt, 8))
                continue

            # 4xx (or exhausted retries on 5xx): raise with parsed error
            raise self._parse_error(resp)

    @staticmethod
    def _compute_rate_wait(reset_header: str | None) -> float:
        if not reset_header:
            return 5.0
        try:
            reset_ts = int(reset_header)
            wait = max(reset_ts - time.time(), 1.0)
            return min(wait + 0.5, 65.0)
        except ValueError:
            return 5.0

    @staticmethod
    def _parse_error(resp: requests.Response) -> ArenaAPIError:
        body = resp.text or ""
        # Cloudflare 1010 returns plain text "error code: 1010"
        if "error code: 1010" in body.lower():
            return ArenaAPIError(
                resp.status_code,
                "Cloudflare blocked the request based on User-Agent (error code: 1010). "
                "This client always sets a browser-shape UA — if you see this, something "
                "downstream stripped the User-Agent header.",
                {"raw": body[:300]},
            )

        # Try to parse as Are.na v3 error JSON
        try:
            parsed = resp.json()
            message = (
                parsed.get("error")
                or (parsed.get("details") or {}).get("message")
                or parsed.get("message")
                or "Are.na API error"
            )
            return ArenaAPIError(resp.status_code, message, parsed)
        except ValueError:
            return ArenaAPIError(resp.status_code, "Are.na API error (non-JSON body)", body[:300])

    # ----------------------------------------------------------------------
    # Doctor / auth verification
    # ----------------------------------------------------------------------

    def me(self) -> dict:
        """Get the authenticated user. Raises 401 if token is invalid."""
        return self._request("GET", "/me")

    def verify_channel_writable(self, slug_or_id: str | int) -> dict:
        """Get channel and confirm `can.add_to: true`. Returns channel object."""
        ch = self.get_channel(slug_or_id)
        can = ch.get("can") or {}
        if not can.get("add_to"):
            raise ArenaAPIError(
                403,
                f"Channel '{slug_or_id}' is not writable by this token "
                f"(can.add_to: {can.get('add_to')}). Confirm the PAT was issued by the "
                f"account that owns the channel, and has `write` scope.",
                {"channel": ch.get("slug"), "owner": (ch.get("owner") or {}).get("slug")},
            )
        return ch

    # ----------------------------------------------------------------------
    # Channels
    # ----------------------------------------------------------------------

    def get_channel(self, slug_or_id: str | int) -> dict:
        return self._request("GET", f"/channels/{slug_or_id}")

    def create_channel(
        self,
        title: str,
        visibility: str = "closed",
        description: str | None = None,
        group_id: int | None = None,
        metadata: dict | None = None,
    ) -> dict:
        body: dict[str, Any] = {"title": title, "visibility": visibility}
        if description is not None:
            body["description"] = description
        if group_id is not None:
            body["group_id"] = group_id
        if metadata is not None:
            body["metadata"] = metadata
        return self._request("POST", "/channels", json_body=body)

    def update_channel(
        self,
        slug_or_id: str | int,
        *,
        title: str | None = None,
        description: str | None = None,
        visibility: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if visibility is not None:
            body["visibility"] = visibility
        if metadata is not None:
            body["metadata"] = metadata
        if not body:
            raise ValueError("update_channel requires at least one field to update.")
        return self._request("PUT", f"/channels/{slug_or_id}", json_body=body)

    def list_channel_contents(
        self,
        slug_or_id: str | int,
        page: int = 1,
        per: int = 24,
        sort: str | None = None,
    ) -> dict:
        params: dict[str, Any] = {"page": page, "per": min(per, 100)}
        if sort is not None:
            params["sort"] = sort
        return self._request("GET", f"/channels/{slug_or_id}/contents", params=params)

    def list_channel_connections(
        self,
        slug_or_id: str | int,
        page: int = 1,
        per: int = 24,
    ) -> dict:
        params = {"page": page, "per": min(per, 100)}
        return self._request("GET", f"/channels/{slug_or_id}/connections", params=params)

    # ----------------------------------------------------------------------
    # Blocks
    # ----------------------------------------------------------------------

    def get_block(self, block_id: int) -> dict:
        return self._request("GET", f"/blocks/{block_id}")

    def create_block(
        self,
        value: str,
        channel_ids: Iterable[int],
        *,
        title: str | None = None,
        description: str | None = None,
        alt_text: str | None = None,
        original_source_url: str | None = None,
        original_source_title: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        ids = [int(cid) for cid in channel_ids]
        if not ids:
            raise ValueError("create_block requires at least one channel_id.")
        body: dict[str, Any] = {"value": value, "channel_ids": ids}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if alt_text is not None:
            body["alt_text"] = alt_text
        if original_source_url is not None:
            body["original_source_url"] = original_source_url
        if original_source_title is not None:
            body["original_source_title"] = original_source_title
        if metadata is not None:
            body["metadata"] = metadata
        return self._request("POST", "/blocks", json_body=body)

    def update_block(
        self,
        block_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
        content: str | None = None,
        alt_text: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if content is not None:
            body["content"] = content
        if alt_text is not None:
            body["alt_text"] = alt_text
        if metadata is not None:
            body["metadata"] = metadata
        if not body:
            raise ValueError("update_block requires at least one field to update.")
        return self._request("PUT", f"/blocks/{block_id}", json_body=body)

    # ----------------------------------------------------------------------
    # Connections (the correct path to "remove a block from a channel")
    # ----------------------------------------------------------------------

    def connect_block(
        self,
        block_id: int,
        channel_ids: Iterable[int],
    ) -> Any:
        """Add an existing block to one or more additional channels.

        Note: the API also accepts channels for type=Channel via the same
        endpoint; this helper is scoped to blocks for clarity.
        """
        ids = [int(cid) for cid in channel_ids]
        body = {
            "connectable_id": int(block_id),
            "connectable_type": "Block",
            "channel_ids": ids,
        }
        return self._request("POST", "/connections", json_body=body)

    def disconnect(self, connection_id: int) -> None:
        """Remove a block from a channel (the block itself persists)."""
        return self._request("DELETE", f"/connections/{connection_id}")

    # ----------------------------------------------------------------------
    # Users
    # ----------------------------------------------------------------------

    def get_user(self, slug_or_id: str | int) -> dict:
        return self._request("GET", f"/users/{slug_or_id}")

    def list_user_contents(
        self,
        slug_or_id: str | int,
        page: int = 1,
        per: int = 24,
        type_filter: str | None = None,
    ) -> dict:
        params: dict[str, Any] = {"page": page, "per": min(per, 100)}
        if type_filter is not None:
            params["type"] = type_filter
        return self._request("GET", f"/users/{slug_or_id}/contents", params=params)
