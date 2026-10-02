# E2 of the wrapper study (pre-registered on thread 1a0edd99fff644f9, 2026-10-01).
# One serve at a time; each cell refuses to run unless its serve log names the arm it was given
# and ollama has the cell's tag loaded. Run files are opened with mode "x" by brain_probe.py.
$ErrorActionPreference = 'Stop'
$root = 'C:\Users\nflach\source\flaukowski-brain'
$bin = 'C:\Users\nflach\AppData\Local\Temp\claude\C--Windows-System32\928d7661-9c22-4174-ad5c-1c935d87cee6\scratchpad\km\kannaka-memory\target\release\kannaka.exe'
$logs = "$env:USERPROFILE\.kannaka\logs"
# The study runs against a private, frozen copy of the data dir. swarm serve exits on any change
# to kannaka.hrm (#563) and relies on systemd to restart it; on this box another process writes the
# shared store, and on 10-01 that ended the first E2 run after one cell. A copy nobody writes also
# holds the prompt's state block (phi, counts) constant across every cell.
$snap = "$env:USERPROFILE\.kannaka-e2"
$cfg = "$snap\config.toml"
$V1 = 'f291f2d20001f4c9d84bdc4163e48c3eb34cb4bb363232ac31a40a66ddb8e07b'
$V2 = '5c7fcab3dc664e51c22c134ea77afff58185dfa9a3b3d50ac29e6dd338ac429a'
foreach ($n in 'NATS_USER', 'NATS_PASSWORD', 'KANNAKA_NATS_URL') { Set-Item "env:$n" ([Environment]::GetEnvironmentVariable($n, 'User')) }
$env:PYTHONIOENCODING = 'utf-8'

Start-Transcript -Path "$root\logs\run_e2s.transcript.txt" -Append | Out-Null
if (-not (Test-Path "$snap\kannaka.hrm")) {
    New-Item -ItemType Directory -Force $snap | Out-Null
    Get-ChildItem "$env:USERPROFILE\.kannaka" -File | Where-Object { $_.Name -notlike '*.bak*' } | Copy-Item -Destination $snap
}
"snapshot $snap kannaka.hrm sha256 $((Get-FileHash "$snap\kannaka.hrm").Hash.ToLower())"
$env:KANNAKA_DATA_DIR = $snap

$cells = @(
    @{ name = 'e2s-baseline';           arm = 'baseline';           tag = 'kannaka-brain-7b-v2-serve'; temp = 0.2 },
    @{ name = 'e2s-no-state';           arm = 'no-state';           tag = 'kannaka-brain-7b-v2-serve'; temp = 0.2 },
    @{ name = 'e2s-no-reference';       arm = 'no-reference';       tag = 'kannaka-brain-7b-v2-serve'; temp = 0.2 },
    @{ name = 'e2s-no-state-reference'; arm = 'no-state-reference'; tag = 'kannaka-brain-7b-v2-serve'; temp = 0.2 },
    @{ name = 'e2s-prod-baseline';      arm = 'baseline';           tag = 'kannaka-brain-7b-v2';       temp = 0.8 }
)

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

Stop-Serves
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
    $subscribed = $false
    for ($i = 0; $i -lt 60 -and -not $subscribed; $i++) {
        Start-Sleep 2
        $subscribed = [bool](Select-String -Path "$logs\$name.err.log" -Pattern 'subscribing to KANNAKA.ask.flaukowski' -SimpleMatch -ErrorAction SilentlyContinue)
    }
    if (-not $subscribed) { Stop-Serves; throw "$name : serve never subscribed" }
    # smoke ask (not a probe item), then the loaded tag must be this cell's
    python -c "import asyncio,json,os,nats`nasync def m():`n    nc=await nats.connect('nats://swarm.ninja-portal.com:4222',user=os.environ['NATS_USER'],password=os.environ['NATS_PASSWORD'])`n    r=await nc.request('KANNAKA.ask.flaukowski',json.dumps({'from':'$name-smoke','text':'Record excerpt:\nThe build passed on runner r3.\n\nQuestion: What time did the build pass?','mode':'no_recall'}).encode(),timeout=180)`n    print('smoke:',json.loads(r.data).get('text'))`n    await nc.close()`nasyncio.run(m())"
    $ps = (ollama ps | Out-String)
    if ($ps -notmatch [regex]::Escape("$($c.tag):latest")) { Stop-Serves; throw "$name : ollama ps does not show $($c.tag): $ps" }
    "ollama ps ok: $($c.tag)"
    Set-Location $root
    python brain_probe.py probe-v1-items.json --sha256 $V1 --out "runs/$name-v1.jsonl" --arms B --b-temp $c.temp --serve-model $c.tag
    if ($LASTEXITCODE -ne 0) { Stop-Serves; throw "$name v1 failed" }
    python brain_probe.py probe-v2-items.json --sha256 $V2 --out "runs/$name-v2.jsonl" --arms B --b-temp $c.temp --serve-model $c.tag
    if ($LASTEXITCODE -ne 0) { Stop-Serves; throw "$name v2 failed" }
    $restarts = (Select-String -Path "$logs\$name.err.log" -Pattern 'restarting to serve the fresh mind' -SimpleMatch).Count
    if ($restarts -gt 0 -or $p.HasExited) { Stop-Serves; throw "$name : serve restarted or exited during the cell; rows are not from one serve" }
    Stop-Serves
    $asks = (Select-String -Path "$logs\$name.err.log" -Pattern 'directed from probe-' -SimpleMatch).Count
    "$name done: $asks probe asks in the serve log (expect 240)"
}
Remove-Item env:KANNAKA_SERVE_PROMPT_ARM
"snapshot kannaka.hrm sha256 at end $((Get-FileHash "$snap\kannaka.hrm").Hash.ToLower())"
"ALL DONE"
Stop-Transcript | Out-Null
