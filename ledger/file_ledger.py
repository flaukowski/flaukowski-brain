"""File records to the SpaceChild research ledger as Agent-Flaukowski (key in ~/.spacechild_ledger_key).

    python file_ledger.py drafts.json [--only CLIENTREF ...] [--dry-run]

drafts.json = {"campaign": {...} | null, "records": [{...}, ...]}. Each record needs a clientRef, so a
retry returns the original record (HTTP 200, created:false) instead of filing twice. A record whose
"after" names an earlier clientRef gets that record's ledger id substituted into "correctsId",
"amendsId" or "aboutId" fields written as "@clientRef". Backfilled records carry "_backfill": true.
Results are appended to filed.jsonl beside the drafts. The secret is read from the key file and never
printed.

Every record is checked by pub_guard before it is sent, dry runs included. A held-out number or
4-gram refuses the whole run. The guard fails closed, so a missing fingerprint also refuses.
`--accept "string"` passes one hit that has been confirmed already public (e.g. a solver log line
that a probe excerpt was drawn from); say why in the record.
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pub_guard  # noqa: E402

BASE = "https://research.spacechild.love"
FP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pubguard.fp.json")


def key():
    return open(os.path.expanduser("~/.spacechild_ledger_key"), encoding="utf-8").read().strip()


def post(path, body, backfill=False):
    hdr = ["-H", "Authorization: Bearer " + key(), "-H", "Content-Type: application/json"]
    if backfill:
        hdr += ["-H", "x-ledger-backfill: 1"]
    r = subprocess.run(["curl", "-s", "-A", "curl/8", "--max-time", "90", "-X", "POST", BASE + path, *hdr,
                        "--data-binary", "@-"], input=json.dumps(body), capture_output=True, text=True,
                       encoding="utf-8")
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"error": "non_json", "message": r.stdout[:300] or r.stderr[:300]}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("drafts")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--accept", action="append", default=[], help="a hit string confirmed already public")
    a = ap.parse_args()
    d = json.load(open(a.drafts, encoding="utf-8"))
    if not os.path.exists(FP):
        sys.exit(f"file_ledger: no publication fingerprint at {FP}; run pub_guard.py build first (fails closed)")
    fp = json.load(open(FP, encoding="utf-8"))
    blocked = 0
    for rec in d["records"]:
        if a.only and rec["clientRef"] not in a.only:
            continue
        hits = [x for x in pub_guard.check_text(chr(10).join(pub_guard.strings(rec)), fp) if x[2] not in a.accept]
        blocked += pub_guard.report(hits, rec["clientRef"])
    if blocked:
        sys.exit("file_ledger: refused, held-out text in a draft (nothing was sent)")
    log_path = os.path.join(os.path.dirname(os.path.abspath(a.drafts)), "filed.jsonl")
    ids = {}
    if os.path.exists(log_path):
        for line in open(log_path, encoding="utf-8"):
            e = json.loads(line)
            if e.get("id"):
                ids[e["clientRef"]] = e["id"]
    if d.get("campaign") and not a.only:
        c = d["campaign"]
        if a.dry_run:
            print("DRY campaign", c["id"])
        else:
            res = post("/api/ledger/campaigns", c)
            print("campaign", c["id"], "->", json.dumps(res)[:200])
    for rec in d["records"]:
        ref = rec["clientRef"]
        if a.only and ref not in a.only:
            continue
        body = {k: v for k, v in rec.items() if not k.startswith("_")}
        for f in ("correctsId", "amendsId", "aboutId", "reviewsId"):
            if isinstance(body.get(f), str) and body[f].startswith("@"):
                body[f] = ids[body[f][1:]]
        if a.dry_run:
            print("DRY", ref, body["kind"], len(body.get("body", "")), "chars,", len(body.get("evidence", [])), "evidence")
            continue
        res = post("/api/ledger/records", body, backfill=rec.get("_backfill", False))
        rid = (res.get("record") or res).get("id") if isinstance(res, dict) else None
        print(ref, "->", rid or json.dumps(res)[:300])
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"clientRef": ref, "id": rid, "response": res if not rid else None}) + "\n")
        if rid:
            ids[ref] = rid
        else:
            sys.exit("stopping at the first refusal")
        time.sleep(1)


if __name__ == "__main__":
    main()
