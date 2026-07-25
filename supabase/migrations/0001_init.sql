-- azure-cost-cli initial schema
--
-- Inventory (input) + snapshots (output):
--   applications           -- one row per product/app to price
--   application_resources  -- the Azure meters each app consumes
--   cost_snapshots         -- a costed result for an app at a point in time
--   cost_snapshot_lines    -- per-resource breakdown of a snapshot
--
-- Guardrails baked into the schema: non-negative quantities/prices, a
-- constrained price_type, cascading deletes, and Row Level Security enabled on
-- every table (add policies to match how you authenticate).

create extension if not exists "pgcrypto";

create table if not exists public.applications (
    id          uuid primary key default gen_random_uuid(),
    name        text not null unique,
    environment text not null default 'prod',
    created_at  timestamptz not null default now()
);

create table if not exists public.application_resources (
    id             uuid primary key default gen_random_uuid(),
    application_id uuid not null references public.applications (id) on delete cascade,
    label          text,
    service_name   text not null,
    region         text not null,
    arm_sku_name   text,
    meter_name     text,
    product_name   text,
    price_type     text not null default 'Consumption'
                   check (price_type in ('Consumption', 'Reservation', 'DevTestConsumption')),
    unit           text not null default '1 Hour',
    quantity       numeric not null default 0 check (quantity >= 0)
);

create index if not exists application_resources_app_idx
    on public.application_resources (application_id);

create table if not exists public.cost_snapshots (
    id               uuid primary key default gen_random_uuid(),
    application_id   uuid references public.applications (id) on delete set null,
    application_name text not null,
    currency         text not null,
    monthly_total    numeric not null default 0 check (monthly_total >= 0),
    annual_total     numeric not null default 0 check (annual_total >= 0),
    generated_at     timestamptz not null default now()
);

create index if not exists cost_snapshots_app_idx
    on public.cost_snapshots (application_id, generated_at desc);

create table if not exists public.cost_snapshot_lines (
    id             uuid primary key default gen_random_uuid(),
    snapshot_id    uuid not null references public.cost_snapshots (id) on delete cascade,
    resource_label text,
    service_name   text not null,
    region         text not null,
    arm_sku_name   text,
    quantity       numeric not null default 0 check (quantity >= 0),
    unit_price     numeric not null default 0 check (unit_price >= 0),
    monthly_cost   numeric not null default 0 check (monthly_cost >= 0),
    meter_id       text
);

create index if not exists cost_snapshot_lines_snapshot_idx
    on public.cost_snapshot_lines (snapshot_id);

-- Enable RLS on every table. No permissive policies are created here on
-- purpose: with the service-role key (used by this CLI) RLS is bypassed, while
-- anon/authenticated access stays denied until you add explicit policies.
alter table public.applications          enable row level security;
alter table public.application_resources enable row level security;
alter table public.cost_snapshots        enable row level security;
alter table public.cost_snapshot_lines   enable row level security;
