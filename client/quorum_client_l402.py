"""
Mycelia Signal Quorum Client — L402 (Lightning)

Queries multiple Mycelia Signal oracle endpoints, verifies signatures,
enforces price coherence, and returns a quorum-validated median price.

Payment flow:
  1. Client sends GET to L402-gated endpoint
  2. Server returns HTTP 402 + Lightning invoice + macaroon
  3. Client pays invoice via lnget (automatic) or manual wallet
  4. Client retries with Authorization: L402 <macaroon>:<preimage>
  5. Oracle returns signed attestation

Usage:
  python quorum_client_l402.py
  python quorum_client_l402.py --pair EURUSD
  python quorum_client_l402.py --pair BTCUSD --backend lnget
  python quorum_client_l402.py --oracles https://api.myceliasignal.com/oracle/price/btc/usd https://api.myceliasignal.com/oracle/price/btc/usd/vwap
"""

import argparse
import base64
import hashlib
import json
import statistics
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

# -------------------------
# Configuration
# -------------------------

# Default oracle set — spot + VWAP for quorum
ORACLE_SETS = {
    "BTCUSD": [
        "https://api.myceliasignal.com/oracle/price/btc/usd",
        "https://api.myceliasignal.com/oracle/price/btc/usd/vwap",
    ],
    "BTCEUR": [
        "https://api.myceliasignal.com/oracle/price/btc/eur",
        "https://api.myceliasignal.com/oracle/price/btc/eur/vwap",
    ],
    "ETHUSD": [
        "https://api.myceliasignal.com/oracle/price/eth/usd",
    ],
    "EURUSD": [
        "https://api.myceliasignal.com/oracle/price/eur/usd",
    ],
    "XAUUSD": [
        "https://api.myceliasignal.com/oracle/price/xau/usd",
    ],
}

# Expected public keys per node — pin for identity verification
# US GC secp256k1 pubkey
EXPECTED_PUBKEYS = {
    "https://api.myceliasignal.com/oracle/price/btc/usd":      "03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf",
    "https://api.myceliasignal.com/oracle/price/btc/usd/vwap": "03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf",
    "https://api.myceliasignal.com/oracle/price/btc/eur":      "03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf",
    "https://api.myceliasignal.com/oracle/price/btc/eur/vwap": "03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf",
    "https://api.myceliasignal.com/oracle/price/eth/usd":      "03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf",
    "https://api.myceliasignal.com/oracle/price/eur/usd":      "03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf",
    "https://api.myceliasignal.com/oracle/price/xau/usd":      "03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf",
}

MIN_RESPONSES    = 2
MAX_DEVIATION_PCT = 0.5   # percent allowed deviation from median
MAX_STALENESS_SEC = 300   # max age of response in seconds

# lnget configuration
LNGET_BIN      = "lnget"
LNGET_MAX_COST = 100   # max sats per request (safety cap)


# -------------------------
# Data structures
# -------------------------
@dataclass
class OracleResponse:
    url:       str
    canonical: str
    price:     float
    pubkey_hex: str
    valid:     bool


# -------------------------
# Payment backends
# -------------------------
def fetch_via_lnget(url: str, max_cost: int = LNGET_MAX_COST) -> Optional[dict]:
    """
    Use lnget (Lightning Labs CLI) to fetch an L402-gated resource.
    lnget handles the full L402 flow transparently.
    Install: go install github.com/lightninglabs/lnget@latest
    """
    try:
        result = subprocess.run(
            [LNGET_BIN, "-k", "-q", url],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise RuntimeError(f"lnget failed: {result.stderr.strip()}")
        return json.loads(result.stdout)
    except FileNotFoundError:
        raise RuntimeError(
            f"lnget not found at '{LNGET_BIN}'. "
            "Install: go install github.com/lightninglabs/lnget@latest"
        )


def fetch_via_manual(url: str) -> Optional[dict]:
    """
    Manual L402 flow using Python requests.
    Requires: LIGHTNING_PREIMAGE env var set to preimage for the current invoice.
    For automated use, implement pay_invoice() with your LND node.
    """
    import os
    import re
    import requests

    r = requests.get(url, timeout=30)
    if r.status_code != 402:
        return r.json()

    auth = r.headers.get("Www-Authenticate", "")
    macaroon_match = re.search(r'macaroon="([^"]+)"', auth)
    invoice_match  = re.search(r'invoice="([^"]+)"', auth)

    if not macaroon_match or not invoice_match:
        raise RuntimeError("Could not parse L402 challenge")

    macaroon = macaroon_match.group(1)
    invoice  = invoice_match.group(1)

    print(f"  Invoice: {invoice}")
    print(f"  Pay the invoice and press Enter, or set LIGHTNING_PREIMAGE env var.")

    preimage = os.environ.get("LIGHTNING_PREIMAGE") or input("  Preimage (hex): ").strip()

    r2 = requests.get(url, headers={"Authorization": f"L402 {macaroon}:{preimage}"}, timeout=30)
    if r2.status_code != 200:
        raise RuntimeError(f"L402 retry failed: {r2.status_code}")
    return r2.json()


BACKENDS = {
    "lnget":  fetch_via_lnget,
    "manual": fetch_via_manual,
}


# -------------------------
# Helpers
# -------------------------
def pct_diff(a, b):
    return abs(a - b) / b * 100


def get_canonical(data: dict) -> str:
    """Get canonical string — handles both field names."""
    return data.get("canonical") or data.get("canonicalstring", "")


def parse_price_from_canonical(canonical: str) -> float:
    """Parse price from canonical string. Handles PRICE type."""
    parts = canonical.split("|")
    if len(parts) < 4:
        raise ValueError(f"Cannot parse canonical: {canonical}")
    msg_type = parts[1]
    if msg_type == "PRICE":
        return float(parts[3])
    else:
        # Econ/commodities — value at index 3
        return float(parts[3])


def verify_oracle_response(data: dict, url: str) -> OracleResponse:
    """Verify secp256k1 signature and parse canonical message."""
    try:
        from coincurve import PublicKey
    except ImportError:
        raise RuntimeError(
            "coincurve required. Install: pip install coincurve"
        )

    canonical  = get_canonical(data)
    pubkey_hex = data.get("pubkey", "")
    sig_b64    = data.get("signature", "")

    if not canonical or not pubkey_hex or not sig_b64:
        return OracleResponse(url=url, canonical=canonical, price=0.0,
                               pubkey_hex=pubkey_hex, valid=False)

    # Verify signature
    valid = False
    try:
        msg_hash = hashlib.sha256(canonical.encode("utf-8")).digest()
        pubkey   = PublicKey(bytes.fromhex(pubkey_hex))
        sig      = base64.b64decode(sig_b64)
        valid    = pubkey.verify(sig, msg_hash, hasher=None)
    except Exception:
        valid = False

    # Verify pubkey matches expected (if configured)
    expected = EXPECTED_PUBKEYS.get(url)
    if expected and pubkey_hex != expected:
        valid = False

    price = 0.0
    try:
        price = parse_price_from_canonical(canonical)
    except Exception:
        valid = False

    return OracleResponse(
        url=url,
        canonical=canonical,
        price=price,
        pubkey_hex=pubkey_hex,
        valid=valid,
    )


# -------------------------
# Client execution
# -------------------------
def run_quorum_client(
    pair: str = "BTCUSD",
    backend_name: str = "lnget",
    oracles: list = None,
):
    pair = pair.upper()
    if oracles is None:
        oracles = ORACLE_SETS.get(pair)
        if not oracles:
            raise ValueError(
                f"Unknown pair '{pair}'. Available: {list(ORACLE_SETS.keys())}\n"
                f"Or pass --oracles with explicit URLs."
            )

    fetch_fn = BACKENDS.get(backend_name)
    if not fetch_fn:
        raise ValueError(
            f"Unknown backend '{backend_name}'. Choose from: {list(BACKENDS.keys())}"
        )

    prices = []
    valid_count = 0

    print("=" * 80)
    print(f"MYCELIA SIGNAL QUORUM CLIENT — {pair} (backend: {backend_name})")
    print("=" * 80)

    for i, url in enumerate(oracles, start=1):
        print(f"\n[Oracle {i}] {url}")

        try:
            print(f"  Fetching...")
            data = fetch_fn(url)

            if not data or "error" in data:
                print(f"  ✗ Oracle error: {data.get('error') if data else 'no data'}")
                continue

            result = verify_oracle_response(data, url)

            if not result.valid:
                print("  ✗ Invalid signature or pubkey mismatch")
                continue

            prices.append(result.price)
            valid_count += 1
            print(f"  Canonical: {result.canonical}")
            print(f"  Pubkey:    {result.pubkey_hex[:16]}...")
            print(f"  Price:     {result.price}")
            print("  ✓ Signature: VALID")

        except Exception as e:
            print(f"  ✗ Oracle failed: {e}")

    # -------------------------
    # Quorum enforcement
    # -------------------------
    if valid_count < MIN_RESPONSES:
        print(f"\n✗ Quorum not met: {valid_count}/{len(oracles)} valid responses (need {MIN_RESPONSES})")
        sys.exit(1)

    median_price = statistics.median(prices)

    for p in prices:
        if pct_diff(p, median_price) > MAX_DEVIATION_PCT:
            print(f"\n✗ Coherence failure: {p} deviates >{MAX_DEVIATION_PCT}% from median {median_price}")
            sys.exit(1)

    print("\n" + "=" * 80)
    print(f"QUORUM RESULT")
    print(f"  Pair:     {pair}")
    print(f"  Median:   {median_price:,.4f}")
    print(f"  Prices:   {prices}")
    print(f"  Oracles:  {valid_count}/{len(oracles)} valid")
    print("=" * 80)

    return median_price


# -------------------------
# CLI
# -------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mycelia Signal Quorum Client (L402)")
    parser.add_argument(
        "--pair",
        default="BTCUSD",
        help="Trading pair to query (default: BTCUSD)"
    )
    parser.add_argument(
        "--backend",
        choices=list(BACKENDS.keys()),
        default="lnget",
        help="Payment backend (default: lnget)"
    )
    parser.add_argument(
        "--oracles",
        nargs="+",
        default=None,
        help="Override oracle URLs (space-separated)"
    )
    args = parser.parse_args()

    run_quorum_client(
        pair=args.pair,
        backend_name=args.backend,
        oracles=args.oracles,
    )
