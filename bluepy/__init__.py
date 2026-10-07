# The package version; setup.py reads it from here
__version__ = '1.4.0'

from . import btle
from . import sensortag
from . import thingy52
__all__ = ["btle", "sensortag", "thingy52"]
