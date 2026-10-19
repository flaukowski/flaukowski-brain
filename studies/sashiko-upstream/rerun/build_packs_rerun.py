"""Build the blind A/B packs for sux-controls-rerun (pre-registration 01M5A5K2C9SRMCE6VFGXVK1Y4F).

    python -I -X utf8 build_packs_rerun.py <k0-dir> <k1-dir> <key.json> <out-dir>

K0 = the parent study's arm-K reports (<commit>-K.json), K1 = the new reports (<commit>*.json, not
an *.attempt1.* file). Same method as the parent study's build_packs.py: each pack holds only the final
report of each set (summary, inline review, findings, dismissed concerns marked as not counting);
prompts, history, stages and review_map are left out. Project-naming strings become [project]; the
leading "tag:" label on each finding's problem line is removed in both sets. Before any pack is written,
the two sets are compared for format tells (field sets, build or version strings, label conventions);
a tell that is not already scrubbed stops the build. Every replacement is counted in scrub-log.json.
"""
import glob
import json
import os
import re
import sys

k0dir, k1dir, keyf, out = sys.argv[1:5]
key = json.load(open(keyf, encoding="utf-8"))["a_is"]
CONTROLS = {"5a5b667": "X1", "505a024": "X2", "0035364": "X3", "248f7cb": "X4"}
SCRUB = [r"--project\s+kannaka", r"Kannaka Labs", r"[Kk]annaka", r"KANNAKA"]
PREFIX = re.compile(r"^\s*[\w.-]+:\s*")
TELLS = [r"731bdf8", r"380d01c", r"tests-findings-bar", r"sashiko-kannaka", r"\b0\.5\.[0-9]\b", r"\bkm-"]
os.makedirs(out, exist_ok=True)
log = {}


def k1_file(commit):
    fs = [f for f in glob.glob(os.path.join(k1dir, commit + "*.json")) if "attempt1" not in os.path.basename(f)]
    assert len(fs) == 1, (commit, fs)
    return fs[0]


def scrub(s, counts):
    for p in SCRUB:
        s, n = re.subn(p, "[project]", s)
        counts[p] = counts.get(p, 0) + n
    return s


def report(path):
    d = json.load(open(path, encoding="utf-8"))
    r = d["review"]
    c = {}
    findings = []
    for x in r["findings"]:
        prob = x["problem"]
        m = PREFIX.match(prob)
        if m:
            c["finding label removed"] = c.get("finding label removed", 0) + 1
            prob = prob[m.end():]
        findings.append({
            "problem": scrub(prob, c), "severity": x["severity"], "type": scrub(x["type"], c),
            "preexisting": x.get("preexisting"),
            "explanation": scrub(x.get("severity_explanation", ""), c),
            "locations": [{k: scrub(str(v), c) for k, v in loc.items()} for loc in x.get("locations", [])],
        })
    dismissed = [{"description": scrub(x.get("description", ""), c), "reasoning": scrub(x.get("reasoning", ""), c),
                  "locations": [{k: scrub(str(v), c) for k, v in loc.items()} for loc in x.get("locations", [])]}
                 for x in r["dismissed_concerns"]]
    rep = {"summary": scrub(r["summary"], c), "inline_review": scrub(d["inline_review"], c),
           "findings": findings, "dismissed_concerns_DO_NOT_COUNT": dismissed}
    return d, rep, c


def shape(d):
    """The field sets the pack keeps, so a new or missing field would show which set a report is from."""
    r = d["review"]
    f = sorted({k for x in r["findings"] for k in x}) if r["findings"] else []
    dc = sorted({k for x in r["dismissed_concerns"] for k in x}) if r["dismissed_concerns"] else []
    return {"top": sorted(k for k in d if k in ("inline_review", "review")), "review": sorted(k for k in r if k in ("summary", "findings", "dismissed_concerns")),
            "finding": f, "dismissed": dc}


# 1. format-tell check over the kept fields of all eight reports, before any pack is written
shapes = {"K0": {}, "K1": {}}
tells = []
for commit in CONTROLS:
    for name, path in (("K0", os.path.join(k0dir, f"{commit}-K.json")), ("K1", k1_file(commit))):
        d, rep, _ = report(path)
        shapes[name][commit] = shape(d)
        s = json.dumps(rep, ensure_ascii=False)
        for t in TELLS:
            for m in re.findall(t, s):
                tells.append((name, commit, t, m))
ks0 = {json.dumps(v, sort_keys=True) for v in shapes["K0"].values()}
ks1 = {json.dumps(v, sort_keys=True) for v in shapes["K1"].values()}
if ks0 != ks1:
    print("FIELD SETS DIFFER between K0 and K1:", ks0 ^ ks1)
    sys.exit(2)
if tells:
    print("TELLS LEFT AFTER SCRUB:", tells[:10])
    sys.exit(2)
print("format check: kept-field sets identical across all eight reports; no build, version or label tell left")

# 2. packs
for commit, label in sorted(CONTROLS.items(), key=lambda kv: kv[1]):
    a_set = key[commit]
    b_set = "K1" if a_set == "K0" else "K0"
    paths = {"K0": os.path.join(k0dir, f"{commit}-K.json"), "K1": k1_file(commit)}
    _, ra, ca = report(paths[a_set])
    _, rb, cb = report(paths[b_set])
    pack = {"commit": commit, "label": label, "A": ra, "B": rb}
    s = json.dumps(pack, ensure_ascii=False, indent=1)
    left = re.findall(r"(?i)kannaka|--project\s+kannaka|\bkm-", s)
    assert not left, (commit, left[:5])
    with open(os.path.join(out, f"pack-{label}-{commit}.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    log[f"{label} {commit}"] = {"A": {k: v for k, v in ca.items() if v}, "B": {k: v for k, v in cb.items() if v}}
    print(label, commit, "A findings", len(ra["findings"]), "B findings", len(rb["findings"]))

json.dump(log, open(os.path.join(os.path.dirname(os.path.abspath(out)), "scrub-log.json"), "w", encoding="utf-8"), indent=1)
print("scrub log written beside the packs dir, not in it")
