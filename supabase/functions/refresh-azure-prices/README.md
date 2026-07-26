# refresh-azure-prices

Server-side refresher for the Azure price cache. Fetches `prices.azure.com`
(paginated, with 429 handling) and upserts a filtered subset into
`public.azure_prices`. The GitHub Pages frontend reads that table via the anon
key and never calls Microsoft directly.

## One-time setup

1. **Apply the schema** (creates `azure_prices` + RLS read policy):
   ```bash
   supabase db push          # or paste supabase/migrations/0002_azure_prices_cache.sql into the SQL editor
   ```

2. **Deploy the function** (public entry point; it gates itself with a secret,
   so JWT verification is disabled):
   ```bash
   supabase functions deploy refresh-azure-prices --no-verify-jwt
   ```

3. **Set secrets.** `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are injected
   automatically; you provide the rest:
   ```bash
   supabase secrets set \
     REFRESH_SECRET="$(openssl rand -hex 24)" \
     AZURE_PRICE_CURRENCY=EUR \
     AZURE_PRICE_FILTER="serviceName eq 'Virtual Machines' and armRegionName eq 'westeurope' and priceType eq 'Consumption'"
   ```
   Widen `AZURE_PRICE_FILTER` to cache more (e.g. add `or serviceName eq 'Storage'`,
   more regions, or filter by `serviceFamily eq 'Compute'`). Keep it targeted —
   the whole price sheet is millions of rows.

4. **Populate + schedule.** Edit `supabase/schedule/azure_prices_refresh.sql`
   (replace `<PROJECT_REF>` / `<REFRESH_SECRET>`), run it in the SQL editor, then
   run the one-off `net.http_post` at the bottom to fill the cache immediately.

## Verify

```bash
curl -X POST "https://<PROJECT_REF>.functions.supabase.co/refresh-azure-prices" \
  -H "x-refresh-secret: <REFRESH_SECRET>"
# -> {"ok":true,"pages":N,"fetched":X,"upserted":X,...}
```

Then point the web calculator at your Supabase URL + anon key and estimate.

## Overrides

`currency`, `filter`, and `secret` may be passed as query params for an ad-hoc
run, e.g. `?currency=USD&filter=serviceName eq 'Storage' and armRegionName eq 'eastus'`.
