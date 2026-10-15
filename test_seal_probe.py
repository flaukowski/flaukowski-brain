"""seal_probe.py on synthetic items (no real v3 item is ever in this repo).
Run: python -m pytest test_seal_probe.py"""
import json

import pytest

import seal_probe as sp

FP3 = "probes-v1v2-e5.fp3.json"
SLICE = "probe-slice-e4-items.json"


def _items(n=4):
    its = []
    for i in range(n):
        its.append({"id": f"T{i:02d}", "kind": "present" if i % 2 else "absent",
                    "excerpt": f"Synthetic excerpt number {i}: the lantern ledger notes amber reading "
                               f"{i * 7} beside the quiet harbour gauge on the northern pier.",
                    "question": f"What reading did the lantern ledger note on pier {i}?",
                    "gold": f"amber reading {i * 7} on the northern pier" if i % 2 else "not in the record"})
    return {"name": "synthetic test set", "frozen": "2026-10-15", "items": its}


def _write(tmp_path, d, name="probe-test-items.json"):
    p = tmp_path / name
    p.write_text(json.dumps(d), encoding="utf-8")
    return str(p)


def _seal(path, out):
    return sp.main(["seal", path, "--public-fp", FP3, "--public-items", SLICE, "--out-dir", str(out)])


def test_clean_set_seals_and_outputs_carry_no_text(tmp_path, capsys):
    d = _items()
    out = tmp_path / "sealed"
    assert _seal(_write(tmp_path, d), out) == 0
    printed = capsys.readouterr().out
    seal = json.loads((out / "probe-test-items.seal.json").read_text(encoding="utf-8"))
    fp_text = (out / "probe-test-items.fp.json").read_text(encoding="utf-8")
    assert seal["n_items"] == 4 and seal["n_present"] == 2 and seal["public_overlaps"] == 0
    assert seal["canonical_sha256"] == sp.canonical_sha(d)
    for it in d["items"]:
        for field in ("excerpt", "question", "gold"):
            frag = it[field][:24]
            assert frag not in printed and frag not in fp_text and frag not in json.dumps(seal)


def test_a_public_item_is_refused(tmp_path, capsys):
    d = _items()
    v1 = json.load(open("probe-v1-items.json", encoding="utf-8"))["items"][0]
    d["items"].append({**v1, "id": "T99"})
    with pytest.raises(SystemExit):
        _seal(_write(tmp_path, d), tmp_path / "sealed")
    assert "OVERLAP v3 item T99" in capsys.readouterr().out
    assert not (tmp_path / "sealed" / "probe-test-items.seal.json").exists()


def test_duplicate_id_is_refused(tmp_path):
    d = _items()
    d["items"][1]["id"] = d["items"][0]["id"]
    with pytest.raises(SystemExit):
        _seal(_write(tmp_path, d), tmp_path / "sealed")


def test_a_seal_is_written_once(tmp_path):
    p = _write(tmp_path, _items())
    assert _seal(p, tmp_path / "sealed") == 0
    with pytest.raises(SystemExit):
        _seal(p, tmp_path / "sealed")
