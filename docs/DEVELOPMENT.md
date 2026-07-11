# Development

## Setup

```powershell
.\install.ps1
```

## Run tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Build the flagship app

```powershell
.\scripts\build\build_desktop_app.bat
```

## Build all Windows artifacts

```powershell
.\scripts\build\build_all.bat
```

Older scripts remain available at the repository root as compatibility wrappers.
