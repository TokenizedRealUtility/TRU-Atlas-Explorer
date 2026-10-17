# TRU Atlas 1.1 Beta — Release Notes

New UI, standalone read-only backend, source-mapped TRU API features, bundled optimized graphics. No changes required to TRU Core.

## Changes

- **Identity:** User-provided TRU hexagonal logo in the left brand bar, encoded as ~11 KB WebP instead of loading a 3 MB original image.
- **Hero media:** User-provided 5.9-second video compressed to ~731 KB H.264 MP4. Starts loading after first status cards, muted, one play per page refresh, pauses on its last frame. Reduced-motion and data-saver users see the ~55 KB final-frame poster.
- **Dashboard:** First render waits only for `/api/v1/status`; block lists and analytics fill in afterward. Additional indexed KPI cards include addresses, contracts, TRUScripts and block target.
- **Addresses:** Sortable/searchable 25-per-page directory using TRU Core `/api/addresses`; links to existing address detail view.
- **Smart contracts:** Contract list with per-address record inspection using `/api/contracts` and `/api/contracts/{address}/txs`.
- **Network & supply:** Curated read-only reporting of Core's `/api/chain`, `/api/health`, `/api/supply`, `/api/uptime`, `/api/token-burn`, and aggregate peer count. No peer IP records or RPC secrets leaked. The `circulating_supply_status` is shown; missing circulation is never treated as zero or invented.
- **Server media support:** Static allowlist, browser byte-range requests (206) for MP4, 416 for invalid ranges, HEAD probes.
- **Deploy:** Upgrading from v1.0 works on a separate port first. Source package does not include `.env` or wallet credentials.

## Verification

- 23 local automated test invocations passed; frontend Node.js syntax verified and Python compiled successfully.
- Frontend layout and new views rendered under controlled fixture data in a headless browser without JS errors. This is not a live Core integration test.
- On bt878, the user confirmed all nine underlying Core API GET routes return HTTP 200. This confirms reachability, not correctness of every endpoint payload or TRU Atlas v1.1 integration.
- **Next:** Run the mainnet smoke tests on bt878 from `UPGRADE_FROM_1.0.md` before public production release.

## Security

Do not publish `.env`, the Core RPC cookie, wallet secrets or the Core's private RPC. Keep the Core RPC bound to loopback. The standalone Atlas service accepts no transaction signing, sends or arbitrary RPC dispatch. Use HTTPS and a reverse proxy before making a public Internet deployment.
