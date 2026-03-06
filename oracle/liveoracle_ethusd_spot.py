# liveoracle_ethusd_spot.py
"""
Live ETHUSD Spot Oracle (Median of Last Trades)
"""

import hashlib, base64, sys, time, statistics, requests
import secrets
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
from ecdsa import SigningKey, SECP256k1
import sys; sys.path.insert(0, "/home/jonathan_bulkeley/slo"); from oracle.keys import PRIVATE_KEY, PUBLIC_KEY

app = FastAPI()
# [PROMETHEUS INSTRUMENTED]
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)


# Key loaded from oracle/keys/ (persistent, shared across all backends)

def fetch_coinbase():
    r = requests.get("https://api.exchange.coinbase.com/products/ETH-USD/ticker", timeout=5)
    return float(r.json()["price"])

def fetch_kraken():
    r = requests.get("https://api.kraken.com/0/public/Ticker?pair=ETHUSD", timeout=5)
    pair = list(r.json()["result"].keys())[0]
    return float(r.json()["result"][pair]["c"][0])

def fetch_gemini():
    r = requests.get("https://api.gemini.com/v1/pubticker/ethusd", timeout=5)
    return float(r.json()["last"])

def fetch_bitfinex():
    r = requests.get("https://api-pub.bitfinex.com/v2/ticker/tETHUSD", timeout=5)
    return float(r.json()[6])

def fetch_bitstamp():
    r = requests.get("https://www.bitstamp.net/api/v2/ticker/ethusd/", timeout=5)
    return float(r.json()["last"])

def get_price():
    prices = []
    sources = []
    for name, f in [("coinbase", fetch_coinbase), ("kraken", fetch_kraken), ("bitstamp", fetch_bitstamp), ("gemini", fetch_gemini), ("bitfinex", fetch_bitfinex)]:
        try:
            prices.append(f())
            sources.append(name)
        except: pass
    if len(prices) < 3:
        raise RuntimeError("insufficient sources")
    return round(statistics.median(prices), 2), sources

@app.get("/oracle/ethusd")
def oracle_ethusd():
    price, sources = get_price()
    value = f"{price:.2f}"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    canonical = f"v1|ETHUSD|{value}|USD|2|{ts}|{secrets.randbelow(900000) + 100000}|{','.join(sorted(sources))}|median"
    h = hashlib.sha256(canonical.encode()).digest()
    sig = PRIVATE_KEY.sign_digest(h)
    return JSONResponse({"domain":"ETHUSD","canonical":canonical,"signature":base64.b64encode(sig).decode(),"pubkey":PUBLIC_KEY.to_string("compressed").hex()})

# Preview cache
_preview_cache_ethusd = {"data": None, "ts": 0.0}
PREVIEW_CACHE_TTL = 300

@app.get("/oracle/ethusd/preview")
def ethusd_preview():
    now = time.time()
    if _preview_cache_ethusd["data"] is None or (now - _preview_cache_ethusd["ts"]) > PREVIEW_CACHE_TTL:
        price = get_price()
        value = f"{price:.2f}"
        sources = ["binance_us","bitfinex","bitstamp","coinbase","gemini","kraken"]
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _preview_cache_ethusd["data"] = {
            "pair": "ETHUSD",
            "price": value,
            "currency": "USD",
            "timestamp": ts,
            "sources": sorted(sources),
            "method": "median",
            "preview": True,
            "signed": False,
            "note": "Preview mode — data up to 5 minutes stale, no cryptographic signature. Set MYCELIA_WALLET_PRIVATE_KEY for signed real-time attestations via x402."
        }
        _preview_cache_ethusd["ts"] = now
    return JSONResponse(_preview_cache_ethusd["data"])

@app.get("/health")
def health():
    return {"status":"ok","domain":"ETHUSD","version":"v1"}
if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv)>1 else 9102

    uvicorn.run(app, host="0.0.0.0", port=port)
