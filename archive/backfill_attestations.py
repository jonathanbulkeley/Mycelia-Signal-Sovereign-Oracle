import sqlite3, json, sys, time, os

DB = sys.argv[1] if len(sys.argv) > 1 else None
if not DB or not os.path.exists(DB):
    sys.exit("usage: backfill_attestations.py <path-to-db>   (file must exist)")

BATCH = 10000
con = sqlite3.connect(DB)
con.execute("PRAGMA journal_mode=WAL")

total = con.execute(
    "SELECT COUNT(*) FROM attestations WHERE timestamp NOT GLOB '[0-9]*'"
).fetchone()[0]
print(f"rows needing backfill: {total}")
if total == 0:
    sys.exit("nothing to do")

fixed = skipped = 0
t0 = time.time()
last_id = -1

while True:
    rows = con.execute(
        """SELECT id, canonical_message, raw_response
           FROM attestations
           WHERE timestamp NOT GLOB '[0-9]*' AND id > ?
           ORDER BY id LIMIT ?""", (last_id, BATCH)).fetchall()
    if not rows:
        break
    updates = []
    for rid, canon, raw in rows:
        last_id = rid
        parts = (canon or "").split("|")
        # v1|PRICE|PAIR|PRICE|CURRENCY|DECIMALS|SOURCES|METHOD|TIMESTAMP|NONCE
        if len(parts) < 10 or parts[0] != "v1" or parts[1] != "PRICE":
            skipped += 1
            continue
        ts, srcs = parts[8], parts[6]
        if not ts.isdigit():
            skipped += 1
            continue
        try:
            d = json.loads(raw) if raw else {}
        except Exception:
            d = {}
        pk = d.get("pubkey")
        ss = d.get("signingScheme")
        updates.append((ts, json.dumps(srcs.split(",")), pk, ss, rid))
    if updates:
        con.executemany(
            """UPDATE attestations
               SET timestamp = ?, sources = ?,
                   pubkey = COALESCE(?, pubkey),
                   sig_scheme = COALESCE(?, sig_scheme)
               WHERE id = ?""", updates)
        con.commit()
        fixed += len(updates)
    el = time.time() - t0
    print(f"  {fixed+skipped}/{total}  fixed={fixed} skipped={skipped}  {el:.0f}s", flush=True)

print(f"DONE fixed={fixed} skipped={skipped} in {time.time()-t0:.0f}s")
con.close()
