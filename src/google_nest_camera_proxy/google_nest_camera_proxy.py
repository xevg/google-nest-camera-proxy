# Script to proxy output from Nest Cameras

import configparser
import logging
import os
import time

import click
import nest
from colorama import Fore
from colorama import Style

from auth import AuthCredentials
from rtsp_server import RTSPServer


@click.command()
@click.option('-c', '--configuration-file', type=click.Path(exists=True),
              default=f"{os.path.expanduser('~')}/.config/nest/config",
              help="Where the configuration for this program is located")
@click.option('-d', '--debug', is_flag=True, help="Turn on debugging output")
def google_nest_camera_proxy(configuration_file, debug):
    """ Configures the proxy rtsp server, and keeps it updated

    \b
    CONFIGURATION
    -------------
    The configuration file looks like this:

    \b
    [AUTH]
        client_id = client_id from Google
        client_secret = client secret from Google
        project_id = project id from Google
        access_token_cache_file = /Users/ME/.config/nest/token_cache

    \b
    [RTSP_SERVER]
        executable = /usr/local/bin/rtsp-simple-server
        config_filename = /Users/ME/.config/nest/rtsp

        See the README.md file to see how to get those values.
    """

    configfile = configuration_file
    configuration = configparser.ConfigParser()
    configuration.read(configfile)

    logging_format = '%(asctime)s <%(name)s> %(message)s'
    logging_dateformat = '%m/%d/%Y %I:%M:%S %p'
    if debug:
        logging_level = logging.INFO
    else:
        logging_level = logging.WARNING

    logging.basicConfig(level=logging_level, format=logging_format, datefmt=logging_dateformat)
    _LOGGER = logging.getLogger(__name__)
    _LOGGER.info("Starting the program")

    credentials = AuthCredentials(configuration)

    _LOGGER.warning(f"{Fore.BLUE}Refreshing the camera list{Style.RESET_ALL}")

    # Set up the RTSP Server
    rtsp_server = RTSPServer(configuration)

    # Try getting the devices till we succeed
    while True:
        try:
            napi = nest.Nest(credentials.client_id, credentials.client_secret,
                             credentials.project_id, access_token_cache_file=credentials.access_token_cache_file)
            devices = napi.get_devices()
            break

        except Exception as error:
            _LOGGER.warning(f"{Fore.RED}Error connecting to Nest ({error=}). "
                            f"Sleeping and trying again.{Style.RESET_ALL}")
            time.sleep(30)

    max_devices = 5000
    total_devices = 0
    camera_list = []
    for i in range(0, len(devices)):
        if total_devices >= max_devices:
            break

        device = devices[i]
        # Because this sometimes gives a rate limiting error, wrap it in a loop until it succeeds
        while True:
            try:
                if device.type == 'THERMOSTAT':
                    _LOGGER.warning(f"{Fore.BLUE}Skipping Thermostat{Style.RESET_ALL}")
                    break
                elif device.type == 'CAMERA':
                    device_name = device.where
                    device_id = device.name
                    custom_name = device.traits['Info']['customName']
                    if custom_name != "":
                        device_name = f"{device_name} {custom_name}"

                    # Do a lazy load to avoid circular dependencies
                    from camera import Camera
                    camera = Camera(credentials, configuration, device, device_name, device_id)
                    _LOGGER.warning(f"{Fore.BLUE}Added camera {camera.name}{Style.RESET_ALL}")
                    camera_list.append(camera)
                    rtsp_server.add_camera(camera)
                    total_devices += 1
                    break

                else:
                    _LOGGER.error(f"{Fore.RED}Unknown device type '{device.type}'{Style.RESET_ALL}")
                    break
            except Exception as error:
                _LOGGER.error(f"{Fore.RED}Error connecting to Nest ({error=}). "
                              f"Sleeping and trying again.{Style.RESET_ALL}")
                time.sleep(30)

    rtsp_server.run()
    # Now wait till all threads end or until someone hits 'q'
    _LOGGER.debug("Program chugging away ...")
    while True:
        time.sleep(15)
        out_string = str()
        for camera in sorted(camera_list):
            name = camera.legal_camera_name
            out_string = f"{out_string}\n{name:>25}: {rtsp_server.status[name]}"
        _LOGGER.info(f"{out_string}\n")


if __name__ == "__main__":
    google_nest_camera_proxy()
