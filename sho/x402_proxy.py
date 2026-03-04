# sho/x402_proxy.py
"""
SHO — Sovereign HTTP Oracle x402 Proxy
Standard x402 Protocol Implementation

x402-compatible payment proxy for the Sovereign Lightning Oracle.
Uses the standard x402 payment flow with the Coinbase CDP facilitator
for EIP-3009 payment verification and settlement on Base.

Flow:
  1. Client → GET /oracle/btcusd (no X-PAYMENT header)
  2. Server → 402 + PaymentRequirements (standard x402 body + PAYMENT-REQUIRED header)
  3. Client signs EIP-3009 transferWithAuthorization (EIP-712)
  4. Client → GET /oracle/btcusd + X-PAYMENT: <base64 PaymentPayload>
  5. Server → CDP facilitator /verify + /settle
  6. Server → 200 + attestation + X-PAYMENT-RESPONSE header

Architecture:
  Consumer → SHO x402 Proxy (:8402) → Oracle Backend (:9100-9107)
                                    ↕
                              CDP Facilitator (verify + settle)
"""

import hashlib
import json
import os
import time
import base64
import secrets
import logging
from pathlib import Path

import httpx
import jwt as pyjwt
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from nacl.signing import SigningKey
from nacl.encoding import HexEncoder


# ── Configuration ─────────────────────────────────────────────────────────────

BASE_RPC_URL = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on Base
PAYMENT_ADDRESS = os.environ.get("SHO_PAYMENT_ADDRESS", "")
DEPEG_THRESHOLD = float(os.environ.get("DEPEG_THRESHOLD", "0.02"))  # 2%

SHO_PORT = int(os.environ.get("SHO_PORT", "8402"))
KEYS_DIR = Path(os.environ.get("SHO_KEYS_DIR", str(Path(__file__).parent / "keys")))

# CDP Facilitator
CDP_API_KEY_ID = os.environ.get("CDP_API_KEY_ID", "")
CDP_API_KEY_SECRET = os.environ.get("CDP_API_KEY_SECRET", "")
CDP_FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402"

# x402 protocol constants
X402_NETWORK = "eip155:8453"  # Base mainnet (CAIP-2)
X402_SCHEME = "exact"
USDC_DECIMALS = 6

# ── Oracle Backend Routes ─────────────────────────────────────────────────────

ROUTES = {
    "/oracle/btcusd":      {"backend": "http://127.0.0.1:9100/oracle/btcusd",      "price_usd": 0.001, "description": "BTC/USD spot price — Ed25519-signed attestation"},
    "/oracle/btcusd/vwap": {"backend": "http://127.0.0.1:9101/oracle/btcusd/vwap",  "price_usd": 0.002, "description": "BTC/USD VWAP — Ed25519-signed attestation"},
    "/oracle/ethusd":      {"backend": "http://127.0.0.1:9102/oracle/ethusd",      "price_usd": 0.001, "description": "ETH/USD spot price — Ed25519-signed attestation"},
    "/oracle/eurusd":      {"backend": "http://127.0.0.1:9103/oracle/eurusd",      "price_usd": 0.001, "description": "EUR/USD spot price — Ed25519-signed attestation"},
    "/oracle/xauusd":      {"backend": "http://127.0.0.1:9105/oracle/xauusd",      "price_usd": 0.001, "description": "XAU/USD spot price — Ed25519-signed attestation"},
    "/oracle/btceur":      {"backend": "http://127.0.0.1:9106/oracle/btceur",      "price_usd": 0.001, "description": "BTC/EUR spot price — Ed25519-signed attestation"},
    "/oracle/solusd":      {"backend": "http://127.0.0.1:9107/oracle/solusd",      "price_usd": 0.001, "description": "SOL/USD spot price — Ed25519-signed attestation"},
    "/oracle/etheur":      {"backend": "http://127.0.0.1:9108/oracle/etheur",      "price_usd": 0.001, "description": "ETH/EUR spot price — Ed25519-signed attestation"},
    "/oracle/soleur":      {"backend": "http://127.0.0.1:9109/oracle/soleur",      "price_usd": 0.001, "description": "SOL/EUR spot price — Ed25519-signed attestation"},
    "/oracle/xaueur":      {"backend": "http://127.0.0.1:9110/oracle/xaueur",      "price_usd": 0.001, "description": "XAU/EUR spot price — Ed25519-signed attestation"},
    "/oracle/btceur/vwap": {"backend": "http://127.0.0.1:9111/oracle/btceur/vwap",  "price_usd": 0.002, "description": "BTC/EUR VWAP — Ed25519-signed attestation"},
}

FREE_ROUTES = {
    "/health":   "http://127.0.0.1:9100/health",
    "/sho/info": None,  # handled internally
}

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SHO] %(message)s")
log = logging.getLogger("sho")


# ══════════════════════════════════════════════════════════════════════════════
# CDP JWT Authentication
# ══════════════════════════════════════════════════════════════════════════════

def _load_cdp_signing_key():
    """
    Load the CDP signing key. CDP secrets are either:
    - Ed25519: base64-encoded 64 bytes (32-byte seed + 32-byte pubkey)
    - EC (ES256): PEM-encoded private key
    Returns (key_object, algorithm) for PyJWT.
    """
    secret = CDP_API_KEY_SECRET
    if not secret:
        return None, None

    if secret.startswith("-----BEGIN EC PRIVATE KEY-----"):
        # ES256 PEM key — PyJWT accepts this directly
        return secret, "ES256"
    else:
        # Ed25519 key — base64-encoded, 64 bytes (seed + pubkey)
        # PyJWT EdDSA expects an Ed25519PrivateKey object from cryptography
        import base64 as b64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        decoded = b64.b64decode(secret)
        if len(decoded) == 64:
            # First 32 bytes are the seed (private key)
            seed = decoded[:32]
        elif len(decoded) == 32:
            seed = decoded
        else:
            raise ValueError(f"CDP Ed25519 key: unexpected length {len(decoded)}, expected 32 or 64")

        private_key = Ed25519PrivateKey.from_private_bytes(seed)
        return private_key, "EdDSA"


# Pre-load the signing key at module level
_CDP_SIGNING_KEY, _CDP_ALGORITHM = _load_cdp_signing_key()


def create_cdp_jwt(method: str, path: str) -> str:
    """
    Generate a CDP JWT for authenticating with the Coinbase facilitator.
    Follows the exact format from Coinbase's JWT authentication docs.
    """
    if not _CDP_SIGNING_KEY:
        raise RuntimeError("CDP signing key not configured")

    now = int(time.time())
    uri = f"{method} api.cdp.coinbase.com{path}"

    payload = {
        "sub": CDP_API_KEY_ID,
        "iss": "cdp",
        "aud": ["cdp_service"],
        "nbf": now,
        "exp": now + 120,  # 2 minute expiry
        "uris": [uri],
    }

    headers = {
        "kid": CDP_API_KEY_ID,
        "typ": "JWT",
        "nonce": secrets.token_hex(16),
    }

    token = pyjwt.encode(payload, _CDP_SIGNING_KEY, algorithm=_CDP_ALGORITHM, headers=headers)
    return token


def create_cdp_auth_headers() -> dict[str, dict[str, str]]:
    """
    Create auth headers for CDP facilitator calls.

    The x402 SDK expects create_headers to return a nested dict:
      {"verify": {headers}, "settle": {headers}}
    Each with a JWT scoped to the specific endpoint path.
    """
    verify_jwt = create_cdp_jwt("POST", "/platform/v2/x402/verify")
    settle_jwt = create_cdp_jwt("POST", "/platform/v2/x402/settle")
    return {
        "verify": {"Authorization": f"Bearer {verify_jwt}"},
        "settle": {"Authorization": f"Bearer {settle_jwt}"},
    }


# ══════════════════════════════════════════════════════════════════════════════
# x402 Facilitator Client
# ══════════════════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════════════════
# Ed25519 Key Management
# ══════════════════════════════════════════════════════════════════════════════

def load_or_create_ed25519_key() -> SigningKey:
    """Load existing Ed25519 key or generate a new one."""
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    sk_path = KEYS_DIR / "sho_ed25519.key"

    if sk_path.exists():
        sk_hex = sk_path.read_text().strip()
        sk = SigningKey(bytes.fromhex(sk_hex))
        log.info(f"Loaded Ed25519 key: {sk.verify_key.encode(HexEncoder).decode()[:16]}...")
        return sk

    sk = SigningKey.generate()
    sk_path.write_text(sk.encode(HexEncoder).decode())
    os.chmod(str(sk_path), 0o600)
    log.info(f"Generated new Ed25519 key: {sk.verify_key.encode(HexEncoder).decode()[:16]}...")
    return sk


ED25519_SK = load_or_create_ed25519_key()
ED25519_PK = ED25519_SK.verify_key


def ed25519_sign(canonical: str) -> str:
    """Sign a canonical message string with Ed25519, return base64 signature."""
    msg_hash = hashlib.sha256(canonical.encode()).digest()
    signed = ED25519_SK.sign(msg_hash)
    return base64.b64encode(signed.signature).decode()


# ══════════════════════════════════════════════════════════════════════════════
# Payment Requirements Builder
# ══════════════════════════════════════════════════════════════════════════════

def build_payment_requirements(route_path: str, route: dict) -> dict:
    """Build a standard x402 PaymentRequirements object for an endpoint."""
    amount_atomic = str(int(route["price_usd"] * (10 ** USDC_DECIMALS)))
    return {
        "scheme": X402_SCHEME,
        "network": X402_NETWORK,
        "maxAmountRequired": amount_atomic,
        "resource": f"https://api.myceliasignal.com{route_path}",
        "description": route["description"],
        "mimeType": "application/json",
        "payTo": PAYMENT_ADDRESS,
        "maxTimeoutSeconds": 60,
        "asset": USDC_CONTRACT,
        "extra": {
            "name": "USD Coin",
            "version": "2"
        }
    }


def build_402_response(requirements: dict) -> tuple[dict, dict]:
    """
    Build the standard 402 response body and headers.
    Body: JSON with x402Version, accepts array, and error message.
    Header: PAYMENT-REQUIRED with base64-encoded requirements.
    """
    body = {
        "x402Version": 1,
        "accepts": [requirements],
        "error": "X-PAYMENT header is required",
    }

    # PAYMENT-REQUIRED header: base64-encoded JSON of the accepts array wrapper
    header_payload = {
        "x402Version": 1,
        "accepts": [requirements],
    }
    payment_required_header = base64.b64encode(
        json.dumps(header_payload).encode()
    ).decode()

    headers = {
        "PAYMENT-REQUIRED": payment_required_header,
    }

    return body, headers


# ══════════════════════════════════════════════════════════════════════════════
# Tiered Enforcement
# ══════════════════════════════════════════════════════════════════════════════

# In-memory enforcement state
_failure_log: dict[str, list[float]] = {}
_hard_blocked: set[str] = set()

GRACE_COOLDOWN_SECONDS = 600        # 10 minutes
HARD_BLOCK_THRESHOLD = 10           # failures in rolling window
HARD_BLOCK_WINDOW_SECONDS = 604800  # 7 days


def check_enforcement(payment_address: str) -> dict:
    """Check if a payment address is blocked or in cooldown."""
    addr = payment_address.lower()

    if addr in _hard_blocked:
        return {"allowed": False, "reason": "hard_blocked", "tier": 3}

    now = time.time()
    if addr in _failure_log:
        _failure_log[addr] = [
            t for t in _failure_log[addr]
            if now - t < HARD_BLOCK_WINDOW_SECONDS
        ]
        failures = _failure_log[addr]

        if len(failures) >= HARD_BLOCK_THRESHOLD:
            _hard_blocked.add(addr)
            log.warning(f"HARD BLOCK: {addr} ({len(failures)} failures in 7d)")
            return {"allowed": False, "reason": "hard_blocked", "tier": 3}

        if failures and (now - failures[-1]) < GRACE_COOLDOWN_SECONDS:
            remaining = int(GRACE_COOLDOWN_SECONDS - (now - failures[-1]))
            return {"allowed": False, "reason": f"cooldown_{remaining}s", "tier": 1}

    return {"allowed": True, "reason": None, "tier": 0}


def record_failure(payment_address: str):
    """Record a payment failure for tiered enforcement."""
    addr = payment_address.lower()
    if addr not in _failure_log:
        _failure_log[addr] = []
    _failure_log[addr].append(time.time())
    log.info(f"Payment failure recorded: {addr} (total: {len(_failure_log[addr])})")


def record_success(payment_address: str):
    """Record a successful payment."""
    pass


# ══════════════════════════════════════════════════════════════════════════════
# Depeg Circuit Breaker
# ══════════════════════════════════════════════════════════════════════════════

_depeg_active = False
_last_depeg_check = 0.0
DEPEG_CHECK_INTERVAL = 60


async def check_depeg() -> dict:
    """Check USDC/USD peg using multiple exchange sources."""
    global _depeg_active, _last_depeg_check

    now = time.time()
    if now - _last_depeg_check < DEPEG_CHECK_INTERVAL:
        return {"pegged": not _depeg_active, "rate": None, "sources": 0}

    _last_depeg_check = now

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            rates = []

            try:
                r = await client.get("https://api.kraken.com/0/public/Ticker?pair=USDCUSD")
                d = r.json()
                rates.append(float(d["result"]["USDCUSD"]["c"][0]))
            except Exception:
                pass

            try:
                r = await client.get("https://www.bitstamp.net/api/v2/ticker/usdcusd/")
                rates.append(float(r.json()["last"]))
            except Exception:
                pass

            try:
                r = await client.get("https://api.exchange.coinbase.com/products/USDT-USDC/ticker")
                rates.append(float(r.json()["price"]))
            except Exception:
                pass

            try:
                r = await client.get("https://api.gemini.com/v1/pubticker/usdcusd")
                rates.append(float(r.json()["last"]))
            except Exception:
                pass

            try:
                r = await client.get("https://api-pub.bitfinex.com/v2/ticker/tUDCUSD")
                rates.append(float(r.json()[6]))
            except Exception:
                pass

            if len(rates) < 2:
                log.warning(f"Depeg check: only {len(rates)} sources available, need 2")
                return {"pegged": not _depeg_active, "rate": None, "sources": len(rates)}

            import statistics
            usdc_rate = statistics.median(rates)
            deviation = abs(usdc_rate - 1.0)

            if deviation > DEPEG_THRESHOLD:
                if not _depeg_active:
                    log.warning(f"DEPEG CIRCUIT BREAKER ACTIVE: USDC/USD = {usdc_rate:.4f} ({len(rates)} sources)")
                _depeg_active = True
                return {"pegged": False, "rate": usdc_rate, "sources": len(rates)}
            else:
                if _depeg_active:
                    log.info(f"Depeg circuit breaker cleared: USDC/USD = {usdc_rate:.4f} ({len(rates)} sources)")
                _depeg_active = False
                return {"pegged": True, "rate": usdc_rate, "sources": len(rates)}

    except Exception as e:
        log.error(f"Depeg check error: {e}")
        return {"pegged": not _depeg_active, "rate": None, "sources": 0}


# ══════════════════════════════════════════════════════════════════════════════
# x402 Payment Verification & Settlement
# ══════════════════════════════════════════════════════════════════════════════

async def verify_and_settle_payment(
    x_payment_b64: str,
    requirements: dict,
) -> tuple[bool, str | None, dict | None]:
    try:
        payload_json = base64.b64decode(x_payment_b64)
        payload_dict = json.loads(payload_json)
    except Exception as e:
        return False, f"invalid_x_payment_encoding: {e}", None
    # Clean payload for CDP V1: only x402Version, scheme, network, payload
    cdp_payload = {
        "x402Version": payload_dict.get("x402Version", 1),
        "scheme": payload_dict.get("scheme", "exact"),
        "network": "base",
        "payload": payload_dict.get("payload", {}),
    }
    cdp_requirements = dict(requirements)
    cdp_requirements["network"] = "base"
    auth_headers = create_cdp_auth_headers()
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            verify_resp = await client.post(
                f"{CDP_FACILITATOR_URL}/verify",
                json={"x402Version": 1, "paymentPayload": cdp_payload, "paymentRequirements": cdp_requirements},
                headers={**auth_headers["verify"], "Content-Type": "application/json"},
            )
            if verify_resp.status_code != 200:
                return False, f"facilitator_verify_failed ({verify_resp.status_code}): {verify_resp.text} | SENT: {json.dumps(cdp_payload, default=str)[:500]}", None
            verify_data = verify_resp.json()
            if not verify_data.get("isValid", False):
                return False, f"verification_failed: {verify_data.get('invalidReason', 'unknown')}", None
        except Exception as e:
            return False, f"facilitator_verify_error: {e}", None
        try:
            settle_resp = await client.post(
                f"{CDP_FACILITATOR_URL}/settle",
                json={"x402Version": 1, "paymentPayload": cdp_payload, "paymentRequirements": cdp_requirements},
                headers={**auth_headers["settle"], "Content-Type": "application/json"},
            )
            if settle_resp.status_code != 200:
                return False, f"facilitator_settle_failed ({settle_resp.status_code}): {settle_resp.text}", None
            settle_data = settle_resp.json()
            if not settle_data.get("success", False):
                return False, f"settlement_failed: {settle_data.get('errorReason', 'unknown')}", None
        except Exception as e:
            return False, f"facilitator_settle_error: {e}", None
    log.info(f"Payment settled: tx={settle_data.get('transaction')} network={settle_data.get('network')}")
    return True, None, settle_data



# ══════════════════════════════════════════════════════════════════════════════
# FastAPI Application
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="SHO — Sovereign HTTP Oracle", version="0.2.1")
# [PROMETHEUS INSTRUMENTED]
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)



@app.get("/health")
async def health():
    return {"status": "ok", "protocol": "x402", "version": "0.2.1"}


@app.get("/sho/info")
async def sho_info():
    """Public info endpoint — no payment required."""
    depeg = await check_depeg()
    return {
        "protocol": "x402",
        "version": "0.2.1",
        "x402Version": 1,
        "signing_scheme": "ed25519",
        "pubkey": ED25519_PK.encode(HexEncoder).decode(),
        "payment_network": X402_NETWORK,
        "payment_scheme": X402_SCHEME,
        "payment_asset": USDC_CONTRACT,
        "payment_address": PAYMENT_ADDRESS,
        "facilitator": CDP_FACILITATOR_URL,
        "depeg_active": not depeg["pegged"],
        "endpoints": {
            path: {
                "price_usd": r["price_usd"],
                "maxAmountRequired": str(int(r["price_usd"] * (10 ** USDC_DECIMALS))),
            }
            for path, r in ROUTES.items()
        },
    }


@app.get("/sho/enforcement/{address}")
async def enforcement_status(address: str):
    """Check enforcement status for a payment address (public)."""
    return check_enforcement(address)


@app.api_route("/{path:path}", methods=["GET"])
async def main_handler(request: Request, path: str):
    """Main x402 handler for oracle endpoints."""
    route_path = "/" + path

    # ── Free routes ──
    if route_path in FREE_ROUTES:
        backend = FREE_ROUTES[route_path]
        if backend is None:
            return JSONResponse({"error": "use specific endpoint"}, status_code=404)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(backend)
            return JSONResponse(resp.json())

    # ── Paid route lookup ──
    route = ROUTES.get(route_path)
    if route is None:
        return JSONResponse({"error": "not_found"}, status_code=404)

    # ── Depeg circuit breaker ──
    depeg = await check_depeg()
    if not depeg["pegged"]:
        return JSONResponse({
            "error": "depeg_circuit_breaker",
            "message": "USDC payment suspended — stablecoin deviation exceeds threshold",
            "usdc_rate": depeg["rate"],
            "threshold": DEPEG_THRESHOLD,
        }, status_code=503)

    # ── Build payment requirements for this endpoint ──
    requirements = build_payment_requirements(route_path, route)

    # ── Check for X-PAYMENT header (standard x402) ──
    # Starlette headers are case-insensitive
    x_payment = request.headers.get("X-PAYMENT")

    if not x_payment:
        # No payment — return standard 402 response
        body, headers = build_402_response(requirements)
        return JSONResponse(body, status_code=402, headers=headers)

    # ── Extract payer address from payload for enforcement ──
    try:
        payload_dict = json.loads(base64.b64decode(x_payment))
        # EIP-3009 authorization contains the 'from' address
        from_address = (
            payload_dict.get("payload", {})
            .get("authorization", {})
            .get("from", "unknown")
        )
    except Exception:
        from_address = "unknown"

    # ── Check enforcement ──
    if from_address != "unknown":
        enforcement = check_enforcement(from_address)
        if not enforcement["allowed"]:
            return JSONResponse({
                "error": "payment_address_blocked",
                "reason": enforcement["reason"],
                "tier": enforcement["tier"],
            }, status_code=403)

    # ── Verify and settle payment via CDP facilitator ──
    success, error, settle_resp = await verify_and_settle_payment(x_payment, requirements)

    if not success:
        if from_address != "unknown":
            record_failure(from_address)
        return JSONResponse({
            "error": "payment_verification_failed",
            "detail": error,
        }, status_code=402)

    # ── Payment accepted — fetch attestation from backend ──
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(route["backend"])
            backend_data = resp.json()
    except Exception as e:
        log.error(f"Backend error: {e}")
        return JSONResponse({"error": "oracle_backend_error"}, status_code=502)

    # ── Re-sign with Ed25519 ──
    canonical = backend_data.get("canonical", "")
    if not canonical:
        return JSONResponse({"error": "backend_missing_canonical"}, status_code=502)

    ed25519_sig = ed25519_sign(canonical)

    if from_address != "unknown":
        record_success(from_address)

    # ── Build X-PAYMENT-RESPONSE header ──
    payment_response = settle_resp if settle_resp else {}

    payment_response_header = base64.b64encode(
        json.dumps(payment_response).encode()
    ).decode()

    # ── Return attestation with Ed25519 signature ──
    return JSONResponse(
        {
            "domain": backend_data.get("domain", ""),
            "canonical": canonical,
            "signature": ed25519_sig,
            "signing_scheme": "ed25519",
            "pubkey": ED25519_PK.encode(HexEncoder).decode(),
            "payment": {
                "protocol": "x402",
                "network": X402_NETWORK,
                "settled": True,
            },
        },
        headers={
            "X-PAYMENT-RESPONSE": payment_response_header,
        },
    )


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    log.info(f"SHO x402 Proxy v0.2.1 starting on :{SHO_PORT}")
    log.info(f"Ed25519 pubkey: {ED25519_PK.encode(HexEncoder).decode()}")
    log.info(f"Payment address: {PAYMENT_ADDRESS}")
    log.info(f"Network: {X402_NETWORK}")
    log.info(f"Facilitator: {CDP_FACILITATOR_URL}")
    log.info(f"CDP auth: {'configured' if CDP_API_KEY_ID else 'MISSING'}")


# ══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    missing = []
    if not PAYMENT_ADDRESS:
        missing.append("SHO_PAYMENT_ADDRESS")
    if not CDP_API_KEY_ID:
        missing.append("CDP_API_KEY_ID")
    if not CDP_API_KEY_SECRET:
        missing.append("CDP_API_KEY_SECRET")

    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        exit(1)

    uvicorn.run(app, host="0.0.0.0", port=SHO_PORT)
