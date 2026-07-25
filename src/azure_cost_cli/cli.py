"""Command-line entry point.

Deliberately thin: it wires configuration to the estimator/repository and prints
results. All the guardrails live in the library, so the CLI's only job is to
turn argv into calls and turn errors into tidy messages (exit code 2) instead of
tracebacks.

Commands
--------
* ``check``    – validate the environment/config and exit.
* ``list-apps``– list applications catalogued in Supabase.
* ``estimate`` – price one application (optionally saving a snapshot).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .config import Settings
from .errors import AzureCostError
from .estimator import Estimator
from .models import ApplicationCost


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="azure-cost",
        description="Estimate the Azure cost of applications catalogued in Supabase.",
    )
    parser.add_argument("--version", action="version", version=f"azure-cost {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="validate configuration and exit")
    sub.add_parser("list-apps", help="list applications tracked in Supabase")

    est = sub.add_parser("estimate", help="estimate the cost of one application")
    est.add_argument("app", help="application name (as stored in Supabase)")
    est.add_argument(
        "--save", action="store_true", help="write the result back as a snapshot"
    )
    est.add_argument(
        "--skip-unpriced",
        action="store_true",
        help="omit resources with no matching meter instead of failing",
    )
    return parser


def _print_cost(cost: ApplicationCost) -> None:
    print(f"\n{cost.application.name}  [{cost.application.environment}]  ({cost.currency})")
    print("-" * 60)
    for pr in cost.priced_resources:
        print(
            f"  {pr.spec.display_name:<28} "
            f"{pr.spec.quantity:>10.2f} x {pr.unit_price:>10.4f} "
            f"= {pr.monthly_cost:>12.2f}"
        )
    print("-" * 60)
    print(f"  Monthly total: {cost.monthly_total:>12.2f} {cost.currency}")
    print(f"  Annual total : {cost.annual_total:>12.2f} {cost.currency}\n")


def _cmd_estimate(args: argparse.Namespace, settings: Settings) -> int:
    # Imported here so `check` works without `requests` installed.
    from .azure.pricing_client import RetailPricesClient
    from .supabasedb.repository import SupabaseRepository

    repo = SupabaseRepository(settings)
    application = repo.get_application(args.app)
    estimator = Estimator(RetailPricesClient(settings), currency=settings.currency)
    cost = estimator.estimate(application, skip_unpriced=args.skip_unpriced)
    _print_cost(cost)
    if args.save:
        snapshot_id = repo.save_snapshot(cost)
        print(f"Saved snapshot {snapshot_id}")
    return 0


def _cmd_list_apps(settings: Settings) -> int:
    from .supabasedb.repository import SupabaseRepository

    for app in SupabaseRepository(settings).list_applications():
        print(f"{app.name:<30} {app.environment:<8} {len(app.resources)} resources")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        if args.command == "check":
            settings.require_supabase()
            print("Configuration OK: currency, region, endpoint and Supabase creds valid.")
            return 0
        if args.command == "list-apps":
            return _cmd_list_apps(settings)
        if args.command == "estimate":
            return _cmd_estimate(args, settings)
    except AzureCostError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
