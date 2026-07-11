# Repository audit

Date: 2026-07-12

This audit records the product-oriented repository structure after the cleanup.

## Current structure classification

| Path | Status | Notes |
| --- | --- | --- |
| `README.md` | current | Product landing page for Co-pilot Facultate. |
| `LICENSE` | current | Product license file. |
| `CHANGELOG.md` | current | Human-readable release history. |
| `assets/` | current | Product logo, screenshots, icons and visual resources. |
| `apps/desktop/` | current | Primary unified desktop application. This is the flagship app. |
| `apps/web/app.py` | current infrastructure | Streamlit app used by Server Mode. Root `app.py` is a compatibility shim. |
| `apps/launcher/` | current infrastructure | Windows server control panel used by the unified app. |
| `apps/client/` | legacy-supported | Older lightweight WebView client, retained and tested. |
| `apps/legacy_client/` | legacy-supported | Older client wrapper, retained for compatibility. |
| `server/api/api_server.py` | current infrastructure | FastAPI server. Root `api_server.py` is a compatibility shim. |
| `server/memory/study_memory.py` | current infrastructure | Study memory, progress, notebook and persistence helpers. |
| `server/users/user_accounts.py` | current infrastructure | User profiles, workspaces and isolation helpers. |
| `server/users/manage_users.py` | current infrastructure | User-management helper. |
| `server/queue/request_queue.py` | current infrastructure | Queue/rate/concurrency protection. |
| `server/config/deployment.py` | current infrastructure | URL/deployment/status helpers. |
| `deploy/` | current infrastructure | Reverse proxy and Cloudflare examples. Future target name: `deployment/`. |
| `scripts/build/` | current | Product-oriented build entry points. |
| `scripts/start/` | current | Product-oriented start entry points. |
| `scripts/deployment/` | current | Cloudflare and Tailscale public access scripts. |
| `scripts/diagnostics/` | current | Diagnostics and test scripts. |
| `scripts/maintenance/` | current | Install/maintenance scripts. |
| `scripts/legacy/` | legacy-supported | Old BAT entry points kept away from root for compatibility. |
| `docs/` | current | Technical and product documentation. |
| `.github/workflows/` | current | Release artifact build workflow. |
| `tests/` | current | Existing test suite. |
| `requirements.txt` | current | Python dependencies for server/development. |
| `storage/` | runtime data | Ignored by Git except `.gitkeep`; contains user data, ChromaDB, logs and runtime URLs. |
| `documents/` | runtime/user data | Ignored by Git except `.gitkeep`; local documents. |
| `build/` | generated | Ignored by Git. |
| `dist/` | generated | Ignored by Git; contains release artifacts. |
| `.venv/`, `*/.venv_build/` | generated | Ignored by Git. |
| `__pycache__/` | generated | Ignored by Git. |

## Files moved

| Old path | New path |
| --- | --- |
| `README.md` | `docs/DEVELOPMENT_LEGACY.md` |
| `INSTALL_CLIENT.md` | `docs/CLIENT_LEGACY.md` |
| `desktop_app/` | `apps/desktop/` |
| `desktop_client/` | `apps/client/` |
| `server_launcher/` | `apps/launcher/` |
| `client_app/` | `apps/legacy_client/` |
| `app.py` | `apps/web/app.py` |
| `api_server.py` | `server/api/api_server.py` |
| `study_memory.py` | `server/memory/study_memory.py` |
| `user_accounts.py` | `server/users/user_accounts.py` |
| `request_queue.py` | `server/queue/request_queue.py` |
| `deployment.py` | `server/config/deployment.py` |
| `manage_users.py` | `server/users/manage_users.py` |
| `start_server.bat` | `scripts/legacy/start_server.bat` |
| `START_CLOUDFLARE_TUNNEL.bat` | `scripts/legacy/START_CLOUDFLARE_TUNNEL.bat` |
| `START_PUBLIC_TAILSCALE.bat` | `scripts/legacy/START_PUBLIC_TAILSCALE.bat` |
| `START_AI_STUDY_ASSISTANT.bat` | `scripts/legacy/START_AI_STUDY_ASSISTANT.bat` |
| `build_copilot_facultate.bat` | `scripts/legacy/build_copilot_facultate.bat` |
| `build_client.bat` | `scripts/legacy/build_client.bat` |
| `build_desktop_client.bat` | `scripts/legacy/build_desktop_client.bat` |
| `build_server_launcher.bat` | `scripts/legacy/build_server_launcher.bat` |
| `start_cloudflare_tunnel.ps1` | `scripts/deployment/start_cloudflare_tunnel.ps1` |
| `start_public_tailscale.ps1` | `scripts/deployment/start_public_tailscale.ps1` |
| `install.ps1` | `scripts/maintenance/install.ps1` |
| `server_network_diagnostics.ps1` | `scripts/diagnostics/server_network_diagnostics.ps1` |
| `run_app.ps1` | `scripts/legacy/run_app.ps1` |

## Compatibility shims

The following old module names remain as tiny compatibility aliases so existing tests, scripts and Streamlit/uvicorn commands keep working:

- `app.py`
- `api_server.py`
- `study_memory.py`
- `user_accounts.py`
- `request_queue.py`
- `deployment.py`
- `manage_users.py`
- `desktop_app/`
- `desktop_client/`
- `server_launcher/`
- `client_app/`

## Files deleted

None.

## Files archived

No working files were archived. Legacy scripts were moved to `scripts/legacy/`.

## Reasoning

The repository now presents the desktop application as the primary product while keeping server infrastructure separated under `server/` and application surfaces under `apps/`. Compatibility shims reduce migration risk and preserve existing user-facing behavior.
