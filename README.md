# Co-pilot Facultate

<p align="center">
  <img src="assets/logos/copilot-facultate.svg" alt="Co-pilot Facultate logo" width="900">
</p>

<p align="center">
  <a href="https://github.com/stxfanee/ai-facultate/releases/latest">
    <img alt="Download latest release" src="https://img.shields.io/badge/Download-latest%20release-2563eb?style=for-the-badge&logo=github">
  </a>
</p>

**Co-pilot Facultate** is a Windows desktop AI study assistant. It opens like a normal app, lets you chat with your courses, and connects to your AI server without asking normal users to run scripts or understand Ollama, Streamlit, FastAPI, ChromaDB, tunnels, or localhost.

<p align="center">
  <img src="assets/screenshots/desktop-preview.svg" alt="Co-pilot Facultate desktop preview" width="900">
</p>

## Quick Start

1. Download **Co-pilot Facultate Setup.exe** from the [latest release](https://github.com/stxfanee/ai-facultate/releases/latest).
2. Install the application.
3. Launch **Co-pilot Facultate** from the Desktop or Start Menu.
4. Log in or create a profile.
5. Start chatting with the AI.

If a release is not uploaded yet, the server owner can build the installer locally:

```powershell
.\scripts\build\build_desktop_app.bat
```

The generated files are placed in `dist/`:

```text
dist/
  Co-pilot Facultate Setup.exe
  Co-pilot Facultate Portable.exe
  Co-pilot Facultate.exe
```

## What users see

- A polished desktop app called **Co-pilot Facultate**.
- ChatGPT/Claude-style chat interface.
- Persistent chats, profiles, workspaces, documents and study memory.
- Upload PDFs and ask questions with citations.
- Flashcards, quizzes, session plans and progress tracking.
- No PowerShell, no BAT files, no local models, no server setup.

## What the server owner runs

The desktop app can also run in **Server Mode** on the desktop PC that owns the AI stack:

- starts Ollama;
- starts FastAPI;
- starts Streamlit;
- starts Cloudflare Tunnel or Tailscale Funnel when configured;
- shows Local, LAN and Public URLs;
- opens the same AI interface inside the app.

Normal friends/classmates use **Client Mode** and connect to the public HTTPS URL. They do not download models and they do not run ChromaDB or Ollama.

## Which file should I run?

| Situation | Run this |
| --- | --- |
| Normal user installing the app | `Co-pilot Facultate Setup.exe` from GitHub Releases |
| Portable desktop app | `dist\Co-pilot Facultate Portable.exe` or `dist\Co-pilot Facultate.exe` |
| Build app + installer | `scripts\build\build_desktop_app.bat` |
| Start the AI server manually | `scripts\start\start_local_server.bat` |
| Start public server/tunnel manually | `scripts\start\start_public_server.bat` |
| Legacy/manual scripts | `scripts\legacy\` and old root wrappers |

## Public access

For sharing with friends outside your home network, use **Cloudflare Tunnel** or **Tailscale Funnel**. Do not use raw router port forwarding.

Recommended path:

1. Run **Co-pilot Facultate** on the desktop PC.
2. Choose Server Mode.
3. Enable Public Access with Cloudflare Tunnel.
4. Copy the HTTPS Public URL.
5. Share the link only with trusted people until real authentication is enabled.

No-password profiles are convenient for local/LAN/Tailscale testing, but a fully public deployment should enable proper authentication before wider use.

## Architecture in one minute

```text
Friend laptop / client PC
        |
        | HTTPS
        v
Cloudflare Tunnel or Tailscale Funnel
        |
        v
Desktop server PC
  - Co-pilot Facultate Server Mode
  - Streamlit UI
  - FastAPI
  - Ollama
  - ChromaDB
  - per-user storage
```

The desktop PC is the only AI server. Clients never download models.

## Main features

- Chat-first AI assistant experience.
- RAG over uploaded PDFs and course material.
- Citations and an “Explain why” transparency panel.
- Per-user profiles and isolated workspaces.
- Per-user documents, memory, conversations, quizzes, flashcards and plans.
- Smart model routing between fast and accurate Ollama models.
- Manual and Auto selection for `qwen3:8b`, `qwen3:14b` and optional Mistral Small 3.2 24B.
- RTX 3070-oriented performance profiles and benchmark tools.
- Request queue, rate limits, upload limits and timeout protection.
- Cloudflare Tunnel and Tailscale Funnel public access support.
- Windows desktop launcher with WebView2/pywebview.


## Local AI model optimization

Co-pilot Facultate keeps `Auto` as the default model mode. On an RTX 3070 8GB system:

- `qwen3:8b` stays the fast/default model for simple chat, normal RAG, quizzes and flashcards.
- `qwen3:14b` stays the practical reasoning model for harder analysis and study strategy.
- `mistral-small3.2:24b` / local GGUF Mistral Small 3.2 24B variants can be selected manually from Settings.
- Mistral 24B is not enabled as the automatic default just because it is installed. Run Benchmark first, then explicitly allow Mistral in Auto routing from Settings.
- For RTX 3070 8GB, prefer a local Q3_K_M GGUF test first. Q2 is experimental; Q4_K_M is a quality reference and will usually offload to RAM/CPU.

Settings includes a guided Mistral installer/import panel that creates an Ollama Modelfile with `FROM <path-to-gguf>` for local GGUF files. The app does not download unofficial GGUF files automatically.

## For developers and server owners

Documentation lives in [`docs/`](docs/):

- [Installation](docs/INSTALLATION.md)
- [Client usage](docs/CLIENT.md)
- [Server operation](docs/SERVER.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development](docs/DEVELOPMENT.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Releases](docs/RELEASES.md)
- [Repository audit](docs/REPOSITORY_AUDIT.md)
- [Repository cleanup](docs/REPOSITORY_CLEANUP.md)
- [Legacy development README](docs/DEVELOPMENT_LEGACY.md)

## Build and release

Build locally:

```powershell
.\scripts\build\build_desktop_app.bat
```

Create a GitHub Release automatically by pushing a tag:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The GitHub Actions workflow builds the portable EXE and, if Inno Setup is available on the runner, the installer. If installer compilation is not available, upload the generated local files from `dist/` manually to GitHub Releases.

## License

See [LICENSE](LICENSE).
