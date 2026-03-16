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
lnget -k -q http://104.197.109.246:8080/oracle/btcusd | jq .
```

lnget caches L402 tokens, so repeated requests to the same endpoint reuse the token until it expires.

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

data = fetch_oracle("http://104.197.109.246:8080/oracle/btcusd")
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

ORACLE_URL = "http://104.197.109.246:8080/oracle/btcusd"

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
v1|BTCUSD|96482.15|USD|2|2026-02-13T18:44:30Z|890123|coinbase,kraken,bitstamp|median
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
nonce     = parts[6]  # "890123"
sources   = parts[7]  # "coinbase,kraken,bitstamp"
method    = parts[8]  # "median"
```

## Quorum Pattern

For production use, query multiple oracles and aggregate:
```python
import statistics

ORACLES = [
    "http://104.197.109.246:8080/oracle/btcusd",       # 10 sats
    "http://104.197.109.246:8080/oracle/btcusd/vwap",   # 20 sats
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

- Spot query (BTC, ETH, EUR, XAU, BTC/EUR, SOL): **10 sats** (~$0.007)
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
```

---

Add that to `docs/CLIENT_INTEGRATION.md`. How's the channel looking?
```
curl -k --header "Grpc-Metadata-macaroon: %MAC%" https://mycelia.m.voltageapp.io:8080/v1/channels/pending
