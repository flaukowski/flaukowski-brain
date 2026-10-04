# E4 slice re-run for the two serve cells. The first run put 360 asks through each serve, past its
# 300-asks/hour total limit, so the last ~60 slice asks came back "[error] rate limited". Those files are
# kept as INVALID-*. Here only the slice is re-run, with the total limit raised via the serve's own
# KANNAKA_SERVE_ASKS_PER_HOUR_TOTAL (admission only: prompt, model and arm are unchanged), and the ask
# count and the error count are HARD gates: the cell throws instead of printing a mismatch.
$ErrorActionPreference = 'Stop'
$root = 'C:\Users\nflach\source\flaukowski-brain'
$bin = 'C:\Users\nflach\AppData\Local\Temp\claude\C--Windows-System32\928d7661-9c22-4174-ad5c-1c935d87cee6\scratchpad\km\kannaka-memory\target\release\kannaka.exe'
$logs = "$env:USERPROFILE\.kannaka\logs"
$snap = "$env:USERPROFILE\.kannaka-e2"
$cfg = "$snap\config.toml"
$SL = 'b3c30d39c928d50022a145798556148db89a7608f2c67a8ab7482c51f0a43ff9'
foreach ($n in 'NATS_USER', 'NATS_PASSWORD', 'KANNAKA_NATS_URL') { Set-Item "env:$n" ([Environment]::GetEnvironmentVariable($n, 'User')) }
$env:PYTHONIOENCODING = 'utf-8'
$env:KANNAKA_SERVE_ASKS_PER_HOUR_TOTAL = '1000'
Start-Transcript -Path "$root\logs\run_e4_slice_rerun.transcript.txt" -Append | Out-Null
$h0 = (Get-FileHash "$snap\kannaka.hrm").Hash.ToLower()
if ($h0 -ne 'ae566fd8249ce6f7773bf101c6c844705102ff3836be1b345401f64d48e61c6d') { throw "snapshot changed since E2" }
$env:KANNAKA_DATA_DIR = $snap

$cells = @(
    @{ name = 'e4-serve-slice-r2'; arm = 'baseline'; tag = 'kannaka-brain-e4-serve'; temp = 0.2 },
    @{ name = 'e4-prod-slice-r2';  arm = 'baseline'; tag = 'kannaka-brain-e4';       temp = 0.8 }
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
    Set-Location $root
    python brain_probe.py probe-slice-e4-items.json --sha256 $SL --out "runs/$name.jsonl" --arms B --b-temp $c.temp --serve-model $c.tag
    if ($LASTEXITCODE -ne 0) { Stop-Serves; throw "$name slice failed" }
    $restarts = (Select-String -Path "$logs\$name.err.log" -Pattern 'restarting to serve the fresh mind' -SimpleMatch).Count
    if ($restarts -gt 0 -or $p.HasExited) { Stop-Serves; throw "$name : serve restarted or exited" }
    Stop-Serves
    $asks = (Select-String -Path "$logs\$name.err.log" -Pattern 'directed from probe-' -SimpleMatch).Count
    $errs = (Select-String -Path "runs\$name.jsonl" -Pattern '[error]' -SimpleMatch).Count
    "$name : $asks probe asks (need 120), $errs error answers (need 0)"
    if ($asks -ne 120 -or $errs -ne 0) { throw "$name failed its gates: asks $asks, errors $errs" }
}
"snapshot at end $((Get-FileHash "$snap\kannaka.hrm").Hash.ToLower())"
"ALL DONE"
Stop-Transcript | Out-Null
