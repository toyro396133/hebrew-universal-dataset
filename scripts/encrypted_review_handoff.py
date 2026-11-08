#!/usr/bin/env python3
"""Encrypted handoff of blinded external-text review packets.

Needs third-party dependency: pip install "cryptography>=42,<48".
GitHub Actions uploads ONLY authenticated ciphertext; private keys and raw text
remain unavailable in the public repository. No passphrase is logged or passed
as a CLI argument; passphrase comes from a private environment variable.
"""
import argparse
import hashlib
import io
import json
import os
import sys
import zipfile
from pathlib import Path

try:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
except ImportError as exc:
    raise SystemExit('Install dependency: python -m pip install "cryptography>=42,<48"') from exc

MAGIC = b"HU-REVIEW-AESGCM-01\n"
FILE_NAMES = (
    "blind-review-packet.jsonl",
    "internal-manifest.json",
    "REVIEW-INSTRUCTIONS.md",
)
KDF_PARAMS = {"n": 2**15, "r": 8, "p": 1}


def key_from_phrase(passphrase, salt):
    if not isinstance(passphrase, str) or len(passphrase) < 20:
        raise ValueError("A private 20+-character passphrase is required")
    return Scrypt(salt=salt, length=32, **KDF_PARAMS).derive(passphrase.encode("utf-8"))


def parse_jsonl(blob):
    try:
        return [json.loads(line) for line in blob.decode("utf-8").splitlines() if line.strip()]
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Review JSONL is invalid") from exc


def check_packet(files):
    if set(files) != set(FILE_NAMES):
        raise ValueError("Review bundle must contain only the required files")
    packet = parse_jsonl(files["blind-review-packet.jsonl"])
    manifest = json.loads(files["internal-manifest.json"].decode("utf-8"))
    if manifest.get("status") != "REVIEW_PENDING_NOT_CALIBRATED":
        raise ValueError("Unrecognized review manifest status")
    items = manifest.get("items")
    if not isinstance(items, list) or not packet or len(packet) != len(items):
        raise ValueError("Manifest count does not match packet")
    manifest_by_id = {i.get("id"): i for i in items}
    if len(manifest_by_id) != len(items):
        raise ValueError("Duplicate manifest IDs")
    seen = set()
    for row in packet:
        if not isinstance(row, dict) or set(row) != {"id", "text"}:
            raise ValueError("Blind packet must contain only id and text")
        rid, content = row["id"], row["text"]
        if not isinstance(rid, str) or not isinstance(content, str) or rid in seen:
            raise ValueError("Invalid or duplicate packet ID")
        seen.add(rid)
        item = manifest_by_id.get(rid)
        if not item:
            raise ValueError("Packet ID absent from manifest")
        if hashlib.sha256(content.encode("utf-8")).hexdigest() != item.get("source_text_sha256"):
            raise ValueError("Packet text does not match manifest hash")
    if len(seen) != len(manifest_by_id):
        raise ValueError("Manifest contains missing packet documents")
    return len(packet)


def encrypt(review_dir, ciphertext, passphrase):
    review_dir, ciphertext = Path(review_dir), Path(ciphertext)
    files = {name: (review_dir / name).read_bytes() for name in FILE_NAMES}
    count = check_packet(files)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in FILE_NAMES:
            zf.writestr(name, files[name])
    salt, nonce = os.urandom(16), os.urandom(12)
    header = MAGIC + salt + nonce
    encrypted = AESGCM(key_from_phrase(passphrase, salt)).encrypt(nonce, buffer.getvalue(), header)
    ciphertext.parent.mkdir(parents=True, exist_ok=True)
    with ciphertext.open("xb") as f:
        f.write(header + encrypted)
    return {"status":"ENCRYPTED_ONLY", "item_count":count,
            "sha256_encrypted":hashlib.sha256(ciphertext.read_bytes()).hexdigest(),
            "bytes_encrypted":ciphertext.stat().st_size}


def decrypt(ciphertext, output_dir, passphrase):
    ciphertext, output_dir = Path(ciphertext), Path(output_dir)
    raw = ciphertext.read_bytes()
    if not raw.startswith(MAGIC) or len(raw) < len(MAGIC) + 16 + 12 + 16:
        raise ValueError("Unrecognized or truncated encrypted packet")
    offset = len(MAGIC)
    salt, nonce = raw[offset:offset+16], raw[offset+16:offset+28]
    try:
        decrypted = AESGCM(key_from_phrase(passphrase, salt)).decrypt(
            nonce, raw[offset+28:], raw[:offset+28])
    except InvalidTag as exc:
        raise ValueError("Incorrect passphrase or altered ciphertext") from exc
    with zipfile.ZipFile(io.BytesIO(decrypted), "r") as zf:
        if set(zf.namelist()) != set(FILE_NAMES):
            raise ValueError("Unexpected archive file contents")
        files = {name: zf.read(name) for name in FILE_NAMES}
    count = check_packet(files)
    if output_dir.exists():
        raise ValueError("Output directory exists; refusing to overwrite review files")
    output_dir.mkdir(parents=True)
    for name in FILE_NAMES:
        (output_dir / name).write_bytes(files[name])
    return {"status":"DECRYPTED_LOCALLY", "item_count":count,
            "blind_packet":str(output_dir / FILE_NAMES[0]),
            "private_manifest":str(output_dir / FILE_NAMES[1])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passphrase-env", default="REVIEW_PACKET_PASSPHRASE",
                        help="Name of environment variable containing secret; never pass secret as argv")
    sub = parser.add_subparsers(dest="command", required=True)
    e = sub.add_parser("encrypt")
    e.add_argument("--review-dir", type=Path, required=True)
    e.add_argument("--output", type=Path, required=True)
    d = sub.add_parser("decrypt")
    d.add_argument("--input", type=Path, required=True)
    d.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    secret = os.environ.get(args.passphrase_env)
    try:
        if not secret:
            raise ValueError(f"Missing environment variable {args.passphrase_env}")
        if args.command == "encrypt":
            result = encrypt(args.review_dir, args.output, secret)
        else:
            result = decrypt(args.input, args.output_dir, secret)
    except (ValueError, FileExistsError, OSError, KeyError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
