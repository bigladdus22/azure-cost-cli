"""Runtime configuration and its guardrails.

Configuration is read from the environment (never hard-coded) and validated up
front so a misconfigured run fails immediately with a clear message rather than
midway through a pricing job. Secrets (the Supabase key) are read from env and
never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .errors import ConfigError, ValidationError
from .models import SUPPORTED_CURRENCIES

# A conservative allow-list of common Azure regions. It is not exhaustive; the
# point is to catch typos ("westeu") before they turn into an empty price
# result. Extend via AZURE_COST_EXTRA_REGIONS (comma-separated).
DEFAULT_REGIONS: frozenset[str] = frozenset(
    {
        "westeurope", "northeurope", "uksouth", "ukwest", "eastus", "eastus2",
        "westus", "westus2", "westus3", "centralus", "southcentralus",
        "francecentral", "germanywestcentral", "swedencentral", "norwayeast",
        "switzerlandnorth", "eastasia", "southeastasia", "australiaeast",
        "japaneast", "canadacentral", "brazilsouth",
    }
)

DEFAULT_PRICES_ENDPOINT = "https://prices.azure.com/api/retail/prices"
DEFAULT_API_VERSION = "2023-01-01-preview"


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated settings for a run. Build via :meth:`from_env`."""

    currency: str = "EUR"
    default_region: str = "westeurope"
    prices_endpoint: str = DEFAULT_PRICES_ENDPOINT
    api_version: str = DEFAULT_API_VERSION
    http_timeout: float = 30.0
    max_pages: int = 20
    supabase_url: str | None = None
    supabase_key: str | None = None
    allowed_regions: frozenset[str] = DEFAULT_REGIONS

    def __post_init__(self) -> None:
        if self.currency not in SUPPORTED_CURRENCIES:
            raise ValidationError(
                f"currency {self.currency!r} not in {sorted(SUPPORTED_CURRENCIES)}"
            )
        if self.default_region not in self.allowed_regions:
            raise ValidationError(
                f"default_region {self.default_region!r} is not in the allowed set"
            )
        if not self.prices_endpoint.startswith("https://"):
            raise ValidationError("prices_endpoint must be an https:// URL")
        if self.http_timeout <= 0:
            raise ValidationError("http_timeout must be positive")
        if self.max_pages < 1:
            raise ValidationError("max_pages must be >= 1")
        if self.supabase_url is not None and not self.supabase_url.startswith("https://"):
            raise ValidationError("supabase_url must be an https:// URL")

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        extra = env.get("AZURE_COST_EXTRA_REGIONS", "")
        regions = set(DEFAULT_REGIONS)
        regions.update(r.strip().lower() for r in extra.split(",") if r.strip())
        return cls(
            currency=env.get("AZURE_COST_CURRENCY", "EUR").upper(),
            default_region=env.get("AZURE_COST_REGION", "westeurope").lower(),
            prices_endpoint=env.get("AZURE_COST_PRICES_ENDPOINT", DEFAULT_PRICES_ENDPOINT),
            api_version=env.get("AZURE_COST_API_VERSION", DEFAULT_API_VERSION),
            http_timeout=float(env.get("AZURE_COST_HTTP_TIMEOUT", "30")),
            max_pages=int(env.get("AZURE_COST_MAX_PAGES", "20")),
            supabase_url=env.get("SUPABASE_URL") or None,
            supabase_key=(
                env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_KEY") or None
            ),
            allowed_regions=frozenset(regions),
        )

    def require_supabase(self) -> tuple[str, str]:
        """Return (url, key) or raise a clear :class:`ConfigError`."""
        if not self.supabase_url or not self.supabase_key:
            raise ConfigError(
                "Supabase access requires SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY) in the environment"
            )
        return self.supabase_url, self.supabase_key
