from __future__ import annotations

import pytest

from azure_cost_cli.azure.filters import build_filter, escape_odata_literal
from azure_cost_cli.errors import ValidationError
from azure_cost_cli.models import ResourceSpec


def test_escape_doubles_single_quotes():
    assert escape_odata_literal("O'Brien") == "O''Brien"


def test_escape_rejects_control_characters():
    with pytest.raises(ValidationError):
        escape_odata_literal("bad\x00value")


def test_build_filter_includes_required_clauses():
    spec = ResourceSpec(
        service_name="Virtual Machines",
        region="westeurope",
        quantity=730,
        arm_sku_name="Standard_D2s_v5",
    )
    f = build_filter(spec)
    assert "serviceName eq 'Virtual Machines'" in f
    assert "armRegionName eq 'westeurope'" in f
    assert "priceType eq 'Consumption'" in f
    assert "armSkuName eq 'Standard_D2s_v5'" in f


def test_build_filter_neutralises_injection_attempt():
    # A malicious SKU name must be escaped, not interpreted as OData syntax.
    spec = ResourceSpec(
        service_name="Virtual Machines",
        region="westeurope",
        quantity=1,
        arm_sku_name="x' or serviceName eq 'Storage",
    )
    f = build_filter(spec)
    assert "armSkuName eq 'x'' or serviceName eq ''Storage'" in f
