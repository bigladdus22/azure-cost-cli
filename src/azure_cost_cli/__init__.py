"""azure-cost-cli: price a Supabase-catalogued application on Azure.

Public API surface kept intentionally small; import the pieces you need.
"""

from __future__ import annotations

from .config import Settings
from .estimator import Estimator
from .models import Application, ApplicationCost, PricedResource, ResourceSpec

__version__ = "0.1.0"

__all__ = [
    "Settings",
    "Estimator",
    "Application",
    "ApplicationCost",
    "PricedResource",
    "ResourceSpec",
    "__version__",
]
