from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None


APP_NAME = "AI Study Copilot Server Launcher"
WINDOW_TITLE = "AI Study Copilot Server"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NEW_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
CLOUDFLARE_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)
HTTPS_URL = re.compile(r"https://[A-Za-z0-9][A-Za-z0-9.-]*(?::\d+)?")


def default_project_root() -> Path:
    if getattr(sys, "frozen", False):
        folder = Path(sys.executable).resolve().parent
        return folder.parent if folder.name.lower() == "dist" else folder
    return Path(__file__).resolve().parents[2]


def default_settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return base / "AI Study Copilot" / "server_launcher.json"


@dataclass
class LauncherSettings:
    project_root: str = ""
    api_port: int = 8000
    streamlit_port: int = 8501
    tunnel: str = "none"
    start_minimized: bool = False
    start_with_windows: bool = False
    auto_start: bool = False
    auto_restart: bool = True
    auto_public_access: bool = False

    @classmethod
    def load(cls, path: Path | None = None) -> "LauncherSettings":
        defaults = cls(project_root=str(default_project_root()))
        try:
            data = json.loads((path or default_settings_path()).read_text("utf-8"))
        except (OSError, ValueError, TypeError):
            return defaults
        values = asdict(defaults)
        values.update({key: value for key, value in data.items() if key in values})
        try:
            values["api_port"] = max(1, min(65535, int(values["api_port"])))
            values["streamlit_port"] = max(
                1, min(65535, int(values["streamlit_port"]))
            )
        except (TypeError, ValueError):
            values["api_port"], values["streamlit_port"] = 8000, 8501
        if values["tunnel"] not in {"none", "cloudflare", "tailscale"}:
            values["tunnel"] = "none"
        return cls(**values)

    def save(self, path: Path | None = None) -> None:
        target = path or default_settings_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
        )


@dataclass(frozen=True)
class StatusSnapshot:
    ollama: bool
    fastapi: bool
    streamlit: bool
    tunnel: bool
    local_url: str
    lan_url: str
    public_url: str


def find_program(name: str, candidates: list[Path]) -> str | None:
    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())
    return next((str(item.resolve()) for item in candidates if item.exists()), None)


def find_ollama() -> str | None:
    local, programs = Path(os.getenv("LOCALAPPDATA", "")), Path(
        os.getenv("ProgramFiles", "")
    )
    return find_program(
        "ollama.exe",
        [
            local / "Programs" / "Ollama" / "ollama.exe",
            programs / "Ollama" / "ollama.exe",
        ],
    )


def find_cloudflared() -> str | None:
    local, programs = Path(os.getenv("LOCALAPPDATA", "")), Path(
        os.getenv("ProgramFiles", "")
    )
    return find_program(
        "cloudflared.exe",
        [
            local / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe",
            local / "cloudflared" / "cloudflared.exe",
            programs / "cloudflared" / "cloudflared.exe",
            programs / "Cloudflare" / "Cloudflared" / "cloudflared.exe",
        ],
    )


def find_tailscale() -> str | None:
    local, programs = Path(os.getenv("LOCALAPPDATA", "")), Path(
        os.getenv("ProgramFiles", "")
    )
    return find_program(
        "tailscale.exe",
        [
            programs / "Tailscale" / "tailscale.exe",
            local / "Tailscale" / "tailscale.exe",
        ],
    )


def lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def http_ok(url: str, timeout: float = 2.5) -> bool:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": APP_NAME})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= int(response.status) < 400
    except (OSError, urllib.error.URLError, ValueError):
        return False


def extract_cloudflare_url(text: str) -> str:
    match = CLOUDFLARE_URL.search(text or "")
    return match.group(0).rstrip("/") if match else ""


def parse_cloudflare_named_config(text: str) -> tuple[str, str]:
    """Return tunnel reference and first public hostname from config.yml."""
    tunnel = re.search(
        r"(?mi)^\s*tunnel\s*:\s*[\"']?([^#\s\"']+)", text or ""
    )
    hostname = re.search(
        r"(?mi)^\s*-\s*hostname\s*:\s*[\"']?([^#\s\"']+)", text or ""
    )
    reference = tunnel.group(1).strip() if tunnel else ""
    public_url = f"https://{hostname.group(1).strip()}" if hostname else ""
    return reference, public_url.rstrip("/")


class ServerController:
    def __init__(
        self,
        settings: LauncherSettings,
        log_callback: Callable[[str], None] | None = None,
    ):
        self.settings = settings
        self.log_callback = log_callback or (lambda _line: None)
        self.processes: dict[str, subprocess.Popen] = {}
        self.external_services: set[str] = set()
        self.desired_running = False
        self.active_tunnel = "none"
        self.public_url = ""
        self.public_access_suspended = False
        self._operation_lock = threading.Lock()
        self._process_lock = threading.RLock()
        self._last_start = 0.0
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    @property
    def project_root(self) -> Path:
        return Path(self.settings.project_root).expanduser().resolve()

    @property
    def python(self) -> Path:
        return self.project_root / ".venv" / "Scripts" / "python.exe"

    @property
    def runtime_dir(self) -> Path:
        return self.project_root / "storage" / "runtime"

    @property
    def public_url_file(self) -> Path:
        return self.runtime_dir / "public_url.txt"

    @property
    def log_file(self) -> Path:
        return self.runtime_dir / "server_launcher.log"

    def log(self, message: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        self.log_callback(line)
        try:
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            with self.log_file.open("a", encoding="utf-8") as output:
                output.write(line + "\n")
        except OSError:
            pass

    def environment(self) -> dict[str, str]:
        env = os.environ.copy()
        defaults = {
            "FACULTY_COPILOT_API_HOST": "0.0.0.0",
            "FACULTY_COPILOT_API_PORT": str(self.settings.api_port),
            "FACULTY_COPILOT_STREAMLIT_PORT": str(self.settings.streamlit_port),
            "FACULTY_COPILOT_START_STREAMLIT": "0",
            "FACULTY_COPILOT_AUTH_ENABLED": "0",
            "FACULTY_COPILOT_DEFAULT_USER": "default_user",
            "FACULTY_COPILOT_DEPLOYMENT_MODE": (
                "Public Internet" if self.settings.tunnel != "none" else "LAN"
            ),
            "FACULTY_COPILOT_MAX_UPLOAD_MB": "100",
            "FACULTY_COPILOT_MAX_TOTAL_UPLOAD_MB": "250",
            "FACULTY_COPILOT_MAX_UPLOAD_FILES": "10",
            "FACULTY_COPILOT_IP_RATE_LIMIT": "60",
            "FACULTY_COPILOT_MAX_CONCURRENT_REQUESTS": "32",
            "FACULTY_COPILOT_API_TIMEOUT_SECONDS": "600",
            "FACULTY_COPILOT_STREAMLIT_ACTION_RATE_LIMIT": "20",
            "FACULTY_COPILOT_MAX_CONCURRENT_UI_ACTIONS": "8",
            "FACULTY_COPILOT_TRUSTED_PROXY_IPS": "127.0.0.1,::1",
            "AI_STUDY_SERVER_MODE": "1",
            "AI_STUDY_SERVER_PORT": str(self.settings.streamlit_port),
            "PYTHONUNBUFFERED": "1",
        }
        env.update(defaults)
        return env

    def _spawn(self, name: str, command: list[str], env: dict[str, str]) -> bool:
        with self._process_lock:
            current = self.processes.get(name)
            if current and current.poll() is None:
                self.log(f"{name} rulează deja; nu pornesc un duplicat.")
                return True
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(self.project_root),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=NO_WINDOW | NEW_GROUP,
                )
            except (OSError, ValueError) as exc:
                self.log(f"Nu am putut porni {name}: {exc}")
                return False
            self.processes[name] = process
            self.external_services.discard(name)
        threading.Thread(
            target=self._read_output, args=(name, process), daemon=True
        ).start()
        self.log(f"{name} pornit (PID {process.pid}).")
        return True

    def _read_output(self, name: str, process: subprocess.Popen) -> None:
        if process.stdout is None:
            return
        for raw in iter(process.stdout.readline, ""):
            line = raw.rstrip()
            if not line:
                continue
            self.log(f"{name}: {line}")
            if name == "Tunnel Cloudflare":
                url = extract_cloudflare_url(line)
                if url:
                    self._set_public_url(url)
        code = process.poll()
        if code is not None:
            self.log(f"{name} s-a oprit (cod {code}).")

    def _run(self, command: list[str], timeout: float = 10) -> tuple[int, str]:
        try:
            result = subprocess.run(
                command,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=NO_WINDOW,
                check=False,
            )
            output = "\n".join(part for part in (result.stdout, result.stderr) if part)
            return result.returncode, output.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            return 1, str(exc)

    @staticmethod
    def _wait(probe: Callable[[], bool], seconds: int) -> bool:
        for _ in range(seconds):
            if probe():
                return True
            time.sleep(1)
        return False

    def _set_public_url(self, url: str) -> None:
        self.public_url = url.strip().rstrip("/")
        if self.public_url:
            try:
                self.public_url_file.write_text(self.public_url, encoding="utf-8")
            except OSError as exc:
                self.log(f"Nu am putut salva URL-ul public: {exc}")

    def _clear_public_url(self) -> None:
        self.public_url = ""
        try:
            self.public_url_file.unlink(missing_ok=True)
        except OSError:
            pass

    def ollama_running(self) -> bool:
        return http_ok("http://127.0.0.1:11434/api/tags")

    def fastapi_running(self) -> bool:
        return http_ok(f"http://127.0.0.1:{self.settings.api_port}/health")

    def streamlit_running(self) -> bool:
        return http_ok(
            f"http://127.0.0.1:{self.settings.streamlit_port}/_stcore/health"
        )

    def _tailscale_identity(self) -> tuple[bool, str, str]:
        executable = find_tailscale()
        if not executable:
            return False, "", "Tailscale nu este instalat."
        code, output = self._run([executable, "status", "--json"], 5)
        if code:
            return False, "", "Tailscale nu este conectat."
        try:
            status = json.loads(output)
        except ValueError:
            return False, "", "Starea Tailscale nu este validă."
        online = status.get("BackendState") == "Running" and bool(
            (status.get("Self") or {}).get("Online")
        )
        dns = str((status.get("Self") or {}).get("DNSName") or "").strip(". ")
        return online, dns, "" if online else "Tailscale nu este online."

    def _tailscale_funnel_status(self) -> tuple[bool, str]:
        executable = find_tailscale()
        if not executable:
            return False, ""
        code, output = self._run(
            [executable, "funnel", "status", "--json"], timeout=5
        )
        if code:
            return False, ""
        match = HTTPS_URL.search(output)
        if match:
            return True, match.group(0).rstrip("/")
        try:
            status = json.loads(output)
        except ValueError:
            status = {}
        configured = bool(status) and bool(
            status.get("Web") or status.get("AllowFunnel") or status.get("TCP")
        )
        return configured, ""

    def _cloudflare_named_tunnel(
        self, executable: str
    ) -> tuple[list[str], str, str] | None:
        code, output = self._run(
            [executable, "tunnel", "list", "--output", "json"], timeout=12
        )
        if code:
            self.log("Nu am putut verifica lista Cloudflare Named Tunnels.")
            return None
        try:
            tunnels = json.loads(output)
        except ValueError:
            tunnels = []
        if not isinstance(tunnels, list) or not tunnels:
            self.log("Nu există Cloudflare Named Tunnel; folosesc Quick Tunnel.")
            return None

        config_dir = Path.home() / ".cloudflared"
        configs = [config_dir / "config.yml", config_dir / "config.yaml"]
        for config in configs:
            try:
                reference, public_url = parse_cloudflare_named_config(
                    config.read_text(encoding="utf-8")
                )
            except OSError:
                continue
            known = next(
                (
                    item
                    for item in tunnels
                    if reference
                    in {
                        str(item.get("id") or ""),
                        str(item.get("name") or ""),
                    }
                ),
                None,
            )
            if known and public_url:
                name = str(known.get("name") or reference)
                command = [
                    executable,
                    "tunnel",
                    "--config",
                    str(config),
                    "run",
                    reference,
                ]
                return command, public_url, name
        self.log(
            "Am detectat un Named Tunnel, dar nu are config.yml cu hostname public; "
            "folosesc Quick Tunnel."
        )
        return None

    def tunnel_running(self) -> bool:
        tunnel = self.active_tunnel if self.active_tunnel != "none" else self.settings.tunnel
        if tunnel == "cloudflare":
            process = self.processes.get("Tunnel Cloudflare")
            return bool(process and process.poll() is None and self.public_url)
        if tunnel == "tailscale":
            running, url = self._tailscale_funnel_status()
            if running:
                if not url:
                    online, dns, _error = self._tailscale_identity()
                    url = f"https://{dns}" if online and dns else ""
                if url:
                    self._set_public_url(url)
            return running
        return False

    def status_snapshot(self) -> StatusSnapshot:
        tunnel = self.tunnel_running() if self.settings.tunnel != "none" else False
        if not self.public_url and self.public_url_file.exists():
            try:
                self.public_url = self.public_url_file.read_text("utf-8").strip()
            except OSError:
                pass
        return StatusSnapshot(
            self.ollama_running(),
            self.fastapi_running(),
            self.streamlit_running(),
            tunnel,
            f"http://localhost:{self.settings.streamlit_port}",
            f"http://{lan_ip()}:{self.settings.streamlit_port}",
            self.public_url,
        )

    def start_all(self) -> None:
        if not self._operation_lock.acquire(blocking=False):
            self.log("O operație este deja în curs.")
            return
        try:
            self.desired_running = True
            self._last_start = time.monotonic()
            if not (self.project_root / "apps" / "web" / "app.py").exists():
                self.log("Folder invalid: apps\\web\\app.py lipsește. Verifică Settings.")
                return
            if not self.python.exists():
                self.log("Mediul .venv lipsește. Rulează install.ps1 o singură dată.")
                return
            if self.ollama_running():
                if not (
                    self.processes.get("Ollama")
                    and self.processes["Ollama"].poll() is None
                ):
                    self.external_services.add("Ollama")
                self.log("Ollama rulează deja; nu pornesc un duplicat.")
            else:
                executable = find_ollama()
                if not executable:
                    self.log("Ollama lipsește. Instalează-l de la ollama.com/download/windows.")
                    return
                self._spawn("Ollama", [executable, "serve"], os.environ.copy())
                if not self._wait(self.ollama_running, 30):
                    self.log("Ollama nu a răspuns în 30 de secunde.")
                    return
            env = self.environment()
            if self.fastapi_running():
                if not (
                    self.processes.get("FastAPI")
                    and self.processes["FastAPI"].poll() is None
                ):
                    self.external_services.add("FastAPI")
                self.log("FastAPI rulează deja; nu pornesc un duplicat.")
            else:
                self._spawn(
                    "FastAPI",
                    [
                        str(self.python),
                        "-m",
                        "uvicorn",
                        "server.api.api_server:app",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        str(self.settings.api_port),
                        "--proxy-headers",
                        "--forwarded-allow-ips",
                        env["FACULTY_COPILOT_TRUSTED_PROXY_IPS"],
                    ],
                    env,
                )
            if self.streamlit_running():
                if not (
                    self.processes.get("Streamlit")
                    and self.processes["Streamlit"].poll() is None
                ):
                    self.external_services.add("Streamlit")
                self.log("Streamlit rulează deja; nu pornesc un duplicat.")
            else:
                self._spawn(
                    "Streamlit",
                    [
                        str(self.python),
                        "-m",
                        "streamlit",
                        "run",
                        "apps/web/app.py",
                        "--server.address",
                        "0.0.0.0",
                        "--server.port",
                        str(self.settings.streamlit_port),
                        "--server.headless",
                        "true",
                        "--server.maxUploadSize",
                        env["FACULTY_COPILOT_MAX_UPLOAD_MB"],
                        "--server.enableXsrfProtection",
                        "true",
                        "--server.enableCORS",
                        "true",
                        "--server.enableWebsocketCompression",
                        "true",
                        "--browser.gatherUsageStats",
                        "false",
                    ],
                    env,
                )
            api_ready = self._wait(self.fastapi_running, 60)
            ui_ready = self._wait(self.streamlit_running, 60)
            if not api_ready:
                self.log("FastAPI nu a devenit disponibil în 60 de secunde.")
            if not ui_ready:
                self.log("Streamlit nu a devenit disponibil în 60 de secunde.")
                return
            if (
                self.settings.auto_public_access
                and self.settings.tunnel != "none"
                and not self.public_access_suspended
            ):
                self.start_tunnel()
            self.log("Pornirea serviciilor s-a încheiat.")
        finally:
            self._operation_lock.release()

    def start_tunnel(self) -> None:
        self.public_access_suspended = False
        if self.settings.tunnel == "cloudflare":
            self._start_cloudflare()
        elif self.settings.tunnel == "tailscale":
            self._start_tailscale()
        else:
            self.log("Selectează Cloudflare sau Tailscale în Settings.")

    def enable_public_access(self) -> None:
        if self.settings.tunnel == "none":
            self.log("Public Access nu are un tunnel selectat. Deschide Settings.")
            return
        self.public_access_suspended = False
        if not self.streamlit_running():
            self.log("Streamlit nu rulează; pornesc mai întâi serverul.")
            self.start_all()
        if self.streamlit_running() and not self.tunnel_running():
            self.start_tunnel()

    def disable_public_access(self) -> None:
        self.public_access_suspended = True
        self.stop_tunnel(include_configured=True)

    def restart_public_access(self) -> None:
        self.disable_public_access()
        time.sleep(1)
        self.enable_public_access()

    def _start_cloudflare(self) -> None:
        if self.tunnel_running():
            self.log("Cloudflare Tunnel rulează deja.")
            return
        executable = find_cloudflared()
        if not executable:
            self.log(
                "cloudflared lipsește. Instalează: winget install --id Cloudflare.cloudflared"
            )
            self.log(
                "Alternativ: developers.cloudflare.com/cloudflare-one/"
                "connections/connect-networks/downloads/"
            )
            return
        self._clear_public_url()
        self.active_tunnel = "cloudflare"
        named = self._cloudflare_named_tunnel(executable)
        if named:
            command, public_url, tunnel_name = named
            self._set_public_url(public_url)
            self.log(f"Pornesc Cloudflare Named Tunnel: {tunnel_name}.")
        else:
            command = [
                executable,
                "tunnel",
                "--no-autoupdate",
                "--url",
                f"http://127.0.0.1:{self.settings.streamlit_port}",
            ]
        started = self._spawn(
            "Tunnel Cloudflare",
            command,
            self.environment(),
        )
        if not started:
            self.active_tunnel = "none"
            self._clear_public_url()
            return
        if self._wait(self.tunnel_running, 45):
            self.log(f"Link public: {self.public_url}")
            self.log("Atenție: distribuie linkul numai persoanelor de încredere.")
        else:
            self.log("Cloudflare nu a furnizat un URL în 45 de secunde.")

    def _start_tailscale(self) -> None:
        executable = find_tailscale()
        if not executable:
            self.log("Tailscale lipsește. Instalează-l de la tailscale.com/download/windows.")
            return
        online, dns, error = self._tailscale_identity()
        if not online:
            self.log(error + " Deschide Tailscale și autentifică-te.")
            return
        configured, configured_url = self._tailscale_funnel_status()
        if configured:
            self.active_tunnel = "tailscale"
            self._set_public_url(configured_url or f"https://{dns}")
            self.log(f"Tailscale Funnel este deja configurat: {self.public_url}")
            return
        code, output = self._run([executable, "funnel", "--help"], 10)
        if code or "unknown command" in output.lower():
            self.log("Versiunea Tailscale nu oferă Funnel. Actualizează Tailscale.")
            return
        code, output = self._run(
            [
                executable,
                "funnel",
                "--bg",
                "--https=443",
                "--yes",
                f"http://127.0.0.1:{self.settings.streamlit_port}",
            ],
            30,
        )
        if code:
            self.log(f"Funnel nu a putut fi activat: {output}")
            self.log("Verifică permisiunea Funnel în tailnet; pașii manuali sunt în README.")
            return
        self.active_tunnel = "tailscale"
        _, status_url = self._tailscale_funnel_status()
        url = status_url or (f"https://{dns}" if dns else "")
        self._set_public_url(url)
        self.log(f"Link public: {url or 'nu a putut fi detectat'}")
        self.log("Atenție: distribuie linkul numai persoanelor de încredere.")

    def _stop_process(self, name: str) -> None:
        process = self.processes.get(name)
        if not process or process.poll() is not None:
            return
        self.log(f"Opresc {name}...")
        try:
            process.terminate()
            process.wait(timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                self.log(f"{name} nu a putut fi oprit complet.")
        self.processes.pop(name, None)

    def stop_tunnel(self, include_configured: bool = False) -> None:
        # Stop external Funnel only after an explicit Disable Public Access action.
        tunnel = self.active_tunnel
        if include_configured and tunnel == "none":
            tunnel = self.settings.tunnel
        if tunnel == "cloudflare":
            self._stop_process("Tunnel Cloudflare")
        elif tunnel == "tailscale":
            executable = find_tailscale()
            if executable:
                code, output = self._run(
                    [executable, "funnel", "--https=443", "off"], 15
                )
                self.log(
                    "Tailscale Funnel oprit."
                    if not code
                    else f"Funnel nu s-a oprit curat: {output}"
                )
        self.active_tunnel = "none"
        self._clear_public_url()

    def stop_all(self) -> None:
        if not self._operation_lock.acquire(blocking=False):
            self.log("O operație este deja în curs.")
            return
        try:
            self.desired_running = False
            self.stop_tunnel()
            for name in ("Streamlit", "FastAPI", "Ollama"):
                self._stop_process(name)
            if self.external_services:
                self.log(
                    "Nu am oprit servicii pornite în afara launcherului: "
                    + ", ".join(sorted(self.external_services))
                )
            self.external_services.clear()
            self.log("Serviciile administrate de launcher au fost oprite.")
        finally:
            self._operation_lock.release()

    def restart_all(self) -> None:
        self.stop_all()
        time.sleep(1)
        self.start_all()

    def repair_crashed_services(self) -> None:
        if (
            not self.desired_running
            or not self.settings.auto_restart
            or time.monotonic() - self._last_start < 20
        ):
            return
        status = self.status_snapshot()
        tunnel_expected = (
            self.settings.auto_public_access
            and not self.public_access_suspended
            and self.settings.tunnel != "none"
        )
        tunnel_missing = tunnel_expected and not status.tunnel
        if not all((status.ollama, status.fastapi, status.streamlit)) or tunnel_missing:
            self.log("Serviciu oprit detectat; încerc repornirea automată.")
            self.start_all()


def configure_windows_startup(enabled: bool) -> None:
    if winreg is None:
        return
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        if enabled:
            if getattr(sys, "frozen", False):
                command = f'"{sys.executable}" --minimized'
            else:
                pythonw = Path(sys.executable).with_name("pythonw.exe")
                command = f'"{pythonw}" "{Path(__file__).resolve()}" --minimized'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: "LauncherApp"):
        super().__init__(parent.root)
        self.parent = parent
        self.title("Settings")
        self.resizable(False, False)
        self.transient(parent.root)
        self.grab_set()
        settings = parent.settings
        self.values = {
            "root": tk.StringVar(value=settings.project_root),
            "api": tk.StringVar(value=str(settings.api_port)),
            "ui": tk.StringVar(value=str(settings.streamlit_port)),
            "tunnel": tk.StringVar(value=settings.tunnel),
            "minimized": tk.BooleanVar(value=settings.start_minimized),
            "windows": tk.BooleanVar(value=settings.start_with_windows),
            "auto_start": tk.BooleanVar(value=settings.auto_start),
            "auto_restart": tk.BooleanVar(value=settings.auto_restart),
            "auto_public": tk.BooleanVar(value=settings.auto_public_access),
        }
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Project folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.values["root"], width=52).grid(
            row=1, column=0, padx=(0, 8)
        )
        ttk.Button(frame, text="Browse", command=self._browse).grid(row=1, column=1)
        for row, label, key in (
            (2, "FastAPI port", "api"),
            (4, "Streamlit port", "ui"),
        ):
            ttk.Label(frame, text=label).grid(
                row=row, column=0, sticky="w", pady=(12, 0)
            )
            ttk.Entry(frame, textvariable=self.values[key], width=12).grid(
                row=row + 1, column=0, sticky="w"
            )
        ttk.Label(frame, text="Public tunnel").grid(
            row=6, column=0, sticky="w", pady=(12, 0)
        )
        ttk.Combobox(
            frame,
            textvariable=self.values["tunnel"],
            values=("none", "cloudflare", "tailscale"),
            state="readonly",
            width=20,
        ).grid(row=7, column=0, sticky="w")
        options = ttk.Frame(frame)
        options.grid(row=8, column=0, columnspan=2, sticky="w", pady=(14, 0))
        for text, key in (
            ("Start minimized", "minimized"),
            ("Start with Windows", "windows"),
            ("Auto-start server when launcher opens", "auto_start"),
            ("Auto Public Access", "auto_public"),
            ("Auto-restart crashed services", "auto_restart"),
        ):
            ttk.Checkbutton(options, text=text, variable=self.values[key]).pack(
                anchor="w"
            )
        actions = ttk.Frame(frame)
        actions.grid(row=9, column=0, columnspan=2, sticky="e", pady=(18, 0))
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(actions, text="Save", command=self._save).pack(side="right")

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.values["root"].get() or None)
        if chosen:
            self.values["root"].set(chosen)

    def _save(self) -> None:
        try:
            api, ui = int(self.values["api"].get()), int(self.values["ui"].get())
            if not 1 <= api <= 65535 or not 1 <= ui <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Invalid ports", "Ports must be between 1 and 65535.", parent=self
            )
            return
        root = Path(self.values["root"].get()).expanduser()
        if not (root / "apps" / "web" / "app.py").exists():
            messagebox.showerror(
                "Invalid folder", "The selected folder does not contain apps\\web\\app.py.", parent=self
            )
            return
        settings = LauncherSettings(
            str(root.resolve()),
            api,
            ui,
            self.values["tunnel"].get(),
            self.values["minimized"].get(),
            self.values["windows"].get(),
            self.values["auto_start"].get(),
            self.values["auto_restart"].get(),
            self.values["auto_public"].get(),
        )
        try:
            settings.save()
            configure_windows_startup(settings.start_with_windows)
        except OSError as exc:
            messagebox.showerror("Settings", str(exc), parent=self)
            return
        self.parent.apply_settings(settings)
        self.destroy()


class LauncherApp:
    def __init__(self, root: tk.Tk, settings: LauncherSettings, minimized=False):
        self.root, self.settings = root, settings
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.controller = ServerController(settings, self._queue_log)
        self.status_vars = {
            name: tk.StringVar(value="checking...")
            for name in ("Ollama", "FastAPI", "Streamlit", "Tunnel")
        }
        self.local_url, self.lan_url, self.public_url = (
            tk.StringVar(value="-"),
            tk.StringVar(value="-"),
            tk.StringVar(value="-"),
        )
        self.public_status = tk.StringVar(value="🔴 Offline")
        self._refreshing = False
        self._build()
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(150, self._drain)
        root.after(300, self._refresh)
        root.after(7000, self._maintenance)
        if minimized or settings.start_minimized:
            root.after(100, root.iconify)
        if settings.auto_public_access or settings.auto_start:
            root.after(500, self.start_all)

    def _build(self) -> None:
        self.root.title(WINDOW_TITLE)
        self.root.geometry("900x650")
        self.root.minsize(760, 540)
        frame = ttk.Frame(self.root, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=WINDOW_TITLE, font=("Segoe UI", 18, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            frame, text="Manage Ollama, FastAPI, Streamlit and secure public tunnels."
        ).pack(anchor="w", pady=(0, 12))
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(0, 12))
        for text, command in (
            ("Start All", self.start_all),
            ("Stop All", self.stop_all),
            ("Restart All", self.restart_all),
            ("Open App", self.open_app),
            ("Open Logs", self.open_logs),
            ("Settings", lambda: SettingsDialog(self)),
        ):
            ttk.Button(actions, text=text, command=command).pack(
                side="left", padx=(0, 7)
            )
        statuses = ttk.LabelFrame(frame, text="Service status", padding=10)
        statuses.pack(fill="x")
        for index, name in enumerate(self.status_vars):
            cell = ttk.Frame(statuses, padding=(8, 4))
            cell.grid(row=0, column=index, sticky="ew")
            statuses.columnconfigure(index, weight=1)
            ttk.Label(cell, text=name, font=("Segoe UI", 10, "bold")).pack()
            ttk.Label(cell, textvariable=self.status_vars[name]).pack()
        urls = ttk.LabelFrame(frame, text="URLs", padding=10)
        urls.pack(fill="x", pady=12)
        for row, (label, variable) in enumerate(
            (
                ("Local URL", self.local_url),
                ("LAN URL", self.lan_url),
            )
        ):
            ttk.Label(urls, text=label, width=12).grid(row=row, column=0, sticky="w")
            ttk.Entry(urls, textvariable=variable, state="readonly").grid(
                row=row, column=1, sticky="ew", pady=2
            )
        urls.columnconfigure(1, weight=1)
        public = ttk.LabelFrame(frame, text="Public Access", padding=10)
        public.pack(fill="x", pady=(0, 12))
        ttk.Label(public, text="Status", width=12).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            public,
            textvariable=self.public_status,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(public, text="Public URL", width=12).grid(
            row=1, column=0, sticky="w", pady=(5, 0)
        )
        ttk.Entry(public, textvariable=self.public_url, state="readonly").grid(
            row=1, column=1, columnspan=4, sticky="ew", pady=(5, 0)
        )
        buttons = ttk.Frame(public)
        buttons.grid(row=2, column=0, columnspan=5, sticky="w", pady=(9, 0))
        for text, command in (
            ("Enable Public Access", self.enable_public),
            ("Disable Public Access", self.disable_public),
            ("Restart Public Access", self.restart_public),
            ("Copy", self.copy_public),
            ("Open", self.open_public),
        ):
            ttk.Button(buttons, text=text, command=command).pack(
                side="left", padx=(0, 7)
            )
        public.columnconfigure(1, weight=1)
        logs = ttk.LabelFrame(frame, text="Logs", padding=8)
        logs.pack(fill="both", expand=True)
        self.log_view = scrolledtext.ScrolledText(
            logs,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
            background="#111827",
            foreground="#e5e7eb",
        )
        self.log_view.pack(fill="both", expand=True)
        self._append("Launcher ready. Status refresh runs every 7 seconds.")

    def _queue_log(self, line: str) -> None:
        self.events.put(("log", line))

    def _append(self, line: str) -> None:
        self.log_view.configure(state="normal")
        self.log_view.insert("end", line + "\n")
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def _drain(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "log":
                    self._append(str(payload))
                else:
                    self._apply_status(payload)
                    self._refreshing = False
        except queue.Empty:
            pass
        self.root.after(150, self._drain)

    def _apply_status(self, status: StatusSnapshot) -> None:
        for name, running in (
            ("Ollama", status.ollama),
            ("FastAPI", status.fastapi),
            ("Streamlit", status.streamlit),
            ("Tunnel", status.tunnel),
        ):
            self.status_vars[name].set("● running" if running else "○ stopped")
        self.local_url.set(status.local_url)
        self.lan_url.set(status.lan_url)
        self.public_url.set(status.public_url or "-")
        self.public_status.set("🟢 Online" if status.tunnel else "🔴 Offline")

    def _refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True

        def worker() -> None:
            try:
                self.events.put(("status", self.controller.status_snapshot()))
            except Exception as exc:
                self.events.put(("log", f"Status check failed: {exc}"))
                self._refreshing = False

        threading.Thread(target=worker, daemon=True).start()

    def _maintenance(self) -> None:
        self._refresh()
        threading.Thread(
            target=self.controller.repair_crashed_services, daemon=True
        ).start()
        self.root.after(7000, self._maintenance)

    @staticmethod
    def _background(action: Callable[[], None]) -> None:
        threading.Thread(target=action, daemon=True).start()

    def start_all(self) -> None:
        self._background(self.controller.start_all)

    def stop_all(self) -> None:
        self._background(self.controller.stop_all)

    def restart_all(self) -> None:
        self._background(self.controller.restart_all)

    def enable_public(self) -> None:
        self._background(self.controller.enable_public_access)

    def disable_public(self) -> None:
        self._background(self.controller.disable_public_access)

    def restart_public(self) -> None:
        self._background(self.controller.restart_public_access)

    def open_app(self) -> None:
        url = self.local_url.get()
        webbrowser.open(
            url if url != "-" else f"http://localhost:{self.settings.streamlit_port}"
        )

    def copy_public(self) -> None:
        url = self.public_url.get()
        if url == "-":
            messagebox.showinfo(
                "Public link", "No public URL is available. Start a tunnel first."
            )
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self._append("Public link copied. Share it only with trusted people.")

    def open_public(self) -> None:
        url = self.public_url.get()
        if url == "-":
            messagebox.showinfo(
                "Public link", "No public URL is available. Enable Public Access first."
            )
            return
        webbrowser.open(url)

    def open_logs(self) -> None:
        self.controller.runtime_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(self.controller.runtime_dir))
        except (AttributeError, OSError) as exc:
            messagebox.showerror("Logs", str(exc))

    def apply_settings(self, settings: LauncherSettings) -> None:
        self.settings = settings
        self.controller.settings = settings
        self._append("Settings saved. Restart services to apply changes.")
        self._refresh()

    def _close(self) -> None:
        managed = any(
            process.poll() is None for process in self.controller.processes.values()
        ) or self.controller.active_tunnel != "none"
        if managed:
            answer = messagebox.askyesno(
                "Close launcher",
                "Closing the launcher also stops the services it started. Continue?",
            )
            if not answer:
                return
            self.controller.stop_all()
        self.root.destroy()


def acquire_single_instance() -> object | None:
    if os.name != "nt":
        return object()
    import ctypes

    handle = ctypes.windll.kernel32.CreateMutexW(
        None, False, "AIStudyCopilotServerLauncher"
    )
    return None if not handle or ctypes.windll.kernel32.GetLastError() == 183 else handle


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--minimized", action="store_true")
    args = parser.parse_args()
    mutex = acquire_single_instance()
    if mutex is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(APP_NAME, "The server launcher is already running.")
        root.destroy()
        return 0
    root = tk.Tk()
    LauncherApp(root, LauncherSettings.load(), args.minimized)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
