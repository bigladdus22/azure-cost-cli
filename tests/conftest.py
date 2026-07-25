"""Shared test fakes: an in-memory HTTP session, no network required."""

from __future__ import annotations

from typing import Any


class FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class FakeSession:
    """Records calls and replays a scripted queue of responses."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.get_calls: list[dict[str, Any]] = []
        self.post_calls: list[dict[str, Any]] = []

    def _next(self) -> FakeResponse:
        if not self._responses:
            raise AssertionError("FakeSession ran out of scripted responses")
        return self._responses.pop(0)

    def get(self, url, params=None, headers=None, timeout=None):  # noqa: ANN001
        self.get_calls.append({"url": url, "params": params, "timeout": timeout})
        return self._next()

    def post(self, url, json=None, headers=None, timeout=None):  # noqa: ANN001
        self.post_calls.append({"url": url, "json": json, "timeout": timeout})
        return self._next()
