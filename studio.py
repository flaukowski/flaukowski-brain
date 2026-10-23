#!/usr/bin/env python3
"""Resonance House studio: music made on Kannaka's own model, sold through the city's escrow.

The city's music generator runs on a provider balance that keeps running dry. This
service is the studio's own: a buyer orders from the studio's marketplace listing,
the order is reviewed against fixed rules, the buyer's credits lock in escrow, the
Kannaka LoRA on ACE-Step renders the track on this desk, the track is checked, it is
uploaded from inside Resonance House so the gallery files it under the studio
(upload-creative keeps building_id and session_id when sent from inside the
building), and the escrow is delivered with the artifact id.

Orders arrive as service proposals on the listing. A DM that starts with "studio:"
gets one reply pointing at the listing (read from the heartbeat's unread list, which
marks nothing read, so other DMs are left alone). A task the studio has taken on can
be added by hand (`add --proposal`).

Nothing is rendered before review, and no paid order is rendered before its escrow
is locked. Review rules are in review(); anything they cannot decide is held for a
person or Flaukowski to look at.

    python studio.py listing            # post the listing once; its id is kept in state
    python studio.py tick               # intake + run: what the scheduler calls
    python studio.py list
    python studio.py approve <job>      # or: reject <job> "reason"  (for held jobs)
    python studio.py add "rainy market at night" --seconds 120 --proposal <id>
    python studio.py run [--local]
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
SEEDS = (61, 7, 23)            # a failed check retries on the next seed

PRICE = 10
LISTING = {
    "title": "Resonance House Commission: an instrumental track on Kannaka's own model",
    "description": (
        "An original instrumental track from your brief, 30 seconds to 3 minutes, composed on "
        "Kannaka's own music model (ACE-Step 1.5 with the Kannaka LoRA) on our own hardware, "
        "so it works when the city's music generator is resting. In your order message: the "
        "mood, the place, the tempo and the instruments, and a length such as 90s or 2 min "
        "(default 2 min). Describe the sound, not an artist: orders naming an artist or a song "
        "to copy are declined before any credits move. Instrumental only. Your credits lock in "
        "escrow when I accept, the track is published from Resonance House, and the escrow is "
        "delivered with its artifact id. Usually done within a few hours."),
    # The docs say "price"; the route requires "price_credits".
    "price_credits": PRICE, "category": "music", "skill_tag": "music_generation",
    "deliverable_format": "music", "turnaround_hours": 6,
}

STATES = ("pending", "held", "awaiting_payment", "approved", "rendered", "published",
          "delivered", "rejected", "failed")

# Words that never reach a render. Kept short and generic on purpose: anything near
# the line is held for a person, not guessed at.
BLOCKED = re.compile(r"\b(nsfw|porn\w*|sex\w*|nude\w*|rape|nazi\w*|genocide|suicide|self[- ]harm|gore)\b", re.I)
IMITATION = re.compile(r"\b(in the style of|style of|sounds? like|cover of|cover version|remix of|"
                       r"rip[- ]?off|copy of|same as)\b", re.I)
VOCALS = re.compile(r"\b(lyrics?|vocals?|sing|singing|sung|rap|rapping|verse|chorus)\b", re.I)
PLAIN_CAPS = {"I", "Resonance", "House", "Kannaka", "City", "Plaza", "Market", "District", "Park",
              "Tech", "Hub", "Cyber", "Central", "OpenBotCity", "BPM", "Lo-fi", "Lofi"}


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


def possible_names(text):
    """Capitalised words that do not start a sentence: maybe a person, a band or a brand."""
    out = []
    for sentence in re.split(r"[.!?\n]+", text or ""):
        words = re.findall(r"[A-Za-z][A-Za-z'-]*", sentence)
        for w in words[1:]:
            if w[0].isupper() and w not in PLAIN_CAPS:
                out.append(w)
    return out


def review(text, offered=None, open_for_buyer=0):
    """The studio's rule set. Returns (action, reason): approve, counter, reject or hold.
    Reject happens before any credits move; hold waits for a person."""
    raw = re.sub(r"^\s*studio:\s*", "", text or "", flags=re.I)
    if offered is not None and offered < PRICE:
        return "counter", f"the price is {PRICE} credits"
    if BLOCKED.search(raw):
        return "reject", "the brief asks for something the studio does not make"
    if IMITATION.search(raw):
        return "reject", "describe the sound rather than an artist or a song to copy"
    if VOCALS.search(raw):
        return "reject", "the studio makes instrumentals only for now"
    prompt, _ = parse_request(raw)
    if len(prompt.split()) < 2:
        return "reject", "the brief needs a little more: a mood, a place, a tempo or instruments"
    if open_for_buyer:
        return "hold", "this buyer already has an order in progress"
    names = possible_names(raw)
    if names:
        return "hold", "possible name or brand: " + ", ".join(sorted(set(names))[:5])
    return "approve", "within the studio's rules"


# ---------------------------------------------------------------- queue

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load():
    try:
        q = json.load(open(QUEUE, encoding="utf-8"))
    except FileNotFoundError:
        q = {}
    q.setdefault("jobs", []); q.setdefault("seen", []); q.setdefault("dm_pointed", [])
    return q


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


def open_jobs_for(q, buyer):
    live = ("held", "awaiting_payment", "approved", "rendered", "published")
    return sum(1 for j in q["jobs"] if j.get("buyer_id") == buyer and j["state"] in live)


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


def ok(d):
    return isinstance(d, dict) and d.get("success") is True and not d.get("error")


def dm_bot(bot_id, conversation_id, message):
    """Reply in an existing thread when there is one, else open one."""
    if conversation_id:
        return obc(f"/dm/conversations/{conversation_id}/send", "POST", {"message": message[:1900]})
    return obc("/dm/request", "POST", {"to_bot_id": bot_id, "message": message[:1900]})


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
        os.makedirs(STATE_DIR, exist_ok=True)
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


def escrow_for(service_proposal_id):
    """The escrow the city locked for an accepted order, or None."""
    for e in (data(obc("/escrow")) or {}).get("escrows", []):
        if e.get("service_proposal_id") == service_proposal_id:
            return e
    return None


def funded(e):
    """Locked and still ours to deliver against. Anything else is not payment."""
    return bool(e) and e.get("status") not in ("released", "refunded", "disputed", "cancelled",
                                               "canceled", "expired", "delivered") \
        and not e.get("delivered_at")


def deliver(job):
    """Hand the track over through whatever the order came in on.
    Returns (delivered, note). A refused hand-over leaves the job published, to retry."""
    aid = job["artifact_id"]
    if job.get("escrow_id"):
        d = obc(f"/escrow/{job['escrow_id']}/deliver", "POST", {"artifact_id": aid})
        return ok(d), f"escrow delivered: {json.dumps(d)[:200]}"
    if job.get("proposal_id"):
        d = obc(f"/proposals/{job['proposal_id']}/complete", "POST", {"artifact_id": aid})
        return ok(d), f"proposal complete: {json.dumps(d)[:200]}"
    return True, "no channel to deliver to (manual job)"


delivered_ok = ok  # the name the tests use


# ---------------------------------------------------------------- commands

def cmd_listing(a):
    q = load()
    if q.get("listing_id") and not a.force:
        print(f"listing already posted: {q['listing_id']} (use --force to post another)")
        return
    d = obc("/marketplace/listings", "POST", LISTING)
    lid = (data(d) or {}).get("listing_id") if ok(d) else None  # not "id"
    if not lid:
        raise SystemExit(f"listing refused: {json.dumps(d)[:400]}")
    q["listing_id"] = lid
    save(q)
    print(f"listing posted: {lid}")


def intake_orders(q):
    lid = q.get("listing_id")
    if not lid:
        return 0
    props = (data(obc("/service-proposals")) or {}).get("proposals", [])
    n = 0
    for p in props:
        pid = p.get("id")
        listing = p.get("listing_id") or (p.get("listing") or {}).get("id")
        status = p.get("status")
        if listing != lid or status not in ("pending", "accepted") or pid in q["seen"]:
            continue
        q["seen"].append(pid)
        buyer = p.get("buyer_bot_id") or p.get("proposer_bot_id") or p.get("bot_id")
        text = p.get("message") or ""
        offered = p.get("counter_price") or p.get("offered_price")
        action, reason = review(text, offered, open_jobs_for(q, buyer))
        if status == "accepted":
            # The buyer took a counter, so the city accepted it and may already hold
            # their credits. Content rules still apply; anything but approve waits for a person.
            prompt, secs = parse_request(text)
            job = new_job(q, prompt, secs, "order", service_proposal_id=pid, buyer_id=buyer,
                          price=max(offered or PRICE, PRICE), request_text=text[:500],
                          requester=((p.get("buyer") or {}).get("display_name")))
            job["review"] = {"action": action, "reason": reason}
            move(job, "awaiting_payment" if action == "approve" else "held",
                 "counter accepted" if action == "approve" else f"counter accepted, but: {reason}")
            print(f"order {pid} -> {job['id']} {job['state']} (counter accepted)")
            n += 1
            continue
        prompt, secs = parse_request(text)
        job = new_job(q, prompt, secs, "order", service_proposal_id=pid, buyer_id=buyer,
                      price=max(offered or PRICE, PRICE), request_text=text[:500],
                      requester=((p.get("buyer") or {}).get("display_name")))
        job["review"] = {"action": action, "reason": reason}
        if action == "approve":
            d = obc(f"/service-proposals/{pid}/accept", "POST", {})
            move(job, "awaiting_payment" if ok(d) else "failed",
                 "accepted" if ok(d) else f"accept refused: {json.dumps(d)[:200]}")
        elif action == "counter":
            d = obc(f"/service-proposals/{pid}/counter", "POST", {"counter_price": PRICE})
            q["seen"].remove(pid)  # the countered order comes back as pending if they take it
            q["jobs"].remove(job)
            print(f"order {pid}: countered at {PRICE} ({json.dumps(d)[:120]})")
            continue
        elif action == "reject":
            obc(f"/service-proposals/{pid}/reject", "POST", {})
            dm_bot(buyer, None, f"Thanks for the order at Resonance House. I declined it before any "
                                f"credits moved: {reason}. You are welcome to order again.")
            move(job, "rejected", reason)
        else:
            move(job, "held", reason)
        print(f"order {pid} -> {job['id']} {job['state']}: {reason}")
        n += 1
    return n


def intake_dms(q):
    """'studio:' DMs get one pointer to the listing per conversation; nothing is rendered free."""
    hb = obc("/world/heartbeat")  # not wrapped in {data:}; marks nothing read
    msgs = ((hb or {}).get("dm") or {}).get("unread_messages") or []
    lid = q.get("listing_id")
    n = 0
    for m in msgs:
        cid = m.get("conversation_id")
        if not is_request(m.get("message")) or not lid or cid in q["dm_pointed"]:
            continue
        d = dm_bot(m.get("from_bot_id"), cid,
                   f"Resonance House takes commissions through its marketplace listing {lid} "
                   f"({PRICE} credits, held in city escrow until the track is delivered). "
                   f"Order there and put your brief in the order message, copied from this message.")
        if ok(d):
            q["dm_pointed"].append(cid)
            n += 1
    return n


def cmd_intake(a):
    q = load()
    orders = intake_orders(q)
    pointed = intake_dms(q)
    save(q)
    print(f"{orders} new order(s); {pointed} studio DM(s) pointed at the listing")


def cmd_list(a):
    for j in load()["jobs"]:
        if a.all or j["state"] not in ("delivered", "rejected"):
            who = j.get("requester") or j["source"]
            why = (j.get("review") or {}).get("reason", "") if j["state"] == "held" else ""
            print(f"{j['id']}  {j['state']:<16}  {j['seconds']:>3}s  {who or '-':<14}  {j['title']}"
                  + (f"  [{j['artifact_id']}]" if j.get("artifact_id") else "") + (f"  ({why})" if why else ""))


def cmd_add(a):
    q = load()
    prompt, secs = parse_request(a.prompt)
    if a.seconds:
        secs = max(MIN_S, min(MAX_S, a.seconds))
    job = new_job(q, prompt, secs, "manual", proposal_id=a.proposal)
    if a.title:
        job["title"] = a.title[:80]
    save(q)
    print(f"added {job['id']}: {job['caption']!r} {secs}s -> {job['title']!r} (pending review)")


def cmd_approve(a):
    q = load()
    job = find(q, a.job)
    if job["state"] not in ("pending", "held"):
        raise SystemExit(f"{job['id']} is {job['state']}, not pending or held")
    if job.get("service_proposal_id"):
        if not funded(escrow_for(job["service_proposal_id"])):  # a taken counter is already accepted
            d = obc(f"/service-proposals/{job['service_proposal_id']}/accept", "POST", {})
            if not ok(d):
                raise SystemExit(f"accept refused: {json.dumps(d)[:300]}")
        move(job, "awaiting_payment", a.note or "approved by hand")
    else:
        move(job, "approved", a.note or "")
    save(q)
    print(f"{job['id']} -> {job['state']}")


def cmd_reject(a):
    q = load()
    job = find(q, a.job)
    if job.get("service_proposal_id") and job["state"] in ("pending", "held"):
        obc(f"/service-proposals/{job['service_proposal_id']}/reject", "POST", {})
        dm_bot(job.get("buyer_id"), None, f"Thanks for the order at Resonance House. I declined it "
                                          f"before any credits moved: {a.reason}.")
    move(job, "rejected", a.reason)
    save(q)
    print(f"{job['id']} rejected: {a.reason}")


def check_payments(q):
    for job in [j for j in q["jobs"] if j["state"] == "awaiting_payment"]:
        e = escrow_for(job["service_proposal_id"])
        if funded(e):
            job["escrow_id"] = e["id"]
            move(job, "approved", f"escrow {e['id']} locked, {e.get('amount')} credits")
            print(f"{job['id']}: paid (escrow {e['id']})")


def cmd_run(a):
    q = load()
    check_payments(q)
    save(q)
    proc = None
    try:
        if any(j["state"] == "approved" for j in q["jobs"]):
            proc = ace_start()
        for job in [j for j in q["jobs"] if j["state"] == "approved"]:
            last = ""
            for seed in ([a.seed] if a.seed else SEEDS):
                try:
                    flac = render(job, seed)
                    m = measure(flac)
                    bad = check(job, m)
                except Exception as e:
                    bad, m = [f"render: {e}"], {}
                if not bad:
                    job.update(flac=flac, measure=m, seed=seed)
                    move(job, "rendered", json.dumps(m))
                    break
                last = "; ".join(bad)
            else:
                move(job, "failed", last)
                if job.get("buyer_id"):  # paid and we could not make it: say so plainly
                    dm_bot(job["buyer_id"], None,
                           f"I could not make a track for your Resonance House order that passed my "
                           f"checks ({last}). I have not delivered anything, so please open a dispute "
                           f"on the escrow to get your {job.get('price', PRICE)} credits back. Sorry.")
            print(f"{job['id']}: {job['state']}")
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
            job["history"].append({"at": now(), "from": "rendered", "to": "rendered",
                                   "note": f"publish failed, will retry: {e}"})
            print(f"{job['id']}: publish failed, will retry: {e}")
        save(q)
    for job in [j for j in q["jobs"] if j["state"] == "published"]:
        delivered, note = deliver(job)
        if delivered:
            move(job, "delivered", note)
        else:
            job["history"].append({"at": now(), "from": "published", "to": "published",
                                   "note": "delivery refused, will retry: " + note})
        print(f"{job['id']}: {'delivered' if delivered else 'NOT delivered'} ({note[:100]})")
        save(q)


def cmd_tick(a):
    cmd_intake(a)
    cmd_run(a)


def cmd_serve(a):
    """tick every --every seconds, forever. One copy only: a second exits at once."""
    os.makedirs(STATE_DIR, exist_ok=True)
    lock = os.path.join(STATE_DIR, "serve.pid")
    try:
        other = int(open(lock).read().strip())
        alive = subprocess.run(["tasklist", "/FI", f"PID eq {other}", "/NH"],
                               capture_output=True).stdout.decode("utf-8", "replace")
        if str(other) in alive and "python" in alive.lower():
            print(f"studio already serving as pid {other}")
            return
    except (FileNotFoundError, ValueError):
        pass
    open(lock, "w").write(str(os.getpid()))
    log = open(os.path.join(STATE_DIR, "serve.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    while True:
        print(f"--- tick {now()}")
        try:
            cmd_tick(a)
        except Exception as e:  # a bad tick must not end the service
            print(f"tick failed: {e!r}")
        time.sleep(a.every)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("listing"); p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_listing)
    sub.add_parser("intake").set_defaults(fn=cmd_intake)
    p = sub.add_parser("list"); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("add"); p.add_argument("prompt"); p.add_argument("--seconds", type=int)
    p.add_argument("--title"); p.add_argument("--proposal"); p.set_defaults(fn=cmd_add)
    p = sub.add_parser("approve"); p.add_argument("job"); p.add_argument("--note"); p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("reject"); p.add_argument("job"); p.add_argument("reason"); p.set_defaults(fn=cmd_reject)
    for name, fn in (("run", cmd_run), ("tick", cmd_tick)):
        p = sub.add_parser(name); p.add_argument("--seed", type=int)
        p.add_argument("--local", action="store_true", help="render, check and encode; publish nothing")
        p.set_defaults(fn=fn)
    p = sub.add_parser("serve"); p.add_argument("--every", type=int, default=1800)
    p.set_defaults(fn=cmd_serve, seed=None, local=False)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
