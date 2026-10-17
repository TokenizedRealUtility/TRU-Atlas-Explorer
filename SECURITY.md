# Security — TRU Atlas

## Threat model and safe deployment

The web UI is **read-only**, and the server only invokes a fixed, hardcoded set of read-only Core JSON-RPC methods. However, **the TRU RPC Bearer cookie grants broader access to Core than this explorer uses**. Protect the cookie and run Atlas only on a trusted machine and account. Keep Core's own RPC listener bound to loopback (127.0.0.1). Never make port 21832 publicly reachable.

- Never upload `.env`, RPC cookies, private keys, wallets, data directories, token values, user credentials or server logs that contain sensitive information to GitHub.
- `TRU_RPC_TOKEN_FILE` is read only on the server. The browser cannot select an RPC method or upstream host.
- Atlas handles **GET only** for public API routes and uses strict validation for height, block hash, TXID and address input.
- No wallet signing, transaction submission, staking, mining, consensus execution, marketplaces or private account management APIs exist in Atlas.
- The frontend escapes dynamic HTML fields, sets Content-Security-Policy and avoids external JavaScript/CSS CDNs.
- Use HTTPS at the public reverse proxy. Apply rate limiting and DDoS protection there for high-traffic public installs.
- The underlying TRU Core node must be regularly updated, monitored and tested separately.
- `TRU_ALLOW_REMOTE_RPC=1` bypasses the default remote-RPC safeguard and should **not** be used on untrusted networks. Prefer SSH tunnels when Atlas and Core reside on different machines.
- If you also set `TRU_API_URL`, inspect the exposure of that separate Core HTTP server. Atlas doesn't forward its POST routes, but other reverse proxies may still expose them.

## Reporting vulnerabilities

Open a private GitHub security advisory on the eventual public repository rather than publicly posting an exploit or any secret.

The included automated tests are **not** a security audit or a guarantee of production safety. A live TRU integration test and security review are appropriate before announcing general availability.
