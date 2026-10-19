"""Score sux-controls-rerun once the verdicts are recorded and the key is opened.

    python -I tally.py <verdicts.json> <sux2-key.json> <parent-verdicts.json> <parent-key.json>

Prints the per-control table (REAL / PLAUSIBLE / FALSE for K0 and K1), the totals, the pre-registered
reading (K1 at most 4 FALSE over the four controls; K1 REAL more than 2 below K0 is a cost), and the
K0 re-grade against the parent study's verdicts on the same findings (agreement counts, decides nothing).
"""
import json
import sys

CONTROLS = [("5a5b667", "X1"), ("505a024", "X2"), ("0035364", "X3"), ("248f7cb", "X4")]
CLASSES = ("REAL", "PLAUSIBLE", "FALSE")

v, key, pv, pkey = (json.load(open(p, encoding="utf-8")) for p in sys.argv[1:5])
a_is = key["a_is"]
parent_a_is = pkey["a_is"]


def counts(entries):
    c = {k: 0 for k in CLASSES}
    for e in entries:
        c[e["class"]] += 1
    return c


tot = {"K0": {k: 0 for k in CLASSES}, "K1": {k: 0 for k in CLASSES}}
print("| Control | K0 REAL/PLAUSIBLE/FALSE | K1 REAL/PLAUSIBLE/FALSE |")
print("|---|---|---|")
by_set = {}
for commit, label in CONTROLS:
    rec = v[commit]
    sides = {"A": rec["A"]["findings"], "B": rec["B"]["findings"]}
    k0_side = "A" if a_is[commit] == "K0" else "B"
    k1_side = "B" if k0_side == "A" else "A"
    c0, c1 = counts(sides[k0_side]), counts(sides[k1_side])
    by_set[commit] = {"K0": sides[k0_side], "K1": sides[k1_side]}
    for k in CLASSES:
        tot["K0"][k] += c0[k]
        tot["K1"][k] += c1[k]
    print(f"| {label} {commit} | {c0['REAL']} / {c0['PLAUSIBLE']} / {c0['FALSE']} | {c1['REAL']} / {c1['PLAUSIBLE']} / {c1['FALSE']} |")
print(f"| **Total** | **{tot['K0']['REAL']} / {tot['K0']['PLAUSIBLE']} / {tot['K0']['FALSE']}** | **{tot['K1']['REAL']} / {tot['K1']['PLAUSIBLE']} / {tot['K1']['FALSE']}** |")
print()
f1, r0, r1 = tot["K1"]["FALSE"], tot["K0"]["REAL"], tot["K1"]["REAL"]
print(f"K1 FALSE total {f1} ({f1 / 4:.2f} per control): bar is at most 4 ->",
      "CLEARS THE BAR" if f1 <= 4 else "DOES NOT CLEAR THE BAR")
print(f"REAL: K0 {r0}, K1 {r1} ->", "K1 REAL more than 2 below K0: reported as a cost" if r1 < r0 - 2 else "within the stated margin")
print()

# K0 re-grade against the parent study's verdicts on the same reports
print("K0 re-grade vs parent verdicts (same finding index):")
agree = total = 0
for commit, label in CONTROLS:
    p = pv[commit]
    p_side = "A" if parent_a_is[commit] == "K" else "B"
    parent = {e["index"]: e["class"] for e in p[p_side]["other_findings"]}
    now = {e["index"]: e["class"] for e in by_set[commit]["K0"]}
    assert set(parent) == set(now), (commit, sorted(parent), sorted(now))
    diffs = [(i, parent[i], now[i]) for i in sorted(now) if parent[i] != now[i]]
    agree += len(now) - len(diffs)
    total += len(now)
    print(f"  {label} {commit}: {len(now) - len(diffs)}/{len(now)} agree" + (f"; changed: {diffs}" if diffs else ""))
pf = sum(1 for commit, _ in CONTROLS for e in pv[commit]["A" if parent_a_is[commit] == "K" else "B"]["other_findings"] if e["class"] == "FALSE")
print(f"  agreement {agree}/{total}; K0 FALSE total: parent grading {pf}, this grading {tot['K0']['FALSE']}")
