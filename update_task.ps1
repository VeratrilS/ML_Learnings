$Task = Get-ScheduledTask -TaskName "Daily Incident Reporter"
$Task.Settings.StartWhenAvailable = $true
Set-ScheduledTask -TaskName "Daily Incident Reporter" -Settings $Task.Settings
