# Run as administrator. Downloaded files and saved credentials remain on disk.
$ErrorActionPreference = 'Stop'
Stop-ScheduledTask -TaskName 'LAN Browser Desktop' -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'LAN Browser Desktop' -Confirm:$false -ErrorAction SilentlyContinue
Get-NetFirewallRule -DisplayName 'LAN Browser Desktop HTTPS' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
$result = Start-Process msiexec.exe -ArgumentList @('/x', "`"$PSScriptRoot\tightvnc.msi`"", '/quiet', '/norestart') -Wait -PassThru -WindowStyle Hidden
if ($result.ExitCode -notin @(0,3010)) {throw "Uninstall failed: $($result.ExitCode)"}
