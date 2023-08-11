
import configparser
import os
from google_nest_camera_proxy.rtsp_server import RTSPServer


def test_rtsp_server():
        configfile = f"{os.path.dirname(__file__)}/test-config"
        configuration = configparser.ConfigParser()
        configuration.read(configfile)
        rtsp = RTSPServer(configuration)
        assert rtsp is not None


if __name__ == "__main__":
    test_rtsp_server()