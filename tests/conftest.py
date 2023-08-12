import pytest
import configparser
import os


@pytest.fixture
def get_configuration():
    configfile = get_configuration_file()
    configuration = configparser.ConfigParser()
    configuration.read(configfile)


def get_configuration_file():
    return f"{os.path.expanduser('~')}/.config/nest/config"
