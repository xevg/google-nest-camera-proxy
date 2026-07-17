# rtsp_server.py
import configparser
import logging
import os
import re
import subprocess
import threading

from .camera import Camera


class RTSPServer:
    """Manage MediaMTX and its per-camera paths."""

    def __init__(self, configuration: configparser.ConfigParser) -> None:
        self._configuration = configuration
        self._camera_list = {}
        self._status = {}
        self._write_lock = threading.Lock()
        self._separator = "# NEST EDITS BELOW -- DO NOT EDIT THIS LINE OR BELOW\n"

        self._config_filename = self._configuration.get(
            "RTSP_SERVER",
            "config_filename",
            fallback=f"{os.path.expanduser('~')}/.config/nest/rtsp.yml",
        )
        self._executable = configuration.get("RTSP_SERVER", "executable")
        self._logger = logging.getLogger("RTSP Server")

        self._terminate_signal = threading.Event()
        self._server_started = threading.Event()
        self._server_start_error = None
        self._rtsp_thread = None
        self._subprocess = None

        self._update_thread = threading.Thread(
            target=self._update_configuration,
            name="RTSP Configuration Update",
        )
        self._update_thread.start()

    def run(self):
        self._rtsp_thread = threading.Thread(
            target=self._run_server, name="RTSP Server"
        )
        self._rtsp_thread.start()
        if not self._server_started.wait(timeout=10):
            raise RuntimeError("MediaMTX did not start within 10 seconds")
        if self._server_start_error is not None:
            raise RuntimeError("MediaMTX could not be started") from self._server_start_error

    def add_camera(self, camera: Camera) -> None:
        self._camera_list[camera.legal_camera_name] = camera

    def _update_configuration(self):
        if self._terminate_signal.wait(120):
            return

        while not self._terminate_signal.is_set():
            needs_update = False
            for camera in self._camera_list.values():
                if camera.stream_reset:
                    needs_update = True
                    camera.stream_reset = False
            if needs_update:
                self.write_configuration_file()
            else:
                self._logger.info("No changes to configuration file needed")
            self._terminate_signal.wait(60)

    def _run_server(self):
        self._logger.warning("Starting MediaMTX")
        re_not_publishing = re.compile(r"no one is publishing to path '([^']*)'")
        re_source_ready = re.compile(r"\[path ([^\]]*)\].*\bready\b")
        # Avoid matching the suffix of "no one is publishing to path".
        re_publishing_to_path = re.compile(
            r"(?<!no one )is publishing to path '([^']*)'"
        )
        re_reading_from_path = re.compile(r"is reading from path '([^']*)'")

        number_not_published = {}
        for camera in self._camera_list.values():
            number_not_published[camera.legal_camera_name] = 0
            self._status[camera.legal_camera_name] = "Initializing"

        self.write_configuration_file()

        try:
            self._subprocess = subprocess.Popen(
                [self._executable, self._config_filename],
                stderr=subprocess.STDOUT,
                stdout=subprocess.PIPE,
                # Do not let a terminal Ctrl-C kill MediaMTX before the parent
                # has stopped camera publishers and set its terminate signal.
                start_new_session=True,
            )
        except Exception as error:
            self._server_start_error = error
            self._server_started.set()
            self._logger.exception("Could not start MediaMTX")
            return
        self._server_start_error = None
        self._server_started.set()

        while not self._terminate_signal.is_set():
            if self._subprocess.poll() is not None:
                self._logger.error("MediaMTX process died")
                if not self._terminate_signal.is_set():
                    self._server_started.clear()
                    self._run_server()
                return

            line_bytes = self._subprocess.stdout.readline()
            if not line_bytes:
                continue
            line = line_bytes.decode("utf-8", errors="replace").strip()
            self._logger.info("MediaMTX: %s", line)

            match = re_not_publishing.search(line)
            if match:
                camera_name = match.group(1)
                if camera_name not in self._camera_list:
                    self._logger.error(
                        "Configuration error: no such camera %s", camera_name
                    )
                else:
                    self._status[camera_name] = "Not Publishing"
                    number_not_published[camera_name] += 1
                    self._logger.warning(
                        "<%s> no one publishing; failure count is %s",
                        camera_name,
                        number_not_published[camera_name],
                    )

            match = re_source_ready.search(line) or re_publishing_to_path.search(line)
            if match:
                camera_name = match.group(1)
                if camera_name in self._camera_list:
                    attempts = number_not_published.get(camera_name, 0)
                    self._status[camera_name] = "Publishing"
                    number_not_published[camera_name] = 0
                    self._logger.warning(
                        "<%s> started publishing after %s attempts",
                        camera_name,
                        attempts,
                    )

            match = re_reading_from_path.search(line)
            if match:
                camera_name = match.group(1)
                if camera_name in self._camera_list:
                    self._logger.warning(
                        "<%s> someone started reading the stream", camera_name
                    )
                    self._status[camera_name] = "Streaming"
                    number_not_published.setdefault(camera_name, 0)

            for camera_name in list(number_not_published):
                if number_not_published[camera_name] > 5:
                    self._status[camera_name] = "Resetting"
                    self._logger.warning(
                        "<%s> too many failures; resetting stream", camera_name
                    )
                    self._camera_list[camera_name].reset()
                    number_not_published[camera_name] = 0
                    # RTSP can receive a new URL. WebRTC remains source:
                    # publisher, so this rewrite is harmless.
                    self.write_configuration_file()

        if self._subprocess.poll() is None:
            self._subprocess.terminate()

    def _get_base_file(self) -> str:
        prefix = ""
        found_separator = False
        with open(self._config_filename, "r") as config_file:
            for line in config_file:
                prefix += line
                if line == self._separator:
                    found_separator = True
                    break

        if not found_separator:
            prefix += self._separator
        return prefix

    def write_configuration_file(self):
        self._logger.info("Writing MediaMTX configuration file")
        with self._write_lock:
            try:
                prefix = self._get_base_file()
                camera_paths = ""
                for camera_name in sorted(self._camera_list):
                    camera = self._camera_list[camera_name]
                    camera_paths += (
                        f"\n"
                        f"  {camera.legal_camera_name}:\n"
                        f"    source: {camera.stream_url}\n\n"
                    )
                with open(self._config_filename, "w") as config_file:
                    config_file.write(prefix + camera_paths)
            except Exception as error:
                self._logger.error("Failed to write configuration file: %r", error)

    def terminate(self) -> None:
        if self._terminate_signal.is_set():
            return
        self._logger.warning("MediaMTX terminating")
        self._terminate_signal.set()
        if self._subprocess is not None and self._subprocess.poll() is None:
            self._subprocess.terminate()
        if (
            self._rtsp_thread is not None
            and self._rtsp_thread.is_alive()
            and threading.current_thread() is not self._rtsp_thread
        ):
            self._rtsp_thread.join(timeout=10)
        if self._update_thread.is_alive():
            self._update_thread.join(timeout=2)

    @property
    def status(self) -> dict:
        return self._status

    @property
    def config_filename(self) -> str:
        return self._config_filename
