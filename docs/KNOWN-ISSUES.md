# Known issues

## The web page cannot connect to Azure pricing (browser CORS)

**Status:** open — parked for a later date.

**Symptom.** On the hosted / on-disk `docs/index.html` page, clicking *Estimate*
fails to fetch prices. The browser console shows a CORS error (or a failed
`fetch`) for `https://prices.azure.com/api/retail/prices`.

**Cause.** The page calls the Azure Retail Prices API **directly from the
browser**. That API does not reliably return
`Access-Control-Allow-Origin` headers for cross-origin browser requests, so the
browser blocks the response. This is a limitation of the API, not of the page
logic — the same request works fine server-side (e.g. from the Python CLI, which
is unaffected).

**Options to fix (later).**

1. **Small serverless proxy (recommended).** Stand up a tiny function that
   fetches from `prices.azure.com` server-side and re-emits the JSON with
   permissive CORS headers, then point the page's `ENDPOINT` at it. Good fits:
   - a **Supabase Edge Function** (keeps everything in the existing project),
   - a Cloudflare Worker, or an Azure Function.
2. **Use the CLI instead.** The Python tool (`azure-cost estimate`) talks to the
   API server-side and is not affected by this issue.

**Where the code is.** `docs/index.html` → the `iterItems()` / `fetchJson()`
functions and the `ENDPOINT` constant. Only `ENDPOINT` needs to change once a
proxy exists; the guardrails (filter building, paging, timeout) stay as-is.

**Not the cause.** API key/auth (the API is anonymous), the filter syntax, or the
region/currency values — those are validated before the request and work from
the CLI.
