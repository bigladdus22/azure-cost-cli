# azure-cost-cli

Estimate what an application would cost to run on **Microsoft Azure**, using an
inventory of applications catalogued in a **Supabase** database and live prices
from the **Azure Retail Prices API** (the public, no-auth programmatic equivalent
of the Azure Pricing Calculator).

> **Status: foundation / guardrails.** This is the first milestone — a validated
> core (models, pricing client, Supabase repository, estimator) with tests. It is
> not yet a polished end-to-end product.

## How it works

```
Supabase (inventory)          Azure Retail Prices API
  applications          ─┐      prices.azure.com
  application_resources  │            │
        │                ▼            ▼
        └──────►  Estimator  ──►  ApplicationCost  ──►  Supabase (snapshots)
                                                          cost_snapshots
                                                          cost_snapshot_lines
```

* **Applications** and their **resources** (Azure meters: service, region, SKU,
  monthly quantity) live in Supabase — this is the source of truth for *what* to
  price.
* The **estimator** looks up each resource's unit price on the Retail Prices API
  and sums a monthly/annual total.
* The result is written back to Supabase as a **cost snapshot** for history and
  reporting.

## The guardrails (what this milestone is really about)

* **Input validation** — regions checked against an allow-list, currencies against
  Azure's supported set, quantities must be finite and non-negative, price types
  constrained. Bad input fails *before* any network call.
* **OData-injection safe** — every value going into an Azure `$filter` is escaped
  and restricted to an allow-list of fields (`src/azure_cost_cli/azure/filters.py`).
* **Bounded network behaviour** — explicit timeouts, capped exponential-backoff
  retries on 429/5xx, and a hard page cap so a loose filter can't walk the whole
  price sheet.
* **Secrets stay in the environment** — never hard-coded, never logged; `.env` is
  git-ignored.
* **Schema-level checks** — `CHECK` constraints, cascading deletes, and RLS
  enabled on every table (`supabase/migrations/0001_init.sql`).
* **Fully unit-testable offline** — the HTTP layer is injected, so tests run with
  zero network (`tests/`).

## Install

```bash
pip install -e .
```

## Configure

```bash
cp .env.example .env   # then edit; or export the vars directly
```

| Variable | Purpose | Default |
| --- | --- | --- |
| `AZURE_COST_CURRENCY` | Billing currency for prices | `EUR` |
| `AZURE_COST_REGION` | Default Azure region | `westeurope` |
| `SUPABASE_URL` | Your Supabase project URL | — |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key (read inventory, write snapshots) | — |

## Database

Apply the schema to your Supabase project:

```bash
# via the Supabase CLI, or paste supabase/migrations/0001_init.sql into the SQL editor
supabase db push
```

## Usage

```bash
azure-cost check                 # validate config and credentials
azure-cost list-apps             # list applications tracked in Supabase
azure-cost estimate web-app      # price one application
azure-cost estimate web-app --save   # …and store the snapshot
```

## Develop

```bash
pip install -r requirements.txt ruff pytest
ruff check .
pytest -q
```
