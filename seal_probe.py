"""Seal a new held-out probe set (probe v3 onward) on the author's own machine.

v1, v2, the E4 slice and the E5 items have been public since 2026-10-07 (they were committed to this
public repo). This tool exists so the next set never has to leave its author's machine: the author
runs it where the items live, and only its outputs travel. It never prints item text.

    python seal_probe.py seal probe-v3-items.json --public-fp probes-v1v2-e5.fp3.json \
        --public-items probe-slice-e4-items.json --out-dir sealed/

What it does, in order (any failure refuses and writes nothing):
  1. validates the file: {"name", "frozen", "items": [...]}; each item has a unique id, kind
     "present" or "absent", and non-empty excerpt, question and gold; no two items share a question;
  2. checks every item against the sets that are already public (fingerprints and/or raw files) with
     leak_guard's own rule; any overlap refuses, because an item anyone can already read cannot be sealed;
  3. writes <out-dir>/<stem>.fp.json, the leak_guard fingerprint (hashes only), and
     <out-dir>/<stem>.seal.json: counts, raw and canonical sha256 (canonical = probe_cells'
     canonical_sha), the fingerprint's sha256 and the tool's own sha256.

What travels: the .seal.json (to the ledger and the pre-registration) and the .fp.json (to whoever
must keep the set out of training data). The items file itself does not. The fingerprint hashes a
present item's gold when it is 12+ characters; a gold drawn from a small public set (an id that
appears in a public record) can be confirmed by guessing, so hand the fingerprint only to hosts that
need it, and prefer golds that are not enumerable.
"""
import argparse
import hashlib
import json
import os
import sys

import leak_guard as lg

KINDS = ("present", "absent")


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def canonical_sha(obj):
    return sha_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def refuse(msg):
    print(f"seal_probe: REFUSED: {msg}")
    sys.exit(2)


def validate(d):
    if not isinstance(d, dict) or not isinstance(d.get("items"), list):
        refuse('the file must be {"name", "frozen", "items": [...]}')
    for k in ("name", "frozen"):
        if not d.get(k):
            refuse(f"missing {k!r}")
    ids, questions = set(), set()
    for n, it in enumerate(d["items"]):
        where = f"item #{n}"
        if not isinstance(it, dict):
            refuse(f"{where} is not an object")
        iid = it.get("id")
        if not iid or iid in ids:
            refuse(f"{where} has a missing or duplicate id")
        ids.add(iid)
        if it.get("kind") not in KINDS:
            refuse(f"item {iid}: kind must be one of {KINDS}")
        for k in ("excerpt", "question", "gold"):
            if not str(it.get(k) or "").strip():
                refuse(f"item {iid}: empty {k}")
        q = " ".join(lg.words(it["question"]))
        if q in questions:
            refuse(f"item {iid}: its question duplicates another item's")
        questions.add(q)
    if not d["items"]:
        refuse("no items")


def public_overlaps(items, fp_paths, item_paths):
    """[(v3 id, public id, how)] for every v3 item that a public set's fingerprint matches."""
    fps = []
    for p in fp_paths:
        f = json.load(open(p, encoding="utf-8"))
        if (f["n"], f["contain"], f["min_gold"]) != (lg.N, lg.CONTAIN, lg.MIN_GOLD):
            refuse(f"{p} was made with different leak_guard parameters")
        fps.extend(f["items"])
    if item_paths:
        fps.extend(lg.fingerprint(lg.load_items(item_paths)))
    hits = []
    for it in items:
        text = "\n".join([it["excerpt"], it["question"], str(it["gold"])])
        for pid, _set, how in lg.check_row(text, fps):
            hits.append((it["id"], pid, how))
    return hits, len(fps)


def cmd_seal(a):
    raw = open(a.items, "rb").read()
    d = json.loads(raw)
    validate(d)
    items = d["items"]
    if not a.public_fp and not a.public_items:
        refuse("name the public sets to check against (--public-fp and/or --public-items)")
    hits, n_public = public_overlaps(items, a.public_fp, a.public_items)
    if hits:
        for v, p, how in hits:
            print(f"OVERLAP v3 item {v} matches public item {p} by {how}")
        refuse(f"{len(hits)} overlap(s) with sets that are already public")
    os.makedirs(a.out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(a.items))[0]
    fp_path = os.path.join(a.out_dir, stem + ".fp.json")
    seal_path = os.path.join(a.out_dir, stem + ".seal.json")
    for p in (fp_path, seal_path):
        if os.path.exists(p):
            refuse(f"{p} exists; a seal is written once")
    loaded = [{**it, "_set": sha_bytes(raw)[:8]} for it in items]
    fp_bytes = json.dumps({"n": lg.N, "contain": lg.CONTAIN, "min_gold": lg.MIN_GOLD,
                           "items": lg.fingerprint(loaded)}).encode("utf-8")
    seal = {"name": d["name"], "frozen": d["frozen"], "n_items": len(items),
            "n_present": sum(i["kind"] == "present" for i in items),
            "n_absent": sum(i["kind"] == "absent" for i in items),
            "raw_sha256": sha_bytes(raw), "canonical_sha256": canonical_sha(d),
            "fingerprint_file": os.path.basename(fp_path), "fingerprint_sha256": sha_bytes(fp_bytes),
            "public_items_checked": n_public, "public_overlaps": 0,
            "tool_sha256": sha_bytes(open(__file__, "rb").read()),
            "leak_guard_sha256": sha_bytes(open(lg.__file__, "rb").read())}
    with open(fp_path, "xb") as f:
        f.write(fp_bytes)
    with open(seal_path, "x", encoding="utf-8") as f:
        json.dump(seal, f, indent=1)
    print(f"seal_probe: {seal['n_items']} items ({seal['n_present']} present, {seal['n_absent']} absent); "
          f"0 overlaps with {n_public} public items")
    print(f"seal_probe: raw {seal['raw_sha256']}")
    print(f"seal_probe: canonical {seal['canonical_sha256']}")
    print(f"seal_probe: fingerprint {fp_path} sha256 {seal['fingerprint_sha256']}")
    print(f"seal_probe: seal record {seal_path}")
    return 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("seal")
    s.add_argument("items")
    s.add_argument("--public-fp", nargs="*", default=[])
    s.add_argument("--public-items", nargs="*", default=[])
    s.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    return {"seal": cmd_seal}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
