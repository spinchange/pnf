# Weekly Bullish Percent report: S&P 500 overall + the 11 SPDR sectors, as
# of Friday's close (or the last trading day before it, when Friday is a
# market holiday; pnf takes that from the price data itself).
#
# Writes reports\bpi\pnf-bpi-<DATE>.txt (report + the BPI's P&F chart) and
# .csv (sector table), then sends a compact summary to Telegram via
# `hermes send`, with the .txt attached. Run by the "pnf weekly BPI"
# scheduled task, Saturdays 8:00 AM; safe to run by hand any day (it always
# reports as of the most recent Friday).
#
# Membership is tape's point-in-time SPDR holdings (`spx_members`), so this
# should run after tape's Friday-evening snapshot.

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$outDir = Join-Path $root "reports\bpi"
$logDir = Join-Path $outDir "logs"
$logFile = Join-Path $logDir ("weekly_bpi_{0}.log" -f (Get-Date -Format "yyyy-MM-dd_HHmmss"))

# Versioned interpreter, not the pyenv shims (they have emptied out before
# and silently broken scheduled jobs; see snowball's cron_nightly.ps1).
$py = Join-Path $env:USERPROFILE ".pyenv\pyenv-win\versions\3.12.10\python.exe"
$hermes = Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\venv\Scripts\hermes.exe"

New-Item -ItemType Directory -Force $logDir | Out-Null

function Send-Telegram([string]$Message) {
    if (-not (Test-Path $hermes)) {
        "WARN: hermes not found at $hermes - no Telegram message sent" | Tee-Object -FilePath $logFile -Append
        return
    }
    & $hermes send --to telegram --quiet $Message *>&1 | Tee-Object -FilePath $logFile -Append
}

try {
    if (-not (Test-Path $py)) { throw "python not found at $py" }

    # Friday's date for the file names; pnf reports the actual session date
    $today = Get-Date
    $friday = $today.AddDays(-((([int]$today.DayOfWeek) - 5 + 7) % 7)).ToString("yyyy-MM-dd")
    $txt = Join-Path $outDir "pnf-bpi-$friday.txt"
    $csv = Join-Path $outDir "pnf-bpi-$friday.csv"

    "INFO: pnf bpi as of $friday" | Tee-Object -FilePath $logFile -Append
    # stderr (progress, warnings) goes to the log; stdout is the JSON
    $json = & $py -m pnf bpi --asof $friday --json --txt $txt --csv $csv 2>> $logFile
    if ($LASTEXITCODE -ne 0) { throw "pnf bpi exited $LASTEXITCODE (see $logFile)" }
    $json | Add-Content $logFile
    $r = ($json | Out-String | ConvertFrom-Json)

    function Fmt-Week($v) { if ($null -eq $v) { "n/a" } else { "{0:+0.0;-0.0;0.0}" -f [double]$v } }

    $lines = @(
        "pnf weekly BPI - as of $($r.date) close"
        "S&P 500: $('{0:0.0}' -f $r.bpi)% ($(Fmt-Week $r.week_change) wk) - $($r.status), $($r.bullish)/$($r.members) on buys"
        ""
    )
    foreach ($s in $r.sectors) {
        $lines += "$($s.etf) $($s.name): $('{0:0.0}' -f $s.bpi) ($(Fmt-Week $s.week_change)) $($s.status)"
    }
    $warnings = @(Get-Content $logFile | Select-String -Pattern '^(warning:|\()' | ForEach-Object { $_.Line })
    if ($warnings.Count -gt 0) { $lines += ""; $lines += $warnings }
    $lines += ""
    $lines += "Members: $($r.membership)"

    Send-Telegram ($lines -join "`n")
    Send-Telegram "MEDIA:$txt"
    "INFO: done - $txt, $csv" | Tee-Object -FilePath $logFile -Append
}
catch {
    "ERROR: $($_.Exception.Message)" | Tee-Object -FilePath $logFile -Append
    Send-Telegram "pnf weekly BPI FAILED: $($_.Exception.Message)"
    exit 1
}
