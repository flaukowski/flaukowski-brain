# seat.ps1 — keep one process of Flaukowski's NATS seat alive.
#
#   powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File seat.ps1 -Role join
#   Roles: join (swarm join: presence + metrics), serve (inbox serve, observe-only),
#          tail (inbox tail on KANNAKA.inbox.audit)
#
# The seat dies whenever the broker resets the connection (os error 10054) and the
# CLI exits "for restart" without restarting. This loop restarts it with a backoff
# that resets once a run has lived five minutes. Credentials come from the User env
# (NATS_USER / NATS_PASSWORD / KANNAKA_NATS_URL, set with setx); they are never
# written to the logs. Logs: ~/.kannaka/logs/<role>.<stamp>.{out,err}.log
param(
    [Parameter(Mandatory = $true)][ValidateSet('join', 'serve', 'tail')][string]$Role
)

$exe = "$HOME\.local\bin\kannaka.exe"
$logDir = "$HOME\.kannaka\logs"
$cliArgs = @{ join = 'swarm join'; serve = 'inbox serve'; tail = 'inbox tail' }[$Role]
$logName = @{ join = 'join'; serve = 'inbox-serve'; tail = 'inbox-tail' }[$Role]

foreach ($k in 'NATS_USER', 'NATS_PASSWORD', 'KANNAKA_NATS_URL') {
    $v = [Environment]::GetEnvironmentVariable($k, 'User')
    if ($v) { Set-Item -Path "env:$k" -Value $v }
}
if (-not $env:NATS_USER -or -not $env:NATS_PASSWORD) { throw "NATS seat credentials missing from the User env" }

New-Item -ItemType Directory -Force $logDir | Out-Null
$backoff = 5
while ($true) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $out = "$logDir\$logName.$stamp.out.log"
    $err = "$logDir\$logName.$stamp.err.log"
    $started = Get-Date
    $p = Start-Process -FilePath $exe -ArgumentList $cliArgs -NoNewWindow -PassThru -Wait `
        -RedirectStandardOutput $out -RedirectStandardError $err
    $lived = [int]((Get-Date) - $started).TotalSeconds
    if ($lived -gt 300) { $backoff = 5 } else { $backoff = [Math]::Min($backoff * 2, 300) }
    Add-Content $err "[supervisor] $cliArgs exited $($p.ExitCode) after ${lived}s; restarting in ${backoff}s"
    Start-Sleep -Seconds $backoff
}
