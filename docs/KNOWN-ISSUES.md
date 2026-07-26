# Known issues

## The web page cannot connect to Azure pricing (browser CORS)

**Status:** fixed by the price-cache architecture (see below). Tracked in
[#5](https://github.com/bigladdus22/azure-cost-cli/issues/5).

**Symptom.** The old `docs/index.html` called `https://prices.azure.com/api/retail/prices`
directly from the browser; clicking *Estimate* failed with `Load failed` and
€0.00 totals.

**Cause.** That API does not return an `Access-Control-Allow-Origin` header, so
the browser blocks the cross-origin response. It's an API limitation, not a bug
in the page — the same request works server-side (the Python CLI is unaffected).

**Fix (shipped).** The browser no longer calls Microsoft. Instead:

1. A **Supabase Edge Function** (`supabase/functions/refresh-azure-prices`)
   fetches the Retail Prices API server-side — with pagination and `429`
   handling — and upserts a filtered subset into `public.azure_prices`
   (`supabase/migrations/0002_azure_prices_cache.sql`).
2. **pg_cron** refreshes it on a schedule (`supabase/schedule/azure_prices_refresh.sql`);
   retail prices move rarely, so weekly is plenty.
3. The page reads `azure_prices` via the **anon key under RLS** — no cross-origin
   call to Microsoft, no pagination or throttling in the browser.

**Setup.** See `supabase/functions/refresh-azure-prices/README.md`.

**Still works server-side.** The Python CLI (`azure-cost estimate`) talks to the
API directly and doesn't need the cache.
