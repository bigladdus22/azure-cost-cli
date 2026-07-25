from __future__ import annotations

import pytest

from azure_cost_cli.errors import PriceNotFoundError
from azure_cost_cli.estimator import Estimator
from azure_cost_cli.models import Application, PricedResource, ResourceSpec


class FakePricer:
    """Prices by SKU from a lookup; raises for anything unknown."""

    def __init__(self, prices: dict[str, float]) -> None:
        self._prices = prices

    def price_resource(self, spec: ResourceSpec) -> PricedResource:
        key = spec.arm_sku_name or spec.service_name
        if key not in self._prices:
            raise PriceNotFoundError(key)
        return PricedResource(
            spec=spec,
            unit_price=self._prices[key],
            currency="EUR",
            meter_id="m",
            matched_product="P",
            matched_sku="S",
        )


def _app() -> Application:
    return Application(
        name="web-app",
        resources=(
            ResourceSpec("Virtual Machines", "westeurope", 730, arm_sku_name="Standard_D2s_v5"),
            ResourceSpec("Storage", "westeurope", 100, arm_sku_name="std-lrs"),
        ),
    )


def test_estimate_totals_are_summed():
    pricer = FakePricer({"Standard_D2s_v5": 0.10, "std-lrs": 0.02})
    cost = Estimator(pricer, "EUR").estimate(_app())
    assert cost.monthly_total == pytest.approx(73.0 + 2.0)
    assert cost.annual_total == pytest.approx((73.0 + 2.0) * 12)


def test_unpriced_resource_fails_loud_by_default():
    pricer = FakePricer({"Standard_D2s_v5": 0.10})  # missing std-lrs
    with pytest.raises(PriceNotFoundError):
        Estimator(pricer, "EUR").estimate(_app())


def test_skip_unpriced_omits_missing_resources():
    pricer = FakePricer({"Standard_D2s_v5": 0.10})
    cost = Estimator(pricer, "EUR").estimate(_app(), skip_unpriced=True)
    assert len(cost.priced_resources) == 1
    assert cost.monthly_total == pytest.approx(73.0)
