"""kannaka-loop-c1 runner (training and merge stages) for the desktop RTX 3050. Written to be read by Kannaka
before anything runs; it refuses while c1_config.json still has a FILL field.

    python c1/run_c1.py check            # every gate that needs no GPU: config, hashes, commit, snapshot, leaks
    python c1/run_c1.py train [--only NAME ...]
    python c1/run_c1.py merge [--only NAME ...]

Gates, each a refusal (non-zero exit, nothing trained) unless stated:
  - no FILL left in the config; the fingerprint and the init adapter match their pinned sha256;
  - the kannaka-memory worktree is exactly at the configured commit (the full 40 characters, compared whole,
    never as a prefix) and clean, AND the trainer that commit holds (git's LF bytes of
    tools/corpus/p2/train_lora.py) hashes to trainer_sha256_expected: the trainer that runs is the trainer
    that was reviewed;
  - K equals 2 x ceil((320 + |D_W|) / 8) for the configured |D_W| and is at most 160;
  - the base loads offline from the hub cache snapshot b968826d (HF_HUB_OFFLINE=1, recorded per run);
  - each run's holdout.jsonl hashes to holdout_sha256_expected (section 2.3: every arm measures loss on the
    same sft-v2 hold-out), checked right before that run;
  - each run's train.jsonl and holdout.jsonl pass leak_guard against fp3 (0 leaks), checked right before
    that run and hashed into its record;
  - the GPU is idle: nvidia-smi memory.used at most 500 MiB before each run. (The per-process query is not
    a gate on Windows/WDDM: it prints "[N/A]" for used memory, so it cannot fail; measured 2026-10-07 with
    1 GiB held from a second python: memory.used 1105, compute-apps "6712, [N/A]". A gate that cannot read
    is a refusal, not a pass.)
  - no run may start if a run named in stop_on_failure has a non-zero record: section 2.3 files the campaign
    as a failure, and the remaining runs need an amendment, not a runner;
  - a run whose out dir or log exists with no record started and died unrecorded: the runner writes a
    failure record for it and refuses; inspect, then delete the out dir, the log and the record by hand;
  - the GPU-hours cap for TRAINING (gpu_hours_cap_training, 15 of the 24 total so the probe cells fit):
    before a run starts, spent + the slowest finished run must fit under it, or the runner stops in the
    frozen order (L-s7 and N-s7 first), which still allows the gate verdict.
Trainer exits are recorded, not retried: 0 trained, 4 diverged (c1 stop rule), 6 VRAM guard, 7 trl cannot do
answer-only logits, anything else a failure. A run with a record is never re-run (resume skips it); delete
the record by hand to redo one. Each run's record (c1/runs/NAME.json) holds the commit, the trainer sha256,
the snapshot, |D_W| and K, the data hashes, the exact command, wall time, exit code, the trainer manifest
and the adapter's sha256. The merge stage adds the merge pins (route, merge_e3.py, converter, quantizer,
llama.cpp build, the chat template baked into the GGUF, and the merge base's identity with the snapshot)
beside gguf_sha256.

Runner exit codes: 2 a gate refused, 3 leak_guard, 4 merge failed, 5 GPU-hours cap, 6 an unrecorded start,
7 a stop_on_failure run has failed.
"""
import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CFG = Path(os.environ.get("C1_CONFIG", HERE / "c1_config.json"))   # override only for a dry check
RUNS = Path(os.environ.get("C1_RUNS", HERE / "runs"))               # override only for a dry check
KM = Path(r"C:\Users\nflach\AppData\Local\Temp\claude\C--Windows-System32\928d7661-9c22-4174-ad5c-1c935d87cee6"
          r"\scratchpad\km-master")
TRAINER_REL = "tools/corpus/p2/train_lora.py"
PY = r"C:\Users\nflach\venvs\qlora\Scripts\python.exe"
SNAPSHOTS = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen3-8B/snapshots"
MODELS = Path(os.environ.get("C1_MODELS", r"C:\Users\nflach\models\c1"))
MERGE_BASE = Path(r"C:\Users\nflach\models\Qwen3-8B")     # merge_e3.py's base: hard-linked to the snapshot
LC = Path(r"C:\Users\nflach\llama.cpp")
GPU_BUSY_MIB = 500
MERGE_ROUTE = "bf16 merge on CPU (merge_e3.py) -> convert_hf_to_gguf f16 -> llama-quantize q4_K_M; no q8_0 stage"


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


def git(*args, binary=False):
    r = subprocess.run(["git", "-C", str(KM), *args], capture_output=True, text=not binary)
    if r.returncode != 0:
        die(f"git {' '.join(args)} failed in {KM}: {(r.stderr if binary else r.stderr).strip()[-300:]}")
    return r.stdout if binary else r.stdout.strip()


def gates(c: dict) -> dict:
    """Everything that is true of the whole campaign, not of one run. Returns the pins to record."""
    fp = Path(c["leak_fingerprint"]["path"])
    if sha(fp) != c["leak_fingerprint"]["sha256"]:
        die(f"fingerprint {fp} does not match its pinned sha256")
    t = c["trainer"]
    ad = Path(t["init_adapter"]) / "adapter_model.safetensors"
    if sha(ad) != t["init_adapter_sha256"]:
        die("init adapter does not match its pinned sha256")
    commit = t["kannaka_memory_commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        die(f"kannaka_memory_commit must be the full 40-character commit, not {commit!r}")
    head = git("rev-parse", "HEAD")
    dirty = git("status", "--porcelain", "--untracked-files=no")
    if head != commit or dirty:
        die(f"kannaka-memory worktree is at {head[:12]}{' (dirty)' if dirty else ''}, not {commit[:12]} clean")
    trainer_sha = hashlib.sha256(git("show", f"{commit}:{TRAINER_REL}", binary=True)).hexdigest()
    if trainer_sha != t["trainer_sha256_expected"]:
        die(f"{TRAINER_REL} at {commit[:12]} hashes to {trainer_sha[:12]}, not the reviewed "
            f"{t['trainer_sha256_expected'][:12]}")
    d_w, k = int(t["d_w"]), int(t["K"])
    want_k = 2 * math.ceil((320 + d_w) / 8)
    if k != want_k or k > 160:
        die(f"K is {k}; for |D_W| = {d_w} the text gives 2 x ceil((320 + {d_w}) / 8) = {want_k}, at most 160")
    snap = SNAPSHOTS / t["hf_snapshot"]
    if not (snap / "model-00005-of-00005.safetensors").exists():
        die(f"hub cache snapshot {t['hf_snapshot']} is missing the weights (see the hard-link setup)")
    return {"kannaka_memory": head, "trainer_sha256": trainer_sha, "hf_snapshot": t["hf_snapshot"]}


def holdout_gate(c: dict, data: Path) -> str:
    want = c["trainer"]["holdout_sha256_expected"]
    got = sha(data / "holdout.jsonl")
    if got != want:
        die(f"{data / 'holdout.jsonl'} hashes to {got[:12]}, not the sft-v2 hold-out {want[:12]} every arm must share")
    return got


def leak_check(c: dict, data: Path):
    r = subprocess.run([PY, str(ROOT / "leak_guard.py"), "check", "--fp", c["leak_fingerprint"]["path"],
                        str(data / "train.jsonl"), str(data / "holdout.jsonl")], capture_output=True, text=True)
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:], flush=True)
    if r.returncode != 0:
        die(f"leak_guard found probe text in {data} (see above); this run does not start", 3)


def gpu_used_mib() -> int:
    r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    line = r.stdout.strip().splitlines()[0].strip() if r.stdout.strip() else ""
    if r.returncode != 0 or not line.isdigit():
        die(f"cannot read GPU memory.used from nvidia-smi (rc {r.returncode}, {line!r}); not treated as idle")
    return int(line)


def gpu_idle():
    used = gpu_used_mib()
    if used > GPU_BUSY_MIB:
        apps = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                               "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
        die(f"the GPU is in use: memory.used {used} MiB > {GPU_BUSY_MIB}; processes: {apps or '(none listed)'}")


def records():
    RUNS.mkdir(exist_ok=True)
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in RUNS.glob("*.json")}


def record_path(name: str) -> Path:
    return RUNS / f"{name}.json"


def safe(name: str) -> str:
    return name.replace("'", "p")


def stop_on_failure_gate(c: dict, done: dict):
    for name in c.get("stop_on_failure", []):
        if name in done and done[name]["exit"] != 0:
            die(f"{name} recorded exit {done[name]['exit']} ({done[name]['outcome']}); section 2.3 files the "
                "campaign as a failure. No further run starts without an amendment.", 7)


def unrecorded_start_gate(r: dict, out: Path, log: Path, pins: dict):
    """A run that started and died leaves an out dir or a log and no record. Record it as a failure and refuse."""
    traces = [str(p) for p in (out, log) if p.exists()]
    if not traces:
        return
    rec = {"name": r["name"], "arm": r["arm"], "seed": r["seed"], "exit": None, "seconds": 0,
           "outcome": "interrupted: a run started and left no record", "traces": traces,
           "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **pins}
    record_path(r["name"]).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    die(f"{r['name']} started and left no record ({', '.join(traces)}). A failure record is written; inspect, "
        "then delete the out dir, the log and the record by hand to redo it.", 6)


def cmd_check(a):
    c = load_cfg()
    pins = gates(c)
    for r in c["runs"]:
        holdout_gate(c, Path(r["data"]))
        leak_check(c, Path(r["data"]))
    for p in (ROOT / "merge_e3.py", LC / "src" / "convert_hf_to_gguf.py", LC / "bin" / "llama-quantize.exe",
              Path(c["trainer"]["init_adapter"]) / "chat_template.jinja"):
        if not p.exists():
            die(f"merge stage needs {p}")
    base_pins = merge_base_identity(c)
    print(f"run_c1: GPU memory.used now {gpu_used_mib()} MiB (gate: at most {GPU_BUSY_MIB})")
    print(f"run_c1: all gates pass (kannaka-memory {pins['kannaka_memory'][:12]}, trainer "
          f"{pins['trainer_sha256'][:12]}, snapshot {pins['hf_snapshot'][:8]}, |D_W| {c['trainer']['d_w']} K "
          f"{c['trainer']['K']}, merge base {'is' if base_pins['same_bytes_as_snapshot'] else 'IS NOT'} the snapshot)")


def cmd_train(a):
    c = load_cfg()
    pins = gates(c)
    t = c["trainer"]
    cap = c["gpu_hours_cap_training"]
    for r in c["runs"]:
        if a.only and r["name"] not in a.only:
            continue
        done = records()
        if r["name"] in done:
            print(f"run_c1: {r['name']} has a record (exit {done[r['name']]['exit']}); skipped", flush=True)
            continue
        stop_on_failure_gate(c, done)
        spent = sum(d["seconds"] for d in done.values()) / 3600
        slowest = max([d["seconds"] for d in done.values()] or [0]) / 3600
        if spent + slowest > cap:
            die(f"GPU-hours cap: {spent:.1f} h spent, the slowest run took {slowest:.1f} h, training cap "
                f"{cap} h (of {c['gpu_hours_cap_total']} total). Stopping before {r['name']} in the frozen order.", 5)
        # The probe stage shares this ledger (c1/runs/cells/*.json carry seconds too): training must also
        # leave the total under gpu_hours_cap_total once cells have been spent.
        cells_h = sum(json.loads(p.read_text(encoding="utf-8")).get("seconds", 0)
                      for p in (RUNS / "cells").glob("*.json")) / 3600
        if spent + cells_h + slowest > c["gpu_hours_cap_total"]:
            die(f"GPU-hours total: {spent:.1f} h training + {cells_h:.1f} h cells, the slowest run took "
                f"{slowest:.1f} h, total cap {c['gpu_hours_cap_total']} h. Stopping before {r['name']}.", 5)
        data = Path(r["data"])
        out = MODELS / safe(r["name"])
        log_p = HERE / f"{safe(r['name'])}.log"
        unrecorded_start_gate(r, out, log_p, pins)
        holdout_sha = holdout_gate(c, data)
        leak_check(c, data)
        gpu_idle()
        cmd = [PY, str(KM / TRAINER_REL), "--base", t["base"], "--data", str(data),
               "--out", str(out), "--init-adapter", t["init_adapter"], "--r", str(t["r"]), "--alpha", str(t["alpha"]),
               "--dropout", str(t["dropout"]), "--lr", str(t["lr"]),
               "--max-len", str(t["max_len"]), "--batch", str(t["batch"]), "--grad-accum", str(t["grad_accum"]),
               "--max-steps", str(t["K"]), "--seed", str(r["seed"]), "--eval-every", str(t["eval_every"]),
               "--max-holdout-rise", str(t["max_holdout_rise"]), "--vram-guard-gib", str(t["vram_guard_gib"]),
               "--chat-template-kwargs", json.dumps(t["chat_template_kwargs"]), "--eval-samples", "0",
               *t["extra_flags"]]
        env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONIOENCODING="utf-8")
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        print(f"run_c1: {r['name']} starting {started} ({spent:.1f} h spent of {cap})", flush=True)
        t0 = time.time()
        with open(log_p, "x", encoding="utf-8") as log:
            rc = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        secs = round(time.time() - t0)
        man_p = out / "train.manifest.json"
        ad_p = out / "adapter" / "adapter_model.safetensors"
        rec = {"name": r["name"], "arm": r["arm"], "seed": r["seed"], "exit": rc, "seconds": secs,
               "outcome": {0: "trained", 4: "diverged (c1 stop rule)", 6: "VRAM guard",
                           7: "trl cannot do answer-only logits"}.get(rc, "failed"),
               "started": started, **pins, "d_w": t["d_w"], "K": t["K"], "lr": t["lr"], "r": t["r"],
               "alpha": t["alpha"], "dropout": t["dropout"], "eval_every": t["eval_every"],
               "gpu_hours": {"cap_training": cap, "cap_total": c["gpu_hours_cap_total"], "spent_before": round(spent, 3)},
               "cmd": cmd,
               "data_sha256": {"train.jsonl": sha(data / "train.jsonl"), "holdout.jsonl": holdout_sha},
               "manifest": json.loads(man_p.read_text(encoding="utf-8")) if man_p.exists() else None,
               "adapter_sha256": sha(ad_p) if ad_p.exists() and rc == 0 else None}
        record_path(r["name"]).write_text(json.dumps(rec, indent=1), encoding="utf-8")
        print(f"run_c1: {r['name']} exit {rc} ({rec['outcome']}) in {secs / 60:.1f} min", flush=True)
        if rc != 0 and r["name"] in c.get("stop_on_failure", []):
            die(f"{r['name']} exited {rc} ({rec['outcome']}); section 2.3 files the campaign as a failure. "
                "The remaining runs do not start without an amendment.", 7)


def merge_base_identity(c: dict) -> dict:
    """merge_e3.py reads its base from MERGE_BASE, not the hub cache. Prove it is the same bytes as the pinned
    snapshot: every weight shard must be a hard link of the snapshot's (same inode), config.json byte-equal."""
    snap = SNAPSHOTS / c["trainer"]["hf_snapshot"]
    shards = sorted(p.name for p in snap.glob("model-*.safetensors"))
    same = all((MERGE_BASE / s).exists() and os.stat(MERGE_BASE / s).st_ino == os.stat(snap / s).st_ino
               and os.stat(MERGE_BASE / s).st_dev == os.stat(snap / s).st_dev for s in shards)
    same = same and sha(MERGE_BASE / "config.json") == sha(snap / "config.json")
    return {"merge_base": str(MERGE_BASE), "snapshot": c["trainer"]["hf_snapshot"], "shards": len(shards),
            "same_bytes_as_snapshot": same}


def merge_pins(c: dict) -> dict:
    build = sorted(p.name for p in LC.glob("llama-*-bin-*.zip"))
    tmpl = Path(c["trainer"]["init_adapter"]) / "chat_template.jinja"   # merge_e3 saves the adapter's tokenizer
    return {"route": MERGE_ROUTE,
            "merge_e3_sha256": sha(ROOT / "merge_e3.py"),
            "convert_hf_to_gguf_sha256": sha(LC / "src" / "convert_hf_to_gguf.py"),
            "llama_quantize_sha256": sha(LC / "bin" / "llama-quantize.exe"),
            "llama_cpp_build": build[0] if build else None,
            "chat_template": {"file": str(tmpl), "sha256": sha(tmpl)},
            "base": merge_base_identity(c)}


def cmd_merge(a):
    c = load_cfg()
    pins = merge_pins(c)
    if not pins["base"]["same_bytes_as_snapshot"]:
        die(f"{MERGE_BASE} is not the pinned snapshot's bytes; the merge would use a base nobody reviewed")
    for name, rec in sorted(records().items()):
        if (a.only and name not in a.only) or rec["exit"] != 0:
            continue
        out = MODELS / safe(name)
        gguf = out / "merged-gguf" / "gguf" / "kannaka-brain-q4_K_M.gguf"
        if gguf.exists() and rec.get("gguf_sha256"):
            print(f"run_c1: {name} already merged", flush=True)
            continue
        gpu_idle()
        t0 = time.time()
        rc = subprocess.run([PY, str(ROOT / "merge_e3.py"), "--adapter", str(out / "adapter"),
                             "--out", str(out / "merged-gguf")]).returncode
        if rc != 0:
            die(f"merge of {name} failed (exit {rc})", 4)
        rec["merge"] = {**pins, "seconds": round(time.time() - t0), "gguf": str(gguf)}
        rec["gguf_sha256"] = sha(gguf)
        record_path(name).write_text(json.dumps(rec, indent=1), encoding="utf-8")
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
