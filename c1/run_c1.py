"""kannaka-loop-c1 runner (training and merge stages) for the desktop RTX 3050. Written to be read by Kannaka
before anything runs; it refuses while c1_config.json still has a FILL field.

    python c1/run_c1.py check            # every gate that needs no GPU: config, hashes, commit, snapshot, leaks
    python c1/run_c1.py train [--only NAME ...]
    python c1/run_c1.py merge [--only NAME ...]

Gates, each a refusal (non-zero exit, nothing trained) unless stated:
  - no FILL left in the config; the fingerprint and the init adapter match their pinned sha256;
  - the kannaka-memory worktree is exactly at the configured commit and clean (the trainer that runs is the
    trainer that was reviewed);
  - the base loads offline from the hub cache snapshot b968826d (HF_HUB_OFFLINE=1, recorded per run);
  - each run's train.jsonl and holdout.jsonl pass leak_guard against fp3 (0 leaks), checked right before
    that run and hashed into its record;
  - the GPU is idle (no other process holding >500 MiB) before each run;
  - the GPU-hours cap: before a run starts, spent + the slowest finished run must fit under the cap, or the
    runner stops in the frozen order (L-s7 and N-s7 first), which still allows the gate verdict.
Trainer exits are recorded, not retried: 0 trained, 4 diverged (c1 stop rule), 6 VRAM guard, anything else
a failure. A run with a record is never re-run (resume skips it); delete the record by hand to redo one.
Each run's record (c1/runs/NAME.json) holds commit, snapshot, data hashes, the exact command, wall time,
exit code, the trainer manifest and the adapter's sha256.
"""
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CFG = Path(os.environ.get("C1_CONFIG", HERE / "c1_config.json"))   # override only for a dry check
RUNS = HERE / "runs"
KM = Path(r"C:\Users\nflach\AppData\Local\Temp\claude\C--Windows-System32\928d7661-9c22-4174-ad5c-1c935d87cee6"
          r"\scratchpad\km-master")
PY = r"C:\Users\nflach\venvs\qlora\Scripts\python.exe"
SNAPSHOTS = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots"
MODELS = Path(r"C:\Users\nflach\models\c1")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def die(msg: str, code: int = 2):
    print(f"run_c1: REFUSED: {msg}", flush=True)
    sys.exit(code)


def load_cfg() -> dict:
    c = json.loads(CFG.read_text(encoding="utf-8"))
    fills = [k for k, v in walk(c) if isinstance(v, str) and v.startswith("FILL")]
    if fills:
        die(f"config still has FILL in: {', '.join(fills)}")
    return c


def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, o


def gates(c: dict):
    fp = Path(c["leak_fingerprint"]["path"])
    if sha(fp) != c["leak_fingerprint"]["sha256"]:
        die(f"fingerprint {fp} does not match its pinned sha256")
    t = c["trainer"]
    ad = Path(t["init_adapter"]) / "adapter_model.safetensors"
    if sha(ad) != t["init_adapter_sha256"]:
        die("init adapter does not match its pinned sha256")
    head = subprocess.run(["git", "-C", str(KM), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(KM), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True).stdout.strip()
    if not head.startswith(t["kannaka_memory_commit"]) or dirty:
        die(f"kannaka-memory worktree is at {head[:12]}{' (dirty)' if dirty else ''}, "
            f"not {t['kannaka_memory_commit']} clean")
    snap = SNAPSHOTS / t["hf_snapshot"]
    if not (snap / "model-00005-of-00005.safetensors").exists():
        die(f"hub cache snapshot {t['hf_snapshot']} is missing the weights (see the hard-link setup)")
    return head


def leak_check(c: dict, data: Path):
    r = subprocess.run([PY, str(ROOT / "leak_guard.py"), "check", "--fp", c["leak_fingerprint"]["path"],
                        str(data / "train.jsonl"), str(data / "holdout.jsonl")], capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:], flush=True)
    if r.returncode != 0:
        die(f"leak_guard found probe text in {data} (see above); this run does not start", 3)


def gpu_idle():
    r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    busy = [l for l in r.stdout.splitlines() if l.strip() and int(l.split(",")[1]) > 500]
    if busy:
        die(f"the GPU is in use: {busy}")


def records():
    RUNS.mkdir(exist_ok=True)
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in RUNS.glob("*.json")}


def cmd_check(a):
    c = load_cfg()
    head = gates(c)
    for r in c["runs"]:
        leak_check(c, Path(r["data"]))
    print(f"run_c1: all gates pass (kannaka-memory {head[:12]}, snapshot {c['trainer']['hf_snapshot'][:8]})")


def cmd_train(a):
    c = load_cfg()
    head = gates(c)
    t = c["trainer"]
    for r in c["runs"]:
        if a.only and r["name"] not in a.only:
            continue
        done = records()
        if r["name"] in done:
            print(f"run_c1: {r['name']} has a record (exit {done[r['name']]['exit']}); skipped", flush=True)
            continue
        spent = sum(d["seconds"] for d in done.values()) / 3600
        slowest = max([d["seconds"] for d in done.values()] or [0]) / 3600
        if spent + slowest > c["gpu_hours_cap"]:
            die(f"GPU-hours cap: {spent:.1f} h spent, the slowest run took {slowest:.1f} h, cap "
                f"{c['gpu_hours_cap']} h. Stopping before {r['name']} in the frozen order.", 5)
        data = Path(r["data"])
        leak_check(c, data)
        gpu_idle()
        out = MODELS / r["name"].replace("'", "p")
        cmd = [PY, str(KM / "tools/corpus/p2/train_lora.py"), "--base", t["base"], "--data", str(data),
               "--out", str(out), "--init-adapter", t["init_adapter"], "--r", str(t["r"]), "--lr", str(t["lr"]),
               "--max-len", str(t["max_len"]), "--batch", str(t["batch"]), "--grad-accum", str(t["grad_accum"]),
               "--max-steps", str(t["K"]), "--seed", str(r["seed"]), "--eval-every", str(t["eval_every"]),
               "--max-holdout-rise", str(t["max_holdout_rise"]), "--vram-guard-gib", str(t["vram_guard_gib"]),
               "--chat-template-kwargs", json.dumps(t["chat_template_kwargs"]), "--eval-samples", "0",
               *t["extra_flags"]]
        env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONIOENCODING="utf-8")
        print(f"run_c1: {r['name']} starting {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", flush=True)
        t0 = time.time()
        with open(HERE / f"{r['name'].replace(chr(39), 'p')}.log", "x", encoding="utf-8") as log:
            rc = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        secs = round(time.time() - t0)
        man_p = out / "train.manifest.json"
        ad_p = out / "adapter" / "adapter_model.safetensors"
        rec = {"name": r["name"], "arm": r["arm"], "seed": r["seed"], "exit": rc, "seconds": secs,
               "outcome": {0: "trained", 4: "diverged (c1 stop rule)", 6: "VRAM guard"}.get(rc, "failed"),
               "kannaka_memory": head, "hf_snapshot": t["hf_snapshot"], "cmd": cmd,
               "data_sha256": {f: sha(data / f) for f in ("train.jsonl", "holdout.jsonl")},
               "manifest": json.loads(man_p.read_text(encoding="utf-8")) if man_p.exists() else None,
               "adapter_sha256": sha(ad_p) if ad_p.exists() and rc == 0 else None}
        (RUNS / f"{r['name']}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        print(f"run_c1: {r['name']} exit {rc} ({rec['outcome']}) in {secs / 60:.1f} min", flush=True)


def cmd_merge(a):
    c = load_cfg()
    for name, rec in sorted(records().items()):
        if (a.only and name not in a.only) or rec["exit"] != 0:
            continue
        out = MODELS / name.replace("'", "p")
        gguf = out / "merged-gguf" / "gguf" / "kannaka-brain-q4_K_M.gguf"
        if gguf.exists():
            print(f"run_c1: {name} already merged", flush=True)
            continue
        gpu_idle()
        rc = subprocess.run([PY, str(ROOT / "merge_e3.py"), "--adapter", str(out / "adapter"),
                             "--out", str(out / "merged-gguf")]).returncode
        if rc != 0:
            die(f"merge of {name} failed (exit {rc})", 4)
        rec["gguf_sha256"] = sha(gguf)
        (RUNS / f"{name}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        print(f"run_c1: {name} merged, gguf sha256 {rec['gguf_sha256'][:12]}", flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("check")
    for n in ("train", "merge"):
        p = sp.add_parser(n)
        p.add_argument("--only", nargs="*")
    a = ap.parse_args()
    {"check": cmd_check, "train": cmd_train, "merge": cmd_merge}[a.cmd](a)


if __name__ == "__main__":
    main()
