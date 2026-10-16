"""Each check in verify_record must fail when its condition is broken, not only pass when it holds.

    python -I -m pytest ledger/test_verify_record.py -q
"""
import hashlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_record as vr  # noqa: E402

BODY = b"the evidence file"
SHA = hashlib.sha256(BODY).hexdigest()
PIN = "https://raw.githubusercontent.com/o/r/" + "a" * 40 + "/f.md"
PRE, RES, AMD = "01M4ZZSAVA8RQ3QF642TZV6217", "01M52ETE0ASWDFHBE3615RWBMB", "01M505ER0A9VF9JG9HNKRGQN9T"
FP = {"token": {}, "ngram": {}}


def rec(rid, kind, created, **kw):
    r = {"id": rid, "kind": kind, "standing": "measured", "authorUsername": "A", "campaignId": "c",
         "title": "t", "body": "", "evidence": [{"url": PIN, "sha256": SHA, "label": "e"}],
         "createdAt": created, "correctedBy": [], "brokenBy": []}
    r.update(kw)
    return r


@pytest.fixture
def ledger(monkeypatch, request):
    db = {PRE: rec(PRE, "preregistration", "2026-10-15T10:00:00Z"),
          RES: rec(RES, "result", "2026-10-16T10:00:00Z", body=f"pre-registration {PRE}")}
    reviews = {}
    notes = {}

    def get_json(path):
        if path.startswith("/api/ledger/records/"):
            rid = path.rsplit("/", 1)[1]
            return ({"record": db[rid], "reviews": reviews.get(rid, []), "notes": notes.get(rid, [])}
                    if rid in db else None)
        if path.startswith("/api/ledger/campaigns/"):
            return {"records": list(db.values())}
        raise AssertionError(path)

    monkeypatch.setattr(vr, "get_json", get_json)
    monkeypatch.setattr(vr, "fetch_sha256", lambda url: (SHA, len(BODY)) if url == PIN else (None, "HTTP 404"))
    request.node.notes = notes
    return db, reviews


def run(rid):
    lines, failed = vr.check_record(rid, {}, FP)
    return "\n".join(lines), failed


def test_clean_result_is_machine_checked(ledger):
    text, failed = run(RES)
    assert not failed and "=> MACHINE-CHECKED" in text and "rests on the author" in text


def test_wrong_sha_fails(ledger):
    db, _ = ledger
    db[RES]["evidence"][0]["sha256"] = "0" * 64
    text, failed = run(RES)
    assert failed and "!= recorded" in text and "=> CLAIMED" in text


def test_unfetchable_evidence_fails(ledger):
    db, _ = ledger
    db[RES]["evidence"][0]["url"] = "https://example.invalid/gone"
    assert run(RES)[1]


def test_unpinned_url_is_flagged_not_failed(ledger, monkeypatch):
    db, _ = ledger
    url = "https://github.com/o/r/releases/download/t/x.tar.gz"
    db[RES]["evidence"][0]["url"] = url
    monkeypatch.setattr(vr, "fetch_sha256", lambda u: (SHA, len(BODY)))
    text, failed = run(RES)
    assert not failed and "MUTABLE" in text


def test_missing_linked_record_fails(ledger):
    db, _ = ledger
    db[RES]["body"] += " and 01M00000000000000000000000"
    text, failed = run(RES)
    assert failed and "no such record" in text


def test_result_without_preregistration_fails(ledger):
    db, _ = ledger
    del db[PRE]
    db[RES]["body"] = ""
    text, failed = run(RES)
    assert failed and "no preregistration" in text


def test_preregistration_filed_after_result_fails(ledger):
    db, _ = ledger
    db[PRE]["createdAt"] = "2026-10-17T00:00:00Z"
    text, failed = run(RES)
    assert failed and "filed after this result" in text


def test_amendment_filed_before_what_it_amends_fails(ledger):
    db, _ = ledger
    db[AMD] = rec(AMD, "amendment", "2026-10-14T00:00:00Z", amendsId=PRE)
    text, failed = run(AMD)
    assert failed and "order: amends" in text


def test_guard_block_warns_but_does_not_fail(ledger, monkeypatch):
    monkeypatch.setattr(vr.pub_guard, "check_text", lambda t, fp: [("BLOCK", "ngram", "x y z w", ["p"])])
    text, failed = run(RES)
    assert not failed and "WARN    guard: 1" in text


def test_peer_review_by_another_author_raises_tier(ledger):
    _, reviews = ledger
    reviews[RES] = [{"authorUsername": "B", "verdict": "holds"}]
    assert "=> PEER-REVIEWED" in run(RES)[0]


def test_self_review_and_rejection_do_not_raise_tier(ledger):
    _, reviews = ledger
    reviews[RES] = [{"authorUsername": "A", "verdict": "holds"}, {"authorUsername": "B", "verdict": "rejected"}]
    assert "=> MACHINE-CHECKED" in run(RES)[0]


def test_missing_record_is_an_error_not_a_failure(ledger):
    with pytest.raises(vr.CheckError):
        run("01M11111111111111111111111")


def test_no_evidence_stays_claimed_without_failing(ledger):
    db, _ = ledger
    db[RES]["evidence"] = []
    text, failed = run(RES)
    assert not failed and "evidence: none" in text and "=> CLAIMED" in text


def test_backfill_whose_sha_was_cited_at_filing_counts(ledger, request):
    db, _ = ledger
    db[RES]["evidence"] = []
    db[RES]["body"] += f" rows sha256 {SHA}"
    request.node.notes[RES] = [{"id": "n1", "evidence": [{"url": PIN, "sha256": SHA, "label": "late"}]}]
    text, failed = run(RES)
    assert not failed and "backfilled" in text and "=> MACHINE-CHECKED" in text


def test_backfill_with_an_uncited_sha_does_not_count(ledger, request, monkeypatch):
    monkeypatch.setattr(vr, "fetch_crlf_sha256", lambda url: "f" * 64)
    db, _ = ledger
    db[RES]["evidence"] = []
    request.node.notes[RES] = [{"id": "n1", "evidence": [{"url": PIN, "sha256": SHA, "label": "late"}]}]
    text, failed = run(RES)
    assert "was not cited at filing" in text and "=> CLAIMED" in text


def test_backfill_matching_a_cited_crlf_copy_counts(ledger, request, monkeypatch):
    crlf = "c" * 64  # BODY has no newline, so its real CRLF hash would equal SHA; use a distinct one
    monkeypatch.setattr(vr, "fetch_crlf_sha256", lambda url: crlf)
    db, _ = ledger
    db[RES]["evidence"] = []
    db[RES]["body"] += f" judge sha256 {crlf}"
    request.node.notes[RES] = [{"id": "n1", "evidence": [{"url": PIN, "sha256": SHA, "label": "late"}]}]
    text, failed = run(RES)
    assert not failed and "with CRLF line endings it matches" in text and "=> MACHINE-CHECKED" in text


@pytest.mark.parametrize("verdict", ["breaks", "inconclusive", "rejected", "", None, "something new"])
def test_only_holds_raises_the_tier(ledger, verdict):
    _, reviews = ledger
    reviews[RES] = [{"authorUsername": "B", "verdict": verdict}]
    assert "=> MACHINE-CHECKED" in run(RES)[0]


def test_a_breaks_review_by_another_author_is_flagged(ledger):
    _, reviews = ledger
    reviews[RES] = [{"authorUsername": "B", "verdict": "breaks"}]
    text, failed = run(RES)
    assert "say the record breaks" in text and not failed


def test_holds_with_case_and_space_still_counts(ledger):
    _, reviews = ledger
    reviews[RES] = [{"authorUsername": "B", "verdict": " Holds "}]
    assert "=> PEER-REVIEWED" in run(RES)[0]
