param(
  [string]$InputHtml = "C:\Users\cduff\AppData\Local\Temp\7ae3cef4-5c11-48a3-ac1e-969485367da8_vl-rank-changes-2026-07-10.zip.da8\Sheet1.html",
  [string]$OutputCsv = "C:\Users\cduff\pnf\vl-rank-changes-2026-07-10-pnf.csv"
)

$ErrorActionPreference = "Stop"

function Convert-HtmlCellText {
  param([string]$Text)
  $decoded = [System.Net.WebUtility]::HtmlDecode($Text)
  return ($decoded -replace '<[^>]+>', '').Trim()
}

$html = Get-Content -LiteralPath $InputHtml -Raw
$rows = [regex]::Matches($html, '<tr\b[^>]*>(.*?)</tr>', 'Singleline')
$items = foreach ($row in $rows) {
  $cells = [regex]::Matches($row.Groups[1].Value, '<td\b[^>]*>(.*?)</td>', 'Singleline')
  if ($cells.Count -ge 4) {
    [pscustomobject]@{
      Ticker = Convert-HtmlCellText $cells[0].Groups[1].Value
      Name = Convert-HtmlCellText $cells[1].Groups[1].Value
      Curr = Convert-HtmlCellText $cells[2].Groups[1].Value
      Last = Convert-HtmlCellText $cells[3].Groups[1].Value
    }
  }
}

$items = $items | Where-Object { $_.Ticker -and $_.Ticker -ne 'TICKER' }
$total = @($items).Count
$index = 0

$results = foreach ($item in $items) {
  $index++
  Write-Progress -Activity "Running pnf" -Status "$index of ${total}: $($item.Ticker)" -PercentComplete (($index / $total) * 100)

  $stdout = $null
  $stderr = $null
  $errorMessage = $null
  $pnf = $null
  $pnfTicker = switch ($item.Ticker) {
    "BFB" { "BF-B"; break }
    "MOGA" { "MOG-A"; break }
    default { $item.Ticker }
  }

  if ($item.Ticker -like "*.TO") {
    $errorMessage = "Skipped Canadian ticker"
  } else {
    try {
      $stdout = & pnf $pnfTicker --json 2>&1
      if ($LASTEXITCODE -ne 0) {
        $errorMessage = ($stdout | Out-String).Trim()
      } else {
        $pnf = ($stdout | Out-String | ConvertFrom-Json)
      }
    } catch {
      $stderr = $_.Exception.Message
      $errorMessage = $stderr
    }
  }

  [pscustomobject]@{
    Ticker = $item.Ticker
    Name = $item.Name
    Curr = $item.Curr
    Last = $item.Last
    PnfDate = $pnf.date
    Close = $pnf.close
    Status = $pnf.status
    Pattern = $pnf.pattern
    SignalDate = $pnf.signal_date
    Trigger = $pnf.trigger
    Objective = $pnf.objective
    ObjectiveActive = $pnf.objective_active
    Stop = $pnf.stop
    Reward = $pnf.reward
    Risk = $pnf.risk
    RewardRisk = $pnf.rr
    Trend = $pnf.trend
    Reversal = $pnf.reversal
    Note = $pnf.note
    Error = $errorMessage
  }
}

$results | Export-Csv -LiteralPath $OutputCsv -NoTypeInformation -Encoding utf8
Write-Progress -Activity "Running pnf" -Completed
Write-Output $OutputCsv
