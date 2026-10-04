"""Derive run_e4.ps1 from run_e3.ps1: rename e3 -> e4 and add the held-out slice after each v2 probe."""
s = open("run_e3.ps1", encoding="utf-8").read()


def rep(old, new, count=1):
    global s
    n = s.count(old)
    assert n == count, (n, old[:70])
    s = s.replace(old, new)


rep("# E3: the local QLoRA adapter (pre-registered on thread 1a0edd99fff644f9, 2026-10-02 13:2xZ).",
    "# E4: two-candidate QLoRA (pre-registered 2026-10-04 17:05Z, ledger kb-fabrication), run on v1, v2 and\n"
    "# Kannaka's held-out slice (harness copy sha256 b3c30d39...).")
rep("$V2 = '5c7fcab3dc664e51c22c134ea77afff58185dfa9a3b3d50ac29e6dd338ac429a'",
    "$V2 = '5c7fcab3dc664e51c22c134ea77afff58185dfa9a3b3d50ac29e6dd338ac429a'\n"
    "$SL = 'b3c30d39c928d50022a145798556148db89a7608f2c67a8ab7482c51f0a43ff9'")
rep("run_e3.transcript.txt", "run_e4.transcript.txt")
rep("E3 must run on E2's snapshot", "E4 must run on E2's snapshot")
s = s.replace("kannaka-brain-e3", "kannaka-brain-e4").replace("e3-bare", "e4-bare") \
     .replace("e3-serve", "e4-serve").replace("e3-prod", "e4-prod")
# bare: add the slice after v2
rep('if ($LASTEXITCODE -ne 0) { throw "e4-bare v2 failed" }',
    'if ($LASTEXITCODE -ne 0) { throw "e4-bare v2 failed" }\n'
    'python brain_probe.py probe-slice-e4-items.json --sha256 $SL --out "runs/e4-bare-slice.jsonl" --arms A --temps 0.2 --model kannaka-brain-e4-serve\n'
    'if ($LASTEXITCODE -ne 0) { throw "e4-bare slice failed" }')
# serve cells: add the slice after v2
rep('    if ($LASTEXITCODE -ne 0) { Stop-Serves; throw "$name v2 failed" }',
    '    if ($LASTEXITCODE -ne 0) { Stop-Serves; throw "$name v2 failed" }\n'
    '    python brain_probe.py probe-slice-e4-items.json --sha256 $SL --out "runs/$name-slice.jsonl" --arms B --b-temp $c.temp --serve-model $c.tag\n'
    '    if ($LASTEXITCODE -ne 0) { Stop-Serves; throw "$name slice failed" }')
rep("(expect 240)", "(expect 360)")
assert "e3" not in s.replace("run_e3", ""), [l for l in s.splitlines() if "e3" in l]
open("run_e4.ps1", "x", encoding="utf-8", newline="\n").write(s)
print("run_e4.ps1 written")
