import logging
import os
import time

import click

from .google_nest_camera_proxy import GoogleNestCameraProxy


@click.command()
@click.option(
    "-c",
    "--configuration-file",
    type=click.Path(exists=True),
    default=f"{os.path.expanduser('~')}/.config/nest/config",
    help="Where the configuration for this program is located",
)
@click.option("-v", "--verbose", is_flag=True, help="Turn on informational output")
@click.option("-d", "--debug", is_flag=True, help="Turn on debugging output")
@click.option(
    "-n",
    "--no-server",
    is_flag=True,
    help="Update the file, but do not run MediaMTX as a subprocess",
)
def run(configuration_file, debug, no_server, verbose) -> None:
    """Configure MediaMTX and keep all supported Nest camera streams active."""
    logging_format = "%(asctime)s <%(name)s> %(message)s"
    logging_dateformat = "%m/%d/%Y %I:%M:%S %p"
    if debug:
        logging_level = logging.DEBUG
    elif verbose:
        logging_level = logging.INFO
    else:
        logging_level = logging.WARNING

    logging.basicConfig(
        level=logging_level, format=logging_format, datefmt=logging_dateformat
    )
    if debug:
        # These dependencies include bearer / refresh tokens in DEBUG output.
        # Keep WebRTC internals verbose without leaking SDM credentials.
        for sensitive_logger in (
            "requests_oauthlib.oauth2_session",
            "urllib3.connectionpool",
            "nest.nest",
        ):
            logging.getLogger(sensitive_logger).setLevel(logging.WARNING)
    logger = logging.getLogger(__name__)
    logger.info("Starting the program")

    proxy = GoogleNestCameraProxy(
        configuration_file=configuration_file, no_server=no_server
    )
    try:
        proxy.run()
        while True:
            time.sleep(15)
            if not no_server:
                status_lines = []
                for camera in sorted(proxy.camera_list):
                    name = camera.legal_camera_name
                    status = proxy.rtsp_server.status.get(name, "Initializing")
                    status_lines.append(f"{name:>25}: {status}")
                logger.info("\n%s\n", "\n".join(status_lines))
    except KeyboardInterrupt:
        logger.warning("Stopping at user request")
    finally:
        proxy.terminate()


if __name__ == "__main__":
    run()
