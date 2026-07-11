# Legacy entry points

The root BAT/PowerShell scripts are still kept for compatibility:

- `start_server.bat`
- `START_CLOUDFLARE_TUNNEL.bat`
- `START_PUBLIC_TAILSCALE.bat`
- `build_client.bat`
- `build_desktop_client.bat`
- `build_server_launcher.bat`
- `build_copilot_facultate.bat`

New product-oriented entry points live in:

- `scripts/build/`
- `scripts/start/`
- `scripts/diagnostics/`

Do not delete legacy scripts until all tests, documentation and user workflows no longer reference them.
