# =============================================================================
# Meta ETL — Daily Sync
# Runs once per day: fetches last 7 days of ad data, syncs all tables to
# BigQuery, and rebuilds the combined flat table.
#
# Schedule: daily at 03:00 AM (off-peak, after Meta data is settled)
#
# To register with Windows Task Scheduler, run once as Administrator:
#   scripts\setup_task.ps1
# =============================================================================

$ProjectDir = "C:\Users\ASUS\Desktop\facebook_etl_new_big"
$Python     = "python"   # or full path e.g. "C:\Python\python.exe"
$LogDir     = "$ProjectDir\logs"
$LogFile    = "$LogDir\daily_sync_$(Get-Date -Format 'yyyy-MM-dd').log"

# Create logs directory if it doesn't exist
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# Rotate logs older than 30 days
Get-ChildItem "$LogDir\daily_sync_*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force

Set-Location $ProjectDir

$StartTime = Get-Date
"========================================" | Tee-Object -FilePath $LogFile -Append
"Meta ETL Daily Sync — $StartTime"         | Tee-Object -FilePath $LogFile -Append
"========================================" | Tee-Object -FilePath $LogFile -Append

# Run the full daily pipeline:
#   - Refresh all dim tables (accounts, campaigns, adsets, ads, creatives)
#   - Fetch insights for the last 7 days (rolling window)
#   - Sync all tables to BigQuery
#   - Rebuild fact_meta_ads_combined in BigQuery
& $Python main.py run-daily --to-bigquery 2>&1 | Tee-Object -FilePath $LogFile -Append

$ExitCode = $LASTEXITCODE
$EndTime  = Get-Date
$Duration = ($EndTime - $StartTime).TotalMinutes

"" | Tee-Object -FilePath $LogFile -Append
"Finished at $EndTime  (duration: $([math]::Round($Duration,1)) min)  exit=$ExitCode" |
    Tee-Object -FilePath $LogFile -Append

exit $ExitCode
