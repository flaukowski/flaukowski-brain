"""Publication guard: nothing that posts (ledger records, mail, DMs) may carry held-out text.

leak_guard.py guards TRAINING files against whole probe items (8-word shingles, half an excerpt).
That is the wrong threshold for publication. On 2026-10-06 a ledger record leaked a handful of
fragments: a threshold quoted from a model's answer, a 4-word rule phrase, and one domain word.
None of them is half an excerpt. This guard flags any of:

  - token: a distinctive held-out token, meaning one that contains a digit and has 3+ characters,
           or is 5+ letters, and that does NOT already appear in the public corpus;
  - ngram: a 4-word sequence from held-out text that the public corpus does not contain.

The public corpus is every ledger record (fetched with the ledger key) except those named in
EXCLUDE, the record that leaked, plus the training rows (runs/e4-train.jsonl) as ordinary vocabulary. Subtracting it keeps "not in the record" and "2026" from firing,
at a cost the audit makes visible: a held-out token that was ALREADY made public is no longer
flagged. `audit` lists those, by hash and item id only.

LIMIT: it matches words, not meaning. A held-out item's domain word that is already public in
another context (it happened: a word public since an unrelated E2 record) passes, even when the new
text ties it to the item. Describe failures by item id and pattern, never by content, and treat a
clean check as necessary, not sufficient.

Held-out sources: probes v1 and v2, the E4 slice (harness copy and Kannaka's original), the E5
variants and harness file, and the voice holdout. The fingerprint stores sha256 only, so it can
sit beside anything.

    python pub_guard.py build --out pubguard.fp.json        # needs the held-out files + ledger key
    python pub_guard.py check --fp pubguard.fp.json FILE     # any text or JSON file; exit 1 on a hit
    python pub_guard.py audit --fp pubguard.fp.json          # which held-out items are already public
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

HELD_OUT = ["probe-v1-items.json", "probe-v2-items.json", "probe-slice-e4-items.json",
            "runs/e4-heldout-slice-v1.jsonl", "e5/e5-variants-v1.jsonl", "e5/probe-e5-items.json",
            "voice/kannaka-voice-holdout-v2.jsonl"]
EXCLUDE = {"01M490JTB7QA2SP5W0GTPD97XY"}   # E5 result: leaked held-out fragments (corrected by 01M490KGR6...)
SKIP_FIELDS = {"id", "kind", "gold", "version", "base", "present", "pattern", "source", "_set"}
N = 4
BASE = "https://research.spacechild.love"
COMMON = ["runs/e4-train.jsonl", "runs/e3-chunks.jsonl"]   # training rows + the public repo docs they read


def words(text):
    """Tokens, plus their parts split on . - : / so `x.exec` also yields `x` (commas inside numbers stay)."""
    out = []
    for t in re.findall(r"[\w][\w.,:%/-]*[\w%]|\w", text.lower()):
        out.append(t)
        parts = [p for p in re.split(r"[.:/-]", t) if p]
        if len(parts) > 1:
            out.extend(parts)
    return out


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def distinctive(w):
    return (any(c.isdigit() for c in w) and len(w) >= 3) or (w.isalpha() and len(w) >= 5)


def strings(obj, skip=()):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k not in skip:
                yield from strings(v, skip)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v, skip)


def held_out_units():
    """(source:item id, text) for every held-out item."""
    for p in HELD_OUT:
        raw = open(p, encoding="utf-8").read()
        rows = ([json.loads(l) for l in raw.splitlines() if l.strip()] if p.endswith(".jsonl")
                else (lambda d: d["items"] if isinstance(d, dict) else d)(json.loads(raw)))
        for r in rows:
            yield f"{p}:{r.get('id')}", "\n".join(strings(r, SKIP_FIELDS))


def grams(ws):
    return {" ".join(ws[i:i + N]) for i in range(len(ws) - N + 1)}


def public_corpus():
    key = open(os.path.expanduser("~/.spacechild_ledger_key"), encoding="utf-8").read().strip()
    r = subprocess.run(["curl", "-s", "-A", "curl/8", "--max-time", "90", "-H", "Authorization: Bearer " + key,
                        BASE + "/api/ledger/records?limit=1000"], capture_output=True)
    recs = json.loads(r.stdout.decode("utf-8", "replace"))
    texts = [r.get("title", "") + "\n" + r.get("body", "") for r in recs if r["id"] not in EXCLUDE]
    return recs, texts


def cmd_build(a):
    recs, texts = public_corpus()
    ledger_tok = {w for t in texts for w in words(t)}
    # Generic vocabulary: the training rows are written away from the probes and leak-checked
    # (leak_guard fp2, 0 hits), so a WORD they use is ordinary. A NUMBER they use is coincidence,
    # not clearance: a held-out threshold stays flagged unless it is already on the ledger.
    for p in COMMON:
        texts += [chr(10).join(strings(json.loads(l))) for l in open(p, encoding="utf-8") if l.strip()]
    pub_tok, pub_gram = set(), set()
    for t in texts:
        ws = words(t)
        pub_tok.update(ws)
        pub_gram.update(grams(ws))
    tok, gram, already = {}, {}, {}
    for uid, text in held_out_units():
        ws = words(text)
        for w in ws:
            if distinctive(w):
                public = w in ledger_tok if any(c.isdigit() for c in w) else w in pub_tok
                (already if public else tok).setdefault(h(w), set()).add(uid)
        for g in grams(ws):
            if g not in pub_gram:
                gram.setdefault(h(g), set()).add(uid)
    out = {"n": N, "public_records": len(texts), "exclude": sorted(EXCLUDE),
           "token": {k: sorted(v) for k, v in tok.items()}, "ngram": {k: sorted(v) for k, v in gram.items()},
           "already_public": {k: sorted(v) for k, v in already.items()}}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f)
    print(f"pub_guard: {len(tok)} distinctive tokens, {len(gram)} 4-grams held out; "
          f"{len(already)} distinctive held-out tokens already public; corpus {len(texts)} records -> {a.out}")
    return 0


def check_text(text, fp):
    ws = words(text)
    """[(severity, kind, string, item ids)]. BLOCK: a held-out number or 4-gram. WARN: a single held-out
    word; ordinary words collide with the holdout's vocabulary too often to block on."""
    hits = []
    for w in set(ws):
        if h(w) in fp["token"]:
            sev = "BLOCK" if any(c.isdigit() for c in w) else "WARN"
            hits.append((sev, "token", w, fp["token"][h(w)]))
    for g in grams(ws):
        if h(g) in fp["ngram"]:
            hits.append(("BLOCK", "ngram", g, fp["ngram"][h(g)]))
    return hits


def accept(hits, accepted):
    """A hit whose string the operator has accepted as public, with a reason, is reported as ACCEPT and does not
    block. The acceptance is explicit per token and printed with the reason, so it is on the record; a token
    that is not in the list still blocks, and an accepted string that never hits is reported as unused."""
    out, used = [], set()
    for sev, kind, s, uids in hits:
        if s in accepted:
            used.add(s)
            out.append(("ACCEPT", kind, s, [accepted[s]]))
        else:
            out.append((sev, kind, s, uids))
    for s in sorted(set(accepted) - used):
        print(f"pub_guard: --accept {s!r} did not match any hit (stale acceptance?)")
    return out


def report(hits, label):
    for sev, kind, s, uids in sorted(hits):
        print(f"{sev} held-out {kind}: {s!r} ({'reason: ' if sev == 'ACCEPT' else 'from '}"
              f"{', '.join(uids[:3])}{' ...' if len(uids) > 3 else ''})")
    blocks = sum(1 for x in hits if x[0] == "BLOCK")
    accepted = sum(1 for x in hits if x[0] == "ACCEPT")
    print(f"pub_guard: {blocks} block(s), {len(hits) - blocks - accepted} warning(s), {accepted} accepted in {label}")
    return blocks


def parse_accepts(items):
    acc = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"pub_guard: --accept needs TOKEN=reason, got {it!r}")
        tok, reason = it.split("=", 1)
        if not reason.strip():
            raise SystemExit(f"pub_guard: --accept {tok!r} needs a reason")
        acc[tok] = reason.strip()
    return acc


def cmd_check(a):
    fp = json.load(open(a.fp, encoding="utf-8"))
    raw = open(a.file, encoding="utf-8").read()
    try:
        text = "\n".join(strings(json.loads(raw)))
    except ValueError:
        text = raw
    return 1 if report(accept(check_text(text, fp), parse_accepts(a.accept)), a.file) else 0


def cmd_audit(a):
    fp = json.load(open(a.fp, encoding="utf-8"))
    by_item = {}
    for _, uids in fp["already_public"].items():
        for u in uids:
            by_item[u] = by_item.get(u, 0) + 1
    for u, n in sorted(by_item.items(), key=lambda x: -x[1]):
        print(f"{n:3d} distinctive token(s) of {u} also appear in the public corpus")
    return 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build"); b.add_argument("--out", required=True)
    c = sp.add_parser("check"); c.add_argument("--fp", required=True); c.add_argument("file")
    c.add_argument("--accept", action="append", metavar="TOKEN=reason",
                   help="a held-out token confirmed to be the author's own public text; reported, never blocks")
    u = sp.add_parser("audit"); u.add_argument("--fp", required=True)
    a = ap.parse_args(argv)
    return {"build": cmd_build, "check": cmd_check, "audit": cmd_audit}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
