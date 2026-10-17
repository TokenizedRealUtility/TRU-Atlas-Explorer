# TRU Atlas 1.1 — Standalone Public Block Explorer

**A standalone, self-hosted, modern block explorer for the Tokenized Real Utility (TRU) proof-of-work L1.**

> **v1.1 community beta — live-node testing recommended.** Built against the TRU C++ source supplied October 17, 2026. Static source/API matching plus local mock and demo testing are included. **Live connectivity to your TRU mainnet node has not been verified in this environment.** Run the live-node smoke tests below before publishing a production release.

The repository does **not** contain TRU's C++ explorer, wallet, blockchain database, miner, or consensus logic. It is a separate read-only web application. Other people can run it alongside their own synchronized TRU Core node without using your hosted website.

## 1. What you get

- High-tech, responsive dark/light theme with **self-contained CSS, SVG and JavaScript** (no external CDN, npm or npm build step).
- Overview dashboard with chain height, hashrate (when available), difficulty (when available), mempool, miner and asset statistics.
- Latest blocks, individual historical block lookup, previous/next height navigation and transaction lists.
- Transaction detail view with inputs, outputs, confirmations and decoded fields when the source API supports them.
- Address lookup and history, plus a sortable, searchable and paginated address directory when the public index is available.
- TRU-native token UTXO listing; TRUScript listing; smart-contract directory and indexed contract activity; miner leaderboard; network health and supply summaries; network hashrate, difficulty and cadence charts where data exists.
- Supplied TRU logo optimized as WebP; muted 6-second hero animation plays once per page load, stops on its final frame, lazy-loaded after primary content. No-loop, reduced-motion and save-data fallback image.
- Node peer IP addresses are NOT returned in the standalone network summary.
- Search by block height, 64-character block hash/TXID or TRU mainnet address.
- No signing, mining, payments, broadcasts, wallet keys, transaction creation, raw submit or arbitrary RPC pass-through.
- Private server-side RPC authentication. Users' browsers never receive the token.
- A demo mode to test the design without connecting to a node.
- Basic tests, a systemd template, a Caddy HTTPS configuration and an ELI5 quick start.

### Two connection modes

| Mode | Requires | What works | Limits |
|---|---|---|---|
| **`rpc` (recommended)** | Running/synced TRU Core with its RPC cookie/token | Chain data, any block height, transactions, address history, miner activity, recent block spacing. Does **not** need the old C++ explorer enabled. | TRU Core's read-only RPC currently does not provide the same indexed balances, rich token UTXO lists and hashrate history as its public explorer API. They are visibly marked unavailable unless `TRU_API_URL` is also configured. |
| **`api`** | Existing TRU Core public HTTP explorer API | Richest UI: balances, token UTXO lists, TRUScripts, stats, decoded TX data, mining telemetry, history graphs. | Historical height lookups and block paging are limited by the node's `/api/blocks` route (only recent 10). **This mode does use the existing C++ HTTP API as its data source, but not its website.** |
| **`demo`** | Python only | Preview all layouts and sample navigation | All numbers are fictional and prominently labeled. Never use as a live network explorer. |

**Independent means the project can run on another port/domain, be hosted by another person and in RPC mode does not require the Core's C++ block explorer server. It still requires a synchronized TRU Core node as its blockchain data source. It is not a second validating node implementation.**

## 2. ELI5: run it first with NO blockchain connection

**Requirements:** Python 3.10 or later. On Ubuntu/Debian use `sudo apt install python3` if needed. Node.js is **not** required.

1. Download the ZIP from GitHub or clone the repository. For a ZIP, extract it and open a terminal **inside** the `TRU-Explorer-Standalone` directory.
2. Run:

```bash
python3 server.py --demo
```

3. Open **http://127.0.0.1:3030/** on that same computer.
4. Click **Overview**, **Blocks**, **Transactions**, **Mining Network** and **Analytics** to see the design.
5. Stop by pressing **Ctrl+C**.

**Reminder:** all displayed numbers in demo mode are simulated examples. No blockchain data is used.

## 3. ELI5: connect to YOUR TRU Core node (Linux)

### Step A — ensure TRU Core is running

Use your ordinary Core startup process. TRU Atlas does not start, sync or modify Core. Let Core finish syncing before testing.

Confirm the Core RPC endpoint. In the supplied TRU source, the **default mainnet RPC port is 21832**, with HTTP path `/rpc` and Bearer-token authentication.

**Important:** the Core should remain bound to `127.0.0.1`. Do **not** port-forward its RPC to the Internet.

### Step B — copy the sample configuration

From the extracted folder:

```bash
cp .env.example .env
chmod 600 .env
```

Open it with your preferred editor:

```bash
nano .env
```

For the simplest install, leave these lines in place:

```ini
TRU_MODE=rpc
TRU_RPC_URL=http://127.0.0.1:21832/rpc
TRU_RPC_TOKEN_FILE=~/.tru/rpc-cookie-21832
TRU_BIND=127.0.0.1
TRU_PORT=3030
```

In **your uploaded TRU Core source**, Core creates the private RPC cookie at `~/.tru/rpc-cookie-<RPC_PORT>` by default and writes the token into that file. TRU Atlas reads it **server-side**. The cookie belongs to the Linux user running Core. If you start Atlas under another user, that user will not normally have permission to read it.

If you changed your Core RPC port or set `TRU_RPC_COOKIE_FILE`, change the URL/cookie path accordingly. **Do not paste your cookie contents into ChatGPT, a GitHub issue, screenshots or the repository.**

Save in nano with **Ctrl+O**, **Enter**, then **Ctrl+X**.

### Step C — start the explorer

```bash
python3 server.py
```

Open **http://127.0.0.1:3030/** on the **same** machine.

**That is it.** TRU Atlas runs as a separate read-only service. You can stop it with **Ctrl+C** without stopping Core.

### Step D — confirm it is actually connected

Open a second terminal:

```bash
curl -s http://127.0.0.1:3030/healthz
curl -s http://127.0.0.1:3030/api/v1/status
curl -s http://127.0.0.1:3030/api/v1/blocks?limit=2
```

The health endpoint only proves the **explorer** server is up. `/api/v1/status` returning an actual height and hash confirms the **Core connection**. A height equal to the demo example is **not** a connectivity test if the site says DEMO MODE.

Search for a **known confirmed height** in the search bar and open its transactions to exercise RPC lookups.

## 4. Enable more features: token index, TRUScripts, richer charts

The read-only RPC methods you currently have do not provide the same indexed records as Core's explorer HTTP API. If you want them, add this URL to `.env` while staying in RPC mode (this also unlocks richer transaction decoding and address balance/asset fields when that local API is available):

```ini
TRU_MODE=rpc
TRU_API_URL=http://127.0.0.1:8001
```

**Replace `8001` with your actual Core explorer HTTP port; the bt878 test confirmed its Core public API listens on `8001`.** The supplied C++ source defines HTTP paths like `/api/tokens`, `/api/truscripts`, `/api/miners`, `/api/hashrate_history` and `/api/difficulty_history`, but the port is a runtime setting. Restart Atlas after editing. This is optional; the explorer still has a functional block/transaction/address frontend in RPC-only mode.

Alternatively, you may use:

```ini
TRU_MODE=api
TRU_API_URL=http://127.0.0.1:YOUR_CORE_EXPLORER_PORT
```

API-only mode works without reading the privileged RPC cookie, but old height lookup will be limited to the last 10 blocks unless you switch back to RPC mode.

**Security warning:** if you use `TRU_API_URL`, point it at a **trusted local** API. The existing node's HTTP API may include routes unrelated to this explorer (including wallet/mining gateways). Atlas forwards only a narrow fixed set of **GET** requests and never forwards privileged POST routes, but you should not publicly expose or reverse proxy your entire old Core HTTP API unintentionally.

## 5. Make it a public website for everyone

Locally Atlas listens on `127.0.0.1:3030`, so outsiders cannot directly reach it. That is intentional. For a public website:

1. Get a DNS name, e.g. `atlas.example.com`, and point its DNS records at your public server.
2. Install Caddy on that server using the official installation instructions for your operating system.
3. Copy `deploy/Caddyfile.example` to your Caddy configuration, replace `explorer.example.com` with your actual DNS name, then reload Caddy.
4. Make sure ports **80 and 443** are allowed by your firewall. Never open **21832** on the public firewall.
5. Keep Atlas bound to `127.0.0.1`. Caddy handles HTTPS and forwards site visits to Atlas.

Caddy example:

```caddy
atlas.example.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:3030
}
```

To keep Atlas running after terminal logout or reboot, use the supplied `deploy/tru-atlas.service.example` as a starting point. Update its Linux username and absolute folder paths. Then:

```bash
sudo cp deploy/tru-atlas.service.example /etc/systemd/system/tru-atlas.service
sudo nano /etc/systemd/system/tru-atlas.service
# Replace YOUR_LINUX_USER and the folder paths in that file before continuing.
sudo systemctl daemon-reload
sudo systemctl enable --now tru-atlas
sudo systemctl status tru-atlas --no-pager
```

If Core starts under systemd too, ensure Core is up and its cookie exists before Atlas tries to query it. Atlas does not need the Core started when the Atlas process itself starts; temporary connection failures are displayed clearly and recovered on later requests.

## 6. Troubleshooting

| Symptom | Check |
|---|---|
| Browser says cannot connect | Did you run `python3 server.py`? Is `3030` already in use? |
| Site loads but says Node unavailable | Try `curl http://127.0.0.1:3030/api/v1/status` and read the JSON error. |
| RPC authentication error | Verify `TRU_RPC_TOKEN_FILE` matches the Core port and that the **same OS user** can read that file. |
| Connection refused to Core | Check TRU Core is actually listening on `127.0.0.1:21832` or set your actual port in `.env`. |
| No token listings | RPC-only mode intentionally shows "API not configured." Set `TRU_API_URL` if you have the public index. |
| No difficulty/chain hashrate in RPC-only mode | Core's `getchaininfo.difficulty` is a compact header bits field. Atlas does **not** mislabel this as a conventional difficulty number. Use the public API for the derived metrics. |
| Old block page not found in API-only mode | Switch to RPC mode. The supplied `/api/blocks` response contains only ten recent blocks. |
| Address says balance unavailable in RPC-only mode | The exposed `getaddresstransactions` method returns history, not a universally indexed confirmed balance. |
| Demo values still displayed | Stop Atlas; set `TRU_MODE=rpc` in `.env`; restart it without `--demo`. |
| Browser shows raw public API error | Your Core public API may be using a different port or version; compare its JSON with `docs/API_MAPPING.md`. |

## 7. Test before uploading to GitHub

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile server.py
```

Optional JavaScript syntax check if you happen to have Node.js (not required to run Atlas):

```bash
node --check static/app.js
```

When connected to **your own live Core**, test all these by hand:

- Overview loads real height and tip hash (not a demo label).
- Searching a known **old** block height returns the expected hash in RPC mode.
- Clicking a transaction in that block shows a TXID and outputs.
- Searching an address with known activity returns relevant history.
- No RPC Bearer token appears in page HTML, JavaScript, network JSON responses, or logs.
- Entering nonsense inputs returns 400 or 404, not a stack trace.
- Restart Core or briefly disconnect and confirm the explorer recovers.
- If you set `TRU_API_URL`, verify token, TRUScript and miner tables with your live data.
- Verify browser layout on a narrow phone display.

This repository's tests use a fake RPC adapter and a local sample service; they **do not prove** compatibility with every version of the real TRU network. See `docs/API_MAPPING.md` for the source-specific mapping and limitations.

## 8. GitHub release checklist

1. Decide the final repository name (suggested: `TRU-Atlas-Explorer`).
2. Remove all `.env`, cookie files, wallet data, logs and local test captures before committing. `.gitignore` provides defense-in-depth.
3. Include `server.py`, `static/`, `deploy/`, `tests/`, `docs/`, `.env.example`, `README.md`, `LICENSE`.
4. Test against a synchronized TRU node and verify live status. Document the TRU Core version/commit you tested.
5. Publish the source and an initial **beta/pre-release** until independent operators confirm compatibility.
6. Announce that no funds, wallets or private keys are needed to browse.

## 9. Compatibility and honest limitations

This package is **not** a replacement for the blockchain, a wallet, a mining pool, a validator, a marketplace, or an archival indexer. It does not introduce any consensus opcode, fork, daemon patch or database migration. RPC-only view limitations are intentional: the source RPC response for a raw transaction gives output scripts/values but not the public HTTP API's richer token and address decoding. Likewise, `getaddresstransactions` is a bounded read-only history endpoint, not a full address-balance database. The public HTTP API's `/api/tokens` lists token UTXOs rather than unique token ID records. Numerical charts do not invent missing data.

Security: keep the privileged Core RPC loopback-only; always use HTTPS on the public web frontend; use a non-root OS account; protect the Core RPC cookie file; review Core's own public API exposure separately. This is a community-testing release, not a security audit.

## License

MIT — see `LICENSE`. This license applies to **TRU Atlas code in this repository**, not to TRU Core files or code copied from third-party dependencies (none are bundled).

## 10. Windows and macOS notes

- **macOS:** install Python 3.10+, open Terminal, and use the same commands as Linux. A Core instance on the same Mac can use a cookie file in `~/.tru/` when configured identically.
- **Windows:** install Python 3.10+ from python.org (enable Python on PATH); in PowerShell, use `py -3 server.py --demo` or `py -3 server.py`. You can copy `.env.example` to `.env` using File Explorer or PowerShell `Copy-Item .env.example .env`. The supplied Core RPC auth implementation uses `%LOCALAPPDATA%\TRU\rpc-cookie-21832` by default on Windows rather than the Linux `~/.tru/` path; set `TRU_RPC_TOKEN_FILE` to the expanded path if you run Atlas on the same PC. Never paste the cookie value into a GitHub file.

The GitHub-ready ZIP is a normal source repository; no proprietary binary installer, container daemon or hosted account is necessary.

## 8. What's new in 1.1

See `UPGRADE_FROM_1.0.md` for a safe, side-by-side test on bt878. The brand image and media are stored under `static/assets/`. These are pre-optimized for fast loading (WebP header logo ≈11 KB, poster ≈55 KB, video ≈731 KB). The video is not a background stream: it downloads only after the overview is rendered and finishes once. If the visitor prefers reduced motion or uses data saver, the poster is shown instead.

New read-only Atlas endpoints: `GET /api/v1/addresses`, `GET /api/v1/contracts`, `GET /api/v1/contract-activity/{address}`, `GET /api/v1/network`. These only call existing **GET** routes on the configured TRU Core public HTTP API. They never directly access wallet files, chain databases, or authenticated write RPC methods. All advanced endpoints visibly return `available:false` when `TRU_API_URL` is not set.

If you update code on a running site, replace the application files but **preserve your private `.env`**. Restart Atlas; your TRU node keeps running. Do not publish `.env` on GitHub.
