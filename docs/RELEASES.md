# Releases

## Preferred release artifacts

Each public release should contain:

- `Co-pilot Facultate Setup.exe` — preferred installer for normal users.
- `Co-pilot Facultate.exe` — optional portable executable.

## Automatic GitHub Release

Push a tag:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The workflow in `.github/workflows/release.yml` builds the Windows artifacts and attaches them to the GitHub Release.

## Manual upload fallback

If GitHub Actions cannot build the installer, build locally:

```powershell
.\scripts\build\build_desktop_app.bat
```

Then upload these files from `dist/` to GitHub Releases:

```text
Co-pilot Facultate Setup.exe
Co-pilot Facultate.exe
```

Install Inno Setup 6 locally if `Setup.exe` is missing after the build.
