"""Leak guard: a training set must not contain the held-out fabrication probes.

Probe v1 (f291f2d2…) and v2 (5c7fcab3…) are held out forever. A model that saw them in training
can pass them by recall, and its score would then measure memory of the test, not honesty about
the record. This refuses a training file that carries any probe item, exactly or nearly.

A probe item leaks into a training row when either holds:
  - exact:  the row contains the item's question, or its gold value when that is 12+ characters
            (after lowercasing and collapsing whitespace);
  - near:   at least CONTAIN (0.5) of the item's excerpt 8-word shingles appear in the row.
            Shingles, not the whole excerpt, so a reworded or truncated copy is still caught.

Short golds (a bare "3", "master") are not checked on their own: they occur in honest rows.

    python leak_guard.py train.jsonl [more.jsonl ...]          # exit 1 and list hits on any leak
    python leak_guard.py train.jsonl --items probe-v1-items.json probe-v2-items.json

Each training line is JSON; every string anywhere in it is searched (messages, prompt, completion).
"""

import argparse
import json
import re
import sys

N = 8
CONTAIN = 0.5
MIN_GOLD = 12
DEFAULT_ITEMS = ["probe-v1-items.json", "probe-v2-items.json"]


def norm(s):
    return re.sub(r"\s+", " ", s.lower()).strip()


def shingles(text, n=N):
    w = re.findall(r"\w+", text.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


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
        d = json.load(open(p, encoding="utf-8"))
        for it in (d["items"] if isinstance(d, dict) else d):
            items.append({**it, "_set": p})
    return items


def check_row(text, items):
    """[(item id, set, how)] for every probe item this row's text leaks."""
    t = norm(text)
    sh = shingles(text)
    hits = []
    for it in items:
        gold = str(it.get("gold") or it.get("expected") or "")
        if norm(it["question"]) in t:
            hits.append((it["id"], it["_set"], "question"))
        elif len(gold) >= MIN_GOLD and norm(gold) in t:
            hits.append((it["id"], it["_set"], "gold"))
        else:
            ex = shingles(it["excerpt"])
            if ex:
                share = len(ex & sh) / len(ex)
                if share >= CONTAIN:
                    hits.append((it["id"], it["_set"], f"excerpt {share:.0%}"))
    return hits


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("train", nargs="+")
    ap.add_argument("--items", nargs="+", default=DEFAULT_ITEMS)
    a = ap.parse_args(argv)
    items = load_items(a.items)
    rows = leaks = 0
    for path in a.train:
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            if not line.strip():
                continue
            rows += 1
            text = "\n".join(strings(json.loads(line)))
            for iid, s, how in check_row(text, items):
                leaks += 1
                print(f"LEAK {path}:{n} carries {iid} ({s}) by {how}")
    print(f"leak_guard: {rows} rows against {len(items)} probe items: {leaks} leak(s)")
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
