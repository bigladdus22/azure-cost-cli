from __future__ import annotations

from datetime import UTC, datetime

import pytest

from azure_cost_cli.config import Settings
from azure_cost_cli.errors import ConfigError, SupabaseError, ValidationError
from azure_cost_cli.models import Application, ApplicationCost, PricedResource, ResourceSpec
from azure_cost_cli.supabasedb.repository import SupabaseRepository
from tests.conftest import FakeResponse, FakeSession


def test_settings_reject_unknown_currency():
    with pytest.raises(ValidationError):
        Settings(currency="XYZ")


def test_settings_reject_unknown_region():
    with pytest.raises(ValidationError):
        Settings(default_region="atlantis")


def test_from_env_reads_extra_regions_and_creds():
    settings = Settings.from_env({
        "AZURE_COST_CURRENCY": "gbp",
        "AZURE_COST_REGION": "uksouth",
        "AZURE_COST_EXTRA_REGIONS": "atlantis, westeurope",
        "SUPABASE_URL": "https://ref.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "secret",
    })
    assert settings.currency == "GBP"
    assert "atlantis" in settings.allowed_regions
    assert settings.require_supabase() == ("https://ref.supabase.co", "secret")


def test_require_supabase_without_creds_raises():
    with pytest.raises(ConfigError):
        Settings().require_supabase()


def _repo(session: FakeSession) -> SupabaseRepository:
    settings = Settings(supabase_url="https://ref.supabase.co", supabase_key="k")
    return SupabaseRepository(settings, session=session)


def test_get_application_maps_nested_resources():
    row = {
        "id": "app-1",
        "name": "web-app",
        "environment": "prod",
        "application_resources": [
            {"service_name": "Virtual Machines", "region": "westeurope",
             "quantity": 730, "arm_sku_name": "Standard_D2s_v5"},
        ],
    }
    session = FakeSession([FakeResponse(200, [row])])
    app = _repo(session).get_application("web-app")
    assert app.id == "app-1"
    assert app.resources[0].arm_sku_name == "Standard_D2s_v5"


def test_get_application_missing_raises():
    session = FakeSession([FakeResponse(200, [])])
    with pytest.raises(SupabaseError):
        _repo(session).get_application("nope")


def test_non_2xx_status_raises():
    session = FakeSession([FakeResponse(401, {"message": "denied"})])
    with pytest.raises(SupabaseError):
        _repo(session).list_applications()


def test_save_snapshot_posts_header_and_lines():
    app = Application(
        name="web-app",
        id="app-1",
        resources=(ResourceSpec("Virtual Machines", "westeurope", 730,
                                 arm_sku_name="Standard_D2s_v5"),),
    )
    cost = ApplicationCost(
        application=app,
        currency="EUR",
        generated_at=datetime(2026, 7, 25, tzinfo=UTC),
        priced_resources=[PricedResource(
            spec=app.resources[0], unit_price=0.10, currency="EUR",
            meter_id="m", matched_product="P", matched_sku="S",
        )],
    )
    session = FakeSession([
        FakeResponse(201, [{"id": "snap-1"}]),   # snapshot header insert
        FakeResponse(201, [{"id": "line-1"}]),   # lines insert
    ])
    snapshot_id = _repo(session).save_snapshot(cost)
    assert snapshot_id == "snap-1"
    header = session.post_calls[0]["json"]
    assert header["monthly_total"] == pytest.approx(73.0)
    lines = session.post_calls[1]["json"]
    assert lines[0]["snapshot_id"] == "snap-1"
    assert lines[0]["unit_price"] == 0.10
