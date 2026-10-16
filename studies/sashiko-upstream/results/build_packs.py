"""Build the blind A/B packs for sashiko-upstream-xreview (amendment 1).

    python -I -X utf8 build_packs.py <reports-dir> <key.json> <out-dir>

Each pack holds only the final report of each arm: summary, inline review, findings and dismissed
concerns (marked as not counting). Prompts, history and review_map are left out because they carry
each arm's project prompt. Project-naming strings are replaced with [project], per amendment 1; the
leading "tag:" label on each finding's problem line is removed in both arms, because the two arms
use different label conventions. Every replacement is counted in scrub-log.json.
"""
import json, os, re, sys

src, keyf, out = sys.argv[1:4]
key = json.load(open(keyf, encoding="utf-8"))["a_is"]
ITEMS = {"ec1258f": "U1", "ff3ee61": "U2", "7ff827d": "U3", "9d6f5e9": "U4", "81f64ea": "U5",
         "d67c8bd": "U6", "39bf2ac": "U7", "313bdbe": "U8",
         "5a5b667": "X1", "505a024": "X2", "0035364": "X3", "248f7cb": "X4"}
# amendment 1's list, longest first so "Kannaka Labs" is one replacement
# "--project sashiko" is left alone: it occurs only in X3 (0035364), quoted from that commit's own
# GEMINI.md by both arms, so it is the reviewed code's text, not a label of the arm
SCRUB = [r"--project\s+kannaka", r"Kannaka Labs", r"[Kk]annaka", r"KANNAKA"]
PREFIX = re.compile(r"^\s*[\w.-]+:\s*")
os.makedirs(out, exist_ok=True)
log = {}


def scrub(s, counts):
    for p in SCRUB:
        s, n = re.subn(p, "[project]", s)
        counts[p] = counts.get(p, 0) + n
    return s


def report(commit, arm):
    d = json.load(open(os.path.join(src, f"{commit}-{arm}.json"), encoding="utf-8"))
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
    return rep, c


for commit, label in sorted(ITEMS.items(), key=lambda kv: kv[1]):
    a_arm = key[commit]
    b_arm = "S" if a_arm == "K" else "K"
    ra, ca = report(commit, a_arm)
    rb, cb = report(commit, b_arm)
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
