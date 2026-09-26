<#
Registers a Windows scheduled task that runs `wnba update --push` every day:
fetch the latest final scores, rebuild the database, then commit any changed
files in data/raw and push them to GitHub. Re-run to change the settings.

    .\scripts\schedule_daily_update.ps1              # daily at 9:00 AM, with push
    .\scripts\schedule_daily_update.ps1 -Time 11:30
    .\scripts\schedule_daily_update.ps1 -NoPush      # update the database only

Check it:   Get-Content data\update.log -Tail 5
Run now:    Start-ScheduledTask -TaskName "wnba-analytics daily update"
Remove:     Unregister-ScheduledTask -TaskName "wnba-analytics daily update"
#>
param([string]$Time = "09:00", [switch]$NoPush)

$ErrorActionPreference = "Stop"
$TaskName = "wnba-analytics daily update"
$repo = Split-Path -Parent $PSScriptRoot
# pythonw has no console window, so the task doesn't flash one every morning.
$pythonw = Join-Path $repo ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "No virtualenv at $pythonw. Create it first (see README)." }

$arguments = if ($NoPush) { "-m wnba update" } else { "-m wnba update --push" }
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $arguments -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
# Catch up if the PC was off or asleep at $Time, and don't skip runs on battery.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force `
    -Description "Fetch new WNBA games and rebuild $repo\data\wnba.db" | Out-Null
Write-Output "Scheduled '$TaskName' daily at $Time (wnba $($arguments.Substring(8))). Log: $repo\data\update.log"
