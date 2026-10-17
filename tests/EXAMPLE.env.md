# TRU ATLAS LOCAL CONFIGURATION
TRU_MODE=rpc

# The latest TRU Core defaults to RPC port 21832.
# Keep the Core RPC bound to 127.0.0.1. Never expose this port publicly.
TRU_RPC_URL=http://127.0.0.1:21832/rpc

# TRU Core's default private RPC cookie is created automatically.
# File contents are a Bearer token; the explorer reads it server-side.
# On Linux with Core running as the same user:
TRU_RPC_TOKEN_FILE=~/.tru/rpc-cookie-21832

# Optional: if Core uses TRU_RPC_TOKEN instead of the cookie, set the
# explorer's TRU_RPC_TOKEN in its process environment, not in public JS.

# Optional richer API data (tokens, inscriptions, historical hashrate):
# e.g. http://127.0.0.1:8080  (replace 8080 with Core's actual explorer port)
TRU_API_URL=http://127.0.0.1:8001

# Set mode=api and TRU_API_URL to use the existing node public HTTP API
# instead of private Core RPC. Historical-height lookup is then limited.
TRU_BIND=0.0.0.0
#TRU_BIND=127.0.0.1
TRU_PORT=3030
TRU_EXPLORER_NAME=TRU Atlas
TRU_NETWORK_LABEL=TRU Mainnet
