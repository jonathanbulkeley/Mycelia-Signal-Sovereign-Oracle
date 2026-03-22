# Production Deployment Guide

Deploy Mycelia Signal on GCP with Voltage Lightning node.

## Architecture

```
Internet → Cloudflare (TLS) → nginx (:80)
                                  ├── /oracle/price/*  → L402 proxy (:8080) → price-service (:9200)
                                  ├── /oracle/econ/*   → L402 proxy (:8080) → econ-us (:9129)
                                  │                                          → econ-eu (:9130)
                                  │                                          → econ-commodities (:9134)
                                  ├── /health          → L402 proxy (:8080)
                                  └── all paid routes  → x402 proxy (:8402) [signing sidecar]

L402 proxy ↔ Voltage LND node (invoice creation + verification via REST)
x402 proxy ↔ Base RPC (USDC payment verification via CDP facilitator)
x402 proxy ← L402 proxy signing sidecar (/internal/sign/* routes)
```

**Key design point:** The x402 proxy (`x402_proxy.py`) serves dual roles:
1. Handles x402 USDC payment flow directly
2. Acts as a signing sidecar for L402 — the Go L402 proxy routes all paid responses through `/internal/sign/*` on the x402 proxy for secp256k1 ECDSA signing before returning to the client

All oracle backends are Go binaries. No Python oracle backends.

## Port Map

| Port | Service | Binary |
|------|---------|--------|
| 80 | nginx | system |
| 8080 | L402 proxy (Lightning) | `~/myceliasignal/l402-proxy/l402-proxy` |
| 8402 | x402 proxy (USDC + signing sidecar) | `~/myceliasignal/x402_proxy.py` |
| 9200 | price-service (37 price pairs) | `~/myceliasignal/price-service/price-service` |
| 9129 | econ-us (8 US indicators) | `~/myceliasignal/econ-us/econ-us` |
| 9130 | econ-eu (6 EU indicators) | `~/myceliasignal/econ-eu/econ-eu` |
| 9134 | econ-commodities (5 commodities) | `~/myceliasignal/econ-commodities/econ-commodities` |
| 9300 | node-exporter (Prometheus metrics) | system |
| 3000 | Grafana (monitoring) | system |
| 9090 | Prometheus | system |

## Prerequisites

- GCP Compute Engine VM (e2-small or larger, Ubuntu 24.04)
- Voltage account with a mainnet LND node
- Go 1.21+ (for building binaries)
- Python 3.10+ (for x402 proxy)
- Domain with Cloudflare DNS

---

## Step 1: Voltage Lightning Node

1. Create a **mainnet Standard node** at https://app.voltage.cloud
2. Download `admin.macaroon` from **Manage Access → Macaroon Bakery**
3. Note your REST endpoint: `YOURNODE.m.voltageapp.io:8080`

### Fund the Node

```bash
mac_hex=$(xxd -p admin.macaroon | tr -d '\n')
curl -k -H "Grpc-Metadata-macaroon: $mac_hex" \
  https://YOURNODE.m.voltageapp.io:8080/v1/newaddress
```

Send bitcoin to the returned address. Minimum ~3.5M sats for adequate inbound liquidity.

### Open Channels

```bash
# Connect to peer
curl -k -H "Grpc-Metadata-macaroon: $mac_hex" \
  -d '{"addr":{"pubkey":"PEER_PUBKEY","host":"PEER_HOST:9735"}}' \
  https://YOURNODE.m.voltageapp.io:8080/v1/peers

# Open channel with inbound liquidity
curl -k -H "Grpc-Metadata-macaroon: $mac_hex" \
  -d '{"node_pubkey_string":"PEER_PUBKEY","local_funding_amount":"1000000","push_sat":"500000"}' \
  https://YOURNODE.m.voltageapp.io:8080/v1/channels
```

---

## Step 2: GCP VM Setup

1. Create an **e2-small** VM (Ubuntu 24.04, 20GB disk)
2. Enable HTTP/HTTPS firewall rules
3. Add firewall rule for port 8080 (TCP, 0.0.0.0/0)

### Install Dependencies

```bash
sudo apt update
sudo apt install -y golang-go git python3 python3-pip nginx
pip3 install coincurve PyNaCl --break-system-packages
```

### Upload Credentials

```bash
# From local machine
scp -i ~/.ssh/google_compute_engine admin.macaroon \
  jonathan_bulkeley@YOUR_VM_IP:~/myceliasignal/creds/

# Generate L402 root key (32 random bytes)
dd if=/dev/urandom bs=32 count=1 > ~/myceliasignal/creds/l402_root_key.bin
chmod 600 ~/myceliasignal/creds/*
```

---

## Step 3: Clone and Build

```bash
git clone https://github.com/jonathanbulkeley/myceliasignal.git ~/myceliasignal
cd ~/myceliasignal
```

### Build price-service

```bash
cd ~/myceliasignal/price-service
go build -o price-service .
```

### Build L402 proxy

```bash
cd ~/myceliasignal/l402-proxy
go build -o l402-proxy .
```

### Build econ services

```bash
cd ~/myceliasignal/econ-us && go build -o econ-us .
cd ~/myceliasignal/econ-eu && go build -o econ-eu .
cd ~/myceliasignal/econ-commodities && go build -o econ-commodities .
```

---

## Step 4: Generate Signing Keys

Each GC node uses per-instance keypairs. One secp256k1 key for L402, one Ed25519 key for x402.

```bash
mkdir -p ~/myceliasignal/keys
chmod 700 ~/myceliasignal/keys

# Generate secp256k1 key (raw 32-byte binary)
python3 -c "
import os, coincurve
key = coincurve.PrivateKey()
with open('keys/oracle_secp256k1.key', 'wb') as f:
    f.write(key.secret)
print('secp256k1 pubkey:', key.public_key.format(compressed=True).hex())
" 
cd ~/myceliasignal

# Generate Ed25519 key
python3 -c "
from nacl.signing import SigningKey
import binascii
sk = SigningKey.generate()
with open('keys/oracle_ed25519.key', 'wb') as f:
    f.write(bytes(sk))
print('Ed25519 pubkey:', binascii.hexlify(bytes(sk.verify_key)).decode())
"
chmod 600 ~/myceliasignal/keys/*
```

Record both public keys — they are the oracle's verifiable identity.

---

## Step 5: Configure Services

### price-service config (`~/myceliasignal/config/price-service.yaml`)

The config file sets the port, signing key path, and LND credentials for the price service. Edit `config/price-service.yaml` — key fields:

```yaml
port: 9200
signing_key: /home/YOUR_USER/myceliasignal/keys/oracle_secp256k1.key
lnd_rest: https://YOURNODE.m.voltageapp.io:8080
macaroon_path: /home/YOUR_USER/myceliasignal/creds/admin.macaroon
```

### L402 proxy (`~/myceliasignal/l402-proxy/main.go`)

The L402 proxy routes paid requests through the signing sidecar. Key constants:

```go
const signingSidecar = "http://127.0.0.1:8402"
```

Credential paths in `main()`:
```go
macData, err := os.ReadFile("/home/YOUR_USER/myceliasignal/creds/admin.macaroon")
rootKeyPath := "/home/YOUR_USER/myceliasignal/creds/l402_root_key.bin"
```

LND REST endpoint:
```go
lndREST = "https://YOURNODE.m.voltageapp.io:8080"
```

Rebuild after any changes:
```bash
cd ~/myceliasignal/l402-proxy && go build -o l402-proxy .
```

### x402 proxy (`~/myceliasignal/x402_proxy.py`)

Set your USDC recipient address and key paths at the top of the file:

```python
PAYMENT_ADDRESS = "0xYOUR_USDC_ADDRESS_ON_BASE"
SECP256K1_KEY_PATH = "/home/YOUR_USER/myceliasignal/keys/oracle_secp256k1.key"
ED25519_KEY_PATH = "/home/YOUR_USER/myceliasignal/keys/oracle_ed25519.key"
```

---

## Step 6: Configure nginx

```bash
sudo tee /etc/nginx/sites-available/myceliasignal-internal << 'EOF'
server {
    listen 80;
    server_name api.myceliasignal.com;

    log_format detailed '$remote_addr - $http_x_forwarded_for - [$time_local] '
                        '"$request" $status $body_bytes_sent "$http_user_agent"';
    access_log /var/log/nginx/access.log detailed;

    # Health check
    location = /health {
        proxy_pass http://127.0.0.1:8080/health;
        proxy_set_header Host $host;
    }

    # x402 discovery
    location = /.well-known/x402 {
        proxy_pass http://127.0.0.1:8402/.well-known/x402;
        proxy_set_header Host $host;
        add_header Access-Control-Allow-Origin "*" always;
    }

    # Satring verify
    location = /.well-known/satring-verify {
        root /var/www/well-known;
        default_type text/plain;
    }

    # Oracle price + econ endpoints — L402 (primary) and x402
    location /oracle/ {
        add_header Access-Control-Allow-Origin "https://myceliasignal.com" always;
        add_header Access-Control-Allow-Headers "Authorization, X-Payment, Accept, Content-Type" always;
        add_header Access-Control-Allow-Methods "GET, OPTIONS" always;
        add_header Access-Control-Expose-Headers "WWW-Authenticate" always;
        if ($request_method = OPTIONS) { return 204; }
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Authorization $http_authorization;
        proxy_set_header X-Payment $http_x_payment;
    }

    # Legacy redirects — old namespace → new namespace
    location ~ ^/oracle/btcusd/vwap {
        return 301 /oracle/price/btc/usd/vwap;
    }
    location ~ ^/oracle/btcusd {
        return 301 /oracle/price/btc/usd;
    }
    location ~ ^/oracle/ethusd {
        return 301 /oracle/price/eth/usd;
    }
    location ~ ^/oracle/eurusd {
        return 301 /oracle/price/eur/usd;
    }
    location ~ ^/oracle/xauusd {
        return 301 /oracle/price/xau/usd;
    }
    location ~ ^/oracle/solusd {
        return 301 /oracle/price/sol/usd;
    }
    location ~ ^/oracle/btceur/vwap {
        return 301 /oracle/price/btc/eur/vwap;
    }
    location ~ ^/oracle/btceur {
        return 301 /oracle/price/btc/eur;
    }
    location ~ ^/oracle/etheur {
        return 301 /oracle/price/eth/eur;
    }
    location ~ ^/oracle/soleur {
        return 301 /oracle/price/sol/eur;
    }
    location ~ ^/oracle/xaueur {
        return 301 /oracle/price/xau/eur;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/myceliasignal-internal /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### Cloudflare Setup

1. Add domain to Cloudflare
2. A record: `api` → VM external IP, proxy enabled (orange cloud)
3. SSL/TLS mode: **Full**

---

## Step 7: Systemd Services

### price-service

```bash
sudo tee /etc/systemd/system/myceliasignal-price.service << 'EOF'
[Unit]
Description=Mycelia Signal Price Service
After=network.target

[Service]
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/myceliasignal/price-service
ExecStart=/home/YOUR_USER/myceliasignal/price-service/price-service
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### x402 proxy (also signing sidecar)

```bash
sudo tee /etc/systemd/system/myceliasignal-x402.service << 'EOF'
[Unit]
Description=Mycelia Signal x402 Proxy + Signing Sidecar
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/myceliasignal
ExecStart=/usr/bin/python3 /home/YOUR_USER/myceliasignal/x402_proxy.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### L402 proxy

```bash
sudo tee /etc/systemd/system/myceliasignal-l402.service << 'EOF'
[Unit]
Description=Mycelia Signal L402 Proxy
After=network.target myceliasignal-x402.service

[Service]
User=YOUR_USER
ExecStart=/home/YOUR_USER/myceliasignal/l402-proxy/l402-proxy
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

### econ services

```bash
for svc in econ-us econ-eu econ-commodities; do
sudo tee /etc/systemd/system/myceliasignal-${svc}.service << EOF
[Unit]
Description=Mycelia Signal ${svc}
After=network.target

[Service]
User=YOUR_USER
WorkingDirectory=/home/YOUR_USER/myceliasignal/${svc}
ExecStart=/home/YOUR_USER/myceliasignal/${svc}/${svc}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
done
```

### Enable and start all

```bash
sudo systemctl daemon-reload
for svc in myceliasignal-price myceliasignal-x402 myceliasignal-l402 \
           myceliasignal-econ-us myceliasignal-econ-eu myceliasignal-econ-commodities; do
    sudo systemctl enable $svc
    sudo systemctl start $svc
done
```

---

## Step 8: Verify

```bash
# Health check
curl https://api.myceliasignal.com/health

# Free preview — should return data immediately
curl https://api.myceliasignal.com/oracle/price/btc/usd/preview

# Paid endpoint — should return 402 with Lightning invoice
curl -i https://api.myceliasignal.com/oracle/price/btc/usd

# Discovery document
curl https://api.myceliasignal.com/.well-known/x402

# Full smoke test — all 57 preview endpoints
BASE="https://api.myceliasignal.com"
PASS=0; FAIL=0
for path in \
  oracle/price/btc/usd/preview oracle/price/btc/usd/vwap/preview \
  oracle/price/btc/eur/preview oracle/price/btc/eur/vwap/preview \
  oracle/price/btc/jpy/preview oracle/price/btc/jpy/vwap/preview \
  oracle/price/eth/usd/preview oracle/price/eth/eur/preview oracle/price/eth/jpy/preview \
  oracle/price/sol/usd/preview oracle/price/sol/eur/preview oracle/price/sol/jpy/preview \
  oracle/price/xrp/usd/preview oracle/price/ada/usd/preview oracle/price/doge/usd/preview \
  oracle/price/xau/usd/preview oracle/price/xau/eur/preview oracle/price/xau/jpy/preview \
  oracle/price/eur/usd/preview oracle/price/eur/jpy/preview oracle/price/eur/gbp/preview \
  oracle/price/eur/chf/preview oracle/price/eur/cny/preview oracle/price/eur/cad/preview \
  oracle/price/gbp/usd/preview oracle/price/gbp/jpy/preview oracle/price/gbp/chf/preview \
  oracle/price/gbp/cny/preview oracle/price/gbp/cad/preview \
  oracle/price/usd/jpy/preview oracle/price/usd/chf/preview \
  oracle/price/usd/cny/preview oracle/price/usd/cad/preview \
  oracle/price/chf/jpy/preview oracle/price/chf/cad/preview \
  oracle/price/cny/jpy/preview oracle/price/cny/cad/preview oracle/price/cad/jpy/preview \
  oracle/econ/us/cpi/preview oracle/econ/us/cpi_core/preview \
  oracle/econ/us/unrate/preview oracle/econ/us/nfp/preview \
  oracle/econ/us/fedfunds/preview oracle/econ/us/gdp/preview \
  oracle/econ/us/pce/preview oracle/econ/us/yield_curve/preview \
  oracle/econ/eu/hicp/preview oracle/econ/eu/hicp_core/preview \
  oracle/econ/eu/hicp_services/preview oracle/econ/eu/unrate/preview \
  oracle/econ/eu/gdp/preview oracle/econ/eu/employment/preview \
  oracle/econ/commodities/wti/preview oracle/econ/commodities/brent/preview \
  oracle/econ/commodities/natgas/preview oracle/econ/commodities/copper/preview \
  oracle/econ/commodities/dxy/preview; do
  status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/$path")
  if [ "$status" = "200" ]; then PASS=$((PASS+1))
  else FAIL=$((FAIL+1)); echo "FAIL $status $path"; fi
done
echo "PASSED: $PASS / FAILED: $FAIL"
```

Expected: `PASSED: 57 / FAILED: 0`

---

## Troubleshooting

| Problem | Fix |
|---|---|
| L402 proxy fails to start | Check macaroon path and LND endpoint in main.go |
| `NO_ROUTE` payment errors | Node needs inbound liquidity |
| price-service returns 500 | Exchange API down; check logs |
| Signing sidecar 500 | Check x402 proxy is running, key paths correct |
| Go TLS rejected by Cloudflare | Use direct IP for L402 calls (`http://IP:8080`) |
| x402 returns 503 | USDC depeg circuit breaker — check USDC/USD peg |
| Preview endpoints 404 | Check nginx config, l402-proxy routing |

## Adding a New Endpoint

1. Add the pair to `price-service/main.go` pair map and rebuild
2. Add the route to `l402-proxy/main.go` routes map and rebuild
3. Add the route to `x402_proxy.py` ROUTES dict
4. Reload nginx if path pattern is new
5. Test preview endpoint, then paid endpoint
