import configparser
import os
from google_nest_camera_proxy.auth import AuthCredentials


def test_auth():
    configfile = f"{os.path.dirname(__file__)}/test-config"
    configuration = configparser.ConfigParser()
    configuration.read(configfile)
    creds = AuthCredentials(configuration)
    assert creds.access_token_cache_file is not None
    assert creds.client_id is not None
    assert creds.client_secret is not None
    assert creds.project_id is not None


if __name__ == "__main__":
    test_auth()