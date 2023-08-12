# Script to proxy output from Nest Cameras

import configparser
import logging
import time

import nest
from colorama import Fore
from colorama import Style

from .auth import AuthCredentials
from .rtsp_server import RTSPServer


class GoogleNestCameraProxy:
    """ Gathers the information about the Nest cameras proxies it through mediamtx"""

    def __init__(self, configuration_file: str, no_server: bool = False) -> None:

        self._configfile = configuration_file
        self._no_server = no_server
        self._configuration = configparser.ConfigParser()
        self._configuration.read(self._configfile)

        self._credentials = AuthCredentials(self._configuration)
        self._logger = logging.getLogger(__name__)
        self._logger.warning(f"{Fore.BLUE}Refreshing the camera list{Style.RESET_ALL}")

        # Set up the RTSP Server
        self._rtsp_server = RTSPServer(self._configuration)

        self._devices = None
        self._camera_list = []
        self._get_devices()

    def _get_devices(self):

        # Try getting the devices till we succeed
        while True:
            try:
                napi = nest.Nest(self._credentials.client_id, self._credentials.client_secret,
                                 self._credentials.project_id,
                                 access_token_cache_file=self._credentials.access_token_cache_file)
                self._devices = napi.get_devices()
                break

            except Exception as error:
                self._logger.warning(f"{Fore.RED}Error connecting to Nest ({error=}). "
                                     f"Sleeping and trying again.{Style.RESET_ALL}")
                time.sleep(30)

        max_devices = 5000
        total_devices = 0
        self._camera_list = []
        for i in range(0, len(self._devices)):
            if total_devices >= max_devices:
                break

            device = self._devices[i]
            # Because this sometimes gives a rate limiting error, wrap it in a loop until it succeeds
            while True:
                try:
                    if device.type == 'THERMOSTAT':
                        self._logger.warning(f"{Fore.BLUE}Skipping Thermostat{Style.RESET_ALL}")
                        break
                    elif device.type == 'CAMERA':
                        device_name = device.where
                        device_id = device.name
                        custom_name = device.traits['Info']['customName']
                        if custom_name != "":
                            device_name = f"{device_name} {custom_name}"

                        # Do a lazy load to avoid circular dependencies
                        from .camera import Camera
                        camera = Camera(self._configuration, device, device_name, device_id)
                        self._logger.warning(f"{Fore.BLUE}Added camera {camera.name}{Style.RESET_ALL}")
                        self._camera_list.append(camera)
                        self._rtsp_server.add_camera(camera)
                        total_devices += 1
                        break

                    else:
                        self._logger.error(f"{Fore.RED}Unknown device type '{device.type}'{Style.RESET_ALL}")
                        break
                except Exception as error:
                    self._logger.error(f"{Fore.RED}Error connecting to Nest ({error=}). "
                                       f"Sleeping and trying again.{Style.RESET_ALL}")
                    time.sleep(30)

        # Now that we have all the cameras configured, write the configuration file
        self._rtsp_server.write_configuration_file()

    def run(self):
        if self._no_server:
            self._logger.warning(f"{Fore.RED}Not running mediamtx server, please start it manually.{Style.RESET_ALL}")
        else:
            self._rtsp_server.run()

    def terminate(self):
        self._rtsp_server.terminate()
        for camera in self._camera_list:
            camera.terminate()

    @property
    def camera_list(self) -> list:
        return self._camera_list
    
    @property
    def rtsp_server(self) -> RTSPServer:
        return self._rtsp_server
    
    
    