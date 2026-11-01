# Home

Browser access to this Windows Home computer over the local network.

Open **https://192.168.0.12:8443** from a device on the same Wi-Fi/LAN. The locally issued HTTPS certificate produces a browser warning: confirm the address before continuing. Enter the desktop password from `lan-desktop/credentials.txt` on the host computer. This password is separate from the Windows sign-in password.

## How it works

The browser runs noVNC. A small Node HTTPS/WebSocket gateway forwards its connection to TightVNC on loopback port 5900. TightVNC shares and controls the actual Windows desktop, including on Windows Home. No cloud service, account, Docker, Python, or port forwarding is needed at runtime.

Dependencies are limited to TightVNC 2.8.90, noVNC 1.6.0, Node.js, and the `ws` WebSocket package. `ws` has no required package dependencies. The standard desktop protocol and WebSocket implementation are reused rather than implementing a new remote-control protocol. Git for Windows' OpenSSL is used only to generate the certificate during preparation. Preparation needs internet access; normal LAN use does not.

## Install on this computer

Prerequisites: Windows x64, Node.js/npm, and Git for Windows. The configuration currently targets `192.168.0.12` and subnet `192.168.0.0/24`. Reserve that address in your router. For a different subnet, update the certificate address in `prepare.ps1`, the allowlist in `server.cjs`, and the address/firewall rule in `setup.ps1`.

```powershell
cd lan-desktop
.\prepare.ps1
```

Then run `setup.ps1` from an administrator PowerShell. It installs the signed TightVNC server, generates passwords, limits VNC connections to loopback, adds a firewall rule for TCP 8443 from `192.168.0.0/24`, and registers the gateway as a Windows startup task. Keep the folder in its installed location. The Windows desktop service and HTTPS gateway start automatically after reboot. The computer must be awake.

```powershell
.\setup.ps1
node .\verify.cjs
```

Run setup once: rerunning it rotates passwords and reinstalls server configuration. The verification checks the HTTPS page and performs a password-authenticated VNC handshake through WebSockets, reporting the desktop dimensions. It does not move the mouse or type on the desktop. A test from a second LAN device is still required to verify that device's network path.

## Access and maintenance

- Credentials and the HTTPS private key stay on the host and are excluded from Git.
- HTTPS protects the browser connection; the VNC connection stays on loopback. VNC uses its legacy eight-character password authentication inside that encrypted connection.
- The gateway rejects connections from outside the configured subnet. Do not forward the port on the router.
- The certificate expires after 365 days. Renew it locally and restart the `LAN Browser Desktop` scheduled task.
- `Stop-ScheduledTask -TaskName 'LAN Browser Desktop'` stops browser access. `Start-ScheduledTask -TaskName 'LAN Browser Desktop'` restarts it. These commands may require administrator rights.
- Run `lan-desktop/uninstall.ps1` as administrator to remove the task, firewall rule, and TightVNC. This assumes TightVNC was installed by this project.

Upstream projects: [TightVNC](https://www.tightvnc.com/), [noVNC](https://github.com/novnc/noVNC), [ws](https://github.com/websockets/ws). Their licenses apply to downloaded components; their binaries and source trees are not committed here.
