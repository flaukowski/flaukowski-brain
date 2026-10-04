"""Mechanical gate for E4's two-candidate rows (rows carry their own excerpt). A row is kept only if:
  present: grader rules v1 do not call its answer FABRICATED against its own excerpt, and it doesn't abstain;
  absent:  the answer begins "That is not in the record." and rules v1 do not call it FABRICATED;
  every:   leak_guard against the probe fingerprint (fp2) finds nothing, the excerpt is 80-400 chars,
           and no excerpt is a near-duplicate (>= 50% shared 8-word shingles) of an earlier kept row.
Optionally --slice: any row sharing even ONE 8-word shingle with a held-out slice item is dropped.

    python e4_validate.py runs/e4-rows-*.jsonl --out runs/e4-rows-valid.jsonl [--slice runs/e4-slice.json]
"""
import argparse
import hashlib
import json
import sys

import leak_guard as lg
from fab_grader import grade_answer

OPEN = "That is not in the record."


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("rows", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fp", default="probes-v1v2.fp2.json")
    ap.add_argument("--slice")
    a = ap.parse_args(argv)
    fp = json.load(open(a.fp, encoding="utf-8"))["items"]
    banned = set()
    if a.slice:
        for it in json.load(open(a.slice, encoding="utf-8"))["items"]:
            for f in ("excerpt", "question", "gold"):
                banned |= lg.shingles(str(it.get(f) or ""))
    kept, seen, reasons = [], [], {}

    def drop(r, why):
        reasons[why] = reasons.get(why, 0) + 1
        print(f"DROP {r.get('pattern')}/{r.get('kind')} {why}: {str(r.get('question'))[:70]}")

    for path in a.rows:
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                reasons["unparseable"] = reasons.get("unparseable", 0) + 1
                continue
            ex, q, ans, kind = r.get("excerpt", ""), r.get("question", ""), r.get("answer", ""), r.get("kind")
            if kind not in ("present", "absent") or not (q and ans) or not (80 <= len(ex) <= 400):
                drop(r, "malformed")
                continue
            g, rule, _ = grade_answer(f"Record excerpt:\n{ex}", q, ans)
            if g == "FABRICATED":
                drop(r, f"{rule}")
                continue
            if kind == "absent" and not ans.startswith(OPEN):
                drop(r, "absent-without-opening")
                continue
            if kind == "present" and (g == "ABSTAINED" or ans.startswith(OPEN)):
                drop(r, "present-abstains")
                continue
            if lg.check_row(ex + "\n" + q + "\n" + ans, fp):
                drop(r, "probe-leak")
                continue
            sh = lg.shingles(ex)
            if banned and (lg.shingles(ex + " " + q + " " + ans) & banned):
                drop(r, "shares-slice-shingle")
                continue
            if sh and any(len(sh & s) / len(sh) >= 0.5 for s in seen):
                drop(r, "near-duplicate")
                continue
            seen.append(sh)
            kept.append(r)
    with open(a.out, "x", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    by = {}
    for r in kept:
        by[r["pattern"]] = by.get(r["pattern"], 0) + 1
    print(f"kept {len(kept)} {dict(sorted(by.items()))}; dropped {sum(reasons.values())}: {reasons}")
    print(f"sha256 {hashlib.sha256(open(a.out, 'rb').read()).hexdigest()}")


if __name__ == "__main__":
    sys.exit(main())
