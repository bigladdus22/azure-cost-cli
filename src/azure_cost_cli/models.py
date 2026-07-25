"""Domain model for pricing an application's Azure footprint.

The model is deliberately small and pure (no I/O). An :class:`Application` is a
product tracked in Supabase; it owns a list of :class:`ResourceSpec` line items
describing the Azure meters it consumes. The estimator turns those into
:class:`PricedResource` rows and an :class:`ApplicationCost` total, which is what
we persist back to Supabase as a snapshot.

All construction runs through ``validate``/``__post_init__`` guardrails so an
invalid object can never reach the network or the database.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .errors import ValidationError

# Azure billing currencies accepted by the Retail Prices API `currencyCode`
# parameter. Anything outside this set is rejected before a request is built.
SUPPORTED_CURRENCIES: frozenset[str] = frozenset(
    {
        "USD", "AUD", "BRL", "CAD", "CHF", "CNY", "DKK", "EUR", "GBP", "INR",
        "JPY", "KRW", "NOK", "NZD", "RUB", "SEK", "TWD",
    }
)

# Azure Retail Prices `type` / `priceType` values.
SUPPORTED_PRICE_TYPES: frozenset[str] = frozenset(
    {"Consumption", "Reservation", "DevTestConsumption"}
)


def _clean(value: str, field_name: str) -> str:
    """Guardrail: reject empty / whitespace-only identifiers."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    """One priceable Azure line item belonging to an application.

    ``quantity`` is the number of billed units per month for this meter (e.g.
    730 hours for an always-on VM, or GB-months of storage). The remaining
    fields narrow the Retail Prices lookup; the more you set, the more precise
    the matched meter.
    """

    service_name: str
    region: str
    quantity: float
    arm_sku_name: str | None = None
    meter_name: str | None = None
    product_name: str | None = None
    price_type: str = "Consumption"
    unit: str = "1 Hour"
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "service_name", _clean(self.service_name, "service_name"))
        object.__setattr__(self, "region", _clean(self.region, "region").lower())
        if self.price_type not in SUPPORTED_PRICE_TYPES:
            raise ValidationError(
                f"price_type {self.price_type!r} not in {sorted(SUPPORTED_PRICE_TYPES)}"
            )
        if not isinstance(self.quantity, (int, float)) or isinstance(self.quantity, bool):
            raise ValidationError("quantity must be a number")
        if not math.isfinite(self.quantity) or self.quantity < 0:
            raise ValidationError("quantity must be a finite, non-negative number")

    @property
    def display_name(self) -> str:
        return self.label or self.arm_sku_name or self.meter_name or self.service_name


@dataclass(frozen=True, slots=True)
class Application:
    """A product/application whose Azure cost we want to estimate."""

    name: str
    resources: tuple[ResourceSpec, ...]
    environment: str = "prod"
    id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _clean(self.name, "name"))
        object.__setattr__(self, "environment", _clean(self.environment, "environment"))
        if not self.resources:
            raise ValidationError(f"application {self.name!r} has no resources to price")


@dataclass(frozen=True, slots=True)
class PricedResource:
    """A :class:`ResourceSpec` matched to a meter, with a monthly cost."""

    spec: ResourceSpec
    unit_price: float
    currency: str
    meter_id: str
    matched_product: str
    matched_sku: str

    @property
    def monthly_cost(self) -> float:
        return round(self.unit_price * self.spec.quantity, 4)


@dataclass(slots=True)
class ApplicationCost:
    """The priced result for one application; persisted as a snapshot."""

    application: Application
    currency: str
    priced_resources: list[PricedResource] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def monthly_total(self) -> float:
        return round(sum(r.monthly_cost for r in self.priced_resources), 4)

    @property
    def annual_total(self) -> float:
        return round(self.monthly_total * 12, 4)
