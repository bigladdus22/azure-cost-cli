-- Azure retail price cache
--
-- The GitHub Pages frontend must not call prices.azure.com directly (no CORS,
-- paginated, throttle-prone). Instead, the refresh-azure-prices Edge Function
-- fetches a filtered subset server-side and upserts it here; the browser reads
-- these rows via the anon key under RLS and never talks to Microsoft.

create extension if not exists "pgcrypto";

create table if not exists public.azure_prices (
    id                      uuid primary key default gen_random_uuid(),
    meter_id                text not null,
    arm_sku_name            text,
    arm_region_name         text not null,
    service_name            text not null,
    service_family          text,
    meter_name              text,
    product_name            text,
    sku_name                text,
    retail_price            numeric not null check (retail_price >= 0),
    unit_price              numeric check (unit_price >= 0),
    currency_code           text not null,
    unit_of_measure         text,
    price_type              text not null
                            check (price_type in ('Consumption', 'Reservation', 'DevTestConsumption')),
    tier_minimum_units      numeric not null default 0,
    is_primary_meter_region boolean not null default false,
    effective_start_date    timestamptz,
    fetched_at              timestamptz not null default now(),
    -- Natural key for idempotent upserts. A meter can appear per region and per
    -- consumption tier, so both are part of the key.
    constraint azure_prices_natural_key
        unique (meter_id, currency_code, price_type, tier_minimum_units, arm_region_name)
);

-- The frontend filters by service + region + price type + currency, then picks
-- the cheapest primary-region meter (optionally narrowed by ARM SKU).
create index if not exists azure_prices_lookup_idx
    on public.azure_prices (service_name, arm_region_name, price_type, currency_code);
create index if not exists azure_prices_sku_idx
    on public.azure_prices (arm_sku_name);

alter table public.azure_prices enable row level security;

-- Browser-safe, read-only access for the anon (and authenticated) roles. Writes
-- are performed by the Edge Function using the service-role key, which bypasses
-- RLS, so no insert/update/delete policy is defined here on purpose.
drop policy if exists "azure_prices anon read" on public.azure_prices;
create policy "azure_prices anon read"
    on public.azure_prices
    for select
    to anon, authenticated
    using (true);
