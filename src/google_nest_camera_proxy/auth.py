# auth.py

import configparser
import os


class AuthCredentials:
    """Store the Google credentials"""

    def __init__(self, configuration: configparser.ConfigParser) -> None:
        """Class for holding authentication information"""

        self._client_id = configuration.get(
            "AUTH", "client_id", fallback=os.environ["CLIENT_ID"]
        )
        self._client_secret = configuration.get(
            "AUTH", "client_secret", fallback=os.environ["CLIENT_SECRET"]
        )
        self._project_id = configuration.get(
            "AUTH", "project_id", fallback=os.environ["PROJECT_ID"]
        )
        self._access_token_cache_file = configuration.get(
            "AUTH",
            "access_token_cache_file",
            fallback=f"{os.path.expanduser('~')}/.config/nest/token_cache",
        )

    @property
    def client_id(self) -> str:
        """Return the client_id."""
        return self._client_id

    @property
    def client_secret(self) -> str:
        """Return the client_secret."""
        return self._client_secret

    @property
    def project_id(self) -> str:
        """Return the project_id."""
        return self._project_id

    @property
    def access_token_cache_file(self) -> str:
        """Return the access_token_cache_file."""
        return self._access_token_cache_file
