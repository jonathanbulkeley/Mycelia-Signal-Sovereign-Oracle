# Client Integration Guide

How to consume SLO oracle data in your application.

## Overview

SLO uses the L402 protocol (formerly LSAT) to gate data behind Lightning micropayments. Your client needs to:

1. Make an HTTP request
2. Handle the 402 response
3. Pay the Lightning invoice
4. Retry with proof of payment
5. Verify the signature on the returned data

## Quick Start: lnget

The fastest way to integrate. [lnget](https://github.com/lightninglabs/lnget) handles the entire L402 flow in one command:
```bash
# Install
go install github.com/lightninglabs/lnget@latest

# Configure (one time)
lnget config init
# Edit ~/.lnget/config.yaml with your LND credentials

# Fetch signed price data
lnget -k -q https://api.myceliasignal.com/oracle/btcusd | jq .
```

lnget caches L402 tokens, so repeated requests to the same endpoint reuse the token until it expires.

**Note:** Go's default TLS ClientHello is fingerprinted and rejected by Cloudflare's bot protection. If you experience 400 errors with lnget through the HTTPS domain, use the VM's direct IP as a workaround or configure a custom TLS profile. `curl` and Python `urllib` work fine through Cloudflare.

## Python Integration

### With lnget (subprocess)

Simplest approach — shell out to lnget and parse the JSON:
```python
import json
import subprocess

def fetch_oracle(url: str) -> dict:
    result = subprocess.run(
        ["lnget", "-k", "-q", url],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"lnget failed: {result.stderr.strip()}")
    return json.loads(result.stdout)

data = fetch_oracle("https://api.myceliasignal.com/oracle/btcusd")
print(f"BTCUSD: {data['canonical'].split('|')[2]}")
```

### Native Python (manual L402 flow)

For full control without external dependencies:
```python
import requests
import re
import hashlib
import base64
from ecdsa import VerifyingKey, SECP256k1

ORACLE_URL = "https://api.myceliasignal.com/oracle/btcusd"

def fetch_with_l402(url: str, pay_invoice_func) -> dict:
    """
    Full L402 flow:
    1. GET the URL
    2. Parse 402 response for macaroon + invoice
    3. Pay the invoice (you provide the payment function)
    4. Retry with L402 token
    5. Return the data
    """
    # Step 1: Initial request
    r = requests.get(url)

    if r.status_code != 402:
        return r.json()

    # Step 2: Parse the L402 challenge
    auth_header = r.headers.get("Www-Authenticate", "")
    macaroon_match = re.search(r'macaroon="([^"]+)"', auth_header)
    invoice_match = re.search(r'invoice="([^"]+)"', auth_header)

    if not macaroon_match or not invoice_match:
        raise RuntimeError("Could not parse L402 challenge")

    macaroon = macaroon_match.group(1)
    invoice = invoice_match.group(1)

    # Step 3: Pay the invoice
    # pay_invoice_func should return the preimage (hex string)
    preimage = pay_invoice_func(invoice)

    # Step 4: Retry with L402 token
    token = f"L402 {macaroon}:{preimage}"
    r2 = requests.get(url, headers={"Authorization": token})

    if r2.status_code != 200:
        raise RuntimeError(f"L402 retry failed: {r2.status_code}")

    return r2.json()


def verify_response(data: dict) -> bool:
    """Verify the secp256k1 signature on the canonical message."""
    try:
        canonical = data["canonical"]
        sig_bytes = base64.b64decode(data["signature"])
        pubkey_bytes = bytes.fromhex(data["pubkey"])

        vk = VerifyingKey.from_string(pubkey_bytes, curve=SECP256k1)
        h = hashlib.sha256(canonical.encode()).digest()
        return vk.verify_digest(sig_bytes, h)
    except Exception:
        return False
```

### Payment Function Examples

The `pay_invoice_func` depends on how you connect to Lightning:
```python
# Via LND REST API
def pay_via_lnd(invoice: str) -> str:
    import base64 as b64
    mac_hex = open("admin.macaroon", "rb").read().hex()
    r = requests.post(
        "https://YOUR_NODE:8080/v1/channels/transactions",
        headers={"Grpc-Metadata-macaroon": mac_hex},
        json={"payment_request": invoice},
        verify=False
    )
    data = r.json()
    preimage_b64 = data["payment_preimage"]
    return b64.b64decode(preimage_b64).hex()

# Via lncli
def pay_via_lncli(invoice: str) -> str:
    result = subprocess.run(
        ["lncli", "payinvoice", "--force", invoice],
        capture_output=True, text=True
    )
    # Parse preimage from output
    for line in result.stdout.split("\n"):
        if "preimage" in line.lower():
            return line.split(":")[-1].strip()
```

## JavaScript / Node.js Integration
```javascript
const https = require('https');

async function fetchOracle(url) {
  // Step 1: Initial request
  const res = await fetch(url);

  if (res.status !== 402) {
    return await res.json();
  }

  // Step 2: Parse L402 challenge
  const authHeader = res.headers.get('www-authenticate');
  const macaroon = authHeader.match(/macaroon="([^"]+)"/)[1];
  const invoice = authHeader.match(/invoice="([^"]+)"/)[1];

  // Step 3: Pay invoice (implement with your Lightning library)
  const preimage = await payInvoice(invoice);

  // Step 4: Retry with token
  const res2 = await fetch(url, {
    headers: { 'Authorization': `L402 ${macaroon}:${preimage}` }
  });

  return await res2.json();
}

// Verify signature (using secp256k1 library)
const crypto = require('crypto');
const secp256k1 = require('secp256k1');

function verifyResponse(data) {
  const hash = crypto.createHash('sha256')
    .update(data.canonical)
    .digest();
  const sig = Buffer.from(data.signature, 'base64');
  const pubkey = Buffer.from(data.pubkey, 'hex');
  return secp256k1.ecdsaVerify(sig, hash, pubkey);
}
```

## Go Integration
```go
package main

import (
    "crypto/sha256"
    "encoding/base64"
    "encoding/hex"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "regexp"

    "github.com/btcsuite/btcd/btcec/v2/ecdsa"
    "github.com/btcsuite/btcd/btcec/v2"
)

type OracleResponse struct {
    Domain    string `json:"domain"`
    Canonical string `json:"canonical"`
    Signature string `json:"signature"`
    Pubkey    string `json:"pubkey"`
}

func verifyResponse(resp OracleResponse) bool {
    hash := sha256.Sum256([]byte(resp.Canonical))
    sigBytes, _ := base64.StdEncoding.DecodeString(resp.Signature)
    pubBytes, _ := hex.DecodeString(resp.Pubkey)

    pubKey, _ := btcec.ParsePubKey(pubBytes)
    sig, _ := ecdsa.ParseDERSignature(sigBytes)

    return sig.Verify(hash[:], pubKey)
}
```

## Parsing the Canonical Message

Every response includes a pipe-delimited canonical string:
```
v1|BTCUSD|96482.15|USD|2|2026-02-13T18:44:30Z|482910|coinbase,kraken,bitstamp|median
```

Parse it in any language:
```python
parts = canonical.split("|")
version   = parts[0]  # "v1"
pair      = parts[1]  # "BTCUSD"
price     = parts[2]  # "96482.15"
currency  = parts[3]  # "USD"
decimals  = parts[4]  # "2"
timestamp = parts[5]  # "2026-02-13T18:44:30Z"
nonce     = parts[6]  # "482910" (random 6-digit integer per request)
sources   = parts[7]  # "coinbase,kraken,bitstamp"
method    = parts[8]  # "median"
```

## Quorum Pattern

For production use, query multiple oracles and aggregate:
```python
import statistics

ORACLES = [
    "https://api.myceliasignal.com/oracle/btcusd",       # 10 sats
    "https://api.myceliasignal.com/oracle/btcusd/vwap",   # 20 sats
    # Add third-party SLO operators here as they come online
]

MIN_RESPONSES = 2
MAX_DEVIATION_PCT = 0.5

prices = []
for url in ORACLES:
    data = fetch_oracle(url)             # your L402 fetch function
    if verify_response(data):            # signature check
        price = float(data["canonical"].split("|")[2])
        prices.append(price)

if len(prices) >= MIN_RESPONSES:
    median = statistics.median(prices)
    # Check coherence
    for p in prices:
        if abs(p - median) / median * 100 > MAX_DEVIATION_PCT:
            raise ValueError("Price divergence detected")
    print(f"Trusted price: ${median:.2f}")
```

The quorum pattern means no single oracle can deceive you. As more operators come online, you add their URLs to your list and increase `MIN_RESPONSES`.

## Error Handling

| HTTP Status | Meaning | Action |
|---|---|---|
| 402 | Payment required | Parse invoice, pay, retry with token |
| 200 | Success | Verify signature, parse data |
| 500 | Oracle error | Exchange API failure; retry or skip |
| Connection timeout | Server down | Skip this oracle, proceed with others |

## Cost Management

- Spot query (BTC, ETH, EUR, XAU, BTC/EUR, SOL, ETH/EUR, SOL/EUR, XAU/EUR): **10 sats** (~$0.007)
- VWAP query: **20 sats** (~$0.014)
- DLC attestation: **1000 sats** (~$0.70)
- Full quorum (spot + VWAP): **30 sats** (~$0.021)

At 1 query per minute, 24/7:
- Spot only: ~432,000 sats/month (~$290)
- Full quorum: ~1,296,000 sats/month (~$870)

lnget caches tokens, so repeated requests within the token validity window don't require new payments.

## Security Considerations

1. **Always verify signatures.** Never trust data without checking the secp256k1 signature against the pubkey.
2. **Pin pubkeys.** Once you trust an oracle, store its pubkey and reject responses signed by different keys.
3. **Use quorum.** A single oracle can lie. Two independent oracles lying in the same direction is much harder.
4. **Check timestamps.** Reject assertions older than your staleness threshold (e.g., 60 seconds).
5. **Monitor deviation.** If oracles start diverging beyond your threshold, halt and investigate.

## x402 Integration (SHO — USDC on Base)
SHO provides the same oracle data via the standard x402 payment protocol. Instead of Lightning sats, consumers pay with USDC on Base using EIP-3009 `transferWithAuthorization` signatures — gasless, no on-chain transaction required from the client.

### Quick Start
```bash
# Get oracle info (free)
curl https://api.myceliasignal.com/sho/info

# Get health status (free)
curl https://api.myceliasignal.com/health

# Request price — returns 402 with standard x402 accepts array
curl https://api.myceliasignal.com/oracle/btcusd

# Discovery document
curl https://api.myceliasignal.com/.well-known/x402
```

### Standard x402 Clients (Recommended)

Any standard x402 client works out of the box:
```javascript
// Using @x402/fetch (Node.js / TypeScript)
import { fetchWithPayment } from "@x402/fetch";
import { createWalletClient, http } from "viem";
import { base } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

const account = privateKeyToAccount("0x...");
const client = createWalletClient({ account, chain: base, transport: http() });

const response = await fetchWithPayment(
  "https://api.myceliasignal.com/oracle/btcusd",
  {}, // fetch options
  { walletClient: client }
);
const data = await response.json();
```

### Python x402 Client
```python
import json
import hashlib
import base64
import secrets
import time
import requests

ORACLE_URL = "https://api.myceliasignal.com"

def fetch_x402(pair: str, wallet_address: str, sign_typed_data_fn) -> dict:
    """Full standard x402 flow: request → sign EIP-712 → retry with X-PAYMENT.

    Args:
        pair: Trading pair (e.g., "btcusd")
        wallet_address: Your Ethereum address
        sign_typed_data_fn: Function that signs EIP-712 typed data
            signature = sign_typed_data_fn(typed_data: dict) -> str
    """
    # Step 1: Get payment requirements
    r = requests.get(f"{ORACLE_URL}/oracle/{pair}")
    if r.status_code != 402:
        return r.json()

    body402 = r.json()
    req = body402["accepts"][0]

    # Step 2: Build EIP-3009 transferWithAuthorization parameters
    nonce = "0x" + secrets.token_hex(32)
    valid_before = str(int(time.time()) + 300)  # 5 minutes

    typed_data = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": {
            "name": req["extra"]["name"],      # "USD Coin"
            "version": req["extra"]["version"], # "2"
            "chainId": 8453,                    # Base mainnet
            "verifyingContract": req["asset"],
        },
        "message": {
            "from": wallet_address,
            "to": req["payTo"],
            "value": req["maxAmountRequired"],
            "validAfter": "0",
            "validBefore": valid_before,
            "nonce": nonce,
        },
    }

    # Step 3: Sign (your wallet implementation)
    signature = sign_typed_data_fn(typed_data)

    # Step 4: Build standard PaymentPayload
    payment_payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "eip155:8453",
        "payload": {
            "signature": signature,
            "authorization": {
                "from": wallet_address,
                "to": req["payTo"],
                "value": req["maxAmountRequired"],
                "validAfter": "0",
                "validBefore": valid_before,
                "nonce": nonce,
            },
        },
    }

    # Step 5: Base64-encode and retry
    x_payment = base64.b64encode(json.dumps(payment_payload).encode()).decode()
    r2 = requests.get(
        f"{ORACLE_URL}/oracle/{pair}",
        headers={"X-PAYMENT": x_payment},
    )
    return r2.json()


def verify_ed25519(data: dict) -> bool:
    """Verify Ed25519 signature on x402 response."""
    try:
        from nacl.signing import VerifyKey
        msg_hash = hashlib.sha256(data["canonical"].encode()).digest()
        sig = base64.b64decode(data["signature"])
        vk = VerifyKey(bytes.fromhex(data["pubkey"]))
        vk.verify(msg_hash, sig)
        return True
    except Exception:
        return False
```

### x402 Error Handling

| HTTP Status | Meaning | Action |
|---|---|---|
| 402 | Payment required | Parse `accepts` array, sign EIP-712, retry with `X-PAYMENT` header |
| 200 | Success | Verify Ed25519 signature, parse data |
| 400 | Invalid payment payload or signature | Check payload format matches spec |
| 403 | Address blocked (enforcement) | Grace cooldown or hard block — check `/sho/enforcement/{address}` |
| 503 | Depeg circuit breaker active | USDC off peg — try again later or use L402 (Lightning) instead |

### x402 Cost

- Spot query (BTC, ETH, EUR, XAU, BTC/EUR, SOL, ETH/EUR, SOL/EUR, XAU/EUR): **$0.001 USDC**
- VWAP query: **$0.002 USDC**
- No gas fee for the client — EIP-3009 signatures are settled by the CDP facilitator

### Choosing Between L402 and x402

| Use L402 (Lightning) when... | Use x402 (USDC) when... |
|---|---|
| You already have a Lightning wallet | You already have USDC on Base |
| You want pseudonymous payments | You want EVM-native integration |
| You're building on Bitcoin | You're building on Base/EVM |
| Sub-second payment finality matters | You prefer stablecoin accounting |
| | Standard x402 SDK clients work out of the box |

Both protocols return the same oracle data with the same canonical format. Only the signature scheme and payment mechanism differ.

