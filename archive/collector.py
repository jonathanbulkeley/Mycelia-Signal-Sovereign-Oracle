#!/usr/bin/env python3
"""
Mycelia Signal — Attestation Archive Collector
Standalone service that polls oracle backends every 60s and archives
signed responses to SQLite. Zero changes to running proxies.

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

ORACLES = {
    "BTCUSD":      {"port": 9100, "path": "/oracle/btcusd"},
    "BTCUSD_VWAP": {"port": 9101, "path": "/oracle/btcusd/vwap"},
    "ETHUSD":      {"port": 9102, "path": "/oracle/ethusd"},
    "EURUSD":      {"port": 9103, "path": "/oracle/eurusd"},
    "XAUUSD":      {"port": 9105, "path": "/oracle/xauusd"},
    "BTCEUR":      {"port": 9106, "path": "/oracle/btceur"},
    "SOLUSD":      {"port": 9107, "path": "/oracle/solusd"},
    "ETHEUR":      {"port": 9108, "path": "/oracle/etheur"},
    "SOLEUR":      {"port": 9109, "path": "/oracle/soleur"},
    "XAUEUR":      {"port": 9110, "path": "/oracle/xaueur"},
    "BTCEUR_VWAP": {"port": 9111, "path": "/oracle/btceur/vwap"},
}

DLC_PORT = 9104
DLC_ATTESTATIONS_PATH = "/dlc/oracle/attestations"
DLC_ANNOUNCEMENTS_PATH = "/dlc/oracle/announcements"

PUBKEYS = {
    "l402_secp256k1": "0236a051b7a0384ebe19fe31fcee6837bff7a9532a2a9ae04731ea04df5cd94adf",
    "x402_ed25519": "c40ad8cbd866189eecb7c68091a984644fb7736ef3b8d96cd31b600ef0072623",
    "dlc_schnorr": "03ec3f43aa21878c55c2838fbf54aa2408d25abdcacd4cef6f32c48f3a53eda843",
}


# ── Database ───────────────────────────────────────────────────────

def init_db():
    """Initialize SQLite database with WAL mode and schema."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
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
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pair_ts ON attestations(pair, timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rail ON attestations(rail)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event ON attestations(event_id)")

    conn.execute("""
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
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_pair ON dlc_events(pair, maturity_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_event_status ON dlc_events(status)")

    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")


def get_conn():
    """Get a new SQLite connection (one per thread)."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Oracle Polling ─────────────────────────────────────────────────

def parse_canonical(canonical):
    """Parse v1 canonical string into components."""
    parts = canonical.split("|")
    if len(parts) < 9 or parts[0] != "v1":
        return None
    return {
        "pair": parts[1],
        "price": parts[2],
        "currency": parts[3],
        "decimals": parts[4],
        "timestamp": parts[5],
        "nonce": parts[6],
        "sources": parts[7].split(","),
        "method": parts[8],
    }


def is_duplicate(conn, rail, pair, timestamp, signature):
    """Check if this exact attestation is already archived."""
    row = conn.execute(
        "SELECT 1 FROM attestations WHERE rail=? AND pair=? AND timestamp=? AND signature=? LIMIT 1",
        (rail, pair, timestamp, signature)
    ).fetchone()
    return row is not None


def archive_oracle_response(conn, rail, pair, data, sig_scheme, pubkey):
    """Archive a single oracle backend response."""
    canonical = data.get("canonical", "")
    parsed = parse_canonical(canonical)
    if not parsed:
        print(f"  WARN: malformed canonical for {pair}: {canonical[:50]}")
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
    """Poll all oracle backends once."""
    conn = get_conn()
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    archived = 0
    errors = 0

    for pair, cfg in ORACLES.items():
        url = f"http://localhost:{cfg['port']}{cfg['path']}"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            archive_oracle_response(
                conn, "collector", pair, data,
                "ecdsa_secp256k1", PUBKEYS["l402_secp256k1"]
            )
            archived += 1
        except Exception as e:
            errors += 1
            print(f"  ERROR polling {pair}: {e}")

    conn.close()
    if errors:
        print(f"[{now}] Polled {len(ORACLES)} backends: {archived} ok, {errors} errors")
    return archived


def poll_dlc():
    """Poll DLC attestations for any new ones since last check."""
    conn = get_conn()
    try:
        url = f"http://localhost:{DLC_PORT}{DLC_ATTESTATIONS_PATH}"
        resp = requests.get(url, timeout=15)
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
    """Export attestations for a given date to JSONL files."""
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
    """Regenerate manifest.json with current archive stats."""
    rows = conn.execute("""
        SELECT rail, pair,
               MIN(DATE(timestamp)) as first_date,
               MAX(DATE(timestamp)) as last_date
        FROM attestations
        WHERE status='valid'
        GROUP BY rail, pair
    """).fetchall()

    pairs = {}
    for rail, pair, first_date, last_date in rows:
        if pair not in pairs:
            pairs[pair] = {"first_attestation": first_date, "latest_attestation": last_date, "rails": []}
        pairs[pair]["rails"].append(rail)
        if first_date < pairs[pair]["first_attestation"]:
            pairs[pair]["first_attestation"] = first_date
        if last_date > pairs[pair]["latest_attestation"]:
            pairs[pair]["latest_attestation"] = last_date

    for pair in pairs:
        pairs[pair]["rails"] = sorted(set(pairs[pair]["rails"]))

    total = conn.execute("SELECT COUNT(*) FROM attestations WHERE status='valid'").fetchone()[0]

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
    """Write latest.json with most recent attestation per pair."""
    rows = conn.execute("""
        SELECT pair, rail, timestamp, price, canonical_message, signature
        FROM attestations
        WHERE status='valid'
        AND id IN (
            SELECT MAX(id) FROM attestations WHERE status='valid' GROUP BY pair
        )
    """).fetchall()

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
    """Run daily export at 00:05 UTC."""
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
    print(f"Pairs: {len(ORACLES)}")
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
