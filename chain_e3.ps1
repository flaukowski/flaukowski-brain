# After training: merge + quantize, create the two tags, run the probes. Stops at the first failure.
$ErrorActionPreference = 'Stop'
$root = 'C:\Users\nflach\source\flaukowski-brain'
Start-Transcript -Path "$root\logs\chain_e3.transcript.txt" -Append | Out-Null
while (-not (Test-Path 'C:\Users\nflach\models\e3-adapter\adapter_model.safetensors')) {
    if (-not (Get-Process -Id 9884 -ErrorAction SilentlyContinue)) {
        Start-Sleep 10
        if (-not (Test-Path 'C:\Users\nflach\models\e3-adapter\adapter_model.safetensors')) { throw "training process exited without saving the adapter" }
    }
    Start-Sleep 20
}
Start-Sleep 10
"[$((Get-Date).ToUniversalTime().ToString('HH:mm:ssZ'))] adapter saved; merging"
Set-Location $root
& 'C:\Users\nflach\venvs\qlora\Scripts\python.exe' merge_e3.py --adapter C:/Users/nflach/models/e3-adapter --out C:/Users/nflach/models/e3
if ($LASTEXITCODE -ne 0) { throw "merge failed" }
"gguf sha256 $((Get-FileHash 'C:\Users\nflach\models\e3\gguf\kannaka-brain-q4_K_M.gguf').Hash.ToLower())"
ollama create kannaka-brain-e3-serve -f C:\Users\nflach\models\e3\Modelfile.e3-serve
if ($LASTEXITCODE -ne 0) { throw "ollama create e3-serve failed" }
ollama create kannaka-brain-e3 -f C:\Users\nflach\models\e3\Modelfile.e3
if ($LASTEXITCODE -ne 0) { throw "ollama create e3 failed" }
ollama list | Select-String 'kannaka-brain-e3'
"[$((Get-Date).ToUniversalTime().ToString('HH:mm:ssZ'))] tags created; starting run_e3"
Stop-Transcript | Out-Null
& powershell -NoProfile -ExecutionPolicy Bypass -File "$root\run_e3.ps1"
