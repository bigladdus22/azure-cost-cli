"""Read the application inventory from Supabase and write cost snapshots back.

This talks to Supabase's auto-generated PostgREST API rather than a raw Postgres
connection, so the only dependency is HTTP. As with the pricing client the HTTP
layer is injected, so the repository is unit-testable offline.

Guardrails here: the base URL must be https, credentials are required (via
:meth:`Settings.require_supabase`) and never logged, and every response status is
checked so a silent 4xx can't be mistaken for an empty inventory.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..config import Settings
from ..errors import SupabaseError
from ..models import Application, ApplicationCost, ResourceSpec


class HttpResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


class HttpSession(Protocol):
    def get(
        self, url: str, params: dict[str, str] | None = ..., headers: dict[str, str] = ...,
        timeout: float = ...,
    ) -> HttpResponse: ...

    def post(
        self, url: str, json: Any = ..., headers: dict[str, str] = ..., timeout: float = ...
    ) -> HttpResponse: ...


def _default_session() -> HttpSession:
    import requests

    return requests.Session()


class SupabaseRepository:
    """Data access for applications, their resources, and cost snapshots."""

    def __init__(self, settings: Settings, session: HttpSession | None = None) -> None:
        url, key = settings.require_supabase()
        self._settings = settings
        self._rest = url.rstrip("/") + "/rest/v1"
        self._key = key
        self._session = session or _default_session()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _check(self, resp: HttpResponse, action: str) -> Any:
        if resp.status_code not in (200, 201):
            raise SupabaseError(f"{action} failed with status {resp.status_code}")
        return resp.json()

    def list_applications(self) -> list[Application]:
        """Load every application together with its resource line items."""
        resp = self._session.get(
            f"{self._rest}/applications",
            params={"select": "id,name,environment,application_resources(*)"},
            headers=self._headers,
            timeout=self._settings.http_timeout,
        )
        rows = self._check(resp, "list_applications")
        return [_row_to_application(row) for row in rows]

    def get_application(self, name: str) -> Application:
        resp = self._session.get(
            f"{self._rest}/applications",
            params={
                "select": "id,name,environment,application_resources(*)",
                "name": f"eq.{name}",
                "limit": "1",
            },
            headers=self._headers,
            timeout=self._settings.http_timeout,
        )
        rows = self._check(resp, "get_application")
        if not rows:
            raise SupabaseError(f"no application named {name!r}")
        return _row_to_application(rows[0])

    def save_snapshot(self, cost: ApplicationCost) -> str:
        """Persist a costed snapshot and its line items; return the snapshot id."""
        snap_resp = self._session.post(
            f"{self._rest}/cost_snapshots",
            json={
                "application_id": cost.application.id,
                "application_name": cost.application.name,
                "currency": cost.currency,
                "monthly_total": cost.monthly_total,
                "annual_total": cost.annual_total,
                "generated_at": cost.generated_at.isoformat(),
            },
            headers=self._headers,
            timeout=self._settings.http_timeout,
        )
        snap_rows = self._check(snap_resp, "save_snapshot")
        snapshot_id = str(snap_rows[0]["id"])

        lines = [
            {
                "snapshot_id": snapshot_id,
                "resource_label": pr.spec.display_name,
                "service_name": pr.spec.service_name,
                "region": pr.spec.region,
                "arm_sku_name": pr.spec.arm_sku_name,
                "quantity": pr.spec.quantity,
                "unit_price": pr.unit_price,
                "monthly_cost": pr.monthly_cost,
                "meter_id": pr.meter_id,
            }
            for pr in cost.priced_resources
        ]
        if lines:
            line_resp = self._session.post(
                f"{self._rest}/cost_snapshot_lines",
                json=lines,
                headers=self._headers,
                timeout=self._settings.http_timeout,
            )
            self._check(line_resp, "save_snapshot_lines")
        return snapshot_id


def _row_to_application(row: dict[str, Any]) -> Application:
    specs = tuple(_row_to_spec(r) for r in row.get("application_resources", []))
    return Application(
        id=str(row["id"]) if row.get("id") is not None else None,
        name=row["name"],
        environment=row.get("environment", "prod"),
        resources=specs,
    )


def _row_to_spec(row: dict[str, Any]) -> ResourceSpec:
    return ResourceSpec(
        service_name=row["service_name"],
        region=row["region"],
        quantity=float(row.get("quantity", 0)),
        arm_sku_name=row.get("arm_sku_name"),
        meter_name=row.get("meter_name"),
        product_name=row.get("product_name"),
        price_type=row.get("price_type", "Consumption"),
        unit=row.get("unit", "1 Hour"),
        label=row.get("label"),
    )
