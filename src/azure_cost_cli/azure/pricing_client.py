"""A thin, defensive client for the Azure Retail Prices API.

The Retail Prices API (https://prices.azure.com/api/retail/prices) is the public,
unauthenticated, programmatic equivalent of the Azure Pricing Calculator. This
client wraps it with the guardrails a batch pricing job needs:

* every request has an explicit timeout (never hang the run),
* transient failures (429, 5xx) are retried with bounded exponential backoff,
* pagination is followed but capped at ``max_pages`` so a bad filter can't walk
  the entire price sheet,
* the HTTP layer is injected, so the whole thing is unit-testable offline.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from ..config import Settings
from ..errors import PriceNotFoundError, PricingError, ValidationError
from ..models import PricedResource, ResourceSpec
from .filters import build_filter

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class HttpResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


class HttpSession(Protocol):
    """Minimal surface we need from an HTTP client (``requests.Session`` fits)."""

    def get(
        self, url: str, params: dict[str, str] | None = None, timeout: float = ...
    ) -> HttpResponse: ...


def _default_session() -> HttpSession:
    # Imported lazily so importing the package never requires `requests` to be
    # installed (tests inject a fake session instead).
    import requests

    return requests.Session()


class RetailPricesClient:
    """Query the Azure Retail Prices API for unit prices."""

    def __init__(
        self,
        settings: Settings,
        session: HttpSession | None = None,
        sleep: Callable[[float], None] | None = None,
        max_retries: int = 4,
    ) -> None:
        self._settings = settings
        self._session = session or _default_session()
        self._sleep = sleep or _real_sleep
        self._max_retries = max_retries

    def _get(self, url: str, params: dict[str, str] | None) -> dict[str, Any]:
        """GET with bounded exponential backoff on transient failures."""
        last_status: int | None = None
        for attempt in range(self._max_retries + 1):
            resp = self._session.get(
                url, params=params, timeout=self._settings.http_timeout
            )
            if resp.status_code == 200:
                return resp.json()
            last_status = resp.status_code
            if resp.status_code not in _RETRYABLE_STATUS or attempt == self._max_retries:
                break
            self._sleep(2.0**attempt)
        raise PricingError(
            f"Retail Prices API request failed with status {last_status}"
        )

    def iter_items(self, odata_filter: str) -> list[dict[str, Any]]:
        """Return all price items matching an OData filter (paged, capped)."""
        if not odata_filter:
            raise ValidationError("odata_filter must not be empty")
        params: dict[str, str] | None = {
            "$filter": odata_filter,
            "currencyCode": self._settings.currency,
            "api-version": self._settings.api_version,
        }
        url = self._settings.prices_endpoint
        items: list[dict[str, Any]] = []
        for _ in range(self._settings.max_pages):
            payload = self._get(url, params)
            items.extend(payload.get("Items", []))
            next_link = payload.get("NextPageLink")
            if not next_link:
                return items
            # NextPageLink is a fully-formed URL that already carries the query.
            url, params = next_link, None
        raise PricingError(
            f"filter matched more than {self._settings.max_pages} pages; "
            "narrow the resource spec (add armSkuName/meterName)"
        )

    def price_resource(self, spec: ResourceSpec) -> PricedResource:
        """Resolve the cheapest primary-region unit price for a resource spec."""
        items = self.iter_items(build_filter(spec))
        if not items:
            raise PriceNotFoundError(
                f"no Azure meter matched {spec.display_name!r} "
                f"(service={spec.service_name!r}, region={spec.region!r})"
            )
        chosen = _pick_meter(items)
        return PricedResource(
            spec=spec,
            unit_price=float(chosen["retailPrice"]),
            currency=str(chosen.get("currencyCode", self._settings.currency)),
            meter_id=str(chosen.get("meterId", "")),
            matched_product=str(chosen.get("productName", "")),
            matched_sku=str(chosen.get("skuName", "")),
        )


def _pick_meter(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministically choose one meter from a set of matches.

    Prefer the primary meter region (so cross-region duplicates don't sway the
    result), then the lowest non-zero retail price. Falling back to price keeps
    the choice stable when ``isPrimaryMeterRegion`` is absent.
    """
    primary = [i for i in items if i.get("isPrimaryMeterRegion")] or items
    priced = [i for i in primary if float(i.get("retailPrice", 0)) > 0] or primary
    return min(priced, key=lambda i: float(i.get("retailPrice", 0)))


def _real_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
