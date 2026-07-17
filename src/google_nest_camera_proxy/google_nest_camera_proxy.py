# Script to proxy output from Nest Cameras

import configparser
import logging
import os
import time

import nest
from colorama import Fore
from colorama import Style

from .auth import AuthCredentials
from .rtsp_server import RTSPServer


class GoogleNestCameraProxy:
    """Discover Nest cameras and expose each one through MediaMTX."""

    def __init__(self, configuration_file: str, no_server: bool = False) -> None:
        self._configfile = configuration_file
        self._no_server = no_server
        self._configuration = configparser.ConfigParser()
        self._configuration.read(self._configfile)

        self._credentials = AuthCredentials(self._configuration)
        self._logger = logging.getLogger(__name__)
        self._logger.warning(f"{Fore.BLUE}Refreshing the camera list{Style.RESET_ALL}")

        self._rtsp_server = RTSPServer(self._configuration)
        self._devices = None
        self._camera_list = []
        self._get_devices()

    def _get_devices(self):
        camera_names = {
            name.strip()
            for name in os.environ.get("NEST_CAMERA_NAMES", "").split(",")
            if name.strip()
        }
        while True:
            try:
                napi = nest.Nest(
                    self._credentials.client_id,
                    self._credentials.client_secret,
                    self._credentials.project_id,
                    access_token_cache_file=self._credentials.access_token_cache_file,
                )
                self._devices = napi.get_devices()
                break
            except Exception as error:
                self._logger.warning(
                    f"{Fore.RED}Error connecting to Nest ({error=}). "
                    f"Sleeping and trying again.{Style.RESET_ALL}"
                )
                time.sleep(30)

        max_devices = 5000
        total_devices = 0
        self._camera_list = []
        for device in self._devices:
            if total_devices >= max_devices:
                break

            while True:
                try:
                    if device.type == "THERMOSTAT":
                        self._logger.warning(
                            f"{Fore.BLUE}Skipping Thermostat{Style.RESET_ALL}"
                        )
                        break
                    if device.type == "CAMERA":
                        device_name = device.where
                        device_id = device.name
                        custom_name = device.traits["Info"]["customName"]
                        if custom_name:
                            device_name = custom_name

                        # Lazy load avoids a circular import through RTSPServer.
                        from .camera import Camera
                        from .camera import UnsupportedCameraProtocol
                        from .camera import _get_legal_camera_name

                        legal_name = _get_legal_camera_name(device_name)
                        if camera_names and legal_name not in camera_names:
                            self._logger.info(
                                "Skipping camera %s because it is not in "
                                "NEST_CAMERA_NAMES",
                                legal_name,
                            )
                            break

                        try:
                            camera = Camera(
                                self._configuration, device, device_name, device_id
                            )
                        except UnsupportedCameraProtocol as error:
                            self._logger.error(
                                f"{Fore.RED}Skipping camera {device_name}: "
                                f"{error}{Style.RESET_ALL}"
                            )
                            break

                        self._logger.warning(
                            f"{Fore.BLUE}Added camera {camera.legal_camera_name} "
                            f"using {camera.stream_protocol}{Style.RESET_ALL}"
                        )
                        self._camera_list.append(camera)
                        self._rtsp_server.add_camera(camera)
                        total_devices += 1
                        break

                    self._logger.error(
                        f"{Fore.RED}Unknown device type '{device.type}'{Style.RESET_ALL}"
                    )
                    break
                except Exception as error:
                    self._logger.error(
                        f"{Fore.RED}Error connecting to Nest ({error=}). "
                        f"Sleeping and trying again.{Style.RESET_ALL}"
                    )
                    time.sleep(30)

        # The WebRTC entries use source: publisher; RTSP entries retain their
        # Google RTSPS source URL.
        self._rtsp_server.write_configuration_file()

    def run(self):
        if self._no_server:
            self._logger.warning(
                f"{Fore.RED}Not running MediaMTX; it must already be running for "
                f"WebRTC cameras to publish.{Style.RESET_ALL}"
            )
        else:
            # Wait for MediaMTX's process to exist before opening WHIP sessions.
            self._rtsp_server.run()

        for camera in self._camera_list:
            camera.start()

    def terminate(self):
        # Stop publishers first so they can DELETE WHIP sessions and tell Google
        # to stop the corresponding media sessions while MediaMTX still exists.
        # Signal every worker before joining any one of them: macOS Chromium
        # processes can share helper infrastructure, so one worker's shutdown
        # may cause another to exit immediately.
        for camera in self._camera_list:
            camera.request_terminate()
        for camera in self._camera_list:
            camera.terminate()
        self._rtsp_server.terminate()

    @property
    def camera_list(self) -> list:
        return self._camera_list

    @property
    def rtsp_server(self) -> RTSPServer:
        return self._rtsp_server
