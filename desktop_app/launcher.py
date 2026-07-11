
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import threading
import time
import urllib.error
import urllib.request
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
    read_url_text,
    security_warning_for_url,
    streamlit_health_url,
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
VALID_THEMES = {"dark", "light", "auto"}
DEFAULT_THEME = "dark"
DEFAULT_SERVER_URL_FILENAME = "default_server_url.txt"


@dataclass
class UnifiedConfig:
    app_mode: str = ""
    default_server_url: str = ""
    developer_mode: bool = False
    remember_session: bool = True
    mode: str = ""
    server_url: str = ""
    project_root: str = ""
    tunnel: str = "none"
    auto_public_access: bool = False
    auto_restart: bool = True
    theme: str = DEFAULT_THEME
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
        if not values.get("app_mode") and values.get("mode"):
            values["app_mode"] = values["mode"]
        if not values.get("default_server_url") and values.get("server_url"):
            values["default_server_url"] = values["server_url"]
        if not values.get("mode") and values.get("app_mode"):
            values["mode"] = values["app_mode"]
        if not values.get("server_url") and values.get("default_server_url"):
            values["server_url"] = values["default_server_url"]
        if values.get("app_mode") not in VALID_MODES:
            values["app_mode"] = ""
        if values["mode"] not in VALID_MODES:
            values["mode"] = ""
        if values["app_mode"] and not values["mode"]:
            values["mode"] = values["app_mode"]
        if values["mode"] and not values["app_mode"]:
            values["app_mode"] = values["mode"]
        if values["tunnel"] not in VALID_TUNNELS:
            values["tunnel"] = "none"
        if values.get("theme") not in VALID_THEMES:
            values["theme"] = DEFAULT_THEME
        if values.get("server_url"):
            try:
                values["server_url"] = normalize_server_url(str(values["server_url"]))
            except ValueError:
                values["server_url"] = ""
        if values.get("default_server_url"):
            try:
                values["default_server_url"] = normalize_server_url(str(values["default_server_url"]))
            except ValueError:
                values["default_server_url"] = ""
        if values["server_url"] and not values["default_server_url"]:
            values["default_server_url"] = values["server_url"]
        if values["default_server_url"] and not values["server_url"]:
            values["server_url"] = values["default_server_url"]
        values["width"] = safe_int(values.get("width"), DEFAULT_WIDTH, MIN_WIDTH, 4096)
        values["height"] = safe_int(values.get("height"), DEFAULT_HEIGHT, MIN_HEIGHT, 2160)
        values["developer_mode"] = bool(values.get("developer_mode"))
        values["remember_session"] = bool(values.get("remember_session", True))
        values["auto_public_access"] = bool(values.get("auto_public_access"))
        values["auto_restart"] = bool(values.get("auto_restart", True))
        values["maximized"] = bool(values.get("maximized"))
        return cls(**values)

    def save(self, path: Path | None = None) -> None:
        target = path or config_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        if self.app_mode and not self.mode:
            self.mode = self.app_mode
        if self.mode and not self.app_mode:
            self.app_mode = self.mode
        if self.default_server_url and not self.server_url:
            self.server_url = self.default_server_url
        if self.server_url and not self.default_server_url:
            self.default_server_url = self.server_url
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



def normalize_theme(theme: str | None) -> str:
    return theme if theme in VALID_THEMES else DEFAULT_THEME


def webview_background(theme: str | None) -> str:
    return "#f8fafc" if normalize_theme(theme) == "light" else "#07090f"


def theme_select_html(theme: str, element_id: str = "theme") -> str:
    current = normalize_theme(theme)
    return (
        f'<label>Theme</label><select id="{element_id}">'
        f'<option value="dark" {"selected" if current == "dark" else ""}>Dark mode</option>'
        f'<option value="light" {"selected" if current == "light" else ""}>Light mode</option>'
        f'<option value="auto" {"selected" if current == "auto" else ""}>Auto</option>'
        '</select>'
    )


def theme_css(theme: str | None) -> str:
    mode = normalize_theme(theme)
    common = "--a:#7c3aed; --b:#06b6d4; --danger:#fb7185; --ok:#34d399; font-family:Inter,ui-sans-serif,'Segoe UI',system-ui,sans-serif;"
    dark_vars = "color-scheme: dark; --page:#07090f; --panel:rgba(15,23,42,.84); --line:rgba(148,163,184,.22); --text:#f8fafc; --muted:#a7b0c0; --field:rgba(2,6,23,.72); --choice:rgba(2,6,23,.48); --pre:rgba(2,6,23,.68); --grid:rgba(255,255,255,.035); --secondary:rgba(148,163,184,.16); --secondary-text:#e2e8f0; " + common
    light_vars = "color-scheme: light; --page:#f8fafc; --panel:rgba(255,255,255,.88); --line:rgba(15,23,42,.16); --text:#0f172a; --muted:#475569; --field:rgba(255,255,255,.88); --choice:rgba(255,255,255,.70); --pre:rgba(241,245,249,.92); --grid:rgba(15,23,42,.035); --secondary:rgba(15,23,42,.08); --secondary-text:#0f172a; " + common
    if mode == "light":
        return light_vars
    if mode == "auto":
        return dark_vars + " } @media (prefers-color-scheme: light) { :root { " + light_vars
    return dark_vars

def config_file() -> Path:
    return app_data_folder() / "settings.json"


def log_file() -> Path:
    return app_data_folder() / "desktop_app.log"


def bundled_resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def executable_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_server_url_candidates() -> list[Path]:
    return [
        executable_folder() / DEFAULT_SERVER_URL_FILENAME,
        app_data_folder() / DEFAULT_SERVER_URL_FILENAME,
        bundled_resource_path(DEFAULT_SERVER_URL_FILENAME),
        Path.cwd() / DEFAULT_SERVER_URL_FILENAME,
    ]


def discover_default_server_url() -> str:
    env_url = (
        os.environ.get("FACULTY_COPILOT_SERVER_URL")
        or os.environ.get("FACULTY_COPILOT_DEFAULT_SERVER_URL")
        or ""
    ).strip()
    if env_url:
        return normalize_server_url(env_url)
    for candidate in default_server_url_candidates():
        try:
            if candidate.exists():
                value = candidate.read_text(encoding="utf-8").strip()
                if value and not value.startswith("#"):
                    return normalize_server_url(value)
        except (OSError, ValueError):
            continue
    return ""


def client_url_or_default(config: UnifiedConfig) -> str:
    if config.default_server_url:
        return config.default_server_url
    if config.server_url:
        return config.server_url
    try:
        return discover_default_server_url()
    except ValueError:
        return ""


def effective_app_mode(config: UnifiedConfig) -> str:
    mode = config.app_mode or config.mode
    if mode in VALID_MODES:
        return mode
    return "client" if client_url_or_default(config) else ""


def client_startup_url(config: UnifiedConfig) -> str:
    return client_url_or_default(config) if effective_app_mode(config) == "client" else ""


def quick_client_health(server_url: str, timeout: int = 4) -> dict:
    normalized = normalize_server_url(server_url)
    warning = security_warning_for_url(normalized)
    status, body = read_url_text(streamlit_health_url(normalized), timeout=timeout)
    return {
        "ok": 200 <= status < 400,
        "target": normalized,
        "kind": "streamlit",
        "message": "Connected to Co-pilot Facultate.",
        "warning": warning,
        "details": body[:300],
        "status": status,
    }



def webview_storage_path() -> Path:
    return app_data_folder() / "webview_profile"


def streamlit_url(port: int = 8501, cache_bust: bool = True) -> str:
    url = f"http://localhost:{port}"
    return f"{url}/?_copilot_reload={int(time.time())}" if cache_bust else url


def clear_webview_cache_files() -> list[str]:
    root = webview_storage_path()
    removed: list[str] = []
    candidates = [
        root / "Cache",
        root / "Code Cache",
        root / "GPUCache",
        root / "DawnCache",
        root / "Service Worker" / "CacheStorage",
        root / "EBWebView" / "Default" / "Cache",
        root / "EBWebView" / "Default" / "Code Cache",
        root / "EBWebView" / "Default" / "GPUCache",
        root / "EBWebView" / "Default" / "DawnCache",
        root / "EBWebView" / "Default" / "Service Worker" / "CacheStorage",
    ]
    for target in candidates:
        try:
            if target.exists():
                shutil.rmtree(target, ignore_errors=False)
                removed.append(str(target))
        except OSError:
            # WebView may keep a cache file locked; a cache-busted reload still helps.
            pass
    return removed


def clear_webview_cache_if_rebuilt() -> None:
    marker = app_data_folder() / "webview_build_id.txt"
    try:
        executable = Path(sys.executable if getattr(sys, "frozen", False) else __file__)
        build_id = str(int(executable.stat().st_mtime))
        previous = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
        if previous != build_id:
            clear_webview_cache_files()
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(build_id, encoding="utf-8")
    except OSError:
        pass


def streamlit_frontend_ready(port: int = 8501, timeout: float = 60.0) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout
    health_url = f"http://127.0.0.1:{port}/_stcore/health"
    root_url = f"http://127.0.0.1:{port}/"
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2.5) as response:
                health_ok = 200 <= int(response.status) < 400
            logging.info("Streamlit health check result: %s", health_ok)
            if not health_ok:
                last_error = "Streamlit health endpoint is not ready."
                time.sleep(1)
                continue
            request = urllib.request.Request(root_url, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(request, timeout=3.5) as response:
                body = response.read(16384).decode("utf-8", errors="replace")
                root_ok = 200 <= int(response.status) < 400 and "streamlit" in body.lower()
            logging.info("Streamlit frontend root check result: %s", root_ok)
            if root_ok:
                return True, "Streamlit frontend ready."
            last_error = "Streamlit root HTML did not look ready."
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(1)
    return False, last_error or "Streamlit frontend did not become ready in time."

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


def dark_html(
    body: str,
    script: str = "",
    payload: dict | None = None,
    theme: str = DEFAULT_THEME,
) -> str:
    data = json.dumps(payload or {}, ensure_ascii=False)
    return f"""
<!doctype html>
<html lang="ro">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{APP_TITLE}</title>
  <style>
    :root {{ {theme_css(theme)} }}
    * {{ box-sizing:border-box; }}
    html,body {{ background:var(--page); }}
    body {{ margin:0; min-height:100vh; color:var(--text); background:radial-gradient(circle at 18% 18%,rgba(124,58,237,.26),transparent 30rem),radial-gradient(circle at 82% 14%,rgba(6,182,212,.18),transparent 32rem),linear-gradient(135deg,var(--page) 0%,var(--page) 100%); }}
    body:before {{ content:""; position:fixed; inset:0; background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px); background-size:42px 42px; mask-image:radial-gradient(circle at center,black,transparent 74%); pointer-events:none; }}
    main {{ position:relative; width:min(980px,calc(100vw - 44px)); margin:0 auto; padding:34px 0; }}
    .card {{ border:1px solid var(--line); border-radius:28px; background:var(--panel); box-shadow:0 26px 90px rgba(0,0,0,.24); backdrop-filter:blur(22px); padding:30px; }}
    .brand {{ display:flex; align-items:center; gap:16px; margin-bottom:18px; }}
    .logo {{ width:56px; height:56px; border-radius:18px; background:radial-gradient(circle at 32% 25%,#fff 0 6%,transparent 7%),linear-gradient(135deg,var(--a),var(--b)); box-shadow:0 16px 40px rgba(124,58,237,.34); }}
    h1 {{ margin:0; font-size:34px; letter-spacing:-.04em; }} h2 {{ margin:12px 0 8px; }}
    p,.muted {{ color:var(--muted); line-height:1.6; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }}
    .choice {{ border:1px solid var(--line); border-radius:22px; padding:18px; background:var(--choice); cursor:pointer; }}
    .choice:hover {{ border-color:rgba(6,182,212,.7); transform:translateY(-1px); }}
    label {{ display:block; margin:16px 0 7px; font-weight:700; }}
    input,select {{ width:100%; border:1px solid var(--line); border-radius:14px; padding:13px 14px; font-size:15px; color:var(--text); background:var(--field); outline:none; }}
    input:focus,select:focus {{ border-color:rgba(6,182,212,.8); box-shadow:0 0 0 4px rgba(6,182,212,.12); }}
    .actions {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:18px; }}
    button {{ border:0; border-radius:999px; padding:12px 18px; color:white; background:linear-gradient(135deg,var(--a),var(--b)); font-weight:800; cursor:pointer; }}
    button.secondary {{ background:var(--secondary); color:var(--secondary-text); }} button.danger {{ background:rgba(251,113,133,.25); color:#fecdd3; }} button:disabled {{ opacity:.55; cursor:wait; }}
    .message {{ min-height:24px; margin-top:16px; color:#10b981; white-space:pre-wrap; }} .message.error {{ color:var(--danger); }}
    .warning {{ margin-top:12px; padding:12px 14px; border-radius:14px; border:1px solid rgba(251,191,36,.36); background:rgba(251,191,36,.10); color:#b45309; }}
    .status {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin:18px 0; }}
    .pill {{ border:1px solid var(--line); border-radius:16px; padding:12px; background:var(--choice); }} .ok {{ color:var(--ok); }} .bad {{ color:var(--danger); }}
    .urls code {{ display:block; overflow:auto; padding:8px 0; color:#0284c7; }}
    pre {{ max-height:220px; overflow:auto; padding:14px; border-radius:16px; background:var(--pre); color:var(--text); }}
    .loader {{ width:42px; height:42px; border-radius:50%; border:4px solid rgba(127,127,127,.18); border-top-color:var(--b); animation:spin 1s linear infinite; margin:18px 0; }} @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
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


def first_launch_html(config: UnifiedConfig | None = None) -> str:
    theme = config.theme if config else DEFAULT_THEME
    question = "Cum vrei s\u0103 folose\u0219ti aplica\u021bia?"
    default_url = ""
    try:
        default_url = discover_default_server_url()
    except ValueError:
        default_url = ""
    client_text = (
        f"Conectare automata la serverul configurat: {default_url}."
        if default_url
        else "Conecteaza-te la un server existent. Daca app-ul are un URL implicit, il va folosi automat."
    )
    body = f"""
<div class="card">
  <div class="brand"><div class="logo"></div><div><h1>Co-pilot Facultate</h1><div class="muted">Alege cum ruleaza aplicatia pe acest PC.</div></div></div>
  <h2>{question}</h2>
  {theme_select_html(theme)}
  <div class="grid">
    <div class="choice" onclick="choose('server')"><h2>Server mode</h2><p>Ruleaza AI-ul pe acest PC: Ollama, FastAPI, Streamlit si optional public access.</p></div>
    <div class="choice" onclick="choose('client')"><h2>Client mode</h2><p>{client_text} Nu descarca modele si nu porneste procese AI.</p></div>
  </div>
  <div class="message" id="message"></div>
</div>
"""
    script = """
async function choose(mode) {
  msg('Salvez modul ales...');
  try { await callApi('choose_mode', mode, document.getElementById('theme').value); } catch(e) { msg(e.message || String(e), true); }
}
"""
    return dark_html(body, script, theme=theme)


def loading_html(message: str, details: str = "", config: UnifiedConfig | None = None) -> str:
    theme = config.theme if config else DEFAULT_THEME
    body = f"""
<div class="card">
  <div class="brand"><div class="logo"></div><div><h1>Co-pilot Facultate</h1><div class="muted">{message}</div></div></div>
  <div class="loader"></div>
  <p>{details}</p>
  <div class="message" id="message"></div>
</div>
"""
    return dark_html(body, theme=theme)


def client_setup_html(config: UnifiedConfig, message: str = "", warning: str = "") -> str:
    default_url = client_url_or_default(config)
    url_value = config.server_url or default_url
    advanced = config.developer_mode
    intro = (
        f"Aplicatia are server configurat automat: {url_value}. Apasa Connect sau asteapta reconectarea."
        if url_value
        else "Nu am gasit inca un URL implicit pentru server. Cere proprietarului aplicatiei un build cu default_server_url.txt sau seteaza URL-ul in Settings."
    )
    url_controls = (
        f"""
  <label for="server-url">Server URL fallback</label>
  <input id="server-url" spellcheck="false" placeholder="https://your-public-url" value="{url_value}">
"""
        if advanced
        else f'<input id="server-url" type="hidden" value="{url_value}">'
    )
    body = f"""
<div class="card">
  <div class="brand"><div class="logo"></div><div><h1>Co-pilot Facultate</h1><div class="muted">Client mode</div></div></div>
  <p>{intro} Acest PC nu ruleaza Ollama, ChromaDB sau modele AI.</p>
  {url_controls}
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
    return dark_html(body, script, theme=config.theme)


def client_unavailable_html(config: UnifiedConfig) -> str:
    body = """
<div class="card">
  <div class="brand"><div class="logo"></div><div><h1>Co-pilot Facultate</h1><div class="muted">Conexiune</div></div></div>
  <h2>Serverul nu este disponibil momentan.</h2>
  <p>Verifica daca serverul de pe desktop este pornit si daca linkul public este activ.</p>
  <div class="actions"><button onclick="retry()">Retry</button><button class="secondary" onclick="settings()">Open Settings</button></div>
  <div class="message" id="message"></div>
</div>
"""
    script = """
async function retry(){ msg('Reincerc conectarea...'); await callApi('retry_client_connection'); }
async function settings(){ await callApi('show_settings'); }
"""
    return dark_html(body, script, theme=config.theme)



def recovery_html(config: UnifiedConfig, message: str, logs: list[str] | None = None) -> str:
    body = f"""
<div class="card">
  <div class="brand"><div class="logo"></div><div><h1>Co-pilot Facultate</h1><div class="muted">Streamlit frontend recovery</div></div></div>
  <h2>Nu am putut incarca interfata Streamlit.</h2>
  <p>{message}</p>
  <div class="warning">Daca tocmai ai reconstruit aplicatia sau ai actualizat Streamlit, sterge cache-ul WebView si reincarca.</div>
  <div class="actions"><button onclick="retryLoad()">Retry</button><button class="secondary" onclick="reloadApp()">Reload app</button><button class="secondary" onclick="clearCache()">Clear WebView cache and reload</button><button class="secondary" onclick="showStatus()">Server Status</button></div>
  <div class="message" id="message"></div>
  <h2>Logs</h2><pre>{chr(10).join((logs or [])[-80:])}</pre>
</div>
"""
    script = """
async function retryLoad(){ msg('AÈ™tept Streamlit...'); await callApi('open_server_app'); }
async function reloadApp(){ msg('ReÃ®ncarc...'); await callApi('reload_streamlit_app'); }
async function clearCache(){ msg('È˜terg cache-ul WebView...'); await callApi('clear_webview_cache_and_reload'); }
async function showStatus(){ await callApi('refresh_status'); }
"""
    return dark_html(body, script, theme=config.theme)

def server_status_html(snapshot: dict, logs: list[str], config: UnifiedConfig | None = None) -> str:
    theme = config.theme if config else DEFAULT_THEME
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
    <button onclick="startServer()">Start Server</button><button class="secondary" onclick="openServerApp()">Open Chat</button><button class="secondary" onclick="reloadApp()">Reload app</button><button class="secondary" onclick="clearCache()">Clear WebView cache and reload</button><button class="secondary" onclick="restartServer()">Restart</button><button class="danger" onclick="stopServer()">Stop</button>
    <button class="secondary" onclick="enablePublic()">Enable Public</button><button class="secondary" onclick="disablePublic()">Disable Public</button><button class="secondary" onclick="showSettings()">Settings</button>
  </div>
  <div class="message" id="message"></div>
  <h2>Logs</h2><pre>{chr(10).join(logs[-80:])}</pre>
</div>
"""
    script = """
async function startServer(){ msg('Pornesc serverul...'); await callApi('start_server', false); }
async function openServerApp(){ await callApi('open_server_app'); }
async function reloadApp(){ msg('ReÃ®ncarc interfaÈ›a...'); await callApi('reload_streamlit_app'); }
async function clearCache(){ msg('È˜terg cache-ul WebView...'); await callApi('clear_webview_cache_and_reload'); }
async function restartServer(){ msg('Repornesc serverul...'); await callApi('restart_server'); }
async function stopServer(){ msg('Opresc serviciile...'); await callApi('stop_server'); }
async function enablePublic(){ msg('Pornesc public access...'); await callApi('enable_public_access'); }
async function disablePublic(){ msg('Opresc public access...'); await callApi('disable_public_access'); }
async function showSettings(){ await callApi('show_settings'); }
setTimeout(async()=>{ try { await callApi('refresh_status'); } catch(e){} }, 5000);
"""
    return dark_html(body, script, theme=theme)


def settings_html(config: UnifiedConfig) -> str:
    advanced = ""
    if config.developer_mode:
        advanced = f"""
  <h2>Advanced</h2>
  <label>Mode</label><select id="mode"><option value="server" {'selected' if effective_app_mode(config)=='server' else ''}>Server mode</option><option value="client" {'selected' if effective_app_mode(config)=='client' else ''}>Client mode</option></select>
  <label>Server URL</label><input id="server-url" value="{client_url_or_default(config)}" placeholder="https://your-public-url">
  <label>Project root pentru Server mode</label><input id="project-root" value="{config.project_root}">
  <label>Public tunnel</label><select id="tunnel"><option value="none" {'selected' if config.tunnel=='none' else ''}>none</option><option value="cloudflare" {'selected' if config.tunnel=='cloudflare' else ''}>Cloudflare</option><option value="tailscale" {'selected' if config.tunnel=='tailscale' else ''}>Tailscale</option></select>
  <label><input id="auto-public" type="checkbox" {'checked' if config.auto_public_access else ''} style="width:auto"> Auto Public Access in Server mode</label>
  <label><input id="auto-restart" type="checkbox" {'checked' if config.auto_restart else ''} style="width:auto"> Auto-restart crashed services</label>
"""
    body = f"""
<div class="card">
  <div class="brand"><div class="logo"></div><div><h1>Co-pilot Facultate</h1><div class="muted">Settings</div></div></div>
  {theme_select_html(config.theme)}
  <label><input id="remember-session" type="checkbox" {'checked' if config.remember_session else ''} style="width:auto"> Remember session</label>
  <label><input id="developer-mode" type="checkbox" {'checked' if config.developer_mode else ''} style="width:auto"> Developer Mode</label>
  {advanced}
  <div class="actions"><button onclick="saveSettings()">Save</button><button class="secondary" onclick="goHome()">Back</button><button class="danger" onclick="resetApp()">Reset saved setup</button></div>
  <div class="message" id="message"></div>
</div>
"""
    script = """
function valueOf(id, fallback){ const el=document.getElementById(id); return el ? el.value : fallback; }
function checkedOf(id, fallback){ const el=document.getElementById(id); return el ? el.checked : fallback; }
async function saveSettings(){
  msg('Salvez setarile...');
  try { await callApi('save_settings', {theme:document.getElementById('theme').value, mode:valueOf('mode',''), server_url:valueOf('server-url',''), project_root:valueOf('project-root',''), tunnel:valueOf('tunnel',''), auto_public_access:checkedOf('auto-public', false), auto_restart:checkedOf('auto-restart', true), developer_mode:checkedOf('developer-mode', false), remember_session:checkedOf('remember-session', true)}); msg('Setari salvate.'); }
  catch(e) { msg(e.message || String(e), true); }
}
async function goHome(){ await callApi('go_home'); }
async function resetApp(){ await callApi('reset_setup'); }
"""
    return dark_html(body, script, theme=config.theme)


class UnifiedAppApi:
    def __init__(self) -> None:
        self._window = None
        self.config = UnifiedConfig.load()
        self.logs: list[str] = []
        self.controller = self._new_controller()
        self._server_thread: threading.Thread | None = None
        self._startup_started = time.monotonic()

    def _log(self, line: str) -> None:
        self.logs.append(line)
        self.logs = self.logs[-300:]
        logging.info(line)

    def _new_controller(self) -> ServerController:
        return ServerController(self.config.server_settings(), self._log)

    def bind_window(self, window: object) -> None:
        self._window = window

    def _save(self) -> None:
        self.config.save()

    def _load_html(self, html: str) -> None:
        if self._window is not None:
            self._window.load_html(html)

    def choose_mode(self, mode: str, theme: str | None = None) -> None:
        if mode not in VALID_MODES:
            raise ValueError("Mod invalid.")
        self.config.mode = mode
        self.config.app_mode = mode
        self.config.theme = normalize_theme(theme or self.config.theme)
        self._save()
        if mode == "server":
            self._load_html(loading_html("Pornesc serverul...", "Ollama, FastAPI si Streamlit pornesc pe acest PC.", self.config))
            self.start_server(True)
        else:
            try:
                self.connect_client("")
            except Exception as exc:
                client_url = client_url_or_default(self.config)
                self._load_html(client_unavailable_html(self.config) if client_url else client_setup_html(self.config, str(exc), ""))

    def connect_client(self, server_url: str) -> dict:
        source = server_url.strip() if server_url else client_url_or_default(self.config)
        if not source:
            self._load_html(client_setup_html(self.config, "Nu am gasit URL-ul serverului configurat automat. Deschide Settings sau adauga default_server_url.txt langa exe.", ""))
            return {"message": "Missing server URL.", "warning": ""}
        normalized = normalize_server_url(source)
        self.config.app_mode = "client"
        self.config.mode = "client"
        self.config.default_server_url = normalized
        self.config.server_url = normalized
        self._save()
        self._load_client_url(normalized)
        self._start_client_health_check(normalized)
        return {"ok": True, "target": normalized, "message": "Conectez la server...", "warning": security_warning_for_url(normalized)}

    def _load_client_url(self, url: str) -> None:
        if self._window is None:
            return
        elapsed = time.monotonic() - self._startup_started
        self._log(f"Client loading server URL after {elapsed:.2f}s: {url}")
        self._window.load_url(url)

    def _start_client_health_check(self, url: str) -> None:
        threading.Thread(target=self._client_health_check_worker, args=(url,), daemon=True).start()

    def _client_health_check_worker(self, url: str) -> None:
        started = time.monotonic()
        try:
            result = quick_client_health(url, timeout=4)
            elapsed = time.monotonic() - started
            self._log(f"Client health check finished in {elapsed:.2f}s: {result.get('ok')} {url}")
            if not result.get("ok"):
                self._load_html(client_unavailable_html(self.config))
        except Exception:
            elapsed = time.monotonic() - started
            self._log(f"Client health check failed in {elapsed:.2f}s for {url}")
            if elapsed < 3.8:
                self._load_html(client_unavailable_html(self.config))

    def retry_client_connection(self) -> dict:
        return self.connect_client("")

    def start_server(self, open_when_ready: bool = False) -> dict:
        self.config.app_mode = "server"
        self.config.mode = "server"
        self._save()
        self.controller.settings = self.config.server_settings()
        if self._server_thread and self._server_thread.is_alive():
            return {"started": False, "message": "Server start already running."}

        def worker() -> None:
            self._load_html(loading_html("Pornesc serverul...", "Pornesc sau reutilizez Ollama, FastAPI si Streamlit.", self.config))
            self.controller.start_all()
            snapshot = self.snapshot_dict()
            if open_when_ready and snapshot.get("streamlit") and self._window is not None:
                self._load_html(loading_html("AÈ™tept Streamlit...", "Verific health check si frontend HTML. Timeout: 60s.", self.config))
                ready, message = streamlit_frontend_ready(self.controller.settings.streamlit_port, 60.0)
                self._log(f"Streamlit frontend readiness: {ready} - {message}")
                if ready:
                    self._load_html(loading_html("ÃŽncarc interfaÈ›a...", "Deschid Streamlit in WebView cu cache-busting.", self.config))
                    self._load_streamlit_url()
                else:
                    self._log(f"frontend loading failure: {message}")
                    self._window.load_html(recovery_html(self.config, message, self.logs))
            elif self._window is not None:
                self._window.load_html(server_status_html(snapshot, self.logs, self.config))

        self._server_thread = threading.Thread(target=worker, daemon=True)
        self._server_thread.start()
        return {"started": True}

    def _load_streamlit_url(self) -> None:
        if self._window is None:
            return
        url = streamlit_url(self.controller.settings.streamlit_port, cache_bust=True)
        self._log(f"WebView URL loaded: {url}")
        self._window.load_url(url)

    def open_server_app(self) -> None:
        snapshot = self.snapshot_dict()
        if snapshot.get("streamlit") and self._window is not None:
            self._load_html(loading_html("AÈ™tept Streamlit...", "Verific frontend-ul inainte de incarcare.", self.config))
            ready, message = streamlit_frontend_ready(self.controller.settings.streamlit_port, 60.0)
            self._log(f"Streamlit health/frontend check before open: {ready} - {message}")
            if ready:
                self._load_html(loading_html("ÃŽncarc interfaÈ›a...", "Deschid Streamlit in WebView.", self.config))
                self._load_streamlit_url()
            else:
                self._log(f"frontend loading failure: {message}")
                self._load_html(recovery_html(self.config, message, self.logs))
        else:
            self._load_html(server_status_html(snapshot, self.logs + ["Streamlit nu este inca online."], self.config))

    def reload_streamlit_app(self) -> None:
        self._log("Reload app requested.")
        self.open_server_app()

    def clear_webview_cache_and_reload(self) -> dict:
        removed = clear_webview_cache_files()
        self._log("cache clear action: " + (", ".join(removed) if removed else "no cache folders removed or files were locked"))
        self.open_server_app()
        return {"removed": removed}

    def stop_server(self) -> None:
        threading.Thread(target=self._stop_and_show, daemon=True).start()

    def _stop_and_show(self) -> None:
        self.controller.stop_all()
        self.refresh_status()

    def restart_server(self) -> None:
        self._load_html(loading_html("Repornesc serverul...", config=self.config))
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
        self._load_html(server_status_html(snapshot, self.logs, self.config))
        return snapshot

    def show_settings(self) -> None:
        self._load_html(settings_html(self.config))

    def save_settings(self, payload: dict) -> dict:
        advanced_payload = any(str(payload.get(key) or "").strip() for key in ("mode", "server_url", "project_root", "tunnel"))
        mode = str(payload.get("mode") or self.config.mode or self.config.app_mode)
        if mode not in VALID_MODES:
            raise ValueError("Mode must be server or client.")
        tunnel = str(payload.get("tunnel") or self.config.tunnel or "none")
        if tunnel not in VALID_TUNNELS:
            raise ValueError("Tunnel invalid.")
        server_url = str(payload.get("server_url") or "").strip()
        if server_url:
            server_url = normalize_server_url(server_url)
        project_root = str(payload.get("project_root") or self.config.project_root or default_project_root())
        self.config.mode = mode
        self.config.app_mode = mode
        self.config.theme = normalize_theme(str(payload.get("theme") or self.config.theme))
        if advanced_payload or server_url:
            self.config.server_url = server_url
            self.config.default_server_url = server_url or self.config.default_server_url
        self.config.project_root = project_root
        self.config.tunnel = tunnel
        if advanced_payload:
            self.config.auto_public_access = bool(payload.get("auto_public_access"))
            self.config.auto_restart = bool(payload.get("auto_restart", True))
        self.config.developer_mode = bool(payload.get("developer_mode"))
        self.config.remember_session = bool(payload.get("remember_session", True))
        self._save()
        self.controller = self._new_controller()
        return {"ok": True}

    def go_home(self) -> None:
        if self.config.mode == "server":
            self.refresh_status()
        elif self.config.mode == "client":
            if client_url_or_default(self.config):
                self._load_client_url(client_url_or_default(self.config))
                self._start_client_health_check(client_url_or_default(self.config))
            else:
                self._load_html(client_setup_html(self.config))
        else:
            self._load_html(first_launch_html(self.config))

    def reset_setup(self) -> None:
        self.config = UnifiedConfig(project_root=str(default_project_root()), theme=DEFAULT_THEME)
        try:
            config_file().unlink(missing_ok=True)
        except OSError:
            pass
        self.controller = self._new_controller()
        self._load_html(first_launch_html(self.config))

    def reload_app(self) -> None:
        if self._window is None:
            return
        if self.config.mode == "client" and self.config.server_url:
            self._load_client_url(self.config.server_url)
        elif self.config.mode == "server":
            snapshot = self.snapshot_dict()
            if snapshot.get("streamlit"):
                self.open_server_app()
            else:
                self.refresh_status()

    def toggle_fullscreen(self) -> None:
        if self._window is not None:
            self._window.toggle_fullscreen()


def initial_html(config: UnifiedConfig) -> str:
    if "--reset" in sys.argv:
        try:
            config_file().unlink(missing_ok=True)
        except OSError:
            pass
        config.mode = ""
    mode = effective_app_mode(config)
    if not mode:
        return first_launch_html(config)
    if mode == "client":
        if client_url_or_default(config):
            return loading_html("Conectez clientul...", "Deschid interfața AI.", config)
        return client_setup_html(config)
    return loading_html("Pornesc serverul...", "Server mode salvat. Pornesc serviciile si deschid chat-ul cand e gata.", config)


def on_start(api: UnifiedAppApi) -> None:
    mode = effective_app_mode(api.config)
    if mode == "client":
        client_url = client_url_or_default(api.config)
        if not client_url:
            api._load_html(client_setup_html(api.config))
            return
        api.config.app_mode = "client"
        api.config.mode = "client"
        api.config.default_server_url = client_url
        api.config.server_url = client_url
        api._save()
        api._log("Client Mode startup: skipping local Ollama/FastAPI/Streamlit checks.")
        api._start_client_health_check(client_url)
    elif mode == "server":
        api.start_server(True)


def initial_window_url(config: UnifiedConfig) -> str:
    if "--reset" in sys.argv:
        return ""
    return client_startup_url(config)


def main() -> None:
    configure_logging()
    if webview is None:
        raise RuntimeError("pywebview is required. Run build_copilot_facultate.bat or install pywebview.")
    clear_webview_cache_if_rebuilt()
    config = UnifiedConfig.load()
    api = UnifiedAppApi()
    api.config = config
    api.controller = api._new_controller()
    menu = [Menu(APP_TITLE, [MenuAction("Settings", api.show_settings), MenuAction("Reload", api.reload_app), MenuSeparator(), MenuAction("Fullscreen", api.toggle_fullscreen)])]
    startup_url = initial_window_url(config)
    startup_html = "" if startup_url else initial_html(config)
    logging.info("Desktop window startup mode=%s url=%s", effective_app_mode(config) or "setup", bool(startup_url))
    window = webview.create_window(
        APP_TITLE,
        url=startup_url or None,
        html=startup_html or None,
        width=config.width,
        height=config.height,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        resizable=True,
        maximized=config.maximized,
        confirm_close=False,
        background_color=webview_background(config.theme),
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
        storage_path=str(webview_storage_path()),
        menu=menu,
        icon=str(Path(__file__).resolve().parent / "assets" / "copilot_facultate.ico"),
    )


if __name__ == "__main__":
    main()

