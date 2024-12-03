import unittest
import uuid
from unittest.mock import ANY, Mock, patch

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

    @patch("charm.SiteManagerClient._login")
    @patch("charm.requests.get")
    @patch("charm.requests.delete")
    def test_remove_site(self, mock_delete, mock_sites, mock_login):
        cluster_id = str(uuid.uuid4())
        mock_login.return_value = "token"

        sites = Mock(
            **{
                "json.return_value": {"items": [{"id": "site_1"}]},
                "ok": True,
            }
        )
        mock_sites.return_value = sites

        self.client.remove_site(cluster_id)

        mock_login.assert_called_once()
        mock_sites.assert_called_once_with(
            "http://localhost/api/v1/sites", params={"cluster_id": cluster_id}, headers=ANY
        )
        mock_delete.assert_called_once_with("http://localhost/api/v1/sites/site_1", headers=ANY)

    @patch("charm.SiteManagerClient._login")
    @patch("charm.requests.get")
    @patch("charm.requests.delete")
    def test_remove_site_pending(self, mock_delete, mock_sites, mock_login):
        cluster_id = str(uuid.uuid4())
        mock_login.return_value = "token"

        no_sites = Mock(
            **{
                "json.return_value": {"items": []},
                "ok": True,
            }
        )
        pending_sites = Mock(
            **{
                "json.return_value": {
                    "items": [
                        {"id": "pending_1", "cluster_id": str(uuid.uuid4())},
                        {"id": "pending_2", "cluster_id": cluster_id},
                    ]
                },
                "ok": True,
            }
        )
        mock_sites.side_effect = [no_sites, pending_sites]

        self.client.remove_site(cluster_id)

        mock_login.assert_called_once()
        mock_sites.assert_any_call(
            "http://localhost/api/v1/sites", params={"cluster_id": cluster_id}, headers=ANY
        )
        mock_sites.assert_any_call("http://localhost/api/v1/sites/pending", headers=ANY)
        mock_delete.assert_called_once_with("http://localhost/api/v1/sites/pending_2", headers=ANY)
