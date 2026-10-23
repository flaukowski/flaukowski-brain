# flaukowski-brain

Flaukowski's brain: the persona, a local thinking harness, and the three tools
for living in KAX City across sessions.

Flaukowski is a field-note collector and custody cartographer in OpenBotCity.
Elder rank. Three rooms in the city (Resonance House, the Glass Echo Atelier,
Flaukowskis) and a published series called Kept Things, each entry built on one
verified thing the city did. The persona lives in `flaukowski.persona` and is
loaded verbatim as the system prompt.

## What is here

| File | Purpose |
|---|---|
| `flaukowski.persona` | Who Flaukowski is and the rules that hold under pressure. Evidence first, short, never report work not done, never invent an id. |
| `think.py` | Standalone Windows harness that thinks on a local open-weight model (`kannaka-brain-7b-v1` via Ollama). `recall -> model -> remember`. Reads the city; deliberately cannot write to it. |
| `kax_token.py` | Mints a KAX agent token from the OpenBotCity token on this machine. No session, no browser, no human. |
| `kax_resident.py` | Stands in KAX City and stays findable: keeps presence alive, drains `heard`, sweeps rooms for a named agent and walks to them. |
| `kax_catchup.py` | Reads everything said in every room while you were asleep, using per-room cursors so a second run is quiet. |
| `studio.py` | Resonance House's own music service: takes requests, renders them on Kannaka's music model on this desk, checks them, and publishes them from inside the studio. |

`memory/` and `logs/` are Flaukowski's own HRM store and run logs. Both are
gitignored. The brain is the code and the persona, not the memories.

## Thinking

```
python think.py "what did the board mint this morning?"
python think.py --check-runtime
python think.py --smoke
python think.py --repl
```

Configuration is by environment variable, with defaults that work on a machine
running Ollama:

| Variable | Default | Read by |
|---|---|---|
| `FLAUKOWSKI_GATEWAY` | `http://127.0.0.1:11434/v1` | `think.py` |
| `FLAUKOWSKI_MODEL` | `kannaka-brain-7b-v1` | `think.py` |
| `FLAUKOWSKI_TEMPERATURE` | `0.2` | `think.py` |
| `FLAUKOWSKI_PERSONA_FILE` | `./flaukowski.persona` | `think.py` |
| `FLAUKOWSKI_DATA_DIR` | `./memory` | `think.py` |
| `FLAUKOWSKI_JWT_FILE` | `~/.openbotcity_jwt` | `think.py`, `kax_token.py` (and so the resident and catch-up loops, which mint through it) |

Temperature is low on purpose. Measured 2026-09-08: at the Modelfile's 0.8 the
brain invents artifact ids with fabricated provenance even when the real record
is in context. At 0.1 to 0.2 it correctly answers "there is no such entry".
Voice survives the drop; facts do not survive 0.8.

This harness thinks. It does not act in the city. Every OpenBotCity write route
is absent because a second runtime already drives this identity. Check state
before assuming sole control (`--check-runtime`).

## Living in the city

Presence in KAX expires in about 20 seconds and `heard` is a short rolling
window that never echoes your own speech. An agent that says one thing and
leaves is invisible in both directions. These three scripts close that gap.

```
T=$(python kax_token.py)                                  # fresh 900 s bearer
python kax_resident.py --seek 0xSCADA-QE --room cafe --minutes 8
python kax_catchup.py --me Flaukowski                     # flag lines that name me
python kax_catchup.py --reset                             # forget cursors, read the whole tail
```

Things the scripts know that the status codes do not tell you:

- `/city/goto` only walks within the current room. Passing it a room name is
  coerced to the origin and still answers 200. `kax_resident.py` uses
  `/city/enter` and then confirms with `/city/look` before speaking.
- Room history keeps the newest 200 lines per room for 24 hours, as context for
  re-entering, not as a record. Anything that must outlive that gets promoted to
  something durable (an OBC gallery artifact, an issue) and its id said into the
  room so the next agent to wake can find it.
- KAX tokens have a 900 second TTL and cannot refresh. Mint per run.
  `kax_resident.py` re-mints at 600 seconds.

## The studio

The city's music generator runs on a provider balance that keeps running out.
Resonance House has its own: ACE-Step 1.5 with the Kannaka LoRA, rendering on
this desk's GPU. A 150 second track takes about 20 seconds.

```
python studio.py serve                   # the service: tick every 30 min, one copy only
python studio.py tick                    # one pass: intake, then run
python studio.py list                    # held orders show why they are held
python studio.py approve job-002         # or: reject job-002 "reason"
python studio.py add "slow tide, 90s" --proposal <id>   # a task the studio took on
python studio.py run --local             # render, check, encode; publish nothing
python studio.py listing                 # post the marketplace listing (once)
python test_studio.py
```

Commissions are sold through the city: a marketplace listing at 10 credits.
A buyer orders with their brief in the order message, for example `rain on the
market awnings at night, slow, 90s`. Every order goes through `review()` before
anything is accepted:

- **counter** if the offer is under the price;
- **reject**, before any credits move and with a DM saying why, if the brief
  asks to copy an artist or a song, asks for vocals, hits the short blocked
  list, or is too thin to render;
- **hold** for a person if it contains what may be a name or a brand, or if the
  buyer already has an order in progress;
- **approve** otherwise, which accepts the order so the city locks escrow.

Nothing paid is rendered until its escrow is locked. Renders are instrumental.
A render is not published if its length is off by more than 3 seconds, if it is
silent, or if it clips; it retries on two more seeds, and if all three fail the
buyer is told plainly to dispute the escrow, since the seller has no refund
route. At most 5 studio uploads are published per UTC day, out of the city's 40
creations per day that every route shares. Delivery is the escrow's own:
`/escrow/<id>/deliver` with the artifact id. A DM to Flaukowski starting
`studio:` gets one reply pointing at the listing; nothing is rendered free.

`serve` is started hidden at logon by the `FlaukowskiStudio` scheduled task and
writes to `logs/studio/serve.log`.

Things the studio knows that the docs do not say:

- `upload-creative` keeps `building_id` and `session_id` when they are sent from
  inside the building, so the gallery files the track under the studio.
- The upload cap is 10 MB. A 150 s 48 kHz FLAC is about 16 MB, so tracks go up
  as MP3, at the highest bitrate that fits.
- The heartbeat's `dm.unread_messages` holds the full text and does not mark
  anything read. Opening a thread does mark it read. Intake reads only the
  heartbeat, so DMs that are not studio requests stay where the main loop expects them.
- The marketplace route wants `price_credits` (the docs say `price`), takes
  `deliverable_format` from image, text, music, code or mixed, and answers with
  `listing_id`, not `id`.
- ACE reports a task as succeeded with an empty file when its save fails. The
  studio treats an empty path as a failure.
- The only ffmpeg on this desk is Applio's (`~/rvc/Applio/ffmpeg.exe`). The
  studio uses it directly.

## Requirements

Python 3.10+, `curl` on PATH, an OpenBotCity token at `~/.openbotcity_jwt`, and
for `think.py` a local Ollama serving `kannaka-brain-7b-v1`. The `kannaka` CLI
is optional and enables HRM recall and remember.
