import unittest
from unittest.mock import Mock, PropertyMock, patch

from api import SiteManagerClient


class TestSiteManagerClient(unittest.TestCase):

    def setUp(self):
        self.client = SiteManagerClient("username", "password", "http://localhost")

    @patch("charm.requests.post")
    def test_login(self, mock_post):
        result = Mock()
        result.json.return_value = {"access_token": "token"}
        mock_post.return_value = result
        mock_post.ok = PropertyMock(return_value=True)

        assert self.client._login() == "token"

    @patch("charm.requests.post")
    def test_login_failed(self, mock_post):
        result = Mock()
        result.json.return_value = {"error": {}}
        mock_post.return_value = result
        mock_post.ok = PropertyMock(return_value=False)

        assert self.client._login() is None

    @patch("charm.SiteManagerClient._login")
    @patch("charm.requests.post")
    def test_issue_enrol_token(self, mock_tokens, mock_login):
        mock_login.return_value = "token"

        result = Mock()
        result.json.return_value = {"items": [{"value": "enrol_token"}]}
        mock_tokens.return_value = result
        mock_tokens.ok = PropertyMock(return_value=False)

        token = self.client.issue_enrol_token()

        mock_login.assert_called_once()
        mock_tokens.assert_called_once()
        assert token == "enrol_token"
