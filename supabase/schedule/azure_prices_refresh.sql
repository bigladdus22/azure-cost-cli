-- Schedule the Azure price-cache refresh with pg_cron + pg_net.
--
-- Run this in the Supabase SQL editor AFTER deploying the refresh-azure-prices
-- function and setting its secrets. Replace <PROJECT_REF> and <REFRESH_SECRET>.
-- Retail prices move rarely, so weekly is plenty (Mondays 03:00 UTC here).

create extension if not exists pg_cron;
create extension if not exists pg_net;

select cron.schedule(
    'refresh-azure-prices',
    '0 3 * * 1',
    $$
    select net.http_post(
        url     := 'https://<PROJECT_REF>.functions.supabase.co/refresh-azure-prices',
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'x-refresh-secret', '<REFRESH_SECRET>'
        ),
        body    := '{}'::jsonb,
        timeout_milliseconds := 120000
    );
    $$
);

-- Run once immediately to populate the cache the first time:
--   select net.http_post(
--       url     := 'https://<PROJECT_REF>.functions.supabase.co/refresh-azure-prices',
--       headers := jsonb_build_object('Content-Type','application/json','x-refresh-secret','<REFRESH_SECRET>'),
--       body    := '{}'::jsonb,
--       timeout_milliseconds := 120000
--   );
--
-- Inspect / remove the schedule:
--   select * from cron.job;
--   select cron.unschedule('refresh-azure-prices');
