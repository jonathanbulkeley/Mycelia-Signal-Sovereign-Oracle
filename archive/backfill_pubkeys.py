import sqlite3, sys, os, time

DB = sys.argv[1] if len(sys.argv) > 1 else None
if not DB or not os.path.exists(DB):
    sys.exit("usage: backfill_pubkeys.py <path-to-db>   (file must exist)")

con = sqlite3.connect(DB)
con.execute("PRAGMA journal_mode=WAL")

# Rows whose pubkey column disagrees with the pubkey inside their own
# raw_response. Cause: collector.py:271 passed a hardcoded
# ("ecdsa_secp256k1", PUBKEYS["l402_secp256k1"]) for every price oracle while
# those oracles sign Ed25519. The payload was always right; only the indexed
# columns were wrong. Fixed at source 2026-08-22 (commit 7ea0ffd).
sel = """SELECT COUNT(*) FROM attestations
         WHERE json_valid(raw_response)
           AND json_extract(raw_response,'$.pubkey') IS NOT NULL
           AND pubkey <> json_extract(raw_response,'$.pubkey')"""
before = con.execute(sel).fetchone()[0]
print(f"rows with a pubkey mismatch: {before}")
if before == 0:
    sys.exit("nothing to do")

t0 = time.time()
con.execute("""
UPDATE attestations
   SET pubkey     = json_extract(raw_response,'$.pubkey'),
       sig_scheme = COALESCE(json_extract(raw_response,'$.signingScheme'), sig_scheme)
 WHERE json_valid(raw_response)
   AND json_extract(raw_response,'$.pubkey') IS NOT NULL
   AND pubkey <> json_extract(raw_response,'$.pubkey')""")
con.commit()
after = con.execute(sel).fetchone()[0]
print(f"DONE remaining={after} in {time.time()-t0:.0f}s")
con.close()
