from __future__ import annotations

import pytest

from azure_cost_cli.azure.pricing_client import RetailPricesClient, _pick_meter
from azure_cost_cli.config import Settings
from azure_cost_cli.errors import PriceNotFoundError, PricingError
from azure_cost_cli.models import ResourceSpec
from tests.conftest import FakeResponse, FakeSession


def _settings(**kw) -> Settings:
    return Settings(currency="EUR", default_region="westeurope", **kw)


def _spec() -> ResourceSpec:
    return ResourceSpec(
        service_name="Virtual Machines",
        region="westeurope",
        quantity=730,
        arm_sku_name="Standard_D2s_v5",
    )


def test_price_resource_returns_cheapest_primary_meter():
    items = [
        {"retailPrice": 0.20, "isPrimaryMeterRegion": True, "meterId": "a",
         "productName": "P", "skuName": "S", "currencyCode": "EUR"},
        {"retailPrice": 0.10, "isPrimaryMeterRegion": True, "meterId": "b",
         "productName": "P", "skuName": "S", "currencyCode": "EUR"},
    ]
    session = FakeSession([FakeResponse(200, {"Items": items, "NextPageLink": None})])
    client = RetailPricesClient(_settings(), session=session)
    priced = client.price_resource(_spec())
    assert priced.unit_price == 0.10
    assert priced.monthly_cost == pytest.approx(73.0)


def test_currency_and_filter_passed_as_params():
    session = FakeSession([FakeResponse(200, {"Items": [
        {"retailPrice": 1.0, "isPrimaryMeterRegion": True, "meterId": "m",
         "productName": "P", "skuName": "S"}]})])
    RetailPricesClient(_settings(), session=session).price_resource(_spec())
    params = session.get_calls[0]["params"]
    assert params["currencyCode"] == "EUR"
    assert "serviceName eq 'Virtual Machines'" in params["$filter"]


def test_pagination_follows_next_page_link():
    page1 = FakeResponse(200, {"Items": [
        {"retailPrice": 5.0, "isPrimaryMeterRegion": True, "meterId": "1",
         "productName": "P", "skuName": "S"}], "NextPageLink": "https://next"})
    page2 = FakeResponse(200, {"Items": [
        {"retailPrice": 3.0, "isPrimaryMeterRegion": True, "meterId": "2",
         "productName": "P", "skuName": "S"}], "NextPageLink": None})
    session = FakeSession([page1, page2])
    priced = RetailPricesClient(_settings(), session=session).price_resource(_spec())
    assert priced.unit_price == 3.0
    assert session.get_calls[1]["url"] == "https://next"
    assert session.get_calls[1]["params"] is None  # NextPageLink carries its own query


def test_retries_on_transient_status_then_succeeds():
    sleeps: list[float] = []
    session = FakeSession([
        FakeResponse(503, {}),
        FakeResponse(200, {"Items": [
            {"retailPrice": 2.0, "isPrimaryMeterRegion": True, "meterId": "m",
             "productName": "P", "skuName": "S"}]}),
    ])
    client = RetailPricesClient(_settings(), session=session, sleep=sleeps.append)
    priced = client.price_resource(_spec())
    assert priced.unit_price == 2.0
    assert sleeps == [1.0]  # one backoff of 2**0


def test_gives_up_after_max_retries():
    session = FakeSession([FakeResponse(500, {}) for _ in range(10)])
    client = RetailPricesClient(_settings(), session=session, sleep=lambda _: None, max_retries=2)
    with pytest.raises(PricingError):
        client.price_resource(_spec())


def test_no_match_raises_price_not_found():
    session = FakeSession([FakeResponse(200, {"Items": []})])
    with pytest.raises(PriceNotFoundError):
        RetailPricesClient(_settings(), session=session).price_resource(_spec())


def test_page_cap_enforced():
    # Every page points to a next page → cap trips.
    responses = [
        FakeResponse(200, {"Items": [], "NextPageLink": "https://n"}) for _ in range(5)
    ]
    session = FakeSession(responses)
    client = RetailPricesClient(_settings(max_pages=3), session=session)
    with pytest.raises(PricingError):
        client.iter_items("serviceName eq 'X'")


def test_pick_meter_falls_back_when_no_primary_flag():
    items = [{"retailPrice": 0.5}, {"retailPrice": 0.3}]
    assert _pick_meter(items)["retailPrice"] == 0.3
