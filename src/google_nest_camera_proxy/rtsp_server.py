# rtsp_server.py
import logging
import os
import re
import configparser
import subprocess
import threading
from .camera import Camera


class RTSPServer:
    """ Manage the RTSP server. This can run in one of two ways, a single rtsp server, or one for each camera """

    def __init__(self, configuration: configparser.ConfigParser) -> None:

        self._configuration = configuration
        self._camera_list = {}
        self._status = {}
        self._seperator = "# NEST EDITS BELOW -- DO NOT EDIT THIS LINE OR BELOW\n"

        # TODO: Do I want to back up the configuration file?
        # self._dir, self._filename = os.path.split(self._filepath)
        # timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        # shutil.copyfile(self._filepath, f"{self._dir}/backup/{self._filename}.{timestamp}")

        self._config_filename = self._configuration.get('RTSP_SERVER', 'config_filename',
                                                        fallback=f"{os.path.expanduser('~')}/.config/nest/rtsp.yml")
        self._executable = configuration.get('RTSP_SERVER', 'executable')

        # Set up logging
        self._log = logging.getLogger(f'RTSP Server')

        # Set up a signal if we want to terminate the process
        self._terminate_signal = threading.Event()
        self._rtsp_thread = None
        self._subprocess = None

        return

    def run(self):
        # Run the server in a different thread
        self._rtsp_thread = threading.Thread(target=self._run_server)
        self._rtsp_thread.setName('RTSP Server')
        self._rtsp_thread.start()

    def add_camera(self, camera: Camera) -> None:
        """ Add a camera to the list of cameras"""

        self._camera_list[camera.legal_camera_name] = camera
        return

    def _run_server(self):
        """ Run a single RTSP server """

        # Set up regular expressions
        re_not_publishing = re.compile(r"no one is publishing to path '([^']*)")
        re_source_ready = re.compile(r"\[path ([^\]]*)\] \[rtsp source\] ready")
        re_reading_from_path = re.compile(r"is reading from path '([^']*)'")

        # Set up the metrics for the cameras
        number_not_published = {}
        for camera in self._camera_list.values():
            number_not_published[camera.legal_camera_name] = 0
            self._status[camera.legal_camera_name] = 'Initializing'

        # Write the configuration file
        self.write_configuration_file()

        # Start the RTSP process
        self._subprocess = subprocess.Popen([self._executable, self._config_filename],
                                            stderr=subprocess.PIPE, stdout=subprocess.PIPE)

        while True:
            # Check to see if we are being asked to terminate
            if self._terminate_signal.is_set():
                self._subprocess.terminate()
                return

            line = self._subprocess.stdout.readline().decode('utf-8').strip()
            if not line:
                break
            self._log.info(f"RTSP: {line}")
            re_match = re_not_publishing.search(line)
            if re_match:
                camera_name = re_match.group(1)
                if camera_name not in self._status.keys():
                    self._status[camera_name] = 'Initializing'
                    number_not_published[camera_name] = 0

                self._status[camera_name] = "Not Publishing"
                number_not_published[camera_name] += 1
                self._log.info(f"<{camera_name}> No one publishing, incremented to {number_not_published[camera_name]}")

            re_match = re_source_ready.search(line)
            if re_match:
                camera_name = re_match.group(1)
                if camera_name not in self._status.keys():
                    self._status[camera_name] = 'Initializing'
                    number_not_published[camera_name] = 0

                self._status[camera_name] = "Publishing"
                number_not_published[camera_name] = 0
                self._log.warning(f"<{camera_name}> started publishing after "
                                  f"{number_not_published[camera_name]} attempts")

            re_match = re_reading_from_path.search(line)
            if re_match:
                camera_name = re_match.group(1)
                self._log.warning(f"<{camera_name}> Someone started reading the stream")
                if camera_name not in self._status.keys():
                    self._status[camera_name] = 'Initializing'
                    number_not_published[camera_name] = 0

                self._status[camera_name] = "Streaming"

            # If we're not seeing the data published, then we need to reset the feed and get a new token
            for camera_name in number_not_published.keys():
                if number_not_published[camera_name] > 5:
                    self._status[camera_name] = "Resetting"
                    self._log.warning(f"<{camera_name}> Too many failures, trying to reset")
                    self._camera_list[camera_name].reset()
                    number_not_published[camera_name] = 0

                    # After the reset, we may have a new camera stream, so update the config file
                    self.write_configuration_file()

        # Check to see if the process has terminated
        if self._subprocess.poll() is not None:
            self._log.error(f"RTSP process died")
            self._run_server()
            return

    def _get_base_file(self) -> str:
        """ Read the file and save the lines prior to our edits"""

        prefix: str = ''
        with open(self._config_filename, 'r') as file:
            for line in file.readlines():
                prefix = prefix + line
                if line == self._seperator:
                    break

        file.close()
        return prefix

    def write_configuration_file(self):
        """ Write the file with all the camera information """

        prefix = self._get_base_file()
        file_contents = str()
        for camera_name in sorted(self._camera_list.keys()):
            camera = self._camera_list[camera_name]
            file_contents = f"{file_contents}\n  {camera.legal_camera_name}:\n    source: {camera.stream_url}\n"
        with open(self._config_filename, "w") as file:
            file.write(prefix + file_contents)

    def terminate(self) -> None:
        """ Indicate that the threads should terminate """
        self._log.warning(f"RTSP Terminating")
        self._terminate_signal.set()

    @property
    def status(self) -> dict:
        return self._status

    @property
    def config_filename(self) -> str:
        return self._config_filename
