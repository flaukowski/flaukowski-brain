"""Leak guard: a training set must not contain the held-out fabrication probes.

Probe v1 (f291f2d2…) and v2 (5c7fcab3…) are held out forever. A model that saw them in training
can pass them by recall, and its score would then measure memory of the test, not honesty about
the record. This refuses a training file that carries any probe item, exactly or nearly.

The check runs against a FINGERPRINT of the probes, not the probes: sha256 of word sequences, so
the guard can run on a training host without the held-out text ever being copied there.

A probe item leaks into a training row when either holds (text lowercased, split into words):
  - exact:  the row contains the item's whole question as a word sequence, or its gold when the
            gold is 12+ characters;
  - near:   at least CONTAIN (0.5) of the item's excerpt 8-word shingles appear in the row.
            Shingles, not the whole excerpt, so a reworded or truncated copy is still caught.

Short golds (a bare "3", "master") are not checked on their own: they occur in honest rows.

    python leak_guard.py fingerprint probe-v1-items.json probe-v2-items.json --out probes.fp.json
    python leak_guard.py check --fp probes.fp.json train.jsonl [more.jsonl ...]   # exit 1 on any leak

Each training line is JSON; every string anywhere in it is searched (messages, prompt, completion).
"""

import argparse
import hashlib
import json
import re
import sys

N = 8
CONTAIN = 0.5
MIN_GOLD = 12
DEFAULT_ITEMS = ["probe-v1-items.json", "probe-v2-items.json"]


def words(text):
    return re.findall(r"\w+", text.lower())


def h(ws):
    return hashlib.sha256(" ".join(ws).encode()).hexdigest()


def shingles(text, n=N):
    w = words(text)
    return {h(w[i:i + n]) for i in range(len(w) - n + 1)}


def windows(w, n):
    return {h(w[i:i + n]) for i in range(len(w) - n + 1)}


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def load_items(paths):
    items = []
    for p in paths:
        raw = open(p, "rb").read()
        d = json.loads(raw)
        for it in (d["items"] if isinstance(d, dict) else d):
            items.append({**it, "_set": hashlib.sha256(raw).hexdigest()[:8]})
    return items


def fingerprint(items):
    fp = []
    for it in items:
        q = words(it["question"])
        gold = str(it.get("gold") or it.get("expected") or "")
        g = words(gold) if len(gold) >= MIN_GOLD else []
        fp.append({"id": it["id"], "set": it["_set"],
                   "q": [len(q), h(q)] if q else None,
                   "g": [len(g), h(g)] if g else None,
                   "ex": sorted(shingles(it["excerpt"]))})
    return fp


def check_row(text, fp):
    """[(item id, set, how)] for every probe item this row's text leaks."""
    w = words(text)
    sh = windows(w, N)
    cache = {}

    def has(seq):
        n, digest = seq
        if n not in cache:
            cache[n] = windows(w, n)
        return digest in cache[n]

    hits = []
    for it in fp:
        if it["q"] and has(it["q"]):
            hits.append((it["id"], it["set"], "question"))
        elif it["g"] and has(it["g"]):
            hits.append((it["id"], it["set"], "gold"))
        elif it["ex"]:
            share = len(sh.intersection(it["ex"])) / len(it["ex"])
            if share >= CONTAIN:
                hits.append((it["id"], it["set"], f"excerpt {share:.0%}"))
    return hits


def cmd_fingerprint(a):
    fp = fingerprint(load_items(a.items))
    with open(a.out, "x", encoding="utf-8") as f:
        json.dump({"n": N, "contain": CONTAIN, "min_gold": MIN_GOLD, "items": fp}, f)
    print(f"leak_guard: fingerprint of {len(fp)} items -> {a.out} "
          f"(sha256 {hashlib.sha256(open(a.out, 'rb').read()).hexdigest()})")
    return 0


def cmd_check(a):
    d = json.load(open(a.fp, encoding="utf-8"))
    if (d["n"], d["contain"], d["min_gold"]) != (N, CONTAIN, MIN_GOLD):
        sys.exit("leak_guard: fingerprint was made with different parameters; refusing")
    fp = d["items"]
    rows = leaks = 0
    for path in a.train:
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            if not line.strip():
                continue
            rows += 1
            text = "\n".join(strings(json.loads(line)))
            for iid, s, how in check_row(text, fp):
                leaks += 1
                print(f"LEAK {path}:{n} carries {iid} (set {s}) by {how}")
    print(f"leak_guard: {rows} rows in {len(a.train)} file(s) against {len(fp)} probe items: {leaks} leak(s)")
    return 1 if leaks else 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("fingerprint")
    f.add_argument("items", nargs="*", default=DEFAULT_ITEMS)
    f.add_argument("--out", required=True)
    c = sp.add_parser("check")
    c.add_argument("--fp", required=True)
    c.add_argument("train", nargs="+")
    a = ap.parse_args(argv)
    return {"fingerprint": cmd_fingerprint, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
