#!/usr/bin/env python3
"""
Mycelia Signal — Attestation Archive Collector
Polls oracle backends every 60s and archives signed responses to SQLite.
Updated Mar 17 2026 — new stack endpoints, spec v0.4 canonical parsing.

Writes to: ~/slo/repo/archive/attestations.db
Exports to: ~/slo/repo/archive/public/ (daily JSONL + manifest)
"""

import sqlite3
import json
import time
import os
import sys
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests

# ── Configuration ──────────────────────────────────────────────────

ARCHIVE_DIR = Path(os.path.expanduser("~/slo/repo/archive"))
DB_PATH = ARCHIVE_DIR / "attestations.db"
PUBLIC_DIR = ARCHIVE_DIR / "public"
POLL_INTERVAL = 60  # seconds

PRICE_BASE     = "http://localhost:9200"
ECON_US_BASE   = "http://localhost:9129"
ECON_EU_BASE   = "http://localhost:9130"
ECON_COMM_BASE = "http://localhost:9134"

ORACLES = {
    "BTCUSD":           {"base": PRICE_BASE,     "path": "/oracle/price/btc/usd"},
    "BTCEUR":           {"base": PRICE_BASE,     "path": "/oracle/price/btc/eur"},
    "BTCJPY":           {"base": PRICE_BASE,     "path": "/oracle/price/btc/jpy"},
    "ETHUSD":           {"base": PRICE_BASE,     "path": "/oracle/price/eth/usd"},
    "ETHEUR":           {"base": PRICE_BASE,     "path": "/oracle/price/eth/eur"},
    "ETHJPY":           {"base": PRICE_BASE,     "path": "/oracle/price/eth/jpy"},
    "SOLUSD":           {"base": PRICE_BASE,     "path": "/oracle/price/sol/usd"},
    "SOLEUR":           {"base": PRICE_BASE,     "path": "/oracle/price/sol/eur"},
    "SOLJPY":           {"base": PRICE_BASE,     "path": "/oracle/price/sol/jpy"},
    "XRPUSD":           {"base": PRICE_BASE,     "path": "/oracle/price/xrp/usd"},
    "ADAUSD":           {"base": PRICE_BASE,     "path": "/oracle/price/ada/usd"},
    "DOGEUSD":          {"base": PRICE_BASE,     "path": "/oracle/price/doge/usd"},
    "BTCUSD_VWAP":      {"base": PRICE_BASE,     "path": "/oracle/price/btc/usd/vwap"},
    "BTCEUR_VWAP":      {"base": PRICE_BASE,     "path": "/oracle/price/btc/eur/vwap"},
    "XAUUSD":           {"base": PRICE_BASE,     "path": "/oracle/price/xau/usd"},
    "XAUEUR":           {"base": PRICE_BASE,     "path": "/oracle/price/xau/eur"},
    "XAUJPY":           {"base": PRICE_BASE,     "path": "/oracle/price/xau/jpy"},
    "EURUSD":           {"base": PRICE_BASE,     "path": "/oracle/price/eur/usd"},
    "EURJPY":           {"base": PRICE_BASE,     "path": "/oracle/price/eur/jpy"},
    "EURGBP":           {"base": PRICE_BASE,     "path": "/oracle/price/eur/gbp"},
    "EURCHF":           {"base": PRICE_BASE,     "path": "/oracle/price/eur/chf"},
    "EURCNY":           {"base": PRICE_BASE,     "path": "/oracle/price/eur/cny"},
    "EURCAD":           {"base": PRICE_BASE,     "path": "/oracle/price/eur/cad"},
    "GBPUSD":           {"base": PRICE_BASE,     "path": "/oracle/price/gbp/usd"},
    "GBPJPY":           {"base": PRICE_BASE,     "path": "/oracle/price/gbp/jpy"},
    "GBPCHF":           {"base": PRICE_BASE,     "path": "/oracle/price/gbp/chf"},
    "GBPCNY":           {"base": PRICE_BASE,     "path": "/oracle/price/gbp/cny"},
    "GBPCAD":           {"base": PRICE_BASE,     "path": "/oracle/price/gbp/cad"},
    "USDJPY":           {"base": PRICE_BASE,     "path": "/oracle/price/usd/jpy"},
    "USDCHF":           {"base": PRICE_BASE,     "path": "/oracle/price/usd/chf"},
    "USDCNY":           {"base": PRICE_BASE,     "path": "/oracle/price/usd/cny"},
    "USDCAD":           {"base": PRICE_BASE,     "path": "/oracle/price/usd/cad"},
    "CHFJPY":           {"base": PRICE_BASE,     "path": "/oracle/price/chf/jpy"},
    "CHFCAD":           {"base": PRICE_BASE,     "path": "/oracle/price/chf/cad"},
    "CNYJPY":           {"base": PRICE_BASE,     "path": "/oracle/price/cny/jpy"},
    "CNYCAD":           {"base": PRICE_BASE,     "path": "/oracle/price/cny/cad"},
    "CADJPY":           {"base": PRICE_BASE,     "path": "/oracle/price/cad/jpy"},
    "US_CPI":           {"base": ECON_US_BASE,   "path": "/oracle/econ/us/cpi/preview"},
    "US_CPI_CORE":      {"base": ECON_US_BASE,   "path": "/oracle/econ/us/cpi_core/preview"},
    "US_UNRATE":        {"base": ECON_US_BASE,   "path": "/oracle/econ/us/unrate/preview"},
    "US_NFP":           {"base": ECON_US_BASE,   "path": "/oracle/econ/us/nfp/preview"},
    "US_FEDFUNDS":      {"base": ECON_US_BASE,   "path": "/oracle/econ/us/fedfunds/preview"},
    "US_GDP":           {"base": ECON_US_BASE,   "path": "/oracle/econ/us/gdp/preview"},
    "US_PCE":           {"base": ECON_US_BASE,   "path": "/oracle/econ/us/pce/preview"},
    "US_YIELD_CURVE":   {"base": ECON_US_BASE,   "path": "/oracle/econ/us/yield_curve/preview"},
    "EU_HICP":          {"base": ECON_EU_BASE,   "path": "/oracle/econ/eu/hicp/preview"},
    "EU_HICP_CORE":     {"base": ECON_EU_BASE,   "path": "/oracle/econ/eu/hicp_core/preview"},
    "EU_HICP_SERVICES": {"base": ECON_EU_BASE,   "path": "/oracle/econ/eu/hicp_services/preview"},
    "EU_UNRATE":        {"base": ECON_EU_BASE,   "path": "/oracle/econ/eu/unrate/preview"},
    "EU_GDP":           {"base": ECON_EU_BASE,   "path": "/oracle/econ/eu/gdp/preview"},
    "EU_EMPLOYMENT":    {"base": ECON_EU_BASE,   "path": "/oracle/econ/eu/employment/preview"},
    "WTI":              {"base": ECON_COMM_BASE, "path": "/oracle/econ/commodities/wti/preview"},
    "BRENT":            {"base": ECON_COMM_BASE, "path": "/oracle/econ/commodities/brent/preview"},
    "NATGAS":           {"base": ECON_COMM_BASE, "path": "/oracle/econ/commodities/natgas/preview"},
    "COPPER":           {"base": ECON_COMM_BASE, "path": "/oracle/econ/commodities/copper/preview"},
    "DXY":              {"base": ECON_COMM_BASE, "path": "/oracle/econ/commodities/dxy/preview"},
}

DLC_PORT = 9104
DLC_ATTESTATIONS_PATH = "/dlc/oracle/attestations"

PUBKEYS = {
    "l402_secp256k1": "03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf",
    "x402_ed25519":   "f4f0e52b5f7b54831f965632bf1ebf72769beda4c4e3d36a593f7729ec812615",
    "dlc_schnorr":    "03c1955b8c543494c4ecd86d167105bcc7ca9a91b8e06cb9d6601f2f55a89abfbf",
}

PREVIEW_PAIRS = {k for k, v in ORACLES.items() if "/preview" in v["path"]}


# ── Database ───────────────────────────────────────────────────────

def init_db():
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS attestations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rail TEXT NOT NULL,
            pair TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            price TEXT NOT NULL,
            canonical_message TEXT NOT NULL,
            signature TEXT NOT NULL,
            sig_scheme TEXT NOT NULL,
            pubkey TEXT NOT NULL,
            sources TEXT,
            archived_at TEXT NOT NULL,
            raw_response TEXT NOT NULL,
            event_id TEXT,
            scheduled_at TEXT,
            schema_version INTEGER DEFAULT 1,
            status TEXT DEFAULT 'valid'
        )
    ''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pair_ts ON attestations(pair, timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rail ON attestations(rail)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event ON attestations(event_id)")
    conn.execute('''
        CREATE TABLE IF NOT EXISTS dlc_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            pair TEXT NOT NULL,
            event_type TEXT NOT NULL,
            descriptor TEXT NOT NULL,
            nonce_data TEXT NOT NULL,
            maturity_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            published_at TEXT,
            status TEXT DEFAULT 'pending'
        )
    ''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_pair ON dlc_events(pair, maturity_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_status ON dlc_events(status)")
    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Canonical Parsing ──────────────────────────────────────────────

def parse_canonical(canonical):
    """Parse Oracle Attestation Spec v0.4 canonical string.
    Price: v1|PRICE|PAIR|PRICE|CURRENCY|DECIMALS|TIMESTAMP|NONCE|SOURCES|METHOD
    Econ:  v1|REGION|INDICATOR|VALUE|UNIT|...|NONCE
    """
    parts = canonical.split("|")
    if len(parts) < 4 or parts[0] != "v1":
        return None
    if parts[1] == "PRICE" and len(parts) >= 10:
        return {
            "pair":      parts[2],
            "price":     parts[3],
            "currency":  parts[4],
            "decimals":  parts[5] if len(parts) > 5 else "",
            "timestamp": parts[6] if len(parts) > 6 else "",
            "nonce":     parts[7] if len(parts) > 7 else "",
            "sources":   parts[8].split(",") if len(parts) > 8 else [],
            "method":    parts[9] if len(parts) > 9 else "",
        }
    elif len(parts) >= 4:
        return {
            "pair":      parts[2],
            "price":     parts[3],
            "currency":  parts[4] if len(parts) > 4 else "",
            "decimals":  "",
            "timestamp": parts[6] if len(parts) > 6 else "",
            "nonce":     parts[len(parts)-1],
            "sources":   [],
            "method":    "",
        }
    return None


# ── Oracle Polling ─────────────────────────────────────────────────

def is_duplicate(conn, rail, pair, timestamp, signature):
    row = conn.execute(
        "SELECT 1 FROM attestations WHERE rail=? AND pair=? AND timestamp=? AND signature=? LIMIT 1",
        (rail, pair, timestamp, signature)
    ).fetchone()
    return row is not None


def archive_oracle_response(conn, rail, pair, data, sig_scheme, pubkey, is_preview=False):
    if is_preview:
        price = data.get("price", "")
        currency = data.get("currency", "")
        timestamp = str(data.get("timestamp", ""))
        sources = data.get("sources", [])
        canonical = f"preview|{pair}|{price}|{currency}"
        signature = ""
        if is_duplicate(conn, rail, pair, timestamp, signature):
            return
        conn.execute(
            "INSERT INTO attestations (rail, pair, timestamp, price, canonical_message, signature, sig_scheme, pubkey, sources, archived_at, raw_response, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rail, pair, timestamp, price, canonical, signature, "none", pubkey,
             json.dumps(sources if isinstance(sources, list) else sources.split(",")),
             datetime.now(timezone.utc).isoformat(), json.dumps(data), "preview")
        )
        conn.commit()
        return

    canonical = data.get("canonical", "") or data.get("canonicalstring", "")
    parsed = parse_canonical(canonical)
    if not parsed:
        print(f"  WARN: malformed canonical for {pair}: {canonical[:80]}")
        conn.execute(
            "INSERT INTO attestations (rail, pair, timestamp, price, canonical_message, signature, sig_scheme, pubkey, sources, archived_at, raw_response, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rail, pair, "", "", canonical, data.get("signature", ""), sig_scheme, pubkey,
             None, datetime.now(timezone.utc).isoformat(), json.dumps(data), "malformed")
        )
        conn.commit()
        return

    if is_duplicate(conn, rail, pair, parsed["timestamp"], data.get("signature", "")):
        return

    conn.execute(
        "INSERT INTO attestations (rail, pair, timestamp, price, canonical_message, signature, sig_scheme, pubkey, sources, archived_at, raw_response, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (rail, pair, parsed["timestamp"], parsed["price"], canonical,
         data.get("signature", ""), sig_scheme, pubkey,
         json.dumps(parsed["sources"]), datetime.now(timezone.utc).isoformat(),
         json.dumps(data), "valid")
    )
    conn.commit()


def poll_oracles():
    conn = get_conn()
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    archived = 0
    errors = 0
    for pair, cfg in ORACLES.items():
        url = f"{cfg['base']}{cfg['path']}"
        is_preview = pair in PREVIEW_PAIRS
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            archive_oracle_response(
                conn, "collector", pair, data,
                "ecdsa_secp256k1", PUBKEYS["l402_secp256k1"],
                is_preview=is_preview
            )
            archived += 1
        except Exception as e:
            errors += 1
            print(f"  ERROR polling {pair} ({url}): {e}")
    conn.close()
    if errors:
        print(f"[{now}] Polled {len(ORACLES)} endpoints: {archived} ok, {errors} errors")
    return archived


def poll_dlc():
    conn = get_conn()
    try:
        url = f"http://localhost:{DLC_PORT}{DLC_ATTESTATIONS_PATH}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        attestations = data if isinstance(data, list) else data.get("attestations", [])
        for att in attestations:
            event_id = att.get("event_id", "")
            if not event_id:
                continue
            row = conn.execute(
                "SELECT 1 FROM attestations WHERE event_id=? AND rail='dlc' LIMIT 1",
                (event_id,)
            ).fetchone()
            if row:
                continue
            canonical = att.get("canonical", "")
            parsed = parse_canonical(canonical) if canonical else None
            conn.execute(
                "INSERT INTO attestations (rail, pair, timestamp, price, canonical_message, signature, sig_scheme, pubkey, sources, archived_at, raw_response, event_id, scheduled_at, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("dlc",
                 parsed["pair"] if parsed else att.get("pair", "BTCUSD"),
                 parsed["timestamp"] if parsed else att.get("timestamp", ""),
                 parsed["price"] if parsed else att.get("price", ""),
                 canonical,
                 att.get("signature", ""),
                 "schnorr_bip340",
                 PUBKEYS["dlc_schnorr"],
                 json.dumps(parsed["sources"]) if parsed else None,
                 datetime.now(timezone.utc).isoformat(),
                 json.dumps(att),
                 event_id,
                 att.get("scheduled_at", att.get("maturity_at", "")),
                 "valid")
            )
            conn.commit()
    except Exception as e:
        print(f"  DLC poll error: {e}")
    finally:
        conn.close()


# ── Daily JSONL Export ─────────────────────────────────────────────

def export_daily(date_str=None):
    if date_str is None:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM attestations WHERE timestamp LIKE ? ORDER BY timestamp",
        (f"{date_str}%",)
    ).fetchall()
    if not rows:
        print(f"No attestations for {date_str}")
        conn.close()
        return
    groups = {}
    for row in rows:
        key = (row["rail"], row["pair"])
        if key not in groups:
            groups[key] = []
        groups[key].append(dict(row))
    exported = 0
    for (rail, pair), attestations in groups.items():
        dir_path = PUBLIC_DIR / rail / pair
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{date_str}.jsonl"
        with open(file_path, "w") as f:
            for att in attestations:
                record = {
                    "pair": att["pair"],
                    "timestamp": att["timestamp"],
                    "price": att["price"],
                    "canonical": att["canonical_message"],
                    "signature": att["signature"],
                    "sig_scheme": att["sig_scheme"],
                    "pubkey": att["pubkey"],
                    "sources": json.loads(att["sources"]) if att["sources"] else [],
                    "status": att["status"],
                }
                if att["event_id"]:
                    record["event_id"] = att["event_id"]
                f.write(json.dumps(record) + "\n")
                exported += 1
    update_manifest(conn)
    update_latest(conn)
    conn.close()
    print(f"Exported {exported} attestations for {date_str}")


def update_manifest(conn):
    rows = conn.execute('''
        SELECT rail, pair,
               MIN(DATE(timestamp)) as first_date,
               MAX(DATE(timestamp)) as last_date
        FROM attestations
        WHERE status IN ('valid', 'preview')
        GROUP BY rail, pair
    ''').fetchall()
    pairs = {}
    for rail, pair, first_date, last_date in rows:
        if pair not in pairs:
            pairs[pair] = {"first_attestation": first_date, "latest_attestation": last_date, "rails": []}
        pairs[pair]["rails"].append(rail)
        if first_date and first_date < pairs[pair]["first_attestation"]:
            pairs[pair]["first_attestation"] = first_date
        if last_date and last_date > pairs[pair]["latest_attestation"]:
            pairs[pair]["latest_attestation"] = last_date
    for pair in pairs:
        pairs[pair]["rails"] = sorted(set(pairs[pair]["rails"]))
    total = conn.execute("SELECT COUNT(*) FROM attestations WHERE status IN ('valid', 'preview')").fetchone()[0]
    manifest = {
        "oracle": "Mycelia Signal",
        "pubkeys": PUBKEYS,
        "pairs": pairs,
        "total_attestations": total,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(PUBLIC_DIR / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)


def update_latest(conn):
    rows = conn.execute('''
        SELECT pair, rail, timestamp, price, canonical_message, signature
        FROM attestations
        WHERE status IN ('valid', 'preview')
        AND id IN (
            SELECT MAX(id) FROM attestations
            WHERE status IN ('valid', 'preview') GROUP BY pair
        )
    ''').fetchall()
    latest = {}
    for pair, rail, ts, price, canonical, sig in rows:
        latest[pair] = {
            "rail": rail,
            "timestamp": ts,
            "price": price,
            "canonical": canonical,
            "signature": sig,
        }
    with open(PUBLIC_DIR / "latest.json", "w") as f:
        json.dump(latest, f, indent=2)


# ── Export Scheduler ───────────────────────────────────────────────

def export_scheduler():
    while True:
        now = datetime.now(timezone.utc)
        tomorrow = now.replace(hour=0, minute=5, second=0, microsecond=0) + timedelta(days=1)
        if now.hour == 0 and now.minute < 5:
            tomorrow = now.replace(hour=0, minute=5, second=0, microsecond=0)
        wait = (tomorrow - now).total_seconds()
        print(f"Next export in {wait/3600:.1f} hours at {tomorrow.isoformat()}")
        time.sleep(wait)
        try:
            export_daily()
        except Exception as e:
            print(f"Export error: {e}")


# ── Main Loop ──────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Mycelia Signal — Attestation Archive Collector")
    print(f"Database: {DB_PATH}")
    print(f"Public export: {PUBLIC_DIR}")
    print(f"Poll interval: {POLL_INTERVAL}s")
    print(f"Pairs: {len(ORACLES)} ({len(ORACLES) - len(PREVIEW_PAIRS)} paid + {len(PREVIEW_PAIRS)} preview)")
    print("=" * 60)
    init_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        export_daily(today)
    except Exception as e:
        print(f"Startup export: {e}")
    export_thread = threading.Thread(target=export_scheduler, daemon=True)
    export_thread.start()
    cycle = 0
    while True:
        cycle += 1
        poll_oracles()
        if cycle % 5 == 0:
            poll_dlc()
        if cycle % 10 == 0:
            try:
                conn = get_conn()
                update_latest(conn)
                update_manifest(conn)
                conn.close()
            except Exception as e:
                print(f"Manifest update error: {e}")
        if cycle % 30 == 0:
            try:
                conn = get_conn()
                total = conn.execute("SELECT COUNT(*) FROM attestations").fetchone()[0]
                today_count = conn.execute(
                    "SELECT COUNT(*) FROM attestations WHERE timestamp LIKE ?",
                    (f"{today}%",)
                ).fetchone()[0]
                conn.close()
                print(f"[STATS] Total: {total} | Today: {today_count}")
            except Exception:
                pass
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "export":
        init_db()
        date = sys.argv[2] if len(sys.argv) > 2 else None
        export_daily(date)
    else:
        main()
