# TRU Atlas — 5-minute beginner guide

**Step 1.** Extract `TRU-Atlas-Explorer-v1.1.zip` on your Linux, macOS or Windows computer.

**Step 2.** Open a terminal in the extracted `TRU-Atlas-Explorer-v1.1` folder.

**Step 3.** Preview the website without connecting to any blockchain:

```bash
python3 server.py --demo
```

Windows users can use `py -3 server.py --demo` instead.

**Step 4.** Open **http://127.0.0.1:3030/** in your web browser. All sample values are explicitly marked **DEMO**.

**Step 5.** To connect to a real, synced TRU Core node on the same computer, stop the demo with Ctrl+C and run:

```bash
cp .env.example .env
chmod 600 .env
python3 server.py
```

The sample `.env` is set for local TRU Core mainnet RPC port **21832** with your standard private cookie in `~/.tru/rpc-cookie-21832`. If those values differ, edit `.env` first. On Windows create `.env` through File Explorer and configure the cookie path to match your Core installation.

Open **http://127.0.0.1:3030/** again. You should see **real** height/hash data from your synchronized node and **no DEMO** label.

**Step 6.** For the optional token/inscription/advanced miner indexes, configure `TRU_API_URL` in `.env` to the Core's actual **local** public HTTP explorer API and restart Atlas. Read `README.md` for details and public HTTPS deployment.

**Never put your RPC cookie or a TRU wallet private key on GitHub. Never expose Core's RPC port 21832 to the Internet.**

## If you already have v1.0 running on bt878

For the safest upgrade, **run v1.1 on port 3031 first** and leave v1.0 on port 3030 unchanged. Full commands are in `UPGRADE_FROM_1.0.md`. The locally tested Core API URL on bt878 is `http://127.0.0.1:8001`.
