"""Build the blind A/B/C packs for sashiko-noise-floor (pre-registration 01M5D5V8Y4WR8N2FJZ3XNK8BW7).

    python -I -X utf8 build_packs_noise.py <r1-dir> <r23-dir> <key.json> <out-dir>

R1 = the sux-controls-rerun reports (<commit>-K.json); R2 and R3 = the noise-floor reports, found in
<r23-dir> by commit and run name (a file whose name holds the commit and R2 or R3, not an attempt file).
Same report extraction and scrub as rerun/build_packs_rerun.py, reused from there unchanged. All three
runs come from one build, so a format tell would be a run-level artifact (a timestamp, a run id, a field
one run has and another lacks); the field sets are compared and a list of run-level strings is searched
before any pack is written, and either stops the build.
"""
import glob
import importlib.util
import json
import os
import re
import sys

r1dir, r23dir, keyf, out = sys.argv[1:5]
key = json.load(open(keyf, encoding="utf-8"))["labels"]
CONTROLS = {"5a5b667": "X1", "505a024": "X2", "0035364": "X3", "248f7cb": "X4"}
TELLS = [r"\bR[123]\b", r"random\.Random", r"noise.floor", r"controls.rerun", r"2026-10-(19|20)"]

# reuse report() and shape() from the rerun builder without running its module body
here = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(here, "..", "rerun", "build_packs_rerun.py"), encoding="utf-8").read()
src = src[:src.index("# 1. format-tell check")]
src = src.replace("k0dir, k1dir, keyf, out = sys.argv[1:5]", "").replace('key = json.load(open(keyf, encoding="utf-8"))["a_is"]', "")
src = src.replace("os.makedirs(out, exist_ok=True)", "")
ns = {}
exec(compile(src, "build_packs_rerun.py(head)", "exec"), ns)
report, shape = ns["report"], ns["shape"]


def path_for(commit, run):
    if run == "R1":
        return os.path.join(r1dir, f"{commit}-K.json")
    fs = [f for f in glob.glob(os.path.join(r23dir, "**", f"*{commit}*.json"), recursive=True)
          if run in os.path.basename(f) and "attempt" not in os.path.basename(f) and "manifest" not in f.lower()]
    assert len(fs) == 1, (commit, run, fs)
    return fs[0]


# 1. format-tell check over the kept fields of all twelve reports
shapes, tells = {}, []
for commit in CONTROLS:
    for run in ("R1", "R2", "R3"):
        d, rep, _ = report(path_for(commit, run))
        shapes.setdefault(run, {})[commit] = shape(d)
        s = json.dumps(rep, ensure_ascii=False)
        tells += [(run, commit, t, m) for t in TELLS for m in re.findall(t, s)]


def pooled(run):
    u = {}
    for v in shapes[run].values():
        for part, names in v.items():
            u.setdefault(part, set()).update(names)
    return {k: sorted(s) for k, s in u.items()}


p = {r: pooled(r) for r in shapes}
if not (p["R1"] == p["R2"] == p["R3"]):
    print("FIELD SETS DIFFER between runs:", p)
    sys.exit(2)
if tells:
    print("RUN-LEVEL TELLS:", len(tells), "(strings not printed with their run)")
    sys.exit(2)
print("format check: kept-field sets identical across all twelve reports; no run-level tell found")

# 2. packs
os.makedirs(out, exist_ok=True)
log = {}
for commit, label in sorted(CONTROLS.items(), key=lambda kv: kv[1]):
    pack = {"commit": commit, "label": label}
    log[f"{label} {commit}"] = {}
    for slot in "ABC":
        _, rep, c = report(path_for(commit, key[commit][slot]))
        pack[slot] = rep
        log[f"{label} {commit}"][slot] = {k: v for k, v in c.items() if v}
    s = json.dumps(pack, ensure_ascii=False, indent=1)
    left = re.findall(r"(?i)kannaka|\bkm-", s)
    assert not left, (commit, left[:5])
    with open(os.path.join(out, f"pack-{label}-{commit}.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    print(label, commit, "findings", *(len(pack[x]["findings"]) for x in "ABC"))

json.dump(log, open(os.path.join(os.path.dirname(os.path.abspath(out)), "scrub-log.json"), "w", encoding="utf-8"), indent=1)
print("scrub log written beside the packs dir, not in it")
