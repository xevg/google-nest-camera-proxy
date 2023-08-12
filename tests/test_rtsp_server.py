import configparser
import os
import time
from google_nest_camera_proxy.rtsp_server import RTSPServer
import pytest


@pytest.mark.slow
def test_rtsp_server():
    configfile = f"{os.path.expanduser('~')}/.config/nest/config"
    configuration = configparser.ConfigParser()
    configuration.read(configfile)
    rtsp = RTSPServer(configuration)
    assert rtsp is not None

    rtsp.run()
    time.sleep(2)  # Let the process start
    assert rtsp._subprocess.poll() is None
    rtsp.terminate()


if __name__ == "__main__":
    test_rtsp_server()
