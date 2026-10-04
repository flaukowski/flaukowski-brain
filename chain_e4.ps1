# After E4 training: merge + quantize, create the two tags, run the probes. Stops at the first failure.
$ErrorActionPreference = 'Stop'
$root = 'C:\Users\nflach\source\flaukowski-brain'
$adapter = 'C:\Users\nflach\models\e4-adapter\adapter_model.safetensors'
Start-Transcript -Path "$root\logs\chain_e4.transcript.txt" -Append | Out-Null
while (-not (Test-Path $adapter)) {
    if (-not (Get-Process -Id 20132 -ErrorAction SilentlyContinue)) {
        Start-Sleep 10
        if (-not (Test-Path $adapter)) { throw "training process exited without saving the adapter" }
    }
    Start-Sleep 20
}
Start-Sleep 10
"[$((Get-Date).ToUniversalTime().ToString('HH:mm:ssZ'))] adapter saved; merging"
Set-Location $root
& 'C:\Users\nflach\venvs\qlora\Scripts\python.exe' merge_e3.py --adapter C:/Users/nflach/models/e4-adapter --out C:/Users/nflach/models/e4
if ($LASTEXITCODE -ne 0) { throw "merge failed" }
"gguf sha256 $((Get-FileHash 'C:\Users\nflach\models\e4\gguf\kannaka-brain-q4_K_M.gguf').Hash.ToLower())"
ollama create kannaka-brain-e4-serve -f C:\Users\nflach\models\e4\Modelfile.e4-serve
if ($LASTEXITCODE -ne 0) { throw "ollama create e4-serve failed" }
ollama create kannaka-brain-e4 -f C:\Users\nflach\models\e4\Modelfile.e4
if ($LASTEXITCODE -ne 0) { throw "ollama create e4 failed" }
ollama list | Select-String 'kannaka-brain-e4'
"[$((Get-Date).ToUniversalTime().ToString('HH:mm:ssZ'))] tags created; starting run_e4"
Stop-Transcript | Out-Null
& powershell -NoProfile -ExecutionPolicy Bypass -File "$root\run_e4.ps1"
