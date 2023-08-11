# read version from installed package
from importlib.metadata import version
__version__ = version("google_nest_camera_proxy")

from google_nest_camera_proxy import google_nest_camera_proxy
google_nest_camera_proxy.google_nest_camera_proxy()
