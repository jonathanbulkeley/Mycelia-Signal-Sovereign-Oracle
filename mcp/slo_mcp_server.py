import json
import subprocess
import hashlib
import base64
import urllib.request
from fastmcp import FastMCP

mcp = FastMCP(
    name="Mycelia Signal Oracle",
    instructions=(
        "You have access to Mycelia Signal — a sovereign price oracle with 56 endpoints "
        "across crypto pairs, FX rates, economic indicators, and commodities.\n"
        "Two payment protocols:\n"
        "  • L402 (Lightning): pays real sats automatically via lnget\n"
        "  • x402: pays USDC on Base chain\n"
        "Responses are cryptographically signed (secp256k1 ECDSA for L402, Ed25519 for x402) "
        "and independently verifiable.\n\n"
        "Crypto pairs (15): BTC/USD spot+VWAP, BTC/EUR spot+VWAP, BTC/JPY spot+VWAP, "
        "ETH/USD, ETH/EUR, ETH/JPY, SOL/USD, SOL/EUR, SOL/JPY, XRP/USD, ADA/USD, DOGE/USD — 10 sats/$0.01 (20/$0.02 for VWAP)\n"
        "Precious metals (3): XAU/USD, XAU/EUR, XAU/JPY — 10 sats/$0.01\n"
        "FX pairs (19): EUR/USD, EUR/JPY, EUR/GBP, EUR/CHF, EUR/CNY, EUR/CAD, "
        "GBP/USD, GBP/JPY, GBP/CHF, GBP/CNY, GBP/CAD, "
        "USD/JPY, USD/CHF, USD/CNY, USD/CAD, CHF/JPY, CHF/CAD, CNY/JPY, CAD/JPY — 10 sats/$0.01\n"
        "US Economic (8): CPI, CPI Core, Unemployment, NFP, Fed Funds, GDP, PCE, Yield Curve — 1000 sats/$0.10\n"
        "EU Economic (6): HICP, HICP Core, HICP Services, Unemployment, GDP, Employment — 1000 sats/$0.10\n"
        "Commodities (5): WTI, Brent, NatGas, Copper, DXY — 1000 sats/$0.10\n"
    )
)

# ── Base URLs ─────────────────────────────────────────────────────────────────

# L402 proxy — direct IP to bypass Cloudflare (lnget TLS incompatibility)
L402_BASE = "http://104.197.109.246:8080"

# x402 proxy — direct IP, same reason
X402_BASE = os.environ.get("SLO_X402_BASE", "https://api.myceliasignal.com")

# ── Endpoint URLs ─────────────────────────────────────────────────────────────

L402_URLS = {
    # Crypto — spot
    "btc_usd":      f"{L402_BASE}/oracle/price/btc/usd",
    "btc_eur":      f"{L402_BASE}/oracle/price/btc/eur",
    "btc_jpy":      f"{L402_BASE}/oracle/price/btc/jpy",
    "eth_usd":      f"{L402_BASE}/oracle/price/eth/usd",
    "eth_eur":      f"{L402_BASE}/oracle/price/eth/eur",
    "eth_jpy":      f"{L402_BASE}/oracle/price/eth/jpy",
    "sol_usd":      f"{L402_BASE}/oracle/price/sol/usd",
    "sol_eur":      f"{L402_BASE}/oracle/price/sol/eur",
    "sol_jpy":      f"{L402_BASE}/oracle/price/sol/jpy",
    "xrp_usd":      f"{L402_BASE}/oracle/price/xrp/usd",
    "ada_usd":      f"{L402_BASE}/oracle/price/ada/usd",
    "doge_usd":     f"{L402_BASE}/oracle/price/doge/usd",
    # Crypto — VWAP
    "btc_usd_vwap": f"{L402_BASE}/oracle/price/btc/usd/vwap",
    "btc_eur_vwap": f"{L402_BASE}/oracle/price/btc/eur/vwap",
    # Precious metals
    "xau_usd":      f"{L402_BASE}/oracle/price/xau/usd",
    "xau_eur":      f"{L402_BASE}/oracle/price/xau/eur",
    "xau_jpy":      f"{L402_BASE}/oracle/price/xau/jpy",
    # FX
    "eur_usd":      f"{L402_BASE}/oracle/price/eur/usd",
    "eur_jpy":      f"{L402_BASE}/oracle/price/eur/jpy",
    "eur_gbp":      f"{L402_BASE}/oracle/price/eur/gbp",
    "eur_chf":      f"{L402_BASE}/oracle/price/eur/chf",
    "eur_cny":      f"{L402_BASE}/oracle/price/eur/cny",
    "eur_cad":      f"{L402_BASE}/oracle/price/eur/cad",
    "gbp_usd":      f"{L402_BASE}/oracle/price/gbp/usd",
    "gbp_jpy":      f"{L402_BASE}/oracle/price/gbp/jpy",
    "gbp_chf":      f"{L402_BASE}/oracle/price/gbp/chf",
    "gbp_cny":      f"{L402_BASE}/oracle/price/gbp/cny",
    "gbp_cad":      f"{L402_BASE}/oracle/price/gbp/cad",
    "usd_jpy":      f"{L402_BASE}/oracle/price/usd/jpy",
    "usd_chf":      f"{L402_BASE}/oracle/price/usd/chf",
    "usd_cny":      f"{L402_BASE}/oracle/price/usd/cny",
    "usd_cad":      f"{L402_BASE}/oracle/price/usd/cad",
    "chf_jpy":      f"{L402_BASE}/oracle/price/chf/jpy",
    "chf_cad":      f"{L402_BASE}/oracle/price/chf/cad",
    "cny_jpy":      f"{L402_BASE}/oracle/price/cny/jpy",
    "cny_cad":      f"{L402_BASE}/oracle/price/cny/cad",
    "cad_jpy":      f"{L402_BASE}/oracle/price/cad/jpy",
    # US Economic
    "us_cpi":        f"{L402_BASE}/oracle/econ/us/cpi",
    "us_cpi_core":   f"{L402_BASE}/oracle/econ/us/cpi_core",
    "us_unrate":     f"{L402_BASE}/oracle/econ/us/unrate",
    "us_nfp":        f"{L402_BASE}/oracle/econ/us/nfp",
    "us_fedfunds":   f"{L402_BASE}/oracle/econ/us/fedfunds",
    "us_gdp":        f"{L402_BASE}/oracle/econ/us/gdp",
    "us_pce":        f"{L402_BASE}/oracle/econ/us/pce",
    "us_yield_curve":f"{L402_BASE}/oracle/econ/us/yield_curve",
    # EU Economic
    "eu_hicp":          f"{L402_BASE}/oracle/econ/eu/hicp",
    "eu_hicp_core":     f"{L402_BASE}/oracle/econ/eu/hicp_core",
    "eu_hicp_services": f"{L402_BASE}/oracle/econ/eu/hicp_services",
    "eu_unrate":        f"{L402_BASE}/oracle/econ/eu/unrate",
    "eu_gdp":           f"{L402_BASE}/oracle/econ/eu/gdp",
    "eu_employment":    f"{L402_BASE}/oracle/econ/eu/employment",
    # Commodities
    "wti":     f"{L402_BASE}/oracle/econ/commodities/wti",
    "brent":   f"{L402_BASE}/oracle/econ/commodities/brent",
    "natgas":  f"{L402_BASE}/oracle/econ/commodities/natgas",
    "copper":  f"{L402_BASE}/oracle/econ/commodities/copper",
    "dxy":     f"{L402_BASE}/oracle/econ/commodities/dxy",
}

X402_URLS = {k: v.replace(L402_BASE, X402_BASE) for k, v in L402_URLS.items()}

# Free endpoints
HEALTH_URL = "https://api.myceliasignal.com/health"

# lnget binary for L402 payments
LNGET_PATH = r"C:\Users\JBulkeley\lnget\lnget.exe"

# Common headers
HTTP_HEADERS = {"User-Agent": "MyceliaSignal-MCP/2.0"}


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


def _fetch_x402(url):
    """Fetch a paid endpoint via x402 (USDC on Base).
    Returns 402 payment details if no wallet configured."""
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 402:
            body = json.loads(e.read().decode())
            body["_x402_status"] = "payment_required"
            body["_x402_note"] = (
                "This endpoint requires x402 payment (USDC on Base). "
                "Use any x402-compatible client or SDK to sign an EIP-3009 "
                "transferWithAuthorization and send as base64 X-Payment header. "
                "See https://api.myceliasignal.com/.well-known/x402 for details."
            )
            return body
        raise


def _fetch_free(url):
    """Fetch a free endpoint via simple HTTP GET."""
    req = urllib.request.Request(url, headers=HTTP_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _get_canonical(data):
    """Get canonical string from response — handles both field names."""
    return data.get("canonical") or data.get("canonicalstring", "")


def _parse_canonical(canonical):
    """Parse canonical string. Handles PRICE, ECON, and COMMODITIES types."""
    parts = canonical.split("|")
    if len(parts) < 4:
        return {"raw": canonical}
    result = {"version": parts[0], "type": parts[1]}
    if parts[1] == "PRICE":
        # v1|PRICE|PAIR|PRICE|CURRENCY|DECIMALS|SOURCES|METHOD|TIMESTAMP|NONCE
        result.update({
            "pair":      parts[2] if len(parts) > 2 else "",
            "price":     parts[3] if len(parts) > 3 else "",
            "currency":  parts[4] if len(parts) > 4 else "",
            "decimals":  int(parts[5]) if len(parts) > 5 else 0,
            "timestamp": parts[6] if len(parts) > 6 else "",
            "nonce":     parts[7] if len(parts) > 7 else "",
            "sources":   parts[8].split(",") if len(parts) > 8 else [],
            "method":    parts[9] if len(parts) > 9 else "",
        })
    else:
        # v1|US|INDICATOR|VALUE|UNIT|REF_START|REF_END|SOURCE|SERIES_ID|METHOD|EXTRA|NONCE
        # v1|COMMODITIES|INDICATOR|VALUE|...
        result.update({
            "indicator":   parts[2] if len(parts) > 2 else "",
            "value":       parts[3] if len(parts) > 3 else "",
            "unit":        parts[4] if len(parts) > 4 else "",
            "ref_start":   parts[5] if len(parts) > 5 else "",
            "ref_end":     parts[6] if len(parts) > 6 else "",
            "source":      parts[7] if len(parts) > 7 else "",
            "series_id":   parts[8] if len(parts) > 8 else "",
            "method":      parts[9] if len(parts) > 9 else "",
            "nonce":       parts[11] if len(parts) > 11 else "",
        })
    return result


def _verify_secp256k1(canonical, signature_b64, pubkey_hex):
    """Verify secp256k1 ECDSA signature (L402 responses)."""
    try:
        from coincurve import PublicKey
        sig_bytes = base64.b64decode(signature_b64)
        pubkey = PublicKey(bytes.fromhex(pubkey_hex))
        h = hashlib.sha256(canonical.encode()).digest()
        return pubkey.verify(sig_bytes, h, hasher=None)
    except Exception:
        return False


def _verify_ed25519(canonical, signature_b64, pubkey_hex):
    """Verify Ed25519 signature (x402 responses)."""
    try:
        from nacl.signing import VerifyKey
        from nacl.encoding import RawEncoder
        vk = VerifyKey(bytes.fromhex(pubkey_hex), encoder=RawEncoder)
        sig_bytes = base64.b64decode(signature_b64)
        msg_hash = hashlib.sha256(canonical.encode()).digest()
        vk.verify(msg_hash, sig_bytes)
        return True
    except Exception:
        return False


def _build_result(data, signing_scheme="secp256k1"):
    """Build standardized result from oracle response."""
    canonical = _get_canonical(data)
    if not canonical:
        return data

    parsed = _parse_canonical(canonical)

    if signing_scheme == "ed25519":
        sig_valid = _verify_ed25519(canonical, data.get("signature", ""), data.get("pubkey", ""))
    else:
        sig_valid = _verify_secp256k1(canonical, data.get("signature", ""), data.get("pubkey", ""))

    result = {
        "signature_valid": sig_valid,
        "signing_scheme": data.get("signing_scheme", signing_scheme),
        "canonical": canonical,
        "pubkey": data.get("pubkey", ""),
    }
    result.update(parsed)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# L402 Tools — Crypto Pairs (Lightning)
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_btc_usd() -> dict:
    """Get BTC/USD spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["btc_usd"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_btc_usd_vwap() -> dict:
    """Get BTC/USD 5-min VWAP via L402 (Lightning). 20 sats."""
    return _build_result(_fetch_l402(L402_URLS["btc_usd_vwap"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_btc_eur() -> dict:
    """Get BTC/EUR spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["btc_eur"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_btc_eur_vwap() -> dict:
    """Get BTC/EUR 5-min VWAP via L402 (Lightning). 20 sats."""
    return _build_result(_fetch_l402(L402_URLS["btc_eur_vwap"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_btc_jpy() -> dict:
    """Get BTC/JPY spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["btc_jpy"]))


@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eth_usd() -> dict:
    """Get ETH/USD spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["eth_usd"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eth_eur() -> dict:
    """Get ETH/EUR spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["eth_eur"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eth_jpy() -> dict:
    """Get ETH/JPY spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["eth_jpy"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_sol_usd() -> dict:
    """Get SOL/USD spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["sol_usd"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_sol_eur() -> dict:
    """Get SOL/EUR spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["sol_eur"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_sol_jpy() -> dict:
    """Get SOL/JPY spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["sol_jpy"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_xrp_usd() -> dict:
    """Get XRP/USD spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["xrp_usd"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_ada_usd() -> dict:
    """Get ADA/USD spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["ada_usd"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_doge_usd() -> dict:
    """Get DOGE/USD spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["doge_usd"]))


# ── L402 — Precious Metals ────────────────────────────────────────────────────

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_xau_usd() -> dict:
    """Get XAU/USD (gold) spot price via L402 (Lightning). 10 sats. 8 sources."""
    return _build_result(_fetch_l402(L402_URLS["xau_usd"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_xau_eur() -> dict:
    """Get XAU/EUR (gold in euros) spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["xau_eur"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_xau_jpy() -> dict:
    """Get XAU/JPY (gold in yen) spot price via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["xau_jpy"]))


# ── L402 — FX Rates ───────────────────────────────────────────────────────────

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eur_usd() -> dict:
    """Get EUR/USD rate via L402 (Lightning). 10 sats. 6 central banks + exchanges."""
    return _build_result(_fetch_l402(L402_URLS["eur_usd"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eur_jpy() -> dict:
    """Get EUR/JPY rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["eur_jpy"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eur_gbp() -> dict:
    """Get EUR/GBP rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["eur_gbp"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eur_chf() -> dict:
    """Get EUR/CHF rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["eur_chf"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eur_cny() -> dict:
    """Get EUR/CNY rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["eur_cny"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eur_cad() -> dict:
    """Get EUR/CAD rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["eur_cad"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_gbp_usd() -> dict:
    """Get GBP/USD rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["gbp_usd"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_gbp_jpy() -> dict:
    """Get GBP/JPY rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["gbp_jpy"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_gbp_chf() -> dict:
    """Get GBP/CHF rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["gbp_chf"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_gbp_cny() -> dict:
    """Get GBP/CNY rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["gbp_cny"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_gbp_cad() -> dict:
    """Get GBP/CAD rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["gbp_cad"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_usd_jpy() -> dict:
    """Get USD/JPY rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["usd_jpy"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_usd_chf() -> dict:
    """Get USD/CHF rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["usd_chf"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_usd_cny() -> dict:
    """Get USD/CNY rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["usd_cny"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_usd_cad() -> dict:
    """Get USD/CAD rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["usd_cad"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_chf_jpy() -> dict:
    """Get CHF/JPY rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["chf_jpy"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_chf_cad() -> dict:
    """Get CHF/CAD rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["chf_cad"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_cny_jpy() -> dict:
    """Get CNY/JPY rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["cny_jpy"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_cny_cad() -> dict:
    """Get CNY/CAD rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["cny_cad"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_cad_jpy() -> dict:
    """Get CAD/JPY rate via L402 (Lightning). 10 sats."""
    return _build_result(_fetch_l402(L402_URLS["cad_jpy"]))


# ── L402 — US Economic Indicators ─────────────────────────────────────────────

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_us_cpi() -> dict:
    """Get US CPI headline inflation via L402 (Lightning). 1000 sats. Source: BLS."""
    return _build_result(_fetch_l402(L402_URLS["us_cpi"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_us_cpi_core() -> dict:
    """Get US CPI Core (ex food & energy) via L402 (Lightning). 1000 sats. Source: BLS/FRED."""
    return _build_result(_fetch_l402(L402_URLS["us_cpi_core"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_us_unemployment() -> dict:
    """Get US Unemployment Rate via L402 (Lightning). 1000 sats. Source: BLS/FRED."""
    return _build_result(_fetch_l402(L402_URLS["us_unrate"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_us_nfp() -> dict:
    """Get US Nonfarm Payrolls via L402 (Lightning). 1000 sats. Source: BLS/FRED."""
    return _build_result(_fetch_l402(L402_URLS["us_nfp"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_us_fedfunds() -> dict:
    """Get US Federal Funds Rate via L402 (Lightning). 1000 sats. Source: FRED."""
    return _build_result(_fetch_l402(L402_URLS["us_fedfunds"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_us_gdp() -> dict:
    """Get US GDP via L402 (Lightning). 1000 sats. Source: BEA/FRED."""
    return _build_result(_fetch_l402(L402_URLS["us_gdp"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_us_pce() -> dict:
    """Get US PCE Price Index via L402 (Lightning). 1000 sats. Source: BEA/FRED."""
    return _build_result(_fetch_l402(L402_URLS["us_pce"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_us_yield_curve() -> dict:
    """Get US Yield Curve (10Y-2Y spread) via L402 (Lightning). 1000 sats. Source: FRED."""
    return _build_result(_fetch_l402(L402_URLS["us_yield_curve"]))


# ── L402 — EU Economic Indicators ─────────────────────────────────────────────

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eu_hicp() -> dict:
    """Get EU HICP headline inflation via L402 (Lightning). 1000 sats. Source: Eurostat."""
    return _build_result(_fetch_l402(L402_URLS["eu_hicp"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eu_hicp_core() -> dict:
    """Get EU HICP Core inflation via L402 (Lightning). 1000 sats. Source: Eurostat."""
    return _build_result(_fetch_l402(L402_URLS["eu_hicp_core"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eu_hicp_services() -> dict:
    """Get EU HICP Services inflation via L402 (Lightning). 1000 sats. Source: Eurostat."""
    return _build_result(_fetch_l402(L402_URLS["eu_hicp_services"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eu_unemployment() -> dict:
    """Get EU Unemployment Rate via L402 (Lightning). 1000 sats. Source: Eurostat."""
    return _build_result(_fetch_l402(L402_URLS["eu_unrate"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eu_gdp() -> dict:
    """Get EU GDP via L402 (Lightning). 1000 sats. Source: Eurostat."""
    return _build_result(_fetch_l402(L402_URLS["eu_gdp"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_eu_employment() -> dict:
    """Get EU Employment via L402 (Lightning). 1000 sats. Source: Eurostat."""
    return _build_result(_fetch_l402(L402_URLS["eu_employment"]))


# ── L402 — Commodities ────────────────────────────────────────────────────────

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_wti() -> dict:
    """Get WTI Crude Oil price via L402 (Lightning). 1000 sats. Source: EIA/FRED."""
    return _build_result(_fetch_l402(L402_URLS["wti"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_brent() -> dict:
    """Get Brent Crude Oil price via L402 (Lightning). 1000 sats. Source: FRED."""
    return _build_result(_fetch_l402(L402_URLS["brent"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_natgas() -> dict:
    """Get Henry Hub Natural Gas price via L402 (Lightning). 1000 sats. Source: EIA/FRED."""
    return _build_result(_fetch_l402(L402_URLS["natgas"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_copper() -> dict:
    """Get Copper price via L402 (Lightning). 1000 sats. Source: FRED."""
    return _build_result(_fetch_l402(L402_URLS["copper"]))

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_dxy() -> dict:
    """Get US Dollar Index (DXY) via L402 (Lightning). 1000 sats. Source: FRED."""
    return _build_result(_fetch_l402(L402_URLS["dxy"]))


# ══════════════════════════════════════════════════════════════════════════════
# x402 Tools — all 56 endpoints, USDC on Base
# ══════════════════════════════════════════════════════════════════════════════

def _x402(key):
    data = _fetch_x402(X402_URLS[key])
    if data.get("_x402_status") == "payment_required":
        return data
    return _build_result(data, "ed25519")

# Crypto — spot
@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_btc_usd() -> dict:
    """Get BTC/USD spot price via x402 (USDC on Base). $0.01."""
    return _x402("btc_usd")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_btc_usd_vwap() -> dict:
    """Get BTC/USD VWAP via x402 (USDC on Base). $0.02."""
    return _x402("btc_usd_vwap")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_btc_eur() -> dict:
    """Get BTC/EUR spot price via x402 (USDC on Base). $0.01."""
    return _x402("btc_eur")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_btc_eur_vwap() -> dict:
    """Get BTC/EUR VWAP via x402 (USDC on Base). $0.02."""
    return _x402("btc_eur_vwap")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_btc_jpy() -> dict:
    """Get BTC/JPY spot price via x402 (USDC on Base). $0.01."""
    return _x402("btc_jpy")

@mcp.tool()
@mcp.tool()

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eth_usd() -> dict:
    """Get ETH/USD spot price via x402 (USDC on Base). $0.01."""
    return _x402("eth_usd")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eth_eur() -> dict:
    """Get ETH/EUR spot price via x402 (USDC on Base). $0.01."""
    return _x402("eth_eur")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eth_jpy() -> dict:
    """Get ETH/JPY spot price via x402 (USDC on Base). $0.01."""
    return _x402("eth_jpy")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_sol_usd() -> dict:
    """Get SOL/USD spot price via x402 (USDC on Base). $0.01."""
    return _x402("sol_usd")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_sol_eur() -> dict:
    """Get SOL/EUR spot price via x402 (USDC on Base). $0.01."""
    return _x402("sol_eur")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_sol_jpy() -> dict:
    """Get SOL/JPY spot price via x402 (USDC on Base). $0.01."""
    return _x402("sol_jpy")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_xrp_usd() -> dict:
    """Get XRP/USD spot price via x402 (USDC on Base). $0.01."""
    return _x402("xrp_usd")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_ada_usd() -> dict:
    """Get ADA/USD spot price via x402 (USDC on Base). $0.01."""
    return _x402("ada_usd")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_doge_usd() -> dict:
    """Get DOGE/USD spot price via x402 (USDC on Base). $0.01."""
    return _x402("doge_usd")

# Precious metals
@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_xau_usd() -> dict:
    """Get XAU/USD (gold) spot price via x402 (USDC on Base). $0.01."""
    return _x402("xau_usd")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_xau_eur() -> dict:
    """Get XAU/EUR (gold in euros) via x402 (USDC on Base). $0.01."""
    return _x402("xau_eur")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_xau_jpy() -> dict:
    """Get XAU/JPY (gold in yen) via x402 (USDC on Base). $0.01."""
    return _x402("xau_jpy")

# FX rates
@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eur_usd() -> dict:
    """Get EUR/USD rate via x402 (USDC on Base). $0.01."""
    return _x402("eur_usd")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eur_jpy() -> dict:
    """Get EUR/JPY rate via x402 (USDC on Base). $0.01."""
    return _x402("eur_jpy")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eur_gbp() -> dict:
    """Get EUR/GBP rate via x402 (USDC on Base). $0.01."""
    return _x402("eur_gbp")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eur_chf() -> dict:
    """Get EUR/CHF rate via x402 (USDC on Base). $0.01."""
    return _x402("eur_chf")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eur_cny() -> dict:
    """Get EUR/CNY rate via x402 (USDC on Base). $0.01."""
    return _x402("eur_cny")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eur_cad() -> dict:
    """Get EUR/CAD rate via x402 (USDC on Base). $0.01."""
    return _x402("eur_cad")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_gbp_usd() -> dict:
    """Get GBP/USD rate via x402 (USDC on Base). $0.01."""
    return _x402("gbp_usd")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_gbp_jpy() -> dict:
    """Get GBP/JPY rate via x402 (USDC on Base). $0.01."""
    return _x402("gbp_jpy")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_gbp_chf() -> dict:
    """Get GBP/CHF rate via x402 (USDC on Base). $0.01."""
    return _x402("gbp_chf")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_gbp_cny() -> dict:
    """Get GBP/CNY rate via x402 (USDC on Base). $0.01."""
    return _x402("gbp_cny")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_gbp_cad() -> dict:
    """Get GBP/CAD rate via x402 (USDC on Base). $0.01."""
    return _x402("gbp_cad")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_usd_jpy() -> dict:
    """Get USD/JPY rate via x402 (USDC on Base). $0.01."""
    return _x402("usd_jpy")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_usd_chf() -> dict:
    """Get USD/CHF rate via x402 (USDC on Base). $0.01."""
    return _x402("usd_chf")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_usd_cny() -> dict:
    """Get USD/CNY rate via x402 (USDC on Base). $0.01."""
    return _x402("usd_cny")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_usd_cad() -> dict:
    """Get USD/CAD rate via x402 (USDC on Base). $0.01."""
    return _x402("usd_cad")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_chf_jpy() -> dict:
    """Get CHF/JPY rate via x402 (USDC on Base). $0.01."""
    return _x402("chf_jpy")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_chf_cad() -> dict:
    """Get CHF/CAD rate via x402 (USDC on Base). $0.01."""
    return _x402("chf_cad")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_cny_jpy() -> dict:
    """Get CNY/JPY rate via x402 (USDC on Base). $0.01."""
    return _x402("cny_jpy")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_cny_cad() -> dict:
    """Get CNY/CAD rate via x402 (USDC on Base). $0.01."""
    return _x402("cny_cad")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_cad_jpy() -> dict:
    """Get CAD/JPY rate via x402 (USDC on Base). $0.01."""
    return _x402("cad_jpy")

# US Economic
@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_us_cpi() -> dict:
    """Get US CPI via x402 (USDC on Base). $0.10."""
    return _x402("us_cpi")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_us_cpi_core() -> dict:
    """Get US CPI Core via x402 (USDC on Base). $0.10."""
    return _x402("us_cpi_core")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_us_unemployment() -> dict:
    """Get US Unemployment Rate via x402 (USDC on Base). $0.10."""
    return _x402("us_unrate")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_us_nfp() -> dict:
    """Get US Nonfarm Payrolls via x402 (USDC on Base). $0.10."""
    return _x402("us_nfp")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_us_fedfunds() -> dict:
    """Get US Federal Funds Rate via x402 (USDC on Base). $0.10."""
    return _x402("us_fedfunds")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_us_gdp() -> dict:
    """Get US GDP via x402 (USDC on Base). $0.10."""
    return _x402("us_gdp")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_us_pce() -> dict:
    """Get US PCE Price Index via x402 (USDC on Base). $0.10."""
    return _x402("us_pce")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_us_yield_curve() -> dict:
    """Get US Yield Curve (10Y-2Y) via x402 (USDC on Base). $0.10."""
    return _x402("us_yield_curve")

# EU Economic
@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eu_hicp() -> dict:
    """Get EU HICP inflation via x402 (USDC on Base). $0.10."""
    return _x402("eu_hicp")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eu_hicp_core() -> dict:
    """Get EU HICP Core inflation via x402 (USDC on Base). $0.10."""
    return _x402("eu_hicp_core")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eu_hicp_services() -> dict:
    """Get EU HICP Services inflation via x402 (USDC on Base). $0.10."""
    return _x402("eu_hicp_services")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eu_unemployment() -> dict:
    """Get EU Unemployment Rate via x402 (USDC on Base). $0.10."""
    return _x402("eu_unrate")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eu_gdp() -> dict:
    """Get EU GDP via x402 (USDC on Base). $0.10."""
    return _x402("eu_gdp")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_eu_employment() -> dict:
    """Get EU Employment via x402 (USDC on Base). $0.10."""
    return _x402("eu_employment")

# Commodities
@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_wti() -> dict:
    """Get WTI Crude Oil price via x402 (USDC on Base). $0.10."""
    return _x402("wti")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_brent() -> dict:
    """Get Brent Crude Oil price via x402 (USDC on Base). $0.10."""
    return _x402("brent")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_natgas() -> dict:
    """Get Henry Hub Natural Gas price via x402 (USDC on Base). $0.10."""
    return _x402("natgas")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_copper() -> dict:
    """Get Copper price via x402 (USDC on Base). $0.10."""
    return _x402("copper")

@mcp.tool()
@mcp.tool()
@mcp.tool()
def x402_get_dxy() -> dict:
    """Get US Dollar Index (DXY) via x402 (USDC on Base). $0.10."""
    return _x402("dxy")


# ══════════════════════════════════════════════════════════════════════════════
# Free Tools
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
@mcp.tool()
@mcp.tool()
def get_health() -> dict:
    """Check Mycelia Signal API health. Free endpoint."""
    return _fetch_free(HEALTH_URL)


if __name__ == "__main__":
    mcp.run()