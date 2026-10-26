from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("video2psp")
except PackageNotFoundError:
    __version__ = "unknown"
