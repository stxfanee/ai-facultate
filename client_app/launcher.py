from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import webview


APP_TITLE = "Copilot Facultate"
DEFAULT_STREAMLIT_URL = "http://localhost:8501"


def settings_file() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_TITLE / "settings.json"
    return Path.home() / ".copilot_facultate" / "settings.json"


def load_settings() -> dict:
    path = settings_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings: dict) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_url(value: str) -> str:
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        return DEFAULT_STREAMLIT_URL
    parsed = urlparse(cleaned)
    if not parsed.scheme:
        cleaned = f"http://{cleaned}"
    return cleaned.rstrip("/")


def setup_html(default_url: str) -> str:
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
      width: min(640px, calc(100vw - 48px));
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
    button {{
      margin-top: 18px;
      border: 0;
      border-radius: 6px;
      background: #ff4b55;
      color: white;
      padding: 12px 18px;
      font-weight: 700;
      cursor: pointer;
    }}
    .hint {{
      margin-top: 18px;
      color: #aab0bd;
      font-size: 13px;
    }}
    .error {{
      color: #ff9aa1;
      min-height: 20px;
      margin-top: 12px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Copilot Facultate</h1>
    <p>Introdu URL-ul Streamlit al serverului desktop. AI-ul, Ollama,
    ChromaDB si documentele raman pe server.</p>
    <label for="url">Server Streamlit URL</label>
    <input id="url" value="{default_url}" placeholder="http://100.x.y.z:8501">
    <button onclick="save()">Salveaza si deschide</button>
    <div class="error" id="error"></div>
    <div class="hint">
      Recomandat prin Tailscale: http://ADRESA_TAILSCALE:8501.
      Nu folosi port forwarding public.
    </div>
  </main>
  <script>
    async function save() {{
      const input = document.getElementById('url');
      const error = document.getElementById('error');
      const value = input.value.trim();
      if (!value) {{
        error.textContent = 'Introdu URL-ul serverului.';
        return;
      }}
      try {{
        await window.pywebview.api.save_url(value);
      }} catch (e) {{
        error.textContent = e && e.message ? e.message : String(e);
      }}
    }}
    document.getElementById('url').addEventListener('keydown', (event) => {{
      if (event.key === 'Enter') save();
    }});
  </script>
</body>
</html>
"""


class LauncherApi:
    def __init__(self, window: webview.Window) -> None:
        self.window = window

    def save_url(self, url: str) -> None:
        normalized = normalize_url(url)
        save_settings({"streamlit_url": normalized})
        self.window.load_url(normalized)


def initial_url_or_html() -> tuple[str | None, str | None]:
    if "--reset" in sys.argv:
        try:
            settings_file().unlink(missing_ok=True)
        except OSError:
            pass

    settings = load_settings()
    url = settings.get("streamlit_url")
    if url:
        return normalize_url(url), None
    return None, setup_html(DEFAULT_STREAMLIT_URL)


def maximize_window(window: webview.Window) -> None:
    try:
        window.maximize()
    except Exception:
        pass


def main() -> None:
    url, html = initial_url_or_html()
    window = webview.create_window(
        APP_TITLE,
        url=url,
        html=html,
        width=1280,
        height=820,
        resizable=True,
        confirm_close=False,
        js_api=None,
    )
    window.expose(LauncherApi(window).save_url)
    webview.start(maximize_window, window, gui="edgechromium")


if __name__ == "__main__":
    main()
