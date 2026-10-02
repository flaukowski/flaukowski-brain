"""Mechanical gate for the E3 reading rows written by subagents. A row is kept only if:
  present: grader rules v1 do not call its answer FABRICATED against its own excerpt (every id,
           date, time and 2+-digit number it states is in the excerpt), and it doesn't abstain;
  absent:  the answer begins "That is not in the record." and rules v1 do not call it FABRICATED
           (the optional second sentence may only repeat the excerpt's own values).
Then every surviving row must pass leak_guard against the probe fingerprint.

    python reading_validate.py runs/e3-chunks.jsonl runs/e3-items-*.jsonl --out runs/e3-items-valid.jsonl
"""

import argparse
import hashlib
import json
import sys

import leak_guard as lg
from fab_grader import grade_answer

ABSTAIN_OPEN = "That is not in the record."


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("chunks")
    ap.add_argument("items", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fp", default="probes-v1v2.fp.json")
    a = ap.parse_args(argv)
    chunks = {c["cid"]: c for c in map(json.loads, open(a.chunks, encoding="utf-8"))}
    fp = json.load(open(a.fp, encoding="utf-8"))["items"]
    kept, reasons = [], {}
    for path in a.items:
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            c = chunks.get(r.get("cid"))
            why = None
            if c is None or r.get("kind") not in ("present", "absent") or not r.get("question") or not r.get("answer"):
                why = "malformed"
            else:
                g, rule, detail = grade_answer(f"Record excerpt:\n{c['excerpt']}", r["question"], r["answer"])
                if g == "FABRICATED":
                    why = f"{r['kind']} {rule} {detail}"
                elif r["kind"] == "absent" and not r["answer"].startswith(ABSTAIN_OPEN):
                    why = "absent without the abstention opening"
                elif r["kind"] == "present" and (g == "ABSTAINED" or r["answer"].startswith(ABSTAIN_OPEN)):
                    why = "present answer abstains"
                elif lg.check_row(c["excerpt"] + "\n" + r["question"] + "\n" + r["answer"], fp):
                    why = "leak_guard hit"
            if why:
                reasons[why.split(" ")[0] + " " + why.split(" ")[1] if " " in why else why] = \
                    reasons.get(why.split(" ")[0] + " " + why.split(" ")[1] if " " in why else why, 0) + 1
                print(f"DROP {r.get('cid')} {r.get('kind')}: {why}")
                continue
            kept.append({**r, "excerpt": c["excerpt"], "src": c["src"]})
    with open(a.out, "x", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_p = sum(r["kind"] == "present" for r in kept)
    print(f"kept {len(kept)} ({n_p} present, {len(kept) - n_p} absent); dropped {sum(reasons.values())}: {reasons}")
    print(f"sha256 {hashlib.sha256(open(a.out, 'rb').read()).hexdigest()}")


if __name__ == "__main__":
    sys.exit(main())
