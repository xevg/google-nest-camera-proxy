import click
import logging
import time
import os
from .google_nest_camera_proxy import GoogleNestCameraProxy


@click.command()
@click.option('-c', '--configuration-file', type=click.Path(exists=True),
              default=f"{os.path.expanduser('~')}/.config/nest/config",
              help="Where the configuration for this program is located")
@click.option('-v', '--verbose', is_flag=True, help="Turn on more informational output")
@click.option('-d', '--debug', is_flag=True, help="Turn on debugging output")
@click.option('-n', '--no-server', is_flag=True,
              help="Update the file, but don't run the mediamtx server as a subprocess")
def run(configuration_file, debug, no_server, verbose) -> None:
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

    logging_format = '%(asctime)s <%(name)s> %(message)s'
    logging_dateformat = '%m/%d/%Y %I:%M:%S %p'
    if debug:
        logging_level = logging.DEBUG
    elif verbose:
        logging_level = logging.INFO
    else:
        logging_level = logging.WARNING

    logging.basicConfig(level=logging_level, format=logging_format, datefmt=logging_dateformat)
    _logger = logging.getLogger(__name__)
    _logger.info("Starting the program")

    proxy = GoogleNestCameraProxy(configuration_file=configuration_file, no_server=no_server)
    proxy.run()

    # Now wait till all threads end or until someone hits 'q'
    _logger.debug("Program chugging away ...")

    while True:
        time.sleep(15)
        if not no_server:
            out_string = str()
            for camera in sorted(proxy.camera_list):
                name = camera.legal_camera_name
                out_string = f"{out_string}\n{name:>25}: {proxy.rtsp_server.status[name]}"
            _logger.info(f"{out_string}\n")


if __name__ == "__main__":
    run()
