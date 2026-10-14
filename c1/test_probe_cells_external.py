"""probe_cells.py's external-serve path as KSHB rev 5 runs it: the ask half on O1 (Linux, no winreg) and attach.

Imported with winreg blocked, as on Linux. NATS is stubbed, so nothing reaches the hub and no serve runs: this
checks the plumbing (rows, records, the join with an operator record, the gates), not a model.
Run: python -m pytest c1/test_probe_cells_external.py
"""
import importlib
import json
import sys

import pytest

HELD_ANSWER = "That isn't in my record."
P_PROD = ["P/v1/production", "P/v2/production"]


@pytest.fixture
def pc(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "winreg", None)   # `import winreg` now raises ImportError, as on Linux
    monkeypatch.setenv("C1_RUNS", str(tmp_path / "runs"))
    monkeypatch.setenv("C1_SMOKE_DIR", str(tmp_path / "smoke"))
    for k in ("NATS_USER", "NATS_PASSWORD"):
        monkeypatch.setenv(k, "test")
    sys.modules.pop("probe_cells", None)
    monkeypatch.syspath_prepend(str(__import__("pathlib").Path(__file__).parent))
    mod = importlib.import_module("probe_cells")
    assert mod.winreg is None

    class NC:
        async def close(self):
            pass

    async def connect(c):
        return NC()

    async def ask(nc, subject, frm, text):
        mod._asked.append((subject, frm))
        return HELD_ANSWER

    mod._asked = []
    monkeypatch.setattr(mod, "_connect", connect)
    monkeypatch.setattr(mod, "ask_serve", ask)
    return mod


def _main(mod, monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["probe_cells.py", *argv])
    mod.main()


def _operator(tmp_path, directed, tag="kannaka-brain-7b-v2", ctx=4096, same_hrm=True):
    log = tmp_path / "op.json.err.log"
    log.write_text("[swarm serve] prompt arm: baseline\n"
                   "[swarm serve] rate limit: 1000/hour total\n"
                   "[swarm serve] subscribing to KANNAKA.ask.kannaka-prime\n"
                   + "".join(f"[swarm serve] ask directed from probe-x{i}\n" for i in range(directed)),
                   encoding="utf-8")
    rec = {"tag": tag, "num_ctx": ctx, "hrm_sha256_before": "a" * 64, "hrm_sha256_after": "a" * 64 if same_hrm else "b" * 64,
           "alive_at_end": True, "ollama_loaded_after_smoke": [{"name": f"{tag}:latest", "context_length": ctx}],
           "operator": "test-driver"}
    op = tmp_path / "op.json"
    op.write_text(json.dumps(rec), encoding="utf-8")
    return op, log


def test_user_env_without_winreg(pc, monkeypatch):
    assert pc.user_env("NATS_USER") == "test"
    monkeypatch.delenv("NATS_PASSWORD")
    with pytest.raises(SystemExit):
        pc.user_env("NATS_PASSWORD")


def test_external_ask_then_attach_measures(pc, tmp_path, monkeypatch):
    _main(pc, monkeypatch, "run", "--external", "--smoke", "--only", *P_PROD,
          "--ask-subject", "KANNAKA.ask.kannaka-prime", "--model-digest", "d" * 12)
    subjects = {s for s, _ in pc._asked}
    assert subjects == {"KANNAKA.ask.kannaka-prime"}
    probes = [f for _, f in pc._asked if f.startswith("probe-")]
    assert len(probes) == 2                                   # smoke: 1 item x 1 sample per cell, plus one smoke ask
    for cid in P_PROD:
        rec = json.loads((pc.CELLS / f"{pc.safe(cid)}.json").read_text(encoding="utf-8"))
        assert rec["serve"] == "pending-operator-record" and rec["exit"] is None
        assert rec["seconds"] == 0 and rec["mode"] == "external-serve"
    op, log = _operator(tmp_path, directed=2)
    _main(pc, monkeypatch, "attach", "--smoke", "--cells", *P_PROD, "--operator-record", str(op), "--serve-log", str(log))
    for cid in P_PROD:
        rec = json.loads((pc.CELLS / f"{pc.safe(cid)}.json").read_text(encoding="utf-8"))
        assert rec["outcome"] == "measured", rec["outcome"]
        assert rec["exit"] == 0 and all(rec["gates"].values())


@pytest.mark.parametrize("bad", ["count", "snapshot", "tag"])
def test_attach_refuses_a_bad_operator_record(pc, tmp_path, monkeypatch, bad):
    _main(pc, monkeypatch, "run", "--external", "--smoke", "--only", *P_PROD,
          "--ask-subject", "KANNAKA.ask.kannaka-prime", "--model-digest", "d" * 12)
    op, log = _operator(tmp_path, directed=3 if bad == "count" else 2, same_hrm=bad != "snapshot",
                        tag="kannaka-brain-e3" if bad == "tag" else "kannaka-brain-7b-v2")
    with pytest.raises(SystemExit):
        _main(pc, monkeypatch, "attach", "--smoke", "--cells", *P_PROD, "--operator-record", str(op),
              "--serve-log", str(log))
    if bad != "tag":   # a wrong tag is refused before any record is rewritten
        rec = json.loads((pc.CELLS / f"{pc.safe(P_PROD[0])}.json").read_text(encoding="utf-8"))
        assert rec["exit"] == 3 and rec["outcome"].startswith("failed its gates")
