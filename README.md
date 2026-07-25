# azure-cost-cli

Estimate what an application would cost to run on **Microsoft Azure**, using an
inventory of applications catalogued in a **Supabase** database and live prices
from the **Azure Retail Prices API** (the public, no-auth programmatic equivalent
of the Azure Pricing Calculator).

> **Status: foundation / guardrails.** This is the first milestone — a validated
> core (models, pricing client, Supabase repository, estimator) with tests. It is
> not yet a polished end-to-end product.

## Two ways to use it

* **Web page (no install)** — `docs/index.html` is a self-contained calculator
  that prices resources live from the browser against the Azure Retail Prices API
  (it's public and CORS-enabled). It runs on **GitHub Pages** with no server and
  no keys. See [Hosting the web page](#hosting-the-web-page).
* **CLI** — the Python tool below, for full read **and** snapshot-write against
  Supabase.

## Hosting the web page

The page lives in `docs/` and deploys automatically via
`.github/workflows/pages.yml`. One-time setup:

1. Repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. Push to `main` (or run the *Deploy Pages* workflow). The workflow prints the
   published URL, typically `https://<owner>.github.io/azure-cost-cli/`.

You can also open `docs/index.html` straight from disk — it needs no build step.
The optional "Load inventory from Supabase" panel reads applications with the
**public anon key** (add a row-level-security `SELECT` policy first); writing
snapshots stays with the CLI because it needs the secret key.

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
