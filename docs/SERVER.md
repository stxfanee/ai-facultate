# Server operation

Server Mode is for the desktop PC that runs the AI stack.

It can start and monitor:

- Ollama;
- FastAPI on port `8000`;
- Streamlit on port `8501`;
- Cloudflare Tunnel or Tailscale Funnel.

Recommended entry point:

```powershell
.\dist\Co-pilot Facultate.exe
```

Manual fallback:

```powershell
.\scripts\start\start_local_server.bat
```
