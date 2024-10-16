import unittest
from unittest.mock import Mock, patch

from api import AuthError, SiteManagerClient


class TestSiteManagerClient(unittest.TestCase):

    def setUp(self):
        self.client = SiteManagerClient("username", "password", "http://localhost")

    @patch("charm.requests.post")
    def test_login(self, mock_post):
        result = result = Mock(
            **{
                "json.return_value": {"access_token": "token"},
                "ok": True,
                "status_code": 200,
            }
        )
        mock_post.return_value = result

        assert self.client._login() == {"Authorization": "Bearer token"}

    @patch("charm.requests.post")
    def test_login_failed(self, mock_post):
        result = Mock(
            **{
                "json.return_value": {"error": {}},
                "ok": False,
            }
        )
        mock_post.return_value = result
        with self.assertRaises(AuthError):
            self.client._login()

    @patch("charm.SiteManagerClient._login")
    @patch("charm.requests.post")
    def test_issue_enrol_token(self, mock_tokens, mock_login):
        mock_login.return_value = "token"

        result = Mock(
            **{
                "json.return_value": {"items": [{"value": "enrol_token"}]},
                "ok": True,
            }
        )
        mock_tokens.return_value = result

        token = self.client.issue_enrol_token()

        mock_login.assert_called_once()
        mock_tokens.assert_called_once()
        assert token == "enrol_token"
