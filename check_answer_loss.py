"""answer_loss must equal transformers' own loss (model(labels=...)) on the same rows."""
import json
import random

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

import train_e3 as t

rows = [json.loads(l) for l in open("runs/e3-items-valid.jsonl", encoding="utf-8")][:3]
tok = AutoTokenizer.from_pretrained(t.ADAPTER)
data = t.build(rows, tok, 3, 1024)
bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                         bnb_4bit_compute_dtype=torch.bfloat16)
model = AutoModelForCausalLM.from_pretrained(t.BASE, quantization_config=bnb, device_map={"": 0}, dtype=torch.bfloat16)
model = PeftModel.from_pretrained(model, t.ADAPTER)
model.eval()
with torch.no_grad():
    for ids, labels in data:
        ids, labels = ids.cuda(), labels.cuda()
        ref = model(input_ids=ids[None], labels=labels[None]).loss.item()
        mine = t.answer_loss(model, ids, labels).item()
        print(f"hf {ref:.5f}  answer_loss {mine:.5f}  diff {abs(ref - mine):.2e}")
        assert abs(ref - mine) < 2e-2, "losses differ"
print("EQUIVALENT")
