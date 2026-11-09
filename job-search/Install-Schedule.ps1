$ErrorActionPreference = 'Stop'
$jobPilotRoot = $PSScriptRoot
$jobPilotPython = Join-Path $jobPilotRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $jobPilotPython)) { throw 'Run Setup.cmd first.' }
$jobPilotAction = New-ScheduledTaskAction -Execute $jobPilotPython -Argument ('"' + (Join-Path $jobPilotRoot 'scheduled_run.py') + '"') -WorkingDirectory $jobPilotRoot
# These triggers use Windows wall time. Convert Cameroon UTC+1 into the host timezone.
$jobPilotTriggers = @()
foreach ($jobPilotHour in @(12,17)) {
  $jobPilotUtc = [DateTime]::SpecifyKind([DateTime]::UtcNow.Date.AddHours($jobPilotHour - 1), [DateTimeKind]::Utc)
  $jobPilotLocal = $jobPilotUtc.ToLocalTime()
  $jobPilotTriggers += New-ScheduledTaskTrigger -Daily -At $jobPilotLocal
}
$jobPilotSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$jobPilotPrincipal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'JobPilot Daily Applications' -Action $jobPilotAction -Trigger $jobPilotTriggers -Settings $jobPilotSettings -Principal $jobPilotPrincipal -Description 'Find and apply for matching jobs at noon and 5 pm Cameroon time.' -Force | Out-Null
Get-ScheduledTaskInfo -TaskName 'JobPilot Daily Applications' | Select-Object NextRunTime, LastRunTime, LastTaskResult
