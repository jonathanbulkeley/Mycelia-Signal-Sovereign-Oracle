"""
Mycelia Signal MCP Server v3.0
Sovereign cryptographic oracle — 131 endpoints across crypto, FX, metals,
economic indicators, commodities, gas oracles, indices, marine, weather,
DeFi yield, and COT positioning.

x402 payment (USDC on Base). Ed25519 signed. No API keys.
"""

import json
import hashlib
import base64
import urllib.request
from fastmcp import FastMCP

mcp = FastMCP(
    name="Mycelia Signal Oracle",
    instructions=(
        "You have access to Mycelia Signal — a sovereign cryptographic oracle with 131 endpoints "
        "across crypto prices, FX rates, precious metals, stablecoin pegs, economic indicators, "
        "commodities, gas oracles, volatility/sentiment/stress/contagion indices, marine oracle, "
        "weather oracle, DeFi yield, and CME COT positioning.\n\n"
        "Payment: x402 (USDC on Base). Every response is Ed25519 signed and independently "
        "verifiable against a published public key. No API keys. No subscriptions.\n\n"
        "Pricing: \$0.01 (spot/FX/metals/gas/stablecoins), \$0.02 (VWAP), "
        "\$0.05 (indices: MSVI/MSXI/MSSI/MSTI, DeFi yield), \$0.10 (econ/commodities/COT/marine/weather).\n\n"
        "Free endpoints: /preview (unsigned sample data), /health, funding rates, basis, open interest.\n\n"
        "Indices overview:\n"
        "  MSVI (Volatility Index): 5-component, 0-100. Per-pair (BTC, ETH).\n"
        "  MSXI (Sentiment Index): 5-component, -100 to +100. Per-pair (BTC, ETH).\n"
        "  MSSI (Stress Index): 4-component (vol, stablecoin, funding, dispersion), 0-100. Market-wide.\n"
        "  MSTI (Contagion Index): 4-component, 0-100. Crypto-TradFi coupling. Market-wide.\n"
        "  MSFR (Funding Rate): 10-exchange OI-weighted composite. Free.\n"
    )
)

API_BASE = "https://api.myceliasignal.com"
HTTP_HEADERS = {"User-Agent": "MyceliaSignal-MCP/3.0"}

def _fetch(url):
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
                "Use an x402-compatible client to pay and resend with X-Payment header. "
                "See https://api.myceliasignal.com/.well-known/x402 for details."
            )
            return body
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()[:200]}")

def _verify_ed25519(canonical, signature_b64, pubkey_hex):
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

def _parse_canonical(canonical):
    parts = canonical.split("|")
    if len(parts) < 4:
        return {"raw": canonical}
    result = {"version": parts[0], "type": parts[1]}
    if parts[1] == "PRICE":
        result.update({
            "pair": parts[2] if len(parts) > 2 else "",
            "price": parts[3] if len(parts) > 3 else "",
            "currency": parts[4] if len(parts) > 4 else "",
            "decimals": int(parts[5]) if len(parts) > 5 else 0,
            "sources": parts[6].split(",") if len(parts) > 6 else [],
            "method": parts[7] if len(parts) > 7 else "",
            "timestamp": parts[8] if len(parts) > 8 else "",
            "nonce": parts[9] if len(parts) > 9 else "",
        })
    else:
        result.update({
            "indicator": parts[2] if len(parts) > 2 else "",
            "value": parts[3] if len(parts) > 3 else "",
            "unit": parts[4] if len(parts) > 4 else "",
            "source": parts[7] if len(parts) > 7 else "",
            "nonce": parts[-1] if len(parts) > 5 else "",
        })
    return result

def _build_result(data):
    if "_x402_status" in data:
        return data
    if "error" in data:
        raise RuntimeError(f"Oracle error: {data['error']}")
    canonical = data.get("canonical") or data.get("canonicalstring", "")
    if not canonical:
        sig = data.get("signature", "")
        pubkey = data.get("pubkey", "")
        if sig and pubkey:
            raw = data.get("canonicalString", "") or json.dumps(data.get("components", {}))
            data["signature_valid"] = _verify_ed25519(raw, sig, pubkey)
        return data
    parsed = _parse_canonical(canonical)
    sig_valid = _verify_ed25519(canonical, data.get("signature", ""), data.get("pubkey", ""))
    result = {"signature_valid": sig_valid, "signing_scheme": "ed25519", "canonical": canonical, "pubkey": data.get("pubkey", "")}
    result.update(parsed)
    return result

@mcp.tool()
def get_price(base: str, quote: str) -> dict:
    """Get spot price for any supported pair. Ed25519 signed. \$0.01.
    Supported bases: btc, eth, sol, xrp, ada, doge, xau (gold), eur, gbp, usd, chf, cny, cad, usdt, usdc.
    Supported quotes: usd, eur, jpy, gbp, chf, cny, cad.
    Examples: get_price("btc", "usd"), get_price("xau", "eur"), get_price("eur", "jpy")"""
    return _build_result(_fetch(f"{API_BASE}/oracle/price/{base.lower()}/{quote.lower()}"))

@mcp.tool()
def get_vwap(base: str, quote: str) -> dict:
    """Get 5-minute VWAP price. Ed25519 signed. \$0.02. Available for: btc/usd, btc/eur, eth/usd, eth/eur."""
    return _build_result(_fetch(f"{API_BASE}/oracle/price/{base.lower()}/{quote.lower()}/vwap"))

@mcp.tool()
def get_price_preview(base: str, quote: str) -> dict:
    """Get free unsigned preview price (up to 5 min stale). Not for production."""
    return _fetch(f"{API_BASE}/oracle/price/{base.lower()}/{quote.lower()}/preview")

@mcp.tool()
def get_volatility(base: str, quote: str) -> dict:
    """Get MSVI (Mycelia Signal Volatility Index). Ed25519 signed. \$0.05.
    5 components: Realized Vol (30%), Implied Vol (25%), Term Structure (15%), Funding Rate (20%), Put/Call Ratio (10%). Output: 0-100.
    Available for: btc/usd, eth/usd."""
    return _build_result(_fetch(f"{API_BASE}/oracle/volatility/{base.lower()}/{quote.lower()}"))

@mcp.tool()
def get_sentiment(base: str, quote: str) -> dict:
    """Get MSXI (Mycelia Signal Sentiment Index). Ed25519 signed. \$0.05.
    5 components: Funding Rate (30%), Options Skew (25%), Put/Call Ratio (20%), Term Structure (15%), Cross-exchange Basis (10%).
    Output: -100 to +100. Regimes: EXTREMEBULLISH, BULLISH, NEUTRAL, BEARISH, EXTREMEBEARISH.
    Available for: btc/usd, eth/usd."""
    return _build_result(_fetch(f"{API_BASE}/oracle/sentiment/{base.lower()}/{quote.lower()}"))

@mcp.tool()
def get_stress() -> dict:
    """Get MSSI (Mycelia Signal Stress Index). Ed25519 signed. \$0.05.
    4 components: Volatility Regime (30%), Stablecoin Stress (25%), Funding Extremity (30%), Funding Dispersion (15%).
    Output: 0-100. Regimes: CALM, ELEVATED, HIGH, EXTREME. Market-wide single number."""
    return _build_result(_fetch(f"{API_BASE}/oracle/stress/market"))

@mcp.tool()
def get_contagion() -> dict:
    """Get MSTI (Mycelia Signal Contagion Index). Ed25519 signed. \$0.05.
    Measures crypto-TradFi coupling. 4 components: BTC-equity correlation (30%), Equity Volatility (25%), DXY Momentum (20%), Beta amplification (25%).
    Output: 0-100. Regimes: DECOUPLED, MIXED, COUPLED, CONTAGION. Market-wide single number."""
    return _build_result(_fetch(f"{API_BASE}/oracle/contagion/market"))

@mcp.tool()
def get_index_preview(index: str, pair: str = "") -> dict:
    """Get free unsigned preview of any index. index: volatility, sentiment, stress, contagion.
    pair: btc/usd or eth/usd (required for volatility/sentiment, ignored for stress/contagion)."""
    if index in ("stress", "contagion"):
        return _fetch(f"{API_BASE}/oracle/{index}/market/preview")
    base, quote = pair.lower().split("/")
    return _fetch(f"{API_BASE}/oracle/{index}/{base}/{quote}/preview")

@mcp.tool()
def get_funding(base: str, quote: str) -> dict:

    """Get 10-exchange OI-weighted composite funding rate. Ed25519 signed. $0.05.
    Exchanges: Binance, Bybit, OKX, Deribit, Hyperliquid, dYdX, Bitget, Kraken, Coinbase INTX, Crypto.com.
    Available for: btc/usd, eth/usd, sol/usd."""
    return _build_result(_fetch(f"{API_BASE}/oracle/funding/{base.lower()}/{quote.lower()}"))

@mcp.tool()
def get_basis(base: str, quote: str) -> dict:
    """Get cross-exchange spot-perp basis spread. Ed25519 signed. $0.02. Returns per-exchange basis and annualized carry from 7 exchanges.
    Available for: btc/usd, eth/usd, sol/usd."""
    return _build_result(_fetch(f"{API_BASE}/oracle/basis/{base.lower()}/{quote.lower()}"))

@mcp.tool()
def get_open_interest(base: str, quote: str) -> dict:
    """Get aggregated open interest across exchanges. Ed25519 signed. $0.01. OI normalized to USD.
    Available for: btc/usd, eth/usd, sol/usd."""
    return _build_result(_fetch(f"{API_BASE}/oracle/oi/{base.lower()}/{quote.lower()}"))

@mcp.tool()
def get_gas(chain: str) -> dict:
    """Get L1/L2 gas prices and transaction costs. Ed25519 signed. \$0.01.
    Supported chains: ethereum, polygon, arbitrum, optimism, base, solana."""
    return _build_result(_fetch(f"{API_BASE}/oracle/gas/{chain.lower()}"))

@mcp.tool()
def get_econ(region: str, indicator: str) -> dict:
    """Get economic indicator. Ed25519 signed. \$0.10.
    US: cpi, cpi_core, unrate, nfp, fedfunds, gdp, pce, yield_curve.
    EU: hicp, hicp_core, hicp_services, unrate, gdp, employment."""
    return _build_result(_fetch(f"{API_BASE}/oracle/econ/{region.lower()}/{indicator.lower()}"))

@mcp.tool()
def get_commodity(name: str) -> dict:
    """Get commodity price. Ed25519 signed. \$0.10. Supported: wti, brent, natgas, copper, dxy."""
    return _build_result(_fetch(f"{API_BASE}/oracle/econ/commodities/{name.lower()}"))

@mcp.tool()
def get_cot(asset: str) -> dict:
    """Get CME Commitments of Traders positioning. Ed25519 signed. \$0.10. Supported: btc."""
    return _build_result(_fetch(f"{API_BASE}/oracle/cot/{asset.lower()}"))

@mcp.tool()
def get_marine_sea_state(lat: float, lon: float) -> dict:
    """Get sea state data for coordinates. Ed25519 signed. \$0.10."""
    return _build_result(_fetch(f"{API_BASE}/oracle/marine/{lat}/{lon}"))

@mcp.tool()
def get_marine_route_summary() -> dict:
    """Get marine route summary. Ed25519 signed. \$0.10."""
    return _build_result(_fetch(f"{API_BASE}/oracle/marine/route/summary"))

@mcp.tool()
def get_marine_voyage_forecast() -> dict:
    """Get marine voyage forecast. Ed25519 signed. \$0.10."""
    return _build_result(_fetch(f"{API_BASE}/oracle/marine/voyage/forecast"))

@mcp.tool()
def get_weather(metric: str, lat: float, lon: float, window: int) -> dict:
    """Get parametric weather data. Ed25519 signed. \$0.10.
    metric: temperature, rainfall, wind, drought. window: days (7, 14, 30)."""
    return _build_result(_fetch(f"{API_BASE}/oracle/weather/{lat}/{lon}/{metric}/{window}d"))

@mcp.tool()
def get_defi_yield(protocol: str = "", chain: str = "") -> dict:
    """Get DeFi yield data. Ed25519 signed. \$0.05."""
    params = [f"protocol={protocol}" for p in [protocol] if p] + [f"chain={chain}" for c in [chain] if c]
    qs = f"?{'&'.join(params)}" if params else ""
    return _build_result(_fetch(f"{API_BASE}/oracle/defi/yield{qs}"))

@mcp.tool()
def get_dlc_oracle() -> dict:
    """Get DLC (Discreet Log Contract) oracle attestation. Free."""
    return _fetch(f"{API_BASE}/oracle/dlc")

@mcp.tool()
def get_health() -> dict:
    """Check Mycelia Signal API health, connectivity, and signing key. Free."""
    result = {}
    try:
        result["health"] = _fetch(f"{API_BASE}/health")
        result["health_ok"] = True
    except Exception as e:
        result["health_ok"] = False
        result["health_error"] = str(e)
    try:
        result["preview"] = _fetch(f"{API_BASE}/oracle/price/btc/usd/preview")
        result["preview_ok"] = True
    except Exception as e:
        result["preview_ok"] = False
        result["preview_error"] = str(e)
    result["api_base"] = API_BASE
    return result

@mcp.tool()
def get_catalogue() -> dict:
    """Get full endpoint catalogue with pricing. Free."""
    return _fetch(f"{API_BASE}/sho/info")

if __name__ == "__main__":
    mcp.run()
