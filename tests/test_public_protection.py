import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.requests import Request

import api_server


def make_request(host: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": headers,
            "client": (host, 12345),
            "server": ("testserver", 8000),
            "scheme": "http",
            "query_string": b"",
        }
    )


class PublicProtectionTests(unittest.TestCase):
    def test_trusted_proxy_can_supply_original_client_ip(self):
        request = make_request(
            "127.0.0.1",
            [(b"x-forwarded-for", b"203.0.113.25, 127.0.0.1")],
        )
        with patch.dict(
            os.environ,
            {"FACULTY_COPILOT_TRUSTED_PROXY_IPS": "127.0.0.1/32"},
            clear=False,
        ):
            self.assertEqual(api_server.request_client_ip(request), "203.0.113.25")

    def test_untrusted_client_cannot_spoof_forwarded_ip(self):
        request = make_request(
            "192.168.1.25",
            [(b"x-forwarded-for", b"203.0.113.99")],
        )
        with patch.dict(
            os.environ,
            {"FACULTY_COPILOT_TRUSTED_PROXY_IPS": "127.0.0.1/32"},
            clear=False,
        ):
            self.assertEqual(api_server.request_client_ip(request), "192.168.1.25")

    def test_cloudflare_header_is_used_only_from_trusted_proxy(self):
        request = make_request(
            "127.0.0.1",
            [(b"cf-connecting-ip", b"198.51.100.7")],
        )
        with patch.dict(
            os.environ,
            {"FACULTY_COPILOT_TRUSTED_PROXY_IPS": "127.0.0.1/32"},
            clear=False,
        ):
            self.assertEqual(api_server.request_client_ip(request), "198.51.100.7")

    def test_public_health_reports_urls_connections_gpu_and_protection(self):
        environment = {
            "FACULTY_COPILOT_DEPLOYMENT_MODE": "Public Internet",
            "FACULTY_COPILOT_PUBLIC_URL": "https://study.example.com",
            "FACULTY_COPILOT_PUBLIC_API_URL": "https://api.study.example.com",
            "FACULTY_COPILOT_AUTH_ENABLED": "0",
        }
        with (
            patch.dict(os.environ, environment, clear=False),
            patch.object(api_server.study_app, "ensure_project_dirs"),
            patch.object(api_server.study_app, "ollama_is_running", return_value=True),
            patch.object(api_server.study_app, "get_lan_ip", return_value="192.168.1.50"),
            patch.object(api_server.study_app, "get_tailscale_ip", return_value="100.64.0.2"),
            patch.object(api_server.study_app, "get_indexed_documents", return_value=[]),
            patch.object(api_server.study_app, "count_indexed_chunks", return_value=0),
            patch.object(
                api_server.study_app.SERVER_CONNECTIONS,
                "diagnostics",
                return_value={
                    "connected_users": 2,
                    "distinct_workspaces": 1,
                    "ttl_seconds": 900,
                },
            ),
            patch.object(
                api_server,
                "get_gpu_status",
                return_value={"available": True, "utilization_percent": 25},
            ),
        ):
            response = TestClient(api_server.app).get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deployment_mode"], "Public Internet")
        self.assertEqual(payload["urls"]["public"], "https://api.study.example.com")
        self.assertEqual(payload["urls"]["public_ui"], "https://study.example.com")
        self.assertEqual(payload["connections"]["connected_users"], 2)
        self.assertTrue(payload["gpu"]["available"])
        self.assertIsNone(payload["project_root"])


if __name__ == "__main__":
    unittest.main()
