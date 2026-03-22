# Mycelia Signal Protocol Specification (v1)

## Purpose

Mycelia Signal defines a protocol for purchasing signed data attestations over HTTP, gated by micropayments via L402 (Lightning) or x402 (USDC on Base). The protocol specifies a canonical message format, two signing schemes, and two payment mechanisms. Source selection, aggregation, and trust are the client's responsibility.

## Canonical Message Format

Every oracle response contains a canonical string that is the sole input to the signing function. The format varies by data type.

### PRICE type (crypto pairs, FX, precious metals)

```
v1|PRICE|PAIR|VALUE|CURRENCY|DECIMALS|SOURCES|METHOD|TIMESTAMP|NONCE
```

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| version | string | Protocol version | `v1` |
| type | string | Message type | `PRICE` |
| pair | string | Asset pair (no separator) | `BTCUSD` |
| value | string | Price (exact decimal string) | `84231.50` |
| currency | string | Quote currency | `USD` |
| decimals | integer | Decimal places | `2` |
| sources | string | Comma-separated, lowercase | `binance,coinbase,kraken` |
| method | string | Aggregation method | `median` or `vwap` |
| timestamp | integer | Unix timestamp (UTC) | `1741514400` |
| nonce | integer | Random per-request integer | `482910` |

**Example:**
```
v1|PRICE|BTCUSD|84231.50|USD|2|binance,bitstamp,coinbase,kraken,okx|median|1741514400|482910
```

### ECON types (economic indicators and commodities)

```
v1|ECON|REGION|INDICATOR|VALUE|UNIT|PERIOD|VINTAGEDATE|SOURCEAGENCY|SERIESID|SOURCEMODEL|TIMESTAMP|NONCE
```

| Field | Description | Example |
|-------|-------------|---------|
| version | Protocol version | `v1` |
| type | Always `ECON` | `ECON` |
| region | `US`, `EU`, or `COMMODITIES` | `US` |
| indicator | Indicator code | `CPI` |
| value | Decimal string | `326.785` |
| unit | Unit of measure | `index198284100` |
| period | Reference period | `2026-02` |
| vintagedate | Data release date | `2026-03-21` |
| sourceagency | Source agency | `BLS` |
| seriesid | Series identifier | `CUUR0000SA0` |
| sourcemodel | Retrieval method | `directapi` |
| timestamp | Unix integer timestamp | `1774087200` |
| nonce | Random per-request integer | `631660` |

**Examples:**
```
v1|ECON|US|CPI|326.785|index198284100|2026-02|2026-03-21|BLS|CUUR0000SA0|directapi|1774087200|631660
v1|ECON|EU|HICP|129.560|index2015100|2025-12|2026-03-21|Eurostat|prc_hicp_midx|directapi|1774087200|908558
v1|ECON|COMMODITIES|WTI|93.39|usdperbarrel|2026-03-16|2026-03-21|EIA|DCOILWTICO|directapi|1774086995|905547
```

### Rules

- Fields separated by `|` (pipe), no whitespace padding
- Price encoded as string with exactly `decimals` decimal places
- Timestamp is a Unix integer (seconds since epoch, UTC) — not ISO 8601
- Sources lowercase, comma-separated
- The canonical string is the **only** field that matters for verification

---

## Signing Schemes

### L402 — secp256k1 ECDSA

- Curve: secp256k1
- Hash: SHA-256
- Process: `sign(SHA256(canonical.encode("utf-8")))`
- Signature format: raw DER bytes, base64-encoded
- Key format: 33-byte compressed hex

**Verification (Python):**
```python
import hashlib, base64
from coincurve import PublicKey

def verify(canonical: str, signature_b64: str, pubkey_hex: str) -> bool:
    msg_hash = hashlib.sha256(canonical.encode()).digest()
    pubkey = PublicKey(bytes.fromhex(pubkey_hex))
    return pubkey.verify(base64.b64decode(signature_b64), msg_hash, hasher=None)
```

### x402 — Ed25519

- Curve: Ed25519
- Hash: SHA-256
- Process: `sign(SHA256(canonical.encode("utf-8")))`
- Key format: 32-byte hex

**Verification (Python):**
```python
import hashlib, base64
from nacl.signing import VerifyKey
from nacl.encoding import RawEncoder

def verify(canonical: str, signature_b64: str, pubkey_hex: str) -> bool:
    msg_hash = hashlib.sha256(canonical.encode()).digest()
    vk = VerifyKey(bytes.fromhex(pubkey_hex), encoder=RawEncoder)
    try:
        vk.verify(msg_hash, base64.b64decode(signature_b64))
        return True
    except Exception:
        return False
```

---

## Response Format

### Price / FX / Metals

```json
{
  "domain": "BTCUSD",
  "canonical": "v1|PRICE|BTCUSD|84231.50|USD|2|binance,coinbase,kraken|median|1741514400|482910",
  "signature": "<base64>",
  "pubkey": "<hex>",
  "signing_scheme": "secp256k1_ecdsa"
}
```

### Economic / Commodities

```json
{
  "domain": "US_CPI",
  "canonicalstring": "v1|ECON|US|CPI|326.785|index198284100|2026-02|2026-03-21|BLS|CUUR0000SA0|directapi|1774087200|631660",
  "signature": "<base64>",
  "pubkey": "<hex>",
  "signing_scheme": "secp256k1_ecdsa"
}
```

Note: Econ/commodities responses use `canonicalstring` as the field name. Clients must check both:
```python
canonical = data.get("canonical") or data.get("canonicalstring")
```

| Field | Description |
|-------|-------------|
| domain | Human-readable identifier |
| canonical / canonicalstring | The signed message — sole input to verification |
| signature | Base64-encoded signature |
| pubkey | Hex-encoded compressed public key |
| signing_scheme | `secp256k1_ecdsa` (L402) or `ed25519` (x402) |

---

## Payment Protocols

### L402 (Lightning)

```
1. Client  →  GET /oracle/price/btc/usd         →  L402 proxy
2. Proxy   →  402 + WWW-Authenticate            →  Client
3. Client  →  Pay Lightning invoice              →  LN Network
4. Client  →  GET + Authorization: L402 token   →  L402 proxy
5. Proxy   →  routes to backend, signs via sidecar
6. Proxy   →  200 + secp256k1-signed response   →  Client
```

**402 Response Headers:**
```
HTTP/1.1 402 Payment Required
Www-Authenticate: L402 macaroon="<base64>", invoice="<bolt11>"
```

**Authenticated Retry:**
```
GET /oracle/price/btc/usd HTTP/1.1
Authorization: L402 <macaroon>:<preimage_hex>
```

### x402 (USDC on Base)

```
1. Client  →  GET /oracle/price/btc/usd           →  x402 proxy
2. Proxy   →  402 + payment requirements          →  Client
3. Client  →  Sign EIP-3009 transferWithAuthorization
4. Client  →  GET + X-Payment header              →  x402 proxy
5. Proxy   →  verify payment, sign with Ed25519
6. Proxy   →  200 + Ed25519-signed response       →  Client
```

**402 Response:**
```json
{
  "x402Version": 1,
  "accepts": [
    {
      "scheme": "exact",
      "network": "eip155:8453",
      "maxAmountRequired": "10000",
      "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
      "payTo": "0xYOUR_PAYMENT_ADDRESS",
      "resource": "https://api.myceliasignal.com/oracle/price/btc/usd",
      "mimeType": "application/json",
      "maxTimeoutSeconds": 300
    }
  ]
}
```

`maxAmountRequired` is in USDC atomic units (6 decimals): `10000` = $0.01.

**Authenticated Retry:**
```
GET /oracle/price/btc/usd HTTP/1.1
X-Payment: <base64-encoded PaymentPayload with EIP-3009 signature>
```

---

## Signing Architecture

The x402 proxy (`x402_proxy.py`) acts as a signing sidecar for both payment rails:

- **x402 flow:** Signs responses directly with Ed25519 before returning to client
- **L402 flow:** The Go L402 proxy routes all paid responses through `/internal/sign/*` on the x402 proxy for secp256k1 ECDSA signing

This design keeps all signing logic in one place (Python, using `coincurve` and `PyNaCl`) while keeping the Go proxy focused on payment logic.

---

## Public Keys

Per-instance keypairs — each GC node has its own identity:

| Node | Rail | Scheme | Public Key |
|------|------|--------|-----------|
| US GC | L402 | secp256k1 | `03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf` |
| Asia GC | L402 | secp256k1 | `02b1377c30c7dcfcba428cf299c18782856a12eb4fab32b87081460f4ba2deab73` |
| US GC | x402 | Ed25519 | `f4f0e52b5f7b54831f965632bf1ebf72769beda4c4e3d36a593f7729ec812615` |
| Asia GC | x402 | Ed25519 | `7ab07fbe7d08cd16823e5eb0db0e21f3f38e9366d5fd00d14e95df0fb9b51a1a` |

---

## Pricing

| Category | L402 | x402 |
|----------|------|------|
| Spot price pairs & FX | 10 sats | $0.01 |
| VWAP pairs | 20 sats | $0.02 |
| Economic indicators | 1,000 sats | $1.00 |
| Commodities | 1,000 sats | $1.00 |

---

## Transport

All endpoints available at `https://api.myceliasignal.com`. Cloudflare terminates TLS, nginx routes to backends.

**Free endpoints (no payment):**
- `/health` — proxy health check
- `/oracle/price/*/preview` — unsigned sample data (5-min stale)
- `/oracle/econ/*/preview` — unsigned sample data
- `/.well-known/x402` — payment discovery document

**Legacy redirects:** Old namespace (`/oracle/btcusd` etc.) returns 301 to new namespace permanently.

---

## Trust Model

The protocol provides:
- **Authentication:** Signature proves which key signed the assertion
- **Integrity:** Canonical format ensures the signed message is unambiguous
- **Payment:** L402/x402 ensures data is not released without payment

The protocol does **not** provide:
- **Truthfulness:** An oracle can sign a wrong value
- **Availability:** An oracle can go offline
- **Consistency:** Different nodes may briefly diverge

These are the client's responsibility via pubkey pinning, quorum, coherence checks, and staleness checks.

---

## Design Constraints (Intentional)

1. **No oracle registry.** Clients maintain their own trusted oracle list.
2. **No governance.** No voting, staking, or slashing. Market incentives only.
3. **No subscription model.** Pay per query.
4. **No client authentication.** Payment is authentication. No API keys.
5. **No data caching guarantee.** Each query hits sources live.
6. **No consensus between oracles.** Each node signs independently.

---

## Versioning

The protocol version is the first field in the canonical message (`v1`). Clients should reject messages with unrecognized versions. Future versions may change the field set, signing scheme, or payment mechanism.
