// refresh-azure-prices
//
// Fetches Azure retail prices from prices.azure.com server-side — with
// pagination and 429 handling — and upserts a filtered subset into
// public.azure_prices. The GitHub Pages frontend reads that table via the anon
// key and never calls Microsoft directly (no CORS, no throttling in the browser).
//
// Deploy:
//   supabase functions deploy refresh-azure-prices --no-verify-jwt
// Configure (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are injected automatically):
//   supabase secrets set REFRESH_SECRET=<random> AZURE_PRICE_CURRENCY=EUR \
//     AZURE_PRICE_FILTER="serviceName eq 'Virtual Machines' and armRegionName eq 'westeurope' and priceType eq 'Consumption'"
// Invoke (also what pg_cron calls):
//   curl -X POST "https://<ref>.functions.supabase.co/refresh-azure-prices" -H "x-refresh-secret: <random>"

import { createClient } from "jsr:@supabase/supabase-js@2";

const PRICES_ENDPOINT = "https://prices.azure.com/api/retail/prices";
const API_VERSION = "2023-01-01-preview";
const PAGE_CAP = 200; // 200 pages * 1000 rows = hard ceiling against a runaway filter
const MAX_RETRIES = 5;
const UPSERT_BATCH = 500;
const ON_CONFLICT = "meter_id,currency_code,price_type,tier_minimum_units,arm_region_name";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// deno-lint-ignore no-explicit-any
async function fetchPage(url: string): Promise<any> {
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const resp = await fetch(url, { headers: { Accept: "application/json" } });
    if (resp.status === 200) return await resp.json();

    // Documented throttling: retry after the interval the API asks for.
    if (resp.status === 429) {
      const retryAfter =
        Number(resp.headers.get("x-ms-ratelimit-microsoft.consumption-retry-after")) ||
        Number(resp.headers.get("Retry-After")) ||
        2 ** attempt;
      await sleep(Math.min(retryAfter, 60) * 1000);
      continue;
    }
    if (resp.status >= 500 && attempt < MAX_RETRIES) {
      await sleep(2 ** attempt * 1000);
      continue;
    }
    throw new Error(`Retail Prices API returned ${resp.status}`);
  }
  throw new Error("exceeded retry budget contacting the Retail Prices API");
}

// deno-lint-ignore no-explicit-any
function mapRow(i: any) {
  return {
    meter_id: i.meterId,
    arm_sku_name: i.armSkuName ?? null,
    arm_region_name: i.armRegionName,
    service_name: i.serviceName,
    service_family: i.serviceFamily ?? null,
    meter_name: i.meterName ?? null,
    product_name: i.productName ?? null,
    sku_name: i.skuName ?? null,
    retail_price: i.retailPrice,
    unit_price: i.unitPrice ?? i.retailPrice,
    currency_code: i.currencyCode,
    unit_of_measure: i.unitOfMeasure ?? null,
    price_type: i.type,
    tier_minimum_units: i.tierMinimumUnits ?? 0,
    is_primary_meter_region: !!i.isPrimaryMeterRegion,
    effective_start_date: i.effectiveStartDate ?? null,
  };
}

Deno.serve(async (req) => {
  // Gate the refresh behind a shared secret (verify_jwt is off for cron).
  const secret = Deno.env.get("REFRESH_SECRET");
  const url = new URL(req.url);
  const provided = req.headers.get("x-refresh-secret") ?? url.searchParams.get("secret");
  if (secret && provided !== secret) return json({ error: "unauthorized" }, 401);

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceKey) {
    return json({ error: "missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY" }, 500);
  }
  const supabase = createClient(supabaseUrl, serviceKey);

  const currency =
    url.searchParams.get("currency") ?? Deno.env.get("AZURE_PRICE_CURRENCY") ?? "EUR";
  const filter =
    url.searchParams.get("filter") ??
    Deno.env.get("AZURE_PRICE_FILTER") ??
    "serviceName eq 'Virtual Machines' and armRegionName eq 'westeurope' and priceType eq 'Consumption'";

  const params = new URLSearchParams({
    "$filter": filter,
    currencyCode: currency,
    "api-version": API_VERSION,
  });
  let next: string | null = `${PRICES_ENDPOINT}?${params.toString()}`;

  let fetched = 0;
  let upserted = 0;
  let pages = 0;
  try {
    while (next && pages < PAGE_CAP) {
      const payload = await fetchPage(next);
      const rows = (payload.Items ?? []).map(mapRow);
      fetched += rows.length;

      for (let k = 0; k < rows.length; k += UPSERT_BATCH) {
        const batch = rows.slice(k, k + UPSERT_BATCH);
        const { error } = await supabase
          .from("azure_prices")
          .upsert(batch, { onConflict: ON_CONFLICT });
        if (error) throw new Error(`upsert failed: ${error.message}`);
        upserted += batch.length;
      }

      next = payload.NextPageLink ?? null;
      pages++;
    }
  } catch (e) {
    return json({ ok: false, error: String(e), fetched, upserted, pages }, 502);
  }

  return json({
    ok: true,
    currency,
    filter,
    pages,
    fetched,
    upserted,
    capped: pages >= PAGE_CAP && Boolean(next),
  });
});
