# Mycelia Signal — Client Integration Guide

How to consume Mycelia Signal oracle data in your application.

**Base URL:** `https://api.myceliasignal.com`  
**Docs:** https://myceliasignal.com/docs  
**56 endpoints** — crypto, FX, economic indicators, commodities

---

## Payment Rails

### L402 — Lightning Network

Pay Lightning sats, receive secp256k1 ECDSA-signed attestations.

- Spot/FX/metals: **10 sats**
- VWAP: **20 sats**
- Economic indicators / commodities: **1,000 sats**

### x402 — USDC on Base

Pay USDC on Base L2, receive Ed25519-signed attestations.

- Spot/FX/metals: **$0.01 USDC**
- VWAP: **$0.02 USDC**
- Economic indicators / commodities: **$1.00 USDC**

### Preview (Free)

All endpoints have a free preview route that returns unsigned, cached data:

```
GET https://api.myceliasignal.com/oracle/price/btc/usd/preview
GET https://api.myceliasignal.com/oracle/econ/us/cpi/preview
```

---

## Endpoint Format

```
# Price endpoints
GET /oracle/price/{base}/{quote}
GET /oracle/price/{base}/{quote}/vwap

# Economic indicators
GET /oracle/econ/us/{indicator}
GET /oracle/econ/eu/{indicator}
GET /oracle/econ/commodities/{indicator}

# L402 prefix (Lightning payment)
GET /l402/oracle/price/{base}/{quote}
GET /l402/oracle/econ/us/{indicator}
```

Examples:
```
/oracle/price/btc/usd          BTC/USD spot
/oracle/price/btc/usd/vwap     BTC/USD 5-min VWAP
/oracle/price/eur/usd          EUR/USD
/oracle/econ/us/cpi            US CPI
/oracle/econ/eu/hicp           EU HICP
/oracle/econ/commodities/wti   WTI Crude Oil
```

---

## Python — x402 (USDC on Base)

```python
import httpx
import base64
import json
import os
from eth_account import Account
from eth_account.messages import encode_defunct

API_BASE = "https://api.myceliasignal.com"
PRIVATE_KEY = os.environ["ETH_PRIVATE_KEY"]

def fetch_oracle_x402(endpoint: str) -> dict:
    # Step 1: Request to get 402 + payment requirements
    r = httpx.get(f"{API_BASE}{endpoint}")
    if r.status_code != 402:
        return r.json()

    body = r.json()
    req = body["accepts"][0]

    # Step 2: Build and sign EIP-3009 transferWithAuthorization
    # (See x402 docs for full EIP-712 signing implementation)
    # https://myceliasignal.com/docs/x402

    # Step 3: Encode payment and retry
    payment_payload = { ... }  # See docs for full structure
    x_payment = base64.b64encode(json.dumps(payment_payload).encode()).decode()

    r2 = httpx.get(f"{API_BASE}{endpoint}", headers={"X-PAYMENT": x_payment})
    return r2.json()

data = fetch_oracle_x402("/oracle/price/btc/usd")
```

---

## Python — L402 (Lightning)

```python
import httpx
import re

API_BASE = "https://api.myceliasignal.com"

def fetch_oracle_l402(endpoint: str, pay_invoice_fn) -> dict:
    """
    pay_invoice_fn: callable that takes a Lightning invoice string
                    and returns the payment preimage hex string
    """
    # Step 1: Request to get 402 + invoice
    r = httpx.get(f"{API_BASE}/l402{endpoint}")
    if r.status_code != 402:
        return r.json()

    # Parse macaroon and invoice from WWW-Authenticate header
    www_auth = r.headers.get("WWW-Authenticate", "")
    macaroon_match = re.search(r'macaroon="([^"]+)"', www_auth)
    invoice_match = re.search(r'invoice="([^"]+)"', www_auth)

    if not macaroon_match or not invoice_match:
        body = r.json()
        macaroon = body.get("macaroon")
        invoice = body.get("invoice")
    else:
        macaroon = macaroon_match.group(1)
        invoice = invoice_match.group(1)

    # Step 2: Pay the invoice
    preimage = pay_invoice_fn(invoice)

    # Step 3: Retry with L402 credentials
    r2 = httpx.get(
        f"{API_BASE}/l402{endpoint}",
        headers={"Authorization": f"L402 {macaroon}:{preimage}"}
    )
    return r2.json()

# Example with lnget or any Lightning wallet integration
data = fetch_oracle_l402("/oracle/price/btc/usd", pay_invoice_fn=your_wallet.pay)
```

---

## Parsing the Response

### Price response (PRICE canonical)

```python
def parse_price_response(data: dict) -> dict:
    # canonical field for price endpoints
    canonical = data.get("canonical") or data.get("canonicalstring", "")
    parts = canonical.split("|")

    # Spec v0.4: v1|PRICE|PAIR|VALUE|CURRENCY|DECIMALS|SOURCES|METHOD|TIMESTAMP|NONCE
    return {
        "version":   parts[0],   # "v1"
        "type":      parts[1],   # "PRICE"
        "pair":      parts[2],   # "BTCUSD"
        "price":     parts[3],   # "84231.50"
        "currency":  parts[4],   # "USD"
        "decimals":  parts[5],   # "2"
        "sources":   parts[6].split(","),  # ["binance","coinbase",...]
        "method":    parts[7],   # "median"
        "timestamp": parts[8],   # "1741521600"
        "nonce":     parts[9],   # "562204"
        "signature": data.get("signature"),
        "pubkey":    data.get("pubkey"),
    }

data = fetch_oracle_x402("/oracle/price/btc/usd")
parsed = parse_price_response(data)
print(f"BTC/USD: {parsed['price']} {parsed['currency']}")
print(f"Sources: {', '.join(parsed['sources'])}")
print(f"Timestamp: {parsed['timestamp']}")
```

### Economic indicator response (ECON canonical)

```python
def parse_econ_response(data: dict) -> dict:
    # econ endpoints use "canonicalstring" not "canonical"
    canonical = data.get("canonicalstring") or data.get("canonical", "")
    parts = canonical.split("|")

    # Spec v0.4: v1|ECON|REGION|INDICATOR|VALUE|UNIT|PERIOD|VINTAGEDATE|SOURCEAGENCY|SERIESID|SOURCEMODEL|TIMESTAMP|NONCE
    return {
        "version":       parts[0],   # "v1"
        "type":          parts[1],   # "ECON"
        "region":        parts[2],   # "US"
        "indicator":     parts[3],   # "CPI"
        "value":         parts[4],   # "326.785"
        "unit":          parts[5],   # "index198284100"
        "period":        parts[6],   # "2026-02"
        "vintagedate":   parts[7],   # "2026-03-21"
        "sourceagency":  parts[8],   # "BLS"
        "seriesid":      parts[9],   # "CUUR0000SA0"
        "sourcemodel":   parts[10],  # "directapi"
        "timestamp":     parts[11],  # "1774087200"
        "nonce":         parts[12],  # "631660"
    }

data = fetch_oracle_x402("/oracle/econ/us/cpi")
parsed = parse_econ_response(data)
print(f"US CPI: {parsed['value']} {parsed['unit']} ({parsed['period']})")
```

---

## JavaScript / TypeScript

```typescript
const API_BASE = "https://api.myceliasignal.com";

interface PriceAttestation {
    pair: string;
    price: string;
    currency: string;
    sources: string[];
    timestamp: string;
    signature: string;
    pubkey: string;
}

function parseCanonical(data: any): PriceAttestation {
    const canonical: string = data.canonical ?? data.canonicalstring ?? "";
    const parts = canonical.split("|");
    const type = parts[1];

    if (type === "PRICE") {
        // v1|PRICE|PAIR|VALUE|CURRENCY|DECIMALS|SOURCES|METHOD|TIMESTAMP|NONCE
        return {
            pair:      parts[2],
            price:     parts[3],
            currency:  parts[4],
            sources:   parts[6]?.split(",") ?? [],
            timestamp: parts[8],
            signature: data.signature,
            pubkey:    data.pubkey,
        };
    } else {
        // ECON: v1|ECON|REGION|INDICATOR|VALUE|UNIT|...|TIMESTAMP|NONCE
        return {
            pair:      `${parts[2]}/${parts[3]}`,
            price:     parts[4],
            currency:  parts[5],
            sources:   [parts[8] ?? ""],
            timestamp: parts[11],
            signature: data.signature,
            pubkey:    data.pubkey,
        };
    }
}

// Preview (free, no payment)
const preview = await fetch(`${API_BASE}/oracle/price/btc/usd/preview`);
const data = await preview.json();
const parsed = parseCanonical(data);
console.log(`BTC/USD: ${parsed.price} (preview, unsigned)`);
```

---

## Go

```go
package main

import (
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "strings"
)

const APIBase = "https://api.myceliasignal.com"

type OracleResponse struct {
    Canonical       string `json:"canonical"`
    CanonicalString string `json:"canonicalstring"`
    Signature       string `json:"signature"`
    Pubkey          string `json:"pubkey"`
}

type ParsedAttestation struct {
    Pair      string
    Price     string
    Currency  string
    Sources   []string
    Timestamp string
    Signature string
    Pubkey    string
}

func ParseCanonical(resp OracleResponse) ParsedAttestation {
    canonical := resp.Canonical
    if canonical == "" {
        canonical = resp.CanonicalString
    }
    parts := strings.Split(canonical, "|")

    // PRICE: v1|PRICE|PAIR|VALUE|CURRENCY|DECIMALS|SOURCES|METHOD|TIMESTAMP|NONCE
    if len(parts) >= 10 && parts[1] == "PRICE" {
        return ParsedAttestation{
            Pair:      parts[2],
            Price:     parts[3],
            Currency:  parts[4],
            Sources:   strings.Split(parts[6], ","),
            Timestamp: parts[8],
            Signature: resp.Signature,
            Pubkey:    resp.Pubkey,
        }
    }

    // ECON: v1|ECON|REGION|INDICATOR|VALUE|UNIT|...|TIMESTAMP|NONCE
    return ParsedAttestation{
        Pair:      parts[2] + "/" + parts[3],
        Price:     parts[4],
        Currency:  parts[5],
        Sources:   []string{parts[8]},
        Timestamp: parts[11],
        Signature: resp.Signature,
        Pubkey:    resp.Pubkey,
    }
}

func fetchPreview(endpoint string) (*ParsedAttestation, error) {
    r, err := http.Get(APIBase + endpoint + "/preview")
    if err != nil {
        return nil, err
    }
    defer r.Body.Close()
    body, _ := io.ReadAll(r.Body)

    var resp OracleResponse
    if err := json.Unmarshal(body, &resp); err != nil {
        return nil, err
    }
    parsed := ParseCanonical(resp)
    return &parsed, nil
}

func main() {
    data, err := fetchPreview("/oracle/price/btc/usd")
    if err != nil {
        panic(err)
    }
    fmt.Printf("BTC/USD: %s %s\n", data.Price, data.Currency)
    fmt.Printf("Sources: %s\n", strings.Join(data.Sources, ", "))
}
```

---

## Signature Verification

See the full verification guide at https://myceliasignal.com/docs/verification

**Signing process (both protocols):**
1. UTF-8 encode the canonical string
2. SHA-256 hash the encoded bytes
3. Sign the hash

**L402 responses:** secp256k1 ECDSA, DER-encoded, base64  
**x402 responses:** Ed25519, raw 64 bytes, base64

```python
import hashlib
import base64
from coincurve import PublicKey  # secp256k1 (L402)
# from nacl.signing import VerifyKey  # Ed25519 (x402)

def verify_l402(data: dict) -> bool:
    canonical = (data.get("canonical") or data.get("canonicalstring", "")).encode("utf-8")
    digest = hashlib.sha256(canonical).digest()
    sig = base64.b64decode(data["signature"])
    pubkey = PublicKey(bytes.fromhex(data["pubkey"]))
    return pubkey.verify(sig, digest, hasher=None)
```

---

## Public Keys

| Instance | Protocol | Key |
|----------|----------|-----|
| US GC    | L402 (secp256k1) | `03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf` |
| Asia GC  | L402 (secp256k1) | `02b1377c30c7dcfcba428cf299c18782856a12eb4fab32b87081460f4ba2deab73` |
| US GC    | x402 (Ed25519)   | `f4f0e52b5f7b54831f965632bf1ebf72769beda4c4e3d36a593f7729ec812615` |
| Asia GC  | x402 (Ed25519)   | `7ab07fbe7d08cd16823e5eb0db0e21f3f38e9366d5fd00d14e95df0fb9b51a1a` |

All keys at https://myceliasignal.com/docs/keys

---

## Resources

- Full docs: https://myceliasignal.com/docs
- x402 integration: https://myceliasignal.com/docs/x402
- L402 integration: https://myceliasignal.com/docs/l402
- Signature verification: https://myceliasignal.com/docs/verification
- All endpoints: https://myceliasignal.com/docs/endpoints
- OpenAPI spec: https://myceliasignal.com/openapi.json
