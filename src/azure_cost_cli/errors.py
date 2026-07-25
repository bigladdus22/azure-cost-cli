"""Typed error hierarchy for azure-cost-cli.

Every failure the tool can raise is a subclass of :class:`AzureCostError`, so
callers (and the CLI) can catch one type and present a clean message instead of
leaking tracebacks. Splitting validation from configuration from remote errors
is one of the guardrails: it lets us fail fast and loudly on bad input before we
ever touch the network.
"""

from __future__ import annotations


class AzureCostError(Exception):
    """Base class for all errors raised by this package."""


class ConfigError(AzureCostError):
    """Raised when required configuration (env vars, credentials) is missing."""


class ValidationError(AzureCostError):
    """Raised when caller-supplied data fails a guardrail check."""


class PricingError(AzureCostError):
    """Raised when the Azure Retail Prices API cannot satisfy a request."""


class PriceNotFoundError(PricingError):
    """Raised when no meter matches a resource specification."""


class SupabaseError(AzureCostError):
    """Raised when a Supabase (PostgREST) call fails."""
