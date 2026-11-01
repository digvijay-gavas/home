$ErrorActionPreference = 'Stop'
$base = $PSScriptRoot
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Run this setup as administrator.' }
$password = -join ((48..57)+(65..90)+(97..122) | Get-Random -Count 8 | ForEach-Object {[char]$_})
$adminPassword = [guid]::NewGuid().ToString('N').Substring(0,16)
$argsList = @('/i', "`"$base\tightvnc.msi`"", '/quiet', '/norestart', 'ADDLOCAL=Server', 'SERVER_REGISTER_AS_SERVICE=1', 'SERVER_ADD_FIREWALL_EXCEPTION=0', 'SET_ACCEPTHTTPCONNECTIONS=1', 'VALUE_OF_ACCEPTHTTPCONNECTIONS=0', 'SET_ALLOWLOOPBACK=1', 'VALUE_OF_ALLOWLOOPBACK=1', 'SET_LOOPBACKONLY=1', 'VALUE_OF_LOOPBACKONLY=1', 'SET_USEVNCAUTHENTICATION=1', 'VALUE_OF_USEVNCAUTHENTICATION=1', 'SET_PASSWORD=1', "VALUE_OF_PASSWORD=$password", 'SET_USECONTROLAUTHENTICATION=1', 'VALUE_OF_USECONTROLAUTHENTICATION=1', 'SET_CONTROLPASSWORD=1', "VALUE_OF_CONTROLPASSWORD=$adminPassword")
$installer = Start-Process msiexec.exe -ArgumentList $argsList -PassThru -Wait -WindowStyle Hidden
if ($installer.ExitCode -notin @(0,3010)) {throw "Installer failed: $($installer.ExitCode)"}
@("URL: https://192.168.0.12:8443", "Desktop password: $password", "VNC settings password: $adminPassword") | Set-Content "$base\credentials.txt"
& icacls.exe "$base\credentials.txt" /inheritance:r /grant:r "$($identity.User.Value):(F)" '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' | Out-Null
& icacls.exe "$base\server.key" /inheritance:r /grant:r "$($identity.User.Value):(F)" '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' | Out-Null
New-NetFirewallRule -DisplayName 'LAN Browser Desktop HTTPS' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8443 -RemoteAddress '192.168.0.0/24' -Profile Any | Out-Null
$action = New-ScheduledTaskAction -Execute 'C:\Program Files\nodejs\node.exe' -Argument "`"$base\server.cjs`"" -WorkingDirectory $base
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'LAN Browser Desktop' -Action $action -Trigger $trigger -Settings $settings -User SYSTEM -RunLevel Highest -Force | Out-Null
Start-Service tvnserver
Start-ScheduledTask -TaskName 'LAN Browser Desktop'
& "$base\optimize.ps1"
Write-Output 'Setup complete. Credentials saved in credentials.txt.'
