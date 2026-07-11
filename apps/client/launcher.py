from __future__ import annotations

import json
import logging
import os
import sys
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import ParseResult, urlparse, urlunparse
from urllib.request import Request, urlopen

try:  # Keep unit tests importable even when pywebview is not installed.
    import webview
    from webview.menu import Menu, MenuAction, MenuSeparator
except Exception:  # pragma: no cover
    webview = None
    Menu = MenuAction = MenuSeparator = None


APP_TITLE = "Faculty Copilot"
APP_DATA_FOLDER = "Faculty Copilot"
DEFAULT_WIDTH = 1320
DEFAULT_HEIGHT = 880
MIN_WIDTH = 960
MIN_HEIGHT = 640
PUBLIC_HTTP_WARNING = (
    "Plain HTTP is only recommended for localhost or trusted LAN addresses. "
    "For public sharing, use an HTTPS Cloudflare Tunnel or Tailscale Funnel URL."
)
UNAVAILABLE_MESSAGE = (
    "I could not reach the Faculty Copilot server. Check that the public URL is "
    "correct and that the desktop AI server is running."
)


@dataclass
class ClientConfig:
    server_url: str = ""
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    maximized: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> "ClientConfig":
        target = path or config_file()
        if not target.exists():
            return cls()
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls(
            server_url=normalize_server_url(str(data.get("server_url", ""))) if data.get("server_url") else "",
            width=safe_int(data.get("width"), DEFAULT_WIDTH, MIN_WIDTH, 4096),
            height=safe_int(data.get("height"), DEFAULT_HEIGHT, MIN_HEIGHT, 2160),
            maximized=bool(data.get("maximized", False)),
        )

    def save(self, path: Path | None = None) -> None:
        target = path or config_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")


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
    return Path.home() / ".faculty_copilot"


def config_file() -> Path:
    return app_data_folder() / "client_config.json"


def log_file() -> Path:
    return app_data_folder() / "desktop_client.log"


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


def normalize_server_url(value: str) -> str:
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        return ""
    parsed_initial = urlparse(cleaned)
    has_http_scheme = parsed_initial.scheme in {"http", "https"}
    if not has_http_scheme:
        host = cleaned.split("/")[0].split(":")[0]
        scheme = "http" if is_local_or_lan_host(host) else "https"
        cleaned = f"{scheme}://{cleaned}"
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a valid HTTP or HTTPS server URL.")
    return cleaned.rstrip("/")


def is_local_or_lan_host(host: str) -> bool:
    host = (host or "").lower().strip("[]")
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    if host.startswith("192.168.") or host.startswith("10."):
        return True
    if host.endswith(".local") or host.endswith(".lan"):
        return True
    parts = host.split(".")
    if len(parts) == 4 and all(part.isdigit() for part in parts):
        first, second = int(parts[0]), int(parts[1])
        return first == 172 and 16 <= second <= 31
    return False


def security_warning_for_url(server_url: str) -> str:
    try:
        parsed = urlparse(normalize_server_url(server_url))
    except ValueError:
        return ""
    if parsed.scheme == "https":
        return ""
    return "" if is_local_or_lan_host(parsed.hostname or "") else PUBLIC_HTTP_WARNING


def with_port(parsed: ParseResult, port: int) -> str:
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth += f":{parsed.password}"
        netloc = f"{auth}@{netloc}"
    return urlunparse((parsed.scheme, f"{netloc}:{port}", "", "", "", ""))


def api_url_from_server_url(server_url: str) -> str:
    normalized = normalize_server_url(server_url)
    parsed = urlparse(normalized)
    if parsed.port == 8501:
        return with_port(parsed, 8000)
    return normalized


def streamlit_health_url(server_url: str) -> str:
    return f"{normalize_server_url(server_url)}/_stcore/health"


def api_health_url(server_url: str) -> str:
    return f"{api_url_from_server_url(server_url)}/health"


def read_url_text(url: str, timeout: int = 7) -> tuple[int, str]:
    request = Request(url, headers={"Accept": "application/json,text/plain,*/*"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read(4096).decode("utf-8", errors="replace")
    except HTTPError as exc:
        return int(exc.code), exc.read(4096).decode("utf-8", errors="replace")


def test_server(server_url: str) -> dict:
    normalized = normalize_server_url(server_url)
    warning = security_warning_for_url(normalized)
    errors: list[str] = []
    try:
        status, body = read_url_text(streamlit_health_url(normalized))
        if 200 <= status < 400:
            return {"ok": True, "target": normalized, "kind": "streamlit", "message": "Connected to the Faculty Copilot web app.", "warning": warning, "details": body[:300]}
        errors.append(f"Streamlit health returned HTTP {status}.")
    except (OSError, URLError, TimeoutError) as exc:
        errors.append(f"Streamlit health failed: {exc}")
    try:
        status, body = read_url_text(api_health_url(normalized))
        if 200 <= status < 400:
            return {"ok": True, "target": normalized, "kind": "api", "message": "Connected to the Faculty Copilot API.", "warning": warning, "details": body[:300]}
        errors.append(f"API health returned HTTP {status}.")
    except (OSError, URLError, TimeoutError) as exc:
        errors.append(f"API health failed: {exc}")
    raise RuntimeError(f"{UNAVAILABLE_MESSAGE} {' '.join(errors[-2:])}")


def html_shell(kind: str, server_url: str = "", message: str = "", warning: str = "") -> str:
    payload = json.dumps({"kind": kind, "serverUrl": server_url, "message": message, "warning": warning})
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{APP_TITLE}</title>
  <style>
    :root {{ color-scheme: dark; --bg:#07090f; --panel:rgba(17,24,39,.82); --line:rgba(148,163,184,.22); --text:#f8fafc; --muted:#a7b0c0; --a:#7c3aed; --b:#06b6d4; --danger:#fb7185; font-family:Inter,ui-sans-serif,"Segoe UI",system-ui,sans-serif; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; min-height:100vh; display:grid; place-items:center; overflow:hidden; color:var(--text); background:radial-gradient(circle at 18% 18%,rgba(124,58,237,.34),transparent 30rem),radial-gradient(circle at 82% 14%,rgba(6,182,212,.22),transparent 32rem),linear-gradient(135deg,#07090f 0%,#111827 55%,#0b1120 100%); }}
    body:before {{ content:""; position:fixed; inset:0; background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px); background-size:42px 42px; mask-image:radial-gradient(circle at center,black,transparent 74%); }}
    main {{ position:relative; width:min(760px,calc(100vw - 44px)); padding:34px; border:1px solid var(--line); border-radius:28px; background:var(--panel); box-shadow:0 26px 90px rgba(0,0,0,.42); backdrop-filter:blur(22px); }}
    .brand {{ display:flex; align-items:center; gap:16px; margin-bottom:20px; }}
    .logo {{ width:54px; height:54px; border-radius:18px; background:radial-gradient(circle at 32% 25%,#fff 0 6%,transparent 7%),linear-gradient(135deg,var(--a),var(--b)); box-shadow:0 16px 40px rgba(124,58,237,.34); }}
    h1 {{ margin:0; font-size:32px; letter-spacing:-.04em; }} .subtitle,p {{ color:var(--muted); line-height:1.6; }}
    label {{ display:block; margin:24px 0 8px; font-weight:700; }}
    input {{ width:100%; border:1px solid var(--line); border-radius:16px; padding:15px 16px; font-size:16px; color:var(--text); background:rgba(2,6,23,.72); outline:none; }}
    input:focus {{ border-color:rgba(6,182,212,.8); box-shadow:0 0 0 4px rgba(6,182,212,.12); }}
    .actions {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:18px; }}
    button {{ border:0; border-radius:999px; padding:12px 18px; color:white; background:linear-gradient(135deg,var(--a),var(--b)); font-weight:800; cursor:pointer; }}
    button.secondary {{ background:rgba(148,163,184,.16); color:#e2e8f0; }} button:disabled {{ opacity:.52; cursor:wait; }}
    .message {{ min-height:24px; margin-top:16px; color:#a7f3d0; white-space:pre-wrap; }} .message.error {{ color:var(--danger); }}
    .warning {{ display:none; margin-top:14px; padding:12px 14px; border-radius:14px; border:1px solid rgba(251,191,36,.36); background:rgba(251,191,36,.10); color:#fde68a; }}
    .loader {{ width:46px; height:46px; border-radius:50%; border:4px solid rgba(255,255,255,.14); border-top-color:var(--b); animation:spin 1s linear infinite; margin:18px 0; }} @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
    .tiny {{ font-size:13px; color:#94a3b8; margin-top:14px; }}
  </style>
</head>
<body>
  <main>
    <div class="brand"><div class="logo"></div><div><h1>Faculty Copilot</h1><div class="subtitle">Desktop client for your private AI study server</div></div></div>
    <section id="loading" hidden><div class="loader"></div><p>Connecting to your Faculty Copilot server...</p></section>
    <section id="setup"><p id="intro"></p><label for="server-url">Server URL</label><input id="server-url" spellcheck="false" placeholder="https://your-public-url"><div class="warning" id="warning"></div><div class="actions"><button id="connect">Connect</button><button class="secondary" id="retry">Retry</button></div><div class="message" id="message"></div><div class="tiny">This desktop app is only a client. It does not run Ollama, ChromaDB, or download AI models. Login and session cookies are handled by the server page inside this window.</div></section>
  </main>
  <script>
    const initial = {payload};
    const input=document.getElementById('server-url'), message=document.getElementById('message'), warning=document.getElementById('warning'), connect=document.getElementById('connect'), retry=document.getElementById('retry'), intro=document.getElementById('intro'), loading=document.getElementById('loading');
    input.value=initial.serverUrl||'';
    intro.textContent=initial.kind==='offline'?'The server is unavailable. You can retry or change the URL below.':'Enter the HTTPS link for your Faculty Copilot server. You only do this on first launch.';
    function apiReady() {{ return window.pywebview && window.pywebview.api; }}
    function setMessage(text,isError=false) {{ message.textContent=text||''; message.className=isError?'message error':'message'; }}
    function setWarning(text) {{ warning.textContent=text||''; warning.style.display=text?'block':'none'; }}
    function busy(isBusy) {{ connect.disabled=isBusy; retry.disabled=isBusy; loading.hidden=!isBusy; }}
    setMessage(initial.message||'', initial.kind==='offline'); setWarning(initial.warning||'');
    async function connectNow() {{
      if(!apiReady()) {{ setMessage('The desktop client is still starting. Try again in a moment.', true); return; }}
      busy(true); setMessage('Checking server...'); setWarning('');
      try {{ const result=await window.pywebview.api.connect(input.value); if(result&&result.warning) setWarning(result.warning); setMessage(result&&result.message?result.message:'Connected.'); }}
      catch(e) {{ setMessage(e&&e.message?e.message:String(e), true); }} finally {{ busy(false); }}
    }}
    connect.addEventListener('click', connectNow); retry.addEventListener('click', connectNow); input.addEventListener('keydown', e => {{ if(e.key==='Enter') connectNow(); }});
  </script>
</body>
</html>
"""


class DesktopClientApi:
    def __init__(self) -> None:
        self.window = None
        self._config = ClientConfig.load()

    def bind_window(self, window: object) -> None:
        self.window = window

    def connect(self, server_url: str) -> dict:
        normalized = normalize_server_url(server_url)
        result = test_server(normalized)
        self._config.server_url = normalized
        self._save_window_state()
        self._config.save()
        if self.window is not None:
            self.window.load_url(normalized)
        return result

    def show_settings(self) -> None:
        if self.window is not None:
            self.window.load_html(html_shell("setup", self._config.server_url, "Change the server URL, then press Connect."))

    def retry(self) -> None:
        if self.window is not None and self._config.server_url:
            self.window.load_html(html_shell("loading", self._config.server_url))

    def reload(self) -> None:
        if self.window is not None and self._config.server_url:
            self.window.load_url(self._config.server_url)

    def logout(self) -> None:
        if self.window is not None and self._config.server_url:
            self.window.load_url(f"{self._config.server_url}/logout")

    def toggle_fullscreen(self) -> None:
        if self.window is not None:
            self.window.toggle_fullscreen()

    def _save_window_state(self) -> None:
        if self.window is None:
            return
        try:
            width = getattr(self.window, "width", None)
            height = getattr(self.window, "height", None)
            if width:
                self._config.width = safe_int(width, self._config.width, MIN_WIDTH, 4096)
            if height:
                self._config.height = safe_int(height, self._config.height, MIN_HEIGHT, 2160)
        except Exception:
            logging.debug("Window size could not be saved", exc_info=True)


def initial_view(config: ClientConfig) -> tuple[str | None, str | None]:
    if "--reset" in sys.argv:
        try:
            config_file().unlink(missing_ok=True)
        except OSError:
            pass
        config.server_url = ""
    if not config.server_url:
        return None, html_shell("setup")
    return None, html_shell("loading", config.server_url)


def delayed_connect(api: DesktopClientApi) -> None:
    def worker() -> None:
        if not api._config.server_url or api.window is None:
            return
        try:
            test_server(api._config.server_url)
            api.window.load_url(api._config.server_url)
        except Exception as exc:
            logging.warning("Initial server connection failed: %s", exc)
            api.window.load_html(html_shell("offline", api._config.server_url, str(exc), security_warning_for_url(api._config.server_url)))
    threading.Thread(target=worker, daemon=True).start()


def main() -> None:
    configure_logging()
    if webview is None:
        raise RuntimeError("pywebview is required. Run build_desktop_client.bat or install pywebview.")
    config = ClientConfig.load()
    api = DesktopClientApi()
    api._config = config
    url, html = initial_view(config)
    menu = [Menu("Faculty Copilot", [MenuAction("Settings", api.show_settings), MenuAction("Reload", api.reload), MenuAction("Logout", api.logout), MenuSeparator(), MenuAction("Fullscreen", api.toggle_fullscreen)])]
    window = webview.create_window(
        APP_TITLE,
        url=url,
        html=html,
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
        raise RuntimeError("Could not create the Faculty Copilot desktop window.")
    api.bind_window(window)
    webview.start(
        delayed_connect,
        api,
        gui="edgechromium",
        private_mode=False,
        storage_path=str(app_data_folder() / "webview_profile"),
        menu=menu,
        icon=str(Path(__file__).resolve().parent / "assets" / "faculty_copilot.ico"),
    )


if __name__ == "__main__":
    main()

