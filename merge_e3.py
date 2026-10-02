"""Merge the E3 adapter into Qwen3-8B on CPU and quantize to q4_K_M, the same steps as
kannaka-memory tools/corpus/p2/merge_gguf.py (bf16 merge -> f16 GGUF -> llama-quantize q4_K_M),
run by hand because that tool looks for `llama-quantize` without `.exe` and so can't run on Windows.

    python merge_e3.py --adapter C:/Users/nflach/models/e3-adapter --out C:/Users/nflach/models/e3
"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = r"C:\Users\nflach\models\Qwen3-8B"
LC = Path(r"C:\Users\nflach\llama.cpp")


def log(m):
    print(f"[merge {time.strftime('%H:%M:%S')}] {m}", flush=True)


ap = argparse.ArgumentParser()
ap.add_argument("--adapter", required=True)
ap.add_argument("--out", required=True)
a = ap.parse_args()
out = Path(a.out)
mdir, gdir = out / "merged", out / "gguf"
gdir.mkdir(parents=True, exist_ok=True)
if not (mdir / "config.json").exists():
    log("loading base in bf16 on CPU")
    base = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, low_cpu_mem_usage=True)
    log("attaching adapter + merging")
    merged = PeftModel.from_pretrained(base, a.adapter).merge_and_unload()
    merged.save_pretrained(str(mdir), safe_serialization=True, max_shard_size="5GB")
    AutoTokenizer.from_pretrained(a.adapter).save_pretrained(str(mdir))
    del merged, base
    log(f"merged -> {mdir}")
f16 = gdir / "kannaka-brain-f16.gguf"
if not f16.exists():
    log("converting to GGUF f16")
    subprocess.run([sys.executable, str(LC / "src" / "convert_hf_to_gguf.py"), str(mdir), "--outtype", "f16",
                    "--outfile", str(f16)], check=True)
shutil.rmtree(mdir, ignore_errors=True)
q = gdir / "kannaka-brain-q4_K_M.gguf"
log("quantizing -> q4_K_M")
subprocess.run([str(LC / "bin" / "llama-quantize.exe"), str(f16), str(q), "q4_K_M"], check=True)
if q.stat().st_size < 100_000_000:
    raise SystemExit(f"quantized output is suspiciously small ({q.stat().st_size} bytes)")
f16.unlink()
log(f"done: {q} ({q.stat().st_size / 1e9:.2f} GB)")
