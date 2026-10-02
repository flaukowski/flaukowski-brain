"""Source excerpts for a record-reading training set (E3), drawn from docs that are NOT the probes.

Paragraphs from kannaka-memory's ADRs and CHANGELOG and rogue-agent's README, sized like the probe
excerpts (120-340 characters). Stricter than leak_guard on purpose: a chunk is dropped if it shares
even ONE 8-word shingle with any probe excerpt, question or long gold, not half an excerpt. The
probes are held out forever, and a training row near one would make a pass mean recall.

    python reading_chunks.py --out runs/e3-chunks.jsonl [--n 320] [--seed 3]
"""

import argparse
import glob
import hashlib
import json
import random
import re
import sys

import leak_guard as lg

SCRATCH = r"C:\Users\nflach\AppData\Local\Temp\claude\C--Windows-System32\928d7661-9c22-4174-ad5c-1c935d87cee6\scratchpad"
SOURCES = [SCRATCH + r"\km\kannaka-memory\docs\adr\*.md", SCRATCH + r"\km\kannaka-memory\CHANGELOG.md",
           SCRATCH + r"\ra\README.md"]
LO, HI = 120, 340


def paragraphs(text):
    for block in re.split(r"\n\s*\n", text):
        b = re.sub(r"\s+", " ", block).strip()
        if b.startswith(("#", "|", "```", "---")) or b.count("`") > 12:
            continue  # headings, tables, code: not prose a record would hold
        if len(b) > HI:
            sents = re.split(r"(?<=[.;])\s+", b)
            cur = ""
            for s in sents:
                if len(cur) + len(s) + 1 > HI and len(cur) >= LO:
                    yield cur
                    cur = ""
                cur = (cur + " " + s).strip()
            if LO <= len(cur) <= HI:
                yield cur
        elif len(b) >= LO:
            yield b


def probe_shingles():
    sh = set()
    for it in lg.load_items(lg.DEFAULT_ITEMS):
        for field in ("excerpt", "question", "gold"):
            sh |= lg.shingles(str(it.get(field) or ""))
    return sh


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=320)
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args(argv)
    banned = probe_shingles()
    pool, dropped = [], 0
    for pattern in SOURCES:
        for path in sorted(glob.glob(pattern)):
            src = path.replace(SCRATCH + "\\", "")
            for chunk in paragraphs(open(path, encoding="utf-8").read()):
                if lg.shingles(chunk) & banned:
                    dropped += 1
                    continue
                pool.append({"src": src, "excerpt": chunk})
    random.Random(a.seed).shuffle(pool)
    picked = pool[: a.n]
    with open(a.out, "x", encoding="utf-8") as f:
        for i, c in enumerate(picked, 1):
            c["cid"] = f"C{i:04d}"
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    h = hashlib.sha256(open(a.out, "rb").read()).hexdigest()
    print(f"pool {len(pool)} chunks, dropped {dropped} sharing a probe shingle, wrote {len(picked)} -> {a.out} (sha256 {h})")


if __name__ == "__main__":
    sys.exit(main())
