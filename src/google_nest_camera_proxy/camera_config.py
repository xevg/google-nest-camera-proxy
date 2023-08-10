""" Manage the configuration file"""

import logging
from camera import Camera
from colorama import Fore
from colorama import Style
from filelogger import FileLogger


class ManageConfigurationFile:
    """ Manage the configuration file for the RSTP server """

    def __init__(self, file_logger: FileLogger) -> None:
        self._camera_list = {}
        self._logger = logging.getLogger(__name__)
        self._file_logger = file_logger

    @staticmethod
    def _get_legal_camera_name(name: str) -> str:
        legal_characters = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_.~-/"

        get_vals = list(filter(lambda x: x in legal_characters, name))
        return "".join(get_vals)

    def add_camera(self, camera: Camera) -> None:
        """ Add a camera to the list """

        legal_camera_name = self._get_legal_camera_name(camera.name)
        config_string = f'  {legal_camera_name}:\n    source: {camera.stream_url}\n'
        self._camera_list[legal_camera_name] = {'camera': camera}
        if camera.stream_url is None:
            self._logger.info(f"{Fore.LIGHTCYAN_EX}Skipping camera {camera_name}{Style.RESET_ALL}")
            self._file_logger.log(__name__, 'skipping', f'Skipping camera {camera_name}')
            self._camera_list[legal_camera_name]['skip'] = True
            self._camera_list[legal_camera_name]['updated'] = False
            return

        self._camera_list[legal_camera_name]['stream'] = camera.stream_url
        self._camera_list[legal_camera_name]['config_string'] = config_string
        self._camera_list[legal_camera_name]['updated'] = True

        return

    def update_camera(self, camera: Camera) -> None:
        """ Update a camera """

        legal_camera_name = self._get_legal_camera_name(camera.name)
        if self._camera_list[legal_camera_name]['stream'] == camera.stream_url:
            # Nothing has changed
            return

        self.add_camera(camera)

    def total_skipped(self) -> int:
        """ Return the number of skipped cameras"""
        skipped = 0
        for camera in self._camera_list:
            if camera['skipped']:
                skipped += 1

        return skipped

        """
        
           suffix_string = ''
    total_skipped = 0
    for camera_name in sorted(camera_list.keys()):
        # Remove the illegal characters from the camera name
        #  can contain only alphanumeric characters, underscore, dot, tilde, minus or slash
        

        
        else:
            _LOGGER.info(f"{Fore.LIGHTCYAN_EX}Skipping camera {camera_name}{Style.RESET_ALL}")
            file_logger.log(__name__, 'skipping', f'Skipping camera {camera_name}')
            total_skipped += 1

    if total_skipped > 2:
        cycle_count = 100  # If we are missing cameras, rescan all of them
        _LOGGER.info(f"{Fore.RED}{total_skipped} cameras skipped, rescanning ...{Style.RESET_ALL}")
        file_logger.log(__name__, 'skipping', f'Skipped {total_skipped} camera. Rescanning.')

    else:
        if total_skipped != 0:
            _LOGGER.info(f"{Fore.LIGHTCYAN_EX}{total_skipped} cameras skipped.{Style.RESET_ALL}")
            file_logger.log(__name__, 'skipping', f'Skipped {total_skipped} camera(s)')

    if suffix_string != previous_suffix_string:
        _LOGGER.info(f"{Fore.BLUE}Updating RTSP file{Style.RESET_ALL}")
        file_logger.log(__name__, 'update', 'Updating RTSP file')
        RTSPServer().write_file(suffix_string)
        previous_suffix_string = suffix_string

    cycle_count += 1
    _LOGGER.info(f"Supplying the following cameras (#{cycle_count}): {','.join(camera_list.keys())}")
    file_logger.log(__name__, 'camera list', f"{','.join(camera_list.keys())}")


        """
