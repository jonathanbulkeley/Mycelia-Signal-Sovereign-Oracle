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
| nonce | string | Unique identifier per assertion | `890123` |
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
v1|BTCUSD|96482.15|USD|2|2026-02-13T18:44:30Z|890123|bitstamp,coinbase,kraken|median
```

## Signing Scheme

### Algorithm

- Curve: **secp256k1** (same as Bitcoin)
- Hash: **SHA-256**
- Signature format: **DER-encoded ECDSA**

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
  "canonical": "v1|BTCUSD|96482.15|USD|2|2026-02-13T18:44:30Z|890123|bitstamp,coinbase,kraken|median",
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

Oracles expose HTTP GET endpoints. The URL path determines the data type:

| Path | Data |
|---|---|
| `/oracle/btcusd` | BTCUSD spot price (median, 9 sources) |
| `/oracle/btcusd/vwap` | BTCUSD volume-weighted average |
| `/oracle/ethusd` | ETHUSD spot price (median, 5 sources) |
| `/oracle/eurusd` | EURUSD spot price (median, 7 sources) |
| `/oracle/xauusd` | XAU/USD gold spot price (median, 8 sources) |
| `/oracle/btceur` | BTC/EUR cross-rate (derived from BTCUSD + EURUSD) |
| `/oracle/solusd` | SOL/USD spot price (median, 9 sources) |
| `/dlc/oracle/attestations/{id}` | DLC Schnorr attestation (1000 sats) |
| `/health` | Health check (not payment-gated) |
| `/oracle/status` | Oracle status (not payment-gated) |
| `/dlc/oracle/pubkey` | DLC oracle public key (not payment-gated) |
| `/dlc/oracle/announcements` | DLC nonce commitments (not payment-gated) |
| `/dlc/oracle/status` | DLC oracle status (not payment-gated) |

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
```

---

Add that to `docs/Protocol.md` (replacing the old version). How's the channel?
```
curl -k --header "Grpc-Metadata-macaroon: %MAC%" https://mycelia.m.voltageapp.io:8080/v1/channels/pending
