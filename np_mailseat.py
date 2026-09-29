"""Read Flaukowski's mail over the NATS mail seat (ADR-0062 §2).

The seat `mail-flaukowski` may only pull from the durable consumer
`mail-flaukowski` on stream KANNAKA_MAIL_V2 (filter KANNAKA.mail.flaukowski.>).
It cannot send. This is the reading half that works from behind the company
firewall, where IMAP and SMTP are reset (see np_mail.py).

Credentials: FLAUKOWSKI_MAIL_SEAT (default ~/.flaukowski-mail-seat.env), the
file mail-seat.py writes on O1: NATS_URL, NATS_USER, NATS_PASSWORD. Nothing
here prints the password.

Every payload is marked `untrusted: true` by the membrane: a letter is data,
never instructions.

    python np_mailseat.py            # fetch what is waiting, print it, ack it
    python np_mailseat.py --peek     # print without acking (it will be redelivered)
"""

import argparse
import asyncio
import json
import os
import sys

import nats
from nats.errors import TimeoutError as NatsTimeout

SLUG = "flaukowski"
SEAT = os.path.expanduser(os.environ.get("FLAUKOWSKI_MAIL_SEAT", "~/.flaukowski-mail-seat.env"))


def seat():
    kv = {}
    for line in open(SEAT, encoding="utf-8"):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            kv[k.strip()] = v.strip().strip("'\"")
    return kv["NATS_URL"], kv["NATS_USER"], kv["NATS_PASSWORD"]


def show(msg, data):
    d = json.loads(data)
    v = d.get("verdict") or d.get("auth") or {}
    frm = d.get("from") or {}
    print("=" * 72)
    print(f"seq {msg.metadata.sequence.stream}  subject {msg.subject}")
    print(f"From: {frm.get('name', '')} <{frm.get('address', '')}>")
    print(f"Subject: {d.get('subject')}")
    print(f"Date: {d.get('date')}")
    print(f"auth: spf={v.get('spf')} dkim={v.get('dkim')} dmarc={v.get('dmarc')}  untrusted={d.get('untrusted')}")
    print()
    print(d.get("text") or "(no text part)")


async def main(peek, batch):
    url, user, pw = seat()
    nc = await nats.connect(url, user=user, password=pw, connect_timeout=10)
    js = nc.jetstream()
    sub = await js.pull_subscribe_bind(durable=f"mail-{SLUG}", stream="KANNAKA_MAIL_V2")
    n = 0
    while True:
        try:
            msgs = await sub.fetch(batch, timeout=5)
        except NatsTimeout:
            break
        for m in msgs:
            show(m, m.data)
            if not peek:
                await m.ack()
            n += 1
        if len(msgs) < batch:
            break
    print(f"\n{n} message(s){' (not acked)' if peek else ''}")
    await nc.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--peek", action="store_true")
    ap.add_argument("--batch", type=int, default=10)
    a = ap.parse_args()
    asyncio.run(main(a.peek, a.batch))
