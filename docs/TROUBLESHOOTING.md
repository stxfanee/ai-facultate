# Troubleshooting

## App opens an old Cloudflare link

Run the newest `Co-pilot Facultate.exe`. On the server PC, temporary `trycloudflare.com` links are detected and the app switches back to Server Mode to generate a fresh link.

## Streamlit frontend cannot load

Use **Reload app** first. If the problem appeared after a rebuild/update, use **Clear WebView cache and reload**.

## Server is unavailable

Check that the desktop server PC is on and Server Mode is running. If using Cloudflare Quick Tunnel, remember that temporary URLs change whenever the tunnel restarts.

## Build does not create Setup.exe

Install Inno Setup 6 or upload the portable `dist\Co-pilot Facultate.exe` manually to GitHub Releases.
