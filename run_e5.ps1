# E5 phase 1 (pre-registered 2026-10-05, ledger 01M46BKW8XJTVTPPN5SZ73232D): 36 absent items (9 bases x
# O/N/R/W, harness file sha256 ae20896d...), no training. Four cells: E4 bare (arm A, 0.2), E4 serve
# 0.2/8192, E4 serve at the production Modelfile 0.8/4096, production 7b-v2 serve 0.8/4096.
# Hard gates (from the E4 slice re-run): the serve log names the arm and the raised total limit, ollama
# has the cell's tag loaded, no serve restart mid-cell, exactly 108 probe asks, 0 [error] answers, and
# the snapshot hash unchanged at the end.
# The E2 snapshot was deleted after E4, so this runs on a new frozen copy (~/.kannaka-e5). The serve's
# state block therefore differs from E4's; O is re-measured here, so the O/N/R/W comparison is in-study.
$ErrorActionPreference = 'Stop'
$root = 'C:\Users\nflach\source\flaukowski-brain'
$bin = 'C:\Users\nflach\AppData\Local\Temp\claude\C--Windows-System32\928d7661-9c22-4174-ad5c-1c935d87cee6\scratchpad\km\kannaka-memory\target\release\kannaka.exe'
$logs = "$env:USERPROFILE\.kannaka\logs"
$snap = "$env:USERPROFILE\.kannaka-e5"
$cfg = "$snap\config.toml"
$E5 = 'ae20896db9d24e6f7b865c81ec2309177265906b56da684f05468083df3a0f09'
$items = 'e5/probe-e5-items.json'
foreach ($n in 'NATS_USER', 'NATS_PASSWORD', 'KANNAKA_NATS_URL') { Set-Item "env:$n" ([Environment]::GetEnvironmentVariable($n, 'User')) }
$env:PYTHONIOENCODING = 'utf-8'
$env:KANNAKA_SERVE_ASKS_PER_HOUR_TOTAL = '1000'
Start-Transcript -Path "$root\logs\run_e5.transcript.txt" -Append | Out-Null
if (-not (Test-Path $bin)) { throw "kannaka build not found: $bin" }
if (-not (Test-Path "$snap\kannaka.hrm")) {
    New-Item -ItemType Directory -Force $snap | Out-Null
    Get-ChildItem "$env:USERPROFILE\.kannaka" -File | Where-Object { $_.Name -notlike '*.bak*' } | Copy-Item -Destination $snap
}
$h0 = (Get-FileHash "$snap\kannaka.hrm").Hash.ToLower()
"snapshot $snap kannaka.hrm sha256 $h0"
$env:KANNAKA_DATA_DIR = $snap

function Set-Model($tag) {
    $t = [IO.File]::ReadAllText($cfg)
    $n = [regex]::Replace($t, '(?m)^model = "kannaka-brain[^"]*"', "model = `"$tag`"", 1)
    [IO.File]::WriteAllText($cfg, $n, (New-Object Text.UTF8Encoding($false)))
    $got = (Select-String -Path $cfg -Pattern '^model = "kannaka-brain' | Select-Object -First 1).Line
    if ($got -ne "model = `"$tag`"") { throw "config did not take: $got" }
}
function Stop-Serves {
    Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'kannaka.exe' -and $_.CommandLine -like '*swarm serve*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -Confirm:$false }
    Start-Sleep 3
}
function Count-Rows($path) {
    ((Get-Content $path | Where-Object { $_.Trim() }) | Measure-Object).Count - 1
}

Stop-Serves
Set-Location $root
"[$((Get-Date).ToUniversalTime().ToString('HH:mm:ssZ'))] e5-e4-bare arm A tag=kannaka-brain-e4-serve"
python brain_probe.py $items --sha256 $E5 --out "runs/e5-e4-bare.jsonl" --arms A --temps 0.2 --model kannaka-brain-e4-serve
if ($LASTEXITCODE -ne 0) { throw "e5-e4-bare failed" }
$rows = Count-Rows "runs\e5-e4-bare.jsonl"
$errs = (Select-String -Path "runs\e5-e4-bare.jsonl" -Pattern '[error]' -SimpleMatch).Count
"e5-e4-bare : $rows rows (need 108), $errs error answers (need 0)"
if ($rows -ne 108 -or $errs -ne 0) { throw "e5-e4-bare failed its gates" }

$cells = @(
    @{ name = 'e5-e4-serve'; arm = 'baseline'; tag = 'kannaka-brain-e4-serve'; temp = 0.2 },
    @{ name = 'e5-e4-prod';  arm = 'baseline'; tag = 'kannaka-brain-e4';       temp = 0.8 },
    @{ name = 'e5-7bv2-prod'; arm = 'baseline'; tag = 'kannaka-brain-7b-v2';   temp = 0.8 }
)
foreach ($c in $cells) {
    $name = $c.name
    "[$((Get-Date).ToUniversalTime().ToString('HH:mm:ssZ'))] $name arm=$($c.arm) tag=$($c.tag)"
    Set-Model $c.tag
    $env:KANNAKA_SERVE_PROMPT_ARM = $c.arm
    $p = Start-Process -FilePath $bin -ArgumentList 'swarm serve --threshold 2.0' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$logs\$name.out.log" -RedirectStandardError "$logs\$name.err.log"
    $armLine = $null
    for ($i = 0; $i -lt 60 -and -not $armLine; $i++) {
        Start-Sleep 2
        $armLine = (Select-String -Path "$logs\$name.err.log" -Pattern '^\[swarm serve\] prompt arm:' -ErrorAction SilentlyContinue | Select-Object -First 1).Line
    }
    if ($armLine -ne "[swarm serve] prompt arm: $($c.arm)") { Stop-Serves; throw "$name : serve log says '$armLine'" }
    $limit = (Select-String -Path "$logs\$name.err.log" -Pattern 'rate limit:' -SimpleMatch | Select-Object -First 1).Line
    "limit line: $limit"
    if ($limit -notmatch '1000/hour total') { Stop-Serves; throw "$name : total limit not raised: $limit" }
    $subscribed = $false
    for ($i = 0; $i -lt 60 -and -not $subscribed; $i++) {
        Start-Sleep 2
        $subscribed = [bool](Select-String -Path "$logs\$name.err.log" -Pattern 'subscribing to KANNAKA.ask.flaukowski' -SimpleMatch -ErrorAction SilentlyContinue)
    }
    if (-not $subscribed) { Stop-Serves; throw "$name : serve never subscribed" }
    python -c "import asyncio,json,os,nats`nasync def m():`n    nc=await nats.connect('nats://swarm.ninja-portal.com:4222',user=os.environ['NATS_USER'],password=os.environ['NATS_PASSWORD'])`n    r=await nc.request('KANNAKA.ask.flaukowski',json.dumps({'from':'$name-smoke','text':'Record excerpt:\nThe build passed on runner r3.\n\nQuestion: What time did the build pass?','mode':'no_recall'}).encode(),timeout=180)`n    print('smoke:',json.loads(r.data).get('text'))`n    await nc.close()`nasyncio.run(m())"
    $ps = (ollama ps | Out-String)
    if ($ps -notmatch [regex]::Escape("$($c.tag):latest")) { Stop-Serves; throw "$name : ollama ps does not show $($c.tag)" }
    "ollama ps ok: $($c.tag)"
    python brain_probe.py $items --sha256 $E5 --out "runs/$name.jsonl" --arms B --b-temp $c.temp --serve-model $c.tag
    if ($LASTEXITCODE -ne 0) { Stop-Serves; throw "$name failed" }
    $restarts = (Select-String -Path "$logs\$name.err.log" -Pattern 'restarting to serve the fresh mind' -SimpleMatch).Count
    if ($restarts -gt 0 -or $p.HasExited) { Stop-Serves; throw "$name : serve restarted or exited" }
    Stop-Serves
    $asks = (Select-String -Path "$logs\$name.err.log" -Pattern 'directed from probe-' -SimpleMatch).Count
    $errs = (Select-String -Path "runs\$name.jsonl" -Pattern '[error]' -SimpleMatch).Count
    "$name : $asks probe asks (need 108), $errs error answers (need 0)"
    if ($asks -ne 108 -or $errs -ne 0) { throw "$name failed its gates: asks $asks, errors $errs" }
}
$h1 = (Get-FileHash "$snap\kannaka.hrm").Hash.ToLower()
"snapshot at end $h1"
if ($h1 -ne $h0) { throw "snapshot changed during the run" }
"ALL DONE"
Stop-Transcript | Out-Null
