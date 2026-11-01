# Working checkpoint

The owner confirmed that browser desktop access and the fallback dot cursor work on 2026-11-01. Performance is usable but slower than Chrome Remote Desktop.

This checkpoint uses TightVNC 2.8.90, noVNC 1.6.0, Node.js, and ws 8.22.1. The host uses software capture (`UseD3D=0`, `UseMirrorDriver=0`). The password-protected HTTPS gateway is available to `192.168.0.0/24` on port 8443. Credentials and the private key remain local.

The `working-vnc-baseline` Git tag preserves this revision before further performance tuning. It describes the source checkpoint, not a backup of Windows registry or power settings. Later tuning saves those settings locally for restoration.
