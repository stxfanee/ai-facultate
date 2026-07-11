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

Small compatibility shims remain at old Python import paths. They are intentional and keep these workflows stable:

- `import app`
- `import api_server`
- `from desktop_app import launcher`
- `from server_launcher import launcher`
- `uvicorn api_server:app`
- `streamlit run app.py`

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
