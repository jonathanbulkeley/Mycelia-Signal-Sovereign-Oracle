# Oracle Operator's Guide

How to run your own sovereign oracle using the Mycelia Signal stack and sell signed data for sats and USDC.

## Overview

An operator runs one or more oracle backends behind an L402 proxy (Lightning) and/or x402 proxy (USDC on Base), connected to a Lightning node and/or a Coinbase CDP account. Clients pay per query and receive cryptographically signed price attestations. You earn sats or USDC for every query.

## What You Need

1. **A Linux server** — Cloud VM (GCP, AWS, etc.) or your own hardware. Ubuntu 24 recommended.
2. **A Lightning node** — LND (self-hosted or Voltage/hosted) for L402
3. **Coinbase CDP account** — For x402 USDC payments on Base
4. **Go 1.21+** — For building the L402 proxy and price-service
5. **Python 3.10+** — For running x402 proxy and econ services

Estimated costs:
- Cloud VM: ~$15–30/month (GCP e2-small or e2-medium)
- Lightning node: ~$27/month (Voltage Standard) or free (self-hosted)
- Channel liquidity: 3–4M sats for inbound capacity

## Architecture

```
Internet
  │
  ├── nginx (:80) ──────────────────────────────────────────────────┐
  │                                                                  │
  ├── L402 Proxy (:8080) ─── price-service (:9200)                  │
  │        │                  econ-us (:9129)                        │
  │        └── Voltage LND    econ-eu (:9130)                        │
  │                           econ-commodities (:9134)               │
  └── x402 Proxy (:8402) ─── (same backends)                        │
           │                                                          │
           └── Coinbase CDP (USDC verification on Base)              │
                                                                      │
  Cloudflare (DNS + TLS) ───────────────────────────────────────────┘
```

## Running Services

| Service | Port | Binary/Script | Purpose |
|---------|------|--------------|---------|
| price-service | 9200 | `~/myceliasignal/price-service/price-service` | 37 price pairs (crypto, FX, metals) |
| l402-proxy | 8080 | `~/myceliasignal/l402-proxy/l402-proxy` | L402 Lightning payment layer |
| x402-proxy | 8402 | `~/myceliasignal/x402_proxy.py` | x402 USDC payment layer |
| econ-us | 9129 | `~/myceliasignal/econ-us/econ-us` | 8 US economic indicators |
| econ-eu | 9130 | `~/myceliasignal/econ-eu/econ-eu` | 6 EU economic indicators |
| econ-commodities | 9134 | `~/myceliasignal/econ-commodities/econ-commodities` | 5 commodities |
| dlc-server | 9104 | `~/myceliasignal/dlc/server.py` | DLC oracle (threshold + numeric) |

All services managed by systemd with `Restart=on-failure`.

## Step 1: Set Up Your Lightning Node

### Option A: Voltage (hosted, easiest)

1. Create a mainnet node at https://app.voltage.cloud
2. Download `tls.cert` and `admin.macaroon`
3. Fund the node and open channels

### Option B: Self-hosted LND

1. Install LND: https://github.com/lightningnetwork/lnd
2. Sync to chain, create wallet, open channels

You need **inbound liquidity** to receive payments. Open a channel with `push_sat` to give the remote side funds that flow back to you when clients pay.

## Step 2: Set Up Coinbase CDP (x402)

1. Create a Coinbase Developer Platform account at https://developer.coinbase.com
2. Generate an API key — save the key ID and secret
3. Set environment variables in your x402 proxy systemd unit:
```
Environment="CDP_API_KEY_ID=your_key_id"
Environment="CDP_API_KEY_SECRET=your_key_secret"
```

Set your USDC receiving address in `x402_proxy.py`:
```python
PAYMENT_ADDRESS = "0xYOUR_ADDRESS"
```

## Step 3: Build and Install

```bash
# System packages
sudo apt install -y python3 python3-pip golang-go git nginx

# Python dependencies
pip3 install fastapi uvicorn httpx aiohttp pynacl coincurve prometheus-client --break-system-packages

# Clone the stack
git clone https://github.com/jonathanbulkeley/Mycelia-Signal-Sovereign-Oracle.git ~/sovereign-oracle

# Build price-service
cd ~/myceliasignal/price-service
go build -o price-service .

# Build L402 proxy
cd ~/myceliasignal/l402-proxy
go build -o l402-proxy .

# Build econ services
cd ~/myceliasignal/econ-us && go build -o econ-us .
cd ~/myceliasignal/econ-eu && go build -o econ-eu .
cd ~/myceliasignal/econ-commodities && go build -o econ-commodities .
```

## Step 4: Generate Signing Keys

Each protocol uses its own key:

```bash
# secp256k1 key for L402 signing sidecar
python3 -c "
import os, coincurve
key = coincurve.PrivateKey(os.urandom(32))
with open('keys/secp256k1.key', 'w') as f:
    f.write(key.secret.hex())
print('Pubkey:', key.public_key.format(compressed=True).hex())
"

# Ed25519 key for x402 signing
python3 -c "
import os
from nacl.signing import SigningKey
key = SigningKey.generate()
with open('keys/ed25519.key', 'w') as f:
    f.write(key.encode().hex())
print('Pubkey:', key.verify_key.encode().hex())
"

# L402 root key (macaroon minting)
python3 -c "import os; open('creds/macaroon-root.key','wb').write(os.urandom(32))"

chmod 600 keys/* creds/*
```

Publish your public keys so clients can verify signatures.

## Step 5: Configure price-service

Edit `~/myceliasignal/config/price-service.yaml` to define your pairs and sources:

```yaml
pairs:
  - id: btc/usd
    sources: [binance, coinbase, kraken, bitstamp, gemini, bitfinex, okx, gateio, binanceus]
    method: median
    dlc: true
  - id: eth/usd
    sources: [coinbase, kraken, bitstamp, gemini, bitfinex]
    method: median
```

## Step 6: Configure L402 Proxy

Edit `~/myceliasignal/l402-proxy/main.go` to set your LND connection and route pricing:

```go
// LND connection
lndREST  = "https://YOURNODE.m.voltageapp.io:8080"

// Route pricing (sats)
var freeRoutes = map[string]bool{
    "/oracle/price/btc/usd/preview": true,
    // ... all preview routes
}

var routes = map[string]Route{
    "/oracle/price/btc/usd":      {Backend: "http://127.0.0.1:9200/oracle/price/btc/usd",      Price: 10},
    "/oracle/price/btc/usd/vwap": {Backend: "http://127.0.0.1:9200/oracle/price/btc/usd/vwap", Price: 20},
    "/oracle/econ/us/cpi":        {Backend: "http://127.0.0.1:9129/oracle/econ/us/cpi",        Price: 1000},
    // ... all routes
}
```

Macaroon security — add path and expiry caveats:
```go
// Path caveat: macaroon only valid for the endpoint it was purchased for
// Expiry caveat: 30 seconds from issue
```

## Step 7: Configure x402 Proxy

Edit `~/myceliasignal/x402_proxy.py` to set pricing (in USDC):

```python
PAID_ROUTES = {
    "/oracle/price/btc/usd":      {"backend": f"{PRICE_BACKEND}/oracle/price/btc/usd",      "price_usd": 0.01},
    "/oracle/price/btc/usd/vwap": {"backend": f"{PRICE_BACKEND}/oracle/price/btc/usd/vwap", "price_usd": 0.02},
    "/oracle/econ/us/cpi":        {"backend": f"{ECON_US_BACKEND}/oracle/econ/us/cpi",       "price_usd": 1.00},
    # ... all routes
}
```

## Step 8: Configure nginx

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    # x402 proxy
    location /oracle/ {
        proxy_pass http://127.0.0.1:8402;
        add_header Access-Control-Allow-Origin *;
    }

    # L402 proxy
    location /l402/ {
        proxy_pass http://127.0.0.1:8080;
        add_header Access-Control-Allow-Origin *;
    }

    # DLC oracle
    location /dlc/ {
        proxy_pass http://127.0.0.1:9104;
        add_header Access-Control-Allow-Origin *;
    }
}
```

## Step 9: Systemd Services

Example unit file — repeat for each service:

```bash
sudo tee /etc/systemd/system/myceliasignal-price-service.service << 'EOF'
[Unit]
Description=Mycelia Signal Price Service
After=network.target

[Service]
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/myceliasignal/price-service
ExecStart=/home/YOUR_USER/myceliasignal/price-service/price-service
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable myceliasignal-price-service
sudo systemctl start myceliasignal-price-service
```

## Step 10: Verify

```bash
# Health check
curl http://localhost:9200/health

# Preview (free, no payment)
curl https://api.yourdomain.com/oracle/price/btc/usd/preview | jq .

# Paid endpoint — should return 402
curl -v https://api.yourdomain.com/oracle/price/btc/usd

# L402 paid endpoint — should return 402 with invoice
curl -v https://api.yourdomain.com/l402/oracle/price/btc/usd
```

## Monitoring

### Service status
```bash
sudo systemctl status myceliasignal-price-service
sudo journalctl -u myceliasignal-price-service -f
```

### Revenue database
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('~/myceliasignal/revenue.db')
for row in conn.execute('SELECT rail, recorded_at, amount_usdc, endpoint FROM revenue ORDER BY id DESC LIMIT 20'):
    print(row)
"
```

### Check channel balance
```bash
curl -k --header "Grpc-Metadata-macaroon: YOUR_HEX_MACAROON" \
  https://YOURNODE.m.voltageapp.io:8080/v1/balance/channels
```

### Common issues

- **Price service returning errors** — Exchange APIs may be down; check logs, verify sources
- **L402 proxy not starting** — Check macaroon path and LND REST connection
- **x402 CDP verification failing** — Verify CDP credentials in systemd env, check payment address
- **No payments arriving** — Check inbound Lightning liquidity; channel may need rebalancing
- **High memory usage** — econ services are lightweight; price-service needs ~200MB for all pairs

## Pricing Your Data

```
Spot/FX/metals:          10 sats  /  $0.01 USDC
VWAP:                    20 sats  /  $0.02 USDC
Economic indicators:  1,000 sats  /  $1.00 USDC
DLC registrations:   10,000 sats  /  $7.00 USDC
```

Considerations:
- More computation or better data justifies higher prices (VWAP > spot, econ > spot)
- Align L402 and x402 pricing — clients should not strongly prefer one rail on price alone
- Preview endpoints (free) drive discovery and adoption

## Economics

A rough model running the full Mycelia Signal stack:

| Item | Monthly Cost |
|------|-------------|
| GCP e2-medium VM (×2 GCs) | ~$60 |
| Voltage Standard node | ~$27 |
| **Total operating cost** | **~$87** |

At blended 10–20 sats per query (~$0.008 average):
- **Break even:** ~10,900 queries/month (~360/day)
- **At 1,000 queries/day:** ~$240/month revenue, ~$153 profit

Econ and DLC queries at higher prices dramatically improve economics. A single DLC registration (10,000 sats, ~$7) equals ~875 spot price queries in revenue.

## Adding New Data Types

1. Create a new Go service (or Python FastAPI service) on the next available port
2. Implement the canonical string format: `v1|PRICE|PAIR|VALUE|CURRENCY|DECIMALS|SOURCES|METHOD|TIMESTAMP|NONCE`
3. Add the route to both `l402-proxy/main.go` and `x402_proxy.py`
4. Add a preview route returning unsigned cached data
5. Add a nginx location block
6. Create a systemd unit and enable it

The stack is data-agnostic. Any verifiable assertion can be sold this way.

## Resources

- Docs: https://myceliasignal.com/docs
- Public repo: https://github.com/jonathanbulkeley/Mycelia-Signal-Sovereign-Oracle
- OpenAPI spec: https://myceliasignal.com/openapi.json
- x402 spec: https://github.com/coinbase/x402
- L402 spec: https://docs.lightning.engineering/the-lightning-network/l402
