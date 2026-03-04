# dlc/server.py
"""
DLC Oracle API Server
SLO v1

Endpoints:
  GET /dlc/oracle/pubkey                  — Oracle public key
  GET /dlc/oracle/announcements           — List all announcements
  GET /dlc/oracle/announcements/{eid}     — Single announcement
  GET /dlc/oracle/attestations/{eid}      — Single attestation
  GET /dlc/oracle/status                  — Oracle status and stats
"""

import json
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# Add parent to path so we can import dlc.attestor
sys.path.insert(0, str(Path(__file__).parent.parent))

from dlc.attestor import load_oracle_key, DATA_DIR

app = FastAPI(title="SLO DLC Oracle", version="v1")
# [PROMETHEUS INSTRUMENTED]
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app)


def _load_json(path):
    with open(path) as f:
        return json.load(f)


@app.get("/dlc/oracle/pubkey")
def get_pubkey():
    sk = load_oracle_key()
    return {
        "oracle_pubkey": sk.public_key.format().hex(),
        "key_format": "compressed",
        "key_bytes": 33,
        "curve": "secp256k1",
    }


@app.get("/dlc/oracle/announcements")
def list_announcements():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(DATA_DIR.glob("*.announcement.json"))
    announcements = []
    for f in files:
        ann = _load_json(f)
        announcements.append({
            "event_id": ann["event_id"],
            "pair": ann["pair"],
            "maturity": ann["maturity"],
            "num_digits": ann["num_digits"],
            "created_at": ann["created_at"],
        })
    return {"count": len(announcements), "announcements": announcements}


@app.get("/dlc/oracle/announcements/{eid}")
def get_announcement(eid: str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{eid}.announcement.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Announcement not found: {eid}")
    return _load_json(path)


@app.get("/dlc/oracle/attestations/{eid}")
def get_attestation(eid: str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{eid}.attestation.json"
    if not path.exists():
        ann_path = DATA_DIR / f"{eid}.announcement.json"
        if ann_path.exists():
            ann = _load_json(ann_path)
            raise HTTPException(
                status_code=425,
                detail=f"Event announced but not yet attested. Maturity: {ann['maturity']}",
            )
        raise HTTPException(status_code=404, detail=f"Event not found: {eid}")
    return _load_json(path)


@app.get("/dlc/oracle/status")
def get_status():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ann_count = len(list(DATA_DIR.glob("*.announcement.json")))
    att_count = len(list(DATA_DIR.glob("*.attestation.json")))
    pending = ann_count - att_count

    sk = load_oracle_key()

    return {
        "oracle_pubkey": sk.public_key.format().hex(),
        "announcements": ann_count,
        "attestations": att_count,
        "pending": pending,
        "num_digits": 5,
        "pairs": ["BTCUSD"],
        "version": "v1",
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "slo-dlc", "version": "v1"}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9104
    uvicorn.run(app, host="0.0.0.0", port=port)
