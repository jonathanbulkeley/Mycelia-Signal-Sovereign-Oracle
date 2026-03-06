# liveoracle_solusd_spot.py
"""
Live SOLUSD Spot Oracle (Median of 9 sources with USDT normalization)
SLO v1 — L402-gated via L402 proxy

9 sources:
  Tier 1 (USD): Coinbase, Kraken, Bitstamp, Gemini, Bitfinex
  Tier 2 (USDT normalized): Binance, OKX, Gate.io, Bybit

Port: 9107
Path: /oracle/solusd
"""
import hashlib, base64, sys, time
import secrets
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
from ecdsa import SigningKey, SECP256k1
import sys; sys.path.insert(0, "/home/jonathan_bulkeley/slo"); from oracle.keys import PRIVATE_KEY, PUBLIC_KEY

sys.path.insert(0, str(Path(__file__).parent.parent))
from oracle.feeds.solusd import get_solusd_price

app = FastAPI()
# [PROMETHEUS INSTRUMENTED]
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)

# Key loaded from oracle/keys/ (persistent, shared across all backends)

@app.get("/oracle/solusd")
def oracle_solusd():
    result = get_solusd_price()
    value = f"{result['price']:.4f}"
    sources = result["sources"]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    canonical = f"v1|SOLUSD|{value}|USD|4|{ts}|{secrets.randbelow(900000) + 100000}|{','.join(sorted(sources))}|median"
    h = hashlib.sha256(canonical.encode()).digest()
    sig = PRIVATE_KEY.sign_digest(h)
    return JSONResponse({
        "domain": "SOLUSD",
        "canonical": canonical,
        "signature": base64.b64encode(sig).decode(),
        "pubkey": PUBLIC_KEY.to_string("compressed").hex(),
    })


# Preview cache
_preview_cache_solusd = {"data": None, "ts": 0.0}
PREVIEW_CACHE_TTL = 300

@app.get("/oracle/solusd/preview")
def solusd_preview():
    now = time.time()
    if _preview_cache_solusd["data"] is None or (now - _preview_cache_solusd["ts"]) > PREVIEW_CACHE_TTL:
        result = get_solusd_price()
        value = f"{result['price']:.2f}"
        sources = result["sources"]
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _preview_cache_solusd["data"] = {
            "pair": "SOLUSD",
            "price": value,
            "currency": "USD",
            "timestamp": ts,
            "sources": sorted(sources),
            "method": "median",
            "preview": True,
            "signed": False,
            "note": "Preview mode — data up to 5 minutes stale, no cryptographic signature. Set MYCELIA_WALLET_PRIVATE_KEY for signed real-time attestations via x402."
        }
        _preview_cache_solusd["ts"] = now
    return JSONResponse(_preview_cache_solusd["data"])

@app.get("/health")
def health():
    return {"status": "ok", "domain": "SOLUSD", "version": "v1"}

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9107
    print(f"SLO SOLUSD Oracle (L402-backed) starting on :{port}")
    print(f"  Public key: {PUBLIC_KEY.to_string('compressed').hex()}")
    print(f"  Sources: Coinbase, Kraken, Bitstamp, Gemini, Bitfinex, Binance, OKX, Gate.io, Bybit")
    print(f"  Endpoint:   GET /oracle/solusd (gated by L402 proxy)")
    print(f"  Health:     GET /health (ungated)")
    uvicorn.run(app, host="0.0.0.0", port=port)
