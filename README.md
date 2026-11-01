# Home

Browser access to this Windows Home computer over the local network.

Open **https://192.168.0.12:8443** from a device on the same Wi-Fi/LAN. The locally issued HTTPS certificate produces a browser warning: confirm the address before continuing. Enter the desktop password from `lan-desktop/credentials.txt` on the host computer. This password is separate from the Windows sign-in password.

The browser enables a dot cursor when Windows does not provide a visible pointer. For an existing browser session, enable **Settings → Show Dot when No Cursor** or reopen the main URL. The main URL selects LAN settings: quality 4/9 and compression 1/9. These favor responsiveness over fine image detail. Browser scaling does not change the physical display resolution.

## How it works

The browser runs noVNC. A small Node HTTPS/WebSocket gateway forwards its connection to TightVNC on loopback port 5900. TightVNC shares and controls the actual Windows desktop, including on Windows Home. No cloud service, account, Docker, Python, or port forwarding is needed at runtime.

Dependencies are limited to TightVNC 2.8.90, noVNC 1.6.0, Node.js, and the `ws` WebSocket package. `ws` has no required package dependencies. The standard desktop protocol and WebSocket implementation are reused rather than implementing a new remote-control protocol. Git for Windows' OpenSSL is used only to generate the certificate during preparation. Preparation needs internet access; normal LAN use does not.

## Install on this computer

Prerequisites: Windows x64, Node.js/npm, and Git for Windows. The configuration currently targets `192.168.0.12` and subnet `192.168.0.0/24`. Reserve that address in your router. For a different subnet, update the certificate address in `prepare.ps1`, the allowlist in `server.cjs`, and the address/firewall rule in `setup.ps1`.

```powershell
cd lan-desktop
.\prepare.ps1
```

Then run `setup.ps1` from an administrator PowerShell. It installs the signed TightVNC server, generates passwords, limits VNC connections to loopback, adds a firewall rule for TCP 8443 from `192.168.0.0/24`, and applies `optimize.ps1` to configure performance and startup. Keep the folder in its installed location. Both components start at boot without requiring an interactive sign-in. Windows' PIN/password remains required to unlock the desktop.

```powershell
.\setup.ps1
node .\verify.cjs
```

Run setup once: rerunning it rotates passwords and reinstalls server configuration. To tune an existing installation without rotating passwords, run `optimize.ps1` as administrator instead. The verification checks the HTTPS page and authenticates VNC through WebSockets, then waits up to 15 seconds for non-black screen pixels. VNC can send an initial black placeholder during capture startup, so a single black frame does not establish a capture failure. The check reports startup timing, not ongoing frame rate, and sends no keyboard/mouse input. A real all-black screen can make the pixel check time out. A second LAN device is still required to verify that device's network path and perceived responsiveness.

## Performance and unattended access

The `working-vnc-baseline` tag preserves the confirmed working version before tuning. No new runtime dependencies were added by the tuning.

- Software capture stays enabled because it resolved this computer's black screen. Its fallback screen-polling interval is 100 ms, down from the documented default of 1000 ms. This increases capture activity and can use more CPU; it is not a guarantee of a particular frame rate. See [TightVNC's polling option](https://www.tightvnc.com/doc/win/TightVNC-installer-2.5.2.pdf).
- Browser defaults use quality 4 and compression 1. Existing URLs with explicit quality/compression override these defaults. Reopen the main URL after applying the settings.
- The gateway disables TCP delay for small messages, uses stream backpressure, and leaves WebSocket compression disabled because VNC already compresses its updates. Screen resolution and Windows visual effects are unchanged.
- TightVNC uses automatic startup and service recovery after failures. The gateway is a SYSTEM startup task with no execution time limit, catch-up startup enabled, and up to 999 restart attempts at one-minute intervals. It can run without a signed-in user.
- While plugged in, idle sleep and hibernation are disabled. Battery sleep settings, display timeout, lid-close behavior, Windows sign-in, and existing network restrictions are unchanged. Keep the machine powered and connected to the LAN; a shutdown, sleep caused by another action, or network loss makes it unreachable. Boot and recovery configuration were inspected; an actual reboot was not performed during setup.
- Reserve `192.168.0.12` in the router for a stable URL. DHCP can otherwise change the address. Router settings are not modified by this project.

`optimize.ps1` saves the previous capture registry values, active power-plan sleep values, and gateway task XML in local `diagnostics-*` files, excluded from Git. `optimize.ps1 -Restore` restores those saved registry/power/task settings; it does not revert the gateway source, browser assets, or VNC recovery policy. For the earlier browser quality, use `quality=6&compression=2` in the URL. The Git tag can be used to review or restore the earlier source.

## Access and maintenance

- Credentials and the HTTPS private key stay on the host and are excluded from Git.
- HTTPS protects the browser connection; the VNC connection stays on loopback. VNC uses its legacy eight-character password authentication inside that encrypted connection.
- The gateway rejects connections from outside the configured subnet. Do not forward the port on the router.
- The certificate expires after 365 days. Renew it locally and restart the `LAN Browser Desktop` scheduled task.
- `Stop-ScheduledTask -TaskName 'LAN Browser Desktop'` stops browser access. `Start-ScheduledTask -TaskName 'LAN Browser Desktop'` restarts it. These commands may require administrator rights.
- Run `lan-desktop/uninstall.ps1` as administrator to remove the task, firewall rule, and TightVNC. This assumes TightVNC was installed by this project.
- If authentication succeeds but the image stays black, run `lan-desktop/repair-capture.ps1` as administrator and reconnect. It disables D3D and mirror-driver capture, saving the previous values locally. Use `-Restore` to restore them. Authentication and Windows sign-in settings are unchanged.

Upstream projects: [TightVNC](https://www.tightvnc.com/), [noVNC](https://github.com/novnc/noVNC), [ws](https://github.com/websockets/ws). Their licenses apply to downloaded components; their binaries and source trees are not committed here.
