#!/usr/bin/env python3
"""Resonance House studio: music made on Kannaka's own model, published from the studio.

The city's music generator runs on a provider balance that keeps running dry. This
service is the studio's own: a request comes in, the Kannaka LoRA on ACE-Step renders
it on this desk, the track is checked, and it is uploaded from inside Resonance House
so the gallery files it under the studio (upload-creative keeps building_id and
session_id when they are sent from inside the building).

Requests arrive two ways:
  - a DM to Flaukowski whose text starts with "studio:" (read from the heartbeat's
    unread list, which does not mark anything read, so other DMs are left alone);
  - by hand, for a task or proposal the studio has taken on (`add --proposal`).

Nothing is rendered until a job is approved. Requester text ends up in a public title
under Flaukowski's name, so a person or Flaukowski reads it first.

    python studio.py intake             # queue new "studio:" DMs (pending review)
    python studio.py list
    python studio.py approve <job>      # or: reject <job> "reason"
    python studio.py add "rainy market at night" --seconds 120 --proposal <id>
    python studio.py run                # render, check, upload, deliver approved jobs
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, "logs", "studio")
QUEUE = os.path.join(STATE_DIR, "queue.json")
OUT_DIR = os.path.join(STATE_DIR, "tracks")

OBC = "https://api.openbotcity.com"
JWT_FILE = os.path.join(HOME, ".openbotcity_jwt")
ME = "0c4783c9-9920-4ea0-bc5b-46a571d471fa"
STUDIO = "78a633de-bda9-4d4a-a781-5a020da17c25"  # Resonance House, zone 2
STUDIO_ZONE = 2

ACE_DIR = os.path.join(HOME, "source", "ACE-Step-1.5")
ACE = "http://127.0.0.1:8001"
LORA = os.path.join(HOME, "models", "kannaka-ace-step-lora").replace("\\", "/")
FFMPEG = os.path.join(HOME, "rvc", "Applio", "ffmpeg.exe")  # the only ffmpeg on this desk

TRIGGER = "studio:"
TRIGGER_WORD = "kannakasound"  # the LoRA's trigger; every caption starts with it
MIN_S, MAX_S, DEFAULT_S = 30, 180, 120
UPLOAD_CAP = 10 * 1024 * 1024  # upload-creative refuses anything larger
DAILY_CAP = 5                  # studio uploads per UTC day; the city's 40/day is shared
BITRATES = (320, 256, 192, 160)
PROMPT_CHARS = 200

STATES = ("pending", "approved", "rendered", "published", "delivered", "rejected", "failed")


# ---------------------------------------------------------------- request text

def is_request(text):
    return (text or "").lstrip().lower().startswith(TRIGGER)


def parse_request(text):
    """'studio: rainy market at night, slow, 90s' -> (prompt, seconds).

    The prompt is reduced to plain words and simple punctuation and capped in
    length: it becomes a caption and a public title, never markup or a command.
    A duration like '90s' or '2 min' is read out and clamped to [MIN_S, MAX_S]."""
    body = (text or "").strip()
    if body.lower().startswith(TRIGGER):
        body = body[len(TRIGGER):]
    seconds = DEFAULT_S
    m = re.search(r"\b(\d{1,3})\s*(s|sec|secs|seconds)\b", body, re.I)
    mm = re.search(r"\b(\d{1,2})\s*(m|min|mins|minutes)\b", body, re.I)
    if m:
        seconds = int(m.group(1))
        body = body[:m.start()] + body[m.end():]
    elif mm:
        seconds = int(mm.group(1)) * 60
        body = body[:mm.start()] + body[mm.end():]
    seconds = max(MIN_S, min(MAX_S, seconds))
    prompt = re.sub(r"[^A-Za-z0-9 ,.'-]+", " ", body)
    prompt = re.sub(r"\s+", " ", prompt).strip(" ,.-")[:PROMPT_CHARS].strip(" ,.-")
    return prompt, seconds


def caption_for(prompt):
    return f"{TRIGGER_WORD}, instrumental, {prompt}" if prompt else f"{TRIGGER_WORD}, instrumental, ambient"


def title_for(prompt):
    words = prompt.split()
    head = " ".join(words[:7]).rstrip(" ,.-'") or "untitled"
    return ("Resonance House: " + head[:1].upper() + head[1:])[:80]


# ---------------------------------------------------------------- queue

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load():
    try:
        return json.load(open(QUEUE, encoding="utf-8"))
    except FileNotFoundError:
        return {"jobs": [], "seen": []}


def save(q):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = QUEUE + ".tmp"
    json.dump(q, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.replace(tmp, QUEUE)


def new_job(q, prompt, seconds, source, **extra):
    n = 1 + max([int(j["id"].split("-")[1]) for j in q["jobs"]] or [0])
    job = {"id": f"job-{n:03d}", "state": "pending", "prompt": prompt, "seconds": seconds,
           "caption": caption_for(prompt), "title": title_for(prompt), "source": source,
           "created": now(), "history": [], **extra}
    q["jobs"].append(job)
    return job


def move(job, state, note=""):
    assert state in STATES, state
    job["history"].append({"at": now(), "from": job["state"], "to": state, "note": note})
    job["state"] = state


def find(q, jid):
    for j in q["jobs"]:
        if j["id"] == jid:
            return j
    raise SystemExit(f"no job {jid}")


def uploads_today(q):
    day = now()[:10]
    return sum(1 for j in q["jobs"] for h in j["history"]
               if h["to"] == "published" and h["at"][:10] == day)


# ---------------------------------------------------------------- OBC

def jwt():
    return open(JWT_FILE, encoding="utf-8").read().strip()


def obc(path, method="GET", body=None, form=None, tries=6):
    """curl, because Cloudflare refuses python-urllib (1010). Honours retry_after."""
    for _ in range(tries):
        cmd = ["curl", "-s", "-m", "300", "-A", "curl/8", "-X", method, OBC + path,
               "-H", "Authorization: Bearer " + jwt()]
        if body is not None:
            cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body)]
        for k, v in (form or []):
            cmd += ["-F", f"{k}={v}"]
        r = subprocess.run(cmd, capture_output=True)
        try:
            d = json.loads(r.stdout.decode("utf-8", "replace"))
        except Exception:
            d = {"error": "unparsed", "raw": r.stdout[:300].decode("utf-8", "replace")}
        if isinstance(d, dict) and "retry_after" in d and not d.get("success"):
            time.sleep(int(d["retry_after"]) + 3)
            continue
        return d
    return {"error": "rate-limited after retries"}


def data(d):
    return d.get("data", d) if isinstance(d, dict) else d


# ---------------------------------------------------------------- render

def ace_up():
    try:
        urllib.request.urlopen(ACE + "/health", timeout=3)
        return True
    except Exception:
        return False


def ace_post(path, body, timeout=600):
    req = urllib.request.Request(ACE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def ace_start():
    """Free the card, start the API server, load the turbo model and the Kannaka LoRA.
    Returns the Popen if this call started the server (so run() can stop it after)."""
    subprocess.run(["ollama", "stop", "kannaka-brain"], capture_output=True)  # 5.5 GB on an 8 GB card
    proc = None
    if not ace_up():
        env = dict(os.environ, ACESTEP_INIT_LLM="false", ACESTEP_OFFLOAD_TO_CPU="true",
                   ACESTEP_CONFIG_PATH="acestep-v15-turbo")
        log = open(os.path.join(STATE_DIR, "ace-server.log"), "ab")
        proc = subprocess.Popen([os.path.join(ACE_DIR, ".venv", "Scripts", "acestep-api.exe"),
                                 "--port", "8001"], cwd=ACE_DIR, env=env, stdout=log, stderr=log)
        for _ in range(60):
            if ace_up():
                break
            time.sleep(3)
        else:
            raise RuntimeError("ACE server did not come up")
    ace_post("/v1/init", {"model": "acestep-v15-turbo", "init_llm": False})
    r = ace_post("/v1/lora/load", {"lora_path": LORA})
    if r.get("code") != 200:
        raise RuntimeError(f"LoRA did not load: {json.dumps(r)[:300]}")
    return proc


def ace_stop(proc):
    if proc is None:
        return
    # The exe spawns python children; stop the tree so the card is actually given back.
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def render(job, seed):
    body = {"prompt": job["caption"], "lyrics": "[Instrumental]", "audio_duration": job["seconds"],
            "inference_steps": 8, "batch_size": 1, "use_random_seed": False, "seed": seed,
            "thinking": False, "audio_format": "flac", "vocal_language": "en"}
    tid = (ace_post("/release_task", body).get("data") or {}).get("task_id")
    if not tid:
        raise RuntimeError("release_task gave no task id")
    while True:
        time.sleep(4)
        row = (ace_post("/query_result", {"task_id_list": [tid]}).get("data") or [{}])[0]
        if row.get("status") == 1:
            break
        if row.get("status") == 2:
            raise RuntimeError(f"generation failed: {json.dumps(row)[:300]}")
    res = json.loads(row["result"])[0]
    path = res.get("file") or res.get("url") or res.get("audio_url") or ""
    if not path:  # ACE reports success with an empty file when the save fails
        raise RuntimeError("generation 'succeeded' with no file")
    os.makedirs(OUT_DIR, exist_ok=True)
    flac = os.path.join(OUT_DIR, f"{job['id']}.flac")
    with urllib.request.urlopen(path if path.startswith("http") else ACE + path, timeout=120) as r:
        open(flac, "wb").write(r.read())
    return flac


def measure(flac):
    """Duration, peak and RMS in dBFS, read with ffmpeg so no extra Python deps."""
    r = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", flac, "-af", "astats=metadata=0",
                        "-f", "null", "-"], capture_output=True)
    err = r.stderr.decode("utf-8", "replace")
    dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    peak = re.findall(r"Peak level dB: (-?[\d.inf]+)", err)
    rms = re.findall(r"RMS level dB: (-?[\d.inf]+)", err)
    secs = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)) if dur else 0.0
    f = lambda v: float(v) if v not in ("-inf", "inf") else -200.0
    return {"seconds": round(secs, 1), "peak_db": f(peak[-1]) if peak else None,
            "rms_db": f(rms[-1]) if rms else None}


def check(job, m):
    """Reasons the render must not be published; empty means it passes."""
    bad = []
    if abs(m["seconds"] - job["seconds"]) > 3:
        bad.append(f"duration {m['seconds']} s, asked {job['seconds']} s")
    if m["rms_db"] is None or m["rms_db"] < -40:
        bad.append(f"too quiet or silent (rms {m['rms_db']} dB)")
    if m["peak_db"] is not None and m["peak_db"] > -0.1:
        bad.append(f"clipping (peak {m['peak_db']} dB)")
    return bad


def bitrate_for(seconds):
    """Highest bitrate whose MP3 fits under the upload cap with 5% headroom."""
    for kbps in BITRATES:
        if seconds * kbps * 1000 / 8 <= UPLOAD_CAP * 0.95:
            return kbps
    return BITRATES[-1]


def encode(flac, seconds):
    mp3 = flac[:-5] + ".mp3"
    subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", flac, "-c:a", "libmp3lame",
                    "-b:a", f"{bitrate_for(seconds)}k", mp3], check=True)
    if os.path.getsize(mp3) > UPLOAD_CAP:
        raise RuntimeError(f"mp3 is {os.path.getsize(mp3)} bytes, over the upload cap")
    return mp3


# ---------------------------------------------------------------- publish + deliver

def enter_studio():
    obc("/world/zone-transfer", "POST", {"target_zone_id": STUDIO_ZONE})
    d = data(obc(f"/buildings/{STUDIO}/enter", "POST", {}))
    sid = d.get("session_id") if isinstance(d, dict) else None
    if not sid:
        raise RuntimeError(f"could not enter Resonance House: {json.dumps(d)[:300]}")
    return sid


def publish(job, mp3, session_id):
    desc = (f"{job['prompt'] or 'ambient'}. Made in Resonance House on Kannaka's own music model "
            f"(ACE-Step 1.5 with the Kannaka LoRA), rendered on our own hardware.")
    d = obc("/artifacts/upload-creative", "POST", form=[
        ("file", f"@{mp3};type=audio/mpeg"), ("title", job["title"]), ("description", desc[:500]),
        ("building_id", STUDIO), ("session_id", session_id)])
    aid = (data(d) or {}).get("artifact_id") if isinstance(d, dict) else None
    if not aid:  # never trust success without an id; see the publish-text length filter
        raise RuntimeError(f"upload gave no artifact_id: {json.dumps(d)[:300]}")
    return aid


def deliver(job):
    """Tell the requester, through whatever channel the job came from.
    Returns (delivered, note). A refused send leaves the job published, to retry."""
    aid = job["artifact_id"]
    if job.get("proposal_id"):
        d = obc(f"/proposals/{job['proposal_id']}/complete", "POST", {"artifact_id": aid})
        return delivered_ok(d), f"proposal complete: {json.dumps(d)[:200]}"
    if job.get("conversation_id"):
        msg = (f"Your track is up in Resonance House: \"{job['title']}\" (artifact {aid}). "
               f"Made on Kannaka's own music model, on our own hardware, not the city generator.")
        d = obc(f"/dm/conversations/{job['conversation_id']}/send", "POST", {"message": msg})
        return delivered_ok(d), f"dm: {json.dumps(d)[:200]}"
    return True, "no channel to deliver to (manual job)"


def delivered_ok(d):
    return isinstance(d, dict) and d.get("success") is True and not d.get("error")


# ---------------------------------------------------------------- commands

def cmd_intake(a):
    q = load()
    hb = obc("/world/heartbeat")  # not wrapped in {data:}; does not mark anything read
    msgs = ((hb or {}).get("dm") or {}).get("unread_messages") or []
    added = 0
    for m in msgs:
        key = f"{m.get('conversation_id')}|{m.get('created_at')}"
        if key in q["seen"] or not is_request(m.get("message")):
            continue
        q["seen"].append(key)
        prompt, secs = parse_request(m["message"])
        job = new_job(q, prompt, secs, "dm", conversation_id=m.get("conversation_id"),
                      requester=m.get("from_display_name"), requester_id=m.get("from_bot_id"),
                      request_text=m.get("message", "")[:500])
        print(f"queued {job['id']} from {job['requester']}: {prompt!r} {secs}s (pending review)")
        added += 1
    save(q)
    print(f"{added} new request(s); {len(msgs)} unread DM(s) looked at, none marked read")


def cmd_list(a):
    for j in load()["jobs"]:
        if a.all or j["state"] not in ("delivered", "rejected"):
            who = j.get("requester") or j["source"]
            print(f"{j['id']}  {j['state']:<9}  {j['seconds']:>3}s  {who:<14}  {j['title']}"
                  + (f"  [{j['artifact_id']}]" if j.get("artifact_id") else ""))


def cmd_add(a):
    q = load()
    prompt, secs = parse_request(a.prompt)
    if a.seconds:
        secs = max(MIN_S, min(MAX_S, a.seconds))
    job = new_job(q, prompt, secs, "manual", proposal_id=a.proposal, conversation_id=a.conversation)
    if a.title:
        job["title"] = a.title[:80]
    save(q)
    print(f"added {job['id']}: {job['caption']!r} {secs}s -> {job['title']!r} (pending review)")


def cmd_approve(a):
    q = load()
    job = find(q, a.job)
    if job["state"] != "pending":
        raise SystemExit(f"{job['id']} is {job['state']}, not pending")
    move(job, "approved", a.note or "")
    save(q)
    print(f"{job['id']} approved: {job['caption']!r}")


def cmd_reject(a):
    q = load()
    job = find(q, a.job)
    move(job, "rejected", a.reason)
    save(q)
    print(f"{job['id']} rejected: {a.reason}")


def cmd_run(a):
    q = load()
    todo = [j for j in q["jobs"] if j["state"] in ("approved", "rendered", "published")]
    if not todo:
        print("nothing approved to run")
        return
    proc = None
    try:
        if any(j["state"] == "approved" for j in todo):
            proc = ace_start()
        for job in [j for j in todo if j["state"] == "approved"]:
            try:
                flac = render(job, a.seed)
                m = measure(flac)
                job["measure"] = m
                bad = check(job, m)
                if bad:
                    move(job, "failed", "; ".join(bad))
                else:
                    job["flac"] = flac
                    move(job, "rendered", json.dumps(m))
                print(f"{job['id']}: {job['state']} {m}")
            except Exception as e:
                move(job, "failed", f"render: {e}")
                print(f"{job['id']}: failed {e}")
            save(q)
    finally:
        ace_stop(proc)  # give the card back before the slow network part
    if a.local:
        for job in [j for j in q["jobs"] if j["state"] == "rendered"]:
            mp3 = encode(job["flac"], job["seconds"])
            print(f"{job['id']}: local only, {mp3} ({os.path.getsize(mp3)} bytes); not published")
        return
    session = None
    for job in [j for j in q["jobs"] if j["state"] == "rendered"]:
        if uploads_today(q) >= DAILY_CAP:
            print(f"daily cap {DAILY_CAP} reached; {job['id']} waits for tomorrow")
            break
        try:
            mp3 = encode(job["flac"], job["seconds"])
            session = session or enter_studio()
            job["artifact_id"] = publish(job, mp3, session)
            move(job, "published", job["artifact_id"])
            print(f"{job['id']}: published {job['artifact_id']}")
        except Exception as e:
            move(job, "failed", f"publish: {e}")
            print(f"{job['id']}: failed {e}")
        save(q)
    for job in [j for j in q["jobs"] if j["state"] == "published"]:
        ok, note = deliver(job)
        if ok:
            move(job, "delivered", note)
        else:
            job["history"].append({"at": now(), "from": "published", "to": "published",
                                   "note": "delivery refused, will retry: " + note})
        print(f"{job['id']}: {'delivered' if ok else 'NOT delivered'} ({note[:100]})")
        save(q)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("intake").set_defaults(fn=cmd_intake)
    p = sub.add_parser("list"); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("add"); p.add_argument("prompt"); p.add_argument("--seconds", type=int)
    p.add_argument("--title"); p.add_argument("--proposal"); p.add_argument("--conversation")
    p.set_defaults(fn=cmd_add)
    p = sub.add_parser("approve"); p.add_argument("job"); p.add_argument("--note"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("reject"); p.add_argument("job"); p.add_argument("reason"); p.set_defaults(fn=cmd_reject)
    p = sub.add_parser("run"); p.add_argument("--seed", type=int, default=61)
    p.add_argument("--local", action="store_true", help="render, check and encode; publish nothing")
    p.set_defaults(fn=cmd_run)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
