# =============================================================================
# Meta ETL — Accounts + Insights Sync (every 2 hours)
# Fetches accounts metadata + rolling 7-day insights, syncs to BigQuery,
# and rebuilds fact_meta_ads_combined.
#
# Schedule: every 2 hours (registered by setup_task.ps1)
# =============================================================================

$ProjectDir = "C:\Users\ASUS\Desktop\facebook_etl_new_big"
$Python     = "python"
$LogDir     = "$ProjectDir\logs"
$LogFile    = "$LogDir\accounts_insights_$(Get-Date -Format 'yyyy-MM-dd').log"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# Rotate logs older than 30 days
Get-ChildItem "$LogDir\accounts_insights_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force

Set-Location $ProjectDir

$StartTime = Get-Date
"========================================" | Tee-Object -FilePath $LogFile -Append
"Meta ETL Accounts+Insights — $StartTime" | Tee-Object -FilePath $LogFile -Append
"========================================" | Tee-Object -FilePath $LogFile -Append

& $Python main.py accounts-insights --to-bigquery 2>&1 | Tee-Object -FilePath $LogFile -Append

$ExitCode = $LASTEXITCODE
$EndTime  = Get-Date
$Duration = ($EndTime - $StartTime).TotalMinutes

"" | Tee-Object -FilePath $LogFile -Append
"Finished at $EndTime  (duration: $([math]::Round($Duration,1)) min)  exit=$ExitCode" |
    Tee-Object -FilePath $LogFile -Append

exit $ExitCode
