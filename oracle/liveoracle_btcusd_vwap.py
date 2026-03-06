# liveoracle_btcusd_vwap.py
"""
Live BTCUSD VWAP Oracle (5-minute window, 7 sources)
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
from oracle.feeds.btcusd_vwap import get_btcusd_vwap_price

app = FastAPI()
# [PROMETHEUS INSTRUMENTED]
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)


@app.get("/oracle/btcusd/vwap")
def oracle_btcusd_vwap():
    result = get_btcusd_vwap_price()
    value = f"{result['price']:.2f}"
    sources = result["sources"]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    canonical = f"v1|BTCUSD|{value}|USD|2|{ts}|{secrets.randbelow(900000) + 100000}|{','.join(sorted(sources))}|vwap"
    h = hashlib.sha256(canonical.encode()).digest()
    sig = PRIVATE_KEY.sign_digest(h)
    return JSONResponse({
        "domain": "BTCUSD",
        "canonical": canonical,
        "signature": base64.b64encode(sig).decode(),
        "pubkey": PUBLIC_KEY.to_string("compressed").hex(),
    })


# Preview cache
_preview_cache_btcusd = {"data": None, "ts": 0.0}
PREVIEW_CACHE_TTL = 300

@app.get("/oracle/btcusd/vwap/preview")
def btcusd_preview():
    now = time.time()
    if _preview_cache_btcusd["data"] is None or (now - _preview_cache_btcusd["ts"]) > PREVIEW_CACHE_TTL:
        result = get_btcusd_vwap_price()
        value = f"{result['price']:.2f}"
        sources = result["sources"]
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _preview_cache_btcusd["data"] = {
            "pair": "BTCUSD",
            "price": value,
            "currency": "USD",
            "timestamp": ts,
            "sources": sorted(sources),
            "method": "vwap",
            "preview": True,
            "signed": False,
            "note": "Preview mode — data up to 5 minutes stale, no cryptographic signature. Set MYCELIA_WALLET_PRIVATE_KEY for signed real-time attestations via x402."
        }
        _preview_cache_btcusd["ts"] = now
    return JSONResponse(_preview_cache_btcusd["data"])

@app.get("/health")
def health():
    return {"status": "ok", "domain": "BTCUSD", "method": "vwap", "version": "v1.1"}

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9101
    uvicorn.run(app, host="0.0.0.0", port=port)
