from google_nest_camera_proxy import GoogleNestCameraProxy
import os
import time
import pytest


@pytest.mark.slow
@pytest.mark.xfail
def test_proxy():
    proxy = GoogleNestCameraProxy(f"{os.path.expanduser('~')}/.config/nest/config")
    assert len(proxy.camera_list) > 5
    assert proxy.rtsp_server is not None
    proxy.terminate()
    time.sleep(2)


if __name__ == "__main__":
    test_proxy()