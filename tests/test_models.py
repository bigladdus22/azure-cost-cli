from __future__ import annotations

import math

import pytest

from azure_cost_cli.errors import ValidationError
from azure_cost_cli.models import Application, ResourceSpec


def test_resource_spec_normalises_region_and_service():
    spec = ResourceSpec(service_name="  Virtual Machines ", region="WestEurope", quantity=730)
    assert spec.service_name == "Virtual Machines"
    assert spec.region == "westeurope"


@pytest.mark.parametrize("bad", [-1, math.inf, math.nan])
def test_resource_spec_rejects_bad_quantity(bad):
    with pytest.raises(ValidationError):
        ResourceSpec(service_name="Storage", region="westeurope", quantity=bad)


def test_resource_spec_rejects_bool_quantity():
    with pytest.raises(ValidationError):
        ResourceSpec(service_name="Storage", region="westeurope", quantity=True)


def test_resource_spec_rejects_unknown_price_type():
    with pytest.raises(ValidationError):
        ResourceSpec(
            service_name="Storage", region="westeurope", quantity=1, price_type="Spot"
        )


def test_application_requires_resources():
    with pytest.raises(ValidationError):
        Application(name="empty", resources=())


def test_display_name_prefers_label():
    spec = ResourceSpec(
        service_name="Virtual Machines",
        region="westeurope",
        quantity=730,
        arm_sku_name="Standard_D2s_v5",
        label="web-tier",
    )
    assert spec.display_name == "web-tier"
