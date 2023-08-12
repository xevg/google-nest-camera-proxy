import datetime
import json
import logging
import threading
import time
from configparser import ConfigParser

import nest
import nest.nest
from dateutil import parser
from dateutil import tz

# from .auth import AuthCredentials


def _get_legal_camera_name(name: str) -> str:
    legal_characters = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_.~-"

    get_vals = list(filter(lambda x: x in legal_characters, name))
    return "".join(get_vals)


class Camera:
    """ The Nest Camera Class"""

    def __init__(self, configuration: ConfigParser, device: nest.nest.Device,
                 device_name: str, device_id: str) -> None:

        # Initial Parameter Settings

        # self._credentials = credentials
        self._configuration = configuration
        self._camera = device

        self._stream_url = None
        self._terminate_signal = threading.Event()

        # Get the camera name

        self._name = device_name
        self._device_id = device_id
        self._legal_camera_name = _get_legal_camera_name(self._name)

        # Start the logger

        self._log = logging.getLogger(f'{self._legal_camera_name}')

        # How often we refresh the token. The stream expires after 5 minutes, so no more than 4:30
        self._extension_interval = 4.5 * 60  # 4 minutes 30 seconds
        self._start_time = datetime.datetime.now()

        # Get the initial token
        self._get_token()

        # Set up the extension timer
        self._timer = threading.Timer(self._extension_interval, self._renew_token)
        self._timer.setName(f'{self.name} Extension Timer')
        self._timer.start()

        return

    def __del__(self):
        self.terminate()

    def reset(self):
        self._get_token()

    @property
    def name(self) -> str:
        """Return the camera name. """
        return self._name.replace(' ', '_')

    @property
    def stream_url(self) -> str:
        """ Return the URL """
        return self._stream_url

    @property
    def legal_camera_name(self) -> str:
        return self._legal_camera_name

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
                self._log.error(f"Received a Nest APIError, authenticating camera {error=}. Sleeping for a bit ...")

            except Exception as error:
                self._log.error(f"Unexpected error getting token {error=}, {type(error)=}")

            # Wait till rate limit goes away
            time.sleep(30)

        return

    def _renew_token(self) -> None:
        """ Renew the camera's token """

        # Check to see if we were requested to terminate the process

        if self._terminate_signal.is_set():
            self._log.warning(f"Token renewal for {self.name} ending.")
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
            self._log.error(f"Unexpected error extending token {error=}, {type(error)=}")
            self._get_token()

        # Add the next extension timer
        self._timer = threading.Timer(self._extension_interval, self._renew_token)
        self._timer.start()

    def terminate(self) -> None:
        """ Indicate that the threads should terminate """
        self._log.warning(f"<{self.name}> Terminating")
        self._terminate_signal.set()
        self._timer.cancel()

    def __lt__(self, obj):
        return self.legal_camera_name < obj.legal_camera_name

    def __gt__(self, obj):
        return self.legal_camera_name > obj.legal_camera_name

    def __le__(self, obj):
        return self.legal_camera_name <= obj.legal_camera_name

    def __ge__(self, obj):
        return self.legal_camera_name >= obj.legal_camera_name

    def __eq__(self, obj):
        return self.legal_camera_name == obj.legal_camera_name
