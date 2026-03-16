# Mycelia Signal — Sovereign Oracle

Pay sats. Pay USDC. Get signed data. Trust math, not middlemen.

Mycelia Signal is a sovereign price oracle serving cryptographically signed attestations over two payment protocols: Lightning (L402) and USDC on Base (x402). 56 endpoints across crypto pairs, FX rates, economic indicators, and commodities. No API keys. No accounts. No trust assumptions.

**Live API:** [api.myceliasignal.com](https://api.myceliasignal.com)  
**Docs:** [myceliasignal.com/docs](https://myceliasignal.com/docs)

---

## Try It Now

```bash
# Free preview — no payment required
curl https://api.myceliasignal.com/oracle/price/btc/usd/preview
curl https://api.myceliasignal.com/oracle/econ/us/cpi/preview

# Paid — get a 402 with Lightning invoice
curl -i https://api.myceliasignal.com/oracle/price/btc/usd

# Health check
curl https://api.myceliasignal.com/health
```

---

## Endpoints (56 total)

All endpoints available on both L402 (Lightning) and x402 (USDC on Base). Append `/preview` to any paid endpoint for free unsigned sample data.

### Crypto Pairs (15 endpoints)
| Endpoint | Description | Price |
|----------|-------------|-------|
| `/oracle/price/btc/usd` | BTC/USD spot — 9 exchanges | 10 sats / $0.01 |
| `/oracle/price/btc/usd/vwap` | BTC/USD 5-min VWAP | 20 sats / $0.02 |
| `/oracle/price/btc/eur` | BTC/EUR spot | 10 sats / $0.01 |
| `/oracle/price/btc/eur/vwap` | BTC/EUR VWAP | 20 sats / $0.02 |
| `/oracle/price/btc/jpy` | BTC/JPY spot | 10 sats / $0.01 |
| `/oracle/price/btc/jpy/vwap` | BTC/JPY VWAP | 20 sats / $0.02 |
| `/oracle/price/eth/usd` | ETH/USD spot | 10 sats / $0.01 |
| `/oracle/price/eth/eur` | ETH/EUR spot | 10 sats / $0.01 |
| `/oracle/price/eth/jpy` | ETH/JPY spot | 10 sats / $0.01 |
| `/oracle/price/sol/usd` | SOL/USD spot | 10 sats / $0.01 |
| `/oracle/price/sol/eur` | SOL/EUR spot | 10 sats / $0.01 |
| `/oracle/price/sol/jpy` | SOL/JPY spot | 10 sats / $0.01 |
| `/oracle/price/xrp/usd` | XRP/USD spot | 10 sats / $0.01 |
| `/oracle/price/ada/usd` | ADA/USD spot | 10 sats / $0.01 |
| `/oracle/price/doge/usd` | DOGE/USD spot | 10 sats / $0.01 |

### Precious Metals (3 endpoints)
| Endpoint | Description | Price |
|----------|-------------|-------|
| `/oracle/price/xau/usd` | Gold/USD — 8 sources | 10 sats / $0.01 |
| `/oracle/price/xau/eur` | Gold/EUR cross-rate | 10 sats / $0.01 |
| `/oracle/price/xau/jpy` | Gold/JPY cross-rate | 10 sats / $0.01 |

### FX Rates (19 endpoints)
EUR/USD, EUR/JPY, EUR/GBP, EUR/CHF, EUR/CNY, EUR/CAD, GBP/USD, GBP/JPY, GBP/CHF, GBP/CNY, GBP/CAD, USD/JPY, USD/CHF, USD/CNY, USD/CAD, CHF/JPY, CHF/CAD, CNY/JPY, CAD/JPY — all 10 sats / $0.01

### US Economic Indicators (8 endpoints)
| Endpoint | Description | Price |
|----------|-------------|-------|
| `/oracle/econ/us/cpi` | US CPI (BLS) | 1000 sats / $0.10 |
| `/oracle/econ/us/cpi_core` | US CPI Core | 1000 sats / $0.10 |
| `/oracle/econ/us/unrate` | Unemployment Rate | 1000 sats / $0.10 |
| `/oracle/econ/us/nfp` | Nonfarm Payrolls | 1000 sats / $0.10 |
| `/oracle/econ/us/fedfunds` | Fed Funds Rate | 1000 sats / $0.10 |
| `/oracle/econ/us/gdp` | GDP (BEA/FRED) | 1000 sats / $0.10 |
| `/oracle/econ/us/pce` | PCE Price Index | 1000 sats / $0.10 |
| `/oracle/econ/us/yield_curve` | 10Y-2Y Spread | 1000 sats / $0.10 |

### EU Economic Indicators (6 endpoints)
| Endpoint | Description | Price |
|----------|-------------|-------|
| `/oracle/econ/eu/hicp` | HICP Headline (Eurostat) | 1000 sats / $0.10 |
| `/oracle/econ/eu/hicp_core` | HICP Core | 1000 sats / $0.10 |
| `/oracle/econ/eu/hicp_services` | HICP Services | 1000 sats / $0.10 |
| `/oracle/econ/eu/unrate` | EU Unemployment | 1000 sats / $0.10 |
| `/oracle/econ/eu/gdp` | EU GDP | 1000 sats / $0.10 |
| `/oracle/econ/eu/employment` | EU Employment | 1000 sats / $0.10 |

### Commodities (5 endpoints)
| Endpoint | Description | Price |
|----------|-------------|-------|
| `/oracle/econ/commodities/wti` | WTI Crude (EIA/FRED) | 1000 sats / $0.10 |
| `/oracle/econ/commodities/brent` | Brent Crude | 1000 sats / $0.10 |
| `/oracle/econ/commodities/natgas` | Henry Hub NatGas | 1000 sats / $0.10 |
| `/oracle/econ/commodities/copper` | Copper (FRED) | 1000 sats / $0.10 |
| `/oracle/econ/commodities/dxy` | US Dollar Index | 1000 sats / $0.10 |

### Legacy Redirects
Old paths (`/oracle/btcusd`, `/sho/oracle/btcusd` etc.) redirect 301 permanently to new namespace.

---

## Architecture

### Stack (both GCs)
```
nginx (TLS termination via Cloudflare)
  ├── x402-proxy (Python, :8402) — USDC payments, Ed25519 signing, /internal/sign/* sidecar
  ├── l402-proxy (Go, :8080) — Lightning payments via Voltage node
  ├── price-service (Go, :9200) — 37 price pairs, multi-exchange aggregation
  ├── econ-us (Go, :9129) — 8 US indicators (BLS/FRED)
  ├── econ-eu (Go, :9130) — 6 EU indicators (Eurostat)
  └── econ-commodities (Go, :9134) — 5 commodities (EIA/FRED)
```

### Payment Rails
- **L402 (Lightning):** Client gets 402 with Lightning invoice + macaroon. Pays invoice, retries with `Authorization: L402 <macaroon>:<preimage>`. Response signed with secp256k1 ECDSA.
- **x402 (USDC on Base):** Client gets 402 with USDC payment details. Signs EIP-3009 transfer, retries with `X-Payment` header. Response signed with Ed25519.

### Signing Architecture
L402 and x402 use separate per-instance keypairs. The x402 proxy acts as a signing sidecar for both rails — L402 Go proxy routes paid requests through `/internal/sign/*` after payment verification.

| Rail | Scheme | Key Format |
|------|--------|------------|
| L402 | secp256k1 ECDSA | 33-byte compressed hex |
| x402 | Ed25519 | 32-byte hex |

### Canonical Response Format
Every signed response contains:
```json
{
  "canonical": "v1|PRICE|BTCUSD|84231.50|USD|2|binance,...|median|1741514400|482910",
  "signature": "<base64-encoded>",
  "pubkey": "<hex-pubkey>",
  "signing_scheme": "secp256k1_ecdsa"
}
```

Canonical format: `VERSION|TYPE|<payload>|TIMESTAMP|NONCE`

See [Canonical Format docs](https://myceliasignal.com/docs/canonical-format) for full specification.

---

## Infrastructure

### GC Nodes
| | US GC | Asia GC |
|-|-------|---------|
| Provider | GCP us-central1-a | GCP asia-east1-b |
| IP | 104.197.109.246 | 34.80.169.18 |
| secp256k1 pubkey | `03c1955b8c...` | `02b1377c30...` |

### Monitoring
- Grafana + Prometheus on US GC (permanent)
- Asia Prometheus federates to US Prometheus
- Blackbox Exporter for public endpoint probing
- Uptime Robot monitoring `https://api.myceliasignal.com/health`

---

## Verification

### L402 (secp256k1 ECDSA) — Python
```python
import hashlib, base64
from coincurve import PublicKey

def verify(response):
    msg_hash = hashlib.sha256(response["canonical"].encode()).digest()
    pubkey = PublicKey(bytes.fromhex(response["pubkey"]))
    return pubkey.verify(base64.b64decode(response["signature"]), msg_hash, hasher=None)
```

### x402 (Ed25519) — Python
```python
import hashlib, base64
from nacl.signing import VerifyKey
from nacl.encoding import RawEncoder

def verify(response):
    msg_hash = hashlib.sha256(response["canonical"].encode()).digest()
    vk = VerifyKey(bytes.fromhex(response["pubkey"]), encoder=RawEncoder)
    try:
        vk.verify(msg_hash, base64.b64decode(response["signature"]))
        return True
    except Exception:
        return False
```

Full verification guide: [myceliasignal.com/docs/verification](https://myceliasignal.com/docs/verification)

---

## Integrations

- **ElizaOS plugin:** `@jonathanbulkeley/plugin-mycelia-signal` — [npm](https://www.npmjs.com/package/@jonathanbulkeley/plugin-mycelia-signal)
- **LangChain plugin:** `langchain-mycelia-signal` — coming soon
- **MCP server:** Claude Desktop integration — coming soon
- **Satring:** L402 directory listing — [satring.com](https://satring.com)

---

## Links

- **Website:** [myceliasignal.com](https://myceliasignal.com)
- **Docs:** [myceliasignal.com/docs](https://myceliasignal.com/docs)
- **API:** [api.myceliasignal.com](https://api.myceliasignal.com)
- **x402 discovery:** [api.myceliasignal.com/.well-known/x402](https://api.myceliasignal.com/.well-known/x402)

---

## License

MIT
