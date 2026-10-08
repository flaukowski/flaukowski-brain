"""kannaka-loop-c1 probe-cell stage: the 60 cells of c1_probe_cells.json (prereg revision 3, sections 2.4/2.6),
written by Kannaka 2026-10-07, run on this desktop against the merged q4_K_M of each c1 run plus P and REF.

    python c1/probe_cells.py check                      # cells file, item files, tags, serve binary, GPU, no asks
    python c1/probe_cells.py build-tags [--only RUN ...] # ollama tags for merged runs, from the production Modelfile
    python c1/probe_cells.py run [--only CELL_ID ...]   # the cells, in the frozen order; one record per cell
    python c1/probe_cells.py run --smoke                 # plumbing only: 1 item x 1 sample on P, into a scratch dir

External-serve mode (KSHB T1 on a serve someone else operates; agreed with Kannaka 2026-10-08):
    # the serve's operator, on the serving host: the session half with every E5 gate, then a record + log
    python c1/probe_cells.py operator-serve --tag <tag> --num-ctx <8192|4096> --minutes 240 --out op.json
    # the asker, anywhere with request/reply on the subject: the ask half; records wait on the operator
    python c1/probe_cells.py run --external --only <cell ids> --ask-subject KANNAKA.ask.<subject> --model-digest <d>
    # when the operator's record and err log arrive: join them, recompute the gates, finalize the records
    python c1/probe_cells.py attach --cells <cell ids> --operator-record op.json --serve-log op.json.err.log
  `operator-serve` stops when --minutes pass or `<out>.stop` appears. The same log_gates()/operator_record_gates()
  judge local and external sessions, so the two modes cannot drift apart. The asker's NATS client (nats-py)
  subscribes only to its own _INBOX reply subject, so the ask half carries none of kannaka-memory#1101's refused
  wildcard retries. Every record names instrument_author.

What a cell is (c1_probe_cells.json, cells_defined):
  bare        the neutral bare prompt of E3/E4/E5 (brain_probe.SYSTEM_A + prompt_text, unchanged), straight to
              Ollama, temperature 0.2, num_ctx 8192, one request per sample with that sample's sampling seed.
  serve       the real serve path (kannaka swarm serve, KANNAKA_SERVE_PROMPT_ARM=baseline, mode no_recall) on the
              model's -serve tag: temperature 0.2 and num_ctx 8192 baked into the tag, exactly as E5's
              kannaka-brain-e4-serve was. serve carries NO per-request options (agent.rs passes only
              num_predict), so "0.2/8192 as request options" is realised the way E5 realised it: by the tag.
  production  the same serve path on the production tag (the production Modelfile verbatim: 0.8/4096).
Serve rows carry sampling_seed null: the ask payload has no seed field, so the three samples are three
unseeded draws, as in E3-E5. Bare rows carry the seed they were asked with.

Gates (each a refusal; nothing is asked past a failed gate):
  - the cells file and both item files hash to their pinned values (the canonical-JSON hash of
    held-out-probes.md and the raw-file hash that brain_probe pins);
  - the tag a cell names exists in Ollama, and for a c1 run was built here from the run's gguf whose sha256
    the run record pins (build-tags refuses a gguf that does not match its record);
  - the serve binary matches its pinned sha256 (the E5 build, 0.16.14 at 1b01652, so P/REF/c1 share the
    instrument);
  - a serve session runs on a frozen private data dir (never the live ~/.kannaka), hashed before and after;
    its log must show the arm, the raised total limit (1000/hour) and the subscription before the smoke ask;
    Ollama is emptied before every cell group, and after the smoke ask (or after a bare group) it must hold
    exactly the cell's tag at the cell's context length (Ollama reuses a runner across tags that share a
    blob, so `ollama ps` alone names whichever tag loaded first; measured 2026-10-07); the session must not
    restart or exit; the directed ask count must equal the cell's asks (120, or 240 when both sets share the
    session); 0 [error] answers;
  - the hour ledger: training seconds + cell seconds + the slowest finished cell must fit under
    gpu_hours_cap_total before a cell starts (section 2.3 / review point 4);
  - a cell with a record is never re-run; a cell whose rows file exists with no record is an unrecorded start
    and is refused with a failure record (same rule as the runner).
Every answer row carries run, set, cell, cell_id, item id, kind, sample, sampling_seed, serve_tag (or the bare
tag), model_digest, temperature, num_ctx, and the fields make_pack.py reads (arm, temp, item, sample, answer).

Exit codes: 2 a gate refused, 3 a cell failed its gates after running (rows kept, record says so), 5 the hour
ledger, 6 an unrecorded start.
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import winreg
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import brain_probe  # noqa: E402  (SYSTEM_A, prompt_text, pregrade, model_digest: the E3-E5 prompt, unchanged)

CFG = Path(os.environ.get("C1_CONFIG", HERE / "c1_config.json"))
RUNS = Path(os.environ.get("C1_RUNS", HERE / "runs"))
CELLS = RUNS / "cells"
MODELS = Path(os.environ.get("C1_MODELS", r"C:\Users\nflach\models\c1"))
LOGS = Path.home() / ".kannaka" / "logs"
OLLAMA = "http://127.0.0.1:11434"
SMOKE_EXCERPT = "Record excerpt:\nThe build passed on runner r3.\n\nQuestion: What time did the build pass?"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def canonical_sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


def die(msg, code=2):
    print(f"probe_cells: REFUSED: {msg}", flush=True)
    sys.exit(code)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name.replace("'", "p"))


def user_env(name: str) -> str:
    """A User-scope environment variable, read from the registry: the seat's NATS credentials are set with
    setx and are not in every shell that starts this script."""
    if os.environ.get(name):
        return os.environ[name]
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
        try:
            return winreg.QueryValueEx(k, name)[0]
        except FileNotFoundError:
            die(f"{name} is not set in the User environment")


# ---------------------------------------------------------------- config, cells, items

def load_cfg(require_filled=True) -> dict:
    c = json.loads(CFG.read_text(encoding="utf-8"))
    if require_filled:
        fills = [k for k, v in _walk(c) if isinstance(v, str) and v.startswith("FILL")]
        if fills:
            die(f"config still has FILL in: {', '.join(fills)}")
    return c


def _walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, o


def load_cells(c: dict) -> dict:
    p = HERE / c["probe_cells"]["path"]
    got = sha(p)
    if got != c["probe_cells"]["sha256"]:
        die(f"{p} hashes to {got[:12]}, not the pinned {c['probe_cells']['sha256'][:12]}")
    return json.loads(p.read_text(encoding="utf-8"))


def load_items(c: dict, cells: dict) -> dict:
    """{set: {"path", "raw_sha256", "canonical_sha256", "items"}}, every hash checked against the cells file."""
    out = {}
    for s, spec in cells["items"].items():
        p = (HERE / c["probe"]["items"][spec["file"]]).resolve()
        d = json.loads(p.read_text(encoding="utf-8"))
        items = d["items"] if isinstance(d, dict) else d
        canon = canonical_sha(d)
        if canon != spec["sha256"]:
            die(f"{p} canonical sha256 {canon[:12]} is not the registered {spec['sha256'][:12]} for set {s}")
        for it in items:
            it.setdefault("expected", it.get("gold") if it["kind"] == "present" else "")
        out[s] = {"path": str(p), "raw_sha256": sha(p), "canonical_sha256": canon, "items": items}
    return out


def tags_for(c: dict, run: str, run_records: dict) -> dict:
    """{"production": tag, "serve": tag} for a run: P and REF from the config, c1 runs by the naming rule."""
    if run in c["probe"]["tags"]:
        return dict(c["probe"]["tags"][run])
    base = "kannaka-brain-c1-" + safe(run).lower()
    return {"production": base, "serve": base + "-serve"}


def ollama_tags() -> dict:
    with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=30) as r:
        return {m["name"].removesuffix(":latest"): m["digest"][:12] for m in json.load(r)["models"]}


def ollama_loaded() -> list:
    """What Ollama has in memory right now: name, digest and the context length the runner was built with."""
    with urllib.request.urlopen(OLLAMA + "/api/ps", timeout=30) as r:
        return [{"name": m["name"], "digest": m["digest"][:12], "context_length": m.get("context_length")}
                for m in json.load(r)["models"]]


def unload_all():
    """Ollama reuses a loaded runner across tags that share a GGUF blob (measured 2026-10-07: a serve session on
    kannaka-brain-7b-v2-serve was answered by the runner the bare cells had loaded as kannaka-brain-7b-v2, and
    `ollama ps` kept the first name). So every cell group starts from an empty Ollama, and the tag that loads
    is the one the cell asked for, at the context length its Modelfile or request set."""
    for m in ollama_loaded():
        subprocess.run(["ollama", "stop", m["name"]], capture_output=True, text=True)
    for _ in range(15):
        if not ollama_loaded():
            return
        time.sleep(1)
    die(f"ollama still has models loaded after stop: {ollama_loaded()}")


def loaded_gate(tag: str, num_ctx: int, label: str) -> list:
    loaded = ollama_loaded()
    ok = len(loaded) == 1 and loaded[0]["name"] == f"{tag}:latest" and loaded[0]["context_length"] == num_ctx
    if not ok:
        die(f"{label}: Ollama should hold exactly {tag}:latest at context {num_ctx}, holds {loaded}")
    return loaded


# ---------------------------------------------------------------- tags

def production_modelfile(c: dict) -> str:
    """The production Modelfile, verbatim from the tag P runs on, minus its FROM line."""
    src = c["probe"]["modelfile_source_tag"]
    r = subprocess.run(["ollama", "show", src, "--modelfile"], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        die(f"ollama show {src} --modelfile failed: {r.stderr[-200:]}")
    lines = [l for l in r.stdout.splitlines() if not l.startswith("#") and not l.startswith("FROM ")]
    text = "\n".join(lines).strip() + "\n"
    if "PARAMETER temperature 0.8" not in text or "PARAMETER num_ctx 4096" not in text:
        die(f"{src}'s Modelfile is not the production one (0.8/4096): {text[:200]!r}")
    return text


def serve_modelfile(prod: str) -> str:
    """E5's -serve variant: the production Modelfile with 0.2/8192 in place of 0.8/4096, nothing else changed."""
    s = prod.replace("PARAMETER temperature 0.8", "PARAMETER temperature 0.2").replace("PARAMETER num_ctx 4096",
                                                                                      "PARAMETER num_ctx 8192")
    if s == prod:
        die("serve Modelfile would equal the production one")
    return s


def cmd_build_tags(a):
    c = load_cfg(require_filled=False)
    prod = production_modelfile(c)
    variants = {"production": prod, "serve": serve_modelfile(prod)}
    have = ollama_tags()
    built = {}
    for name, rec in sorted(_run_records().items()):
        if a.only and name not in a.only:
            continue
        if rec.get("exit") != 0 or not rec.get("gguf_sha256"):
            print(f"probe_cells: {name}: no merged gguf in its record; skipped", flush=True)
            continue
        gguf = Path(rec["merge"]["gguf"])
        got = sha(gguf)
        if got != rec["gguf_sha256"]:
            die(f"{gguf} hashes to {got[:12]}, not the recorded {rec['gguf_sha256'][:12]}")
        for kind, tag in tags_for(c, name, {}).items():
            if tag in have:
                print(f"probe_cells: {tag} exists ({have[tag]}); not rebuilt", flush=True)
                continue
            mf = HERE / f"{safe(tag)}.Modelfile"
            mf.write_text(f"FROM {gguf}\n" + variants[kind], encoding="utf-8")
            r = subprocess.run(["ollama", "create", tag, "-f", str(mf)], capture_output=True, text=True)
            if r.returncode != 0:
                die(f"ollama create {tag} failed: {r.stderr[-300:]}")
            built[tag] = {"run": name, "kind": kind, "gguf": str(gguf), "gguf_sha256": got,
                          "modelfile_sha256": hashlib.sha256(mf.read_bytes()).hexdigest(),
                          "digest": ollama_tags().get(tag), "built": now()}
            print(f"probe_cells: built {tag} ({built[tag]['digest']}) from {gguf.name}", flush=True)
        rec.setdefault("tags", {}).update({k: v for k, v in built.items() if v["run"] == name})
        (RUNS / f"{name}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- records, ledger

def _run_records() -> dict:
    RUNS.mkdir(exist_ok=True)
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in RUNS.glob("*.json")}


def cell_records() -> dict:
    CELLS.mkdir(parents=True, exist_ok=True)
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in CELLS.glob("*.json")}


def ledger_gate(c: dict):
    train = sum(r.get("seconds", 0) for r in _run_records().values())
    cells = [r.get("seconds", 0) for r in cell_records().values()]
    spent = (train + sum(cells)) / 3600
    slowest = max(cells or [0]) / 3600
    cap = c["gpu_hours_cap_total"]
    if spent + slowest > cap:
        die(f"hour ledger: {train / 3600:.1f} h training + {sum(cells) / 3600:.1f} h cells = {spent:.1f} h, "
            f"slowest cell {slowest:.2f} h, total cap {cap} h", 5)
    return round(spent, 3)


# ---------------------------------------------------------------- asking

def ask_bare(tag: str, item: dict, temp: float, num_ctx: int, seed: int) -> str:
    body = json.dumps({"model": tag, "stream": False,
                       "options": {"temperature": temp, "num_ctx": num_ctx, "seed": seed},
                       "messages": [{"role": "system", "content": brain_probe.SYSTEM_A},
                                    {"role": "user", "content": brain_probe.prompt_text(item)}]}).encode()
    req = urllib.request.Request(OLLAMA + "/api/chat", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r)["message"]["content"]
    except Exception as e:  # recorded as an [error] row; the cell's gate counts it
        return f"[error] {type(e).__name__}: {str(e)[:200]}"


async def ask_serve(nc, subject: str, frm: str, text: str) -> str:
    payload = json.dumps({"from": frm, "text": text, "mode": "no_recall"}).encode()
    try:
        r = await nc.request(subject, payload, timeout=180)
        d = json.loads(r.data)
        return d.get("text") or f"[error] {d.get('error')}"
    except Exception as e:
        return f"[error] {type(e).__name__}: {str(e)[:200]}"


class ServeSession:
    """One kannaka swarm serve on a frozen data dir, with E5's gates around it."""

    def __init__(self, c: dict, tag: str, label: str, num_ctx: int, subject: str = None):
        self.c, self.tag, self.label, self.num_ctx = c, tag, label, num_ctx
        self.p = c["probe"]
        self.subject = subject or self.p["ask_subject"]   # the subject this serve answers on; the log gate reads it
        self.data = Path(self.p["serve_data_dir"])
        self.bin = Path(self.p["serve_bin"])
        self.out = LOGS / f"c1-{safe(label)}.out.log"
        self.err = LOGS / f"c1-{safe(label)}.err.log"
        self.proc = None
        self.record = {"tag": tag, "serve_bin": str(self.bin), "data_dir": str(self.data)}

    def _grep(self, pat: str) -> list:
        if not self.err.exists():
            return []
        return [l for l in self.err.read_text(encoding="utf-8", errors="replace").splitlines() if pat in l]

    def start(self):
        got = sha(self.bin)
        if got != self.p["serve_bin_sha256"]:
            die(f"serve binary {self.bin} hashes to {got[:12]}, not the pinned {self.p['serve_bin_sha256'][:12]}")
        self.record["serve_bin_sha256"] = got
        self.record["serve_version"] = subprocess.run([str(self.bin), "--version"], capture_output=True,
                                                      text=True).stdout.strip().splitlines()[0]
        live = Path.home() / ".kannaka"
        if self.data.resolve() == live.resolve():
            die("the serve data dir must be a frozen copy, never the live ~/.kannaka")
        if not (self.data / "kannaka.hrm").exists():
            self.data.mkdir(parents=True, exist_ok=True)
            for f in live.iterdir():
                if f.is_file() and ".bak" not in f.name:
                    shutil.copy2(f, self.data / f.name)
            print(f"probe_cells: froze {live} -> {self.data}", flush=True)
        self.record["hrm_sha256_before"] = sha(self.data / "kannaka.hrm")
        cfg = self.data / "config.toml"
        text = cfg.read_text(encoding="utf-8")
        new, n = re.subn(r'(?m)^model = "[^"]*"', f'model = "{self.tag}"', text, count=1)
        if n != 1:
            die(f"{cfg} has no [llm] model line to set")
        cfg.write_text(new, encoding="utf-8")
        if f'model = "{self.tag}"' not in cfg.read_text(encoding="utf-8"):
            die("config did not take the tag")
        if self.tag not in ollama_tags():
            die(f"ollama has no tag {self.tag}")
        unload_all()
        self.record["ollama_loaded_before"] = []
        env = dict(os.environ, KANNAKA_DATA_DIR=str(self.data), KANNAKA_SERVE_PROMPT_ARM="baseline",
                   KANNAKA_SERVE_ASKS_PER_HOUR_TOTAL=str(self.p["asks_per_hour_total"]), PYTHONIOENCODING="utf-8",
                   NATS_USER=user_env("NATS_USER"), NATS_PASSWORD=user_env("NATS_PASSWORD"),
                   KANNAKA_NATS_URL=user_env("KANNAKA_NATS_URL"))
        for p in (self.out, self.err):
            if p.exists():
                p.unlink()
        LOGS.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen([str(self.bin), "swarm", "serve", "--threshold", str(self.p["broadcast_threshold"])],
                                     env=env, stdout=open(self.out, "w"), stderr=open(self.err, "w"),
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        arm = limit = sub = None
        for _ in range(60):
            time.sleep(2)
            arm = arm or next(iter(self._grep("[swarm serve] prompt arm:")), None)
            limit = limit or next(iter(self._grep("rate limit:")), None)
            sub = sub or next(iter(self._grep(f"subscribing to {self.subject}")), None)
            if arm and limit and sub:
                break
            if self.proc.poll() is not None:
                break
        if arm != "[swarm serve] prompt arm: baseline":
            self.stop(); die(f"{self.label}: serve log says {arm!r}, not the baseline arm")
        if not limit or f"{self.p['asks_per_hour_total']}/hour total" not in limit:
            self.stop(); die(f"{self.label}: total limit not raised: {limit!r}")
        if not sub:
            self.stop(); die(f"{self.label}: serve never subscribed")
        self.record.update({"arm_line": arm, "limit_line": limit, "started": now()})

    async def smoke(self, nc):
        ans = await ask_serve(nc, self.subject, f"{safe(self.label)}-smoke", SMOKE_EXCERPT)
        if ans.startswith("[error]"):
            self.stop(); die(f"{self.label}: smoke ask failed: {ans}")
        try:
            self.record["ollama_loaded_after_smoke"] = loaded_gate(self.tag, self.num_ctx, self.label)
        except SystemExit:
            self.stop(); raise
        self.record["smoke_answer"] = ans[:200]

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None and not self._grep("restarting to serve the fresh mind")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=30)
        time.sleep(2)

    def close(self, expected_asks: int):
        ok = self.alive()
        self.stop()
        directed = len(self._grep("directed from probe-"))
        self.record.update({"directed_asks": directed, "expected_asks": expected_asks, "alive_at_end": ok,
                            "hrm_sha256_after": sha(self.data / "kannaka.hrm"), "stopped": now()})
        self.record["gates"] = {"asks_exact": directed == expected_asks, "no_restart": ok,
                                "snapshot_unchanged": self.record["hrm_sha256_after"] == self.record["hrm_sha256_before"]}
        return self.record


# ---------------------------------------------------------------- cells

def plan(c: dict, cells: dict, only, smoke: bool) -> list:
    """Sessions in the frozen order: one per (run, cell kind), both sets inside it."""
    order = [m.strip() for m in cells["order"].split(":")[-1].split(",")]
    by = {}
    for cell in cells["cells"]:
        if only and cell["cell_id"] not in only:
            continue
        if smoke and cell["run"] != "P":
            continue
        by.setdefault((cell["run"], cell["cell"]), []).append(cell)
    kinds = ["bare", "serve", "production"]
    seq = []
    for run in order:
        for k in kinds:
            if (run, k) in by:
                seq.append((run, k, sorted(by[(run, k)], key=lambda x: x["set"])))
    return seq


INSTRUMENT_AUTHOR = "flaukowski"   # KSHB rev 1: every metric names who wrote the instrument that produced it


def log_gates(log_text: str, expected_asks, limit: int) -> dict:
    """The serve-log half of E5's gates, computed from the text of the serve's err log. Used on the local
    session and on an operator-supplied log alike, so the two modes are judged by one function."""
    lines = log_text.splitlines()
    arm = next((l for l in lines if "[swarm serve] prompt arm:" in l), None)
    lim = next((l for l in lines if "rate limit:" in l), None)
    sub = any("subscribing to KANNAKA.ask." in l for l in lines)
    directed = sum(1 for l in lines if "directed from probe-" in l)
    restarted = any("restarting to serve the fresh mind" in l for l in lines)
    return {"arm_line": arm, "limit_line": lim, "directed_asks": directed,
            "gates": {"arm_baseline": arm == "[swarm serve] prompt arm: baseline",
                      "limit_raised": bool(lim) and f"{limit}/hour total" in lim,
                      "subscribed": sub,
                      "asks_exact": (directed == expected_asks) if expected_asks is not None else None,
                      "no_restart": not restarted}}


def operator_record_gates(orec: dict) -> dict:
    """The operator-half gates from an operator record (written by `operator-serve`, or by another driver that
    emits the same fields): the frozen data dir unchanged, serve alive at close, the right tag loaded at the
    right context after the smoke ask."""
    hb, ha = orec.get("hrm_sha256_before"), orec.get("hrm_sha256_after")
    loaded = orec.get("ollama_loaded_after_smoke") or []
    tag, ctx = orec.get("tag"), orec.get("num_ctx")
    return {"snapshot_unchanged": bool(hb) and hb == ha,
            "alive_at_close": bool(orec.get("alive_at_end")),
            "loaded_exactly_this_tag": len(loaded) == 1 and loaded[0].get("name") == f"{tag}:latest"
                                       and loaded[0].get("context_length") == ctx}


def cmd_operator_serve(a):
    """The session half, for the operator of a serve the asker does not control: start the serve on a frozen data
    dir, pass the log gates, answer the smoke ask, hold until --minutes elapse or the stop file appears, close,
    and write the operator record (plus a copy of the err log) that `attach` or `run --external` consumes."""
    c = load_cfg(require_filled=False)
    session = ServeSession(c, a.tag, a.label or f"operator-{safe(a.tag)}", a.num_ctx, a.ask_subject)
    session.start()
    nc = _Loop().run(_connect(c))
    try:
        _Loop().run(session.smoke(nc))
    finally:
        _Loop().run(nc.close())
    out = Path(a.out)
    stop = Path(str(out) + ".stop")
    print(f"probe_cells: operator-serve: {a.tag} up at ctx {a.num_ctx}; serving until {a.minutes} min pass or "
          f"{stop} exists", flush=True)
    t0 = time.time()
    while time.time() - t0 < a.minutes * 60 and not stop.exists():
        if not session.alive():
            break
        time.sleep(5)
    rec = session.close(None)
    rec.update({"tag": a.tag, "num_ctx": a.num_ctx, "operator": a.operator, "instrument_author": INSTRUMENT_AUTHOR,
                "mode": "operator-serve", "err_log_copy": str(out) + ".err.log"})
    shutil.copy2(session.err, rec["err_log_copy"])
    out.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(f"probe_cells: operator record -> {out} (directed asks seen: {rec['directed_asks']}, alive at close: "
          f"{rec['alive_at_end']}, snapshot unchanged: {rec['gates']['snapshot_unchanged']})", flush=True)


def finalize(cell_ids: list, orec_path: Path, log_path: Path, limit: int):
    """Join an operator record and its err log to asker records that are waiting on them, recompute the gates
    and the exit, and rewrite each record. Refuses a record that is not waiting."""
    orec = json.loads(Path(orec_path).read_text(encoding="utf-8"))
    log_text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    done = cell_records()
    expected = sum(done[safe(cid)]["asks"] for cid in cell_ids if safe(cid) in done)
    lg = log_gates(log_text, expected, limit)
    og = operator_record_gates(orec)
    for cid in cell_ids:
        rec = done.get(safe(cid))
        if not rec:
            die(f"{cid}: no asker record to attach to")
        if rec.get("serve") not in (None, "pending-operator-record"):
            die(f"{cid}: its record already carries a serve block; not overwriting")
        if orec.get("tag") != rec["tag"]:
            die(f"{cid}: operator record is for tag {orec.get('tag')}, the cell asked {rec['tag']}")
        gates = dict(rec["gates"]); gates.update(lg["gates"]); gates.update(og)
        rec.update({"serve": {**{k: v for k, v in orec.items() if k != "gates"}, "log_sha256": sha(Path(log_path)),
                              "operator_record": str(orec_path), "arm_line": lg["arm_line"], "limit_line": lg["limit_line"],
                              "directed_asks_in_log": lg["directed_asks"], "expected_asks_in_session": expected},
                    "gates": gates, "exit": 0 if all(gates.values()) else 3,
                    "outcome": "measured" if all(gates.values()) else
                    "failed its gates: " + ", ".join(k for k, v in gates.items() if not v),
                    "finalized_at": now()})
        (CELLS / f"{safe(cid)}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        print(f"probe_cells: {cid}: {rec['outcome']}", flush=True)
    bad = [cid for cid in cell_ids if done.get(safe(cid), {}).get("exit") not in (0, None)]
    return bad


def cmd_attach(a):
    global CELLS
    if a.smoke:
        CELLS = Path(os.environ.get("C1_SMOKE_DIR", str(CELLS / "smoke")))
    c = load_cfg(require_filled=False)
    bad = finalize(a.cells, Path(a.operator_record), Path(a.serve_log), c["probe"]["asks_per_hour_total"])
    if bad:
        die(f"{', '.join(bad)} failed their gates after attach; rows kept; re-run from scratch per section 2.6", 3)


def cmd_run(a):
    c = load_cfg(require_filled=not a.smoke)
    cells = load_cells(c)
    items = load_items(c, cells)
    have = ollama_tags() if not a.external else {}
    external = bool(a.external)
    subject = a.ask_subject or c["probe"]["ask_subject"]
    global CELLS
    if a.smoke:
        CELLS = Path(os.environ.get("C1_SMOKE_DIR", str(CELLS / "smoke")))
        CELLS.mkdir(parents=True, exist_ok=True)
        print(f"probe_cells: SMOKE: 1 item x 1 sample per cell kind on P, records in {CELLS}", flush=True)
    if external:
        if a.only is None:
            die("--external runs one serve session's cells: name them with --only")
        print(f"probe_cells: EXTERNAL serve: asking {subject} as {INSTRUMENT_AUTHOR}; the operator's record and log "
              f"finalize the gates ({'now' if a.operator_record else 'later, via attach'})", flush=True)
    import nats
    for run, kind, group in plan(c, cells, a.only, a.smoke):
        tag = tags_for(c, run, {})["serve" if kind == "serve" else "production"]
        if external and kind == "bare":
            die("bare cells need the model's Ollama; run them on the serving host, not --external")
        if not external and tag not in have:
            die(f"{run}/{kind}: ollama has no tag {tag} (build-tags first)")
        label = f"{run}-{kind}"
        done = cell_records()
        pending = [cell for cell in group if safe(cell["cell_id"]) not in done]
        if not pending:
            print(f"probe_cells: {label}: every cell has a record; skipped", flush=True)
            continue
        for cell in pending:
            rows = CELLS / f"{safe(cell['cell_id'])}.jsonl"
            if rows.exists():
                rec = {"cell_id": cell["cell_id"], "exit": None, "seconds": 0,
                       "outcome": "interrupted: a cell started and left no record", "traces": [str(rows)],
                       "recorded_at": now()}
                (CELLS / f"{safe(cell['cell_id'])}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
                die(f"{cell['cell_id']} started and left no record ({rows}); failure record written; inspect, then "
                    "delete the rows and the record by hand to redo it", 6)
        spent = ledger_gate(c)
        n_items = 1 if a.smoke else None
        n_samples = 1 if a.smoke else None
        session = None
        nc = None
        cell_ctx = 8192 if kind == "bare" else pending[0]["num_ctx"]
        if kind != "bare" and not external:
            session = ServeSession(c, tag, label, cell_ctx, subject)
            session.start()
        elif kind == "bare":
            unload_all()
        digest = have.get(tag) if not external else (a.model_digest or "operator-record")
        try:
            if session:
                nc = _Loop().run(_connect(c))
                _Loop().run(session.smoke(nc))
            elif external:
                nc = _Loop().run(_connect(c))
                smoke = _Loop().run(ask_serve(nc, subject, f"{safe(label)}-smoke", SMOKE_EXCERPT))
                if smoke.startswith("[error]"):
                    die(f"{label}: smoke ask on {subject} failed: {smoke}")
            t0 = time.time()
            expected_total = 0
            cell_results = []
            for cell in pending:
                its = items[cell["set"]]["items"][:n_items] if n_items else items[cell["set"]]["items"]
                seeds = cell["sampling_seeds"][:n_samples] if n_samples else cell["sampling_seeds"]
                rows = CELLS / f"{safe(cell['cell_id'])}.jsonl"
                meta = {"meta": True, "cell_id": cell["cell_id"], "run": run, "set": cell["set"], "cell": kind,
                        "arm": cell["arm"], "tag": tag, "model_digest": digest, "temperature": cell["temperature"],
                        "num_ctx": cell["num_ctx"] if kind != "bare" else 8192,
                        "items_sha256": items[cell["set"]]["raw_sha256"],
                        "items_canonical_sha256": items[cell["set"]]["canonical_sha256"],
                        "items_file": items[cell["set"]]["path"], "sampling_seeds": seeds, "started": now(),
                        "prompt": cell["prompt"], "smoke": a.smoke, "ask_subject": subject if kind != "bare" else None,
                        "mode": "external-serve" if external else "local", "instrument_author": INSTRUMENT_AUTHOR}
                tc = time.time()
                n_err = 0
                with open(rows, "x", encoding="utf-8") as out:
                    out.write(json.dumps(meta, ensure_ascii=False) + "\n")
                    for it in its:
                        for s, seed in enumerate(seeds):
                            ta = time.time()
                            if kind == "bare":
                                ans = ask_bare(tag, it, cell["temperature"], 8192, seed)
                                seed_used = seed
                            else:
                                ans = _Loop().run(ask_serve(nc, subject, f"probe-{it['id']}",
                                                            brain_probe.prompt_text(it)))
                                seed_used = None
                            n_err += ans.startswith("[error]")
                            row = {"run": run, "set": cell["set"], "cell": kind, "cell_id": cell["cell_id"],
                                   "arm": "A" if kind == "bare" else "B", "temp": cell["temperature"],
                                   "num_ctx": meta["num_ctx"], "item": it["id"], "kind": it["kind"], "sample": s,
                                   "sampling_seed": seed_used, "serve_tag": tag if kind != "bare" else None,
                                   "bare_tag": tag if kind == "bare" else None, "model_digest": digest,
                                   "secs": round(time.time() - ta, 2), "answer": ans, **brain_probe.pregrade(it, ans)}
                            out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
                asks = len(its) * len(seeds)
                expected_total += asks
                cell_results.append((cell, rows, asks, n_err, round(time.time() - tc)))
                print(f"probe_cells: {cell['cell_id']}: {asks} asks, {n_err} [error], {round(time.time() - tc) / 60:.1f} min",
                      flush=True)
        finally:
            srec = session.close(expected_total) if session else None
            if nc:
                _Loop().run(nc.close())
        loaded = ollama_loaded() if not external else None
        bare_loaded_ok = (kind != "bare") or (len(loaded) == 1 and loaded[0]["name"] == f"{tag}:latest"
                                              and loaded[0]["context_length"] == cell_ctx)
        for cell, rows, asks, n_err, secs in cell_results:
            gates = {"asks_exact": asks == (len(cell["sampling_seeds"]) * len(items[cell["set"]]["items"]) if not a.smoke else asks),
                     "no_error_answers": n_err == 0}
            if kind == "bare":
                gates["loaded_exactly_this_tag"] = bare_loaded_ok
            if srec:
                gates.update(srec["gates"])
            pending_op = external and not a.operator_record
            # The hour ledger (ledger_gate, run_c1's cap) sums `seconds` as GPU time on this desktop. An external
            # cell burns none of this card, so it charges 0 and keeps its wall clock in wall_seconds_remote.
            rec = {"cell_id": cell["cell_id"], "run": run, "set": cell["set"], "cell": kind, "tag": tag,
                   "model_digest": digest, "asks": asks, "error_answers": n_err,
                   "seconds": 0 if external else secs, "wall_seconds_remote": secs if external else None,
                   "rows": str(rows), "rows_sha256": sha(rows),
                   "serve": "pending-operator-record" if pending_op else srec, "ollama_loaded_after": loaded,
                   "mode": "external-serve" if external else "local", "ask_subject": subject if kind != "bare" else None,
                   "instrument_author": INSTRUMENT_AUTHOR, "gates": gates,
                   "exit": None if pending_op else (0 if all(gates.values()) else 3),
                   "outcome": "asked; gates wait on the operator record" if pending_op else
                   ("measured" if all(gates.values()) else "failed its gates: " + ", ".join(k for k, v in gates.items() if not v)),
                   "hours_spent_before": spent, "smoke": a.smoke, "recorded_at": now()}
            (CELLS / f"{safe(cell['cell_id'])}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
            print(f"probe_cells: {cell['cell_id']}: {rec['outcome']}", flush=True)
            if rec["exit"] == 3:
                die(f"{cell['cell_id']} failed its gates; rows kept at {rows}; re-run from scratch per section 2.6 "
                    "and keep this first attempt on the record", 3)
        if external and a.operator_record:
            bad = finalize([cell["cell_id"] for cell, *_ in cell_results], Path(a.operator_record), Path(a.serve_log),
                           c["probe"]["asks_per_hour_total"])
            if bad:
                die(f"{', '.join(bad)} failed their gates on the operator record; rows kept", 3)


class _Loop:
    """One event loop for the whole process (nats connections must stay on the loop that opened them)."""
    loop = None

    def run(self, coro):
        if _Loop.loop is None:
            _Loop.loop = asyncio.new_event_loop()
        return _Loop.loop.run_until_complete(coro)


async def _connect(c: dict):
    import nats
    return await nats.connect(c["probe"]["nats_url"], user=user_env("NATS_USER"), password=user_env("NATS_PASSWORD"))


def cmd_check(a):
    c = load_cfg(require_filled=False)
    cells = load_cells(c)
    items = load_items(c, cells)
    have = ollama_tags()
    p = c["probe"]
    got = sha(Path(p["serve_bin"]))
    if got != p["serve_bin_sha256"]:
        die(f"serve binary hashes to {got[:12]}, not the pinned {p['serve_bin_sha256'][:12]}")
    runs = sorted({cell["run"] for cell in cells["cells"]})
    missing = []
    for run in runs:
        for kind, tag in tags_for(c, run, {}).items():
            if tag not in have:
                missing.append(f"{run}/{kind}={tag}")
    production_modelfile(c)
    n = len(cells["cells"])
    asks = sum(cell["asks"] for cell in cells["cells"])
    print(f"probe_cells: cells file ok ({n} cells, {asks} asks); items v1 {items['v1']['canonical_sha256'][:12]} "
          f"v2 {items['v2']['canonical_sha256'][:12]}; serve bin {got[:12]}; "
          f"tags present for {len(runs) * 2 - len(missing)}/{len(runs) * 2}"
          + (f"; MISSING (build-tags after merge): {', '.join(missing)}" if missing else ""))
    print(f"probe_cells: hour ledger: {ledger_gate(c)} h spent of {c['gpu_hours_cap_total']}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("check")
    b = sp.add_parser("build-tags"); b.add_argument("--only", nargs="*")
    r = sp.add_parser("run"); r.add_argument("--only", nargs="*"); r.add_argument("--smoke", action="store_true")
    r.add_argument("--external", action="store_true",
                   help="ask a serve someone else operates: no session here; gates come from the operator record")
    r.add_argument("--ask-subject", help="the serve's ask subject (default: probe.ask_subject in the config)")
    r.add_argument("--model-digest", help="the tag's Ollama digest as the operator reports it (external only)")
    r.add_argument("--operator-record", help="finalize now with this operator record (external only)")
    r.add_argument("--serve-log", help="the operator's serve err log, with --operator-record")
    o = sp.add_parser("operator-serve", help="the session half, run by the serve's operator")
    o.add_argument("--tag", required=True); o.add_argument("--num-ctx", type=int, required=True)
    o.add_argument("--minutes", type=float, default=240); o.add_argument("--out", required=True)
    o.add_argument("--label"); o.add_argument("--operator", default="")
    o.add_argument("--ask-subject", help="the subject this serve answers on (default: probe.ask_subject)")
    t = sp.add_parser("attach", help="join an operator record and log to asker records that wait on them")
    t.add_argument("--cells", nargs="+", required=True); t.add_argument("--operator-record", required=True)
    t.add_argument("--serve-log", required=True); t.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    {"check": cmd_check, "build-tags": cmd_build_tags, "run": cmd_run, "operator-serve": cmd_operator_serve,
     "attach": cmd_attach}[a.cmd](a)


if __name__ == "__main__":
    main()
