# =============================================================================
# Run this ONCE as Administrator to register both scheduled tasks.
# Right-click PowerShell → "Run as Administrator", then:
#   cd C:\Users\ASUS\Desktop\facebook_etl_new_big
#   .\scripts\setup_task.ps1
#
# Tasks registered:
#   MetaETL_AccountsInsights  — every 2 hours (08:00–22:00): accounts + insights + BQ sync
#   MetaETL_DimsRefresh       — daily at 02:00 PM: dims + BQ sync
# =============================================================================

$ProjectDir = "C:\Users\ASUS\Desktop\facebook_etl_new_big"

# ---------------------------------------------------------------------------
# Helper: register (or replace) a single scheduled task
# ---------------------------------------------------------------------------
function Register-EtlTask {
    param(
        [string]$TaskName,
        [string]$Script,
        [object]$Trigger,
        [string]$Description
    )

    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed existing task '$TaskName'."
    }

    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$Script`"" `
        -WorkingDirectory $ProjectDir

    $Settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
        -RestartCount 1 `
        -RestartInterval (New-TimeSpan -Minutes 30) `
        -StartWhenAvailable `
        -WakeToRun:$false

    Register-ScheduledTask `1
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -RunLevel Highest `
        -Description $Description |
        Out-Null

    Write-Host "  Registered: $TaskName"
}

# ---------------------------------------------------------------------------
# Remove legacy single-daily task if it exists
# ---------------------------------------------------------------------------
if (Get-ScheduledTask -TaskName "MetaETL_DailySync" -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName "MetaETL_DailySync" -Confirm:$false
    Write-Host "Removed legacy task 'MetaETL_DailySync'."
}

# ---------------------------------------------------------------------------
# Task 1: Accounts + Insights  — every 2 hours, 08:00 to 22:00
# ---------------------------------------------------------------------------
$triggers2h = @()
for ($h = 8; $h -le 22; $h += 2) {
    $timeStr = "{0:D2}:00" -f $h
    $triggers2h += New-ScheduledTaskTrigger -Daily -At $timeStr
}

Register-EtlTask `
    -TaskName   "MetaETL_AccountsInsights" `
    -Script     "$ProjectDir\scripts\accounts_insights_sync.ps1" `
    -Trigger    $triggers2h[0] `
    -Description "Meta Ads ETL: accounts metadata + rolling 7-day insights + BigQuery sync (every 2 hours, 08:00-22:00)"

# Add remaining time triggers + a logon trigger (runs on login if a scheduled run was missed)
$task = Get-ScheduledTask -TaskName "MetaETL_AccountsInsights"
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn
$allTriggers = $task.Triggers + $triggers2h[1..($triggers2h.Count - 1)] + $logonTrigger
Set-ScheduledTask -TaskName "MetaETL_AccountsInsights" -Trigger $allTriggers | Out-Null

# ---------------------------------------------------------------------------
# Task 2: Dims Refresh  — once daily at 09:00 AM
# ---------------------------------------------------------------------------
$dimsTriggers = @(
    (New-ScheduledTaskTrigger -Daily -At "10:00"),
    (New-ScheduledTaskTrigger -AtLogOn)
)
Register-EtlTask `
    -TaskName   "MetaETL_DimsRefresh" `
    -Script     "$ProjectDir\scripts\dims_sync.ps1" `
    -Trigger    $dimsTriggers[0] `
    -Description "Meta Ads ETL: campaigns / adsets / ads / creatives metadata + BigQuery sync (daily 10:00)"

$task2 = Get-ScheduledTask -TaskName "MetaETL_DimsRefresh"
Set-ScheduledTask -TaskName "MetaETL_DimsRefresh" -Trigger ($task2.Triggers + $dimsTriggers[1]) | Out-Null

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "========================================"
Write-Host "Scheduled tasks registered successfully."
Write-Host "========================================"
Write-Host ""
Write-Host "  MetaETL_AccountsInsights"
Write-Host "    Runs every 2 hours (08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00)"
Write-Host "    Script: $ProjectDir\scripts\accounts_insights_sync.ps1"
Write-Host "    Logs:   $ProjectDir\logs\accounts_insights_<date>.log"
Write-Host ""
Write-Host "  MetaETL_DimsRefresh"
Write-Host "    Runs daily at 10:00 AM (or on login if missed)"
Write-Host "    Script: $ProjectDir\scripts\dims_sync.ps1"
Write-Host "    Logs:   $ProjectDir\logs\dims_sync_<date>.log"
Write-Host ""
Write-Host "Useful commands:"
Write-Host "  Start-ScheduledTask -TaskName 'MetaETL_AccountsInsights'"
Write-Host "  Start-ScheduledTask -TaskName 'MetaETL_DimsRefresh'"
Write-Host "  Get-ScheduledTaskInfo -TaskName 'MetaETL_AccountsInsights'"
Write-Host "  Get-ScheduledTaskInfo -TaskName 'MetaETL_DimsRefresh'"
Write-Host "  Unregister-ScheduledTask -TaskName 'MetaETL_AccountsInsights' -Confirm:`$false"
Write-Host "  Unregister-ScheduledTask -TaskName 'MetaETL_DimsRefresh' -Confirm:`$false"
