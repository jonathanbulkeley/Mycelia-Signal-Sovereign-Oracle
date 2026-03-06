# Sovereign Lightning Oracle (SLO) + Sovereign HTTP Oracle (SHO)

Pay sats. Pay USDC. Get signed data. Trust math, not middlemen.

SLO is a protocol for purchasing signed, verifiable data assertions over Lightning micropayments. SHO extends the same oracle to the x402 (HTTP 402) payment protocol, accepting USDC on Base. No API keys. No accounts. No trust. Just payment and proof.

BTCUSD, ETHUSD, EURUSD, XAU/USD (gold), BTC/EUR, SOL/USD, ETH/EUR, SOL/EUR, XAU/EUR, and BTC/EUR VWAP are live on Bitcoin mainnet via L402 Lightning payments — and on Base via x402 USDC payments. The oracle includes the first production DLC oracle with L402 payment gating. The EUR/USD oracle aggregates rates from 6 central banks across 4 continents plus 2 live exchanges. The DLC attestor publishes hourly Schnorr-signed price attestations for non-custodial Bitcoin-native derivatives. The design generalizes to any metric where truth is contested and verification matters.

## Try It Now

### Live (mainnet — any Lightning wallet)
```bash
curl -v https://api.myceliasignal.com/oracle/btcusd
curl -v https://api.myceliasignal.com/oracle/ethusd
curl -v https://api.myceliasignal.com/oracle/eurusd
curl -v https://api.myceliasignal.com/oracle/solusd
curl -v https://api.myceliasignal.com/oracle/etheur
curl -v https://api.myceliasignal.com/oracle/xaueur
```

You'll get a 402 Payment Required with a Lightning invoice. Pay it with any Lightning wallet, get a cryptographically signed price sourced from major exchanges and central banks.

### L402-gated endpoints (pay per query)

| Endpoint | Asset | Method | Price | Sources |
|---|---|---|---|---|
| `/oracle/btcusd` | BTC/USD | Spot median | 10 sats | 9 sources: Coinbase, Kraken, Bitstamp, Gemini, Bitfinex, Binance, Binance US, OKX, Gate.io |
| `/oracle/btcusd/vwap` | BTC/USD | Volume-weighted average | 20 sats | 7 sources: Coinbase, Kraken, Bitstamp, Gemini, Bitfinex, OKX, Gate.io (5-min window) |
| `/oracle/ethusd` | ETH/USD | Spot median | 10 sats | Coinbase, Kraken, Bitstamp, Gemini, Bitfinex |
| `/oracle/eurusd` | EUR/USD | Spot median | 10 sats | 8 sources: ECB, ECB Direct, Bank of Canada, RBA, Norges Bank, Czech National Bank, Kraken, Bitstamp |
| `/oracle/btceur` | BTC/EUR | Cross-rate | 10 sats | Derived from BTCUSD (9 sources) / EURUSD (8 sources) |
| `/oracle/xauusd` | XAU/USD | Spot median | 10 sats | 8 sources: Kitco, JM Bullion, GoldBroker, Coinbase, Kraken, Gemini, Binance, OKX |
| `/oracle/solusd` | SOL/USD | Spot median | 10 sats | 9 sources: Coinbase, Kraken, Bitstamp, Gemini, Bitfinex, Binance, OKX, Gate.io, Bybit |
| `/oracle/etheur` | ETH/EUR | Hybrid spot | 10 sats | 4 sources: Coinbase, Kraken, Bitstamp (direct EUR) + cross-rate |
| `/oracle/soleur` | SOL/EUR | Hybrid spot | 10 sats | 4 sources: Coinbase, Kraken, Bitstamp (direct EUR) + cross-rate |
| `/oracle/xaueur` | XAU/EUR | Cross-rate | 10 sats | Derived from XAUUSD / EURUSD |
| `/oracle/btceur/vwap` | BTC/EUR | VWAP cross-rate | 20 sats | Derived from BTCUSD VWAP (7 sources) / EURUSD (8 sources) |
| `/dlc/oracle/attestations/{id}` | BTC/USD | Schnorr attestation | 1000 sats | 9 sources (same as BTCUSD spot) |

The VWAP oracle costs more because it processes full trade history rather than a single last-trade price — more computation, more data, more signal. The DLC attestation costs 1000 sats because it settles real financial contracts.

### Free endpoints (no payment required)

| Endpoint | Description |
|---|---|
| `https://api.myceliasignal.com/health` | L402 proxy health check |
| `https://api.myceliasignal.com/health` | x402 proxy health check |
| `https://api.myceliasignal.com/sho/info` | x402 oracle info (pubkey, endpoints, pricing) |
| `https://api.myceliasignal.com/dlc/oracle/pubkey` | Oracle's persistent Schnorr public key |
| `https://api.myceliasignal.com/dlc/oracle/announcements` | List upcoming events with nonce commitments |
| `https://api.myceliasignal.com/dlc/oracle/status` | DLC oracle status and statistics |

Announcements are free to encourage adoption — the more contracts built against SLO, the more attestation revenue.

> ⚡ **Status: Beta** — Live on Bitcoin mainnet. Endpoints may go down for maintenance.

## SHO — x402 Payment Protocol (USDC on Base)

SHO delivers the same oracle data over the x402 payment protocol. Instead of Lightning sats, consumers pay with USDC on Base. Attestations are signed with Ed25519 instead of secp256k1 — same canonical message, different signature scheme.

### Try It Now (x402)
```bash
# Get oracle info (free)
curl https://api.myceliasignal.com/sho/info

# Request price data — returns 402 with USDC payment requirements
curl https://api.myceliasignal.com/oracle/btcusd
```

### x402-gated endpoints (pay per query in USDC)

| Endpoint | Asset | Price (USDC) | Sources |
|---|---|---|---|
| `/oracle/btcusd` | BTC/USD | $0.001 | 9 sources |
| `/oracle/btcusd/vwap` | BTC/USD | $0.002 | 7 sources (5-min window) |
| `/oracle/ethusd` | ETH/USD | $0.001 | 5 sources |
| `/oracle/eurusd` | EUR/USD | $0.001 | 8 sources |
| `/oracle/xauusd` | XAU/USD | $0.001 | 8 sources |
| `/oracle/btceur` | BTC/EUR | $0.001 | 17 sources |
| `/oracle/solusd` | SOL/USD | $0.001 | 9 sources |
| `/oracle/etheur` | ETH/EUR | $0.001 | 4 sources (3 direct + cross-rate) |
| `/oracle/soleur` | SOL/EUR | $0.001 | 4 sources (3 direct + cross-rate) |
| `/oracle/xaueur` | XAU/EUR | $0.001 | Derived from XAUUSD / EURUSD |
| `/oracle/btceur/vwap` | BTC/EUR | $0.002 | VWAP cross-rate (7 + 8 sources) |

### x402 Flow

1. Consumer requests price data (e.g., `GET /oracle/btcusd`) → oracle returns HTTP 402 with standard x402 `accepts` array
2. Consumer signs EIP-3009 transferWithAuthorization (EIP-712 — gasless, no on-chain tx)
3. Consumer sends base64-encoded PaymentPayload as X-PAYMENT header
4. Proxy verifies signature and settles payment via CDP facilitator
5. Oracle returns Ed25519-signed attestation

### x402 Response Format
```json
{
  "domain": "BTCUSD",
  "canonical": "v1|BTCUSD|64179.76|USD|2|2026-02-24T17:48:21Z|482910|binance,...|median",
  "signature": "3yYxQATXEqFgwjzG+CLmzLdlSBODbQc03q2xnu49KU0t...",
  "signing_scheme": "ed25519",
  "pubkey": "c40ad8cbd866189eecb7c68091a984644fb7736ef3b8d96cd31b600ef0072623",
  "payment": {
    "protocol": "x402",
    "tx_hash": "0x5237...",
    "confirmed": true
  }
}
```

### Oracle Identity

Both L402 and x402 delivery use the same oracle core — same sources, same aggregation, same canonical message format. Only the signature and delivery differ:

| Protocol | Port | Signing | Payment |
|---|---|---|---|
| L402 (SLO) | 8080 | ECDSA secp256k1 | Lightning sats |
| x402 (SHO) | 8402 | Ed25519 | USDC on Base |

### Safety Features

- **Depeg circuit breaker:** If USDC deviates >2% from USD parity (median of 5 sources: Kraken, Bitstamp, Coinbase (USDT-USDC), Gemini, Bitfinex; minimum 2 required), x402 payment acceptance is automatically suspended
- **Tiered enforcement:** Failed payments trigger a 10-minute grace cooldown (Tier 1); 10+ failures in 7 days trigger a hard block (Tier 3)
- **Replay protection:** Single-use request nonces prevent payment replay attacks
- **Optimistic delivery:** Attestations returned before on-chain confirmation; failed payments tracked asynchronously

### Local demo (no Lightning node needed)

Clone this repo and run the Polar Setup Guide to simulate the full L402 flow on your machine in ~30 minutes. No real bitcoin required.

## Why SLO?

Oracles today are broken. Most price feeds are free — which means you're not the customer, you're the product. Free oracles create hidden dependencies: opaque update schedules, silent failures, governance capture, and single points of trust that defeat the purpose of building on Bitcoin.

SLO takes a different approach:

**Payment replaces trust.** Every query costs sats. Every response is signed. If the data is wrong, stop paying. The market decides which oracles survive. **No accounts, no API keys.** A Lightning payment is your authentication. Any machine with a wallet can buy data — humans, bots, smart contracts, AI agents. **Multiple oracles, client aggregation.** You choose which oracles to query. You aggregate the results. No single oracle can lie to you without detection.

**Cryptographic proof at every layer.** Signed assertions (secp256k1/Schnorr) mean you can verify data independently, store it, forward it, or submit it on-chain — all without trusting the transport. **Censorship resistant.** No platform can revoke your access. If you can reach the endpoint and pay the invoice, you get the data. No terms of service, no rate limits, no deplatforming. **Aligned incentives.** Oracle operators earn sats per query. More accurate data attracts more paying clients. Bad data means lost revenue. The economic feedback loop enforces quality without governance.

## How It Works
```
Client                       L402 Proxy                      Oracle (FastAPI)
  │                                │                              │
  │  GET /oracle/btcusd            │                              │
  │ ─────────────────────────────► │                              │
  │                                │                              │
  │  402 + Lightning invoice       │  (creates invoice via LND    │
  │ ◄───────────────────────────── │   REST API)                  │
  │                                │                              │
  │  ⚡ Pay invoice (10 sats)      │                              │
  │ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─► │                              │
  │                                │                              │
  │  Retry with L402 token         │                              │
  │ ─────────────────────────────► │  GET /oracle/btcusd          │
  │                                │ ───────────────────────────► │
  │                                │                              │
  │                                │  Signed price assertion      │
  │                                │ ◄─────────────────────────── │
  │  { canonical, signature,       │                              │
  │    pubkey }                    │                              │
  │ ◄───────────────────────────── │                              │
```

1. Client requests price data
2. L402 proxy returns HTTP 402 with a Lightning invoice (created via LND REST API)
3. Client pays the invoice (any Lightning wallet or L402 client like `lnget`)
4. Client retries with proof of payment (L402 token with macaroon + preimage)
5. L402 proxy verifies the macaroon and proxies to the oracle backend
6. Oracle returns a signed price assertion

## Response Formats

### L402 Oracle Response (ECDSA)
```json
{
  "domain": "BTCUSD",
  "canonical": "v1|BTCUSD|69005.00|USD|2|2026-02-15T17:55:46Z|482910|binance,binance_us,bitfinex,bitstamp,coinbase,gateio,gemini,kraken,okx|median",
  "signature": "Fc9m9prAixo1DeZh1xNwkzSXD0zLw6BNlTutaBj/03F7...",
  "pubkey": "02b9b8ec862ee9ca1ab6293f67c473b327a45ed0988d..."
}
```

The `canonical` field is the signed message. The `signature` is a secp256k1 ECDSA signature over `SHA256(canonical)`. Any client can verify the signature using the `pubkey`.

### DLC Attestation Response (Schnorr)
```json
{
  "event_id": "BTCUSD-2026-02-15T17:00:00Z",
  "pair": "BTCUSD",
  "maturity": "2026-02-15T17:00:00Z",
  "oracle_pubkey": "03ec3f43aa21878c55c2838fbf54aa2408d25abdcacd4cef6f32c48f3a53eda843",
  "price": 69005,
  "price_digits": [6, 9, 0, 0, 5],
  "s_values": ["801e97...", "a1d83e...", "4a7406...", "f4f672...", "d461cd..."],
  "attested_at": "2026-02-15T16:50:56Z"
}
```

Five Schnorr s-values, one per digit. Verifiable against the R-points published in the announcement. DLC clients use these to settle contracts without trusting the oracle at execution time.

## DLC Oracle

SLO includes a fully functional DLC (Discreet Log Contract) oracle for non-custodial Bitcoin-native derivatives. No production-grade DLC oracle existed on Bitcoin mainnet before SLO.

### How DLC attestations work

1. **Announcement (free):** Oracle pre-publishes nonce commitments (R-points) for the next 24 hours of hourly price events
2. **Contract setup:** Two parties build CETs (Contract Execution Transactions) using the R-points, locking bitcoin in a 2-of-2 multisig
3. **Attestation (1000 sats via L402):** At maturity, oracle fetches the BTCUSD price from 9 sources and publishes Schnorr s-values decomposed into 5 digits
4. **Settlement:** The winning party combines the s-values with their adaptor signature to claim funds — no oracle involvement required

### Oracle identity
```
Pubkey:   03ec3f43aa21878c55c2838fbf54aa2408d25abdcacd4cef6f32c48f3a53eda843
Format:   Compressed secp256k1 (33 bytes)
Digits:   5 (covers $10,000–$99,999)
Schedule: Hourly attestations, 24h rolling announcements
```

### Verification

For each digit `i` with value `d`, verify:
```
e = SHA256("{event_id}/{i}/{d}")
s*G == R + e*P
```

Where `R` is the nonce commitment from the announcement and `P` is the oracle pubkey.

## BTCUSD 9-Source Feed

The BTCUSD spot oracle and DLC attestor share the same price feed (`oracle/feeds/btcusd.py`), aggregating from 9 exchanges:

**Tier 1 — USD pairs:** Coinbase, Kraken, Bitstamp, Gemini, Bitfinex, Binance US

**Tier 2 — USDT pairs** (normalized to USD via live USDT/USD rate): Binance, OKX, Gate.io

The USDT/USD rate is sourced from Kraken and Bitstamp (median). If the USD median and USDT median diverge by more than 0.5%, USDT sources are dropped automatically. Minimum 6 of 9 sources required for a valid price.

## Source Thresholds and Safety Mechanisms

Each pair requires a minimum number of sources to produce a valid attestation. If the threshold is not met, the endpoint returns an error rather than serving unreliable data.

| Pair | Total Sources | Minimum Required | Adaptive Condition |
|---|---|---|---|
| BTC/USD Spot | 9 | 6 | Drops to 4 if USDT sources excluded (>0.5% USD/USDT divergence) |
| BTC/USD VWAP | 7 | 4 | Drops to 3 if USDT sources excluded |
| ETH/USD | 5 | 3 | — |
| EUR/USD | 8 | 4 | — |
| XAU/USD | 8 | 3 | Drops to 2 if PAXG-derived sources excluded |
| SOL/USD | 9 | 5 | Drops to 3 if USDT sources excluded |
| ETH/EUR | 4 | 2 | — |
| SOL/EUR | 4 | 2 | — |
| BTC/EUR | 17 (composite) | Inherited | Fails if BTC/USD (min 6) or EUR/USD (min 4) fails |
| XAU/EUR | Combined | Inherited | Fails if XAU/USD (min 3) or EUR/USD (min 4) fails |
| BTC/EUR VWAP | Combined | Inherited | Fails if BTC/USD VWAP (min 4) or EUR/USD (min 4) fails |

### USDT Normalization

BTC/USD, BTC/USD VWAP, and SOL/USD include USDT-denominated sources (Binance, OKX, Gate.io) that are normalized to USD using a live USDT/USD rate from Kraken and Bitstamp. If the USD and USDT medians diverge by more than 0.5%, USDT sources are automatically dropped and the minimum threshold is reduced.

### XAU/USD Source Composition

XAU/USD aggregates from 3 bullion dealers (Kitco, JM Bullion, GoldBroker) and 5 crypto exchanges trading PAXG (Coinbase, Kraken, Gemini, Binance, OKX). If PAXG sources are excluded, the minimum threshold drops from 3 to 2.

## Repository Structure
```
slo/
├── oracle/
│   ├── feeds/
│   │   ├── __init__.py
│   │   ├── btcusd.py                  # 9-source BTCUSD feed with USDT normalization
│   │   ├── ethusd.py                  # 5-source ETH feed
│   │   ├── eurusd.py                  # 8-source EUR/USD feed (6 central banks + 2 exchanges)
│   │   ├── btcusd_vwap.py             # 7-source VWAP feed (5-min window, USDT normalization)
│   │   ├── xauusd.py                  # 8-source XAU/USD feed (traditional + PAXG)
│   │   ├── btceur.py                  # BTC/EUR cross-rate derivation
│   │   ├── solusd.py                  # 9-source SOL/USD feed with USDT normalization
│   │   ├── etheur.py                  # 4-source ETH/EUR hybrid (3 direct + cross-rate)
│   │   ├── soleur.py                  # 4-source SOL/EUR hybrid (3 direct + cross-rate)
│   │   ├── xaueur.py                  # XAU/EUR cross-rate (XAUUSD / EURUSD)
│   │   └── btceur_vwap.py             # BTC/EUR VWAP cross-rate
│   ├── liveoracle_btcusd_spot.py      # BTC spot oracle (10 sats, 9 sources)
│   ├── liveoracle_btcusd_vwap.py      # BTC VWAP oracle (20 sats, 7 sources)
│   ├── liveoracle_ethusd_spot.py      # ETH spot oracle (10 sats, 5 sources)
│   ├── liveoracle_eurusd_spot.py      # EUR/USD oracle (10 sats, 8 sources)
│   ├── liveoracle_xauusd_spot.py      # Gold spot oracle (10 sats, 8 sources)
│   ├── liveoracle_btceur_spot.py      # BTC/EUR cross-rate oracle (10 sats, 16 sources)
│   └── liveoracle_solusd_spot.py      # SOL/USD spot oracle (10 sats, 9 sources)
│   ├── liveoracle_etheur_spot.py      # ETH/EUR hybrid oracle (10 sats, 4 sources)
│   ├── liveoracle_soleur_spot.py      # SOL/EUR hybrid oracle (10 sats, 4 sources)
│   ├── liveoracle_xaueur_spot.py      # XAU/EUR cross-rate oracle (10 sats)
│   └── liveoracle_btceur_vwap.py      # BTC/EUR VWAP oracle (20 sats)
├── dlc/
│   ├── __init__.py
│   ├── attestor.py                    # Schnorr nonce commitment & attestation
│   ├── server.py                      # DLC API server (FastAPI, port 9104)
│   └── scheduler.py                   # Hourly attestation loop
├── sho/
│   ├── __init__.py
│   ├── x402_proxy.py                  # x402 payment proxy (USDC on Base, Ed25519 signing)
│   ├── cross_certify.py               # Cross-certification tool (secp256k1 ↔ Ed25519)
│   ├── test_client.py                 # End-to-end x402 test client
│   ├── requirements.txt               # SHO-specific dependencies
│   └── keys/                          # Ed25519 signing key (gitignored)
├── l402-proxy/
│   ├── main.go                        # L402 payment proxy (Go, uses LND REST API)
│   ├── go.mod                         # Go module dependencies
│   └── go.sum
├── mcp/
│   └── slo_mcp_server.py             # MCP server for AI agents
├── client/
│   └── quorum_client_l402.py          # L402-aware quorum client
├── config/
│   └── aperture.yaml                  # Legacy Aperture config (reference only)
├── docs/
│   ├── POLAR_SETUP.md                 # Local demo guide (Polar + regtest)
│   ├── DEPLOYMENT.md                  # Production deployment guide
│   ├── DEMO.md                        # Live demo walkthrough
│   ├── CLIENT_INTEGRATION.md          # Python, JS, Go integration guide
│   ├── OPERATOR_GUIDE.md              # How to run your own oracle
│   ├── Protocol.md                    # Canonical protocol specification
│   └── Quorum_Specification.md        # Client quorum and aggregation rules
├── legacy/                            # Original oracles with simulated payments
├── .gitignore
├── LICENSE
└── README.md
```

## Infrastructure

### Domain & TLS

All endpoints are served via `api.myceliasignal.com` with Cloudflare TLS termination. Cloudflare proxies HTTPS traffic to an nginx reverse proxy on the VM, which routes to the appropriate backend:

```
Internet → Cloudflare (HTTPS) → nginx (:80) → L402 proxy (:8080)
                                            → x402 proxy (:8402)
                                            → DLC server (:9104)
```

nginx routes:
- `/oracle/*` and `/health` → x402 proxy (port 8402)
- `/sho/*` → x402 proxy (port 8402), with `/sho/` prefix stripped
- `/dlc/*` → L402 proxy (port 8080)

### Known Issue: Go TLS + Cloudflare

Go's default TLS ClientHello is fingerprinted and rejected by Cloudflare's bot protection. This affects `lnget` and any Go HTTP client hitting `https://api.myceliasignal.com`. Python `urllib` and `curl` work fine through Cloudflare.

**Workaround for MCP server / lnget users:** The MCP server uses the VM's direct IP for L402 calls (bypassing Cloudflare) while using the HTTPS domain for free endpoints via Python urllib. If you're building a Go client, either use the direct IP or configure a TLS fingerprint that Cloudflare accepts.

## Protocol (v1)

### Canonical Message
```
v1|<PAIR>|<price>|USD|<decimals>|<timestamp>|<nonce>|<sources>|<method>
```

### Core Invariants

1. **Payment before release** — No signed data without Lightning payment (enforced by L402 proxy)
2. **Explicit trust** — Clients choose which oracles to query (no registry, no governance)
3. **Deterministic verification** — Every response is signed (secp256k1/Schnorr) and verifiable
4. **Deterministic aggregation** — Clients aggregate via median across multiple oracles

### What SLO Is Not

- Not a price feed (you pay per query, not per subscription)
- Not a global oracle registry
- Not a governance system
- Not a consensus protocol

SLO does not decide which oracle is correct. That responsibility belongs to the client.

## Architecture

The oracle uses a shared core with dual delivery layers:

- **Oracle servers** — Stateless FastAPI services that fetch prices, sign assertions (secp256k1), and return JSON. One per trading pair, each on its own port (9100–9111).
- **L402 Proxy (SLO)** — Lightweight Go reverse proxy on port 8080. Creates Lightning invoices via LND REST API, mints L402 macaroons, verifies payment tokens, proxies to oracle backends.
- **x402 Proxy (SHO)** — Python FastAPI proxy on port 8402. Verifies USDC payments on Base, re-signs attestations with Ed25519, handles optimistic delivery, depeg circuit breaker, and tiered enforcement.
- **nginx** — Reverse proxy on port 80. Routes `/oracle/*` to L402, `/sho/*` to x402 (stripping prefix), `/dlc/*` to L402. Sits behind Cloudflare.
- **LND Node** — Voltage-hosted Lightning node (mainnet) for L402 invoice creation and payment settlement
- **DLC attestor** — Scheduled Schnorr signing service with persistent oracle key and hourly attestation loop

The oracle servers contain zero payment logic. Both proxies enforce "payment before data" at the proxy layer, routing to the same backends.

## For AI Agents

SLO is designed to be consumed by machines. The L402 protocol lets AI agents pay for data programmatically — no API keys, no OAuth, no accounts. An agent with a Lightning wallet can:
```bash
lnget -k -q https://api.myceliasignal.com/oracle/btcusd
lnget -k -q https://api.myceliasignal.com/oracle/ethusd
lnget -k -q https://api.myceliasignal.com/oracle/eurusd
lnget -k -q https://api.myceliasignal.com/oracle/solusd
lnget -k -q https://api.myceliasignal.com/oracle/etheur
lnget -k -q https://api.myceliasignal.com/oracle/soleur
lnget -k -q https://api.myceliasignal.com/oracle/xaueur
```

10 sats spent, signed price received, cryptographically verified. This is what machine-payable data looks like.

### MCP Server (Claude Desktop / Cursor)

SLO includes an MCP (Model Context Protocol) server that lets AI assistants like Claude buy signed price data automatically.

**Setup:**

1. Install dependencies: `pip install fastmcp ecdsa pynacl`
2. Ensure `lnget` is installed and configured with a Lightning wallet
3. Add to your Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "slo": {
      "command": "python",
      "args": ["/absolute/path/to/mcp/slo_mcp_server.py"]
    }
  }
}
```

4. Restart Claude Desktop and ask: "What's the current Bitcoin price?" or "What's the EUR/USD rate?"

Claude will pay sats over Lightning and return a cryptographically signed price. No API key. No configuration beyond a Lightning wallet.

**Note:** The MCP server uses the VM's direct IP for L402 calls to work around a Cloudflare/Go TLS compatibility issue. See the Infrastructure section for details.

**Available MCP Tools:**

| Tool | Protocol | Cost | Description |
|---|---|---|---|
| `get_btcusd_spot` | L402 | 10 sats | Median BTC spot price from 9 sources |
| `get_btcusd_vwap` | L402 | 20 sats | Volume-weighted average from 7 sources (5-min window) |
| `get_ethusd_spot` | L402 | 10 sats | Median ETH spot price from 5 exchanges |
| `get_eurusd_spot` | L402 | 10 sats | Median EUR/USD from 6 central banks + 2 exchanges |
| `get_xauusd_spot` | L402 | 10 sats | Median gold price from 8 sources |
| `get_btceur_spot` | L402 | 10 sats | BTC/EUR cross-rate derived from BTCUSD + EURUSD |
| `get_solusd_spot` | L402 | 10 sats | Median SOL spot price from 9 sources |
| `get_etheur_spot` | L402 | 10 sats | ETH/EUR hybrid from 3 direct pairs + cross-rate |
| `get_soleur_spot` | L402 | 10 sats | SOL/EUR hybrid from 3 direct pairs + cross-rate |
| `get_xaueur_spot` | L402 | 10 sats | XAU/EUR cross-rate from XAUUSD / EURUSD |
| `get_btceur_vwap` | L402 | 20 sats | BTC/EUR VWAP cross-rate |
| `sho_get_info` | Free | — | x402 oracle info and endpoint listing |
| `sho_get_health` | Free | — | x402 proxy health check |
| `sho_get_btcusd_spot` | x402 | $0.001 | BTC/USD via x402 (returns payment instructions) |
| `sho_get_btcusd_vwap` | x402 | $0.002 | BTC/USD VWAP via x402 (7 sources) |
| `sho_get_ethusd_spot` | x402 | $0.001 | ETH/USD via x402 |
| `sho_get_eurusd_spot` | x402 | $0.001 | EUR/USD via x402 (8 sources) |
| `sho_get_xauusd_spot` | x402 | $0.001 | XAU/USD via x402 |
| `sho_get_btceur_spot` | x402 | $0.001 | BTC/EUR via x402 |
| `sho_get_solusd_spot` | x402 | $0.001 | SOL/USD via x402 |
| `sho_get_etheur_spot` | x402 | $0.001 | ETH/EUR via x402 |
| `sho_get_soleur_spot` | x402 | $0.001 | SOL/EUR via x402 |
| `sho_get_xaueur_spot` | x402 | $0.001 | XAU/EUR via x402 |
| `sho_get_btceur_vwap` | x402 | $0.002 | BTC/EUR VWAP via x402 |
| `get_dlc_pubkey` | Free | — | DLC oracle public key |
| `get_dlc_status` | Free | — | DLC oracle status and stats |
| `get_dlc_announcements` | Free | — | Upcoming DLC event announcements |
| `get_dlc_attestation` | L402 | 1000 sats | Specific DLC attestation by event ID |

## Roadmap

- [x] BTCUSD spot oracle (median, 9 sources)
- [x] BTCUSD VWAP oracle
- [x] ETHUSD spot oracle (5 sources)
- [x] EURUSD spot oracle (8 sources, 6 central banks, 4 continents)
- [x] L402 payment gating
- [x] Mainnet deployment
- [x] MCP server for AI agents
- [x] DLC oracle with Schnorr attestations (hourly, 5-digit decomposition, 1000 sats)
- [x] 9-source BTCUSD feed with USDT normalization
- [x] XAU/USD gold oracle (8 sources: Kitco, JM Bullion, GoldBroker + 5 PAXG exchanges)
- [x] BTC/EUR cross-rate oracle (derived from BTCUSD + EURUSD, 16 sources)
- [x] SOL/USD spot oracle (9 sources: 5 USD + 4 USDT with normalization)
- [x] ETH/EUR hybrid oracle (3 direct EUR pairs + cross-rate)
- [x] SOL/EUR hybrid oracle (3 direct EUR pairs + cross-rate)
- [x] XAU/EUR cross-rate oracle
- [x] BTC/EUR VWAP cross-rate oracle
- [x] BTCUSD VWAP expanded to 7 sources with 5-min window and USDT normalization
- [x] EUR/USD expanded to 8 sources (added ECB Direct)
- [x] **SHO x402 proxy — USDC payments on Base, Ed25519 signing, optimistic delivery**
- [x] **Depeg circuit breaker (USDC/USD peg monitoring, 5 sources with median)**
- [x] **Tiered enforcement for failed payments (grace cooldown + hard block)**
- [x] **Domain name + TLS** (api.myceliasignal.com via Cloudflare)
- [ ] Cross-certification statement (secp256k1 ↔ Ed25519)
- [ ] x402 session tokens (prepaid balances for high-frequency consumers)
- [ ] x402 client SDK (auto-payment integration for MCP and programmatic consumers)
- [ ] Commodity oracles (oil)
- [ ] Interest rate oracles (Fed funds, SOFR)
- [ ] Multi-operator federation

## Design Philosophy

SLO favors:

- explicit failure over hidden retries
- local configuration over global coordination
- payment over access control
- plural oracles over singular truth

## Quick Start (Legacy — Simulated Payments)

No Lightning node required:
```bash
pip install fastapi uvicorn ecdsa requests

# Terminal 1-2: Start oracles
python legacy/liveoracle_btcusd_spot.py 8000
python legacy/liveoracle_btcusd_vwap.py 8002

# Terminal 3: Run quorum client
python legacy/quorum_client.py
```

## License

MIT — see [LICENSE](LICENSE)
