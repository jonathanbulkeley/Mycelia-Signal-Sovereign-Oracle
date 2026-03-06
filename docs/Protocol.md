# SLO Protocol Specification (v1)

## Purpose

SLO defines a protocol for purchasing signed data assertions over HTTP, gated by Lightning micropayments via L402. The protocol is deliberately minimal: it specifies a canonical message format, a signing scheme, and a payment mechanism. Everything else — source selection, aggregation, trust — is the client's responsibility.

## Canonical Message Format

Every oracle response contains a canonical string that is the sole input to the signing function:
```
v1|<pair>|<value>|<currency>|<decimals>|<timestamp>|<nonce>|<sources>|<method>
```

### Fields

| Field | Type | Description | Example |
|---|---|---|---|
| version | string | Protocol version | `v1` |
| pair | string | Asset pair identifier | `BTCUSD` |
| value | string | Price value (string, not float) | `96482.15` |
| currency | string | Quote currency | `USD` |
| decimals | integer | Decimal precision of value | `2` |
| timestamp | string | ISO 8601 UTC timestamp | `2026-02-13T18:44:30Z` |
| nonce | string | Random 6-digit integer, generated fresh per request | `482910` |
| sources | string | Comma-separated data sources | `coinbase,kraken,bitstamp` |
| method | string | Aggregation method | `median` or `vwap` |

### Rules

- Fields are separated by `|` (pipe)
- No whitespace padding
- Price is encoded as a string with exactly `decimals` decimal places
- Timestamp is always UTC, formatted as `YYYY-MM-DDTHH:MM:SSZ`
- Sources are lowercase, comma-separated, alphabetically ordered
- The canonical string is deterministic: the same inputs always produce the same string

### Example
```
v1|BTCUSD|96482.15|USD|2|2026-02-13T18:44:30Z|482910|bitstamp,coinbase,kraken|median
```

## Signing Scheme

### Algorithm

- Curve: **secp256k1** (same as Bitcoin)
- Hash: **SHA-256**
- Signature format: **raw 64-byte (r, s)**

### Process

1. Construct the canonical string
2. Compute `hash = SHA256(canonical.encode("utf-8"))`
3. Sign `hash` with the oracle's secp256k1 private key
4. Encode signature as base64

### Verification

1. Decode the base64 signature
2. Decode the hex public key
3. Compute `hash = SHA256(canonical.encode("utf-8"))`
4. Verify the ECDSA signature against `hash` using the public key
```python
import hashlib, base64
from ecdsa import VerifyingKey, SECP256k1

def verify(canonical: str, signature_b64: str, pubkey_hex: str) -> bool:
    sig = base64.b64decode(signature_b64)
    pubkey = bytes.fromhex(pubkey_hex)
    vk = VerifyingKey.from_string(pubkey, curve=SECP256k1)
    h = hashlib.sha256(canonical.encode()).digest()
    return vk.verify_digest(sig, h)
```

## Response Format

Oracles return JSON over HTTP:
```json
{
  "domain": "BTCUSD",
  "canonical": "v1|BTCUSD|96482.15|USD|2|2026-02-13T18:44:30Z|482910|bitstamp,coinbase,kraken|median",
  "signature": "MEUCIQDr7y8Hx...",
  "pubkey": "0220a2222aae..."
}
```

| Field | Type | Description |
|---|---|---|
| domain | string | Human-readable identifier for the data type |
| canonical | string | The signed message (sole input to signature) |
| signature | string | Base64-encoded ECDSA signature over SHA256(canonical) |
| pubkey | string | Hex-encoded compressed secp256k1 public key of the signer |

The `canonical` field is the **only** field that matters for verification. All other fields are convenience metadata. A client that stores only `canonical`, `signature`, and `pubkey` can verify the assertion indefinitely.

## Payment Protocol (L402)

SLO uses the [L402 protocol](https://github.com/lightninglabs/L402) for payment gating, enforced by a custom Go reverse proxy that creates invoices via the LND REST API and mints/verifies L402 macaroons.

### Flow
```
1. Client  →  GET /oracle/btcusd           →  Server
2. Server  →  402 + WWW-Authenticate       →  Client
3. Client  →  Pay Lightning invoice         →  LN Network
4. Client  →  GET + Authorization: L402     →  Server
5. Server  →  200 + signed assertion        →  Client
```

### 402 Response Headers
```
HTTP/1.1 402 Payment Required
Www-Authenticate: L402 macaroon="<base64>", invoice="<bolt11>"
```

- `macaroon`: Base64-encoded macaroon (access token, locked until payment)
- `invoice`: BOLT-11 Lightning invoice

### Authenticated Retry

After paying the invoice, the client obtains the payment preimage and retries:
```
GET /oracle/btcusd HTTP/1.1
Authorization: L402 <macaroon>:<preimage_hex>
```

### Payment Separation

The oracle servers contain **zero payment logic**. The L402 proxy sits in front as a reverse proxy and handles:
- Invoice creation (via the connected LND node's REST API)
- Payment verification
- Macaroon issuance and validation

This separation means oracle code is simple, testable, and payment-agnostic.

## Transport

### Endpoints

All endpoints are served via `https://api.myceliasignal.com` with Cloudflare TLS. nginx routes requests to the appropriate backend proxy.

#### L402 endpoints (Lightning payment)

| Public Path | Data |
|---|---|
| `/oracle/btcusd` | BTCUSD spot price (median, 9 sources) |
| `/oracle/btcusd/vwap` | BTCUSD volume-weighted average |
| `/oracle/ethusd` | ETHUSD spot price (median, 5 sources) |
| `/oracle/eurusd` | EURUSD spot price (median, 8 sources) |
| `/oracle/xauusd` | XAU/USD gold spot price (median, 8 sources) |
| `/oracle/btceur` | BTC/EUR cross-rate (derived from BTCUSD + EURUSD) |
| `/oracle/solusd` | SOL/USD spot price (median, 9 sources) |
| `/oracle/etheur` | ETH/EUR hybrid spot (3 direct + cross-rate) |
| `/oracle/soleur` | SOL/EUR hybrid spot (3 direct + cross-rate) |
| `/oracle/xaueur` | XAU/EUR cross-rate (derived from XAUUSD + EURUSD) |
| `/oracle/btceur/vwap` | BTC/EUR VWAP cross-rate |
| `/dlc/oracle/attestations/{id}` | DLC Schnorr attestation (1000 sats) |

#### x402 endpoints (USDC on Base)

| Public Path | Data |
|---|---|
| `/oracle/btcusd` | BTCUSD spot price (median, 9 sources) |
| `/oracle/btcusd/vwap` | BTCUSD volume-weighted average |
| `/oracle/ethusd` | ETHUSD spot price (median, 5 sources) |
| `/oracle/eurusd` | EURUSD spot price (median, 8 sources) |
| `/oracle/xauusd` | XAU/USD gold spot price (median, 8 sources) |
| `/oracle/btceur` | BTC/EUR cross-rate |
| `/oracle/solusd` | SOL/USD spot price (median, 9 sources) |
| `/oracle/etheur` | ETH/EUR hybrid spot (3 direct + cross-rate) |
| `/oracle/soleur` | SOL/EUR hybrid spot (3 direct + cross-rate) |
| `/oracle/xaueur` | XAU/EUR cross-rate (derived from XAUUSD + EURUSD) |
| `/oracle/btceur/vwap` | BTC/EUR VWAP cross-rate |

Note: nginx strips the `/sho/` prefix before proxying to the x402 backend, so the x402 proxy internally handles `/oracle/*` paths.

#### Free endpoints (no payment)

| Public Path | Data |
|---|---|
| `/health` | L402 proxy health check |
| `/health` | x402 proxy health check |
| `/sho/info` | x402 oracle info (pubkey, endpoints, pricing) |
| `/dlc/oracle/pubkey` | DLC oracle public key |
| `/dlc/oracle/announcements` | DLC nonce commitments |
| `/dlc/oracle/status` | DLC oracle status |

### Content Type

All responses are `application/json`.

### No State

Oracle servers are stateless. Each request is independent. No sessions, no subscriptions, no websockets. Pay per query.

## Versioning

The protocol version is the first field in the canonical message (`v1`). Future versions may change the field set, signing scheme, or payment mechanism. Clients should reject messages with unrecognized versions.

## Trust Model

SLO makes no claims about oracle honesty. The protocol provides:

- **Authentication**: The signature proves which key signed the assertion
- **Integrity**: The canonical format ensures the signed message is unambiguous
- **Payment**: L402 ensures data is not released without payment

The protocol does **not** provide:

- **Truthfulness**: An oracle can sign a wrong price
- **Availability**: An oracle can go offline
- **Consistency**: Different oracles may return different prices

These properties are the client's responsibility, achieved through:

- **Pubkey pinning**: Only accept responses from known oracle keys
- **Quorum**: Query multiple independent oracles
- **Coherence checks**: Reject prices that diverge beyond a threshold
- **Staleness checks**: Reject timestamps older than acceptable

## Extending the Protocol

### New Data Types

Any data that can be expressed as a key-value assertion fits the canonical format:
```
v1|ETHUSD|3241.50|USD|2|2026-02-13T18:44:30Z|890124|coinbase,kraken|median
v1|GOLD_OZ|2045.30|USD|2|2026-02-13T18:44:30Z|890125|kitco,lbma|median
v1|FED_RATE|5.25|PCT|2|2026-02-13T18:44:30Z|890126|federalreserve|direct
v1|TEMP_NYC|72.4|F|1|2026-02-13T18:44:30Z|890127|noaa,openweather|median
```

The protocol is data-agnostic. The `domain`, `sources`, and `method` fields adapt to the data type. The signing and payment mechanisms remain identical.

### Multi-Operator Federation

The protocol supports multiple independent operators by design. Clients choose which operators to trust and how to aggregate their responses. No coordination between operators is required.

A future version may define a standard discovery mechanism (e.g., DNS-based oracle resolution), but v1 relies on explicit client configuration.

## Design Constraints

These constraints are intentional and will not change:

1. **No oracle registry.** Clients maintain their own list of trusted oracles.
2. **No governance.** No voting, no staking, no slashing. Market incentives only.
3. **No subscription model.** Pay per query. No recurring access.
4. **No client authentication.** Payment is authentication. No API keys, no OAuth.
5. **No data caching guarantee.** Each query hits the sources live. Freshness over efficiency.
6. **No consensus between oracles.** Each oracle signs independently. Aggregation is the client's job.

## x402 Payment Protocol (SHO)

SHO extends the protocol with x402 payment support, accepting USDC on Base. The canonical message format is identical — only the signing scheme and payment mechanism differ.

### Flow
```
1. Client  →  GET /oracle/btcusd            →  nginx → x402 Proxy
2. Proxy   →  402 + payment requirements    →  Client
3. Client  →  Send USDC on Base             →  Base chain
4. Client  →  GET + X-Payment header        →  nginx → SHO Proxy
5. Proxy   →  200 + Ed25519 signed data     →  Client
```

### 402 Response

The SHO returns a standard x402-compliant 402 response with both a `Payment-Required` HTTP header (base64-encoded) and a JSON body. This is compatible with standard x402 client SDKs (`@x402/fetch`, `@x402/axios`), x402scan, and the Coinbase facilitator.

**Response body:**
```json
{
  "x402Version": 1,
  "accepts": [
    {
      "scheme": "exact",
      "network": "eip155:8453",
      "maxAmountRequired": "1000",
      "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
      "payTo": "0xD593832Ce9C2B13B192ba50B55dd9AF44e96700d",
      "resource": "https://api.myceliasignal.com/oracle/btcusd",
      "mimeType": "application/json",
      "description": "Signed price attestation",
      "maxTimeoutSeconds": 300
    }
  ],
  "error": "X-PAYMENT header is required",
  "x402": {
    "version": "1",
    "chain": "base",
    "asset": "USDC",
    "contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "recipient": "0xD593832Ce9C2B13B192ba50B55dd9AF44e96700d",
    "amount": "0.001",
    "nonce": "752c6f1f5c46e8c9031a5a4cec5db1be",
    "expires_in": 300
  }
}
```

**Response headers:**
```
HTTP/1.1 402 Payment Required
Payment-Required: <base64-encoded accepts array>
Content-Type: application/json
```

The `accepts` array follows the standard x402 PaymentRequirements schema. The `x402` object is retained for backward compatibility with existing Mycelia Signal clients. `maxAmountRequired` is in USDC atomic units (6 decimals): `1000` = $0.001.
### Authenticated Retry

After sending USDC on Base, the client retries with an `X-Payment` header:
```
GET /oracle/btcusd HTTP/1.1
X-PAYMENT: <base64-encoded PaymentPayload with EIP-3009 signature>
```

### Ed25519 Signing

x402 responses are signed with Ed25519 instead of secp256k1 ECDSA:

- Curve: **Ed25519**
- Hash: **SHA-256**
- Process: `sign(SHA256(canonical))`

```python
import hashlib, base64
from nacl.signing import VerifyKey

def verify_ed25519(canonical: str, signature_b64: str, pubkey_hex: str) -> bool:
    msg_hash = hashlib.sha256(canonical.encode()).digest()
    sig = base64.b64decode(signature_b64)
    vk = VerifyKey(bytes.fromhex(pubkey_hex))
    vk.verify(msg_hash, sig)
    return True
```

### Optimistic Delivery

The x402 proxy verifies and settles payments via the CDP facilitator before returning data. EIP-3009 signatures are verified off-chain and settled on-chain by the facilitator. If verification or settlement fails, the sending address is subject to tiered enforcement (grace cooldown → hard block).

### Depeg Circuit Breaker

If USDC deviates more than 2% from USD parity (median of 5 sources: Kraken, Bitstamp, Coinbase, Gemini, Bitfinex; minimum 2 required), the x402 proxy suspends payment acceptance and returns HTTP 503.

### Dual Signing Identity

Both L402 and x402 delivery use the same canonical message format. The same attestation can be verified by either key:

| Delivery | Signing Scheme | Pubkey |
|---|---|---|
| L402 (SLO) | ECDSA secp256k1 | `0236a051b7a0384ebe19fe31fcee6837bff7a9532a2a9ae04731ea04df5cd94adf` |
| x402 (SHO) | Ed25519 | `c40ad8cbd866189eecb7c68091a984644fb7736ef3b8d96cd31b600ef0072623` |

A cross-certification statement binding both keys will be published, proving common ownership under a single oracle identity.
