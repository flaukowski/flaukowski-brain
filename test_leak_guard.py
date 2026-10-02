"""leak_guard.py against the real frozen probes, through the hashed fingerprint the training host
gets: it must catch every probe item copied in, whole or partly, and pass honest rows.
Run: python -m pytest test_leak_guard.py"""
import json

import leak_guard as lg

ITEMS = lg.load_items(lg.DEFAULT_ITEMS)
FP = lg.fingerprint(ITEMS)
BY_ID = {(f["set"], f["id"]): f for f in FP}


def fp_of(it):
    return [BY_ID[(it["_set"], it["id"])]]


def _write(tmp_path, rows):
    p = tmp_path / "train.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return str(p)


def _fp_file(tmp_path):
    out = tmp_path / "probes.fp.json"
    assert lg.main(["fingerprint", *lg.DEFAULT_ITEMS, "--out", str(out)]) == 0
    return str(out)


def chat(user, assistant="Not in the record."):
    return {"messages": [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]}


def test_fingerprint_carries_no_probe_text(tmp_path):
    raw = open(_fp_file(tmp_path), encoding="utf-8").read()
    for it in ITEMS:
        assert it["question"] not in raw and it["excerpt"][:40] not in raw, it["id"]


def test_every_probe_item_copied_whole_is_caught():
    for it in ITEMS:
        assert lg.check_row(f"Record excerpt:\n{it['excerpt']}\n\nQuestion: {it['question']}", fp_of(it)), it["id"]


def test_the_question_alone_is_caught():
    for it in ITEMS:
        assert lg.check_row(f"Someone asked: {it['question']} I said I didn't know.", fp_of(it)), it["id"]


def test_excerpt_alone_with_a_new_question_is_caught():
    # the subtle leak: the probe's record, paired with a question the probe doesn't ask
    for it in ITEMS:
        if len(lg.shingles(it["excerpt"])) >= 4:
            assert lg.check_row(it["excerpt"] + "\nWhat else happened that day?", fp_of(it)), it["id"]


def test_sixty_percent_of_the_excerpt_still_counts():
    it = max(ITEMS, key=lambda i: len(i["excerpt"]))
    words = it["excerpt"].split()
    assert lg.check_row(" ".join(words[: int(len(words) * 0.6)]), fp_of(it))


def test_honest_rows_pass(tmp_path):
    rows = [chat("Record excerpt:\nThe build passed on runner r3.\n\nQuestion: What time did it pass?",
                 "The record does not say when it passed."),
            chat("Write one short line for the plaza.", "The fountain is louder at night.")]
    assert lg.main(["check", "--fp", _fp_file(tmp_path), _write(tmp_path, rows)]) == 0


def test_a_leak_fails_the_build(tmp_path):
    it = ITEMS[0]
    rows = [chat("hello", "hi"), chat(f"{it['excerpt']}\n\n{it['question']}", "x")]
    assert lg.main(["check", "--fp", _fp_file(tmp_path), _write(tmp_path, rows)]) == 1


def test_distinct_records_do_not_flag_each_other():
    # A guard that fires on everything is no guard. Present and absent items deliberately share
    # one record (A01/P01 …), so identical excerpts match; two DIFFERENT excerpts must not.
    wrong = [(a["id"], b["id"]) for a in ITEMS for b in ITEMS
             if lg.words(a["excerpt"]) != lg.words(b["excerpt"])
             and any("excerpt" in hit[2] for hit in lg.check_row(b["excerpt"], fp_of(a)))]
    assert wrong == []


def test_an_honest_abstention_is_not_a_leak():
    # absent items' gold is the generic "not in the record"; matching it would flag every abstention
    rows = "That is not in the record. The record does not say what time it passed."
    assert lg.check_row(rows, FP) == []
