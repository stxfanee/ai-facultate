import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TailscaleLauncherTests(unittest.TestCase):
    def test_batch_delegates_to_checked_powershell_launcher(self):
        batch = (PROJECT_ROOT / "scripts" / "legacy" / "START_PUBLIC_TAILSCALE.bat").read_text(
            encoding="utf-8"
        )
        self.assertIn("start_public_tailscale.ps1", batch)
        self.assertIn("%ERRORLEVEL%", batch)

    def test_launcher_exposes_only_streamlit_and_keeps_safety_limits(self):
        script = (PROJECT_ROOT / "scripts" / "deployment" / "start_public_tailscale.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('"--https=443"', script)
        self.assertIn('"http://127.0.0.1:$StreamlitPort"', script)
        self.assertNotIn('"--https=8443"', script)
        self.assertIn('$env:FACULTY_COPILOT_AUTH_ENABLED = "0"', script)
        self.assertIn('$env:FACULTY_COPILOT_MAX_UPLOAD_MB = "100"', script)
        self.assertIn('$env:FACULTY_COPILOT_STREAMLIT_ACTION_RATE_LIMIT = "20"', script)
        self.assertIn("Distribuie linkul numai persoanelor de incredere", script)

    def test_launcher_contains_manual_recovery_steps(self):
        script = (PROJECT_ROOT / "scripts" / "deployment" / "start_public_tailscale.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("https://tailscale.com/download/windows", script)
        self.assertIn("tailscale status", script)
        self.assertIn("tailscale funnel status --json", script)


if __name__ == "__main__":
    unittest.main()


