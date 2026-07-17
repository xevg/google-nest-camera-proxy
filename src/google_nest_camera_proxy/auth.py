# auth.py

import configparser
import os


class AuthCredentials:
    """Store the Google credentials."""

    def __init__(self, configuration: configparser.ConfigParser) -> None:
        self._client_id = configuration.get("AUTH", "client_id")
        self._client_secret = configuration.get("AUTH", "client_secret")
        self._project_id = configuration.get("AUTH", "project_id")
        self._access_token_cache_file = configuration.get(
            "AUTH",
            "access_token_cache_file",
            fallback=f"{os.path.expanduser('~')}/.config/nest/token_cache",
        )

    @property
    def client_id(self) -> str:
        return self._client_id

    @property
    def client_secret(self) -> str:
        return self._client_secret

    @property
    def project_id(self) -> str:
        return self._project_id

    @property
    def access_token_cache_file(self) -> str:
        return self._access_token_cache_file
