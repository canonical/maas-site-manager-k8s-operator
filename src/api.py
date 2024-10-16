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
