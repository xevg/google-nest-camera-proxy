import datetime
import datetime
import json
import logging
import os
import subprocess
import threading
import time
from configparser import ConfigParser
from custom_logger import CustomLogger

import nest
import nest.nest
from colorama import Fore
from colorama import Style
from dateutil import parser
from dateutil import tz

from auth import AuthCredentials
from filelogger import FileLogger
from rtsp_server import RTSPServer


class Camera:
    """ The Nest Camera Class"""

    def __init__(self, credentials: AuthCredentials, configuration: ConfigParser, device: nest.nest.Device,
                 device_name: str, device_id: str) -> None:

        # Initial Parameter Settings

        self._credentials = credentials
        self._configuration = configuration
        self._camera = device
        self._current_status = 'Initializing'

        self._stream_url = None
        self._terminate_signal = threading.Event()

        # Get the camera name

        self._name = device_name
        self._device_id = device_id
        self._legal_camera_name = self._get_legal_camera_name(self._name)

        # Start the logger

        self._log = CustomLogger(f'{self._legal_camera_name}', log_dir='/Users/xev/logs/rtsp')

        # Get the port the rtsp server will listen on

        self._server_port = configuration.getint('CAMERAS', self._legal_camera_name, fallback=None)
        if self._server_port is None:
            self._log.error(f"No camera for '{self._legal_camera_name}' in configuration file")
            return

        self._executable = configuration.get('RTSP_SERVER', 'executable')

        # How often we refresh the token. The stream expires after 5 minutes, so no more than 4:30
        self._extension_interval = 4.5 * 60  # 4 minutes 30 seconds
        self._start_time = datetime.datetime.now()

        # Get the initial token
        self._get_token()

        # Set up the extension timer
        self._timer = threading.Timer(self._extension_interval, self._renew_token)
        self._timer.setName(f'{self.name} Timer')
        self._timer.start()

        # Write the configuration file
        self._config_file = RTSPServer(self)
        self._config_file.write_file()

        # Run the server in a different thread
        self._rtsp_thread = threading.Thread(target=self._run_rtsp_server)
        self._rtsp_thread.setName(f'{self.name} RSTP Server')
        self._rtsp_thread.start()
        return

    def __del__(self):
        self.terminate()

    def _run_rtsp_server(self):

        # Start the RTSP process
        self._subprocess = subprocess.Popen([self._executable, self._config_file.config_filename],
                                            stderr=subprocess.PIPE, stdout=subprocess.PIPE)

        number_not_published = 0
        while True:
            # Check to see if we are being asked to terminate
            if self._terminate_signal.is_set():
                self._subprocess.terminate()
                return

            line = self._subprocess.stdout.readline().decode('utf-8').strip()
            if not line:
                break
            self._log.info(f"RTSP: {line}")
            if line.find('no one is publishing to path') != -1:
                number_not_published += 1
                self._current_status = "Not Publishing"
                self._log.info(f"<{self.name}> No one publishing, incremented to {number_not_published}")

            elif line.find('[rtsp source] ready') != -1:
                self._log.info(f"<{self.name}> started publishing after {number_not_published} attempts")
                self._current_status = "Publishing"
                number_not_published = 0

            elif line.find('is reading from path') != -1:
                self._log.info(f"<{self.name}> SecuritySpy started reading")
                self._current_status = "Streaming"

            # If we're not seeing the data published, then we need to reset the feed and get a new token
            if number_not_published > 5:
                self._log.info(f"<{self.name}> Too many failures, trying to reset")
                self._current_status = "Resetting"
                self._reset()
                return

        # Check to see if the process has terminated
        if self._subprocess.poll() is not None:
            self._log.error(f"Process camera for '{self._legal_camera_name}' died")
            self._current_status = "Resetting"
            self._reset()
            return

    def _reset(self):
        # Kill the RTSP server, and then wait 5 seconds for the port to clear
        self._subprocess.terminate()
        time.sleep(5)
        self._get_token()
        # Write the configuration file
        self._config_file = RTSPServer(self)
        self._config_file.write_file()

        # Run the server in a different thread
        self._rtsp_thread = threading.Thread(target=self._run_rtsp_server)
        self._rtsp_thread.start()

    @staticmethod
    def _get_legal_camera_name(name: str) -> str:
        legal_characters = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_.~-"

        get_vals = list(filter(lambda x: x in legal_characters, name))
        return "".join(get_vals)

    @property
    def name(self) -> str:
        """Return the camera name. """
        return self._name.replace(' ', '_')

    @property
    def stream_url(self) -> str:
        """ Return the URL """
        return self._stream_url

    @property
    def configuration(self) -> ConfigParser:
        return self._configuration

    @property
    def legal_camera_name(self) -> str:
        return self._legal_camera_name

    @property
    def server_port(self) -> int:
        return self._server_port

    @property
    def current_status(self) -> str:
        return self._current_status

    def _get_token(self) -> None:
        """ Get the Rtsp Stream Token """

        # Loop until we actually get a token
        while True:
            try:
                parameters = json.loads('{}')
                response = self._camera.send_cmd('CameraLiveStream.GenerateRtspStream', parameters)

                self._stream_url = response['results']['streamUrls']['rtspUrl']
                self._streamToken = response['results']['streamToken']
                self._streamExtensionToken = response['results']['streamExtensionToken']
                self._expiresAt = response['results']['expiresAt']

                # print(f"Got token:\n"
                #       f"         StreamURL: {self._stream_url}\n"
                #       f"      Stream Token: {self._streamToken}\n"
                #       f"   Extension Token: {self._streamExtensionToken}\n"
                #       f"        Expires At: {self._expiresAt}")

                self._expiration_time = parser.isoparse(response['results']['expiresAt']).astimezone(tz.tzlocal())
                message = 'Got token for {}, expiration time: {} - time to expiration = {}'.format(
                    self.name, str(self._expiration_time).split('.')[0],
                    str(self._expiration_time - datetime.datetime.now(tz.tzlocal())).split('.')[0])
                self._log.info(message)

                # We succeeded in getting the token, so break the loop
                break

            except nest.APIError as error:
                self._log.error(f"Received a Nest APIError, authenticating camera {error=}")

            except Exception as error:
                self._log.info(f"Unexpected error getting token {error=}, {type(error)=}")

            # Wait till rate limit goes away
            time.sleep(30)

        return

    def _renew_token(self) -> None:
        """ Renew the camera's token """

        # Check to see if we were requested to terminate the process

        if self._terminate_signal.is_set():
            self._log.debug(f"Token renewal for {self.name} ending.")
            return

        try:
            json_string = '{"streamExtensionToken" : "' + self._streamExtensionToken + '"}'
            parameter = json.loads(json_string)
            extend_response = self._camera.send_cmd('CameraLiveStream.ExtendRtspStream', parameter)
            self._streamExtensionToken = extend_response['results']['streamExtensionToken']
            self._expiresAt = extend_response['results']['expiresAt']

            # print(f"Got token:\n"
            #       f"         StreamURL: {self._stream_url}\n"
            #       f"      Stream Token: {self._streamToken}\n"
            #       f"   Extension Token: {self._streamExtensionToken}\n"
            #       f"        Expires At: {self._expiresAt}")

            self._expiration_time = parser.isoparse(extend_response['results']['expiresAt']).astimezone(tz.tzlocal())
            message = f"Renewed token for {self.name} expiration time: {str(self._expiration_time).split('.')[0]}" \
                      f" - time to expiration = " \
                      f"{str(self._expiration_time - datetime.datetime.now(tz.tzlocal())).split('.')[0]}"
            self._log.info(message)

        except nest.APIError as error:
            self._log.error(f"Received a Nest APIError, re-authenticating camera {error=}")
            self._get_token()

        except Exception as error:
            self._log.info(f"Unexpected error extending token {error=}, {type(error)=}")
            self._get_token()

        # Add the next extension timer
        self._timer = threading.Timer(self._extension_interval, self._renew_token)
        self._timer.start()

    def terminate(self) -> None:
        """ Indicate that the threads should terminate """
        print(f"<{self.name}> Terminating")
        self._terminate_signal.set()

