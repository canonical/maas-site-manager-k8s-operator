"""MAAS Site Manager API client."""

import logging
from typing import Dict

import requests

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Failed to authenticate with the API."""


class ApiError(Exception):
    """API client error."""


class SiteManagerClient:
    """Site Manager API client."""

    def __init__(self, username: str, password: str, url: str) -> None:
        self._username = username
        self._password = password
        self._url = url

    def _login(self) -> Dict[str, str]:
        """Authenticate client."""
        resp = requests.post(
            f"{self._url}/api/v1/login",
            data={
                "username": self._username,
                "password": self._password,
            },
        )
        if not resp.ok:
            raise AuthError(f"Failed to authenticate: {resp.text}")
        jwt = resp.json().get("access_token")
        return {"Authorization": f"Bearer {jwt}"}

    def issue_enrol_token(self) -> str:
        """Issue an enrolment token.

        Raises:
            ApiError: API failed to comply with request

        Returns:
            str: encoded JWT enrolment token
        """
        headers = self._login()

        resp = requests.post(
            f"{self._url}/api/v1/tokens",
            json={
                "count": 1,
                "duration": 3600,
            },
            headers=headers,
        )
        if not resp.ok:
            raise ApiError(f"Failed to issue enrolment token: {resp.text}")

        tokens = resp.json().get("items")
        return tokens[0]["value"]

    def remove_site(self, cluster_id: str) -> None:
        """Remove a MAAS Site from MAAS Site Manager.

        Raises:
            ApiError: API failed to comply with request

        Returns:
            None
        """
        headers = self._login()

        resp = requests.get(
            f"{self._url}/api/v1/sites",
            params={"cluster_id": cluster_id},
            headers=headers,
        )
        if not resp.ok:
            raise ApiError(f"Failed to query sites: {resp.text}")

        sites = resp.json().get("items")
        if len(sites) > 1:
            raise ApiError(
                f"More than one sites with the same cluster_id: {[site['id'] for site in sites]}"
            )
        elif len(sites) == 1:
            resp = requests.delete(
                f"{self._url}/api/v1/sites/{sites[0]['id']}",
                headers=headers,
            )
            if not resp.ok:
                raise ApiError(f"Failed to delete site: {resp.text}")
            return

        # search pending sites
        resp = requests.get(
            f"{self._url}/api/v1/sites/pending",
            headers=headers,
        )
        if not resp.ok:
            raise ApiError(f"Failed to query pending sites: {resp.text}")

        sites = resp.json().get("items")
        # perform check with Python since we cannot filter pending sites from the API
        sites_with_cluster_id = [site["id"] for site in sites if site["cluster_id"] == cluster_id]
        if len(sites_with_cluster_id) > 1:
            raise ApiError(
                f"More than one pending sites with the same cluster_id: {sites_with_cluster_id}"
            )
        elif len(sites_with_cluster_id) == 1:
            resp = requests.delete(
                f"{self._url}/api/v1/sites/{sites[0]['id']}",
                headers=headers,
            )
            if not resp.ok:
                raise ApiError(f"Failed to delete site: {resp.text}")
