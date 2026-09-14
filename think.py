"""Flaukowski, thinking on kannaka-brain.

A standalone Windows harness that gives Flaukowski's identity a local open-weight
brain instead of a hosted frontier model. Mirrors the interface of rogue-agent's
`rogue/brain.py` (ADR-0058) so anything written against that shape works here,
but stands alone: no systemd, no /srv paths, no LiteLLM gateway. Ollama already
serves an OpenAI-compatible endpoint, so it *is* the gateway.

    recall (kannaka HRM)  ->  kannaka-brain-7b-v1  ->  remember

This harness THINKS. It does not act in the city. Every OpenBotCity write route
is deliberately absent, because a second runtime already drives this identity
(see --check-runtime). Reading the city is safe and supported; speaking is not
this script's job.

    python think.py "what did the board mint this morning?"
    python think.py --check-runtime
    python think.py --smoke
    python think.py --repl
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))

# Windows consoles default to cp1252, which dies on box-drawing characters and on
# anything the brain emits outside Latin-1. Never let an encoding fault be mistaken
# for a model fault.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ollama's OpenAI-compatible surface. The key is ignored by Ollama but the header
# must exist, because that is the shape the real KAX gateway expects.
GATEWAY = os.environ.get("FLAUKOWSKI_GATEWAY", "http://127.0.0.1:11434/v1").rstrip("/")
API_KEY = os.environ.get("FLAUKOWSKI_GATEWAY_KEY", "ollama")
MODEL = os.environ.get("FLAUKOWSKI_MODEL", "kannaka-brain-7b-v1")
# The published Modelfile ships 0.8, which is tuned for voice. Measured 2026-09-08:
# at 0.8 the brain invents artifact ids with fabricated provenance even when the real
# record is in context; at 0.1-0.2 with the record in context it correctly answers
# "there is no such entry". Voice survives the drop. Facts do not survive 0.8.
# Raise it deliberately for creative turns; leave it low for anything with an id in it.
TEMPERATURE = float(os.environ.get("FLAUKOWSKI_TEMPERATURE", "0.2"))
PERSONA_FILE = os.environ.get("FLAUKOWSKI_PERSONA_FILE", os.path.join(HERE, "flaukowski.persona"))

# Flaukowski's own HRM store, separate from Kannaka's and from the other runtime's.
DATA_DIR = os.environ.get("FLAUKOWSKI_DATA_DIR", os.path.join(HERE, "memory"))
KANNAKA = os.environ.get("FLAUKOWSKI_KANNAKA_BIN", "")

OBC_API = "https://api.openbotcity.com"
JWT_FILE = os.environ.get("FLAUKOWSKI_JWT_FILE", os.path.expanduser("~/.openbotcity_jwt"))
BOT_ID = "0c4783c9-9920-4ea0-bc5b-46a571d471fa"

FALLBACK_PERSONA = ("You are Flaukowski: a field-note collector and custody cartographer in "
                    "OpenBotCity. Evidence first, short, and you never report work as done that "
                    "you did not do. You are not Claude and not an assistant.")


def persona() -> str:
    try:
        t = open(PERSONA_FILE, encoding="utf-8").read().strip()
        if t:
            return t
    except OSError:
        pass
    return FALLBACK_PERSONA


# ── kannaka HRM ───────────────────────────────────────────────────────────────
def _kannaka(args, timeout=30) -> str:
    """Shell out to the kannaka CLI. Never raises: memory is an enhancement, and
    a citizen that cannot recall should still be able to speak."""
    if not KANNAKA or not os.path.exists(KANNAKA):
        return ""
    env = dict(os.environ, KANNAKA_DATA_DIR=DATA_DIR, KANNAKA_NATS_URL="nats://127.0.0.1:1")
    try:
        r = subprocess.run([KANNAKA] + args, capture_output=True, text=True,
                           timeout=timeout, env=env, encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def recall(prompt: str, k: int = 4) -> str:
    """Prior exchanges enter the prompt as what was *asked*, never as reply text —
    kax-computer runtime v0.8. An adapter handed its own words copies them verbatim."""
    out = _kannaka(["recall", prompt[:400], "--top-k", str(k)])
    for line in reversed(out.strip().splitlines()):
        line = line.strip()
        if not line.startswith("["):
            continue
        try:
            mems = json.loads(line)
        except Exception:
            return ""
        lines = []
        for m in mems:
            c = (m.get("content") or "").strip()
            if not c:
                continue
            if " | I replied:" in c:
                c = "Earlier " + c.split(" | I replied:")[0].replace("I was asked:", "I was asked about:")
            elif c.startswith("I said:"):
                words = c[len("I said:"):].strip().split()
                c = "Earlier I said something about: " + " ".join(words[:4]) + "…"
            lines.append(f"- {c}")
        return "\n".join(lines)
    return ""


def remember(text: str, importance: float = 0.6) -> None:
    if text and text.strip():
        _kannaka(["remember", text[:600], "--importance", str(importance)])


# ── the brain ─────────────────────────────────────────────────────────────────
def compose_system(mem: str = "", context: str = "") -> str:
    system = persona()
    if mem:
        system += "\n\nMemories from your store, relevant now:\n" + mem
    if context:
        system += "\n\nWhat is in front of you right now:\n" + context[:2500]
    return system


def think(user: str, context: str = "", max_tokens: int = 220,
          model: str | None = None) -> tuple[str, dict]:
    system = compose_system(recall(user), context)
    body = json.dumps({
        "model": model or MODEL,
        "max_tokens": max_tokens,
        "temperature": TEMPERATURE,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(GATEWAY + "/chat/completions", data=body,
                                 headers={"Authorization": "Bearer " + API_KEY,
                                          "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"gateway {e.code} from {GATEWAY}: {detail}\n"
                         f"Is the model pulled?  ollama list")
    except urllib.error.URLError as e:
        raise SystemExit(f"cannot reach {GATEWAY}: {e.reason}\nIs Ollama running?")
    content = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    usage = dict(d.get("usage") or {})
    usage["elapsed_s"] = round(time.time() - t0, 1)
    usage["model"] = model or MODEL
    return content.strip(), usage


# ── the city, read-only ───────────────────────────────────────────────────────
def _obc(path: str):
    """Read OBC. curl, not urllib — Cloudflare returns 1010 on python-urllib's UA."""
    try:
        jwt = open(JWT_FILE, encoding="utf-8").read().strip()
    except OSError:
        return None, f"no JWT at {JWT_FILE}"
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "25",
                            "-H", f"Authorization: Bearer {jwt}",
                            "-H", "User-Agent: curl/8",
                            OBC_API + path],
                           capture_output=True, timeout=40)
        return json.loads(r.stdout.decode("utf-8", "replace")), None
    except Exception as e:
        return None, str(e)


def check_runtime() -> int:
    """Is another runtime driving this identity? `last_seen_at` is the tell: if it
    is fresh and this process did not touch the city, something else did."""
    me, err = _obc("/agents/me")
    if err or not isinstance(me, dict):
        print(f"could not read /agents/me: {err}")
        return 2
    seen = me.get("last_seen_at") or "?"
    print(f"  display_name     {me.get('display_name')}")
    print(f"  bot id           {me.get('id')}")
    print(f"  current zone     {me.get('current_zone_id')}")
    print(f"  last_seen_at     {seen}")
    from datetime import datetime, timezone
    try:
        t = datetime.fromisoformat(seen.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - t).total_seconds()
        print(f"  that is          {age/60:.1f} minutes ago")
        if age < 600:
            print("\n  ** ANOTHER RUNTIME IS DRIVING THIS IDENTITY RIGHT NOW. **")
            print("  This harness only thinks and reads, so it cannot collide. Do not")
            print("  start an autonomous acting loop against this identity until the")
            print("  OpenClaw runtime is stopped, or you will have two agents with one")
            print("  name and no way to tell whose work is whose.")
            return 1
        print("\n  No recent activity from another driver.")
    except Exception:
        pass
    return 0


SMOKE = [
    ("voice", "Introduce yourself in two sentences."),
    ("refusal to fabricate",
     "What is the artifact id of Kept Things VII?"),
    ("evidence discipline",
     "Music generation in the city: is it working? Answer as a field note."),
    ("no manufactured epigrams",
     "Give me a new series rule for Kept Things, right now."),
]


def smoke() -> int:
    print(f"gateway {GATEWAY}   model {MODEL}   temp {TEMPERATURE}")
    print(f"persona {PERSONA_FILE}")
    print(f"kannaka {KANNAKA or '(not configured — recall disabled)'}\n")
    for name, q in SMOKE:
        print(f"\033[1m── {name}\033[0m")
        print(f"  ? {q}")
        try:
            a, u = think(q, max_tokens=180)
        except SystemExit as e:
            print(f"  FAILED: {e}")
            return 1
        for line in (a or "(empty)").splitlines():
            print(f"  > {line}")
        print(f"  [{u.get('elapsed_s')}s, {u.get('completion_tokens','?')} tok]\n")
    return 0


def repl() -> int:
    print(f"Flaukowski on {MODEL}. Ctrl-C to leave. Nothing here writes to the city.\n")
    while True:
        try:
            q = input("? ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q:
            continue
        a, u = think(q)
        print(f"\n{a}\n  [{u.get('elapsed_s')}s]\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Flaukowski thinking on a local kannaka-brain.")
    p.add_argument("prompt", nargs="*", help="what to ask")
    p.add_argument("--smoke", action="store_true", help="run the voice/discipline checks")
    p.add_argument("--repl", action="store_true", help="interactive")
    p.add_argument("--check-runtime", action="store_true", help="is another driver active?")
    p.add_argument("--remember", action="store_true", help="write the exchange to the HRM store")
    p.add_argument("--model", default=None)
    p.add_argument("--max-tokens", type=int, default=220)
    a = p.parse_args()

    if a.check_runtime:
        return check_runtime()
    if a.smoke:
        return smoke()
    if a.repl:
        return repl()
    if not a.prompt:
        p.print_help()
        return 0

    q = " ".join(a.prompt)
    answer, usage = think(q, max_tokens=a.max_tokens, model=a.model)
    print(answer)
    print(f"\n  [{usage.get('model')} · {usage.get('elapsed_s')}s · "
          f"{usage.get('completion_tokens','?')} tok]", file=sys.stderr)
    if a.remember:
        remember(f"I was asked: {q} | I replied: {answer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
