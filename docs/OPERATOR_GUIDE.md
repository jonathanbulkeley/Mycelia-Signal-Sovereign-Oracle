# Oracle Operator's Guide

How to run your own Sovereign Lightning Oracle and sell signed data for sats.

## Overview

An SLO operator runs one or more oracle servers behind a custom L402 proxy, connected to a Lightning node. Clients pay Lightning invoices to receive signed price assertions. You earn sats for every query.

## What You Need

1. **A Linux server** — Cloud VM (GCP, AWS, etc.) or your own hardware
2. **A Lightning node** — LND (self-hosted or Voltage/hosted)
3. **Go 1.21+** — For building the L402 proxy
4. **Python 3.10+** — For running the oracle servers

Estimated costs:
- Cloud VM: ~$15/month (GCP e2-small)
- Lightning node: ~$27/month (Voltage Standard) or free (self-hosted)
- Channel liquidity: 3-4M sats (~$2,000 at current prices) for inbound capacity

## Architecture
```
Internet → L402 Proxy (:8080) → Oracle backends (:9100-9107)
                 ↕
          Your LND node
          (REST API for invoices)
```

The L402 proxy handles all payment logic — invoice creation, macaroon minting, and token verification. Your oracle code is a simple HTTP server that fetches prices, signs them, and returns JSON. Zero payment logic in the oracle itself.

## Current Production Setup

SLO runs 8 oracle endpoints on a single GCP VM:

| Endpoint | Port | Sources | Price |
|---|---|---|---|
| BTCUSD spot | 9100 | 9 exchanges (5 USD + 4 USDT) | 10 sats |
| BTCUSD VWAP | 9101 | Coinbase, Kraken trades | 20 sats |
| ETHUSD spot | 9102 | 5 exchanges | 10 sats |
| EURUSD spot | 9103 | 5 central banks + 2 exchanges | 10 sats |
| DLC attestor | 9104 | Same as BTCUSD (9 sources) | 1000 sats |
| XAU/USD gold | 9105 | 3 traditional + 5 PAXG exchanges | 10 sats |
| BTC/EUR cross | 9106 | Derived from BTCUSD + EURUSD | 10 sats |
| SOL/USD spot | 9107 | 9 exchanges (5 USD + 4 USDT) | 10 sats |

## Step 1: Set Up Your Lightning Node

### Option A: Voltage (hosted, easiest)

1. Create a mainnet node at https://app.voltage.cloud
2. Download `tls.cert` and `admin.macaroon`
3. Fund the node and open channels (see [DEPLOYMENT.md](DEPLOYMENT.md))

### Option B: Self-hosted LND

1. Install LND: https://github.com/lightningnetwork/lnd
2. Sync to chain, create wallet
3. Open channels to well-connected peers

Either way, you need **inbound liquidity** to receive payments. Open a channel with `push_sat` to give the remote side funds that can flow back to you when clients pay.

## Step 2: Install and Build
```bash
# System packages
sudo apt install -y python3 python3-pip golang-go git

# Python dependencies
pip3 install fastapi uvicorn ecdsa requests --break-system-packages

# Clone SLO
git clone https://github.com/jonathanbulkeley/sovereign-lightning-oracle.git ~/slo

# Build the L402 proxy
mkdir -p ~/slo-l402-proxy
cp ~/slo/l402-proxy/* ~/slo-l402-proxy/
cd ~/slo-l402-proxy
go build -o slo-l402-proxy .
```

## Step 3: Configure Your Oracle

### Signing Keys

Each oracle generates a fresh secp256k1 key pair on startup. The public key is returned with every response so clients can verify signatures.

For production, you should use a persistent key so clients can pin your identity across restarts. Modify the oracle code to load a key from disk:
```python
import os
from ecdsa import SigningKey, SECP256k1

KEY_PATH = "/home/your_user/slo/keys/oracle.pem"

if os.path.exists(KEY_PATH):
    with open(KEY_PATH, "rb") as f:
        PRIVATE_KEY = SigningKey.from_pem(f.read())
else:
    PRIVATE_KEY = SigningKey.generate(curve=SECP256k1)
    os.makedirs(os.path.dirname(KEY_PATH), exist_ok=True)
    with open(KEY_PATH, "wb") as f:
        f.write(PRIVATE_KEY.to_pem())

PUBLIC_KEY = PRIVATE_KEY.get_verifying_key()
```

### Price Sources

Each oracle feed aggregates from multiple exchanges. The pattern:

- **Tier 1 (USD pairs):** Direct fiat trading pairs from major exchanges
- **Tier 2 (USDT pairs):** USDT-denominated pairs normalized to USD via a live USDT/USD rate

The USDT/USD rate is sourced from Kraken and Bitstamp (median). If USD and USDT medians diverge by more than 0.5%, USDT sources are dropped automatically.

Considerations when selecting sources:
- **Redundancy** — Use at least 5 sources; the oracle takes the median
- **Rate limits** — Public APIs may throttle you; use timeouts and handle failures gracefully
- **Latency** — Slower sources add response time; set aggressive timeouts (5s per source)
- **Geographic diversity** — Mix US and EU exchanges to reduce correlated failures

### Pricing Your Data

Prices are configured in the L402 proxy's route map (`main.go`):
```go
var routes = map[string]Route{
    "/oracle/btcusd":      {Backend: "http://127.0.0.1:9100", Price: 10},
    "/oracle/btcusd/vwap": {Backend: "http://127.0.0.1:9101", Price: 20},
    "/oracle/solusd":      {Backend: "http://127.0.0.1:9107", Price: 10},
}
```

Pricing considerations:
- Too cheap and you don't cover costs
- Too expensive and clients choose other oracles
- More computation or better data justifies higher prices (VWAP > spot, DLC attestation > spot)
- The market will tell you — if query volume drops, your price is too high

## Step 4: Configure the L402 Proxy

Edit `main.go` to set your LND connection details:
```go
var (
    lndREST     = "https://YOURNODE.m.voltageapp.io:8080"
    macaroonHex string
    rootKey     []byte
)
```

Update credential paths in `main()`:
```go
macData, err := os.ReadFile("/home/YOUR_USER/slo/creds/admin.macaroon")
rootKeyPath := "/home/YOUR_USER/slo/creds/l402_root_key.bin"
```

The proxy generates an L402 root key on first run and persists it to disk. This key mints and verifies all macaroons — back it up.

Rebuild after any changes:
```bash
cd ~/slo-l402-proxy
go build -o slo-l402-proxy .
```

## Step 5: Launch
```bash
# Start oracles
python3 ~/slo/oracle/liveoracle_btcusd_spot.py &
python3 ~/slo/oracle/liveoracle_btcusd_vwap.py &
python3 ~/slo/oracle/liveoracle_ethusd_spot.py &
python3 ~/slo/oracle/liveoracle_eurusd_spot.py &
python3 ~/slo/oracle/liveoracle_xauusd_spot.py &
python3 ~/slo/oracle/liveoracle_btceur_spot.py &
python3 ~/slo/oracle/liveoracle_solusd_spot.py &

# Start L402 proxy
~/slo-l402-proxy/slo-l402-proxy &
```

### Verify
```bash
curl -v http://localhost:8080/oracle/btcusd
# Should return 402 with a Lightning invoice
```

## Step 6: Keep It Running

Use systemd to survive reboots and SSH disconnects:
```bash
sudo tee /etc/systemd/system/slo-btcusd-spot.service << 'EOF'
[Unit]
Description=SLO BTCUSD Spot Oracle
After=network.target

[Service]
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/slo
ExecStart=/usr/bin/python3 /home/YOUR_USER/slo/oracle/liveoracle_btcusd_spot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable slo-btcusd-spot
sudo systemctl start slo-btcusd-spot
```

Repeat for each oracle and the L402 proxy.

## Monitoring

### Check oracle health
```bash
curl http://localhost:9100/health  # BTCUSD
curl http://localhost:9107/health  # SOLUSD
```

### Check channel balance
```bash
curl -k --header "Grpc-Metadata-macaroon: YOUR_HEX_MACAROON" \
  https://YOURNODE.m.voltageapp.io:8080/v1/balance/channels
```

### Check earnings
```bash
curl -k --header "Grpc-Metadata-macaroon: YOUR_HEX_MACAROON" \
  https://YOURNODE.m.voltageapp.io:8080/v1/invoices?reversed=true&num_max_invoices=10
```

### Watch for problems

- **Oracle returning errors** — Exchange APIs may be down; check logs
- **L402 proxy not starting** — Usually a macaroon path or LND connection issue
- **No payments arriving** — Check inbound liquidity; channel may be depleted
- **Channel force-closed** — Peer went offline; need to open a new channel

## Adding New Data Types

To create a new oracle (e.g., a new trading pair):

1. Create the feed: `oracle/feeds/newpair.py` — fetch from exchanges, compute median
2. Create the oracle server: `oracle/liveoracle_newpair_spot.py` — FastAPI, sign canonical message, run on next available port
3. Add the route to `main.go`: `"/oracle/newpair": {Backend: "http://127.0.0.1:910X", Price: 10},`
4. Rebuild the proxy: `go build -o slo-l402-proxy .`
5. Start the oracle, restart the proxy

The protocol is data-agnostic. Any verifiable assertion can be sold this way — prices, rates, weather, election results, sports scores. If a client will pay for it and you can sign it, it's an oracle.

## Economics

A rough model for an SLO instance running 8 oracle endpoints:

| Item | Monthly Cost |
|---|---|
| GCP e2-small VM | $15 |
| Voltage Standard node | $27 |
| **Total operating cost** | **$42** |

At 10 sats per query (~$0.007):
- **Break even:** ~6,000 queries/month (~200/day)
- **At 1,000 queries/day:** ~$210/month revenue, ~$168 profit

The real value comes from serving multiple data types on the same infrastructure. Each new oracle endpoint is incremental revenue on the same fixed costs. Adding SOL/USD to an existing BTC/USD setup costs zero additional infrastructure — just a new Python file and a one-line proxy route.
