#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Apply one of the patches in patches/*.json to YOUR OWN 256 KB flash dump.

    python apply_patch.py --list
    python apply_patch.py <patch-id> <stock_dump.bin> <patched_out.bin>

No firmware is shipped with this repository. The tool refuses to write
anything unless your dump matches the exact stock image the patch was
written for (SHA-256), and it checks the result the same way.
"""
import argparse
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_patches():
    out = {}
    for fn in sorted(glob.glob(os.path.join(HERE, "patches", "*.json"))):
        with open(fn, encoding="utf-8") as f:
            p = json.load(f)
        out[p["id"]] = p
    return out


def apply(patch, stock):
    if len(stock) != patch["image_size"]:
        raise SystemExit("dump is %d bytes, expected %d"
                         % (len(stock), patch["image_size"]))
    got = hashlib.sha256(stock).hexdigest()
    if got != patch["stock_sha256"]:
        raise SystemExit(
            "this dump is not the stock image this patch was written for.\n"
            "  your dump : %s\n  expected  : %s\n"
            "Nothing was written. A different software version needs its own "
            "patch." % (got, patch["stock_sha256"]))
    img = bytearray(stock)
    for op in patch["ops"]:
        off = int(op["offset"], 16)
        new = bytes.fromhex(op["write"])
        old = bytes(img[off:off + len(new)])
        if op["expect"].startswith("ff*"):
            if any(b != 0xFF for b in old):
                raise SystemExit("flash at %s is not empty" % op["offset"])
        elif old != bytes.fromhex(op["expect"]):
            raise SystemExit("unexpected bytes at %s" % op["offset"])
        img[off:off + len(new)] = new
    img = bytes(img)
    if hashlib.sha256(img).hexdigest() != patch["patched_sha256"]:
        raise SystemExit("internal error: result checksum mismatch")
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", action="store_true", help="list patches")
    ap.add_argument("patch_id", nargs="?")
    ap.add_argument("stock", nargs="?")
    ap.add_argument("out", nargs="?")
    a = ap.parse_args()
    patches = load_patches()
    if a.list or not a.patch_id:
        for p in patches.values():
            print("%-26s SW %s  [%s]\n    %s" % (
                p["id"], p["sw_pn"], p["status"], p["summary"]))
        return 0
    if a.patch_id not in patches:
        raise SystemExit("unknown patch id; use --list")
    if not (a.stock and a.out):
        raise SystemExit("usage: apply_patch.py <patch-id> <stock.bin> <out.bin>")
    if os.path.exists(a.out):
        raise SystemExit("%s already exists; refusing to overwrite" % a.out)
    p = patches[a.patch_id]
    with open(a.stock, "rb") as f:
        img = apply(p, f.read())
    with open(a.out, "wb") as f:
        f.write(img)
    print("wrote %s  (%d bytes changed in %d places)" % (
        a.out, sum(len(o["write"]) // 2 for o in p["ops"]), len(p["ops"])))
    print("status of this patch: %s" % p["status"])
    for n in p.get("notes", []):
        print("note: %s" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
