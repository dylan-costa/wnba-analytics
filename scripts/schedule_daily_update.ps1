<#
Registers a Windows scheduled task that runs `wnba update` every day, so the
database always has the latest final scores. Re-run to change the time.

    .\scripts\schedule_daily_update.ps1              # daily at 9:00 AM
    .\scripts\schedule_daily_update.ps1 -Time 11:30

Check it:   Get-Content data\update.log -Tail 5
Run now:    Start-ScheduledTask -TaskName "wnba-analytics daily update"
Remove:     Unregister-ScheduledTask -TaskName "wnba-analytics daily update"
#>
param([string]$Time = "09:00")

$ErrorActionPreference = "Stop"
$TaskName = "wnba-analytics daily update"
$repo = Split-Path -Parent $PSScriptRoot
# pythonw has no console window, so the task doesn't flash one every morning.
$pythonw = Join-Path $repo ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "No virtualenv at $pythonw. Create it first (see README)." }

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-m wnba update" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
# Catch up if the PC was off or asleep at $Time, and don't skip runs on battery.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force `
    -Description "Fetch new WNBA games and rebuild $repo\data\wnba.db" | Out-Null
Write-Output "Scheduled '$TaskName' daily at $Time. Log: $repo\data\update.log"
