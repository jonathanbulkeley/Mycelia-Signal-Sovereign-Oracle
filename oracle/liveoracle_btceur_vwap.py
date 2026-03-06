"""
Live BTCEUR VWAP Oracle — Cross-rate from BTCUSD VWAP / EURUSD
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
from oracle.feeds.btceur_vwap import get_btceur_vwap_price

app = FastAPI()
# [PROMETHEUS INSTRUMENTED]
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)


@app.get("/oracle/btceur/vwap")
def oracle_btceur_vwap():
    result = get_btceur_vwap_price()
    value = f"{result['price']:.2f}"
    sources = result["sources"]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    canonical = f"v1|BTCEUR|{value}|EUR|2|{ts}|{secrets.randbelow(900000) + 100000}|{','.join(sorted(sources))}|vwap"
    h = hashlib.sha256(canonical.encode()).digest()
    sig = PRIVATE_KEY.sign_digest(h)
    return JSONResponse({
        "domain": "BTCEUR",
        "canonical": canonical,
        "signature": base64.b64encode(sig).decode(),
        "pubkey": PUBLIC_KEY.to_string("compressed").hex(),
    })


# Preview cache
_preview_cache_btceur = {"data": None, "ts": 0.0}
PREVIEW_CACHE_TTL = 300

@app.get("/oracle/btceur/vwap/preview")
def btceur_preview():
    now = time.time()
    if _preview_cache_btceur["data"] is None or (now - _preview_cache_btceur["ts"]) > PREVIEW_CACHE_TTL:
        result = get_btceur_vwap_price()
        value = f"{result['price']:.2f}"
        sources = result["sources"]
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _preview_cache_btceur["data"] = {
            "pair": "BTCEUR",
            "price": value,
            "currency": "EUR",
            "timestamp": ts,
            "sources": sorted(set(sources)),
            "method": "vwap",
            "preview": True,
            "signed": False,
            "note": "Preview mode — data up to 5 minutes stale, no cryptographic signature. Set MYCELIA_WALLET_PRIVATE_KEY for signed real-time attestations via x402."
        }
        _preview_cache_btceur["ts"] = now
    return JSONResponse(_preview_cache_btceur["data"])

@app.get("/health")
def health():
    return {"status": "ok", "domain": "BTCEUR", "method": "vwap"}

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9111
    print(f"BTCEUR VWAP oracle on :{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
