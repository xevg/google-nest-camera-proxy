# auth.py

import configparser


class AuthCredentials:
    """Store the Google credentials """

    def __init__(self, configuration: configparser) -> None:
        """Class for holding authentication information"""

        self._client_id = configuration['AUTH']['client_id']
        self._client_secret = configuration['AUTH']['client_secret']
        self._project_id = configuration['AUTH']['project_id']
        self._access_token_cache_file = configuration['AUTH']['access_token_cache_file']

    @property
    def client_id(self) -> str:
        """Return the client_id. """
        return self._client_id

    @property
    def client_secret(self) -> str:
        """Return the client_secret. """
        return self._client_secret

    @property
    def project_id(self) -> str:
        """Return the project_id. """
        return self._project_id

    @property
    def access_token_cache_file(self) -> str:
        """Return the access_token_cache_file. """
        return self._access_token_cache_file

