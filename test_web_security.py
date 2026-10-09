import base64
import unittest
from unittest.mock import patch

from web_app import MatchDeskHandler


class ProductionRouteSecurityTests(unittest.TestCase):
    def test_health_is_public_for_platform_probe(self):
        handler = object.__new__(MatchDeskHandler)
        handler.headers = {}
        with patch("web_app.IS_PRODUCTION", True):
            self.assertTrue(handler._authorized("/health"))

    def test_requires_credentials_in_production(self):
        handler = object.__new__(MatchDeskHandler)
        handler.headers = {}
        with patch("web_app.IS_PRODUCTION", True):
            self.assertFalse(handler._authorized())

    def test_accepts_correct_basic_credentials(self):
        handler = object.__new__(MatchDeskHandler)
        token = base64.b64encode(b"private-user:long-private-password").decode("ascii")
        handler.headers = {"Authorization": f"Basic {token}"}
        with (
            patch("web_app.IS_PRODUCTION", True),
            patch("web_app.WEB_AUTH_USERNAME", "private-user"),
            patch("web_app.WEB_AUTH_PASSWORD", "long-private-password"),
        ):
            self.assertTrue(handler._authorized())

    def test_rejects_wrong_password(self):
        handler = object.__new__(MatchDeskHandler)
        token = base64.b64encode(b"private-user:wrong-password").decode("ascii")
        handler.headers = {"Authorization": f"Basic {token}"}
        with (
            patch("web_app.IS_PRODUCTION", True),
            patch("web_app.WEB_AUTH_USERNAME", "private-user"),
            patch("web_app.WEB_AUTH_PASSWORD", "long-private-password"),
        ):
            self.assertFalse(handler._authorized())


if __name__ == "__main__":
    unittest.main()