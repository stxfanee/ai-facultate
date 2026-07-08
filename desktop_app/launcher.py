
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import webview
    from webview.menu import Menu, MenuAction, MenuSeparator
except Exception:  # pragma: no cover
    webview = None
    Menu = MenuAction = MenuSeparator = None

from desktop_client.launcher import (
    PUBLIC_HTTP_WARNING,
    normalize_server_url,
    security_warning_for_url,
    test_server,
)
from server_launcher.launcher import LauncherSettings, ServerController, default_project_root


APP_TITLE = "Co-pilot Facultate"
APP_DATA_FOLDER = "Co-pilot Facultate"
DEFAULT_WIDTH = 1320
DEFAULT_HEIGHT = 880
MIN_WIDTH = 980
MIN_HEIGHT = 640
VALID_MODES = {"server", "client"}
VALID_TUNNELS = {"none", "cloudflare", "tailscale"}


@dataclass
class UnifiedConfig:
    mode: str = ""
    server_url: str = ""
    project_root: str = ""
    tunnel: str = "none"
    auto_public_access: bool = False
    auto_restart: bool = True
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    maximized: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> "UnifiedConfig":
        target = path or config_file()
        defaults = cls(project_root=str(default_project_root()))
        if not target.exists():
            return defaults
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return defaults
        values = asdict(defaults)
        values.update({key: value for key, value in data.items() if key in values})
        if values["mode"] not in VALID_MODES:
            values["mode"] = ""
        if values["tunnel"] not in VALID_TUNNELS:
            values["tunnel"] = "none"
        if values.get("server_url"):
            try:
                values["server_url"] = normalize_server_url(str(values["server_url"]))
            except ValueError:
                values["server_url"] = ""
        values["width"] = safe_int(values.get("width"), DEFAULT_WIDTH, MIN_WIDTH, 4096)
        values["height"] = safe_int(values.get("height"), DEFAULT_HEIGHT, MIN_HEIGHT, 2160)
        values["auto_public_access"] = bool(values.get("auto_public_access"))
        values["auto_restart"] = bool(values.get("auto_restart", True))
        values["maximized"] = bool(values.get("maximized"))
        return cls(**values)

    def save(self, path: Path | None = None) -> None:
        target = path or config_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def server_settings(self) -> LauncherSettings:
        return LauncherSettings(
            project_root=self.project_root or str(default_project_root()),
            tunnel=self.tunnel,
            auto_public_access=self.auto_public_access,
            auto_restart=self.auto_restart,
        )


def safe_int(value: object, fallback: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(maximum, number))


def app_data_folder() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_DATA_FOLDER
    return Path.home() / ".copilot_facultate_unified"


def config_file() -> Path:
    return app_data_folder() / "settings.json"


def log_file() -> Path:
    return app_data_folder() / "desktop_app.log"


def configure_logging() -> None:
    try:
        path = log_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=path,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            encoding="utf-8",
        )
    except OSError:
        logging.basicConfig(level=logging.INFO)


def dark_html(body: str, script: str = "", payload: dict | None = None) -> str:
    data = json.dumps(payload or {}, ensure_ascii=False)
    return f"""
<!doctype html>
<html lang="ro">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{APP_TITLE}</title>
  <style>
    :root {{ color-scheme: dark; --panel:rgba(15,23,42,.84); --line:rgba(148,163,184,.22); --text:#f8fafc; --muted:#a7b0c0; --a:#7c3aed; --b:#06b6d4; --danger:#fb7185; --ok:#34d399; font-family:Inter,ui-sans-serif,"Segoe UI",system-ui,sans-serif; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; color:var(--text); background:radial-gradient(circle at 18% 18%,rgba(124,58,237,.34),transparent 30rem),radial-gradient(circle at 82% 14%,rgba(6,182,212,.22),transparent 32rem),linear-gradient(135deg,#07090f 0%,#111827 55%,#0b1120 100%); }}
    body:before {{ content:""; position:fixed; inset:0; background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px); background-size:42px 42px; mask-image:radial-gradient(circle at center,black,transparent 74%); pointer-events:none; }}
    main {{ position:relative; width:min(980px,calc(100vw - 44px)); margin:0 auto; padding:34px 0; }}
    .card {{ border:1px solid var(--line); border-radius:28px; background:var(--panel); box-shadow:0 26px 90px rgba(0,0,0,.42); backdrop-filter:blur(22px); padding:30px; }}
    .brand {{ display:flex; align-items:center; gap:16px; margin-bottom:18px; }}
    .logo {{ width:56px; height:56px; border-radius:18px; background:radial-gradient(circle at 32% 25%,#fff 0 6%,transparent 7%),linear-gradient(135deg,var(--a),var(--b)); box-shadow:0 16px 40px rgba(124,58,237,.34); }}
    h1 {{ margin:0; font-size:34px; letter-spacing:-.04em; }} h2 {{ margin:12px 0 8px; }}
    p,.muted {{ color:var(--muted); line-height:1.6; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }}
    .choice {{ border:1px solid var(--line); border-radius:22px; padding:18px; background:rgba(2,6,23,.48); cursor:pointer; }}
    .choice:hover {{ border-color:rgba(6,182,212,.7); transform:translateY(-1px); }}
    label {{ display:block; margin:16px 0 7px; font-weight:700; }}
    input,select {{ width:100%; border:1px solid var(--line); border-radius:14px; padding:13px 14px; font-size:15px; color:var(--text); background:rgba(2,6,23,.72); outline:none; }}
    input:focus,select:focus {{ border-color:rgba(6,182,212,.8); box-shadow:0 0 0 4px rgba(6,182,212,.12); }}
    .actions {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:18px; }}
    button {{ border:0; border-radius:999px; padding:12px 18px; color:white; background:linear-gradient(135deg,var(--a),var(--b)); font-weight:800; cursor:pointer; }}
    button.secondary {{ background:rgba(148,163,184,.16); color:#e2e8f0; }} button.danger {{ background:rgba(251,113,133,.25); color:#fecdd3; }} button:disabled {{ opacity:.55; cursor:wait; }}
    .message {{ min-height:24px; margin-top:16px; color:#a7f3d0; white-space:pre-wrap; }} .message.error {{ color:var(--danger); }}
    .warning {{ margin-top:12px; padding:12px 14px; border-radius:14px; border:1px solid rgba(251,191,36,.36); background:rgba(251,191,36,.10); color:#fde68a; }}
    .status {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:18px 0; }}
    .pill {{ border:1px solid var(--line); border-radius:16px; padding:12px; background:rgba(2,6,23,.46); }} .ok {{ color:var(--ok); }} .bad {{ color:var(--danger); }}
    .urls code {{ display:block; overflow:auto; padding:8px 0; color:#bae6fd; }}
    pre {{ max-height:220px; overflow:auto; padding:14px; border-radius:16px; background:rgba(2,6,23,.68); color:#cbd5e1; }}
    .loader {{ width:42px; height:42px; border-radius:50%; border:4px solid rgba(255,255,255,.14); border-top-color:var(--b); animation:spin 1s linear infinite; margin:18px 0; }} @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
  </style>
</head>
<body>
<script>window.__DATA__ = {data};</script>
<main>{body}</main>
<script>
function apiReady() {{ return window.pywebview && window.pywebview.api; }}
function msg(text, error=false) {{ const el=document.getElementById('message'); if(el) {{ el.textContent=text||''; el.className=error?'message error':'message'; }} }}
async function callApi(name, ...args) {{ if(!apiReady()) throw new Error('Aplicatia inca porneste. Incearca din nou.'); return await window.pywebview.api[name](...args); }}
{script}
</script>
</body>
</html>
"""


def first_launch_html() -> str:
    question = "Cum vrei s? folose?ti aplica?ia?"
    body = f"""
<div class="card">
  <div class="brand"><div class="logo"></div><div><h1>Co-pilot Facultate</h1><div class="muted">Alege cum ruleaza aplicatia pe acest PC.</div></div></div>
  <h2>{question}</h2>
  <div class="grid">
    <div class="choice" onclick="choose('server')"><h2>Server mode</h2><p>Ruleaza AI-ul pe acest PC: Ollama, FastAPI, Streamlit si optional public access.</p></div>
    <div class="choice" onclick="choose('client')"><h2>Client mode</h2><p>Conecteaza-te la un server existent. Nu descarca modele si nu porneste procese AI.</p></div>
  </div>
  <div class="message" id="message"></div>
</div>
"""
    script = """
async function choose(mode) {
  msg('Salvez modul ales...');
  try { await callApi('choose_mode', mode); } catch(e) { msg(e.message || String(e), true); }
}
"""
    return dark_html(body, script)


def loading_html(message: str, details: str = "") -> str:
    body = f"""
<div class="card">
  <div class="brand"><div class="logo"></div><div><h1>Co-pilot Facultate</h1><div class="muted">{message}</div></div></div>
  <div class="loader"></div>
  <p>{details}</p>
  <div class="message" id="message"></div>
</div>
"""
    return dark_html(body)


def client_setup_html(config: UnifiedConfig, message: str = "", warning: str = "") -> str:
    body = f"""
<div class="card">
  <div class="brand"><div class="logo"></div><div><h1>Co-pilot Facultate</h1><div class="muted">Client mode</div></div></div>
  <p>Introdu URL-ul serverului public sau LAN. Acest PC nu ruleaza Ollama, ChromaDB sau modele AI.</p>
  <label for="server-url">Server URL</label>
  <input id="server-url" spellcheck="false" placeholder="https://your-public-url" value="{config.server_url}">
  <div id="warning" class="warning" style="display:{'block' if warning else 'none'}">{warning}</div>
  <div class="actions"><button onclick="connectClient()">Connect</button><button class="secondary" onclick="showSettings()">Settings</button><button class="secondary" onclick="resetApp()">Reset setup</button></div>
  <div class="message {'error' if message else ''}" id="message">{message}</div>
</div>
"""
    script = """
async function connectClient() {
  msg('Verific serverul...');
  try { const result = await callApi('connect_client', document.getElementById('server-url').value); const w=document.getElementById('warning'); if(result.warning){w.style.display='block'; w.textContent=result.warning;} msg(result.message || 'Conectat.'); }
  catch(e) { msg(e.message || String(e), true); }
}
async function showSettings(){ await callApi('show_settings'); }
async function resetApp(){ await callApi('reset_setup'); }
"""
    return dark_html(body, script)


def server_status_html(snapshot: dict, logs: list[str]) -> str:
    def status_item(name: str, ok: bool) -> str:
        return f"<div class='pill'><strong>{name}</strong><br><span class='{'ok' if ok else 'bad'}'>{'Online' if ok else 'Offline'}</span></div>"
    public = snapshot.get("public_url") or "-"
    body = f"""
<div class="card">
  <div class="brand"><div class="logo"></div><div><h1>Co-pilot Facultate</h1><div class="muted">Server mode</div></div></div>
  <div class="status">
    {status_item('Ollama', snapshot.get('ollama', False))}
    {status_item('FastAPI', snapshot.get('fastapi', False))}
    {status_item('Streamlit', snapshot.get('streamlit', False))}
    {status_item('Public Access', snapshot.get('tunnel', False))}
  </div>
  <div class="urls">
    <strong>Local URL</strong><code>{snapshot.get('local_url') or '-'}</code>
    <strong>LAN URL</strong><code>{snapshot.get('lan_url') or '-'}</code>
    <strong>Public URL</strong><code>{public}</code>
  </div>
  <div class="warning">Daca public access este ON si auth este OFF, distribuie linkul doar persoanelor de incredere.</div>
  <div class="actions">
    <button onclick="startServer()">Start Server</button><button class="secondary" onclick="openServerApp()">Open Chat</button><button class="secondary" onclick="restartServer()">Restart</button><button class="danger" onclick="stopServer()">Stop</button>
    <button class="secondary" onclick="enablePublic()">Enable Public</button><button class="secondary" onclick="disablePublic()">Disable Public</button><button class="secondary" onclick="showSettings()">Settings</button>
  </div>
  <div class="message" id="message"></div>
  <h2>Logs</h2><pre>{chr(10).join(logs[-80:])}</pre>
</div>
"""
    script = """
async function startServer(){ msg('Pornesc serverul...'); await callApi('start_server', false); }
async function openServerApp(){ await callApi('open_server_app'); }
async function restartServer(){ msg('Repornesc serverul...'); await callApi('restart_server'); }
async function stopServer(){ msg('Opresc serviciile...'); await callApi('stop_server'); }
async function enablePublic(){ msg('Pornesc public access...'); await callApi('enable_public_access'); }
async function disablePublic(){ msg('Opresc public access...'); await callApi('disable_public_access'); }
async function showSettings(){ await callApi('show_settings'); }
setTimeout(async()=>{ try { await callApi('refresh_status'); } catch(e){} }, 5000);
"""
    return dark_html(body, script)


def settings_html(config: UnifiedConfig) -> str:
    body = f"""
<div class="card">
  <div class="brand"><div class="logo"></div><div><h1>Co-pilot Facultate</h1><div class="muted">Settings</div></div></div>
  <label>Mode</label><select id="mode"><option value="server" {'selected' if config.mode=='server' else ''}>Server mode</option><option value="client" {'selected' if config.mode=='client' else ''}>Client mode</option></select>
  <label>Server URL pentru Client mode</label><input id="server-url" value="{config.server_url}" placeholder="https://your-public-url">
  <label>Project root pentru Server mode</label><input id="project-root" value="{config.project_root}">
  <label>Public tunnel</label><select id="tunnel"><option value="none" {'selected' if config.tunnel=='none' else ''}>none</option><option value="cloudflare" {'selected' if config.tunnel=='cloudflare' else ''}>Cloudflare</option><option value="tailscale" {'selected' if config.tunnel=='tailscale' else ''}>Tailscale</option></select>
  <label><input id="auto-public" type="checkbox" {'checked' if config.auto_public_access else ''} style="width:auto"> Auto Public Access in Server mode</label>
  <label><input id="auto-restart" type="checkbox" {'checked' if config.auto_restart else ''} style="width:auto"> Auto-restart crashed services</label>
  <div class="actions"><button onclick="saveSettings()">Save</button><button class="secondary" onclick="goHome()">Back</button><button class="danger" onclick="resetApp()">Reset saved setup</button></div>
  <div class="message" id="message"></div>
</div>
"""
    script = """
async function saveSettings(){
  msg('Salvez setarile...');
  try { await callApi('save_settings', {mode:document.getElementById('mode').value, server_url:document.getElementById('server-url').value, project_root:document.getElementById('project-root').value, tunnel:document.getElementById('tunnel').value, auto_public_access:document.getElementById('auto-public').checked, auto_restart:document.getElementById('auto-restart').checked}); msg('Setari salvate.'); }
  catch(e) { msg(e.message || String(e), true); }
}
async function goHome(){ await callApi('go_home'); }
async function resetApp(){ await callApi('reset_setup'); }
"""
    return dark_html(body, script)


class UnifiedAppApi:
    def __init__(self) -> None:
        self.window = None
        self.config = UnifiedConfig.load()
        self.logs: list[str] = []
        self.controller = self._new_controller()
        self._server_thread: threading.Thread | None = None

    def _log(self, line: str) -> None:
        self.logs.append(line)
        self.logs = self.logs[-300:]
        logging.info(line)

    def _new_controller(self) -> ServerController:
        return ServerController(self.config.server_settings(), self._log)

    def bind_window(self, window: object) -> None:
        self.window = window

    def _save(self) -> None:
        self.config.save()

    def _load_html(self, html: str) -> None:
        if self.window is not None:
            self.window.load_html(html)

    def choose_mode(self, mode: str) -> None:
        if mode not in VALID_MODES:
            raise ValueError("Mod invalid.")
        self.config.mode = mode
        self._save()
        if mode == "server":
            self._load_html(loading_html("Pornesc serverul...", "Ollama, FastAPI si Streamlit pornesc pe acest PC."))
            self.start_server(True)
        else:
            self._load_html(client_setup_html(self.config))

    def connect_client(self, server_url: str) -> dict:
        normalized = normalize_server_url(server_url)
        result = test_server(normalized)
        self.config.mode = "client"
        self.config.server_url = normalized
        self._save()
        if self.window is not None:
            self.window.load_url(normalized)
        return result

    def start_server(self, open_when_ready: bool = False) -> dict:
        self.config.mode = "server"
        self._save()
        self.controller.settings = self.config.server_settings()
        if self._server_thread and self._server_thread.is_alive():
            return {"started": False, "message": "Server start already running."}

        def worker() -> None:
            self.controller.start_all()
            snapshot = self.snapshot_dict()
            if open_when_ready and snapshot.get("streamlit") and self.window is not None:
                self.window.load_url(snapshot["local_url"])
            elif self.window is not None:
                self.window.load_html(server_status_html(snapshot, self.logs))

        self._server_thread = threading.Thread(target=worker, daemon=True)
        self._server_thread.start()
        return {"started": True}

    def open_server_app(self) -> None:
        snapshot = self.snapshot_dict()
        if snapshot.get("streamlit") and self.window is not None:
            self.window.load_url(snapshot["local_url"])
        else:
            self._load_html(server_status_html(snapshot, self.logs + ["Streamlit nu este inca online."]))

    def stop_server(self) -> None:
        threading.Thread(target=self._stop_and_show, daemon=True).start()

    def _stop_and_show(self) -> None:
        self.controller.stop_all()
        self.refresh_status()

    def restart_server(self) -> None:
        self._load_html(loading_html("Repornesc serverul..."))
        threading.Thread(target=self._restart_and_show, daemon=True).start()

    def _restart_and_show(self) -> None:
        self.controller.restart_all()
        self.refresh_status()

    def enable_public_access(self) -> None:
        threading.Thread(target=self._enable_public_and_show, daemon=True).start()

    def _enable_public_and_show(self) -> None:
        self.controller.settings = self.config.server_settings()
        self.controller.enable_public_access()
        self.refresh_status()

    def disable_public_access(self) -> None:
        threading.Thread(target=self._disable_public_and_show, daemon=True).start()

    def _disable_public_and_show(self) -> None:
        self.controller.disable_public_access()
        self.refresh_status()

    def snapshot_dict(self) -> dict:
        snapshot = self.controller.status_snapshot()
        return {
            "ollama": snapshot.ollama,
            "fastapi": snapshot.fastapi,
            "streamlit": snapshot.streamlit,
            "tunnel": snapshot.tunnel,
            "local_url": snapshot.local_url,
            "lan_url": snapshot.lan_url,
            "public_url": snapshot.public_url,
        }

    def refresh_status(self) -> dict:
        self.controller.repair_crashed_services()
        snapshot = self.snapshot_dict()
        self._load_html(server_status_html(snapshot, self.logs))
        return snapshot

    def show_settings(self) -> None:
        self._load_html(settings_html(self.config))

    def save_settings(self, payload: dict) -> dict:
        mode = str(payload.get("mode") or self.config.mode)
        if mode not in VALID_MODES:
            raise ValueError("Mode must be server or client.")
        tunnel = str(payload.get("tunnel") or "none")
        if tunnel not in VALID_TUNNELS:
            raise ValueError("Tunnel invalid.")
        server_url = str(payload.get("server_url") or "").strip()
        if server_url:
            server_url = normalize_server_url(server_url)
        project_root = str(payload.get("project_root") or self.config.project_root or default_project_root())
        self.config.mode = mode
        self.config.server_url = server_url
        self.config.project_root = project_root
        self.config.tunnel = tunnel
        self.config.auto_public_access = bool(payload.get("auto_public_access"))
        self.config.auto_restart = bool(payload.get("auto_restart", True))
        self._save()
        self.controller = self._new_controller()
        return {"ok": True}

    def go_home(self) -> None:
        if self.config.mode == "server":
            self.refresh_status()
        elif self.config.mode == "client":
            self._load_html(client_setup_html(self.config))
        else:
            self._load_html(first_launch_html())

    def reset_setup(self) -> None:
        self.config = UnifiedConfig(project_root=str(default_project_root()))
        try:
            config_file().unlink(missing_ok=True)
        except OSError:
            pass
        self.controller = self._new_controller()
        self._load_html(first_launch_html())

    def reload_app(self) -> None:
        if self.window is None:
            return
        if self.config.mode == "client" and self.config.server_url:
            self.window.load_url(self.config.server_url)
        elif self.config.mode == "server":
            snapshot = self.snapshot_dict()
            if snapshot.get("streamlit"):
                self.window.load_url(snapshot["local_url"])
            else:
                self.refresh_status()

    def toggle_fullscreen(self) -> None:
        if self.window is not None:
            self.window.toggle_fullscreen()


def initial_html(config: UnifiedConfig) -> str:
    if "--reset" in sys.argv:
        try:
            config_file().unlink(missing_ok=True)
        except OSError:
            pass
        config.mode = ""
    if not config.mode:
        return first_launch_html()
    if config.mode == "client":
        if config.server_url:
            return loading_html("Conectez clientul...", config.server_url)
        return client_setup_html(config)
    return loading_html("Pornesc serverul...", "Server mode salvat. Pornesc serviciile si deschid chat-ul cand e gata.")


def on_start(api: UnifiedAppApi) -> None:
    if api.config.mode == "client" and api.config.server_url:
        try:
            test_server(api.config.server_url)
            if api.window is not None:
                api.window.load_url(api.config.server_url)
        except Exception as exc:
            api._load_html(client_setup_html(api.config, str(exc), security_warning_for_url(api.config.server_url)))
    elif api.config.mode == "server":
        api.start_server(True)


def main() -> None:
    configure_logging()
    if webview is None:
        raise RuntimeError("pywebview is required. Run build_copilot_facultate.bat or install pywebview.")
    config = UnifiedConfig.load()
    api = UnifiedAppApi()
    api.config = config
    api.controller = api._new_controller()
    menu = [Menu(APP_TITLE, [MenuAction("Settings", api.show_settings), MenuAction("Reload", api.reload_app), MenuSeparator(), MenuAction("Fullscreen", api.toggle_fullscreen)])]
    window = webview.create_window(
        APP_TITLE,
        html=initial_html(config),
        width=config.width,
        height=config.height,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        resizable=True,
        maximized=config.maximized,
        confirm_close=False,
        background_color="#07090f",
        js_api=api,
        menu=menu,
    )
    if window is None:
        raise RuntimeError("Could not create Co-pilot Facultate window.")
    api.bind_window(window)
    webview.start(
        on_start,
        api,
        gui="edgechromium",
        private_mode=False,
        storage_path=str(app_data_folder() / "webview_profile"),
        menu=menu,
        icon=str(Path(__file__).resolve().parent / "assets" / "copilot_facultate.ico"),
    )


if __name__ == "__main__":
    main()
