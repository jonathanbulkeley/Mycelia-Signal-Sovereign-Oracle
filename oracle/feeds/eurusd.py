"""
EURUSD Feed Module — Median of 7 sources across 4 continents
"""
import re
import csv
import io
import statistics
import requests


def fetch_ecb():
    r = requests.get("https://api.frankfurter.dev/v1/latest?symbols=USD", timeout=5)
    return float(r.json()["rates"]["USD"])



def fetch_ecb_direct():
    r = requests.get(
        "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?lastNObservations=1&format=csvdata",
        timeout=5,
    )
    reader = csv.DictReader(io.StringIO(r.text))
    row = next(reader)
    return float(row["OBS_VALUE"])

def fetch_bank_of_canada():
    r1 = requests.get(
        "https://www.bankofcanada.ca/valet/observations/FXEURCAD/json?recent=1", timeout=5
    )
    eurcad = float(r1.json()["observations"][0]["FXEURCAD"]["v"])
    r2 = requests.get(
        "https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=1", timeout=5
    )
    usdcad = float(r2.json()["observations"][0]["FXUSDCAD"]["v"])
    return round(eurcad / usdcad, 6)


def fetch_rba():
    r = requests.get("https://www.rba.gov.au/rss/rss-cb-exchange-rates.xml", timeout=5)
    xml = r.text
    usd_match = re.search(r"AU:\s+([\d.]+)\s+USD\s+=\s+1\s+AUD", xml)
    eur_match = re.search(r"AU:\s+([\d.]+)\s+EUR\s+=\s+1\s+AUD", xml)
    if not usd_match or not eur_match:
        raise ValueError("Could not parse RBA XML")
    aud_usd = float(usd_match.group(1))
    aud_eur = float(eur_match.group(1))
    return round(aud_usd / aud_eur, 6)


def fetch_norges_bank():
    r1 = requests.get(
        "https://data.norges-bank.no/api/data/EXR/B.EUR.NOK.SP?format=sdmx-json&lastNObservations=1",
        timeout=5,
    )
    d1 = r1.json()
    obs1 = d1["data"]["dataSets"][0]["series"]["0:0:0:0"]["observations"]
    eurnok = float(obs1[list(obs1.keys())[-1]][0])
    r2 = requests.get(
        "https://data.norges-bank.no/api/data/EXR/B.USD.NOK.SP?format=sdmx-json&lastNObservations=1",
        timeout=5,
    )
    d2 = r2.json()
    obs2 = d2["data"]["dataSets"][0]["series"]["0:0:0:0"]["observations"]
    usdnok = float(obs2[list(obs2.keys())[-1]][0])
    return round(eurnok / usdnok, 6)


def fetch_cnb():
    r = requests.get(
        "https://www.cnb.cz/en/financial-markets/foreign-exchange-market/"
        "central-bank-exchange-rate-fixing/central-bank-exchange-rate-fixing/daily.txt",
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
    r = requests.get("https://api.kraken.com/0/public/Ticker?pair=EURUSD", timeout=5)
    pair = list(r.json()["result"].keys())[0]
    return float(r.json()["result"][pair]["c"][0])


def fetch_bitstamp():
    r = requests.get("https://www.bitstamp.net/api/v2/ticker/eurusd/", timeout=5)
    return float(r.json()["last"])


SOURCES = [
    ("ecb", fetch_ecb),
    ("ecbdirect", fetch_ecb_direct),
    ("bankofcanada", fetch_bank_of_canada),
    ("rba", fetch_rba),
    ("norgesbank", fetch_norges_bank),
    ("cnb", fetch_cnb),
    ("kraken", fetch_kraken),
    ("bitstamp", fetch_bitstamp),
]


def get_eurusd_price():
    prices = []
    sources = []
    for name, fn in SOURCES:
        try:
            p = fn()
            prices.append(p)
            sources.append(name)
        except Exception:
            pass
    if len(prices) < 4:
        raise RuntimeError(f"EURUSD: insufficient sources ({len(prices)}/7, need 4)")
    return {
        "price": round(statistics.median(prices), 5),
        "sources": sources,
    }
