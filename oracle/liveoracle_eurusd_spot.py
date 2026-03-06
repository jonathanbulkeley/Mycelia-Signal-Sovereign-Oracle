"""
Live EURUSD Spot Oracle (Median of 7 Sources)
SLO v1 — L402-gated via Aperture

7 sources across 4 continents:
  - ECB (Frankfurter)       — European Central Bank
  - Bank of Canada          — North American central bank (derived: EURCAD / USDCAD)
  - RBA                     — Asia-Pacific central bank (derived: AUDUSD / AUDEUR)
  - Norges Bank             — Scandinavian central bank (derived: EURNOK / USDNOK)
  - Czech National Bank     — Central European central bank (derived: EUR_CZK / USD_CZK)
  - Kraken                  — Live exchange (direct EUR/USD pair)
  - Bitstamp                — Live exchange (direct EUR/USD pair)
"""

import hashlib
import secrets
import time
import base64
import sys
import re
import statistics
import requests as http_requests
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
from ecdsa import SigningKey, SECP256k1
import sys; sys.path.insert(0, "/home/jonathan_bulkeley/slo"); from oracle.keys import PRIVATE_KEY, PUBLIC_KEY

# Key loaded from oracle/keys/ (persistent, shared across all backends)

app = FastAPI(
    title="SLO EURUSD Spot Oracle",
    description="L402-gated EURUSD price oracle (sits behind Aperture)",
)
# [PROMETHEUS INSTRUMENTED]
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)


def fetch_ecb():
    """European Central Bank via Frankfurter API — direct EUR/USD rate."""
    r = http_requests.get(
        "https://api.frankfurter.dev/v1/latest?symbols=USD", timeout=5
    )
    return float(r.json()["rates"]["USD"])


def fetch_bank_of_canada():
    """Bank of Canada — derived from EURCAD / USDCAD."""
    r1 = http_requests.get(
        "https://www.bankofcanada.ca/valet/observations/FXEURCAD/json?recent=1",
        timeout=5,
    )
    eurcad = float(r1.json()["observations"][0]["FXEURCAD"]["v"])

    r2 = http_requests.get(
        "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=1",
        timeout=5,
    )
    usdcad = float(r2.json()["observations"][0]["FXUSDCAD"]["v"])

    return round(eurcad / usdcad, 6)


def fetch_rba():
    """Reserve Bank of Australia — derived from AUD/USD / AUD/EUR via XML RSS."""
    r = http_requests.get(
        "https://www.rba.gov.au/rss/rss-cb-exchange-rates.xml", timeout=5
    )
    xml = r.text

    usd_match = re.search(r"AU:\s+([\d.]+)\s+USD\s+=\s+1\s+AUD", xml)
    eur_match = re.search(r"AU:\s+([\d.]+)\s+EUR\s+=\s+1\s+AUD", xml)

    if not usd_match or not eur_match:
        raise ValueError("Could not parse RBA XML")

    aud_usd = float(usd_match.group(1))
    aud_eur = float(eur_match.group(1))

    return round(aud_usd / aud_eur, 6)


def fetch_norges_bank():
    """Norges Bank (Norway) — derived from EURNOK / USDNOK via SDMX JSON."""
    r1 = http_requests.get(
        "https://data.norges-bank.no/api/data/EXR/B.EUR.NOK.SP?format=sdmx-json&lastNObservations=1",
        timeout=5,
    )
    d1 = r1.json()
    obs1 = d1["data"]["dataSets"][0]["series"]["0:0:0:0"]["observations"]
    eurnok = float(obs1[list(obs1.keys())[-1]][0])

    r2 = http_requests.get(
        "https://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=sdmx-json&lastNObservations=1",
        timeout=5,
    )
    d2 = r2.json()
    obs2 = d2["data"]["dataSets"][0]["series"]["0:0:0:0"]["observations"]
    usdnok = float(obs2[list(obs2.keys())[-1]][0])

    return round(eurnok / usdnok, 6)


def fetch_cnb():
    """Czech National Bank — derived from EUR/CZK / USD/CZK via daily text file."""
    r = http_requests.get(
        "https://www.cnb.cz/en/financial-markets/foreign-exchange-market/central-bank-exchange-rate-fixing/central-bank-exchange-rate-fixing/daily.txt",
        timeout=5,
    )
    lines = r.text.strip().split("\n")

    eur_rate = None
    usd_rate = None

    for line in lines[2:]:
        parts = line.split("|")
        if len(parts) >= 5:
            code = parts[3].strip()
            amount = float(parts[2].strip())
            rate = float(parts[4].strip())
            if code == "EUR":
                eur_rate = rate / amount
            elif code == "USD":
                usd_rate = rate / amount

    if eur_rate is None or usd_rate is None:
        raise ValueError("Could not parse CNB data")

    return round(eur_rate / usd_rate, 6)


def fetch_kraken():
    """Kraken exchange — direct EUR/USD forex pair."""
    r = http_requests.get(
        "https://api.kraken.com/0/public/Ticker?pair=EURUSD", timeout=5
    )
    pair = list(r.json()["result"].keys())[0]
    return float(r.json()["result"][pair]["c"][0])


def fetch_bitstamp():
    """Bitstamp exchange — direct EUR/USD forex pair."""
    r = http_requests.get(
        "https://www.bitstamp.net/api/v2/ticker/eurusd/", timeout=5
    )
    return float(r.json()["last"])


def get_price():
    prices = []
    sources = []
    for name, f in [
        ("ecb", fetch_ecb),
        ("bankofcanada", fetch_bank_of_canada),
        ("rba", fetch_rba),
        ("norgesbank", fetch_norges_bank),
        ("cnb", fetch_cnb),
        ("kraken", fetch_kraken),
        ("bitstamp", fetch_bitstamp),
    ]:
        try:
            p = f()
            prices.append(p)
            sources.append(name)
            print(f"  {name}: {p}")
        except Exception as e:
            print(f"  {name}: FAILED ({e})")
    if len(prices) < 4:
        raise RuntimeError(f"insufficient sources ({len(prices)} of 7, need 4)")
    return round(statistics.median(prices), 5), sources


@app.get("/oracle/eurusd")
def oracle_eurusd():
    value_raw, sources = get_price()
    value = f"{value_raw:.5f}"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    source_str = ",".join(sorted(sources))
    canonical = (
        f"v1|EURUSD|{value}|USD|5|{ts}|{secrets.randbelow(900000) + 100000}|{source_str}|median"
    )
    h = hashlib.sha256(canonical.encode()).digest()
    sig = PRIVATE_KEY.sign_digest(h)

    return JSONResponse(
        {
            "domain": "EURUSD",
            "canonical": canonical,
            "signature": base64.b64encode(sig).decode(),
            "pubkey": PUBLIC_KEY.to_string("compressed").hex(),
        }
    )



# Preview cache
_preview_cache_eurusd = {"data": None, "ts": 0.0}
PREVIEW_CACHE_TTL = 300

@app.get("/oracle/eurusd/preview")
def eurusd_preview():
    now = time.time()
    if _preview_cache_eurusd["data"] is None or (now - _preview_cache_eurusd["ts"]) > PREVIEW_CACHE_TTL:
        price, sources = get_price()
        value = f"{price:.5f}"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _preview_cache_eurusd["data"] = {
            "pair": "EURUSD",
            "price": value,
            "currency": "USD",
            "timestamp": ts,
            "sources": sorted(sources),
            "method": "median",
            "preview": True,
            "signed": False,
            "note": "Preview mode — data up to 5 minutes stale, no cryptographic signature. Set MYCELIA_WALLET_PRIVATE_KEY for signed real-time attestations via x402."
        }
        _preview_cache_eurusd["ts"] = now
    return JSONResponse(_preview_cache_eurusd["data"])

@app.get("/health")
def health():
    return {"status": "ok", "domain": "EURUSD", "version": "v1"}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9103
    print(f"SLO EURUSD Oracle (L402-backed) starting on :{port}")
    print(f"  Public key: {PUBLIC_KEY.to_string('compressed').hex()}")
    print(f"  Sources: ECB, Bank of Canada, RBA, Norges Bank, CNB, Kraken, Bitstamp")
    print(f"  Endpoint:   GET /oracle/eurusd (gated by Aperture)")
    print(f"  Health:     GET /health (ungated)")
    uvicorn.run(app, host="127.0.0.1", port=port)
