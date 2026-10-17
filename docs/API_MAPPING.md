# TRU Core API compatibility mapping — reviewed 2026-10-17

**Inputs reviewed:** `src(20261017-143828).zip`, the supplied `BLOCKCHAIN_CODE_FOR _EXPLORER.cpp`, `app(1).js`, `index(20261017-144827).html` and README.

This document records what was present in the provided code. It is **not** a claim that every installed TRU node runs this exact build.

## Read-only Core RPC (RPC mode, recommended)

The supplied `rpc_server.cpp` dispatches these methods, using `POST /rpc` with `Authorization: Bearer <server-side-cookie>`:

| Atlas request | Core JSON-RPC method and params | Transform |
|---|---|---|
| `/api/v1/status` | `getchaininfo` `{}`, `getrawmempool` `{}`, `getchainsupply` `{}` (best-effort) | `bestHeight` → height; `bestHash` → tip; do not present compact `difficulty` bits as difficulty ratio. |
| `/api/v1/blocks` | `getblockcount` `{}` + bounded `getblockbyheight` `{height}` | Returns blocks sorted newest first; cap 30 at request boundary, cache short-lived by height. |
| `/api/v1/block/HEIGHT` | `getblockbyheight` `{height}` | `prevhash`→`prevHash`, `merkleroot`→`merkleRoot`, `tx[]`→`transactions[]`. |
| `/api/v1/block/HASH` | `getblock` `{hash}` | Same transform. |
| `/api/v1/transactions` | Recent `getblockbyheight` `{height}` | Bounded scan across the latest 20 heights, TXIDs only; amounts unavailable. |
| `/api/v1/tx/TXID` | `getrawtransaction` `{txid,verbose:true}` and `gettransaction` `{txid}` | `vout[].value` (TRU) → `amountAtoms` strings (integer base units) using Decimal. `gettransaction` locates active/mempool status. More decoded details not provided. |
| `/api/v1/address/ADDRESS` | `getaddresstransactions` `{address,count:100,maxBlocks:0}` | Bounded history. No asserted full confirmed balance or total history count. |
| `/api/v1/miners` | `getallminers` `{}` | Observational data; trust only node's description of source. |
| `/api/v1/charts` | Up to 36 `getblockbyheight` results | Header timestamp intervals, not real-time network propagation; hashrate/difficulty series unavailable without public API. |

**Security check:** No `sendrawtransaction`, `submitblock`, `getblocktemplate`, `sendtoaddress`, wallet-secret, signing, state-changing or arbitrary browser-specified RPC is permitted. The browser sends only GET requests to Atlas.

## Public Core HTTP API (`TRU_API_URL`)

The separate `Blockchain::startExplorerServer` C++ function in the upload defines:

| Original HTTP route | Actual response shape and units | Atlas use |
|---|---|---|
| `/api/stats` | JSON object (`height`, `best_tip_hash`, `difficulty`, `networkHashrate`, `mempool_size`, etc.) | Dashboard stats. Hashrate is a calculated estimate. |
| `/api/blocks` | Array of **up to 10 recent blocks** sorted old→new (`height`, `hash`, `timestamp`, `size`, `cadenceSeconds`) | Recent blocks; **not** arbitrary height lookup. |
| `/block/<hash>` | Detail (`hash`, `prevHash`, `merkleRoot`, `timestamp`, `nonce`, `transactions[]`) | Block detail in API-only mode. |
| `/api/transactions?start=N&limit=M` | Array of objects with `txid`, `blockHeight`, `timestamp`, `vin[]`, `vout[].amount` **in atoms** | Transaction list; exact amounts from integer strings, not floating TRU. |
| `/api/transaction/<txid>` | `vin[]`, `vout[]`, `fee`, `confirmations`, `blockHeight`, `blockHash` (if known), token data; amounts/fee **in atoms** | Detailed transaction, script types, address links, fee. |
| `/api/address/<T...>` | `{address,balance,transactionCount,transactions,tokens,scripts}`; `balance` **in TRU** | Indexed address balance and holdings. |
| `/api/tokens?start=N&limit=M` | Array of **token UTXOs** with `tokenID`, `type`, `amount`, `owner`, `txid`; raw token unit depends on metadata | Token output list. Not unique token issuance count. |
| `/api/truscripts?page=N&limit=M` | Object `{page,limit,total,truscripts[]}` | Paginated inscription listings. |
| `/api/miners` | Object `{success,miners,summary,timestamp}` | Miner reports + chain-derived producer history. |
| `/api/hashrate_history?blocks=N` | Array of `{height,hashrate,hashrate_gh,timestamp}` | Hashrate time series. |
| `/api/difficulty_history` | Array of `{height,difficulty}` | Difficulty time series. |

`/api/wallet/rpc` and `/api/mining/rpc` in the C++ source are **intentionally not proxied by Atlas**. No Core source modifications are needed.

## Important differences from original supplied `app.js`

- Original block-height search checked `/api/blocks` (a ten-block sliding window); it could not find old heights. RPC mode fixes that with `getblockbyheight`.
- Original frontend interpolated node-supplied strings directly into HTML; the new UI HTML-escapes content before rendering.
- Original code let visitors type arbitrary backend URL endpoints stored in `localStorage`; Atlas uses a **server-operator-selected upstream** so visitors cannot use the service as a generic cross-origin proxy.
- Original summary used `formatUnits()` on integer-atom transaction output; Atlas represents atoms as exact decimal strings and only converts for display.
- Original repo required the existing C++ HTTP explorer API. Atlas can run from TRU Core's JSON-RPC alone, while its **advanced optional data** still comes from HTTP when available.

## Known caveats to verify on a live node

- A Core node's `getrawtransaction` returns `vout[].value` as JSON floats, inherently limiting precision before Atlas receives them. If exact large/edge values are needed, a future read-only atomic-value RPC would be preferable.
- `getaddresstransactions` builds a bounded history and may be expensive; Atlas caches address queries for 20 seconds.
- `gettransaction` can describe SIDECHAIN/CONFLICTED/MEMPOOL states. Atlas does not present these as confirmed.
- API `getallminers` and `/api/miners` use different report structures; Atlas normalizes both.
- Changes to RPC auth or output field names in later Core versions require adapter retesting.
- Atlas has no separate persistent address/token index and may have limited chain-wide pagination and token discovery without the optional Core HTTP API.

## Hybrid mode (`TRU_MODE=rpc` plus `TRU_API_URL`)

The RPC connection stays the primary source for block height, tip hash, historical blocks and fallback transaction/address views. The optional HTTP API can enrich transactions, address balances/asset holdings, token lists, TRUScripts and historical charts. Statistical fields are only merged into the RPC status **if the public API reports an identical tip height and block hash**. When the public API is unavailable, RPC-only core browsing continues without it.


## 1.1 additional Core public GET interfaces

| Atlas route | Core public API | Response contract |
|---|---|---|
| `/api/v1/addresses` | `/api/addresses` | `{addresses:[{address,balance,transactionCount}],total,start,limit}`; search and sort forwarded with validation |
| `/api/v1/contracts` | `/api/contracts` | `{contracts:[...]}` |
| `/api/v1/contract-activity/{address}` | `/api/contracts/{address}/txs` | `{address,contracts:[...]}` |
| `/api/v1/network` | `/api/supply`, `/api/chain`, `/api/health`, `/api/uptime`, `/api/token-burn`, `/api/peers` | Curated read-only fields; peer IPs are never returned |

These GET APIs are optional enrichments and are **not** part of the TRU consensus interface. Atlas does not forward any C++ explorer wallet, mining, raw transaction broadcast, or arbitrary RPC methods.
