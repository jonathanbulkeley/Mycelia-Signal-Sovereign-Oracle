# oracle/keys/bip340.py
# BIP-340 Schnorr signing utilities for oracle attestation backends.
# Loads the persistent secp256k1 key, converts to coincurve format,
# exposes sign/verify functions for v2 canonical string signing.
# TODO: Replace TAG with working group confirmed domain string.

import hashlib
from pathlib import Path
from coincurve import PrivateKey, PublicKeyXOnly

# PENDING - replace before v2 deployment
# Example: "bitcoin-oracle/attestation-v1"
TAG = "[PENDING - working group to confirm]"

KEYS_DIR = Path(__file__).parent
KEY_PATH = KEYS_DIR / "oracle_secp256k1.key"

def _load_private_key() -> PrivateKey:
    sk_hex = KEY_PATH.read_text().strip()
    sk_bytes = bytes.fromhex(sk_hex)
    sk = PrivateKey(sk_bytes)
    pubkey_compressed = sk.public_key.format(compressed=True)
    if pubkey_compressed[0] == 0x03:
        SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
        sk_int = int.from_bytes(sk_bytes, "big")
        sk_negated = (SECP256K1_ORDER - sk_int).to_bytes(32, "big")
        sk = PrivateKey(sk_negated)
    return sk

_PRIVATE_KEY = _load_private_key()
BIP340_PUBKEY_HEX: str = _PRIVATE_KEY.public_key.format(compressed=True)[1:].hex()

def tagged_hash(tag: str, msg: bytes) -> bytes:
    tag_hash = hashlib.sha256(tag.encode("utf-8")).digest()
    return hashlib.sha256(tag_hash + tag_hash + msg).digest()

def sign_bip340(canonical: str) -> str:
    if TAG.startswith("[PENDING"):
        raise ValueError(
            "BIP-340 tag string not yet confirmed. "
            "Replace TAG in bip340.py with the working group confirmed value."
        )
    message = canonical.encode("utf-8")
    digest = tagged_hash(TAG, message)
    signature = _PRIVATE_KEY.sign_schnorr(digest)
    return signature.hex()

def verify_bip340(canonical: str, signature_hex: str, pubkey_hex: str) -> bool:
    message = canonical.encode("utf-8")
    digest = tagged_hash(TAG, message)
    sig = bytes.fromhex(signature_hex)
    pubkey = PublicKeyXOnly(bytes.fromhex(pubkey_hex))
    return pubkey.verify(sig, digest)

if __name__ == "__main__":
    print(f"BIP-340 x-only pubkey: {BIP340_PUBKEY_HEX}")
    print(f"Tag: {TAG}")
    print("\nTesting sign/verify with placeholder tag...")
    test_canonical = "v1|BTCUSD|84212.50|USD|2|2026-03-07T09:00:00Z|482910|binance,coinbase,kraken|median"
    message = test_canonical.encode("utf-8")
    digest = tagged_hash("test-tag", message)
    sig = _PRIVATE_KEY.sign_schnorr(digest)
    sig_hex = sig.hex()
    pubkey = PublicKeyXOnly(bytes.fromhex(BIP340_PUBKEY_HEX))
    valid = pubkey.verify(sig, digest)
    print(f"Signature:    {sig_hex}")
    print(f"Verification: {'PASS' if valid else 'FAIL'}")
