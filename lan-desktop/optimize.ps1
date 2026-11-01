# Run as administrator. Saves existing settings before the first application.
param([switch]$Restore)
$ErrorActionPreference = 'Stop'
$base = $PSScriptRoot
$key = 'HKLM:\SOFTWARE\TightVNC\Server'
$backupPath = "$base\diagnostics-performance-backup.json"
$names = @('PollingInterval', 'UseD3D', 'UseMirrorDriver', 'LogLevel')
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {throw 'Run optimize.ps1 as administrator.'}

function Get-AcPowerIndex([string]$setting) {
    $output = (& powercfg.exe /query SCHEME_CURRENT SUB_SLEEP $setting) -join "`n"
    if ($LASTEXITCODE -ne 0) {throw "Cannot read power setting $setting"}
    $indices = [regex]::Matches($output, '0x([0-9a-fA-F]{8})')
    if ($indices.Count -lt 2) {throw "Cannot parse power setting $setting"}
    return [Convert]::ToUInt32($indices[$indices.Count-2].Groups[1].Value,16)
}

if (-not (Test-Path -LiteralPath $backupPath)) {
    if ($Restore) {throw 'No saved settings are available.'}
    $current = Get-ItemProperty $key
    $registry = @{}
    foreach ($name in $names) {
        $registry[$name] = @{Exists=($null -ne $current.PSObject.Properties[$name]);Value=$current.$name}
    }
    $powerScheme = [regex]::Match((& powercfg.exe /getactivescheme) -join '', '[a-fA-F0-9-]{36}').Value
    if (-not $powerScheme) {throw 'Cannot determine active power scheme.'}
    Export-ScheduledTask -TaskName 'LAN Browser Desktop' | Set-Content "$base\diagnostics-task-backup.xml"
    @{Registry=$registry;PowerScheme=$powerScheme;SleepAc=(Get-AcPowerIndex 'STANDBYIDLE');HibernateAc=(Get-AcPowerIndex 'HIBERNATEIDLE')} | ConvertTo-Json -Depth 4 | Set-Content $backupPath
}

if ($Restore) {
    $backup = Get-Content $backupPath -Raw | ConvertFrom-Json
    foreach ($name in $names) {
        $entry = $backup.Registry.$name
        if ($entry.Exists) {New-ItemProperty $key -Name $name -PropertyType DWord -Value $entry.Value -Force | Out-Null}
        else {Remove-ItemProperty $key -Name $name -ErrorAction SilentlyContinue}
    }
    & powercfg.exe /setacvalueindex $backup.PowerScheme SUB_SLEEP STANDBYIDLE $backup.SleepAc
    & powercfg.exe /setacvalueindex $backup.PowerScheme SUB_SLEEP HIBERNATEIDLE $backup.HibernateAc
    & powercfg.exe /setactive $backup.PowerScheme
    Stop-ScheduledTask -TaskName 'LAN Browser Desktop' -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName 'LAN Browser Desktop' -Xml (Get-Content "$base\diagnostics-task-backup.xml" -Raw) -Force | Out-Null
} else {
    New-ItemProperty $key -Name PollingInterval -PropertyType DWord -Value 100 -Force | Out-Null
    foreach ($name in @('UseD3D','UseMirrorDriver','LogLevel')) {
        New-ItemProperty $key -Name $name -PropertyType DWord -Value 0 -Force | Out-Null
    }
    $uiPath = "$base\noVNC-1.6.0\app\ui.js"
    $ui = [IO.File]::ReadAllText($uiPath).Replace("UI.initSetting('quality', 6);", "UI.initSetting('quality', 4);").Replace("UI.initSetting('compression', 2);", "UI.initSetting('compression', 1);")
    [IO.File]::WriteAllText($uiPath,$ui)
    Set-Service tvnserver -StartupType Automatic
    & sc.exe failure tvnserver reset= 86400 actions= restart/5000/restart/15000/restart/60000 | Out-Null
    if ($LASTEXITCODE -ne 0) {throw 'Cannot configure VNC service recovery.'}
    & powercfg.exe /change standby-timeout-ac 0
    if ($LASTEXITCODE -ne 0) {throw 'Cannot configure plugged-in sleep timeout.'}
    & powercfg.exe /change hibernate-timeout-ac 0
    if ($LASTEXITCODE -ne 0) {throw 'Cannot configure plugged-in hibernate timeout.'}
    $action = New-ScheduledTaskAction -Execute 'C:\Program Files\nodejs\node.exe' -Argument "`"$base\server.cjs`"" -WorkingDirectory $base
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
    Stop-ScheduledTask -TaskName 'LAN Browser Desktop' -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName 'LAN Browser Desktop' -Action $action -Trigger $trigger -Settings $settings -User SYSTEM -RunLevel Highest -Force | Out-Null
}
Restart-Service tvnserver
Start-ScheduledTask -TaskName 'LAN Browser Desktop'
$task = Get-ScheduledTask -TaskName 'LAN Browser Desktop'
@{
    PollingInterval=(Get-ItemProperty $key -Name PollingInterval -ErrorAction SilentlyContinue).PollingInterval
    Service=(Get-Service tvnserver | Select-Object Name,Status,StartType)
    Task=($task | Select-Object TaskName,State)
    StartupTriggers=@($task.Triggers | ForEach-Object {$_.CimClass.CimClassName})
    TaskUser=$task.Principal.UserId
    RestartCount=$task.Settings.RestartCount
    RestartInterval=$task.Settings.RestartInterval
    ExecutionTimeLimit=$task.Settings.ExecutionTimeLimit
    SleepAc=(Get-AcPowerIndex 'STANDBYIDLE')
    HibernateAc=(Get-AcPowerIndex 'HIBERNATEIDLE')
} | ConvertTo-Json -Depth 4 | Set-Content "$base\diagnostics-availability.json"
Write-Output 'Settings applied. Reopen the main URL for the LAN browser defaults.'
