"""Turn an application's resource specs into a costed snapshot.

The estimator is the orchestration seam: it walks an application's resources,
asks the pricing client for each unit price, and assembles an
:class:`ApplicationCost`. It holds no I/O of its own, so it is trivially testable
with a fake pricer.
"""

from __future__ import annotations

from typing import Protocol

from .errors import PriceNotFoundError
from .models import Application, ApplicationCost, PricedResource, ResourceSpec


class Pricer(Protocol):
    def price_resource(self, spec: ResourceSpec) -> PricedResource: ...


class Estimator:
    """Estimate the monthly Azure cost of applications."""

    def __init__(self, pricer: Pricer, currency: str) -> None:
        self._pricer = pricer
        self._currency = currency

    def estimate(
        self, application: Application, *, skip_unpriced: bool = False
    ) -> ApplicationCost:
        """Price every resource in ``application``.

        By default a resource with no matching meter aborts the estimate (fail
        loud). Pass ``skip_unpriced=True`` to omit unmatched resources instead —
        useful for exploratory pricing where some SKUs may not be filled in yet.
        """
        cost = ApplicationCost(application=application, currency=self._currency)
        for spec in application.resources:
            try:
                cost.priced_resources.append(self._pricer.price_resource(spec))
            except PriceNotFoundError:
                if not skip_unpriced:
                    raise
        return cost
