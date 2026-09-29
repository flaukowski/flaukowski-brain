"""Flaukowski's mailbox at ninja-portal.com: send over SMTP, read over IMAP.

Credentials come from ~/.kannaka-mail-ninja-portal.env (KANNAKA_MAIL_USER /
KANNAKA_MAIL_PASS), the same file `kannaka mail` reads. Nothing here prints
the password.

TLS: the network this machine sits on re-signs mail.ninja-portal.com with a
FortiGate certificate that no local store trusts. Nick accepted that on
2026-09-29. Rather than switching verification off, every connection is
pinned: the leaf certificate's SHA-256 must equal the one recorded in
~/.kannaka/mail/pin.txt, checked BEFORE login. A different certificate (a new
FortiGate cert, or a network without interception) refuses to log in; re-pin
deliberately after checking the issuer with openssl.

    python np_mail.py send --to a@b --subject S --body-file f.txt
    python np_mail.py list [--limit N]          # newest first
    python np_mail.py read <uid>
"""

import argparse
import email
import hashlib
import imaplib
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import make_msgid

HOST = "mail.ninja-portal.com"
ENV = os.path.expanduser(os.environ.get("FLAUKOWSKI_MAIL_ENV", "~/.kannaka-mail-ninja-portal.env"))
PIN = os.path.expanduser(os.environ.get("FLAUKOWSKI_MAIL_PIN", "~/.kannaka/mail/pin.txt"))


def creds():
    kv = {}
    for line in open(ENV, encoding="utf-8"):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            kv[k.strip()] = v.strip().strip('"')
    return kv["KANNAKA_MAIL_USER"], kv["KANNAKA_MAIL_PASS"]


def pinned_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # replaced by the fingerprint check below
    return ctx


def check_pin(sock):
    want = open(PIN, encoding="utf-8").read().strip().replace(":", "").lower()
    got = hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()
    if got != want:
        sys.exit(f"np_mail: certificate fingerprint {got} does not match the pin; refusing to log in")


def send(to, subject, body, in_reply_to=None):
    user, pw = creds()
    m = EmailMessage()
    m["From"] = f"Flaukowski <{user}>"
    m["To"] = to
    m["Subject"] = subject
    m["Message-ID"] = make_msgid(domain="ninja-portal.com")
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
        m["References"] = in_reply_to
    m.set_content(body)
    with smtplib.SMTP_SSL(HOST, 465, context=pinned_context(), timeout=30) as s:
        check_pin(s.sock)
        s.login(user, pw)
        refused = s.send_message(m)
    if refused:
        sys.exit(f"np_mail: refused recipients {refused}")
    return m["Message-ID"]


def imap():
    user, pw = creds()
    im = imaplib.IMAP4_SSL(HOST, 993, ssl_context=pinned_context())
    check_pin(im.sock)
    im.login(user, pw)
    return im


def list_messages(limit):
    im = imap()
    im.select("INBOX", readonly=True)
    _, data = im.uid("search", None, "ALL")
    uids = data[0].split()[-limit:][::-1]
    for uid in uids:
        _, d = im.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] FLAGS)")
        hdr = email.message_from_bytes(d[0][1])
        seen = b"\\Seen" in d[0][0]
        print(f"{uid.decode():>5} {' ' if seen else '*'} {hdr['Date'][:25]:25} {hdr['From'][:40]:40} {hdr['Subject']}")
    im.logout()


def read(uid):
    im = imap()
    im.select("INBOX", readonly=True)
    _, d = im.uid("fetch", uid.encode(), "(BODY.PEEK[])")
    msg = email.message_from_bytes(d[0][1])
    print(f"From: {msg['From']}\nTo: {msg['To']}\nDate: {msg['Date']}\nSubject: {msg['Subject']}\nMessage-ID: {msg['Message-ID']}\n")
    part = msg.get_body(preferencelist=("plain",)) if msg.is_multipart() else msg
    print(part.get_content() if part else "(no text part)")
    im.logout()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("send")
    s.add_argument("--to", required=True)
    s.add_argument("--subject", required=True)
    s.add_argument("--body-file", required=True)
    s.add_argument("--in-reply-to")
    l = sp.add_parser("list")
    l.add_argument("--limit", type=int, default=15)
    r = sp.add_parser("read")
    r.add_argument("uid")
    a = ap.parse_args()
    if a.cmd == "send":
        body = open(a.body_file, encoding="utf-8").read()
        print(send(a.to, a.subject, body, a.in_reply_to))
    elif a.cmd == "list":
        list_messages(a.limit)
    else:
        read(a.uid)


if __name__ == "__main__":
    main()
