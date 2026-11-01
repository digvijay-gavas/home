param([switch]$Restore)
$ErrorActionPreference = 'Stop'
$key = 'HKLM:\SOFTWARE\TightVNC\Server'
$backupPath = "$PSScriptRoot\diagnostics-capture-backup.json"
$names = @('UseD3D', 'UseMirrorDriver')
if ($Restore) {
    $backup = Get-Content $backupPath -Raw | ConvertFrom-Json
    foreach ($name in $names) {
        $entry = $backup.$name
        if ($entry.Exists) { New-ItemProperty $key -Name $name -PropertyType DWord -Value $entry.Value -Force | Out-Null }
        else { Remove-ItemProperty $key -Name $name -ErrorAction SilentlyContinue }
    }
} else {
    if (-not (Test-Path $backupPath)) {
        $current = Get-ItemProperty $key
        $backup = @{}
        foreach ($name in $names) {
            $property = $current.PSObject.Properties[$name]
            $backup[$name] = @{Exists=($null -ne $property); Value=$current.$name}
        }
        $backup | ConvertTo-Json -Depth 3 | Set-Content $backupPath
    }
    foreach ($name in $names) { New-ItemProperty $key -Name $name -PropertyType DWord -Value 0 -Force | Out-Null }
}
Restart-Service tvnserver
Write-Output 'Capture configuration updated. Reconnect the browser.'
