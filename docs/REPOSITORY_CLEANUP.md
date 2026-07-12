# Repository cleanup

Date: 2026-07-12

## Goal

Make the repository look and behave like a polished desktop application product while preserving existing functionality.

## Moved files and folders

See [`REPOSITORY_AUDIT.md`](REPOSITORY_AUDIT.md) for the full old-to-new mapping.

Main moves:

- application surfaces moved under `apps/`;
- server infrastructure moved under `server/`;
- root BAT/PowerShell scripts moved under `scripts/`;
- technical documentation moved under `docs/`;
- product visual resources consolidated under `assets/`.

## Deleted files

None.

## Archived files

No files were archived outside the repository. Legacy entry points were moved to `scripts/legacy/` and remain usable.

## Compatibility choices

Active code, tests and scripts now use the new package paths directly:

- `apps.web.app`
- `server.api.api_server`
- `apps.desktop.launcher`
- `apps.launcher.launcher`
- `streamlit run apps/web/app.py`
- `uvicorn server.api.api_server:app`

## Product polish completed

- Product-first README.
- Logo and screenshot assets.
- GitHub Release workflow.
- Installer script through Inno Setup.
- Portable EXE copy named `Co-pilot Facultate Portable.exe`.
- Root scripts moved into `scripts/`.
- Server is documented as infrastructure; desktop app is documented as the flagship product.

## Manual steps still required

To build the installer locally, install Inno Setup 6. Without it, the build still creates portable EXE artifacts.
