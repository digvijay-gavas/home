$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Invoke-WebRequest 'https://www.tightvnc.com/download/2.8.90/tightvnc-2.8.90-gpl-setup-64bit.msi' -OutFile "$PSScriptRoot\tightvnc.msi"
$signature = Get-AuthenticodeSignature "$PSScriptRoot\tightvnc.msi"
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'OOO GlavSoft') {throw 'TightVNC installer signature verification failed.'}
Invoke-WebRequest 'https://github.com/novnc/noVNC/archive/refs/tags/v1.6.0.zip' -OutFile "$PSScriptRoot\novnc.zip"
Expand-Archive "$PSScriptRoot\novnc.zip" $PSScriptRoot -Force
$uiPath = "$PSScriptRoot\noVNC-1.6.0\app\ui.js"
$uiSource = [System.IO.File]::ReadAllText($uiPath).Replace("UI.initSetting('show_dot', false);", "UI.initSetting('show_dot', true);")
[System.IO.File]::WriteAllText($uiPath, $uiSource)
& npm.cmd ci --omit=dev --no-audit --no-fund
if ($LASTEXITCODE -ne 0) {throw 'Dependency installation failed.'}
$openssl = 'C:\Program Files\Git\usr\bin\openssl.exe'
if (-not (Test-Path $openssl)) {throw 'OpenSSL is required to generate the local HTTPS certificate (included with Git for Windows).'}
if ((Test-Path server.key) -or (Test-Path server.crt)) {throw 'Existing certificate found. Keep it, or move it before generating another.'}
& $openssl req -x509 -newkey rsa:2048 -nodes -keyout server.key -out server.crt -days 365 -subj '/CN=LAN Desktop' -addext 'subjectAltName=IP:192.168.0.12,DNS:localhost'
if ($LASTEXITCODE -ne 0) {throw 'Certificate generation failed.'}
Write-Output 'Prepared. Run setup.ps1 as administrator to install and start the service.'
