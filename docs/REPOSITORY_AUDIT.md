# Repository audit

Date: 2026-07-12

This audit records the current repository structure before deeper physical code moves. The goal of this refactor is to make the desktop app the primary product while avoiding risky import/path breakage.

## Classification

| Path | Status | Notes |
| --- | --- | --- |
| `README.md` | current | Rewritten as the product landing page for Co-pilot Facultate. |
| `LICENSE` | current | Product license file. |
| `CHANGELOG.md` | current | Human-readable release history. |
| `desktop_app/` | current | Primary unified desktop application. Keep as flagship implementation. |
| `desktop_app/launcher.py` | current | Main desktop app entry point. |
| `desktop_app/assets/` | current | Runtime icon assets used by PyInstaller. |
| `app.py` | current infrastructure | Streamlit app used by Server Mode. Kept at root for compatibility with existing launchers/tests. |
| `api_server.py` | current infrastructure | FastAPI server used by Server Mode. |
| `study_memory.py` | current infrastructure | Study memory, progress, notebook and persistence helpers. |
| `user_accounts.py` | current infrastructure | User profiles, workspaces and isolation helpers. |
| `request_queue.py` | current infrastructure | Queue/rate/concurrency protection. |
| `deployment.py` | current infrastructure | URL/deployment/status helpers. |
| `server_launcher/` | current infrastructure | Windows server control panel used by unified app. |
| `desktop_client/` | legacy-supported | Older lightweight WebView client; still tested and retained. |
| `client_app/` | legacy-supported | Older client wrapper; retained for compatibility. |
| `deploy/` | current infrastructure | Reverse proxy and Cloudflare examples. Future target name: `deployment/`. |
| `tests/` | current | Existing test suite. |
| `requirements.txt` | current | Python dependencies for server/development. |
| `install.ps1`, `run_app.ps1` | legacy-supported | Manual developer/server scripts. |
| `start_server.bat` | legacy-supported | Manual server start wrapper; new preferred wrapper is `scripts/start/start_local_server.bat`. |
| `START_CLOUDFLARE_TUNNEL.bat` | legacy-supported | Manual Cloudflare wrapper; new preferred wrapper is `scripts/start/start_public_server.bat`. |
| `START_PUBLIC_TAILSCALE.bat` | legacy-supported | Manual Tailscale wrapper. |
| `build_copilot_facultate.bat` | legacy-supported wrapper | Root compatibility wrapper. New preferred script is `scripts/build/build_desktop_app.bat`. |
| `build_client.bat` | legacy-supported wrapper | Older client build. |
| `build_desktop_client.bat` | legacy-supported wrapper | Older desktop client build. |
| `build_server_launcher.bat` | legacy-supported wrapper | Server launcher build. |
| `docs/DEVELOPMENT_LEGACY.md` | current docs | Previous root README preserved for historical/developer details. |
| `docs/CLIENT_LEGACY.md` | current docs | Previous client install documentation preserved. |
| `assets/` | current | Product logo, screenshots, shared icons. |
| `scripts/` | current | Product-oriented build/start/diagnostic wrappers. |
| `.github/workflows/` | current | Release artifact build workflow. |
| `storage/` | runtime data | Ignored by Git except `.gitkeep`; contains user data, ChromaDB, logs and runtime URLs. |
| `documents/` | runtime/user data | Ignored by Git except `.gitkeep`; local documents. |
| `build/` | generated | Ignored by Git. |
| `dist/` | generated | Ignored by Git; contains release artifacts. |
| `.venv/`, `*/.venv_build/` | generated | Ignored by Git. |
| `__pycache__/` | generated | Ignored by Git. |

## Files moved in this refactor

| Old path | New path |
| --- | --- |
| `README.md` | `docs/DEVELOPMENT_LEGACY.md` |
| `INSTALL_CLIENT.md` | `docs/CLIENT_LEGACY.md` |

## Files archived

No working files were archived or deleted. Legacy entry points remain available to avoid breaking user workflows.

## Files deleted

None.

## Why code was not physically moved into `apps/`/`server/` yet

The current tests and imports refer directly to modules such as `desktop_app`, `desktop_client`, `server_launcher`, `api_server`, `app`, `study_memory`, `user_accounts` and `request_queue`. A physical package migration would require a larger staged import rewrite.

For this product refactor, the safe change is:

1. Make the GitHub/repository presentation product-first.
2. Add professional installer/release packaging.
3. Add `scripts/` and `docs/` as the new public structure.
4. Keep legacy paths working until a dedicated package migration can be tested end-to-end.

## Future package migration plan

Target package layout remains:

```text
apps/
  desktop/
  client/
  server_launcher/
server/
  api/
  rag/
  models/
  users/
deployment/
scripts/
docs/
assets/
tests/
```

When performed, use `git mv`, compatibility shims, and update tests incrementally.
