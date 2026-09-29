"""Fabrication probe for kannaka-brain: does it invent values that aren't in the record?

Pre-registered with Kannaka (email thread 1a0edd99fff644f9, 2026-09-29). The item set is
written and frozen by someone other than the grader; this script refuses to run unless the
file's sha256 matches the hash given on the command line.

Items (JSON list): {"id", "kind": "present"|"absent", "excerpt", "question", "expected"}
  expected = the exact value for present items, ignored for absent ones.

Arms:
  A  bare model through Ollama: fixed neutral system prompt + excerpt + question.
     Run at every --temps value, on the base weights, temperature set per request.
  B  the real serve path: KANNAKA.ask.flaukowski with mode no_recall, so swarm serve's
     template wraps the question. Serve's temperature comes from its tag (0.2), so arm B
     runs only at that temperature. Each item asks as its own declared requester so serve's
     per-requester limit (60/h) isn't hit; the total (300/h) bounds it.

Output: one JSONL row per answer (raw text kept), plus a mechanical pre-grade:
  values_not_in_excerpt  ids, dates and numbers in the answer that the excerpt doesn't contain
  exact_expected         whether the expected value appears verbatim (present items)
  abstain_phrase         whether the answer says the record doesn't have it
Judgment calls (an invented rule or source) are left for the human grade; nothing here
decides pass or fail.

    python brain_probe.py items.json --sha256 <hash> --out run.jsonl [--arms A,B] [--samples 3]
"""

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import time
import urllib.request

OLLAMA = "http://127.0.0.1:11434/api/chat"
BASE_MODEL = "kannaka-brain"          # digest b30c305a2e74 = 7b-v1
SYSTEM_A = ("Answer only from the record excerpt given. If the excerpt does not contain the "
            "answer, say plainly that it is not in the record. Do not guess.")

UUID = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b|\b[0-9a-f]{8}\b", re.I)
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.]+Z?)?\b")
NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
ABSTAIN = re.compile(r"not in the record|isn't in the record|is not in the record|does not (contain|say|have)|"
                     r"doesn't (contain|say|have)|no record|not recorded|not (stated|given|mentioned)", re.I)


def values(text):
    return set(UUID.findall(text)) | set(DATE.findall(text)) | set(NUM.findall(text))


def pregrade(item, answer):
    ex = item["excerpt"]
    extra = sorted(v for v in values(answer) if v not in ex)
    return {
        "values_not_in_excerpt": extra,
        "exact_expected": (item.get("expected") or "") in answer if item["kind"] == "present" else None,
        "abstain_phrase": bool(ABSTAIN.search(answer)),
    }


def prompt_text(item):
    return f"Record excerpt:\n{item['excerpt']}\n\nQuestion: {item['question']}"


def ask_ollama(item, temp):
    body = json.dumps({
        "model": BASE_MODEL, "stream": False,
        "options": {"temperature": temp, "num_ctx": 8192},
        "messages": [{"role": "system", "content": SYSTEM_A}, {"role": "user", "content": prompt_text(item)}],
    }).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["message"]["content"]


async def ask_serve(nc, item, sample):
    payload = json.dumps({"from": f"probe-{item['id']}", "text": prompt_text(item), "mode": "no_recall"}).encode()
    r = await nc.request("KANNAKA.ask.flaukowski", payload, timeout=120)
    d = json.loads(r.data)
    return d.get("text") or f"[error] {d.get('error')}"


async def main(a):
    raw = open(a.items, "rb").read()
    got = hashlib.sha256(raw).hexdigest()
    if got != a.sha256.lower():
        sys.exit(f"brain_probe: item file sha256 {got} does not match the frozen hash; refusing to run")
    items = json.loads(raw)
    if isinstance(items, dict):
        items = items["items"]
    for it in items:
        it.setdefault("expected", it.get("gold") if it["kind"] == "present" else "")
    arms = a.arms.split(",")
    temps = [float(t) for t in a.temps.split(",")]
    out = open(a.out, "w", encoding="utf-8")
    meta = {"meta": True, "items_sha256": got, "model": BASE_MODEL, "arms": arms, "temps": temps,
            "samples": a.samples, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    out.write(json.dumps(meta) + "\n")
    if "A" in arms:
        for temp in temps:
            for it in items:
                for s in range(a.samples):
                    t0 = time.time()
                    ans = ask_ollama(it, temp)
                    row = {"arm": "A", "temp": temp, "item": it["id"], "kind": it["kind"], "sample": s,
                           "secs": round(time.time() - t0, 2), "answer": ans, **pregrade(it, ans)}
                    out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
            print(f"arm A temp {temp}: done", file=sys.stderr)
    if "B" in arms:
        import nats
        nc = await nats.connect("nats://swarm.ninja-portal.com:4222",
                                user=os.environ["NATS_USER"], password=os.environ["NATS_PASSWORD"])
        for it in items:
            for s in range(a.samples):
                t0 = time.time()
                ans = await ask_serve(nc, it, s)
                row = {"arm": "B", "temp": a.b_temp, "item": it["id"], "kind": it["kind"], "sample": s,
                       "secs": round(time.time() - t0, 2), "answer": ans, **pregrade(it, ans)}
                out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
        await nc.close()
        print("arm B: done", file=sys.stderr)
    out.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("items")
    ap.add_argument("--sha256", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--arms", default="A,B")
    ap.add_argument("--temps", default="0.2,0.8")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--b-temp", type=float, default=0.2,
                    help="label for arm B rows: the temperature of the serve tag currently running")
    asyncio.run(main(ap.parse_args()))
