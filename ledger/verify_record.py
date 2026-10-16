"""Check that a ledger record's evidence and links hold, without trusting its author or the server's word.

    python -I ledger/verify_record.py RECORD_ID [RECORD_ID ...]
    python -I ledger/verify_record.py --campaign CAMPAIGN_ID

A record's standing ("measured", "unverified") is set by whoever files it, so on its own it is a
self-report. This script is the machine gate ahead of that standing (the idea is borrowed from KungFu's
"ready is a request, not a verdict"): it checks what a machine can check and says what is left for a
peer.

Per record:
  evidence   every evidence URL is fetched and its sha256 recomputed; a URL pinned to a full commit sha
             is immutable, anything else (a branch, a release asset) is flagged MUTABLE
  links      every id the record points at (correctsId, amendsId, aboutId, reviewsId) and every record id
             named in its title or body exists on the ledger
  order      a result has a preregistration in its campaign, filed before it; an amendment is filed
             after the record it amends
  guard      the title and body are run through pub_guard; a hit is a warning for a person to judge
             (pub_guard leaves coincidences to a person, and older records predate its fingerprint)
  peer       how many reviews by someone other than the author it has; zero means the standing still
             rests on the author

Tiers, in order: CLAIMED (filed; also any record with no evidence, since nothing could be checked),
MACHINE-CHECKED (it has evidence, and evidence, links and order all pass),
PEER-REVIEWED (also at least one review by another author whose verdict is not a rejection).

Exit 0 when no check fails (a record with no evidence stays CLAIMED but is not a failure), 1 when any
check fails, 2 when the script itself could not
run a check (network, bad id). An error is never reported as a failure, nor a failure as an error.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pub_guard  # noqa: E402

BASE = "https://research.spacechild.love"
FP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pubguard.fp.json")
UA = {"User-Agent": "curl/8"}
MAX_BYTES = 512 * 1024 * 1024
# ledger ids are 26-character Crockford base32, time-sortable; every one seen so far starts 01M
ID_RE = re.compile(r"\b01[0-9A-HJKMNP-TV-Z]{24}\b")
LINK_FIELDS = ("correctsId", "amendsId", "aboutId", "reviewsId")
REJECTING = {"rejected", "broken", "does_not_hold", "fails", "refuted"}


class CheckError(Exception):
    """The check could not be run (as opposed to: it ran and failed)."""


def get_json(path):
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + path, headers=UA), timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise CheckError(f"{path}: HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise CheckError(f"{path}: {e}") from e


def fetch_sha256(url):
    h, n = hashlib.sha256(), 0
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
            while chunk := r.read(1 << 20):
                n += len(chunk)
                if n > MAX_BYTES:
                    raise CheckError(f"{url}: larger than {MAX_BYTES} bytes")
                h.update(chunk)
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError) as e:
        raise CheckError(f"{url}: {e}") from e
    return h.hexdigest(), n


def fetch_crlf_sha256(url):
    """sha256 of the file with LF line endings turned into CRLF: what a Windows working copy hashes to."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
            data = r.read(MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError):
        return None
    if len(data) > MAX_BYTES:
        return None
    return hashlib.sha256(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")).hexdigest()


def pinned(url):
    """True when the URL names content by a full commit sha, so it cannot change under the same URL."""
    return bool(re.search(r"/[0-9a-f]{40}/", url) or re.search(r"/(blob|raw|tree)/[0-9a-f]{40}/", url))


def check_record(rid, cache, fp):
    """Return (lines, failed) for one record. Raises CheckError when a check cannot be run."""
    d = cache.get(rid) or get_json(f"/api/ledger/records/{rid}")
    if d is None:
        raise CheckError(f"record {rid} not found")
    cache[rid] = d
    r = d["record"]
    out, failed = [], False

    def say(status, what):
        nonlocal failed
        failed |= status == "FAIL"
        out.append(f"  {status:<7} {what}")

    out.append(f"{rid}  {r['kind']} / {r['standing']}  by {r['authorUsername']}  ({r['campaignId']})")

    own = r.get("evidence") or []
    # evidence attached later, in a note about this record, counts only when its sha256 was already
    # cited in this record's own text: that hash was committed at filing, before the note existed
    cited = set(re.findall(r"\b[0-9a-f]{64}\b", ((r.get("title") or "") + " " + (r.get("body") or "")).lower()))
    late = [(n["id"], e) for n in d.get("notes") or [] for e in n.get("evidence") or []]
    backed = [e for _, e in late if (e.get("sha256") or "").lower() in cited]
    for nid, e in late:
        if (e.get("sha256") or "").lower() in cited:
            continue
        if fetch_crlf_sha256(e["url"]) in cited:
            # the record cited a Windows (CRLF) copy; the same bytes with CRLF endings match it exactly
            backed.append(e)
            say("PASS", f"evidence '{e.get('label') or e['url']}' (note {nid}): with CRLF line endings it "
                        "matches a sha256 cited at filing, so it is the same file")
        else:
            say("WARN", f"evidence '{e.get('label') or e['url']}' (note {nid}): its sha256 was not cited at "
                        "filing, so it does not back this record")
    ev = own + backed
    if not ev:
        say("WARN", "evidence: none attached")
    for e in ev:
        if e not in own:
            out.append(f"  {'':<7} (backfilled, its sha256 cited at filing)")
        got, size = fetch_sha256(e["url"])
        label = e.get("label") or e["url"]
        if got is None:
            say("FAIL", f"evidence '{label}': not fetchable ({size})")
        elif not e.get("sha256"):
            say("WARN", f"evidence '{label}': no sha256 recorded, fetched {size} bytes, sha256 {got[:16]}...")
        elif got != e["sha256"].lower():
            say("FAIL", f"evidence '{label}': sha256 {got[:16]}... != recorded {e['sha256'][:16]}...")
        else:
            say("PASS", f"evidence '{label}': sha256 matches ({size} bytes)"
                        + ("" if pinned(e["url"]) else "; URL is MUTABLE (not pinned to a commit)"))

    linked = {r[f] for f in LINK_FIELDS if r.get(f)}
    named = set(ID_RE.findall((r.get("title") or "") + " " + (r.get("body") or ""))) - {rid}
    for lid in sorted(linked | named):
        other = cache.get(lid) or get_json(f"/api/ledger/records/{lid}")
        if other is None:
            say("FAIL", f"link {lid}: no such record ({'field' if lid in linked else 'named in text'})")
            continue
        cache[lid] = other
        o = other["record"]
        say("PASS", f"link {lid}: exists ({o['kind']}, {o['campaignId']})")
        if r.get("amendsId") == lid and o["createdAt"] >= r["createdAt"]:
            say("FAIL", f"order: amends {lid}, which was filed after it")

    if r["kind"] == "result":
        camp = get_json(f"/api/ledger/campaigns/{r['campaignId']}")
        if camp is None:
            raise CheckError(f"campaign {r['campaignId']} not found")
        pre = [x for x in camp.get("records", []) if x.get("kind") == "preregistration"]
        dated = [x for x in pre if x.get("createdAt")]
        early = [x for x in dated if x["createdAt"] < r["createdAt"]]
        if not pre:
            say("FAIL", "order: result with no preregistration in its campaign")
        elif not dated:
            say("WARN", "order: preregistration has no filing time, so the order cannot be checked")
        elif not early:
            say("FAIL", "order: the campaign's preregistration was filed after this result")
        else:
            say("PASS", f"order: preregistration {early[0]['id']} filed before this result")

    text = (r.get("title") or "") + "\n" + (r.get("body") or "")
    blocks = [h for h in pub_guard.check_text(text, fp) if h[0] == "BLOCK"]
    if blocks:
        # pub_guard leaves coincidences to a person to accept, and older records predate the current
        # fingerprint, so a hit on a filed record is a prompt to look, not a failed check
        say("WARN", f"guard: {len(blocks)} held-out hit(s) in title/body; a person should judge them")
    else:
        say("PASS", "guard: no held-out hit in title/body")

    peers = [v for v in d.get("reviews") or [] if v.get("authorUsername") != r["authorUsername"]]
    holding = [v for v in peers if str(v.get("verdict") or "").lower() not in REJECTING]
    if r.get("correctedBy") or r.get("brokenBy"):
        say("WARN", f"corrected by {r.get('correctedBy')} / broken by {r.get('brokenBy')}")
    say("INFO", f"peer: {len(peers)} review(s) by another author"
                + (f", {len(holding)} not rejecting" if peers else "; the standing rests on the author"))

    # with no evidence there is nothing for the machine to have checked, so nothing has been raised
    tier = "CLAIMED" if failed or not ev else ("PEER-REVIEWED" if holding else "MACHINE-CHECKED")
    out.append(f"  => {tier}")
    return out, failed


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--campaign")
    a = ap.parse_args()
    if not os.path.exists(FP):
        print(f"verify_record: no fingerprint at {FP}", file=sys.stderr)
        return 2
    fp = json.load(open(FP, encoding="utf-8"))
    try:
        ids = list(a.ids)
        if a.campaign:
            camp = get_json(f"/api/ledger/campaigns/{a.campaign}")
            if camp is None:
                raise CheckError(f"campaign {a.campaign} not found")
            ids += [x["id"] for x in camp.get("records", [])][::-1]
        if not ids:
            ap.error("give record ids or --campaign")
        cache, any_failed = {}, False
        for rid in ids:
            lines, failed = check_record(rid, cache, fp)
            any_failed |= failed
            print("\n".join(lines))
    except CheckError as e:
        print(f"verify_record: could not run a check: {e}", file=sys.stderr)
        return 2
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
