# Changelog

## 1.1.0 (2026-10-17)
- Optimized TRU-branded sidebar icon from supplied artwork; original high-res asset not needed to serve page.
- Six-second animated TRU Blockchain hero media, muted, plays once per page load, rests on final frame. Loads after content and skips animation on reduced-motion/save-data.
- Address directory using `/api/addresses`, searchable and sortable, with pagination.
- Smart contract directory and per-address contract activity using `/api/contracts`.
- Network and supply observability with curated, read-only projections; strips peer identities and network addresses.
- More dashboard KPIs from the matching `/api/stats` Core public API response.
- Added tests for new RPC-supplement routes and media handling.
- No changes to TRU Core, consensus, wallet, node configuration, or its integrated explorer.

## 1.0.0-beta
- Initial independent Atlas release with Core RPC backend and optional advanced public API.
