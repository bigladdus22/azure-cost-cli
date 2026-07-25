"""Build OData `$filter` expressions for the Azure Retail Prices API — safely.

The Retail Prices API takes an OData filter string. Interpolating user/database
values straight into that string is an injection risk (a stray single quote or a
crafted ``or 1 eq 1`` could broaden or break the query). This module is the
guardrail: every value is validated and its single quotes are OData-escaped
(doubled) before it goes anywhere near a request.
"""

from __future__ import annotations

from ..errors import ValidationError
from ..models import ResourceSpec

# Fields we allow callers to filter on. Restricting the set means a caller can
# never smuggle an arbitrary field name into the query.
_ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "serviceName", "armRegionName", "armSkuName", "meterName",
        "productName", "priceType",
    }
)


def escape_odata_literal(value: str) -> str:
    """Escape a string for use inside a single-quoted OData literal.

    OData escapes a single quote by doubling it. We also reject control
    characters outright — they have no place in a SKU or region name and are a
    common smuggling vector.
    """
    if any(ord(ch) < 0x20 for ch in value):
        raise ValidationError("filter value contains control characters")
    return value.replace("'", "''")


def _eq(field: str, value: str) -> str:
    if field not in _ALLOWED_FIELDS:
        raise ValidationError(f"field {field!r} is not filterable")
    return f"{field} eq '{escape_odata_literal(value)}'"


def build_filter(spec: ResourceSpec) -> str:
    """Compose the `$filter` for a single resource spec.

    Only the fields present on the spec are included, ANDed together. Region and
    service name are always present (they are required on the model), so the
    filter is never empty.
    """
    clauses = [
        _eq("serviceName", spec.service_name),
        _eq("armRegionName", spec.region),
        _eq("priceType", spec.price_type),
    ]
    if spec.arm_sku_name:
        clauses.append(_eq("armSkuName", spec.arm_sku_name))
    if spec.meter_name:
        clauses.append(_eq("meterName", spec.meter_name))
    if spec.product_name:
        clauses.append(_eq("productName", spec.product_name))
    return " and ".join(clauses)
