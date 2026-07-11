from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.parse import ParseResult, urlparse, urlunparse
from urllib.request import Request, urlopen

import webview
from webview.menu import Menu, MenuAction, MenuSeparator


APP_TITLE = "Co-pilot Facultate"
APP_DATA_FOLDER = "Copilot Facultate"  # Keep existing client settings compatible.
DEFAULT_SERVER_URL = "http://192.168.1.201:8000"
CONNECTION_ERROR = (
    "Nu pot ajunge la server. Verifică dacă desktopul este pornit și "
    "start_server.bat rulează."
)


def app_data_folder() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_DATA_FOLDER
    return Path.home() / ".copilot_facultate"


def config_file() -> Path:
    return app_data_folder() / "config.json"


def configure_logging() -> None:
    log_path = app_data_folder() / "client_error.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            encoding="utf-8",
        )
    except OSError:
        logging.basicConfig(level=logging.INFO)


def load_config() -> dict:
    path = config_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_config(config: dict) -> None:
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_url(value: str) -> str:
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        cleaned = DEFAULT_SERVER_URL
    if not urlparse(cleaned).scheme:
        cleaned = f"http://{cleaned}"
    return cleaned.rstrip("/")


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
    netloc = f"{netloc}:{port}"
    return urlunparse((parsed.scheme, netloc, "", "", "", ""))


def api_url_from_server_url(server_url: str) -> str:
    normalized = normalize_url(server_url)
    parsed = urlparse(normalized)
    if parsed.port == 8501:
        return with_port(parsed, 8000)
    return normalized


def app_url_from_server_url(server_url: str) -> str:
    normalized = normalize_url(server_url)
    parsed = urlparse(normalized)
    if parsed.port == 8000:
        return with_port(parsed, 8501)
    return normalized


def test_connection(server_url: str) -> dict:
    api_url = api_url_from_server_url(server_url)
    request = Request(f"{api_url}/health", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        logging.exception("Conexiunea FastAPI a esuat pentru %s", api_url)
        raise RuntimeError(CONNECTION_ERROR) from exc
    if not payload.get("api"):
        logging.error("Raspuns /health invalid de la %s: %r", api_url, payload)
        raise RuntimeError(CONNECTION_ERROR)
    return payload


def setup_html(default_url: str, message: str = "") -> str:
    escaped_url = json.dumps(default_url)
    escaped_message = json.dumps(message)
    return f"""
<!doctype html>
<html lang="ro">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{APP_TITLE}</title>
  <style>
    :root {{
      color-scheme: dark;
      font-family: "Segoe UI", Arial, sans-serif;
      background: #0f1117;
      color: #f4f4f5;
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background:
        radial-gradient(circle at 20% 20%, rgba(255, 75, 85, .18), transparent 32rem),
        linear-gradient(135deg, #0f1117 0%, #20232d 100%);
    }}
    main {{
      width: min(680px, calc(100vw - 48px));
      border: 1px solid #343846;
      background: #171923;
      padding: 28px;
      box-shadow: 0 18px 70px rgba(0,0,0,.35);
      border-radius: 8px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      line-height: 1.15;
    }}
    p {{
      color: #c9ced8;
      line-height: 1.5;
    }}
    label {{
      display: block;
      margin-top: 22px;
      margin-bottom: 8px;
      font-weight: 600;
    }}
    input {{
      box-sizing: border-box;
      width: 100%;
      border: 1px solid #44495a;
      border-radius: 6px;
      padding: 13px 14px;
      font-size: 15px;
      color: #f4f4f5;
      background: #0f1117;
      outline: none;
    }}
    input:focus {{
      border-color: #ff4b55;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      background: #ff4b55;
      color: white;
      padding: 12px 18px;
      font-weight: 700;
      cursor: pointer;
    }}
    button.secondary {{
      background: #313643;
    }}
    .hint {{
      margin-top: 18px;
      color: #aab0bd;
      font-size: 13px;
    }}
    .message {{
      min-height: 22px;
      margin-top: 14px;
      color: #a7f3d0;
    }}
    .message.error {{
      color: #ff9aa1;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Co-pilot Facultate</h1>
    <p>Introdu adresa serverului de pe desktop. Laptopul nu rulează Ollama,
    nu descarcă modele și nu creează ChromaDB.</p>
    <label for="url">Server URL</label>
    <input id="url" placeholder="http://192.168.1.201:8000">
    <div class="actions">
      <button id="test-button" onclick="testConnection()" disabled>Test connection</button>
      <button id="save-button" class="secondary" onclick="saveOnly()" disabled>Save</button>
      <button id="open-button" onclick="openApp()" disabled>Open app</button>
    </div>
    <div class="message" id="message"></div>
    <div class="hint">
      Implicit testez API-ul pe portul 8000. Când deschizi aplicația, launcherul
      încarcă automat Streamlit-ul serverului pe portul 8501. Nu folosi localhost
      decât dacă serverul rulează chiar pe acest laptop.
    </div>
  </main>
  <script>
    const defaultUrl = {escaped_url};
    const initialMessage = {escaped_message};
    const input = document.getElementById('url');
    const message = document.getElementById('message');
    const buttons = document.querySelectorAll('button');
    input.value = defaultUrl;
    message.textContent = initialMessage;
    message.className = initialMessage ? 'message' : 'message';

    function setMessage(text, isError=false) {{
      message.textContent = text || '';
      message.className = isError ? 'message error' : 'message';
    }}

    function apiReady() {{
      return window.pywebview && window.pywebview.api;
    }}

    window.addEventListener('pywebviewready', () => {{
      buttons.forEach((button) => button.disabled = false);
    }});

    async function testConnection() {{
      setMessage('Testez conexiunea...');
      try {{
        if (!apiReady()) throw new Error('Launcher API nu este încă pregătit.');
        const result = await window.pywebview.api.test_connection(input.value);
        setMessage(result);
      }} catch (e) {{
        setMessage(e && e.message ? e.message : String(e), true);
      }}
    }}

    async function saveOnly() {{
      try {{
        if (!apiReady()) throw new Error('Launcher API nu este încă pregătit.');
        const result = await window.pywebview.api.save_config(input.value);
        setMessage(result);
      }} catch (e) {{
        setMessage(e && e.message ? e.message : String(e), true);
      }}
    }}

    async function openApp() {{
      setMessage('Deschid aplicația...');
      try {{
        if (!apiReady()) throw new Error('Launcher API nu este încă pregătit.');
        await window.pywebview.api.open_app(input.value);
      }} catch (e) {{
        setMessage(e && e.message ? e.message : String(e), true);
      }}
    }}

    input.addEventListener('keydown', (event) => {{
      if (event.key === 'Enter') openApp();
    }});
  </script>
</body>
</html>
"""


class LauncherApi:
    def __init__(self) -> None:
        self.window: webview.Window | None = None

    def bind_window(self, window: webview.Window) -> None:
        self.window = window

    def save_config(self, server_url: str) -> str:
        normalized = normalize_url(server_url)
        app_url = app_url_from_server_url(normalized)
        write_config({"server_url": normalized, "app_url": app_url})
        logging.info("Configuratie salvata: API=%s Streamlit=%s", normalized, app_url)
        return f"Salvat: {normalized}"

    def test_connection(self, server_url: str) -> str:
        # pywebview executa apelurile JS API in afara firului UI; timeout-ul
        # limiteaza si cazul in care serverul nu este accesibil.
        payload = test_connection(server_url)
        documents = payload.get("documents", 0)
        chunks = payload.get("chunks", 0)
        return f"Conectat la server. Documente: {documents}, fragmente: {chunks}."

    def open_app(self, server_url: str) -> None:
        normalized = normalize_url(server_url)
        try:
            test_connection(normalized)
        except RuntimeError as exc:
            raise exc
        app_url = app_url_from_server_url(normalized)
        write_config({"server_url": normalized, "app_url": app_url})
        if self.window is not None:
            try:
                self.window.load_url(app_url)
            except Exception:
                logging.exception("Nu am putut deschide Streamlit la %s", app_url)
                raise RuntimeError(CONNECTION_ERROR) from None

    def show_settings(self) -> None:
        config = load_config()
        server_url = config.get("server_url", DEFAULT_SERVER_URL)
        if self.window is not None:
            self.window.load_html(setup_html(server_url))

    def reload_app(self) -> None:
        config = load_config()
        app_url = config.get("app_url") or app_url_from_server_url(
            config.get("server_url", DEFAULT_SERVER_URL)
        )
        if self.window is not None:
            self.window.load_url(app_url)

    def toggle_fullscreen(self) -> None:
        if self.window is not None:
            self.window.toggle_fullscreen()


def initial_target() -> tuple[str | None, str | None]:
    if "--reset" in sys.argv:
        try:
            config_file().unlink(missing_ok=True)
        except OSError:
            pass

    config = load_config()
    server_url = config.get("server_url")
    app_url = config.get("app_url")
    if server_url and app_url:
        return app_url, None
    return None, setup_html(server_url or DEFAULT_SERVER_URL)


def on_start(window: webview.Window) -> None:
    try:
        window.maximize()
    except Exception:
        pass


def main() -> None:
    configure_logging()
    logging.info("Pornire launcher")
    api = LauncherApi()
    url, html = initial_target()
    menu = [
        Menu(
            "Copilot",
            [
                MenuAction("Setări server", api.show_settings),
                MenuAction("Reload", api.reload_app),
                MenuSeparator(),
                MenuAction("Fullscreen", api.toggle_fullscreen),
            ],
        )
    ]
    try:
        window = webview.create_window(
            APP_TITLE,
            url=url,
            html=html,
            width=1280,
            height=820,
            resizable=True,
            maximized=True,
            confirm_close=False,
            js_api=api,
            menu=menu,
        )
    except Exception:
        logging.exception("Crearea ferestrei WebView2 a esuat")
        raise
    if window is None:
        raise RuntimeError("Nu am putut crea fereastra WebView2.")
    api.bind_window(window)
    webview.start(on_start, window, gui="edgechromium", menu=menu)


if __name__ == "__main__":
    main()
