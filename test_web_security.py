import unittest
from io import BytesIO
from unittest.mock import Mock

from request_guard import check_request_limit, reset_request_limits
from web_app import MatchDeskHandler


class PublicRouteTests(unittest.TestCase):
    def test_homepage_is_served_without_authentication(self):
        handler = object.__new__(MatchDeskHandler)
        handler.path = "/"
        handler._send_file = Mock()
        handler._send = Mock()

        handler.do_GET()

        handler._send_file.assert_called_once_with("index.html")

    def test_post_routes_are_processed_without_authentication(self):
        handler = object.__new__(MatchDeskHandler)
        handler.path = "/unknown"
        handler._send = Mock()

        handler.do_POST()

        handler._send.assert_called_once_with(404, {"error": "Route inconnue"})

    def test_post_rejects_json_values_that_are_not_objects(self):
        handler = object.__new__(MatchDeskHandler)
        handler.path = "/api/analyze"
        handler.headers = {"Content-Length": "2"}
        handler.rfile = BytesIO(b"[]")
        handler._send = Mock()

        handler.do_POST()

        handler._send.assert_called_once_with(
            400, {"error": "Le corps JSON doit être un objet"}
        )


class RequestLimitTests(unittest.TestCase):
    def setUp(self):
        reset_request_limits()

    def tearDown(self):
        reset_request_limits()

    def test_daily_picks_limit_recovers_after_window(self):
        self.assertIsNone(check_request_limit("local-client", "/api/daily-picks", now=100))
        self.assertEqual(check_request_limit("local-client", "/api/daily-picks", now=101), 29)
        self.assertIsNone(check_request_limit("local-client", "/api/daily-picks", now=130))


if __name__ == "__main__":
    unittest.main()