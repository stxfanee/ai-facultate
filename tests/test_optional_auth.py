import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

import api_server


def make_request(
    host: str = "100.64.0.10",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/documents",
            "headers": headers or [],
            "client": (host, 12345),
            "server": ("testserver", 8000),
            "scheme": "http",
            "query_string": b"",
        }
    )


class OptionalAuthenticationTests(unittest.TestCase):
    def test_remote_request_uses_default_user_when_auth_is_off(self):
        environment = {
            "FACULTY_COPILOT_AUTH_ENABLED": "0",
            "FACULTY_COPILOT_DEFAULT_USER": "default_user",
        }
        with patch.dict("os.environ", environment, clear=False):
            self.assertEqual(
                api_server.authenticate_http_request(make_request()),
                "default_user",
            )

    def test_remote_request_uses_passwordless_profile_header(self):
        environment = {"FACULTY_COPILOT_AUTH_ENABLED": "0"}
        request = make_request(headers=[(b"x-user-profile", b"Ana Pop")])
        with (
            patch.dict("os.environ", environment, clear=False),
            patch.object(
                api_server.study_app.USER_ACCOUNTS,
                "create_profile",
                return_value="ana-pop",
            ) as create_profile,
        ):
            self.assertEqual(
                api_server.authenticate_http_request(request),
                "ana-pop",
            )
        create_profile.assert_called_once_with("Ana Pop")

    def test_remote_request_still_requires_token_when_auth_is_on(self):
        environment = {
            "FACULTY_COPILOT_AUTH_ENABLED": "1",
            "FACULTY_COPILOT_ALLOW_LOCAL_API": "0",
        }
        with patch.dict("os.environ", environment, clear=False):
            with self.assertRaises(HTTPException) as raised:
                api_server.authenticate_http_request(make_request())
        self.assertEqual(raised.exception.status_code, 401)

    def test_api_endpoint_skips_login_and_preserves_default_workspace(self):
        environment = {
            "FACULTY_COPILOT_AUTH_ENABLED": "0",
            "FACULTY_COPILOT_DEFAULT_USER": "default_user",
        }
        with (
            patch.dict("os.environ", environment, clear=False),
            patch.object(api_server.study_app, "ensure_project_dirs"),
            patch.object(api_server.study_app, "get_indexed_documents", return_value=[]),
        ):
            response = TestClient(api_server.app).get("/documents")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "default_user")


if __name__ == "__main__":
    unittest.main()
