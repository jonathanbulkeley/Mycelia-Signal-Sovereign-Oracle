import json
import subprocess
import hashlib
import base64
import urllib.request
from fastmcp import FastMCP

mcp = FastMCP(
    name="Sovereign Lightning Oracle",
    instructions=(
        "You have access to a live price oracle supporting 11 trading pairs "
        "(BTC/USD, BTC/USD VWAP, ETH/USD, EUR/USD, XAU/USD, SOL/USD, BTC/EUR, "
        "ETH/EUR, SOL/EUR, XAU/EUR, BTC/EUR VWAP) "
        "with two payment protocols:\n"
        "  • L402 (Lightning): pays real sats automatically via Lightning Network\n"
        "  • x402 (SHO): pays USDC on Base chain via the Sovereign HTTP Oracle\n"
        "Responses are cryptographically signed (secp256k1 for L402, Ed25519 for x402) "
        "and independently verifiable. You also have access to the DLC oracle for "
        "Schnorr-signed hourly BTC/USD attestations with 5-digit numeric decomposition."
    )
)

# ── Base URLs ─────────────────────────────────────────────────────────────────

# L402 proxy (Lightning payments via lnget)
# NOTE: Uses direct IP to bypass Cloudflare, which rejects Go-based TLS
# clients (lnget) with 400 Bad Request. The HTTPS domain works for all
# non-lnget traffic. See README for details.
L402_BASE = "http://104.197.109.246:8080"

# x402 / SHO proxy (USDC payments on Base)
# NOTE: Uses direct IP to bypass Cloudflare, same pattern as L402.
# x402 proxy runs directly on :8402.
SHO_BASE = "http://104.197.109.246:8402"

# Oracle endpoints (routed by nginx — same backends, different payment rail)
L402_ORACLE_URLS = {
    "btcusd":      f"{L402_BASE}/oracle/btcusd",
    "btcusd_vwap": f"{L402_BASE}/oracle/btcusd/vwap",
    "ethusd":      f"{L402_BASE}/oracle/ethusd",
    "eurusd":      f"{L402_BASE}/oracle/eurusd",
    "xauusd":      f"{L402_BASE}/oracle/xauusd",
    "btceur":      f"{L402_BASE}/oracle/btceur",
    "solusd":      f"{L402_BASE}/oracle/solusd",
    "etheur":      f"{L402_BASE}/oracle/etheur",
    "soleur":      f"{L402_BASE}/oracle/soleur",
    "xaueur":      f"{L402_BASE}/oracle/xaueur",
    "btceur_vwap": f"{L402_BASE}/oracle/btceur/vwap",
}

SHO_ORACLE_URLS = {
    "btcusd":      f"{SHO_BASE}/oracle/btcusd",
    "btcusd_vwap": f"{SHO_BASE}/oracle/btcusd/vwap",
    "ethusd":      f"{SHO_BASE}/oracle/ethusd",
    "eurusd":      f"{SHO_BASE}/oracle/eurusd",
    "xauusd":      f"{SHO_BASE}/oracle/xauusd",
    "btceur":      f"{SHO_BASE}/oracle/btceur",
    "solusd":      f"{SHO_BASE}/oracle/solusd",
    "etheur":      f"{SHO_BASE}/oracle/etheur",
    "soleur":      f"{SHO_BASE}/oracle/soleur",
    "xaueur":      f"{SHO_BASE}/oracle/xaueur",
    "btceur_vwap": f"{SHO_BASE}/oracle/btceur/vwap",
}

# DLC endpoints (free endpoints use domain, paid attestation uses direct IP)
DLC_PUBKEY_URL        = f"https://api.myceliasignal.com/dlc/oracle/pubkey"
DLC_STATUS_URL        = f"https://api.myceliasignal.com/dlc/oracle/status"
DLC_ANNOUNCEMENTS_URL = f"https://api.myceliasignal.com/dlc/oracle/announcements"
DLC_ATTESTATIONS_URL  = f"{L402_BASE}/dlc/oracle/attestations"

# SHO info/health (free)
SHO_INFO_URL   = f"{SHO_BASE}/sho/info"
SHO_HEALTH_URL = f"{SHO_BASE}/health"

# lnget binary for L402 payments
LNGET_PATH = r"C:\Users\JBulkeley\lnget\lnget.exe"

# Common headers to avoid Cloudflare blocking Python's default User-Agent
HTTP_HEADERS = {"User-Agent": "SLO-MCP/1.0"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clear_tokens():
    try:
        subprocess.run(
            [LNGET_PATH, "tokens", "clear", "--force"],
            capture_output=True, text=True, timeout=10
        )
    except Exception:
        pass


def _fetch_l402(url):
    """Fetch a paid endpoint via L402 (Lightning payment through lnget)."""
    _clear_tokens()
    result = subprocess.run(
        [LNGET_PATH, "-k", "-q", url],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"lnget failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _fetch_sho(url):
    """Fetch a paid endpoint via x402/SHO.

    Phase 1: SHO endpoints currently serve data directly (payment
    verification happens on the proxy side via USDC on Base).
    When calling from the MCP server, we make a plain GET which
    returns a 402 with payment instructions. For MCP tool use,
    we pass through the 402 response so the caller can see the
    payment requirements.

    Future: integrate x402 client SDK for automatic USDC payment.
    """
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        # 402 Payment Required — return the payment instructions
        if e.code == 402:
            body = json.loads(e.read().decode())
            body["_sho_status"] = "payment_required"
            body["_sho_note"] = (
                "This endpoint requires x402 payment (USDC on Base). "
                "Use any x402-compatible client or SDK to sign an EIP-3009 "
                "transferWithAuthorization and send as base64 X-PAYMENT header. "
                "See https://api.myceliasignal.com/.well-known/x402 for details."
            )
            return body
        raise


def _fetch_free(url):
    """Fetch a free (no payment) endpoint via simple HTTP GET."""
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _parse_canonical(canonical):
    parts = canonical.split("|")
    return {
        "version": parts[0],
        "pair": parts[1],
        "price": parts[2],
        "currency": parts[3],
        "decimals": int(parts[4]),
        "timestamp": parts[5],
        "nonce": parts[6],
        "sources": parts[7].split(","),
        "method": parts[8],
    }


def _verify_secp256k1(canonical, signature_b64, pubkey_hex):
    """Verify secp256k1 signature (L402 oracle responses)."""
    try:
        from ecdsa import VerifyingKey, SECP256k1
        sig_bytes = base64.b64decode(signature_b64)
        pubkey_bytes = bytes.fromhex(pubkey_hex)
        vk = VerifyingKey.from_string(pubkey_bytes, curve=SECP256k1)
        h = hashlib.sha256(canonical.encode()).digest()
        return vk.verify_digest(sig_bytes, h)
    except Exception:
        return False


def _verify_ed25519(canonical, signature_b64, pubkey_hex):
    """Verify Ed25519 signature (x402/SHO responses)."""
    try:
        from nacl.signing import VerifyKey
        vk = VerifyKey(bytes.fromhex(pubkey_hex))
        sig_bytes = base64.b64decode(signature_b64)
        msg_hash = hashlib.sha256(canonical.encode()).digest()
        vk.verify(msg_hash, sig_bytes)
        return True
    except Exception:
        return False


def _build_result(data, signing_scheme="secp256k1"):
    """Build a standardized result dict from oracle response data."""
    parsed = _parse_canonical(data["canonical"])

    if signing_scheme == "ed25519":
        sig_valid = _verify_ed25519(
            data["canonical"], data["signature"], data["pubkey"]
        )
    else:
        sig_valid = _verify_secp256k1(
            data["canonical"], data["signature"], data["pubkey"]
        )

    return {
        "price": parsed["price"],
        "currency": parsed["currency"],
        "timestamp": parsed["timestamp"],
        "sources": parsed["sources"],
        "method": parsed["method"],
        "signing_scheme": signing_scheme,
        "signature_valid": sig_valid,
        "canonical": data["canonical"],
        "pubkey": data["pubkey"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# L402 Tools (Lightning payment)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_btcusd_spot() -> dict:
    """Get the current BTCUSD spot price from the Sovereign Lightning Oracle.
    Costs 10 sats paid via Lightning. Returns median price from 9 exchanges
    with a cryptographic signature."""
    data = _fetch_l402(L402_ORACLE_URLS["btcusd"])
    return _build_result(data, "secp256k1")


@mcp.tool()
def get_btcusd_vwap() -> dict:
    """Get the current BTCUSD volume-weighted average price (VWAP).
    Costs 20 sats paid via Lightning."""
    data = _fetch_l402(L402_ORACLE_URLS["btcusd_vwap"])
    return _build_result(data, "secp256k1")


@mcp.tool()
def get_ethusd_spot() -> dict:
    """Get the current ETHUSD spot price from the Sovereign Lightning Oracle.
    Costs 10 sats paid via Lightning. Returns median price from
    Coinbase, Kraken, Bitstamp, Gemini, and Bitfinex."""
    data = _fetch_l402(L402_ORACLE_URLS["ethusd"])
    return _build_result(data, "secp256k1")


@mcp.tool()
def get_eurusd_spot() -> dict:
    """Get the current EURUSD spot price from the Sovereign Lightning Oracle.
    Costs 10 sats paid via Lightning. Returns median price from
    ECB, Bank of Canada, RBA, Norges Bank, Czech National Bank, Kraken,
    and Bitstamp."""
    data = _fetch_l402(L402_ORACLE_URLS["eurusd"])
    return _build_result(data, "secp256k1")


@mcp.tool()
def get_xauusd_spot() -> dict:
    """Get the current XAU/USD (gold) spot price from the Sovereign Lightning Oracle.
    Costs 10 sats paid via Lightning. Returns median price from
    Kitco, JM Bullion, GoldBroker, Coinbase, Kraken, Gemini, Binance, and OKX."""
    data = _fetch_l402(L402_ORACLE_URLS["xauusd"])
    return _build_result(data, "secp256k1")


@mcp.tool()
def get_btceur_spot() -> dict:
    """Get the current BTC/EUR spot price from the Sovereign Lightning Oracle.
    Costs 10 sats paid via Lightning. Cross-rate derived from
    BTCUSD (9 sources) and EURUSD (8 sources)."""
    data = _fetch_l402(L402_ORACLE_URLS["btceur"])
    return _build_result(data, "secp256k1")


@mcp.tool()
def get_solusd_spot() -> dict:
    """Get the current SOL/USD spot price from the Sovereign Lightning Oracle.
    Costs 10 sats paid via Lightning. Returns median price from
    Coinbase, Kraken, Bitstamp, Gemini, Bitfinex, Binance, OKX, Gate.io,
    and Bybit."""
    data = _fetch_l402(L402_ORACLE_URLS["solusd"])
    return _build_result(data, "secp256k1")


# ══════════════════════════════════════════════════════════════════════════════
# x402 / SHO Tools (USDC on Base payment)
# ══════════════════════════════════════════════════════════════════════════════


@mcp.tool()
def get_etheur_spot() -> dict:
    """Get ETH/EUR spot. 10 sats Lightning. Hybrid: 3 direct EUR + cross-rate."""
    data = _fetch_l402(L402_ORACLE_URLS["etheur"])
    return _build_result(data, "secp256k1")


@mcp.tool()
def get_soleur_spot() -> dict:
    """Get SOL/EUR spot. 10 sats Lightning. Hybrid: 3 direct EUR + cross-rate."""
    data = _fetch_l402(L402_ORACLE_URLS["soleur"])
    return _build_result(data, "secp256k1")


@mcp.tool()
def get_xaueur_spot() -> dict:
    """Get XAU/EUR spot. 10 sats Lightning. Cross-rate from XAUUSD and EURUSD."""
    data = _fetch_l402(L402_ORACLE_URLS["xaueur"])
    return _build_result(data, "secp256k1")


@mcp.tool()
def get_btceur_vwap() -> dict:
    """Get BTC/EUR VWAP. 20 sats Lightning. Cross-rate from BTCUSD VWAP and EURUSD."""
    data = _fetch_l402(L402_ORACLE_URLS["btceur_vwap"])
    return _build_result(data, "secp256k1")


@mcp.tool()
def sho_get_info() -> dict:
    """Get SHO (Sovereign HTTP Oracle) public info: x402 protocol details,
    Ed25519 public key, payment address, supported endpoints, and prices.
    Free endpoint — no payment required."""
    return _fetch_free(SHO_INFO_URL)


@mcp.tool()
def sho_get_health() -> dict:
    """Get SHO health status.
    Free endpoint — no payment required."""
    return _fetch_free(SHO_HEALTH_URL)


@mcp.tool()
def sho_get_btcusd_spot() -> dict:
    """Get BTC/USD spot price via x402/SHO (USDC on Base).
    Costs $0.001 USDC. Returns payment instructions if no payment provided,
    or Ed25519-signed price data if payment is included."""
    data = _fetch_sho(SHO_ORACLE_URLS["btcusd"])
    if data.get("_sho_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")


@mcp.tool()
def sho_get_btcusd_vwap() -> dict:
    """Get BTC/USD VWAP via x402/SHO (USDC on Base).
    Costs $0.002 USDC."""
    data = _fetch_sho(SHO_ORACLE_URLS["btcusd_vwap"])
    if data.get("_sho_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")


@mcp.tool()
def sho_get_ethusd_spot() -> dict:
    """Get ETH/USD spot price via x402/SHO (USDC on Base).
    Costs $0.001 USDC."""
    data = _fetch_sho(SHO_ORACLE_URLS["ethusd"])
    if data.get("_sho_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")


@mcp.tool()
def sho_get_eurusd_spot() -> dict:
    """Get EUR/USD spot price via x402/SHO (USDC on Base).
    Costs $0.001 USDC."""
    data = _fetch_sho(SHO_ORACLE_URLS["eurusd"])
    if data.get("_sho_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")


@mcp.tool()
def sho_get_xauusd_spot() -> dict:
    """Get XAU/USD (gold) spot price via x402/SHO (USDC on Base).
    Costs $0.001 USDC."""
    data = _fetch_sho(SHO_ORACLE_URLS["xauusd"])
    if data.get("_sho_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")


@mcp.tool()
def sho_get_btceur_spot() -> dict:
    """Get BTC/EUR spot price via x402/SHO (USDC on Base).
    Costs $0.001 USDC."""
    data = _fetch_sho(SHO_ORACLE_URLS["btceur"])
    if data.get("_sho_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")


@mcp.tool()
def sho_get_solusd_spot() -> dict:
    """Get SOL/USD spot price via x402/SHO (USDC on Base).
    Costs $0.001 USDC."""
    data = _fetch_sho(SHO_ORACLE_URLS["solusd"])
    if data.get("_sho_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")



@mcp.tool()
def sho_get_etheur_spot() -> dict:
    """Get ETH/EUR spot via x402/SHO. $0.001 USDC. Hybrid: 3 direct EUR + cross-rate."""
    data = _fetch_sho(SHO_ORACLE_URLS["etheur"])
    if data.get("_sho_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")


@mcp.tool()
def sho_get_soleur_spot() -> dict:
    """Get SOL/EUR spot via x402/SHO. $0.001 USDC. Hybrid: 3 direct EUR + cross-rate."""
    data = _fetch_sho(SHO_ORACLE_URLS["soleur"])
    if data.get("_sho_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")


@mcp.tool()
def sho_get_xaueur_spot() -> dict:
    """Get XAU/EUR spot via x402/SHO. $0.001 USDC. Cross-rate from XAUUSD and EURUSD."""
    data = _fetch_sho(SHO_ORACLE_URLS["xaueur"])
    if data.get("_sho_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")


@mcp.tool()
def sho_get_btceur_vwap() -> dict:
    """Get BTC/EUR VWAP via x402/SHO. $0.002 USDC. Cross-rate from BTCUSD VWAP and EURUSD."""
    data = _fetch_sho(SHO_ORACLE_URLS["btceur_vwap"])
    if data.get("_sho_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")


@mcp.tool()
def sho_get_enforcement(address: str) -> dict:
    """Check x402/SHO enforcement status for a Base address.
    Shows whether the address is allowed, in cooldown, or hard-blocked.
    Free endpoint — no payment required."""
    url = f"{SHO_BASE}/sho/enforcement/{address}"
    return _fetch_free(url)


# ══════════════════════════════════════════════════════════════════════════════
# DLC Oracle Tools (free or Lightning-paid)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
def get_dlc_pubkey() -> dict:
    """Get the DLC oracle's public key (BIP-340 Schnorr).
    Free endpoint — no Lightning payment required."""
    return _fetch_free(DLC_PUBKEY_URL)


@mcp.tool()
def get_dlc_status() -> dict:
    """Get the DLC oracle status: announcement count, attestation count,
    pending events, and supported pairs.
    Free endpoint — no Lightning payment required."""
    return _fetch_free(DLC_STATUS_URL)


@mcp.tool()
def get_dlc_announcements() -> dict:
    """Get all DLC oracle announcements (pre-committed nonces for upcoming events).
    Each announcement contains R-points (public nonces) committed before the
    attestation is published. Free endpoint — no Lightning payment required."""
    return _fetch_free(DLC_ANNOUNCEMENTS_URL)


@mcp.tool()
def get_dlc_attestation(event_id: str) -> dict:
    """Get a specific DLC attestation by event ID (e.g. 'BTCUSD-2026-02-22T17:00:00Z').
    Returns Schnorr-signed 5-digit price decomposition with per-digit s-values.
    Costs 1000 sats paid via Lightning."""
    url = f"{DLC_ATTESTATIONS_URL}/{event_id}"
    return _fetch_l402(url)


if __name__ == "__main__":
    mcp.run()
