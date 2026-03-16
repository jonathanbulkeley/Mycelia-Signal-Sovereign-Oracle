# Mycelia Signal — Live Demo

A step-by-step walkthrough of purchasing signed price data for Lightning sats or USDC.

## What You'll See

1. A free preview response (no payment)
2. An HTTP 402 (Payment Required) with a Lightning invoice or USDC payment requirements
3. A signed price attestation you can verify independently

---

## Free Preview (No Payment Required)

Every paid endpoint has a `/preview` variant that returns unsigned sample data for free. Good for development and testing:

```bash
curl https://api.myceliasignal.com/oracle/price/btc/usd/preview | jq .
curl https://api.myceliasignal.com/oracle/econ/us/cpi/preview | jq .
curl https://api.myceliasignal.com/oracle/econ/commodities/wti/preview | jq .
```

Preview responses are unsigned (no signature field) and may be up to 5 minutes stale.

---

## L402 Demo (Lightning)

### Step 1: Request Price Data

```bash
curl -i https://api.myceliasignal.com/oracle/price/btc/usd
```

Response:
```
HTTP/1.1 402 Payment Required
Www-Authenticate: L402 macaroon="AgEEbHNhdA...", invoice="lnbc100n1p5c..."
```

No data released. Payment first.

### Step 2: Pay the Invoice

#### Option A: lnget (automatic — handles the full flow)

```bash
lnget -k https://api.myceliasignal.com/oracle/price/btc/usd
```

One command. lnget receives the 402, pays the invoice, retries with the token, and prints the signed response.

#### Option B: Any Lightning wallet

Copy the invoice string (`lnbc100n1p5c...`) and paste it into Phoenix, Zeus, Alby, or any Lightning wallet. After payment, retry:

```bash
curl -H "Authorization: L402 <macaroon>:<preimage_hex>" \
  https://api.myceliasignal.com/oracle/price/btc/usd
```

### Step 3: Receive Signed Data

```json
{
  "domain": "BTCUSD",
  "canonical": "v1|PRICE|BTCUSD|84231.50|USD|2|binance,bitstamp,coinbase,kraken,okx|median|1741514400|482910",
  "signature": "MEUCIQDr7y8Hx...",
  "pubkey": "03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf",
  "signing_scheme": "secp256k1_ecdsa"
}
```

#### Reading the canonical message

```
v1|PRICE|BTCUSD|84231.50|USD|2|binance,bitstamp,coinbase,kraken,okx|median|1741514400|482910
│  │     │      │        │  │ │                                      │      │           │
│  │     │      │        │  │ │                                      │      │           └─ nonce
│  │     │      │        │  │ │                                      │      └─ Unix timestamp
│  │     │      │        │  │ │                                      └─ method: median
│  │     │      │        │  │ └─ sources (comma-separated, lowercase)
│  │     │      │        │  └─ decimal places
│  │     │      │        └─ quote currency
│  │     │      └─ price
│  │     └─ asset pair
│  └─ type: PRICE
└─ protocol version: v1
```

### Step 4: Verify the Signature

```python
import hashlib, base64
from coincurve import PublicKey

canonical  = "v1|PRICE|BTCUSD|84231.50|USD|2|binance,bitstamp,coinbase,kraken,okx|median|1741514400|482910"
signature  = "MEUCIQDr7y8Hx..."  # from response
pubkey_hex = "03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf"

msg_hash = hashlib.sha256(canonical.encode()).digest()
pubkey = PublicKey(bytes.fromhex(pubkey_hex))
sig_bytes = base64.b64decode(signature)

assert pubkey.verify(sig_bytes, msg_hash, hasher=None)
print("Signature valid — this price was signed by this oracle.")
```

If the signature verifies, the oracle committed to this price at this timestamp. If it doesn't, reject it.

---

## L402 Demo — Economic Indicator

```bash
lnget -k https://api.myceliasignal.com/oracle/econ/us/cpi
```

Response:
```json
{
  "domain": "US_CPI",
  "canonicalstring": "v1|US|CPI|3.1|pct_yoy|2026-01-01|2026-02-01|BLS|CPIAUCSL|directapi||482910",
  "signature": "...",
  "pubkey": "03c1955b8c...",
  "signing_scheme": "secp256k1_ecdsa"
}
```

Note: Econ responses use `canonicalstring` (not `canonical`). Always check both:
```python
canonical = data.get("canonical") or data.get("canonicalstring")
```

Cost: 1000 sats (~$0.70). Source: BLS direct API. Reference period: `2026-01-01` to `2026-02-01`.

---

## Quorum Demo

Query spot and VWAP, verify both, take the median:

```bash
lnget -k https://api.myceliasignal.com/oracle/price/btc/usd
lnget -k https://api.myceliasignal.com/oracle/price/btc/usd/vwap
```

Total cost: 30 sats (10 + 20). If both prices are within 0.5% of each other, take the median. If they diverge, something is wrong — don't trust either.

```python
import statistics

prices = [84231.50, 84218.77]  # spot, vwap
median = statistics.median(prices)

for p in prices:
    deviation = abs(p - median) / median * 100
    assert deviation < 0.5, f"Price divergence: {deviation:.2f}%"

print(f"Trusted BTC/USD: ${median:,.2f}")
```

---

## x402 Demo (USDC on Base)

### Step 1: Request Price Data

```bash
curl -i https://api.myceliasignal.com/oracle/price/btc/usd
```

Response (402):
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
      "maxTimeoutSeconds": 300
    }
  ]
}
```

`maxAmountRequired: 10000` = $0.01 USDC (6 decimal places).

### Step 2: Pay with x402 SDK

```javascript
import { fetchWithPayment } from "@x402/fetch";
import { createWalletClient, http } from "viem";
import { base } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

const account = privateKeyToAccount("0x...");
const client = createWalletClient({ account, chain: base, transport: http() });

const response = await fetchWithPayment(
  "https://api.myceliasignal.com/oracle/price/btc/usd",
  {},
  { walletClient: client }
);
const data = await response.json();
```

### Step 3: Receive Ed25519-Signed Data

```json
{
  "domain": "BTCUSD",
  "canonical": "v1|PRICE|BTCUSD|84231.50|USD|2|binance,bitstamp,coinbase,kraken|median|1741514400|482910",
  "signature": "3yYxQATXEqFg...",
  "pubkey": "f4f0e52b5f7b54831f965632bf1ebf72769beda4c4e3d36a593f7729ec812615",
  "signing_scheme": "ed25519"
}
```

Same canonical format, same price, same sources — different signing scheme.

### Step 4: Verify Ed25519 Signature

```python
import hashlib, base64
from nacl.signing import VerifyKey
from nacl.encoding import RawEncoder

canonical  = "v1|PRICE|BTCUSD|84231.50|USD|2|binance,bitstamp,coinbase,kraken|median|1741514400|482910"
signature  = "3yYxQATXEqFg..."
pubkey_hex = "f4f0e52b5f7b54831f965632bf1ebf72769beda4c4e3d36a593f7729ec812615"

msg_hash = hashlib.sha256(canonical.encode()).digest()
vk = VerifyKey(bytes.fromhex(pubkey_hex), encoder=RawEncoder)
vk.verify(msg_hash, base64.b64decode(signature))
print("Ed25519 signature valid — same oracle, different key.")
```

---

## Free Endpoints

```bash
# Health check
curl https://api.myceliasignal.com/health

# Discovery document — all 56 endpoints with pricing
curl https://api.myceliasignal.com/.well-known/x402

# Preview any endpoint — no payment required
curl https://api.myceliasignal.com/oracle/price/eur/usd/preview
curl https://api.myceliasignal.com/oracle/econ/eu/hicp/preview
curl https://api.myceliasignal.com/oracle/econ/commodities/brent/preview
```

---

## What Just Happened

You paid a machine 10 sats (~$0.007) or $0.01 USDC and received a cryptographically signed price attestation that you verified independently.

No API key. No account. No trust in the transport. The oracle can't revoke your access. You can't use the data without paying. The incentives are aligned by construction.
