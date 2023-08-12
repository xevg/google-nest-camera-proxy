# read version from installed package
from importlib.metadata import version
__version__ = version("google_nest_camera_proxy")

from .google_nest_camera_proxy import GoogleNestCameraProxy
from .__main__ import run


if __name__ == "__main__":
    run()

